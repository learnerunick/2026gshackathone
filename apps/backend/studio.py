"""Local persona library, versioned briefs and studio preferences."""
import json
import hashlib
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from source_research import AFFILIATE_DOMAINS, normalize_affiliate
from instagram_connection import public_status, verify as verify_instagram, ConnectionError as InstagramConnectionError

DISCLOSURE = "AI로 만든 가상 인물의 창작 일상입니다."


def stamp():
    return datetime.now(timezone.utc).isoformat()


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class StudioStore:
    def init_studio(self):
        original = json.loads((self.root / "config/persona.json").read_text())
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS personas (
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL, profile_json TEXT NOT NULL,
                    is_original INTEGER NOT NULL DEFAULT 0, overridden INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS persona_revisions (
                    persona_id TEXT NOT NULL, version INTEGER NOT NULL, profile_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(persona_id,version)
                );
                CREATE TABLE IF NOT EXISTS studio_meta (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS persona_references (
                    persona_id TEXT NOT NULL, version INTEGER NOT NULL, role TEXT NOT NULL,
                    source_path TEXT NOT NULL, media TEXT NOT NULL, sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(persona_id,version,role)
                );
                CREATE TABLE IF NOT EXISTS briefs (
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL, persona_id TEXT NOT NULL,
                    title TEXT NOT NULL, brief TEXT NOT NULL, format TEXT NOT NULL, affiliate TEXT NOT NULL,
                    status TEXT NOT NULL, run_id TEXT, cycle_id TEXT, content_id TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            """)
            db.execute("INSERT OR IGNORE INTO personas VALUES (?,?,?,1,0,?,?)",
                       (original["id"], original["version"], pack(original), stamp(), stamp()))
            db.execute("INSERT OR IGNORE INTO persona_revisions VALUES (?,?,?,?)",
                       (original["id"], original["version"], pack(original), stamp()))
            db.execute("INSERT OR IGNORE INTO studio_meta VALUES ('active_persona_id',?)", (pack(original["id"]),))
            columns = {r["name"] for r in db.execute("PRAGMA table_info(production_cycles)")}
            if "brief_id" not in columns:
                db.execute("ALTER TABLE production_cycles ADD COLUMN brief_id TEXT")

    def _read_connection(self):
        connection = sqlite3.connect(str(self.db_path), timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _original_persona(self):
        return json.loads((self.root / "config/persona.json").read_text())

    def _persona_profile(self, db, persona_id=None):
        if not persona_id:
            selected = db.execute("SELECT value_json FROM studio_meta WHERE key='active_persona_id'").fetchone()
            persona_id = json.loads(selected[0]) if selected else self._original_persona()["id"]
        row = db.execute("SELECT * FROM personas WHERE id=?", (persona_id,)).fetchone()
        if row is None:
            raise self.problem("페르소나를 찾을 수 없습니다.", 404)
        return self._original_persona() if row["is_original"] and not row["overridden"] else json.loads(row["profile_json"])

    def persona(self, persona_id=None, db=None):
        if db is not None:
            return self.with_persona_references(self._persona_profile(db, persona_id), db=db)
        connection = self._read_connection()
        try:
            return self.with_persona_references(self._persona_profile(connection, persona_id), db=connection)
        finally:
            connection.close()

    def persona_revision(self, persona_id, version):
        connection = self._read_connection()
        try:
            current = self._persona_profile(connection, persona_id)
            if current["version"] == version:
                return self.with_persona_references(current, db=connection)
            row = connection.execute("SELECT profile_json FROM persona_revisions WHERE persona_id=? AND version=?",
                                     (persona_id, version)).fetchone()
            if not row:
                raise self.problem("저장된 페르소나 버전을 찾을 수 없습니다.", 409)
            return self.with_persona_references(json.loads(row[0]), db=connection)
        finally:
            connection.close()

    def with_persona_references(self, profile, db=None):
        connection = db or self._read_connection()
        try:
            rows = connection.execute("SELECT * FROM persona_references WHERE persona_id=? AND version=? ORDER BY role",
                                      (profile["id"], profile["version"])).fetchall()
            if not rows:
                return profile
            result = json.loads(pack(profile))
            references = {}
            for row in rows:
                self._verify_media({"media": row["media"], "sha256": row["sha256"]})
                references[row["role"]] = {"path": str(self.media / row["media"]), "media": row["media"],
                                            "sha256": row["sha256"], "url": "/media/" + row["media"]}
            result["references"] = references
            if "mother" in references:
                result["visual_reference"] = references["mother"]["path"]
                result["visual_reference_status"] = "registered"
            if "daughter" in references:
                result.setdefault("family", {}).setdefault("daughter", {})["visual_reference"] = references["daughter"]["path"]
            return result
        finally:
            if db is None:
                connection.close()

    def save_persona_references(self, persona_id, body):
        version = body.get("version")
        if type(version) is not int or version < 1 or not body.get("mother"):
            raise self.problem("페르소나 version과 mother 기준 이미지 경로가 필요합니다.")
        self.persona_revision(persona_id, version)
        candidates = []
        for role in ["mother", "daughter"]:
            reference = body.get(role)
            if reference is None:
                continue
            if not isinstance(reference, str):
                raise self.problem("기준 이미지 경로는 문자열이어야 합니다.")
            path = (self.root / reference).resolve()
            if self.root not in path.parents or not path.is_file() or path.suffix.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
                raise self.problem("프로젝트 안에 실제 저장된 이미지 파일만 기준으로 등록할 수 있습니다.")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            candidates.append((role, str(path), digest + path.suffix.lower(), digest, data))
        with self.db() as db:
            duplicate = True
            for role, path, media, digest, data in candidates:
                existing = db.execute("SELECT * FROM persona_references WHERE persona_id=? AND version=? AND role=?",
                                      (persona_id, version, role)).fetchone()
                if existing:
                    if existing["source_path"] != path or existing["sha256"] != digest:
                        raise self.problem("이 페르소나 버전의 기준 이미지는 이미 고정되어 있습니다. 교체하려면 새 프로필 버전을 저장해 주세요.", 409)
                    self._verify_media({"media": existing["media"], "sha256": existing["sha256"]})
            for role, path, media, digest, data in candidates:
                existing = db.execute("SELECT 1 FROM persona_references WHERE persona_id=? AND version=? AND role=?",
                                      (persona_id, version, role)).fetchone()
                if existing:
                    continue
                duplicate = False
                destination = self.media / media
                if destination.exists():
                    self._verify_media({"media": media, "sha256": digest})
                else:
                    temp = self.media / (media + "." + uuid.uuid4().hex + ".tmp")
                    temp.write_bytes(data)
                    os.replace(temp, destination)
                db.execute("INSERT INTO persona_references VALUES (?,?,?,?,?,?,?)",
                           (persona_id, version, role, path, media, digest, stamp()))
                self._event(db, None, None, "persona", "persona.reference_saved", "페르소나 버전에 기준 이미지를 고정했습니다.",
                            {"persona_id": persona_id, "version": version, "role": role, "media": media, "sha256": digest})
            refs = self.with_persona_references({"id": persona_id, "version": version}, db=db)["references"]
            return {"persona_id": persona_id, "version": version, "references": refs, "duplicate": duplicate}

    def content_persona_id(self, payload):
        if payload.get("persona_id"):
            return payload["persona_id"]
        connection = self._read_connection()
        try:
            row = connection.execute("SELECT r.persona_id FROM production_cycles c JOIN production_runs r ON r.id=c.run_id WHERE c.content_id=?",
                                     (payload.get("id"),)).fetchone()
            return row[0] if row else self._original_persona()["id"]
        finally:
            connection.close()

    def config(self):
        config = json.loads((self.root / "config/overnight.json").read_text())
        config.setdefault("video", {}).setdefault("duration", 20)
        config["video"].setdefault("resolution", "480p")
        connection = self._read_connection()
        try:
            row = connection.execute("SELECT value_json FROM studio_meta WHERE key='settings'").fetchone()
        finally:
            connection.close()
        if row:
            saved = json.loads(row[0])
            instagram = saved.get("instagram", {})
            if "account" in instagram:
                config["instagram"].update(account=instagram["account"], connection="not-connected")
            for key in ["max_attempts_per_job", "max_pending_requests", "default_format", "video_enabled"]:
                if key in saved.get("generation", {}):
                    config[key] = saved["generation"][key]
            config["video"].update(saved.get("generation", {}).get("auto_video", {}))
        config["instagram"].update(public_status(self.root, config["instagram"].get("account")))
        return config

    def verify_instagram_connection(self):
        account = self.config()["instagram"].get("account")
        try:
            result = verify_instagram(self.root, account)
        except InstagramConnectionError as error:
            raise self.problem(str(error), 409) from None
        with self.db() as db:
            self._event(db, None, None, "settings", "instagram.verified",
                        "Instagram 계정과 게시 권한을 확인했습니다. 실제 게시는 실행하지 않았습니다.",
                        {"account": result["account"], "verified_at": result["verified_at"]})
        return result

    def _persona_record(self, db, row):
        profile = self.with_persona_references(self._persona_profile(db, row["id"]), db=db)
        return {"id": row["id"], "version": profile["version"],
                "display_name": profile.get("display_name") or "여의도 워킹맘",
                "bio": profile.get("bio", ""), "profile": profile,
                "portrait_url": "/api/personas/" + row["id"] + "/portrait?v=" + str(profile["version"]) if self._portrait_path(profile) else None,
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def _portrait_path(self, profile):
        reference = profile.get("visual_reference")
        if isinstance(reference, dict):
            reference = reference.get("path")
        if not isinstance(reference, str) or not reference:
            return None
        path = (self.root / reference).resolve()
        if self.root not in path.parents or path.suffix.lower() not in [".png", ".jpg", ".jpeg", ".webp"] or not path.is_file():
            return None
        return path

    def persona_portrait(self, persona_id):
        return self._portrait_path(self.persona(persona_id))

    def _clean_profile(self, profile, persona_id, version):
        if not isinstance(profile, dict):
            raise self.problem("페르소나 profile 객체가 필요합니다.")
        profile = json.loads(pack(profile))
        name = profile.get("display_name")
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise self.problem("페르소나 이름을 80자 이내로 입력해 주세요.")
        if len(pack(profile)) > 30000:
            raise self.problem("페르소나 설정이 너무 깁니다.")
        for key in ["personality", "interests"]:
            value = profile.get(key, [])
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                raise self.problem(key + " 값은 문자열 목록이어야 합니다.")
            profile[key] = value
        for key in ["work", "home", "family", "content"]:
            if not isinstance(profile.get(key, {}), dict):
                raise self.problem(key + " 값은 객체여야 합니다.")
        profile.update(id=persona_id, version=version, display_name=name.strip())
        # Reference bindings belong to a versioned immutable table. A profile
        # edit creates a new version and cannot smuggle a changed image into it.
        profile.pop("references", None)
        profile["visual_reference"] = None
        profile["visual_reference_status"] = "not-created"
        if isinstance(profile.get("family", {}).get("daughter"), dict):
            profile["family"]["daughter"]["visual_reference"] = None
        content = profile.setdefault("content", {})
        content.update(disclosure=DISCLOSURE, story_first=True, public_retailer_mentions=False,
                       internal_source_tracking=True, no_fabricated_purchase_or_usage=True,
                       no_identifiable_real_person_reference=True)
        content.setdefault("format", "variable-length-carousel")
        content.setdefault("card_count", None)
        profile.setdefault("status", "profile-ready-visual-pending")
        profile.setdefault("visual_reference", None)
        return profile

    def create_persona(self, body):
        persona_id = "persona-" + uuid.uuid4().hex[:16]
        profile = self._clean_profile(body.get("profile"), persona_id, 1)
        with self.db() as db:
            db.execute("INSERT INTO personas VALUES (?,?,?,0,1,?,?)", (persona_id, 1, pack(profile), stamp(), stamp()))
            db.execute("INSERT INTO persona_revisions VALUES (?,?,?,?)", (persona_id, 1, pack(profile), stamp()))
            self._event(db, None, None, "persona", "persona.created", "새 페르소나를 생성했습니다.", {"persona_id": persona_id, "display_name": profile["display_name"]})
            return self._persona_record(db, db.execute("SELECT * FROM personas WHERE id=?", (persona_id,)).fetchone())

    def update_persona(self, persona_id, body):
        with self.db() as db:
            old = self._persona_profile(db, persona_id)
            if body.get("base_version") != old["version"]:
                raise self.problem("페르소나가 변경되었습니다. 최신 버전을 다시 확인해 주세요.", 409)
            profile = self._clean_profile(body.get("profile"), persona_id, old["version"] + 1)
            db.execute("INSERT OR IGNORE INTO persona_revisions VALUES (?,?,?,?)", (persona_id, old["version"], pack(old), stamp()))
            db.execute("INSERT INTO persona_revisions VALUES (?,?,?,?)", (persona_id, profile["version"], pack(profile), stamp()))
            db.execute("UPDATE personas SET version=?,profile_json=?,overridden=1,updated_at=? WHERE id=?",
                       (profile["version"], pack(profile), stamp(), persona_id))
            self._event(db, None, None, "persona", "persona.updated", "페르소나의 새 버전을 저장했습니다.", {"persona_id": persona_id, "version": profile["version"]})
            return self._persona_record(db, db.execute("SELECT * FROM personas WHERE id=?", (persona_id,)).fetchone())

    def select_persona(self, persona_id):
        with self.db() as db:
            self._persona_profile(db, persona_id)
            db.execute("INSERT OR REPLACE INTO studio_meta VALUES ('active_persona_id',?)", (pack(persona_id),))
            return {"active_persona_id": persona_id}

    def _brief_fields(self, body, existing=None):
        data = dict(existing or {})
        for key in ["persona_id", "title", "brief", "format", "affiliate"]:
            if key in body:
                data[key] = body[key]
        if not data.get("persona_id"):
            data["persona_id"] = self.persona()["id"]
        if not isinstance(data.get("title"), str) or not data["title"].strip() or len(data["title"]) > 200:
            raise self.problem("기획 제목을 200자 이내로 입력해 주세요.")
        if not isinstance(data.get("brief", ""), str) or len(data.get("brief", "")) > 12000:
            raise self.problem("기획 메모를 12,000자 이내로 입력해 주세요.")
        data.setdefault("brief", "")
        data.setdefault("format", self.config().get("default_format", "carousel"))
        data.setdefault("affiliate", "")
        if data["format"] not in ["carousel", "image", "video"]:
            raise self.problem("콘텐츠 형식을 선택해 주세요.")
        data["affiliate"] = normalize_affiliate(data["affiliate"])
        if data["affiliate"] not in ["", "일상", *AFFILIATE_DOMAINS]:
            raise self.problem("대상 계열사를 선택해 주세요.")
        return data

    def create_brief(self, body):
        data = self._brief_fields(body)
        with self.db() as db:
            self._persona_profile(db, data["persona_id"])
            brief_id = "brief-" + uuid.uuid4().hex[:16]
            db.execute("INSERT INTO briefs VALUES (?,1,?,?,?,?,?,'draft',NULL,NULL,NULL,?,?)",
                       (brief_id, data["persona_id"], data["title"].strip(), data["brief"], data["format"], data["affiliate"], stamp(), stamp()))
            self._event(db, None, None, "planning", "brief.created", "콘텐츠 기획 초안을 저장했습니다.", {"brief_id": brief_id})
            return dict(db.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone())

    def update_brief(self, brief_id, body):
        with self.db() as db:
            old = db.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()
            if old is None:
                raise self.problem("기획 초안을 찾을 수 없습니다.", 404)
            if body.get("base_version") != old["version"]:
                raise self.problem("기획 초안이 변경되었습니다. 최신 버전을 다시 확인해 주세요.", 409)
            if old["status"] not in ["draft", "failed"]:
                raise self.problem("제작 요청한 초안은 수정할 수 없습니다. 새 초안을 만들어 주세요.", 409)
            data = self._brief_fields(body, old)
            self._persona_profile(db, data["persona_id"])
            db.execute("UPDATE briefs SET version=version+1,persona_id=?,title=?,brief=?,format=?,affiliate=?,status='draft',run_id=NULL,cycle_id=NULL,content_id=NULL,updated_at=? WHERE id=?",
                       (data["persona_id"], data["title"].strip(), data["brief"], data["format"], data["affiliate"], stamp(), brief_id))
            self._event(db, None, None, "planning", "brief.updated", "콘텐츠 기획 초안을 수정했습니다.", {"brief_id": brief_id})
            return dict(db.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone())

    def produce_brief(self, brief_id):
        config = self.config()
        with self.db() as db:
            brief = db.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()
            if brief is None:
                raise self.problem("기획 초안을 찾을 수 없습니다.", 404)
            if brief["status"] in ["queued", "producing", "completed"]:
                run = db.execute("SELECT * FROM production_runs WHERE id=?", (brief["run_id"],)).fetchone()
                return {"brief": dict(brief), "run": self._run(run), "duplicate": True}
            if brief["status"] != "draft":
                raise self.problem("실패한 초안은 수정해 새 버전으로 저장한 뒤 요청해 주세요.", 409)
            pending = db.execute("SELECT COUNT(*) FROM briefs WHERE status IN ('queued','producing')").fetchone()[0]
            if pending >= config.get("max_pending_requests", 20):
                raise self.problem("제작 대기 한도에 도달했습니다.", 409)
            persona = self._persona_profile(db, brief["persona_id"])
            start = datetime.now(timezone.utc)
            end = self._time(config["generation_end_at"]) if config.get("generation_end_at") else None
            if end is not None and end <= start:
                end = None
            run = self._start_run_db(db, persona, config, start, end, "queued")
            db.execute("UPDATE briefs SET status='queued',run_id=?,updated_at=? WHERE id=?", (run["id"], stamp(), brief_id))
            self._event(db, run["id"], None, "planning", "brief.queued", "기획 초안을 다음 콘텐츠 제작 순환에 연결했습니다.",
                        {"brief_id": brief_id, "title": brief["title"], "run_status": run["status"]})
            return {"brief": dict(db.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()), "run": self._run(run), "duplicate": False}

    def update_settings(self, body):
        allowed = {"workspace_name", "instagram", "generation"}
        if set(body) - allowed:
            raise self.problem("지원하지 않는 설정입니다.")
        with self.db() as db:
            row = db.execute("SELECT value_json FROM studio_meta WHERE key='settings'").fetchone()
            saved = json.loads(row[0]) if row else {}
            if "workspace_name" in body:
                value = body["workspace_name"]
                if not isinstance(value, str) or not value.strip() or len(value) > 80:
                    raise self.problem("작업 공간 이름을 80자 이내로 입력해 주세요.")
                saved["workspace_name"] = value.strip()
            if "instagram" in body:
                value = body["instagram"]
                if not isinstance(value, dict) or set(value) - {"account"}:
                    raise self.problem("Instagram 계정명만 저장할 수 있습니다. 연결은 별도의 인증이 필요합니다.")
                account = value.get("account")
                account = account.lstrip("@").strip() if isinstance(account, str) else account
                if account and not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", account):
                    raise self.problem("Instagram 계정명 형식을 확인해 주세요.")
                saved["instagram"] = {"account": account or None}
            if "generation" in body:
                value = body["generation"]
                fields = {"max_attempts_per_job", "max_pending_requests", "default_format", "video_enabled", "auto_video"}
                if not isinstance(value, dict) or set(value) - fields:
                    raise self.problem("지원하지 않는 제작 설정입니다.")
                for key, low, high in [("max_attempts_per_job", 1, 3), ("max_pending_requests", 1, 100)]:
                    if key in value and (type(value[key]) is not int or not low <= value[key] <= high):
                        raise self.problem(key + " 설정 범위를 확인해 주세요.")
                if "default_format" in value and value["default_format"] not in ["carousel", "image", "video"]:
                    raise self.problem("기본 콘텐츠 형식을 선택해 주세요.")
                if "video_enabled" in value and not isinstance(value["video_enabled"], bool):
                    raise self.problem("영상 포함 설정 형식을 확인해 주세요.")
                if "auto_video" in value:
                    value = dict(value, auto_video=self.validate_auto_video(value["auto_video"]))
                saved.setdefault("generation", {}).update(value)
            db.execute("INSERT OR REPLACE INTO studio_meta VALUES ('settings',?)", (pack(saved),))
            self._event(db, None, None, "settings", "settings.updated", "작업 공간 설정을 저장했습니다. 계정 인증 상태는 변경하지 않습니다.")
        return self.studio_state()["settings"]

    def studio_state(self):
        config = self.config()
        with self.db() as db:
            row = db.execute("SELECT value_json FROM studio_meta WHERE key='settings'").fetchone()
            saved = json.loads(row[0]) if row else {}
            personas = [self._persona_record(db, r) for r in db.execute("SELECT * FROM personas ORDER BY created_at")]
            active = self._persona_profile(db)["id"]
            briefs = [dict(r) for r in db.execute("SELECT * FROM briefs ORDER BY created_at DESC")]
            settings = {"workspace_name": saved.get("workspace_name", "BOCA Studio"), "instagram": config["instagram"],
                        "generation": {"max_attempts_per_job": config.get("max_attempts_per_job", 2),
                                       "max_pending_requests": config.get("max_pending_requests", 20),
                                       "default_format": config.get("default_format", "carousel"),
                                       "video_enabled": config.get("video_enabled", False),
                                       "auto_video": self.run_video_settings(config)},
                        "provider": config.get("provider"), "paid_api_allowed": False,
                        "approval_required": True}
            return {"personas": personas, "active_persona_id": active, "briefs": briefs, "settings": settings}
