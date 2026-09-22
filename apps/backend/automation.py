"""Persistent production runs, stage leases, sources and append-only event logs."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import secrets
import uuid
from urllib.parse import urlparse
from production_artifacts import ProductionArtifacts, sanitize
from source_research import AFFILIATE_DOMAINS, SourceResearchStore, normalize_affiliate
from specialists import SpecialistsStore
from local_worker import worker_state

STAGES = [
    {"key": "sources", "label": "GS 소재 확인"},
    {"key": "planning", "label": "일상 주제 기획"},
    {"key": "storyboard", "label": "스토리보드"},
    {"key": "copy", "label": "문안·해시태그"},
    {"key": "images", "label": "이미지·미디어 생성"},
    {"key": "quality", "label": "일관성·정보 검수"},
    {"key": "register", "label": "피드 등록"},
]
ACTIVE = ("scheduled", "running", "paused", "blocked")
UNSET_PRODUCTION_LIMIT = object()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class AutomationStore(SpecialistsStore, SourceResearchStore, ProductionArtifacts):
    def init_automation(self):
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS production_runs (
                    id TEXT PRIMARY KEY, persona_id TEXT NOT NULL, persona_version INTEGER NOT NULL,
                    account TEXT, status TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0, cycle_number INTEGER NOT NULL DEFAULT 0,
                    current_stage TEXT, pause_reason TEXT, last_heartbeat_at TEXT,
                    persona_json TEXT NOT NULL, settings_json TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_persona_run
                    ON production_runs(persona_id) WHERE status IN ('scheduled','running','paused','blocked');
                CREATE TABLE IF NOT EXISTS production_cycles (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, number INTEGER NOT NULL,
                    content_id TEXT NOT NULL UNIQUE, stage_index INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}',
                    lease_token TEXT, lease_owner TEXT, lease_expires_at TEXT, completed_token TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(run_id,number)
                );
                CREATE TABLE IF NOT EXISTS production_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, cycle_id TEXT, stage TEXT,
                    level TEXT NOT NULL, event TEXT NOT NULL, message TEXT NOT NULL,
                    detail_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_materials (
                    id TEXT PRIMARY KEY, affiliate TEXT NOT NULL, title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE, verified_at TEXT NOT NULL, expires_at TEXT,
                    claims_json TEXT NOT NULL, visibility TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS event_run_cursor ON production_events(run_id,id);
            """)
            # Earlier databases required a deadline. Preserve rows and indexes
            # while making an absent deadline explicit instead of using a fake date.
            columns = {row['name']: row for row in db.execute('PRAGMA table_info(production_runs)')}
            if columns['end_at']['notnull']:
                db.execute('BEGIN IMMEDIATE')
                schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='production_runs'").fetchone()[0]
                indexes = [row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE tbl_name='production_runs' AND type IN ('index','trigger') AND sql IS NOT NULL")]
                schema = schema.replace('production_runs', 'production_runs_optional_deadline', 1).replace('end_at TEXT NOT NULL', 'end_at TEXT')
                db.execute(schema)
                db.execute('INSERT INTO production_runs_optional_deadline SELECT * FROM production_runs')
                db.execute('DROP TABLE production_runs')
                db.execute('ALTER TABLE production_runs_optional_deadline RENAME TO production_runs')
                for statement in indexes:
                    db.execute(statement)
            self.init_source_research(db)
            self.init_specialists(db)
            columns = {r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
            for name in ["run_id", "cycle_id"]:
                if name not in columns:
                    db.execute("ALTER TABLE jobs ADD COLUMN " + name + " TEXT")

    def _time(self, value):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                raise ValueError()
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            raise self.problem("시간대를 포함한 ISO 날짜가 필요합니다.")

    def _safe_log(self, value):
        value = sanitize(value)
        if isinstance(value, dict):
            return {key: self._safe_log(entry) for key, entry in value.items()}
        if isinstance(value, list):
            return [self._safe_log(entry) for entry in value]
        if isinstance(value, str) and getattr(self, "token", None):
            return value.replace(self.token, "[redacted]")
        return value

    def _result_summary(self, stage, result):
        def count(field):
            return len(result.get(field)) if isinstance(result.get(field), (list, str)) else 0
        if stage == "sources":
            summary = "활용 가능한 GS 소재 " + str(count("source_ids")) + "건을 확인했습니다."
        elif stage == "planning":
            summary = "기획 주제: " + str(result.get("title", "")) + "; 중복 확인 키: " + str(result.get("topic_key", ""))
        elif stage == "storyboard":
            summary = str(count("cards")) + "장 구성의 스토리보드를 작성했습니다."
        elif stage == "copy":
            summary = "문안 " + str(count("caption")) + "자, 해시태그 " + str(count("hashtags")) + "개를 작성했습니다."
        elif stage == "images":
            summary = "실제 미디어 파일 " + str(count("media")) + "개를 저장했습니다."
        elif stage == "quality":
            summary = "품질 검수 " + ("통과" if result.get("passed") is True else "결과 확인 필요")
        elif stage == "register":
            summary = "콘텐츠 " + str(result.get("content_id", "")) + "의 버전 " + str(result.get("version", "")) + "을 등록했습니다."
        else:
            summary = "단계 결과를 저장했습니다."
        if isinstance(result.get("decision_summary"), str) and result["decision_summary"].strip():
            summary += " 선택 근거 요약: " + result["decision_summary"].strip()
        return self._safe_log(summary)

    def _event(self, db, run_id, cycle_id, stage, event, message, detail=None, level="info"):
        detail = detail if isinstance(detail, dict) else ({"value": detail} if detail is not None else {})
        cursor = db.execute("INSERT INTO production_events (run_id,cycle_id,stage,level,event,message,detail_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                            (run_id, cycle_id, stage, level, event, self._safe_log(message),
                             dumps(self._safe_log(detail or {})), timestamp()))
        return cursor.lastrowid

    def _run(self, row):
        if row is None:
            return None
        result = dict(row)
        result["persona"] = self.with_persona_references(json.loads(result.pop("persona_json")))
        result["settings"] = json.loads(result.pop("settings_json"))
        return result

    def _cycle(self, row):
        result = dict(row)
        result["result"] = json.loads(result.pop("result_json"))
        result["stage"] = STAGES[min(result["stage_index"], len(STAGES)-1)]["key"]
        return result

    def _events(self, rows):
        values = []
        for row in rows:
            value = dict(row)
            value["detail"] = json.loads(value.pop("detail_json"))
            values.append(value)
        return values

    def _refresh(self, db, run):
        if run is None:
            return None
        target = json.loads(run["settings_json"]).get("stop_after_posts")
        if (run["status"] in ACTIVE and type(target) is int and target > 0
                and run["completed_count"] >= target):
            db.execute("UPDATE production_runs SET status='completed',current_stage=NULL,pause_reason='목표 제작 건수 달성',updated_at=? WHERE id=?",
                       (timestamp(), run["id"]))
            self._event(db, run["id"], None, None, "run.completed", "목표 제작 건수를 달성해 자동 제작을 완료했습니다.",
                        {"reason": "target_count_reached", "stop_after_posts": target,
                         "completed_count": run["completed_count"]})
            self._retire_run_work(db, run["id"])
        elif run["status"] in ACTIVE and self._deadline_reached(run):
            db.execute("UPDATE production_runs SET status='completed',pause_reason='종료 시각 도달',updated_at=? WHERE id=?",
                       (timestamp(), run["id"]))
            self._event(db, run["id"], None, None, "run.deadline", "종료 시각에 도달해 새 작업 시작을 중지했습니다.")
            self._retire_run_work(db, run["id"])
        elif run["status"] == "scheduled" and self._time(run["start_at"]) <= datetime.now(timezone.utc):
            db.execute("UPDATE production_runs SET status='running',updated_at=? WHERE id=?", (timestamp(), run["id"]))
            self._event(db, run["id"], None, None, "run.started", "예약 시각이 되어 자동 제작 실행을 시작합니다.")
        return db.execute("SELECT * FROM production_runs WHERE id=?", (run["id"],)).fetchone()

    def _deadline_reached(self, run, current=None):
        return bool(run["end_at"] and self._time(run["end_at"]) <= (current or datetime.now(timezone.utc)))

    def _retire_run_work(self, db, run_id):
        """Return briefs to editing while retaining ownership of in-flight calls."""
        self._cancel_pending_production_videos(db, run_id)
        self._specialist_run_stopped(db, run_id)
        db.execute("UPDATE briefs SET status='draft',version=version+1,run_id=NULL,updated_at=? WHERE run_id=? AND status='queued'", (timestamp(), run_id))
        db.execute("UPDATE briefs SET status='failed',updated_at=? WHERE run_id=? AND status='producing'", (timestamp(), run_id))
        for cycle in db.execute("SELECT id FROM production_cycles WHERE run_id=? AND status IN ('pending','suspended')", (run_id,)).fetchall():
            db.execute("UPDATE production_cycles SET status='cancelled',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?", (timestamp(), cycle["id"]))
            db.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE cycle_id=? AND status IN ('pending','paused')", (timestamp(), cycle["id"]))

    def _retire_if_terminal(self, db, run_id):
        run = self._refresh(db, db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone())
        if run["status"] in ["stopped", "completed"]:
            self._retire_run_work(db, run_id)
        return run

    def _expire_sources(self, db):
        current = datetime.now(timezone.utc)
        for row in db.execute("SELECT * FROM source_materials WHERE status='active' AND expires_at IS NOT NULL").fetchall():
            if self._time(row["expires_at"]) <= current:
                db.execute("UPDATE source_materials SET status='expired',updated_at=? WHERE id=?", (timestamp(), row["id"]))
                self._event(db, None, None, "sources", "source.expired", "소재의 유효기간이 만료되었습니다.",
                            {"source_id": row["id"], "title": row["title"]}, "warning")

    def start_run(self, body=None):
        body = body or {}
        config, persona = self.config(), self.persona(body.get("persona_id"))
        stop_after_posts = body.get("stop_after_posts")
        if stop_after_posts is not None and (type(stop_after_posts) is not int or not 1 <= stop_after_posts <= 1000):
            raise self.problem("목표 제작 건수는 1~1000 사이의 정수여야 합니다. 제한 없이 제작하려면 null을 입력해 주세요.")
        media_mode = body.get("media_mode", config.get("media_mode", "images"))
        if media_mode not in ["images", "mixed", "video", "video_only"]:
            raise self.problem("미디어 형식은 images, mixed, video_only 중에서 선택해 주세요. 기존 video 형식도 지원합니다.")
        config = dict(config, media_mode=media_mode, stop_after_posts=stop_after_posts)
        requested_video = self.validate_auto_video(body["video"]) if "video" in body else None
        if requested_video is not None:
            config["video"] = dict(config.get("video", {}), **requested_video)
        now = datetime.now(timezone.utc)
        start = self._time(body.get("start_at", config["start_at"]))
        end_value = body.get("end_at", config.get("generation_end_at"))
        end = self._time(end_value) if end_value is not None else None
        if end is not None and (end <= start or end <= now):
            raise self.problem("종료 시각은 시작 시각과 현재 시각보다 뒤여야 합니다.")
        with self.db() as db:
            return self._run(self._start_run_db(db, persona, config, start, end, "continuous", body.get("media_mode"), requested_video,
                                               body.get("stop_after_posts", UNSET_PRODUCTION_LIMIT)))

    def _start_run_db(self, db, persona, config, start, end, mode, requested_media_mode=None, requested_video=None,
                      requested_stop_after_posts=UNSET_PRODUCTION_LIMIT):
        for candidate in db.execute("SELECT * FROM production_runs WHERE status IN ('scheduled','running','paused','blocked') ORDER BY created_at").fetchall():
            existing = self._refresh(db, candidate)
            if existing["status"] not in ACTIVE:
                continue
            if existing["persona_id"] != persona["id"]:
                raise self.problem("다른 페르소나의 제작 실행이 있습니다. 해당 실행을 중지한 뒤 시작해 주세요.", 409)
            if existing["persona_version"] != persona["version"]:
                raise self.problem("기존 실행은 이전 페르소나 버전을 사용합니다. 기존 실행을 중지하고 새로 시작해 주세요.", 409)
            settings = json.loads(existing["settings_json"])
            if requested_media_mode is not None and requested_media_mode != settings.get("media_mode", "images"):
                raise self.problem("실행 중인 제작의 미디어 형식은 고정되어 있습니다. 기존 실행을 중지한 뒤 새 실행을 시작해 주세요.", 409)
            if requested_video is not None and requested_video != self.run_video_settings(settings):
                raise self.problem("실행 중인 영상 길이와 해상도는 고정되어 있습니다. 기존 실행을 중지한 뒤 새 실행을 시작해 주세요.", 409)
            if requested_stop_after_posts is not UNSET_PRODUCTION_LIMIT and requested_stop_after_posts != settings.get("stop_after_posts"):
                raise self.problem("실행 중인 목표 제작 건수는 고정되어 있습니다. 기존 실행을 중지한 뒤 새 실행을 시작해 주세요.", 409)
            if mode == "continuous" and settings.get("production_mode") == "queued":
                settings["production_mode"] = "continuous"
                db.execute("UPDATE production_runs SET settings_json=?,updated_at=? WHERE id=?", (dumps(settings), timestamp(), existing["id"]))
                self._event(db, existing["id"], None, None, "run.continuous", "기획안 제작 실행을 연속 자동 생성으로 전환했습니다.")
                existing = db.execute("SELECT * FROM production_runs WHERE id=?", (existing["id"],)).fetchone()
            return existing
        run_id = "run-" + uuid.uuid4().hex[:16]
        status = "scheduled" if start > datetime.now(timezone.utc) else "running"
        settings = dict(config, production_mode=mode, generation_end_at=end.isoformat() if end else None)
        settings.setdefault("stop_after_posts", None)
        settings.setdefault("media_mode", "images")
        settings["video"] = dict(settings.get("video", {}), **self.run_video_settings(settings))
        if settings["media_mode"] == "video_only":
            settings["video"]["required"] = True
        settings["source_research_enabled"] = config.get("source_research_enabled", True) is True
        self._freeze_specialists(settings)
        db.execute("""INSERT INTO production_runs
            (id,persona_id,persona_version,account,status,start_at,end_at,created_at,updated_at,persona_json,settings_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                   (run_id, persona["id"], persona["version"], config["instagram"].get("account"), status,
                    start.isoformat(), end.isoformat() if end else None, timestamp(), timestamp(), dumps(persona), dumps(settings)))
        if mode == "continuous":
            message = (str(settings["stop_after_posts"]) + "건 제작을 목표로 자동 생성 실행을 등록했습니다."
                       if settings["stop_after_posts"] is not None else "건수 제한 없이 자동 생성 실행을 등록했습니다.")
        else:
            message = "요청한 기획안의 제작 실행을 등록했습니다."
        self._event(db, run_id, None, None, "run.created", message,
                    {"start_at": start.isoformat(), "end_at": end.isoformat() if end else None, "stop_after_posts": settings["stop_after_posts"], "mode": mode, "media_mode": settings["media_mode"], "source_research_enabled": settings["source_research_enabled"], "specialist_agents_enabled": settings["specialist_agents_enabled"]})
        return db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone()

    def update_run_deadline(self, run_id, body):
        if set(body) != {"end_at"}:
            raise self.problem("end_at만 지정해 주세요. null이면 종료 시각 제한을 해제합니다.")
        end = self._time(body["end_at"]) if body["end_at"] is not None else None
        with self.db() as db:
            run = self._refresh(db, db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone())
            if run is None:
                raise self.problem("실행을 찾을 수 없습니다.", 404)
            if run["status"] not in ACTIVE:
                raise self.problem("종료된 실행의 일정은 변경할 수 없습니다.", 409)
            if end is not None and (end <= self._time(run["start_at"]) or end <= datetime.now(timezone.utc)):
                raise self.problem("종료 시각은 시작 시각과 현재 시각보다 뒤여야 합니다.")
            value = end.isoformat() if end else None
            if run["end_at"] != value:
                settings = dict(json.loads(run["settings_json"]), generation_end_at=value)
                db.execute("UPDATE production_runs SET end_at=?,settings_json=?,updated_at=? WHERE id=?",
                           (value, dumps(settings), timestamp(), run_id))
                self._event(db, run_id, None, run["current_stage"], "run.deadline_updated",
                            "종료 시각 제한을 해제했습니다." if end is None else "종료 시각을 변경했습니다.",
                            {"previous_end_at": run["end_at"], "end_at": value})
            return self._run(db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone())

    def control_run(self, run_id, action):
        with self.db() as db:
            run = self._refresh(db, db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone())
            if run is None:
                raise self.problem("실행을 찾을 수 없습니다.", 404)
            if action == "stop":
                if run["status"] in ["stopped", "completed"]:
                    return self._run(run)
                status, message = "stopped", "사용자가 자동 생성을 중지했습니다. 진행 중인 결과는 보존합니다."
            elif action == "pause":
                if run["status"] == "paused":
                    return self._run(run)
                if run["status"] not in ["scheduled", "running"]:
                    raise self.problem("현재 실행은 일시정지할 수 없습니다.", 409)
                status, message = "paused", "사용자가 일시정지했습니다. 새 외부 호출을 시작하지 않습니다."
            elif action == "resume":
                if run["status"] not in ["paused", "blocked"]:
                    raise self.problem("일시정지 또는 확인 대기 중인 실행만 재개할 수 있습니다.", 409)
                uncertain = db.execute("SELECT 1 FROM production_cycles WHERE run_id=? AND status='uncertain'", (run_id,)).fetchone()
                if uncertain:
                    raise self.problem("결과가 불확실한 작업을 먼저 확인해야 합니다.", 409)
                status = "scheduled" if self._time(run["start_at"]) > datetime.now(timezone.utc) else "running"
                message = "사용자가 자동 생성을 재개했습니다."
            else:
                raise self.problem("알 수 없는 실행 제어입니다.")
            db.execute("UPDATE production_runs SET status=?,pause_reason=?,updated_at=? WHERE id=?",
                       (status, "사용자 요청" if status in ["paused", "stopped"] else None, timestamp(), run_id))
            if status == "stopped":
                self._retire_run_work(db, run_id)
            self._event(db, run_id, None, run["current_stage"], "run."+action, message)
            return self._run(db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone())

    def upsert_source(self, body):
        body = dict(body, affiliate=normalize_affiliate(body.get("affiliate")))
        affiliates = self.config().get("brand_targets", list(AFFILIATE_DOMAINS))
        if body.get("affiliate") not in affiliates:
            raise self.problem("대상 GS 계열사를 선택해 주세요.")
        if not isinstance(body.get("title"), str) or not body["title"].strip():
            raise self.problem("소재 이름이 필요합니다.")
        url = urlparse(body.get("url", ""))
        if url.scheme != "https" or not url.hostname:
            raise self.problem("공개 출처의 HTTPS URL이 필요합니다.")
        verified = self._time(body.get("verified_at"))
        if verified > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise self.problem("미래 시각을 출처 확인일로 기록할 수 없습니다.")
        expiration = self._time(body["expires_at"]) if body.get("expires_at") else None
        claims = body.get("claims", [])
        if not isinstance(claims, list) or any(not isinstance(c, str) for c in claims):
            raise self.problem("활용할 정보는 문자열 목록이어야 합니다.")
        if body.get("visibility") not in ["internal", "subtle", "explicit"]:
            raise self.problem("공개 노출 범위를 선택해 주세요.")
        with self.db() as db:
            found = db.execute("SELECT * FROM source_materials WHERE url=?", (body["url"],)).fetchone()
            source_id = found["id"] if found else body.get("id", "source-"+uuid.uuid4().hex[:16])
            if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", source_id):
                raise self.problem("소재 ID가 올바르지 않습니다.")
            status = "expired" if expiration and expiration <= datetime.now(timezone.utc) else "active"
            db.execute("""INSERT INTO source_materials
                (id,affiliate,title,url,verified_at,expires_at,claims_json,visibility,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET affiliate=excluded.affiliate,title=excluded.title,url=excluded.url,
                verified_at=excluded.verified_at,expires_at=excluded.expires_at,claims_json=excluded.claims_json,
                visibility=excluded.visibility,status=excluded.status,updated_at=excluded.updated_at,
                origin='manual',discovery_json='{}',source_version=source_materials.source_version+1""",
                       (source_id, body["affiliate"], body["title"], body["url"], verified.isoformat(),
                        expiration.isoformat() if expiration else None, dumps(claims), body["visibility"], status,
                        found["created_at"] if found else timestamp(), timestamp()))
            self._event(db, None, None, "sources", "source.saved", "GS 소재와 출처를 저장했습니다.",
                        {"source_id": source_id, "affiliate": body["affiliate"], "title": body["title"], "status": status})
            return self._source(db.execute("SELECT * FROM source_materials WHERE id=?", (source_id,)).fetchone())

    def _source(self, row):
        result = dict(row)
        result["claims"] = json.loads(result.pop("claims_json"))
        result["provenance"] = json.loads(result.pop("discovery_json", "{}"))
        return result

    def logs(self, run_id=None, after_id=0, limit=100):
        limit = min(max(int(limit), 1), 500)
        with self.db() as db:
            if run_id:
                rows = db.execute("SELECT * FROM production_events WHERE (run_id=? OR run_id IS NULL) AND id>? ORDER BY id LIMIT ?",
                                  (run_id, int(after_id), limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM production_events WHERE id>? ORDER BY id LIMIT ?", (int(after_id), limit)).fetchall()
            return self._events(rows)

    def automation_state(self):
        with self.db() as db:
            self._expire_sources(db)
            row = db.execute("SELECT * FROM production_runs ORDER BY created_at DESC LIMIT 1").fetchone()
            run = self._refresh(db, row)
            sources = [self._source(s) for s in db.execute("SELECT * FROM source_materials ORDER BY updated_at DESC")]
            events = self._events(list(reversed(db.execute("SELECT * FROM production_events ORDER BY id DESC LIMIT 100").fetchall())))
            worker_status, seen = "idle", None
            if run and run["status"] in ACTIVE:
                seen = run["last_heartbeat_at"]
                running = db.execute("SELECT * FROM production_cycles WHERE run_id=? AND status='running'", (run["id"],)).fetchone()
                if running:
                    worker_status = "stale" if self._time(running["lease_expires_at"]) <= datetime.now(timezone.utc) else "active"
                else:
                    worker_status = "waiting"
            specialists = self._specialists_state(db, run)
            stage_settings = {"specialist_agents_enabled": specialists["enabled"], "specialist_roles": specialists["roles"]}
            settings = json.loads(run["settings_json"]) if run else self.config()
            stages = [stage for stage in STAGES if stage["key"] != "quality" or settings.get("ai_quality_review_enabled", True)]
            return {"run": self._run(run), "stages": self._specialist_stages(stage_settings, stages), "logs": events, "sources": sources,
                    "specialists": specialists,
                    "worker_status": worker_status, "worker_last_seen_at": seen,
                    "worker_runtime": worker_state(self),
                    "source_research": self._research_state(db, run)}

    def _defer_quality(self, db, cycle, outputs):
        """Record a review handoff, never a fabricated quality pass or approval."""
        if outputs.get("review_handoff", {}).get("ai_quality_review") == "deferred":
            return
        job = db.execute("SELECT error FROM jobs WHERE id=?", (cycle["id"] + ":quality",)).fetchone()
        notes = ["AI 품질 검수는 보류했습니다. 게시 승인 전에 사람이 영상·음성·자막·인물·정보를 확인해 주세요."]
        if job and job["error"]:
            notes.append(self._safe_log(job["error"]))
        handoff = {"ai_quality_review": "deferred", "human_review_required": True, "notes": notes}
        outputs["review_handoff"] = handoff
        db.execute("UPDATE jobs SET status='skipped',updated_at=? WHERE id=?", (timestamp(), cycle["id"] + ":quality"))
        for assignment in db.execute("SELECT * FROM specialist_assignments WHERE cycle_id=? AND stage='quality' AND status IN ('assigned','uncertain')",
                                     (cycle["id"],)).fetchall():
            self._specialist_change(db, assignment, "skipped", notes[0])
        self._event(db, cycle["run_id"], cycle["id"], "quality", "stage.skipped",
                    "AI 품질 검수를 보류하고 기존 결과로 피드 등록을 진행합니다. 사람의 게시 승인은 별도입니다.", handoff)

    def defer_quality_review(self, run_id):
        """Explicit operator change for an existing run, including a review-only block."""
        with self.db() as db:
            run = db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise self.problem("실행을 찾을 수 없습니다.", 404)
            if run["status"] not in ACTIVE:
                raise self.problem("종료된 실행은 변경할 수 없습니다.", 409)
            cycle = db.execute("SELECT * FROM production_cycles WHERE run_id=? AND status IN ('pending','running','uncertain','suspended') ORDER BY number LIMIT 1",
                               (run_id,)).fetchone()
            at_quality = cycle is not None and STAGES[cycle["stage_index"]]["key"] == "quality"
            if at_quality and cycle["status"] == "running":
                raise self.problem("진행 중인 검수 작업자가 결과를 저장한 뒤 보류해 주세요.", 409)
            settings = json.loads(run["settings_json"])
            if settings.get("ai_quality_review_enabled", True):
                settings["ai_quality_review_enabled"] = False
                db.execute("UPDATE production_runs SET settings_json=?,updated_at=? WHERE id=?", (dumps(settings), timestamp(), run_id))
                self._event(db, run_id, None, None, "run.review_policy_changed",
                            "AI 품질 검수 단계를 자동 제작에서 제외했습니다. 생성 결과와 미확인 항목은 사람의 검수로 넘깁니다.",
                            {"ai_quality_review_enabled": False, "human_approval_required": True})
            if at_quality:
                outputs = json.loads(cycle["result_json"])
                self._check_result(db, cycle, "images", outputs.get("images", {}))
                self._defer_quality(db, cycle, outputs)
                db.execute("UPDATE production_cycles SET stage_index=6,status='pending',result_json=?,lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,completed_token=NULL,updated_at=? WHERE id=?",
                           (dumps(outputs), timestamp(), cycle["id"]))
                # An unrelated worker/budget block and a user pause stay intact.
                review_block = run["status"] == "blocked" and cycle["status"] == "uncertain" and run["pause_reason"] == "외부 작업 결과 확인 필요"
                db.execute("UPDATE production_runs SET current_stage='register',status=?,pause_reason=?,updated_at=? WHERE id=?",
                           ("running" if review_block else run["status"], None if review_block else run["pause_reason"], timestamp(), run_id))
            return self._run(db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone())

    def worker_next(self, worker_id, expected_run_id=None):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise self.problem("작업자 ID가 필요합니다.")
        runtime = worker_state(self)
        if runtime.get("online") and worker_id != runtime.get("worker_id"):
            return {"should_work": False, "reason": "managed_locally"}
        with self.db() as db:
            self._expire_sources(db)
            run = db.execute("SELECT * FROM production_runs ORDER BY created_at DESC LIMIT 1").fetchone()
            run = self._refresh(db, run)
            if not run:
                return {"should_work": False, "reason": "no_run"}
            if expected_run_id is not None and run["id"] != expected_run_id:
                return {"should_work": False, "reason": "run_changed"}
            if (runtime.get("online") and runtime.get("status") in ("starting", "running", "paused", "stopping")
                    and runtime.get("worker_id") == worker_id and runtime.get("run_id") != run["id"]):
                return {"should_work": False, "reason": "run_changed"}
            db.execute("UPDATE production_runs SET last_heartbeat_at=? WHERE id=?", (timestamp(), run["id"]))
            if run["status"] != "running":
                return {"should_work": False, "reason": run["status"], "run": self._run(run)}
            # A run owns its persona snapshot. Editing or selecting a library
            # profile must not change inputs halfway through a generation.
            cycle = db.execute("SELECT * FROM production_cycles WHERE run_id=? AND status IN ('pending','running','uncertain','suspended') ORDER BY number LIMIT 1",
                               (run["id"],)).fetchone()
            if cycle and cycle["status"] == "running":
                if self._time(cycle["lease_expires_at"]) <= datetime.now(timezone.utc):
                    db.execute("UPDATE production_cycles SET status='uncertain',updated_at=? WHERE id=?", (timestamp(), cycle["id"]))
                    db.execute("UPDATE jobs SET status='uncertain',updated_at=? WHERE cycle_id=? AND status='running'", (timestamp(), cycle["id"]))
                    db.execute("UPDATE production_runs SET status='blocked',pause_reason='중단된 작업 결과 확인 필요',updated_at=? WHERE id=?",
                               (timestamp(), run["id"]))
                    self._specialist_cycle_status(db, cycle["id"], "uncertain", "조정자의 작업 소유권이 만료되었습니다. 전문가 결과를 확인하기 전에는 다시 위임하지 않습니다.")
                    self._event(db, run["id"], cycle["id"], STAGES[cycle["stage_index"]]["key"], "worker.stale",
                                "작업자 응답이 끊겼습니다. 기존 외부 결과를 확인하기 전에는 재생성하지 않습니다.", level="warning")
                    return {"should_work": False, "reason": "uncertain"}
                return {"should_work": False, "reason": "in_flight", "cycle": self._cycle(cycle),
                        "run": self._run(run)}
            if cycle and cycle["status"] == "uncertain":
                return {"should_work": False, "reason": "uncertain", "cycle": self._cycle(cycle)}
            if cycle is None:
                brief = db.execute("SELECT * FROM briefs WHERE run_id=? AND status='queued' ORDER BY created_at LIMIT 1", (run["id"],)).fetchone()
                settings = json.loads(run["settings_json"])
                if not brief and settings.get("production_mode") == "queued":
                    db.execute("UPDATE production_runs SET status='completed',pause_reason='요청한 기획안 제작 완료',updated_at=? WHERE id=?", (timestamp(), run["id"]))
                    self._event(db, run["id"], None, None, "run.queue_completed", "요청한 기획안의 제작을 마쳤습니다.")
                    return {"should_work": False, "reason": "queue_completed", "run": self._run(db.execute("SELECT * FROM production_runs WHERE id=?", (run["id"],)).fetchone())}
                number = run["cycle_number"] + 1
                cycle_id = run["id"] + "-c" + str(number).zfill(4)
                db.execute("INSERT INTO production_cycles (id,run_id,number,content_id,status,created_at,updated_at,brief_id) VALUES (?,?,?,?,'pending',?,?,?)",
                           (cycle_id, run["id"], number, cycle_id, timestamp(), timestamp(), brief["id"] if brief else None))
                if brief:
                    db.execute("UPDATE briefs SET status='producing',cycle_id=?,content_id=?,updated_at=? WHERE id=?", (cycle_id, cycle_id, timestamp(), brief["id"]))
                    self._event(db, run["id"], cycle_id, "planning", "brief.claimed", "저장한 기획안을 제작 입력으로 가져왔습니다.", {"brief_id": brief["id"], "version": brief["version"]})
                db.execute("UPDATE production_runs SET cycle_number=?,updated_at=? WHERE id=?", (number, timestamp(), run["id"]))
                self._event(db, run["id"], cycle_id, "sources", "cycle.created", str(number)+"번째 콘텐츠 제작 순환을 시작합니다.")
                cycle = db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle_id,)).fetchone()
            stage = STAGES[cycle["stage_index"]]["key"]
            job_id = cycle["id"] + ":" + stage
            settings = json.loads(run["settings_json"])
            brief = db.execute("SELECT * FROM briefs WHERE id=?", (cycle["brief_id"],)).fetchone() if cycle["brief_id"] else None
            video_guides = self.cycle_video_guides(db, cycle["id"], settings.get("media_mode", "images"))
            max_attempts = min(max(int(settings.get("max_attempts_per_job", 2)), 1), 3)
            db.execute("""INSERT OR IGNORE INTO jobs
                (id,stage,status,attempts,max_attempts,input_json,updated_at,run_id,cycle_id)
                VALUES (?,?,'pending',0,?,?,?,?,?)""",
                       (job_id, stage, max_attempts, dumps({"run_id": run["id"], "cycle_id": cycle["id"],
                                                          "content_id": cycle["content_id"], "persona_id": run["persona_id"],
                                                          "persona_version": run["persona_version"], "brief": dict(brief) if brief else None,
                                                          "media_mode": settings.get("media_mode", "images"),
                                                          "video_settings": self.run_video_settings(settings) if settings.get("media_mode") in ("mixed", "video", "video_only") else None,
                                                          "video_guides": video_guides,
                                                          "video_guide_policy": self.cycle_video_guide_policy(db, cycle["id"]) if video_guides else None,
                                                          "source_research": self._research_input(db, settings) if stage == "sources" else None,
                                                          "specialist": self._specialist_role(settings, stage),
                                                          "previous_results": json.loads(cycle["result_json"])}), timestamp(), run["id"], cycle["id"]))
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            continuing = cycle["status"] == "suspended" and job["status"] == "paused"
            if not continuing and job["attempts"] >= job["max_attempts"]:
                self._cycle_failed(db, run["id"], cycle, stage, "단계 재시도 한도에 도달했습니다.")
                return {"should_work": False, "reason": "retry_exhausted"}
            # The job keeps its frozen persona/brief inputs, but repaired upstream
            # outputs must replace the dependencies from its previous attempt.
            inputs = json.loads(job["input_json"])
            inputs["previous_results"] = json.loads(cycle["result_json"])
            inputs["ai_quality_review_enabled"] = settings.get("ai_quality_review_enabled", True)
            inputs["specialist"] = self._specialist_role(settings, stage)
            db.execute("UPDATE jobs SET input_json=? WHERE id=?", (dumps(inputs), job_id))
            token = secrets.token_hex(24)
            expires = (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
            db.execute("UPDATE production_cycles SET status='running',lease_token=?,lease_owner=?,lease_expires_at=?,updated_at=? WHERE id=?",
                       (token, worker_id, expires, timestamp(), cycle["id"]))
            db.execute("UPDATE jobs SET status='running',attempts=attempts+?,error=NULL,updated_at=? WHERE id=?", (0 if continuing else 1, timestamp(), job_id))
            db.execute("UPDATE production_runs SET current_stage=?,last_heartbeat_at=?,updated_at=? WHERE id=?",
                       (stage, timestamp(), timestamp(), run["id"]))
            self._event(db, run["id"], cycle["id"], stage, "stage.resumed" if continuing else "stage.started",
                        next(s["label"] for s in STAGES if s["key"] == stage)+(" 단계를 저장 지점에서 재개합니다." if continuing else " 단계를 시작합니다."),
                        {"job_id": job_id, "attempt": job["attempts"]+(0 if continuing else 1), "worker_id": worker_id})
            return {"should_work": True, "run": self._run(db.execute("SELECT * FROM production_runs WHERE id=?", (run["id"],)).fetchone()),
                    "cycle": self._cycle(db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle["id"],)).fetchone()),
                    "job": dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()), "lease_token": token}

    def worker_inspect(self, cycle_id=None):
        with self.db() as db:
            if cycle_id:
                cycle = db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle_id,)).fetchone()
                run = db.execute("SELECT * FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone() if cycle else None
            else:
                run = db.execute("SELECT * FROM production_runs ORDER BY created_at DESC LIMIT 1").fetchone()
                cycle = db.execute("SELECT * FROM production_cycles WHERE run_id=? ORDER BY number DESC LIMIT 1", (run["id"],)).fetchone() if run else None
            jobs = [dict(r) for r in db.execute("SELECT * FROM jobs WHERE cycle_id=? ORDER BY updated_at", (cycle["id"],))] if cycle else []
            return {"run": self._run(run), "cycle": self._cycle(cycle) if cycle else None, "jobs": jobs}

    def worker_checkpoint(self, cycle_id, lease_token, result, release=False):
        if not isinstance(result, dict):
            raise self.problem("중간 결과는 JSON 객체여야 합니다.")
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            if cycle["status"] == "uncertain":
                raise self.problem("불확실한 외부 결과는 확인 없이 작업 소유권을 해제할 수 없습니다.", 409)
            stage = STAGES[cycle["stage_index"]]["key"]
            db.execute("UPDATE jobs SET result_json=?,status=?,updated_at=? WHERE id=?",
                       (dumps(result), "paused" if release else "running", timestamp(), cycle_id+":"+stage))
            if release:
                self._specialist_cycle_status(db, cycle_id, "interrupted", "진행 중인 외부 호출이 없음을 확인하고 체크포인트에서 작업을 넘겼습니다.")
                db.execute("UPDATE production_cycles SET status='suspended',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?", (timestamp(), cycle_id))
            else:
                db.execute("UPDATE production_cycles SET lease_expires_at=?,updated_at=? WHERE id=?",
                           ((datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(), timestamp(), cycle_id))
            db.execute("UPDATE production_runs SET last_heartbeat_at=? WHERE id=?", (timestamp(), cycle["run_id"]))
            self._event(db, cycle["run_id"], cycle_id, stage, "stage.checkpoint", "단계의 중간 결과를 저장했습니다.",
                        {"result": result, "released": release, "summary": "중간 결과 항목 저장: " + ", ".join(str(key) for key in result)})
            self._retire_if_terminal(db, cycle["run_id"])
            return {"saved": True, "released": release}

    def _leased(self, db, cycle_id, token):
        cycle = db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle_id,)).fetchone()
        if not cycle:
            raise self.problem("제작 순환을 찾을 수 없습니다.", 404)
        if cycle["status"] not in ["running", "uncertain"] or not token or not secrets.compare_digest(cycle["lease_token"] or "", token):
            raise self.problem("다른 단계이거나 유효하지 않은 작업 소유권입니다.", 409)
        return cycle

    def worker_ping(self, cycle_id, lease_token, external_job_id=None):
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            run = self._refresh(db, db.execute("SELECT * FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone())
            expiry = (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
            db.execute("UPDATE production_cycles SET lease_expires_at=?,updated_at=? WHERE id=?", (expiry, timestamp(), cycle_id))
            db.execute("UPDATE production_runs SET last_heartbeat_at=? WHERE id=?", (timestamp(), cycle["run_id"]))
            if external_job_id:
                job_id = cycle_id + ":" + STAGES[cycle["stage_index"]]["key"]
                db.execute("UPDATE jobs SET external_job_id=?,updated_at=? WHERE id=?", (external_job_id, timestamp(), job_id))
                self._event(db, cycle["run_id"], cycle_id, STAGES[cycle["stage_index"]]["key"], "stage.external_job",
                            "외부 생성 작업 ID를 기록했습니다.", {"external_job_id": external_job_id})
            return {"can_continue": run["status"] == "running" and cycle["status"] == "running",
                    "run_status": run["status"], "lease_expires_at": expiry}

    def worker_log(self, cycle_id, lease_token, event, message, detail=None, level="info"):
        if level not in ["info", "warning", "error"]:
            raise self.problem("올바르지 않은 로그 수준입니다.")
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            event_id = self._event(db, cycle["run_id"], cycle_id, STAGES[cycle["stage_index"]]["key"],
                                   str(event), str(message), detail, level)
            return {"event_id": event_id}

    def _check_result(self, db, cycle, stage, result):
        if not isinstance(result, dict):
            raise self.problem("단계 결과는 JSON 객체여야 합니다.")
        previous = json.loads(cycle["result_json"])
        run_settings = json.loads(db.execute("SELECT settings_json FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone()[0])
        if stage == "planning" and run_settings.get("media_mode") == "video_only" and result.get("content_format") != "video":
            raise self.problem("영상만 실행의 기획은 content_format을 video로 지정해야 합니다.", 409)
        if stage in ["sources", "planning"]:
            ids = result.get("source_ids", [])
            if not isinstance(ids, list):
                raise self.problem("source_ids는 목록이어야 합니다.")
            for source_id in ids:
                source = db.execute("SELECT * FROM source_materials WHERE id=?", (source_id,)).fetchone()
                if not source or source["status"] != "active" or (source["expires_at"] and self._time(source["expires_at"]) <= datetime.now(timezone.utc)):
                    raise self.problem("만료되었거나 확인되지 않은 소재는 사용할 수 없습니다.")
        if stage == "planning":
            if not result.get("title") or not isinstance(result.get("topic_key"), str) or not result["topic_key"].strip():
                raise self.problem("주제 제목과 중복 확인용 topic_key가 필요합니다.")
            topic = re.sub(r"\s+", " ", result["topic_key"].strip().lower())
            for other in db.execute("SELECT result_json FROM production_cycles WHERE id<>? AND status<>'failed'", (cycle["id"],)):
                planned = json.loads(other["result_json"]).get("planning", {})
                if re.sub(r"\s+", " ", planned.get("topic_key", "").strip().lower()) == topic:
                    raise self.problem("이미 기획된 주제입니다. 다른 일상 주제를 선택해 주세요.", 409)
            for row in db.execute("SELECT payload FROM revisions r JOIN contents c ON c.id=r.content_id AND c.current_version=r.version"):
                if re.sub(r"\s+", " ", json.loads(row["payload"]).get("topic_key", "").strip().lower()) == topic:
                    raise self.problem("기존 피드와 동일한 주제입니다.", 409)
        if stage == "storyboard" and (not isinstance(result.get("cards"), list) or not result["cards"]):
            raise self.problem("가변 길이의 cards 스토리보드가 필요합니다.")
        if stage == "copy" and (not isinstance(result.get("caption"), str) or
                                "AI로 만든 가상 인물의 창작 일상입니다." not in result["caption"]):
            raise self.problem("게시 문안과 가상 인물 표시가 필요합니다.")
        if stage == "images":
            media = result.get("media")
            if not isinstance(media, list) or not media:
                raise self.problem("실제 생성한 미디어 경로 목록이 필요합니다.")
            for entry in media:
                path = (self.root / entry).resolve() if isinstance(entry, str) else None
                if path is None or self.root not in path.parents or not path.is_file():
                    raise self.problem("실제로 저장된 프로젝트 미디어만 완료 처리할 수 있습니다.")
            self.require_run_media(run_settings, media)
        if stage == "quality" and result.get("passed") is not True:
            raise self.problem("검수를 통과하지 못했습니다. worker-fail로 실패 사유를 남기거나 필요한 단계로 수정 요청하세요.")
        if stage == "quality" and (previous.get("images", {}).get("video_delivery") or {}).get("version") == 1:
            checks = result.get("video_checks", {})
            if not isinstance(checks, dict) or any(checks.get(key) is not True for key in
                                                  ("voice_heard", "subtitles_readable", "voice_matches_subtitles")):
                raise self.problem("영상을 재생해 한국어 보이스·자막 가독성·대사와 자막의 일치를 확인하고 video_checks로 기록해야 합니다.")
        if stage == "register":
            if result.get("content_id") != cycle["content_id"]:
                raise self.problem("현재 제작 순환의 콘텐츠 ID가 아닙니다.")
            content = db.execute("SELECT * FROM contents WHERE id=?", (cycle["content_id"],)).fetchone()
            if not content or content["current_version"] != result.get("version"):
                raise self.problem("대시보드에 실제 등록된 콘텐츠 버전이 필요합니다.")
            payload = json.loads(db.execute("SELECT payload FROM revisions WHERE content_id=? AND version=?",
                                           (cycle["content_id"], content["current_version"])).fetchone()[0])
            self.require_run_media(run_settings, [card["media"] for card in payload["cards"]])
            run = db.execute("SELECT persona_id,persona_version FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone()
            if payload.get("persona_id", self._original_persona()["id"]) != run["persona_id"] or payload.get("persona_version") != run["persona_version"]:
                raise self.problem("등록된 콘텐츠가 이 실행의 페르소나 버전과 일치하지 않습니다.", 409)
            if run_settings.get("ai_quality_review_enabled", True) and previous.get("quality", {}).get("passed") is not True:
                raise self.problem("품질 검수 결과가 필요합니다.")
            if (not run_settings.get("ai_quality_review_enabled", True)
                    and previous.get("quality", {}).get("passed") is not True
                    and previous.get("review_handoff", {}).get("ai_quality_review") != "deferred"):
                raise self.problem("사람에게 넘길 검수 보류 기록이 필요합니다.")

    def worker_complete(self, cycle_id, lease_token, result, external_job_id=None):
        with self.db() as db:
            existing = db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle_id,)).fetchone()
            if existing and lease_token and existing["completed_token"] == lease_token:
                return {"duplicate": True, "cycle": self._cycle(existing)}
            cycle = self._leased(db, cycle_id, lease_token)
            stage = STAGES[cycle["stage_index"]]["key"]
            if not isinstance(result, dict):
                raise self.problem("단계 결과는 JSON 객체여야 합니다.")
            result = self._research_stage_result(db, cycle, stage, result)
            self._check_result(db, cycle, stage, result)
            recovered_video = None
            if stage == "images" and cycle["status"] == "uncertain":
                video = self._verified_terminal_video(db, cycle, result.get("video_job_id"), "completed")
                if video and result.get("media") == [json.loads(video["result_json"] or "{}").get("media_path")]:
                    recovered_video = video["id"]
            result = self._specialist_complete(db, cycle, stage, result)
            outputs = json.loads(cycle["result_json"])
            outputs[stage] = result
            job_id = cycle_id+":"+stage
            db.execute("UPDATE jobs SET status='completed',result_json=?,external_job_id=COALESCE(?,external_job_id),error=NULL,updated_at=? WHERE id=?",
                       (dumps(result), external_job_id, timestamp(), job_id))
            final = stage == "register"
            next_index = cycle["stage_index"] if final else cycle["stage_index"] + 1
            settings = json.loads(db.execute("SELECT settings_json FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone()[0])
            if stage == "images" and not settings.get("ai_quality_review_enabled", True):
                self._defer_quality(db, cycle, outputs)
                next_index = 6  # Keep persisted legacy stage indexes stable.
            db.execute("""UPDATE production_cycles SET stage_index=?,status=?,result_json=?,completed_token=?,
                lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?""",
                       (next_index, "completed" if final else "pending",
                        dumps(outputs), lease_token, timestamp(), cycle_id))
            self._event(db, cycle["run_id"], cycle_id, stage, "stage.completed",
                        next(s["label"] for s in STAGES if s["key"] == stage)+" 단계를 완료했습니다.",
                        {"job_id": job_id, "result": result, "external_job_id": external_job_id, "summary": self._result_summary(stage, result),
                         "source_materials": [self._source(db.execute("SELECT * FROM source_materials WHERE id=?", (source_id,)).fetchone())
                                              for source_id in result.get("source_ids", [])] if stage in ["sources", "planning"] else []})
            if final:
                if cycle["brief_id"]:
                    db.execute("UPDATE briefs SET status='completed',updated_at=? WHERE id=? AND run_id=? AND cycle_id=? AND status='producing'",
                               (timestamp(), cycle["brief_id"], cycle["run_id"], cycle_id))
                db.execute("UPDATE production_runs SET completed_count=completed_count+1,current_stage=NULL,updated_at=? WHERE id=?",
                           (timestamp(), cycle["run_id"]))
                self._event(db, cycle["run_id"], cycle_id, stage, "cycle.completed",
                            "피드를 승인 대기 상태로 등록했습니다.",
                            {"content_id": cycle["content_id"], "version": result["version"]})
            else:
                db.execute("UPDATE production_runs SET current_stage=?,updated_at=? WHERE id=?",
                           (STAGES[next_index]["key"], timestamp(), cycle["run_id"]))
            if recovered_video:
                self._resume_resolved_video(db, cycle, recovered_video)
            self._retire_if_terminal(db, cycle["run_id"])
            return {"duplicate": False, "cycle": self._cycle(db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle_id,)).fetchone())}

    def _cycle_failed(self, db, run_id, cycle, stage, error):
        self._specialist_cycle_status(db, cycle["id"], "failed", error)
        if cycle["brief_id"]:
            db.execute("UPDATE briefs SET status='failed',updated_at=? WHERE id=? AND run_id=? AND cycle_id=?",
                       (timestamp(), cycle["brief_id"], run_id, cycle["id"]))
        db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE cycle_id=? AND status IN ('running','paused','pending')",
                   (self._safe_log(str(error)), timestamp(), cycle["id"]))
        db.execute("UPDATE production_cycles SET status='failed',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?",
                   (timestamp(), cycle["id"]))
        db.execute("UPDATE production_runs SET failed_count=failed_count+1,current_stage=NULL,updated_at=? WHERE id=?", (timestamp(), run_id))
        self._event(db, run_id, cycle["id"], stage, "cycle.failed", "이 콘텐츠 순환을 실패로 보존하고 다음 주제를 준비합니다.",
                    {"error": error}, "error")
        recent = db.execute("SELECT status FROM production_cycles WHERE run_id=? ORDER BY number DESC LIMIT 3", (run_id,)).fetchall()
        if len(recent) == 3 and all(r["status"] == "failed" for r in recent):
            db.execute("UPDATE production_runs SET status='blocked',pause_reason='3회 연속 실패: 도구·입력 확인 필요',updated_at=? WHERE id=? AND status IN ('running','scheduled')",
                       (timestamp(), run_id))
            self._event(db, run_id, cycle["id"], stage, "run.circuit_breaker", "세 콘텐츠가 연속 실패해 자동 반복을 멈췄습니다.", level="error")

    def worker_fail(self, cycle_id, lease_token, error, retryable=True, uncertain=False, resolved_video_job_id=None):
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            stage = STAGES[cycle["stage_index"]]["key"]
            job_id = cycle_id+":"+stage
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            error = self._safe_log(str(error))
            resolved_video = self._verified_terminal_video(db, cycle, resolved_video_job_id, "failed") if not uncertain else None
            if cycle["status"] == "uncertain" and not uncertain and resolved_video is None:
                raise self.problem("불확실한 작업은 실제 외부 결과 확인 후 완료하거나 명시적으로 중지해야 합니다.", 409)
            db.execute("UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=?",
                       ("uncertain" if uncertain else "failed", error, timestamp(), job_id))
            self._specialist_cycle_status(db, cycle_id, "uncertain" if uncertain else "failed", error)
            self._event(db, cycle["run_id"], cycle_id, stage, "stage.uncertain" if uncertain else "stage.failed",
                        "단계 실행 결과를 확인할 수 없습니다." if uncertain else "단계 실행이 실패했습니다.",
                        {"error": error, "attempt": job["attempts"], "retryable": retryable}, "error")
            if uncertain:
                db.execute("UPDATE production_cycles SET status='uncertain',updated_at=? WHERE id=?", (timestamp(), cycle_id))
                db.execute("UPDATE production_runs SET status='blocked',pause_reason='외부 작업 결과 확인 필요',updated_at=? WHERE id=? AND status IN ('running','scheduled')",
                           (timestamp(), cycle["run_id"]))
            elif retryable and job["attempts"] < job["max_attempts"]:
                db.execute("UPDATE production_cycles SET status='pending',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?",
                           (timestamp(), cycle_id))
            else:
                self._cycle_failed(db, cycle["run_id"], cycle, stage, error)
            if resolved_video is not None:
                self._resume_resolved_video(db, cycle, resolved_video["id"])
            self._retire_if_terminal(db, cycle["run_id"])
            return self._cycle(db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle_id,)).fetchone())

    def worker_repair(self, cycle_id, lease_token, target_stage, issues):
        if target_stage not in ["storyboard", "copy", "images"]:
            raise self.problem("수정할 콘텐츠 단계를 선택해 주세요.")
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            run = self._refresh(db, db.execute("SELECT * FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone())
            if run["status"] != "running" or cycle["status"] != "running":
                raise self.problem("진행 중인 실행에서만 재제작을 요청할 수 있습니다. 저장된 결과는 유지합니다.", 409)
            if STAGES[cycle["stage_index"]]["key"] != "quality":
                raise self.problem("검수 단계에서만 부분 재생성을 요청할 수 있습니다.", 409)
            quality_assignment = self._specialist_required_assignment(db, cycle)
            self._specialist_change(db, quality_assignment, "completed", "독립 검수에서 수정을 요청했습니다: " + str(self._safe_log(issues)))
            target_index = next(i for i, s in enumerate(STAGES) if s["key"] == target_stage)
            jobs = db.execute("SELECT * FROM jobs WHERE cycle_id=?", (cycle_id,)).fetchall()
            if any(job["attempts"] >= job["max_attempts"] for job in jobs if job["stage"] in
                   [s["key"] for s in STAGES[target_index:cycle["stage_index"]+1]]):
                self._cycle_failed(db, cycle["run_id"], cycle, "quality", "부분 재생성 한도 도달")
                return {"retryable": False}
            output = json.loads(cycle["result_json"])
            for item in STAGES[target_index:]:
                output.pop(item["key"], None)
            db.execute("UPDATE jobs SET status='pending',result_json=NULL,external_job_id=NULL,error=NULL,updated_at=? WHERE cycle_id=? AND stage IN ("+
                       ",".join("?" for _ in STAGES[target_index:])+")",
                       (timestamp(), cycle_id, *[s["key"] for s in STAGES[target_index:]]))
            for job in jobs:
                if job["stage"] not in [s["key"] for s in STAGES[target_index:]]:
                    continue
                inputs = json.loads(job["input_json"])
                inputs["previous_results"] = output
                db.execute("UPDATE jobs SET input_json=? WHERE id=?", (dumps(inputs), job["id"]))
                self._event(db, cycle["run_id"], cycle_id, job["stage"], "stage.invalidated",
                            "검수 수정 요청으로 이전 결과를 이력에 보존하고 새 결과를 기다립니다.",
                            {"target_stage": target_stage, "previous_attempt": job["attempts"],
                             "external_job_id": job["external_job_id"], "issues": issues})
            db.execute("UPDATE production_cycles SET stage_index=?,status='pending',result_json=?,lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?",
                       (target_index, dumps(output), timestamp(), cycle_id))
            db.execute("UPDATE production_runs SET current_stage=?,updated_at=? WHERE id=?", (target_stage, timestamp(), cycle["run_id"]))
            self._event(db, cycle["run_id"], cycle_id, "quality", "quality.repair", "검수에서 발견한 문제 부분을 다시 제작합니다.",
                        {"target_stage": target_stage, "issues": issues}, "warning")
            return {"retryable": True, "target_stage": target_stage}
