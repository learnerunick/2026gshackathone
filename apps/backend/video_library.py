"""Read-only historical video library and job-bound local MP4 delivery."""
import hashlib
import json
import re
import sqlite3


class VideoLibrary:
    def _video_library_connection(self):
        connection = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        return connection

    def _library_json(self, raw):
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}

    def _library_digest(self, path):
        stat = path.stat()
        signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        cache = getattr(self, "_video_library_hash_cache", None)
        if cache is None:
            self._video_library_hash_cache = cache = {}
        cached = cache.get(str(path))
        if cached and cached[0] == signature:
            return cached[1]
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
        after_signature = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if signature != after_signature:
            return None
        value = digest.hexdigest()
        cache[str(path)] = (signature, value)
        return value

    def _library_media(self, reference, expected_hash=None, cache=None):
        cache = cache if cache is not None else {}
        key = (reference if isinstance(reference, str) else None, type(expected_hash).__name__, repr(expected_hash))
        if key in cache:
            return cache[key]
        path = self._safe_stage_media_path(reference)
        if path is None or path.suffix.lower() != ".mp4":
            return {"path": None, "available": False, "identity": None, "sha256": None}
        if expected_hash is None and re.fullmatch(r"[a-f0-9]{64}\.mp4", path.name):
            expected_hash = path.stem
        valid_hash = isinstance(expected_hash, str) and re.fullmatch(r"[a-f0-9]{64}", expected_hash)
        identity = "sha256:" + expected_hash if valid_hash else "path:" + str(path)
        available, actual_hash = False, None
        try:
            if path.is_file():
                actual_hash = self._library_digest(path)
                available = bool(actual_hash) and (expected_hash is None or bool(valid_hash and actual_hash == expected_hash))
                if available:
                    identity = "sha256:" + actual_hash
        except (OSError, ValueError):
            pass
        value = {"path": path, "available": available, "identity": identity, "sha256": expected_hash or actual_hash}
        cache[key] = value
        return value

    def _video_cards(self, payload):
        return [(index, card) for index, card in enumerate(payload.get("cards", []))
                if isinstance(card, dict) and isinstance(card.get("media"), str) and card["media"].lower().endswith(".mp4")]

    def _job_registered_video(self, db, snapshot, result):
        content_id, version = result.get("content_id"), result.get("version")
        context = snapshot.get("production")
        if not content_id and isinstance(context, dict):
            cycle = db.execute("SELECT * FROM production_cycles WHERE id=? AND run_id=?",
                               (context.get("cycle_id"), context.get("run_id"))).fetchone()
            if cycle and cycle["content_id"] == context.get("content_id"):
                registration = self._library_json(cycle["result_json"]).get("register", {})
                content_id, version = registration.get("content_id"), registration.get("version")
        if not isinstance(content_id, str) or type(version) is not int:
            return None
        row = db.execute("""SELECT r.payload,c.status AS content_status,c.current_version,c.updated_at AS content_updated_at
                            FROM revisions r JOIN contents c ON c.id=r.content_id
                            WHERE r.content_id=? AND r.version=?""", (content_id, version)).fetchone()
        if not row:
            return None
        payload = self._library_json(row["payload"])
        owner = payload.get("persona_id", self._original_persona()["id"])
        if owner != snapshot.get("persona_id") or payload.get("persona_version") != snapshot.get("persona_version"):
            return None
        cards = self._video_cards(payload)
        if not cards:
            return None
        index, card = cards[0]
        return {"content_id": content_id, "version": version, "payload": payload, "index": index, "card": card,
                "content_status": row["content_status"], "current_version": row["current_version"], "updated_at": row["content_updated_at"]}

    def _library_persona_names(self, db):
        names = {}
        for row in db.execute("SELECT persona_id,version,profile_json FROM persona_revisions"):
            profile = self._library_json(row["profile_json"])
            if profile.get("display_name"):
                names[(row["persona_id"], row["version"])] = profile["display_name"]
        for row in db.execute("SELECT id,profile_json FROM personas"):
            profile = self._library_json(row["profile_json"])
            names[row["id"]] = profile.get("display_name") or "이름 미정 페르소나"
        return names

    def _library_job_entry(self, db, row, names, cache):
        snapshot, result = self._library_json(row["input_json"]), self._library_json(row["result_json"])
        registered = self._job_registered_video(db, snapshot, result)
        content = registered["payload"] if registered else snapshot
        reference = registered["card"]["media"] if registered else result.get("media_path")
        expected_hash = registered["card"].get("sha256") if registered else result.get("sha256")
        media = self._library_media(reference, expected_hash, cache)
        persona_id, persona_version = snapshot.get("persona_id"), snapshot.get("persona_version")
        item = {"id": row["id"], "job_id": row["id"], "title": content.get("title") or snapshot.get("title") or "제목 없는 영상",
                "status": row["status"], "persona_id": persona_id, "persona_version": persona_version,
                "persona_name": names.get((persona_id, persona_version), names.get(persona_id, snapshot.get("persona_description") or persona_id)),
                "created_at": row["created_at"], "updated_at": max(row["updated_at"], registered["updated_at"] if registered else row["updated_at"]),
                "media_url": "/api/video/jobs/" + row["id"] + "/media" if media["available"] else None,
                "media_available": media["available"], "media_sha256": media["sha256"] if media["available"] else None,
                "content_id": registered["content_id"] if registered else None,
                "content_version": registered["version"] if registered else None,
                "content_status": registered["content_status"] if registered else None,
                "current_content_version": registered["current_version"] if registered else None,
                "caption": content.get("caption", ""), "hashtags": content.get("hashtags", []),
                "storyboard": content.get("storyboard", snapshot.get("storyboard", "")),
                "error": row["error"], "external_id": row["external_id"],
                "poll_errors": row["poll_errors"], "next_retry_at": row["next_retry_at"],
                "sync_pending": bool(row["sync_pending"]), "sync_error": row["sync_error"], "sync_errors": row["sync_errors"],
                "duration_requested": snapshot.get("duration"), "resolution": snapshot.get("resolution"),
                "source": "automatic" if isinstance(snapshot.get("production"), dict) else "manual",
                "estimated_cost": row["estimated_cost"], "metrics": result.get("metrics", {})}
        return self._safe_log(item), media, registered

    def video_library(self):
        db = self._video_library_connection()
        try:
            names, cache = self._library_persona_names(db), {}
            items, covered_assets, covered_revisions = [], set(), set()
            for row in db.execute("SELECT * FROM video_jobs ORDER BY created_at DESC,id"):
                item, media, registered = self._library_job_entry(db, row, names, cache)
                items.append(item)
                if media["identity"]:
                    covered_assets.add(media["identity"])
                if registered:
                    covered_revisions.add((registered["content_id"], registered["version"], registered["index"]))
            for row in db.execute("""SELECT r.content_id,r.version,r.payload,r.created_at,c.status AS content_status,
                                     c.current_version,c.updated_at AS content_updated_at
                                     FROM revisions r JOIN contents c ON c.id=r.content_id
                                     ORDER BY r.created_at DESC,r.version DESC,r.content_id"""):
                payload = self._library_json(row["payload"])
                for index, card in self._video_cards(payload):
                    revision = (row["content_id"], row["version"], index)
                    media = self._library_media(card["media"], card.get("sha256"), cache)
                    if revision in covered_revisions or (media["identity"] and media["identity"] in covered_assets):
                        continue
                    if media["identity"]:
                        covered_assets.add(media["identity"])
                    persona_id = payload.get("persona_id", self._original_persona()["id"])
                    persona_version = payload.get("persona_version")
                    identity = media["identity"] or ":".join(map(str, revision))
                    identifier = "imported-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
                    items.append(self._safe_log({"id": identifier, "job_id": None, "title": payload.get("title") or "가져온 영상",
                        "status": "completed", "persona_id": persona_id, "persona_version": persona_version,
                        "persona_name": names.get((persona_id, persona_version), names.get(persona_id, persona_id)),
                        "created_at": row["created_at"], "updated_at": max(row["created_at"], row["content_updated_at"]),
                        "media_url": "/api/video-library/imported/{}/{}/{}/media".format(*revision) if media["available"] else None,
                        "media_available": media["available"], "media_sha256": media["sha256"] if media["available"] else None,
                        "content_id": row["content_id"], "content_version": row["version"],
                        "content_status": row["content_status"], "current_content_version": row["current_version"],
                        "caption": payload.get("caption", ""), "hashtags": payload.get("hashtags", []), "storyboard": payload.get("storyboard", ""),
                        "error": None, "external_id": None, "duration_requested": payload.get("duration"),
                        "resolution": payload.get("resolution"), "source": "imported", "estimated_cost": None, "metrics": {}}))
            items.sort(key=lambda item: (item["updated_at"], item["created_at"], item["id"]), reverse=True)
            return {"items": items, "total": len(items), "updated_at": max((item["updated_at"] for item in items), default=None)}
        finally:
            db.close()

    def _verified_library_file(self, media):
        path = media["path"]
        safe = self._safe_stage_media_path(str(path)) if path else None
        if not media["available"] or safe != path or not self._stage_media_available(path, media["sha256"]):
            raise self.problem("저장된 영상이 없거나 변경되었습니다.", 404)
        return path

    def video_job_media_file(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", job_id):
            raise self.problem("영상 작업을 찾을 수 없습니다.", 404)
        db = self._video_library_connection()
        try:
            row = db.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise self.problem("영상 작업을 찾을 수 없습니다.", 404)
            _, media, _ = self._library_job_entry(db, row, {}, {})
            return self._verified_library_file(media)
        finally:
            db.close()

    def imported_video_media_file(self, content_id, version, index):
        if not isinstance(content_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", content_id) or type(version) is not int or version < 1 or type(index) is not int or index < 0:
            raise self.problem("저장된 영상 버전을 찾을 수 없습니다.", 404)
        db = self._video_library_connection()
        try:
            row = db.execute("SELECT payload FROM revisions WHERE content_id=? AND version=?", (content_id, version)).fetchone()
            if not row:
                raise self.problem("저장된 영상 버전을 찾을 수 없습니다.", 404)
            cards = dict(self._video_cards(self._library_json(row["payload"])))
            if index not in cards:
                raise self.problem("저장된 영상 항목을 찾을 수 없습니다.", 404)
            card = cards[index]
            return self._verified_library_file(self._library_media(card["media"], card.get("sha256")))
        finally:
            db.close()
