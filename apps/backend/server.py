#!/usr/bin/env python3
"""Local review API with explicitly requested video generation; no implicit SNS publishing."""
import argparse
import contextlib
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import uuid

ROOT = Path(__file__).resolve().parents[2]
DISCLOSURE = "AI로 만든 가상 인물의 창작 일상입니다."


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


sys.path.insert(0, str(Path(__file__).resolve().parent))
from automation import AutomationStore
from studio import StudioStore
from segmind_video import VideoStore
from production_media import ProductionMediaStore
from video_library import VideoLibrary
from local_worker import LocalProductionWorker


class Store(VideoLibrary, ProductionMediaStore, VideoStore, StudioStore, AutomationStore):
    problem = Problem

    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.runtime = self.root / ".runtime"
        self.media = self.runtime / "media"
        self.media.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runtime / "boca.sqlite3"
        self.token_path = self.runtime / "access-token"
        if not self.token_path.exists():
            try:
                fd = os.open(str(self.token_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(secrets.token_urlsafe(32))
            except FileExistsError:
                pass
        self.token = self.token_path.read_text().strip()
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS contents (
                    id TEXT PRIMARY KEY, current_version INTEGER NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    content_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, author TEXT NOT NULL, kind TEXT NOT NULL,
                    ingest_key TEXT UNIQUE, created_at TEXT NOT NULL,
                    PRIMARY KEY (content_id, version)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    content_id TEXT NOT NULL, version INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL, approved_at TEXT NOT NULL,
                    PRIMARY KEY (content_id, version)
                );
                CREATE TABLE IF NOT EXISTS publications (
                    content_id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL, account TEXT, status TEXT NOT NULL,
                    claim_id TEXT, permalink TEXT, detail TEXT, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, stage TEXT NOT NULL, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 2,
                    input_json TEXT NOT NULL, result_json TEXT, external_job_id TEXT,
                    error TEXT, updated_at TEXT NOT NULL
                );
            """)
        self.init_automation()
        self.init_studio()
        self.init_video()
        self.sync_production_artifacts()

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        committed = False
        changed = False
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            if db.in_transaction:
                db.commit()
            committed = True
            changed = db.total_changes > 0
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()
        if committed and changed and hasattr(self, "sync_production_artifacts"):
            try:
                self.sync_production_artifacts()
                self.artifact_sync_error = None
            except (OSError, sqlite3.Error) as exc:
                # SQLite remains the source of truth; the next read/start reconciles files.
                self.artifact_sync_error = str(exc)

    def _content(self, db, content_id):
        row = db.execute("SELECT * FROM contents WHERE id=?", (content_id,)).fetchone()
        if row is None:
            raise Problem("콘텐츠를 찾을 수 없습니다.", 404)
        revision = db.execute("SELECT * FROM revisions WHERE content_id=? AND version=?",
                              (content_id, row["current_version"])).fetchone()
        result = dict(row)
        result.update(payload=json.loads(revision["payload"]), fingerprint=revision["fingerprint"])
        result["persona_id"] = result["payload"].get("persona_id") or self._original_persona()["id"]
        publication = db.execute("SELECT * FROM publications WHERE content_id=?", (content_id,)).fetchone()
        result["publication"] = dict(publication) if publication else None
        result["proposals"] = db.execute("SELECT COUNT(*) FROM revisions WHERE content_id=? AND kind='proposal'",
                                         (content_id,)).fetchone()[0]
        return result

    def state(self):
        with self.db() as db:
            ids = db.execute("SELECT id FROM contents ORDER BY created_at DESC").fetchall()
            jobs = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT 100")]
            for job in jobs:
                job["input"] = json.loads(job.pop("input_json"))
                result = job.pop("result_json")
                job["result"] = json.loads(result) if result else None
            state = {"contents": [self._content(db, r["id"]) for r in ids], "jobs": jobs,
                     "config": self.config(), "persona": self.persona()}
        state["automation"] = self.automation_state()
        state["studio"] = self.studio_state()
        state["automation"]["artifact_sync_error"] = getattr(self, "artifact_sync_error", None)
        return state

    def _validate(self, payload, imported=False, allow_empty_media=False):
        data = json.loads(encode(payload))
        if not isinstance(data, dict):
            raise Problem("콘텐츠는 JSON 객체여야 합니다.")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", data.get("id", "")):
            raise Problem("콘텐츠 id에는 영문·숫자·하이픈·밑줄만 사용할 수 있습니다.")
        for field in ["title", "caption", "topic_key"]:
            if not isinstance(data.get(field), str) or not data[field].strip():
                raise Problem(field + " 값이 필요합니다.")
        hashtags = data.get("hashtags", [])
        if not isinstance(hashtags, list) or any(not isinstance(h, str) for h in hashtags):
            raise Problem("해시태그는 문자열 목록이어야 합니다.")
        public_text = data["caption"] + " " + " ".join(hashtags)
        compact = re.sub(r"[\s._-]", "", public_text).lower()
        if any(term in compact for term in ["gsshop", "gs샵", "gs숍", "gs쇼핑", "지에스샵", "지에스숍"]):
            raise Problem("공개 문안·해시태그에 GS SHOP 판매처명이 포함되어 있습니다.")
        if DISCLOSURE not in data["caption"]:
            raise Problem("문안에 가상 인물 표시를 유지해 주세요: " + DISCLOSURE)
        data["persona_id"] = self.content_persona_id(data)
        self.persona_revision(data["persona_id"], data.get("persona_version"))
        cards = data.get("cards")
        if not isinstance(cards, list) or (not cards and not allow_empty_media):
            raise Problem("검토할 이미지 또는 영상이 필요합니다.")
        for card in cards:
            if not isinstance(card, dict) or not isinstance(card.get("alt"), str):
                raise Problem("각 카드의 설명(alt)이 필요합니다.")
            if imported:
                source = (self.root / card.get("media", "")).resolve()
                if self.root not in source.parents or not source.is_file():
                    raise Problem("미디어는 프로젝트 안에 존재하는 파일이어야 합니다.")
                if source.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp", ".mp4"]:
                    raise Problem("지원하지 않는 미디어 형식입니다.")
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                filename = digest + source.suffix.lower()
                dest = self.media / filename
                if not dest.exists():
                    temp = self.media / (filename + "." + uuid.uuid4().hex + ".tmp")
                    shutil.copyfile(source, temp)
                    os.replace(temp, dest)
                card["media"] = filename
                card["sha256"] = digest
            self._verify_media(card)
        sources = data.get("sources", [])
        if not isinstance(sources, list):
            raise Problem("sources는 목록이어야 합니다.")
        for source in sources:
            if not isinstance(source, dict):
                raise Problem("각 출처는 URL과 확인일을 담은 JSON 객체여야 합니다.")
            if not isinstance(source.get("url"), str):
                raise Problem("상품 출처의 HTTPS URL이 필요합니다.")
            try:
                parsed = urlparse(source["url"])
            except ValueError:
                raise Problem("상품 출처의 HTTPS URL 형식을 확인해 주세요.")
            if parsed.scheme != "https" or not parsed.hostname:
                raise Problem("상품 출처의 HTTPS URL이 필요합니다.")
            try:
                checked = datetime.fromisoformat(source["checked_at"])
                if checked.tzinfo is None:
                    raise ValueError()
                if source.get("expires_at"):
                    expires = datetime.fromisoformat(source["expires_at"])
                    if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
                        raise Problem("유효기간이 지났거나 확인되지 않은 상품 정보입니다.")
            except (KeyError, ValueError, TypeError):
                raise Problem("출처 확인일은 시간대를 포함하는 ISO 날짜여야 합니다.")
        data["hashtags"] = hashtags
        data["sources"] = sources
        return data

    def _verify_media(self, card):
        filename = card.get("media", "")
        if not re.fullmatch(r"[a-f0-9]{64}\.(jpg|jpeg|png|webp|mp4)", filename):
            raise Problem("저장된 미디어 참조가 올바르지 않습니다.")
        path = self.media / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != card.get("sha256"):
            raise Problem("승인 대상 미디어가 변경되었거나 사라졌습니다.", 409)

    def _revision(self, db, payload, author, kind, ingest_key=None):
        content_id = payload["id"]
        version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM revisions WHERE content_id=?",
                             (content_id,)).fetchone()[0]
        encoded = encode(payload)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)",
                   (content_id, version, encoded, fingerprint, author, kind, ingest_key, now()))
        return version, fingerprint

    def ingest(self, payload, expected_version=0):
        payload = self._validate(payload, imported=True)
        with self.db() as db:
            cycle = db.execute("SELECT result_json FROM production_cycles WHERE content_id=?", (payload["id"],)).fetchone()
            handoff = json.loads(cycle["result_json"]).get("review_handoff", {}) if cycle else {}
            if handoff.get("ai_quality_review") == "deferred":
                notes = payload.get("review_notes", [])
                if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
                    raise Problem("검수 메모는 문자열 목록이어야 합니다.")
                payload["review_notes"] = list(dict.fromkeys(notes + handoff["notes"]))
                payload["review_handoff"] = handoff
            key = hashlib.sha256(encode(payload).encode()).hexdigest()
            existing = db.execute("SELECT * FROM revisions WHERE ingest_key=?", (key,)).fetchone()
            if existing:
                return {"id": existing["content_id"], "version": existing["version"],
                        "proposal": existing["kind"] == "proposal", "duplicate": True}
            current = db.execute("SELECT * FROM contents WHERE id=?", (payload["id"],)).fetchone()
            if current:
                previous = json.loads(db.execute("SELECT payload FROM revisions WHERE content_id=? AND version=?",
                                                 (payload["id"], current["current_version"])).fetchone()[0])
                owner = previous.get("persona_id") or self._original_persona()["id"]
                if owner != payload["persona_id"]:
                    raise Problem("기존 콘텐츠의 페르소나를 변경할 수 없습니다. 새 콘텐츠로 생성해 주세요.", 409)
            cycle_run = db.execute("SELECT r.persona_id,r.persona_version,r.settings_json FROM production_cycles c JOIN production_runs r ON r.id=c.run_id WHERE c.content_id=?",
                                   (payload["id"],)).fetchone()
            if cycle_run and (payload["persona_id"] != cycle_run["persona_id"] or payload["persona_version"] != cycle_run["persona_version"]):
                raise Problem("제작 실행에 고정된 페르소나와 버전이 일치하지 않습니다.", 409)
            if cycle_run:
                self.require_run_media(json.loads(cycle_run["settings_json"]), [card["media"] for card in payload["cards"]])
            proposal = bool(current and (current["current_version"] != expected_version or
                                        current["status"] != "ready"))
            if not current and expected_version != 0:
                raise Problem("생성 시작 시점의 콘텐츠 버전을 찾을 수 없습니다.", 409)
            version, _ = self._revision(db, payload, "ai", "proposal" if proposal else "current", key)
            if not current:
                db.execute("INSERT INTO contents VALUES (?,?,'ready',?,?)", (payload["id"], version, now(), now()))
            elif not proposal:
                db.execute("UPDATE contents SET current_version=?,status='ready',updated_at=? WHERE id=?",
                           (version, now(), payload["id"]))
            return {"id": payload["id"], "version": version, "proposal": proposal, "duplicate": False}

    def edit(self, content_id, body):
        with self.db() as db:
            current = self._content(db, content_id)
            if current["current_version"] != body.get("base_version"):
                raise Problem("다른 변경이 저장되었습니다. 새로고침 후 다시 수정해 주세요.", 409)
            if current["status"] in ["posting", "published", "uncertain"]:
                raise Problem("게시 중이거나 게시 결과 확인이 필요한 콘텐츠는 수정할 수 없습니다.", 409)
            original = encode(current["payload"])
            payload = json.loads(original)
            for field in ["title", "caption", "hashtags"]:
                if field in body:
                    payload[field] = body[field]
            payload = self._validate(payload)
            if encode(payload) == original:
                return current
            version, _ = self._revision(db, payload, "human", "current")
            db.execute("UPDATE contents SET current_version=?,status='ready',updated_at=? WHERE id=?",
                       (version, now(), content_id))
            db.execute("UPDATE publications SET status='superseded',updated_at=? WHERE content_id=?",
                       (now(), content_id))
            return self._content(db, content_id)

    def decide(self, content_id, version, approve):
        with self.db() as db:
            current = self._content(db, content_id)
            if current["current_version"] != version:
                raise Problem("현재 보고 있는 버전이 최신 버전이 아닙니다.", 409)
            if current["status"] in ["posting", "published", "uncertain"]:
                raise Problem("이미 게시 처리 중이거나 게시 결과 확인이 필요합니다.", 409)
            if approve:
                self._validate(current["payload"])
                db.execute("INSERT OR REPLACE INTO approvals VALUES (?,?,?,?)",
                           (content_id, version, current["fingerprint"], now()))
                account = self.config()["instagram"].get("account")
                db.execute("INSERT OR REPLACE INTO publications VALUES (?,?,?,?, 'queued',NULL,NULL,NULL,?)",
                           (content_id, version, current["fingerprint"], account, now()))
            else:
                db.execute("DELETE FROM approvals WHERE content_id=? AND version=?", (content_id, version))
                db.execute("UPDATE publications SET status='rejected',updated_at=? WHERE content_id=?", (now(), content_id))
            db.execute("UPDATE contents SET status=?,updated_at=? WHERE id=?",
                       ("approved" if approve else "rejected", now(), content_id))
            return self._content(db, content_id)

    def claim_publication(self, account):
        config = self.config()
        settings = config["instagram"]
        if not account or settings.get("account") != account or settings.get("connection") != "verified":
            raise Problem("게시 계정 연결을 먼저 확인해야 합니다.", 409)
        if datetime.now(timezone.utc) < datetime.fromisoformat(config["publish_not_before"]):
            raise Problem("내일 아침 게시 시작 시간 전입니다. 승인 상태로 보관합니다.", 409)
        with self.db() as db:
            rows = db.execute("SELECT * FROM publications WHERE status='queued' ORDER BY updated_at").fetchall()
            for publication in rows:
                current = self._content(db, publication["content_id"])
                approval = db.execute("SELECT * FROM approvals WHERE content_id=? AND version=?",
                                      (current["id"], current["current_version"])).fetchone()
                if current["status"] != "approved" or not approval or approval["fingerprint"] != current["fingerprint"]:
                    continue
                if publication["version"] != current["current_version"] or publication["fingerprint"] != current["fingerprint"]:
                    continue
                if publication["account"] not in [None, account]:
                    raise Problem("승인 시점의 게시 계정과 다릅니다.", 409)
                try:
                    self._validate(current["payload"])
                except Problem as exc:
                    if exc.status not in (400, 409):
                        raise
                    # A stale source or changed media must return to review,
                    # without holding up unrelated approved publications.
                    db.execute("UPDATE publications SET status='blocked',detail=?,updated_at=? WHERE content_id=?",
                               (str(exc), now(), current["id"]))
                    db.execute("UPDATE contents SET status='ready',updated_at=? WHERE id=?",
                               (now(), current["id"]))
                    self._event(db, None, None, "publish", "publication.blocked",
                                "게시 전 검증에 실패해 콘텐츠를 검수 대기로 돌렸습니다.",
                                {"content_id": current["id"], "version": current["current_version"],
                                 "fingerprint": current["fingerprint"], "reason": str(exc)}, "warning")
                    continue
                claim_id = secrets.token_hex(16)
                db.execute("UPDATE publications SET status='sending',claim_id=?,account=?,updated_at=? WHERE content_id=?",
                           (claim_id, account, now(), current["id"]))
                db.execute("UPDATE contents SET status='posting',updated_at=? WHERE id=?", (now(), current["id"]))
                return {"content": current, "claim_id": claim_id, "account": account,
                        "media_paths": [str(self.media / c["media"]) for c in current["payload"]["cards"]]}
            return None

    def finish_publication(self, claim_id, status, permalink=None, detail=None):
        if status not in ["published", "uncertain", "failed_before_publish"]:
            raise Problem("올바르지 않은 게시 결과입니다.")
        if status == "published" and (not isinstance(permalink, str) or
            not re.fullmatch(r"https://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?", permalink)):
            raise Problem("실제 Instagram 게시물 링크가 필요합니다.")
        with self.db() as db:
            row = db.execute("SELECT * FROM publications WHERE claim_id=?", (claim_id,)).fetchone()
            if not row or row["status"] not in ["sending", "uncertain"]:
                raise Problem("유효한 게시 작업을 찾을 수 없습니다.", 409)
            if row["status"] == "uncertain" and status == "failed_before_publish":
                raise Problem("결과가 불확실한 게시는 자동 재시도할 수 없습니다.", 409)
            content_status = {"published": "published", "uncertain": "uncertain", "failed_before_publish": "approved"}[status]
            publication_status = "queued" if status == "failed_before_publish" else status
            db.execute("UPDATE publications SET status=?,permalink=?,detail=?,updated_at=? WHERE claim_id=?",
                       (publication_status, permalink, detail, now(), claim_id))
            db.execute("UPDATE contents SET status=?,updated_at=? WHERE id=?",
                       (content_status, now(), row["content_id"]))
            return {"id": row["content_id"], "status": content_status}

    def add_job(self, job_id, stage, payload, max_attempts=2):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", job_id) or not 1 <= max_attempts <= 3:
            raise Problem("작업 id 또는 재시도 한도가 올바르지 않습니다.")
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO jobs (id,stage,status,input_json,max_attempts,updated_at) VALUES (?,?,'pending',?,?,?)",
                       (job_id, stage, encode(payload), max_attempts, now()))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def update_job(self, job_id, action, result=None, external_id=None, error=None):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise Problem("작업을 찾을 수 없습니다.", 404)
            if row["run_id"]:
                raise Problem("자동 생성 작업은 worker 명령으로만 갱신할 수 있습니다.", 409)
            if action == "claim":
                if row["status"] not in ["pending", "failed"] or row["attempts"] >= row["max_attempts"]:
                    raise Problem("이미 실행 중이거나 재시도 한도를 넘은 작업입니다.", 409)
                db.execute("UPDATE jobs SET status='running',attempts=attempts+1,error=NULL,updated_at=? WHERE id=?", (now(), job_id))
            elif action in ["complete", "fail", "uncertain", "external"]:
                if row["status"] not in ["running", "uncertain"]:
                    raise Problem("실행 중인 작업이 아닙니다.", 409)
                if action == "fail" and row["status"] == "uncertain":
                    raise Problem("불확실한 외부 작업은 확인 없이 재시도할 수 없습니다.", 409)
                status = {"complete": "completed", "fail": "failed", "uncertain": "uncertain", "external": row["status"]}[action]
                db.execute("UPDATE jobs SET status=?,result_json=COALESCE(?,result_json),external_job_id=COALESCE(?,external_job_id),error=?,updated_at=? WHERE id=?",
                           (status, encode(result) if result is not None else None, external_id, error, now(), job_id))
            else:
                raise Problem("알 수 없는 작업 명령입니다.")
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def send_data(self, value, status=200):
            data = encode(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
            super().end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                artifact_match = re.fullmatch(r"/api/runs/([A-Za-z0-9_-]+)/(artifacts|logs)", path)
                stage_match = re.fullmatch(r"/api/runs/([A-Za-z0-9_-]+)/stages/([A-Za-z0-9_-]+)/([a-z]+)", path)
                stage_media_match = re.fullmatch(r"/api/runs/([A-Za-z0-9_-]+)/stages/([A-Za-z0-9_-]+)/([a-z]+)/media/([0-9]+)", path)
                if artifact_match:
                    run_id, kind = artifact_match.groups()
                    if kind == "artifacts":
                        return self.send_data(store.describe_artifacts(run_id))
                    query = parse_qs(urlparse(self.path).query)
                    data, filename, mime = store.export_log(run_id, query.get("format", ["log"])[0])
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if stage_match:
                    return self.send_data(store.read_stage_result(*stage_match.groups()))
                if path == "/api/video":
                    return self.send_data(store.video_state())
                if path == "/api/video-library":
                    return self.send_data(store.video_library())
                if path == "/api/state":
                    state = store.state()
                    state["token"] = store.token
                    return self.send_data(state)
                if path == "/api/health":
                    return self.send_data({"status": "ok", "publisher_connected": store.config()["instagram"]["connection"] == "verified"})
                if path == "/api/logs":
                    query = parse_qs(urlparse(self.path).query)
                    return self.send_data({"logs": store.logs(query.get("run_id", [None])[0],
                                          query.get("after_id", [0])[0], query.get("limit", [100])[0])})
                export_match = re.fullmatch(r"/api/contents/([A-Za-z0-9_-]+)/export", path)
                if export_match:
                    from exporting import export_bundle
                    data, filename = export_bundle(store, export_match.group(1))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                portrait_match = re.fullmatch(r"/api/personas/([A-Za-z0-9_-]+)/portrait", path)
                video_media_match = re.fullmatch(r"/api/video/jobs/([A-Za-z0-9_-]+)/media", path)
                imported_video_match = re.fullmatch(r"/api/video-library/imported/([A-Za-z0-9_-]+)/([0-9]+)/([0-9]+)/media", path)
                static = {"/": "index.html", "/app.js": "app.js", "/production-guides.js": "production-guides.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg",
                          "/video": "video.html", "/video.js": "video.js", "/video.css": "video.css"}
                if video_media_match:
                    file = store.video_job_media_file(video_media_match.group(1))
                elif imported_video_match:
                    content_id, version, index = imported_video_match.groups()
                    file = store.imported_video_media_file(content_id, int(version), int(index))
                elif stage_media_match:
                    run_id, cycle_id, stage, index = stage_media_match.groups()
                    file = store.stage_media_file(run_id, cycle_id, stage, int(index))
                elif portrait_match:
                    file = store.persona_portrait(portrait_match.group(1))
                    if file is None:
                        raise Problem("저장된 페르소나 이미지가 없습니다.", 404)
                elif path in static:
                    file = store.root / "apps/dashboard" / static[path]
                elif path.startswith("/assets/"):
                    asset_root = (store.root / "apps/dashboard/assets").resolve()
                    file = (store.root / "apps/dashboard" / path.lstrip("/")).resolve()
                    if asset_root not in file.parents or file.suffix.lower() not in [".woff2", ".woff", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".txt"]:
                        raise Problem("허용되지 않은 정적 파일입니다.", 404)
                elif re.fullmatch(r"/media/[a-f0-9]{64}\.(jpg|jpeg|png|webp|mp4)", path):
                    file = store.media / path.split("/")[-1]
                else:
                    raise Problem("페이지를 찾을 수 없습니다.", 404)
                if not file.is_file():
                    raise Problem("파일을 찾을 수 없습니다.", 404)
                if file.suffix.lower() == ".mp4":
                    size = file.stat().st_size
                    start, end = 0, size - 1
                    requested = self.headers.get("Range")
                    if requested:
                        bounds = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                        if not bounds or not any(bounds.groups()):
                            raise Problem("지원하지 않는 영상 범위 요청입니다.", 416)
                        first, last = bounds.groups()
                        start = int(first) if first else max(0, size - int(last))
                        end = min(size - 1, int(last)) if first and last else size - 1
                        if start >= size or start > end:
                            self.send_response(416)
                            self.send_header("Content-Range", "bytes */" + str(size))
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                            return
                    self.send_response(206 if requested else 200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(end - start + 1))
                    if requested:
                        self.send_header("Content-Range", "bytes %s-%s/%s" % (start, end, size))
                    self.end_headers()
                    with file.open("rb") as stream:
                        stream.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            block = stream.read(min(1024 * 1024, remaining))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
                    return
                data = file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(file))[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Problem as exc:
                self.send_data({"error": str(exc)}, exc.status)
            except (ValueError, TypeError) as exc:
                self.send_data({"error": "요청 형식을 확인해 주세요: " + str(exc)}, 400)

        def do_POST(self):
            try:
                origin = self.headers.get("Origin")
                allowed = ["http://127.0.0.1:" + str(self.server.server_port), "http://localhost:" + str(self.server.server_port)]
                if origin and origin not in allowed:
                    raise Problem("다른 사이트의 변경 요청은 허용하지 않습니다.", 403)
                if not secrets.compare_digest(self.headers.get("X-BOCA-Token", ""), store.token):
                    raise Problem("로컬 인증이 필요합니다.", 403)
                length = int(self.headers.get("Content-Length", "0"))
                limit = 14_000_000 if urlparse(self.path).path == "/api/video/reference" else 2_000_000
                if not 0 < length <= limit:
                    raise Problem("요청 크기가 올바르지 않습니다.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise Problem("JSON 객체가 필요합니다.")
                path = urlparse(self.path).path
                video_match = re.fullmatch(r"/api/video/jobs/([A-Za-z0-9_-]+)/resume", path)
                guide_match = re.fullmatch(r"/api/video/guides/([A-Za-z0-9_-]+)(/delete)?", path)
                match = re.fullmatch(r"/api/contents/([A-Za-z0-9_-]+)/(edit|approve|reject)", path)
                run_match = re.fullmatch(r"/api/runs/([A-Za-z0-9_-]+)/(pause|resume|stop|deadline)", path)
                persona_match = re.fullmatch(r"/api/personas/([A-Za-z0-9_-]+)(/select|/references)?", path)
                brief_match = re.fullmatch(r"/api/briefs/([A-Za-z0-9_-]+)(/produce)?", path)
                if path == "/api/worker/video":
                    result = store.worker_video(body["cycle_id"], body["lease_token"])
                elif path == "/api/video/connect":
                    result = store.connect_video(body)
                elif path == "/api/video/reference":
                    result = store.upload_video_reference(body)
                elif path == "/api/video/guides":
                    result = store.save_video_guide(body)
                elif guide_match:
                    result = store.change_video_guide(guide_match.group(1), body, delete=bool(guide_match.group(2)))
                elif path == "/api/video/jobs":
                    result = store.create_video(body)
                elif video_match:
                    result = store.resume_video(video_match.group(1), body)
                elif match:
                    content_id, action = match.groups()
                    result = store.edit(content_id, body) if action == "edit" else store.decide(content_id, body.get("version"), action == "approve")
                elif path == "/api/contents/import":
                    result = store.ingest(body["content"], body.get("expected_version", 0))
                elif path == "/api/runs/start":
                    result = store.start_run(body)
                elif path == "/api/personas":
                    result = store.create_persona(body)
                elif persona_match:
                    persona_id, selection = persona_match.groups()
                    if selection == "/references":
                        result = store.save_persona_references(persona_id, body)
                    else:
                        result = store.select_persona(persona_id) if selection else store.update_persona(persona_id, body)
                elif path == "/api/briefs":
                    result = store.create_brief(body)
                elif brief_match:
                    brief_id, production = brief_match.groups()
                    result = store.produce_brief(brief_id) if production else store.update_brief(brief_id, body)
                elif path == "/api/settings":
                    result = store.update_settings(body)
                elif run_match:
                    result = store.update_run_deadline(run_match.group(1), body) if run_match.group(2) == "deadline" else store.control_run(*run_match.groups())
                elif path == "/api/sources":
                    result = store.upsert_source(body)
                elif path == "/api/worker/agent":
                    result = store.worker_agent(body["cycle_id"], body["lease_token"], body["agent_id"], body["role_id"], body.get("action", "assign"))
                elif path == "/api/worker/sources":
                    result = store.worker_sources(body["cycle_id"], body["lease_token"], body["result"])
                elif path == "/api/worker/next":
                    result = store.worker_next(body.get("worker_id", "codex"))
                elif path == "/api/worker/inspect":
                    result = store.worker_inspect(body.get("cycle_id"))
                elif path == "/api/worker/checkpoint":
                    if body.get("release") and body.get("external_idle") is not True:
                        raise Problem("진행 중인 외부 호출이 없음을 확인해야 작업을 넘길 수 있습니다.")
                    result = store.worker_checkpoint(body["cycle_id"], body["lease_token"], body["result"], body.get("release", False))
                elif path == "/api/worker/ping":
                    result = store.worker_ping(body["cycle_id"], body["lease_token"], body.get("external_job_id"))
                elif path == "/api/worker/log":
                    result = store.worker_log(body["cycle_id"], body["lease_token"], body["event"], body["message"], body.get("detail"), body.get("level", "info"))
                elif path == "/api/worker/complete":
                    result = store.worker_complete(body["cycle_id"], body["lease_token"], body["result"], body.get("external_job_id"))
                elif path == "/api/worker/fail":
                    result = store.worker_fail(body["cycle_id"], body["lease_token"], body["error"], body.get("retryable", True), body.get("uncertain", False))
                elif path == "/api/worker/repair":
                    result = store.worker_repair(body["cycle_id"], body["lease_token"], body["target_stage"], body["issues"])
                elif path == "/api/generation-requests":
                    brief = store.create_brief({"persona_id": body.get("persona_id"), "title": body.get("title", "일상과 취향을 담은 새 콘텐츠"),
                                                "brief": body.get("brief", ""), "format": body.get("format", "carousel"), "affiliate": body.get("affiliate", "")})
                    result = store.produce_brief(brief["id"])
                elif path == "/api/publishing/claim":
                    result = store.claim_publication(body.get("account"))
                elif path == "/api/publishing/result":
                    result = store.finish_publication(body.get("claim_id"), body.get("status"), body.get("permalink"), body.get("detail"))
                else:
                    raise Problem("API를 찾을 수 없습니다.", 404)
                if getattr(store, "production_worker", None):
                    store.production_worker.wake.set()
                self.send_data(result)
            except Problem as exc:
                self.send_data({"error": str(exc)}, exc.status)
            except (ValueError, KeyError, TypeError) as exc:
                self.send_data({"error": "요청 형식을 확인해 주세요: " + str(exc)}, 400)

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (now(), fmt % args))
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    sub.add_parser("state")
    start = sub.add_parser("run-start")
    start.add_argument("--start-at")
    start.add_argument("--end-at")
    start.add_argument("--persona-id")
    start.add_argument("--media-mode", choices=["images", "mixed", "video", "video_only"])
    control = sub.add_parser("run-control")
    control.add_argument("id")
    control.add_argument("action", choices=["pause", "resume", "stop"])
    defer_review = sub.add_parser("run-defer-quality")
    defer_review.add_argument("id")
    source = sub.add_parser("source-save")
    source.add_argument("file", type=Path)
    references = sub.add_parser("persona-references")
    references.add_argument("id")
    references.add_argument("--version", type=int, required=True)
    references.add_argument("--mother", required=True)
    references.add_argument("--daughter")
    logs = sub.add_parser("logs")
    logs.add_argument("--run-id")
    logs.add_argument("--after-id", type=int, default=0)
    logs.add_argument("--limit", type=int, default=100)
    next_job = sub.add_parser("worker-next")
    next_job.add_argument("--worker-id", default="codex")
    inspect = sub.add_parser("worker-inspect")
    inspect.add_argument("--cycle-id")
    for name in ["worker-ping", "worker-complete", "worker-fail", "worker-log", "worker-repair", "worker-checkpoint", "worker-video", "worker-sources", "worker-agent"]:
        command = sub.add_parser(name)
        command.add_argument("cycle_id")
        command.add_argument("lease_token")
        if name in ["worker-ping", "worker-complete"]:
            command.add_argument("--external-id")
        if name in ["worker-complete", "worker-checkpoint", "worker-sources"]:
            command.add_argument("--result", type=Path, required=True)
            if name == "worker-checkpoint":
                command.add_argument("--release-external-idle", action="store_true", help="Release only after confirming every external call has resolved.")
        elif name == "worker-agent":
            command.add_argument("--agent-id", required=True)
            command.add_argument("--role-id", required=True)
            command.add_argument("--action", choices=["assign"], default="assign")
        elif name == "worker-fail":
            command.add_argument("--error", required=True)
            command.add_argument("--no-retry", action="store_true")
            command.add_argument("--uncertain", action="store_true")
        elif name == "worker-log":
            command.add_argument("--event", required=True)
            command.add_argument("--message", required=True)
            command.add_argument("--detail", type=Path)
            command.add_argument("--level", choices=["info", "warning", "error"], default="info")
        elif name == "worker-repair":
            command.add_argument("--stage", choices=["storyboard", "copy", "images"], required=True)
            command.add_argument("--issues", type=Path, required=True)
    ingest = sub.add_parser("import")
    ingest.add_argument("manifest", type=Path)
    ingest.add_argument("--expected-version", type=int, default=0)
    add = sub.add_parser("job-add")
    add.add_argument("id")
    add.add_argument("stage")
    add.add_argument("--input", type=Path)
    update = sub.add_parser("job-update")
    update.add_argument("id")
    update.add_argument("action", choices=["claim", "complete", "fail", "uncertain", "external"])
    update.add_argument("--result", type=Path)
    update.add_argument("--external-id")
    update.add_argument("--error")
    claim = sub.add_parser("publish-claim")
    claim.add_argument("account")
    result = sub.add_parser("publish-result")
    result.add_argument("claim_id")
    result.add_argument("status", choices=["published", "uncertain", "failed_before_publish"])
    result.add_argument("--permalink")
    result.add_argument("--detail")
    args = parser.parse_args()
    store = Store(args.root)
    try:
        if args.command == "serve":
            server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(store))
            video_stop, video_thread = store.start_video_worker()
            store.production_worker = LocalProductionWorker(store).start()
            print("Boca review: http://127.0.0.1:%s" % server.server_port, flush=True)
            try:
                server.serve_forever()
            finally:
                video_stop.set()
                store.production_worker.stop.set()
                store.production_worker.wake.set()
                server.server_close()
            return
        if args.command == "state":
            value = store.state()
        elif args.command == "run-start":
            value = store.start_run({k: v for k, v in {"start_at": args.start_at, "end_at": args.end_at, "persona_id": args.persona_id, "media_mode": args.media_mode}.items() if v})
        elif args.command == "run-control":
            value = store.control_run(args.id, args.action)
        elif args.command == "run-defer-quality":
            value = store.defer_quality_review(args.id)
        elif args.command == "source-save":
            value = store.upsert_source(json.loads(args.file.read_text()))
        elif args.command == "persona-references":
            value = store.save_persona_references(args.id, {"version": args.version, "mother": args.mother, "daughter": args.daughter})
        elif args.command == "logs":
            value = {"logs": store.logs(args.run_id, args.after_id, args.limit)}
        elif args.command == "worker-next":
            value = store.worker_next(args.worker_id)
        elif args.command == "worker-inspect":
            value = store.worker_inspect(args.cycle_id)
        elif args.command == "worker-checkpoint":
            value = store.worker_checkpoint(args.cycle_id, args.lease_token, json.loads(args.result.read_text()), args.release_external_idle)
        elif args.command == "worker-ping":
            value = store.worker_ping(args.cycle_id, args.lease_token, args.external_id)
        elif args.command == "worker-video":
            value = store.worker_video(args.cycle_id, args.lease_token)
        elif args.command == "worker-agent":
            value = store.worker_agent(args.cycle_id, args.lease_token, args.agent_id, args.role_id, args.action)
        elif args.command == "worker-sources":
            value = store.worker_sources(args.cycle_id, args.lease_token, json.loads(args.result.read_text()))
        elif args.command == "worker-complete":
            value = store.worker_complete(args.cycle_id, args.lease_token, json.loads(args.result.read_text()), args.external_id)
        elif args.command == "worker-fail":
            value = store.worker_fail(args.cycle_id, args.lease_token, args.error, not args.no_retry, args.uncertain)
        elif args.command == "worker-log":
            value = store.worker_log(args.cycle_id, args.lease_token, args.event, args.message,
                                     json.loads(args.detail.read_text()) if args.detail else None, args.level)
        elif args.command == "worker-repair":
            value = store.worker_repair(args.cycle_id, args.lease_token, args.stage, json.loads(args.issues.read_text()))
        elif args.command == "import":
            value = store.ingest(json.loads(args.manifest.read_text()), args.expected_version)
        elif args.command == "job-add":
            value = store.add_job(args.id, args.stage, json.loads(args.input.read_text()) if args.input else {})
        elif args.command == "job-update":
            value = store.update_job(args.id, args.action, json.loads(args.result.read_text()) if args.result else None, args.external_id, args.error)
        elif args.command == "publish-claim":
            value = store.claim_publication(args.account)
        else:
            value = store.finish_publication(args.claim_id, args.status, args.permalink, args.detail)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except Problem as exc:
        print(encode({"error": str(exc), "status": exc.status}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
