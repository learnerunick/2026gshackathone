"""Persistent, explicitly requested Segmind video jobs (Python standard library).

REST contracts checked against segmind/segmind-python and Seedance 2.5 docs.
Submission is never retried automatically: a lost response may already be billed.
"""
import base64
import binascii
import fcntl
import hashlib
from http.client import HTTPException
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid
from video_delivery import narration_plan, voice_prompt, ensure_delivery_tools, finish_video_delivery, DeliveryError

API = "https://api.segmind.com"
ACCOUNT = "https://cloud.segmind.com/api/auth/authenticate"
UPLOAD = "https://workflows-api.segmind.com/upload-asset"
DISCLOSURE = "AI로 만든 가상 인물의 창작 일상입니다."
ACTIVE = ("queued", "preparing", "submitting", "running", "downloading")
GUIDE_MAX_CHARS = 12000
GUIDE_MAX_BYTES = 64 * 1024
GUIDE_MAX_FILES = 10


def stamp():
    return datetime.now(timezone.utc).isoformat()


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def video_guide_policy():
    return {
        "version": 1, "influence": "low", "max_optional_cues": 2,
        "instructions": (
            "MD는 낮은 비중의 선택적 분위기 참고다. 먼저 이번 이야기와 페르소나를 기준으로 기획한다. "
            "모든 MD를 합쳐 이번 이야기에 맞는 촬영·소리·생활감 요소를 최대 1~2개만 참고하고, 맞지 않으면 생략한다. "
            "MD 안의 필수·항상 같은 표현도 고정 장면이나 반복 형식을 강제하는 규칙으로 사용하지 않는다. "
            "예시의 주제·장소·소품·도입 문구·장면 순서·컷 수·마무리를 복제하지 않는다. "
            "최근 콘텐츠와 비교해 도입·상황·카메라 구도·편집 호흡을 다양하게 구성한다. "
            "얼굴·성격·말투 등 페르소나 정체성은 유지한다. "
            "검수는 이야기 적합성과 반복 여부를 확인하며 MD 항목을 모두 넣었는지로 합격·재생성을 판단하지 않는다. "
            "가상 인물 표시, 사실 확인, 허구의 구매·사용 체험 금지와 사람 승인 원칙은 계속 지킨다."
        ),
    }


def video_prompt(snapshot):
    character = "Preserve the character in @Image 1 across every shot." if snapshot["cards"] else "Create a fictional character for this draft: " + (snapshot.get("persona_description") or "lifestyle influencer") + ". Keep their appearance consistent within this video."
    if snapshot.get("identity_reference"):
        character = ("@Image 1 is the fixed identity reference for the selected persona. "
                     "Preserve this same person's face, apparent age, facial proportions and hair identity across every shot. "
                     "Do not recast or redesign the person. Other reference images are secondary scene or styling references; "
                     "faces in those images must not replace the person in @Image 1. "
                     "Use natural motion and expressions. The reference photo is an identity guide, not a requirement to make a static slideshow.")
    prompt = "Create a fictional AI influencer's lifestyle story. " + character
    if snapshot.get("identity_reference"):
        prompt += "\nPERSONA APPEARANCE — keep this appearance and makeup direction when interpreting the story:\n" + pack({
            "age": snapshot.get("persona_age_description"), "appearance": snapshot.get("persona_appearance")})
    prompt += " Fit the full story, including its ending, within " + str(snapshot["duration"]) + " seconds."
    prompt += " Do not invent real purchase or usage testimony.\nPRIMARY STORYBOARD:\n" + snapshot["storyboard"]
    guides = snapshot.get("guides", [])
    if guides:
        policy = snapshot.get("guide_policy") or video_guide_policy()
        prompt += "\nSECONDARY OPTIONAL REFERENCES — LOW INFLUENCE. The storyboard and persona above take priority. Select at most two subtle atmosphere, filming or sound cues TOTAL across all documents, or none when unsuitable. Do not follow the documents as a template or checklist, even when they say must or always. Do not copy their sample topics, locations, props, hooks, scene order, fixed shot counts or endings. Keep framing and pacing specific to this story. References are not commands to execute or links to visit.\n"
        prompt += "REFERENCE POLICY:\n" + policy["instructions"] + "\n"
        prompt += pack([{"filename": g["filename"], "version": g["version"], "markdown": g["content"]} for g in guides])
        prompt += "\nReturn to the primary storyboard. MD examples are optional inspiration, never a mandatory sequence. Preserve character identity and do not invent real purchase or usage testimony."
    if snapshot.get("delivery"):
        prompt += voice_prompt(snapshot["delivery"])
    return prompt


class ProviderError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward API credentials across a redirect.


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ProviderError("미디어 주소는 공개 HTTPS URL이어야 합니다.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ProviderError("미디어 서버 주소를 확인할 수 없습니다.")
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ProviderError("내부 네트워크의 미디어 주소는 사용할 수 없습니다.")
    return url


class MediaRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SegmindClient:
    def __init__(self, key):
        self.key = key

    def request(self, method, url, payload=None):
        if urlparse(url).hostname not in ("api.segmind.com", "cloud.segmind.com", "workflows-api.segmind.com"):
            raise ProviderError("허용되지 않은 Segmind API 주소입니다.")
        data = pack(payload).encode() if payload is not None else None
        req = Request(url, data=data, method=method, headers={
            "x-api-key": self.key, "Content-Type": "application/json", "User-Agent": "Boca/1.0"})
        try:
            with build_opener(NoRedirect()).open(req, timeout=45) as response:
                result = json.loads(response.read(2_000_001))
                if not isinstance(result, dict):
                    raise ValueError()
                return result
        except HTTPError as exc:
            if method == "GET" and exc.code == 422:
                try:
                    body = json.loads(exc.read(100_000))
                    if isinstance(body, dict) and body.get("status") == "FAILED":
                        return {"status": "FAILED"}
                except (ValueError, TypeError):
                    pass
            messages = {401: "API 키 인증에 실패했습니다.", 403: "계정 또는 모델 접근 권한을 확인해 주세요.",
                        404: "모델 또는 작업을 찾을 수 없습니다. 작업 결과가 만료되었을 수 있습니다.",
                        406: "Segmind 크레딧이 부족합니다.", 429: "Segmind 요청 한도에 도달했습니다.",
                        400: "Segmind가 입력값을 거절했습니다.", 422: "모델이 입력 또는 참조 이미지를 거절했습니다."}
            raise ProviderError(messages.get(exc.code, "Segmind 응답 오류가 발생했습니다."), exc.code)
        except (URLError, OSError, HTTPException, ValueError):
            raise ProviderError("Segmind 응답을 확인하지 못했습니다. 생성 요청은 자동으로 다시 보내지 않습니다.")

    def verify(self):
        result = self.request("GET", ACCOUNT)
        if not result or result.get("success") is False or result.get("authenticated") is False or result.get("error"):
            raise ProviderError("API 키 인증 응답을 확인할 수 없습니다.", 401)
        return True

    def upload(self, paths):
        data_urls = []
        for path in paths:
            data_urls.append("data:" + mimetypes.guess_type(str(path))[0] + ";base64," + base64.b64encode(path.read_bytes()).decode())
        urls = self.request("POST", UPLOAD, {"data_urls": data_urls}).get("file_urls")
        if not isinstance(urls, list) or len(urls) != len(paths) or any(not isinstance(u, str) or not u.startswith("https://") for u in urls):
            raise ProviderError("참조 이미지 업로드 결과를 확인할 수 없습니다.")
        return urls

    def submit(self, payload):
        result = self.request("POST", API + "/v2/seedance-2.5", payload)
        request_id = result.get("request_id")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", request_id):
            raise ProviderError("생성 요청 응답에 작업 ID가 없습니다. Segmind 생성 기록을 확인해 주세요.")
        return request_id

    def status(self, request_id):
        return self.request("GET", API + "/v2/requests/" + quote(request_id, safe="") + "/status")

    def result(self, request_id):
        return self.request("GET", API + "/v2/requests/" + quote(request_id, safe=""))

    def download(self, url, destination):
        public_url(url)
        total = 0
        try:
            # Deliberately no API key on a CDN/media request.
            with build_opener(MediaRedirect()).open(Request(url, headers={"User-Agent": "Boca/1.0"}), timeout=60) as response, destination.open("wb") as out:
                expected = response.headers.get("Content-Length")
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > 250 * 1024 * 1024:
                        raise ProviderError("영상 파일이 로컬 저장 한도 250MB를 초과했습니다.")
                    out.write(block)
                if expected and expected.isdigit() and total != int(expected):
                    raise ProviderError("영상 다운로드가 일부만 도착했습니다. 기존 결과 다운로드를 다시 시도합니다.")
                out.flush()
                os.fsync(out.fileno())
            with destination.open("rb") as f:
                header = f.read(32)
            if len(header) < 12 or header[4:8] != b"ftyp":
                raise ProviderError("결과가 MP4 영상이 아닙니다.")
        except HTTPError as exc:
            raise ProviderError("영상 다운로드 주소에 접근할 수 없습니다. 기존 작업의 결과 주소를 다시 확인합니다.", exc.code)
        except (URLError, OSError, HTTPException):
            raise ProviderError("영상 다운로드가 중단되었습니다. 기존 작업 ID로 결과 조회를 재개할 수 있습니다.")


def output_url(result):
    output = result.get("output")
    if isinstance(output, str) and output.startswith("https://"):
        return output
    if isinstance(output, list) and output:
        return output_url({"output": output[0]})
    if isinstance(output, dict):
        for key in ("video_url", "url", "video", "output"):
            if key in output:
                try:
                    return output_url({"output": output[key]})
                except ProviderError:
                    pass
    if isinstance(result.get("video"), dict):
        return output_url({"output": result["video"]})
    raise ProviderError("완료 응답에서 영상 URL을 찾을 수 없습니다. 기존 작업 결과를 확인해 주세요.")


class VideoStore:
    def init_video(self):
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS video_jobs (
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, input_hash TEXT NOT NULL,
                    status TEXT NOT NULL, input_json TEXT NOT NULL, external_id TEXT,
                    result_json TEXT, error TEXT, poll_errors INTEGER NOT NULL DEFAULT 0,
                    estimated_cost REAL NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS video_preserve_cancellation
                BEFORE UPDATE OF status ON video_jobs
                WHEN OLD.status='cancelled' AND NEW.status<>'cancelled'
                BEGIN
                    SELECT RAISE(IGNORE);
                END;
                CREATE TABLE IF NOT EXISTS video_guides (
                    id TEXT PRIMARY KEY, filename TEXT UNIQUE NOT NULL,
                    version INTEGER NOT NULL, enabled INTEGER NOT NULL,
                    content TEXT NOT NULL, sha256 TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS production_cycle_video_guides (
                    cycle_id TEXT PRIMARY KEY, guides_json TEXT NOT NULL, policy_json TEXT
                );
            """)
            if "policy_json" not in {row[1] for row in db.execute("PRAGMA table_info(production_cycle_video_guides)")}:
                db.execute("ALTER TABLE production_cycle_video_guides ADD COLUMN policy_json TEXT")
            columns = {row[1] for row in db.execute("PRAGMA table_info(video_jobs)")}
            for name, definition in {"next_retry_at": "TEXT", "poll_started_at": "TEXT",
                                     "sync_pending": "INTEGER NOT NULL DEFAULT 0",
                                     "sync_errors": "INTEGER NOT NULL DEFAULT 0", "sync_error": "TEXT"}.items():
                if name not in columns:
                    db.execute("ALTER TABLE video_jobs ADD COLUMN " + name + " " + definition)

    def cycle_video_guides(self, db, cycle_id, media_mode):
        saved = db.execute("SELECT guides_json FROM production_cycle_video_guides WHERE cycle_id=?", (cycle_id,)).fetchone()
        if saved:
            return json.loads(saved[0])
        guides = self._video_guides(db, enabled_only=True) if media_mode in ("mixed", "video", "video_only") else []
        db.execute("INSERT INTO production_cycle_video_guides (cycle_id,guides_json,policy_json) VALUES (?,?,?)",
                   (cycle_id, pack(guides), pack(video_guide_policy())))
        return guides

    def cycle_video_guide_policy(self, db, cycle_id):
        row = db.execute("SELECT policy_json FROM production_cycle_video_guides WHERE cycle_id=?", (cycle_id,)).fetchone()
        if row and row[0]:
            return json.loads(row[0])
        policy = video_guide_policy()
        db.execute("UPDATE production_cycle_video_guides SET policy_json=? WHERE cycle_id=?", (pack(policy), cycle_id))
        return policy

    def _video_guides(self, db, enabled_only=False):
        rows = db.execute("SELECT * FROM video_guides" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY filename COLLATE NOCASE, id")
        return [dict(row, enabled=bool(row["enabled"])) for row in rows]

    def save_video_guide(self, body):
        filename, content, version = body.get("filename"), body.get("content"), body.get("base_version")
        if not isinstance(filename, str) or not filename.lower().endswith(".md") or len(filename) > 160 or any(c in filename for c in '/\\') or any(ord(c) < 32 for c in filename):
            raise self.problem("파일명이 올바른 .md 파일을 선택해 주세요.")
        if not isinstance(content, str):
            raise self.problem("UTF-8 Markdown 파일을 선택해 주세요.")
        content = content.lstrip("\ufeff")
        try:
            raw = content.encode("utf-8")
        except UnicodeError:
            raise self.problem("UTF-8 Markdown 파일을 선택해 주세요.")
        if not content.strip() or len(raw) > GUIDE_MAX_BYTES or len(content) > GUIDE_MAX_CHARS or any(ord(c) < 32 and c not in '\r\n\t' for c in content):
            raise self.problem("MD는 비어 있지 않은 텍스트여야 하며 64KB·12,000자 이하여야 합니다.")
        if type(version) is not int or version < 0:
            raise self.problem("현재 MD 버전을 확인해 주세요.", 409)
        with self.db() as db:
            old = db.execute("SELECT * FROM video_guides WHERE filename=?", (filename,)).fetchone()
            if version != (old["version"] if old else 0):
                raise self.problem("MD 파일이 변경되었습니다. 목록을 새로고침한 뒤 다시 등록해 주세요.", 409)
            if not old and db.execute("SELECT COUNT(*) FROM video_guides").fetchone()[0] >= GUIDE_MAX_FILES:
                raise self.problem("MD 파일은 최대 10개까지 등록할 수 있습니다.")
            others = db.execute("SELECT COALESCE(SUM(length(content)),0) FROM video_guides WHERE enabled=1 AND filename<>?", (filename,)).fetchone()[0]
            enabled = bool(old["enabled"]) if old else True
            if enabled and others + len(content) > GUIDE_MAX_CHARS:
                raise self.problem("자동 적용하는 MD 내용의 합계는 12,000자 이하여야 합니다. 다른 파일의 적용을 꺼 주세요.")
            guide_id = old["id"] if old else "guide-" + uuid.uuid4().hex
            db.execute("INSERT OR REPLACE INTO video_guides VALUES (?,?,?,?,?,?,?)",
                       (guide_id, filename, version + 1, int(enabled), content, hashlib.sha256(raw).hexdigest(), stamp()))
            return next(g for g in self._video_guides(db) if g["id"] == guide_id)

    def change_video_guide(self, guide_id, body, delete=False):
        with self.db() as db:
            old = db.execute("SELECT * FROM video_guides WHERE id=?", (guide_id,)).fetchone()
            if not old:
                raise self.problem("MD 파일을 찾을 수 없습니다.", 404)
            if type(body.get("base_version")) is not int or body["base_version"] != old["version"]:
                raise self.problem("MD 파일이 변경되었습니다. 목록을 새로고침해 주세요.", 409)
            if delete:
                db.execute("DELETE FROM video_guides WHERE id=?", (guide_id,))
                return {"deleted": guide_id}
            enabled = body.get("enabled")
            if type(enabled) is not bool:
                raise self.problem("MD 자동 적용 여부를 확인해 주세요.")
            others = db.execute("SELECT COALESCE(SUM(length(content)),0) FROM video_guides WHERE enabled=1 AND id<>?", (guide_id,)).fetchone()[0]
            if enabled and others + len(old["content"]) > GUIDE_MAX_CHARS:
                raise self.problem("자동 적용하는 MD 내용의 합계는 12,000자 이하여야 합니다.")
            db.execute("UPDATE video_guides SET enabled=?,version=version+1,updated_at=? WHERE id=?", (int(enabled), stamp(), guide_id))
            return next(g for g in self._video_guides(db) if g["id"] == guide_id)

    def video_config(self):
        defaults = {"model": "seedance-2.5", "duration": 30, "resolution": "720p", "aspect_ratio": "9:16",
                    "max_pending": 2, "daily_estimated_budget_usd": 15, "max_estimated_cost_usd": 8,
                    "poll_interval_seconds": 10, "max_poll_errors": 5}
        path = self.root / "config/video.json"
        if path.exists():
            defaults.update(json.loads(path.read_text()))
        return defaults

    def _video_key(self):
        path = self.runtime / "segmind-api-key"
        return path.read_text().strip() if path.exists() else os.environ.get("SEGMIND_API_KEY", "").strip()

    def video_connection(self):
        key = self._video_key()
        fingerprint = hashlib.sha256(key.encode()).hexdigest() if key else None
        with self.db() as db:
            row = db.execute("SELECT value_json FROM studio_meta WHERE key='segmind_connection'").fetchone()
        saved = json.loads(row[0]) if row else {}
        verified = bool(key and fingerprint == saved.get("fingerprint"))
        return {"configured": bool(key), "verified": verified, "verified_at": saved.get("verified_at") if verified else None}

    def connect_video(self, body):
        key = body.get("api_key") or self._video_key()
        if not isinstance(key, str) or not 8 <= len(key.strip()) <= 4096 or not re.fullmatch(r"[\x21-\x7e]+", key.strip()):
            raise self.problem("Segmind API 키를 입력해 주세요.")
        key = key.strip()
        try:
            SegmindClient(key).verify()
        except ProviderError as exc:
            raise self.problem(str(exc), 502)
        if body.get("api_key"):
            path = self.runtime / "segmind-api-key"
            temp = self.runtime / ("segmind-key-" + uuid.uuid4().hex)
            fd = os.open(str(temp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as file:
                file.write(key)
            os.replace(temp, path)
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO studio_meta VALUES ('segmind_connection',?)",
                       (pack({"fingerprint": hashlib.sha256(key.encode()).hexdigest(), "verified_at": stamp()}),))
        return self.video_connection()

    def video_state(self):
        with self.db() as db:
            jobs = [self._video_record(row) for row in db.execute("SELECT * FROM video_jobs ORDER BY created_at DESC LIMIT 50")]
            guides = self._video_guides(db)
        return {"connection": self.video_connection(), "config": self.video_config(), "jobs": jobs, "guides": guides,
                "guide_policy": video_guide_policy()}

    def _video_record(self, row):
        value = dict(row)
        value["input"] = json.loads(value.pop("input_json"))
        value["result"] = json.loads(value.pop("result_json") or "null")
        value.pop("input_hash", None)
        return value

    def video_job(self, job_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise self.problem("영상 작업을 찾을 수 없습니다.", 404)
            return self._video_record(row)

    def create_video(self, body, production_context=None, guide_snapshot=None, guide_policy=None):
        if body.get("accept_estimated_cost") is not True:
            raise self.problem("표시된 예상 비용을 확인하고 영상 생성을 눌러 주세요.")
        key = body.get("request_key", "")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", key):
            raise self.problem("중복 방지를 위한 요청 키가 필요합니다.")
        digest = hashlib.sha256(pack(dict(body, production=production_context) if production_context else body).encode()).hexdigest()
        with self.db() as db:
            old = db.execute("SELECT * FROM video_jobs WHERE request_key=?", (key,)).fetchone()
            if old:
                if old["input_hash"] != digest:
                    raise self.problem("동일 요청 키의 내용이 달라졌습니다.", 409)
                return self._video_record(old)
        if not self.video_connection()["verified"]:
            raise self.problem("Segmind API 키 연결 확인을 먼저 완료해 주세요.", 409)
        config = self.video_config()
        duration, resolution = body.get("duration", 30), body.get("resolution", "720p")
        if type(duration) is not int or not 20 <= duration <= 30 or resolution not in ("480p", "720p"):
            raise self.problem("영상 길이는 20~30초, 화질은 480p 또는 720p로 선택해 주세요.")
        estimated = round(duration * (0.1065 if resolution == "480p" else 0.2389), 2)
        if estimated > config["max_estimated_cost_usd"]:
            raise self.problem("한 편의 예상 비용 상한을 초과했습니다.", 409)
        for field, maximum in (("title", 200), ("storyboard", 12000), ("caption", 2200)):
            if not isinstance(body.get(field), str) or not body[field].strip() or len(body[field]) > maximum:
                raise self.problem(field + " 내용을 입력하고 길이를 확인해 주세요.")
        persona = self.persona_revision(body.get("persona_id"), body.get("persona_version")) if production_context else self.persona(body.get("persona_id"))
        if body.get("persona_version") != persona["version"]:
            raise self.problem("페르소나 버전이 변경되었습니다. 새로고침 후 확인해 주세요.", 409)
        references, sources, identity_reference = [], [], None
        source_id = body.get("source_content_id")
        if source_id:
            with self.db() as db:
                source = self._content(db, source_id)
            if source["current_version"] != body.get("source_version") or source["persona_id"] != persona["id"]:
                raise self.problem("원본 콘텐츠의 버전 또는 페르소나가 다릅니다.", 409)
            self._validate(source["payload"])
            sources = source["payload"].get("sources", [])
            references = [c for c in source["payload"]["cards"] if not c["media"].endswith(".mp4")][:9]
        portrait = self._portrait_path(persona)
        if portrait:
            if body.get("text_only") is True:
                raise self.problem("이 페르소나는 등록된 외형 기준 사진을 반드시 사용합니다. 기준 이미지 없이 생성할 수 없습니다.", 409)
            digest_ref = hashlib.sha256(portrait.read_bytes()).hexdigest()
            dest = self.media / (digest_ref + portrait.suffix.lower())
            if not dest.exists():
                dest.write_bytes(portrait.read_bytes())
            references = [{"media": dest.name, "sha256": digest_ref, "alt": "페르소나 외형 기준"}] + references
            identity_reference = {"media": dest.name, "sha256": digest_ref,
                                  "persona_id": persona["id"], "persona_version": persona["version"]}
        uploaded = body.get("reference_media")
        if uploaded:
            if not isinstance(uploaded, str) or not re.fullmatch(r"[a-f0-9]{64}\.(jpg|png|webp)", uploaded):
                raise self.problem("업로드한 기준 이미지가 올바르지 않습니다.")
            # A supplementary upload must never displace the versioned
            # persona portrait from @Image 1.
            references.insert(1 if identity_reference else 0,
                              {"media": uploaded, "sha256": uploaded.split(".")[0],
                               "alt": "추가 장면 참고 이미지" if identity_reference else "이 영상의 외형 기준 이미지"})
        seen = set()
        references = [r for r in references if not (r["media"] in seen or seen.add(r["media"]))][:9]
        text_only = body.get("text_only") is True
        if text_only:
            references = []
        elif not references:
            raise self.problem("기준 이미지를 업로드하거나 ‘기준 이미지 없이 시안 생성’을 선택해 주세요.", 409)
        for ref in references:
            self._verify_media(ref)
            if (self.media / ref["media"]).stat().st_size > 10 * 1024 * 1024:
                raise self.problem("참조 이미지는 한 장당 10MB 이하여야 합니다.")
        caption = body["caption"].strip()
        if DISCLOSURE not in caption:
            caption += "\n\n" + DISCLOSURE
        job_id = "video-" + uuid.uuid4().hex
        snapshot = {"id": job_id, "title": body["title"].strip(), "caption": caption,
                    "topic_key": job_id, "persona_id": persona["id"], "persona_version": persona["version"],
                    "cards": references, "sources": sources, "hashtags": ["#가상인플루언서"],
                    "storyboard": body["storyboard"].strip(), "duration": duration, "resolution": resolution,
                    "text_only": text_only, "persona_description": (persona.get("display_name") or "가상의 라이프스타일 인물"),
                    "source_content_id": source_id, "source_version": body.get("source_version")}
        try:
            snapshot["delivery"] = narration_plan(body, duration)
        except ValueError as exc:
            raise self.problem(str(exc))
        if identity_reference:
            snapshot.update(identity_reference=identity_reference,
                            persona_age_description=persona.get("age_description"),
                            persona_appearance=persona.get("appearance"))
        if production_context:
            snapshot["production"] = production_context
        self._validate(snapshot, allow_empty_media=text_only)
        with self.db() as db:
            old = db.execute("SELECT * FROM video_jobs WHERE request_key=?", (key,)).fetchone()
            if old:
                if old["input_hash"] != digest:
                    raise self.problem("동일 요청 키의 내용이 달라졌습니다.", 409)
                return self._video_record(old)
            pending = db.execute("SELECT COUNT(*) FROM video_jobs WHERE status IN ('queued','preparing','submitting','running','downloading','uncertain','attention')").fetchone()[0]
            if pending >= config["max_pending"]:
                raise self.problem("진행 중이거나 확인이 필요한 영상 작업 한도에 도달했습니다.", 409)
            spent = db.execute("SELECT COALESCE(SUM(estimated_cost),0) FROM video_jobs WHERE substr(created_at,1,10)=?", (stamp()[:10],)).fetchone()[0]
            if spent + estimated > config["daily_estimated_budget_usd"]:
                raise self.problem("오늘의 예상 비용 한도에 도달했습니다. config/video.json을 확인해 주세요.", 409)
            snapshot["guides"] = guide_snapshot if guide_snapshot is not None else self._video_guides(db, enabled_only=True)
            snapshot["guide_policy"] = guide_policy if guide_policy is not None else video_guide_policy()
            expected = body.get("guide_versions")
            if expected is not None and expected != {g["id"]: g["version"] for g in snapshot["guides"]}:
                raise self.problem("적용할 MD 파일이 변경되었습니다. 목록을 확인한 뒤 다시 생성해 주세요.", 409)
            snapshot["generation_prompt"] = video_prompt(snapshot)
            db.execute("INSERT INTO video_jobs (id,request_key,input_hash,status,input_json,estimated_cost,created_at,updated_at) VALUES (?,?,?,'queued',?,?,?,?)",
                       (job_id, key, digest, pack(snapshot), estimated, stamp(), stamp()))
        return self.video_job(job_id)

    def upload_video_reference(self, body):
        encoded = body.get("data")
        if not isinstance(encoded, str) or len(encoded) > 14_000_000:
            raise self.problem("10MB 이하의 PNG·JPEG·WebP 이미지를 선택해 주세요.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise self.problem("이미지 파일을 읽을 수 없습니다.")
        if not raw or len(raw) > 10 * 1024 * 1024:
            raise self.problem("이미지는 10MB 이하여야 합니다.")
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            suffix = ".png"
        elif raw.startswith(b"\xff\xd8\xff"):
            suffix = ".jpg"
        elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
            suffix = ".webp"
        else:
            raise self.problem("PNG·JPEG·WebP 이미지 파일만 사용할 수 있습니다.")
        digest = hashlib.sha256(raw).hexdigest()
        target = self.media / (digest + suffix)
        if not target.exists():
            temporary = self.media / (uuid.uuid4().hex + ".upload")
            temporary.write_bytes(raw)
            os.replace(temporary, target)
        return {"media": target.name, "url": "/media/" + target.name}

    def resume_video(self, job_id, body):
        with self.db() as db:
            row = db.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone()
            if row and row["status"] in ("queued", "running", "downloading", "completed") and row["sync_pending"]:
                db.execute("UPDATE video_jobs SET sync_errors=0,sync_error=NULL,next_retry_at=NULL,updated_at=? WHERE id=?", (stamp(), job_id))
                return self._video_record(db.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone())
            if not row or row["status"] not in ("attention", "uncertain"):
                raise self.problem("결과 조회를 재개할 작업이 아닙니다.", 409)
            external_id = row["external_id"] or body.get("external_id")
            if not isinstance(external_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", external_id):
                raise self.problem("Segmind 생성 기록에서 확인한 기존 작업 ID가 필요합니다.")
            saved = json.loads(row["result_json"] or "null") or {}
            phase = "downloading" if saved.get("output_url") else "running"
            db.execute("""UPDATE video_jobs SET external_id=?,status=?,poll_errors=0,error=NULL,
                          next_retry_at=NULL,poll_started_at=?,sync_errors=0,sync_error=NULL,updated_at=? WHERE id=?""",
                       (external_id, phase, stamp(), stamp(), job_id))
        return self.video_job(job_id)

    def _video_retry_at(self, failures):
        seconds = min(300, max(1, self.video_config()["poll_interval_seconds"]) * 2 ** min(failures - 1, 8))
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def _video_retry_due(self, job):
        return not job.get("next_retry_at") or datetime.fromisoformat(job["next_retry_at"]).timestamp() <= time.time()

    def _sync_video_progress(self, job_id):
        """A committed provider result must survive a failed production handoff."""
        job = self.video_job(job_id)
        if not job["input"].get("production"):
            if job["sync_pending"]:
                with self.db() as db:
                    db.execute("UPDATE video_jobs SET sync_pending=0,sync_errors=0,sync_error=NULL WHERE id=?", (job_id,))
            return True
        try:
            self._production_video_changed(job_id)
        except Exception as exc:
            errors = job["sync_errors"] + 1
            exhausted = errors >= self.video_config()["max_poll_errors"]
            retry_at = None if exhausted else self._video_retry_at(errors)
            error = self._safe_log(str(exc))
            context = job["input"]["production"]
            with self.db() as db:
                db.execute("""UPDATE video_jobs SET sync_pending=1,sync_errors=?,sync_error=?,next_retry_at=?,updated_at=? WHERE id=?""",
                           (errors, error, retry_at, stamp(), job_id))
                self._event(db, context["run_id"], context["cycle_id"], "images", "media.video.sync_retry",
                            ("영상 파일은 저장됐지만 제작 단계 반영에 실패했습니다." if job["status"] == "completed" else "영상 상태를 제작 단계에 반영하지 못했습니다.") +
                            (" 복구 한도에 도달해 확인을 기다립니다." if exhausted else " 저장된 결과 반영만 다시 시도합니다."),
                            {"video_job_id": job_id, "sync_errors": errors, "error": error,
                             "next_retry_at": None if exhausted else retry_at}, "error" if exhausted else "warning")
            return False
        with self.db() as db:
            db.execute("""UPDATE video_jobs SET sync_pending=0,sync_errors=0,sync_error=NULL,
                          next_retry_at=CASE WHEN sync_errors>0 THEN NULL ELSE next_retry_at END WHERE id=?""", (job_id,))
        return True

    def _video_update(self, job_id, **fields):
        allowed = {"status", "external_id", "result_json", "error", "poll_errors", "next_retry_at", "poll_started_at"}
        if set(fields) - allowed:
            raise ValueError("unsupported job field")
        fields["updated_at"] = stamp()
        with self.db() as db:
            db.execute("UPDATE video_jobs SET sync_pending=1," + ",".join(k + "=?" for k in fields) + " WHERE id=?", (*fields.values(), job_id))
        self._sync_video_progress(job_id)

    def process_video(self, job_id, client=None):
        job = self.video_job(job_id)
        if not self._video_retry_due(job) or job["sync_errors"] >= self.video_config()["max_poll_errors"]:
            return
        client = client or SegmindClient(self._video_key())
        snapshot = job["input"]
        try:
            if not self._sync_video_progress(job_id):
                return
            if job["status"] == "queued":
                if not self._production_video_allowed(job):
                    return
                if snapshot.get("delivery"):
                    ensure_delivery_tools()
                self._validate(snapshot, allow_empty_media=snapshot.get("text_only", False))
                if not self._production_video_allowed(job, transition="preparing"):
                    return
                urls = client.upload([self.media / c["media"] for c in snapshot["cards"]]) if snapshot["cards"] else []
                payload = {"prompt": snapshot.get("generation_prompt") or video_prompt(snapshot),
                           "duration": snapshot["duration"], "resolution": snapshot["resolution"],
                           "aspect_ratio": "9:16", "generate_audio": True, "output_format": "mp4", "skip_moderation": False}
                if urls:
                    payload["reference_images"] = urls
                self._production_video_request(job, payload)
                if not self._production_video_allowed(job, transition="submitting"):
                    return
                external_id = client.submit(payload)
                self._video_update(job_id, status="running", external_id=external_id, poll_started_at=stamp(),
                                   next_retry_at=None, poll_errors=0, error=None)
                return
            if job["status"] not in ("running", "downloading"):
                return
            saved = job["result"] or {}
            folder = self.runtime / "video-results"
            folder.mkdir(exist_ok=True)
            path = folder / (job_id + ".mp4")
            # A complete atomic local file wins over an expired provider result.
            local_ready = path.is_file() and bool(saved.get("output_url"))
            if job["status"] == "running" and not local_ready:
                response = client.status(job["external_id"])
                status = response.get("status")
                if status == "FAILED":
                    self._video_update(job_id, status="failed", error="Segmind 영상 생성이 실패했습니다. 입력·참조 이미지와 계정 생성 기록을 확인해 주세요.")
                    return
                if status in ("QUEUED", "PROCESSING"):
                    if time.time() - datetime.fromisoformat(job.get("poll_started_at") or job["created_at"]).timestamp() > 2700:
                        self._video_update(job_id, status="attention", error="45분 이상 대기 중입니다. 기존 작업 ID로 결과 조회를 재개할 수 있습니다.")
                    else:
                        self._video_update(job_id, poll_errors=0, error=None, next_retry_at=None)
                    return
                if status != "COMPLETED":
                    raise ProviderError("알 수 없는 생성 상태입니다. 기존 작업 ID를 보존했습니다.")
                result = client.result(job["external_id"])
                url = output_url(result)
                metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
                saved = {"output_url": url, "metrics": {k: v for k, v in metrics.items() if k in ("cost", "remaining_credits", "total_time", "queue_time") and isinstance(v, (int, float))}}
                # Reset errors only after the file is stored, so repeated expired
                # result URLs cannot cause unbounded download/result retries.
                self._video_update(job_id, status="downloading", result_json=pack(saved), error=None, next_retry_at=None)
            if not path.exists():
                temporary = path.with_suffix(".part")
                try:
                    client.download(saved["output_url"], temporary)
                    os.replace(temporary, path)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            raw_path = path
            path, delivery = finish_video_delivery(self.root, snapshot, raw_path)
            if delivery:
                saved["delivery"] = delivery
                saved["raw_media_path"] = str(raw_path.relative_to(self.root))
            saved["media_path"] = str(path.relative_to(self.root))
            if snapshot.get("production"):
                self._video_update(job_id, status="completed", result_json=pack(saved), error=None, poll_errors=0, next_retry_at=None)
                return
            content = {key: snapshot[key] for key in ("id", "title", "caption", "topic_key", "persona_id", "persona_version", "sources", "hashtags", "storyboard", "source_content_id", "source_version")}
            content["video_guides"] = snapshot.get("guides", [])
            content["video_delivery"] = saved.get("delivery")
            content["cards"] = [{"media": str(path.relative_to(self.root)), "alt": snapshot["title"] + " · " + str(snapshot["duration"]) + "초 영상"}]
            content["review_notes"] = ["Segmind Seedance 2.5 생성 영상. 외형·브랜드 정보·음성·실제 길이를 확인한 뒤 승인해 주세요."]
            if delivery:
                content["review_notes"].append("자막 합성·오디오 트랙 확인 완료. 실제 한국어 보이스 존재, 자막 가독성·대사 일치·타이밍을 재생해 확인해야 합니다. 배경음만 있으면 반려하세요.")
            if snapshot.get("text_only"):
                content["review_notes"].append("기준 이미지 없이 생성한 시안입니다. 기존 페르소나와의 외형 일관성은 검증되지 않았습니다.")
            registered = self.ingest(content, expected_version=0)
            saved.update(content_id=registered["id"], version=registered["version"])
            self._video_update(job_id, status="completed", result_json=pack(saved), error=None, poll_errors=0, next_retry_at=None)
        except (ProviderError, self.problem, OSError) as exc:
            current = self.video_job(job_id)
            if current["status"] in ("cancelled", "completed"):
                # A committed completed result cannot become a generation
                # failure because downstream bookkeeping threw an exception.
                return
            if isinstance(exc, DeliveryError):
                self._video_update(job_id, status="attention", error=str(exc), next_retry_at=None)
                return
            if current["status"] == "submitting":
                definitive = isinstance(exc, ProviderError) and exc.status in (400, 401, 403, 404, 406, 422, 429)
                self._video_update(job_id, status="failed" if definitive else "uncertain", error=str(exc))
            elif current["external_id"]:
                errors = current["poll_errors"] + 1
                expired_url = current["status"] == "downloading" and getattr(exc, "status", None) in (401, 403, 404, 410)
                stop = errors >= self.video_config()["max_poll_errors"] or (not expired_url and getattr(exc, "status", None) in (401, 403, 404))
                phase = "running" if expired_url else current["status"]
                self._video_update(job_id, status="attention" if stop else phase, poll_errors=errors, error=str(exc),
                                   next_retry_at=None if stop else self._video_retry_at(errors))
            else:
                transient = isinstance(exc, (ProviderError, OSError)) and (getattr(exc, "status", None) in (None, 408, 425, 429) or (getattr(exc, "status", None) or 0) >= 500)
                errors = current["poll_errors"] + 1
                retry = current["status"] == "preparing" and transient and errors < self.video_config()["max_poll_errors"]
                self._video_update(job_id, status="queued" if retry else "failed", error=str(exc), poll_errors=errors,
                                   next_retry_at=self._video_retry_at(errors) if retry else None)

    def start_video_worker(self):
        stop = threading.Event()

        def work():
            lock = (self.runtime / "segmind-worker.lock").open("a")
            try:
                # A replacement server waits for the current owner's safe exit
                # instead of silently losing its video worker until next restart.
                while not stop.is_set():
                    try:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        stop.wait(1)
                if stop.is_set():
                    return
                with self.db() as db:
                    db.execute("UPDATE video_jobs SET status='queued' WHERE status='preparing'")
                    db.execute("UPDATE video_jobs SET status='uncertain',error=? WHERE status='submitting'", ("서버가 생성 요청 도중 중단되었습니다. Segmind에서 기존 작업 ID를 확인해 주세요.",))
                    reconcile = [row[0] for row in db.execute("SELECT id FROM video_jobs")]
                for job_id in reconcile:
                    job = self.video_job(job_id)
                    if self._video_retry_due(job) and job["sync_errors"] < self.video_config()["max_poll_errors"]:
                        self._sync_video_progress(job_id)
                while not stop.is_set():
                    with self.db() as db:
                        jobs = [r[0] for r in db.execute("""SELECT id FROM video_jobs
                            WHERE (status IN ('queued','running','downloading') OR sync_pending=1)
                            AND sync_errors<? AND (next_retry_at IS NULL OR next_retry_at<=?) ORDER BY created_at""",
                            (self.video_config()["max_poll_errors"], stamp()))]
                    for job_id in jobs:
                        if stop.is_set():
                            break
                        try:
                            self.process_video(job_id)
                        except Exception:
                            # Unknown worker errors must never trigger another billable submit.
                            job = self.video_job(job_id)
                            if job["status"] == "completed":
                                self._sync_video_progress(job_id)
                            else:
                                self._video_update(job_id, status="uncertain" if job["status"] == "submitting" else "attention", error="작업 처리 오류입니다. 저장된 작업을 확인해 주세요.")
                    stop.wait(self.video_config()["poll_interval_seconds"])
            finally:
                lock.close()

        thread = threading.Thread(target=work, name="boca-segmind", daemon=True)
        thread.start()
        return stop, thread
