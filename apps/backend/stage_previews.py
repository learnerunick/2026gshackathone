"""Media previews bound to saved stage outputs, never caller-supplied paths."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

MEDIA_EXTENSIONS = {".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".mp4": "video"}
MEDIA_FIELDS = {"media", "media_path", "output_path", "image_path", "video_path", "path", "file", "file_path", "filename"}
MEDIA_CONTAINERS = {"cards", "completed_cards", "completed", "outputs", "output", "files", "images", "videos", "artifacts", "assets", "items", "media_files", "result"}


class StagePreviews:
    def _recorded_registration_content(self, document):
        result = document.get("result")
        if document.get("stage") != "register" or not isinstance(result, dict):
            return None
        if result.get("content_id") != document.get("content_id") or type(result.get("version")) is not int:
            return None
        connection = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        try:
            row = connection.execute("SELECT payload FROM revisions WHERE content_id=? AND version=?",
                                     (result["content_id"], result["version"])).fetchone()
            if not row:
                return None
            payload = json.loads(row[0])
            if payload.get("persona_id", self._original_persona()["id"]) != document.get("persona_id"):
                return None
            return self._safe_log({"id": result["content_id"], "version": result["version"], "payload": payload})
        finally:
            connection.close()

    def _recorded_registration_cards(self, document):
        recorded = self._recorded_registration_content(document)
        return recorded["payload"].get("cards", []) if recorded else []

    def _saved_media_candidates(self, value, origin, inherited_alt=""):
        candidates = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    candidates.append({"reference": item, "alt": inherited_alt, "origin": origin})
                else:
                    candidates.extend(self._saved_media_candidates(item, origin, inherited_alt))
        elif isinstance(value, dict):
            alt = next((value[key] for key in ["alt", "scene", "description", "title"] if isinstance(value.get(key), str) and value[key].strip()), inherited_alt)
            for key, item in value.items():
                if key == "calls" and isinstance(item, list):
                    # Native generation checkpoints keep each finished card
                    # on its call receipt before the final media list exists.
                    for call in item:
                        if (isinstance(call, dict) and call.get("status") == "completed"
                                and isinstance(call.get("result_path"), str)):
                            candidates.append({"reference": call["result_path"], "alt": alt,
                                               "origin": origin, "sha256": call.get("sha256")})
                elif key in MEDIA_FIELDS:
                    if isinstance(item, str):
                        candidates.append({"reference": item, "alt": alt, "origin": origin, "sha256": value.get("sha256")})
                    elif isinstance(item, (list, dict)):
                        candidates.extend(self._saved_media_candidates(item, origin, alt))
                elif key in MEDIA_CONTAINERS and isinstance(item, (list, dict)):
                    candidates.extend(self._saved_media_candidates(item, origin, alt))
            # Some checkpoints key their completed card map by card number.
            for key, item in value.items():
                if str(key).isdigit() and isinstance(item, dict):
                    candidates.extend(self._saved_media_candidates(item, origin, alt))
        return candidates

    def _safe_stage_media_path(self, reference):
        if not isinstance(reference, str) or not reference or "\x00" in reference:
            return None
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", reference) or reference.startswith("//"):
            return None
        route = re.fullmatch(r"/media/([a-f0-9]{64}\.(?:png|jpg|jpeg|webp|mp4))", reference)
        if route:
            path = self.media / route.group(1)
        elif re.fullmatch(r"[a-f0-9]{64}\.(?:png|jpg|jpeg|webp|mp4)", reference):
            path = self.media / reference
        else:
            path = self.root / reference
        try:
            path = path.resolve()
            if self.root not in path.parents or path.suffix.lower() not in MEDIA_EXTENSIONS:
                return None
            return path
        except (OSError, RuntimeError, ValueError):
            return None

    def _stage_media_available(self, path, expected_hash=None):
        try:
            if not path.is_file():
                return False
            if expected_hash:
                if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
                    return False
                digest = hashlib.sha256()
                with path.open("rb") as media:
                    for chunk in iter(lambda: media.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected_hash:
                    return False
            return True
        except (OSError, ValueError):
            return False

    def _stage_preview_entries(self, document):
        candidates = []
        # First appearance in checkpoint history fixes an index. New partial
        # outputs append without changing URLs already displayed by the UI.
        for checkpoint in document.get("checkpoints", []):
            if isinstance(checkpoint, dict):
                candidates.extend(self._saved_media_candidates(checkpoint.get("result"), "checkpoint"))
        candidates.extend(self._saved_media_candidates(document.get("result"), "result"))
        registered = self._recorded_registration_cards(document)
        if registered:
            candidates.extend(self._saved_media_candidates(registered, "registered"))
        ordered = {}
        for candidate in candidates:
            path = self._safe_stage_media_path(candidate["reference"])
            if path is None:
                continue
            # Replacing a dict value preserves its original insertion order.
            ordered[str(path)] = (path, candidate)
        entries = []
        for path, candidate in ordered.values():
            expected_hash = candidate.get("sha256")
            if expected_hash is None and path.parent == self.media.resolve() and re.fullmatch(r"[a-f0-9]{64}\.[a-z0-9]+", path.name):
                expected_hash = path.stem
            available = self._stage_media_available(path, expected_hash)
            index = len(entries)
            url = "/api/runs/{run}/stages/{cycle}/{stage}/media/{index}".format(run=document["run_id"], cycle=document["cycle_id"], stage=document["stage"], index=index)
            metadata = {"kind": MEDIA_EXTENSIONS[path.suffix.lower()], "url": url if available else None,
                        "name": path.name, "alt": candidate.get("alt") or path.name, "available": available,
                        "origin": candidate["origin"]}
            entries.append((metadata, path, expected_hash))
        return entries

    def add_stage_previews(self, document):
        document["registered_content"] = self._recorded_registration_content(document)
        document["previews"] = [entry[0] for entry in self._stage_preview_entries(document)]
        snapshots = [event.get("detail", {}).get("source_materials") for event in document.get("events", [])
                     if event.get("event") == "stage.completed" and isinstance(event.get("detail"), dict)
                     and isinstance(event["detail"].get("source_materials"), list)]
        document["source_snapshot"] = snapshots[-1] if snapshots else None
        return document

    def stage_media_file(self, run_id, cycle_id, stage, index):
        if type(index) is not int or index < 0:
            raise self.problem("미디어 항목을 찾을 수 없습니다.", 404)
        document = self.read_stage_result(run_id, cycle_id, stage)
        entries = self._stage_preview_entries(document)
        if index >= len(entries):
            raise self.problem("단계에 기록된 미디어를 찾을 수 없습니다.", 404)
        metadata, path, expected_hash = entries[index]
        # Resolve again on every media request; a changed symlink must not
        # turn an earlier valid stage record into access outside the project.
        safe = self._safe_stage_media_path(str(path))
        if not metadata["available"] or safe != path or not self._stage_media_available(path, expected_hash):
            raise self.problem("저장된 미디어가 없거나 변경되었습니다.", 404)
        return path
