"""Rebuildable, sanitized production files derived only from committed SQLite."""
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timedelta, timezone
import tempfile
from stage_previews import StagePreviews

STAGE_LABELS = {
    "sources": "GS 소재 확인", "planning": "일상 주제 기획", "storyboard": "스토리보드",
    "copy": "문안·해시태그", "images": "이미지·미디어 생성", "quality": "일관성·정보 검수", "register": "피드 등록",
}
PRIVATE_KEYS = ("secret", "password", "authorization", "api_key", "apikey", "access_token", "refresh_token",
                "lease_token", "completed_token", "auth_token", "cookie", "credential", "chain_of_thought", "reasoning", "internal_thought", "thought_process")


def sanitize(value):
    if isinstance(value, dict):
        return {str(key): ("[redacted]" if str(key).lower() == "token" or any(part in str(key).lower() for part in PRIVATE_KEYS)
                          else sanitize(entry)) for key, entry in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(entry) for entry in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[redacted]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", value)
        value = re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[=:]\s*)[^\s&,;]+", r"\1[redacted]", value)
        return value
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class ProductionArtifacts(StagePreviews):
    def _artifact_id(self, value, kind):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
            raise self.problem(kind + " 경로가 올바르지 않습니다.", 404)
        return value

    def _artifact_base(self):
        base = (self.runtime / "production").resolve()
        if self.root not in base.parents:
            raise self.problem("제작 로그 저장 경로가 올바르지 않습니다.", 409)
        return base

    def _artifact_path(self, *parts):
        base = self._artifact_base()
        path = base.joinpath(*parts).resolve()
        if base not in path.parents:
            raise self.problem("제작 로그 파일 경로가 올바르지 않습니다.", 404)
        return path

    def _atomic_artifact(self, path, data):
        if path.is_file() and path.read_bytes() == data:
            return
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".writing-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            directory = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _artifact_snapshot(self, run_id=None):
        connection = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"production_runs", "production_cycles", "production_events", "jobs"}.issubset(tables):
                return []
            if run_id:
                runs = connection.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchall()
                if not runs:
                    raise self.problem("제작 실행을 찾을 수 없습니다.", 404)
            else:
                runs = connection.execute("SELECT * FROM production_runs ORDER BY created_at").fetchall()
            snapshots = []
            for run in runs:
                events = []
                for event in connection.execute("SELECT * FROM production_events WHERE run_id=? ORDER BY id", (run["id"],)):
                    event = dict(event)
                    event["detail"] = json.loads(event.pop("detail_json"))
                    if not isinstance(event["detail"], dict):
                        event["detail"] = {"value": event["detail"]}
                    events.append(self._safe_log(event))
                cycles = [dict(row) for row in connection.execute("SELECT * FROM production_cycles WHERE run_id=? ORDER BY number", (run["id"],))]
                jobs = [dict(row) for row in connection.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY updated_at,id", (run["id"],))]
                snapshots.append({"run": dict(run), "events": events, "cycles": cycles, "jobs": jobs})
            return snapshots
        finally:
            connection.close()

    def _human_event(self, event):
        try:
            when = datetime.fromisoformat(event["created_at"]).astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
        except (ValueError, TypeError):
            when = event["created_at"]
        step = STAGE_LABELS.get(event.get("stage"), event.get("stage") or "실행")
        line = "[{when}] #{id} {level} · {step} · {message}".format(when=when, id=event["id"], level=event["level"].upper(), step=step, message=event["message"])
        line += "\n  이벤트: " + event["event"]
        if event.get("cycle_id"):
            line += "\n  제작 순환: " + event["cycle_id"]
        if event.get("detail"):
            line += "\n  기록: " + encode(event["detail"])
        return line + "\n"

    def _stage_document(self, run, cycle, job, events):
        stage = job["stage"]
        history = [event for event in events if event.get("cycle_id") == cycle["id"] and event.get("stage") == stage]
        outputs = json.loads(cycle["result_json"])
        latest_result = json.loads(job["result_json"]) if job.get("result_json") else None
        checkpoints = [{"event_id": event["id"], "created_at": event["created_at"], **event["detail"]}
                       for event in history if event["event"] == "stage.checkpoint"]
        invalidated_at = max((event["id"] for event in history if event["event"] == "stage.invalidated"), default=0)
        current_checkpoints = [checkpoint for checkpoint in checkpoints if checkpoint["event_id"] > invalidated_at]
        ids = []
        for candidate in [event["detail"].get("external_job_id") for event in history] + [job.get("external_job_id")]:
            if candidate and candidate not in ids:
                ids.append(candidate)
        final_events = [event for event in history if event["id"] >= invalidated_at and event["event"] in
                        ["stage.completed", "stage.failed", "stage.uncertain", "stage.checkpoint", "stage.invalidated", "stage.skipped"]]
        summary = next((event["detail"].get("summary") for event in reversed(final_events) if event["detail"].get("summary")), None)
        document = {"schema_version": 1, "run_id": run["id"], "cycle_id": cycle["id"], "content_id": cycle["content_id"],
                    "persona_id": run["persona_id"], "persona_version": run["persona_version"], "brief_id": cycle.get("brief_id"),
                    "stage": stage, "stage_label": STAGE_LABELS[stage], "status": job["status"], "cycle_status": cycle["status"],
                    "attempts": job["attempts"], "max_attempts": job["max_attempts"],
                    "input": json.loads(job["input_json"]), "result": outputs.get(stage, latest_result),
                    "checkpoint": current_checkpoints[-1] if current_checkpoints else None, "checkpoints": checkpoints,
                    "external_job_id": job.get("external_job_id"), "external_job_ids": ids, "error": job.get("error"),
                    "summary": summary or (final_events[-1]["message"] if final_events else "단계의 실제 결과를 기다리고 있습니다."),
                    "events": history, "updated_at": job["updated_at"]}
        return self.add_stage_previews(self._safe_log(document))

    def sync_production_artifacts(self, run_id=None):
        """Call after commit; atomic replacement makes crash recovery idempotent."""
        if run_id is not None:
            self._artifact_id(run_id, "실행")
        base = self._artifact_base()
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self._artifact_path(".mirror.lock")
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            snapshots = self._artifact_snapshot(run_id)
            manifests = []
            for snapshot in snapshots:
                run, events = snapshot["run"], snapshot["events"]
                current_id = self._artifact_id(run["id"], "실행")
                root = self._artifact_path(current_id)
                jsonl = "".join(encode(event) + "\n" for event in events).encode()
                human = ("BOCA 콘텐츠 제작 실행 로그\n실행: " + current_id + "\n기록은 커밋된 실제 작업 이벤트입니다.\n\n" + "\n".join(self._human_event(event) for event in events)).encode()
                self._atomic_artifact(self._artifact_path(current_id, "events.jsonl"), jsonl)
                self._atomic_artifact(self._artifact_path(current_id, "events.log"), human)
                cycles = {cycle["id"]: cycle for cycle in snapshot["cycles"]}
                stages = []
                for job in snapshot["jobs"]:
                    if job["stage"] not in STAGE_LABELS or job.get("cycle_id") not in cycles:
                        continue
                    cycle = cycles[job["cycle_id"]]
                    self._artifact_id(cycle["id"], "제작 순환")
                    document = self._stage_document(run, cycle, job, events)
                    path = self._artifact_path(current_id, "cycles", cycle["id"], job["stage"] + ".json")
                    data = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
                    self._atomic_artifact(path, data)
                    stages.append({"cycle_id": cycle["id"], "cycle_number": cycle["number"], "stage": job["stage"],
                                   "stage_label": STAGE_LABELS[job["stage"]], "path": str(path), "bytes": len(data),
                                   "status": job["status"], "attempts": job["attempts"], "external_job_id": self._safe_log(job.get("external_job_id")),
                                   "summary": document["summary"], "updated_at": job["updated_at"],
                                   "url": "/api/runs/" + current_id + "/stages/" + cycle["id"] + "/" + job["stage"]})
                stages.sort(key=lambda entry: (entry["cycle_number"], list(STAGE_LABELS).index(entry["stage"])))
                manifest = {"schema_version": 1, "run_id": current_id, "root": str(root),
                            "event_count": len(events), "last_event_id": events[-1]["id"] if events else None,
                            "events": [{"format": extension, "path": str(self._artifact_path(current_id, "events." + extension)),
                                        "bytes": len(jsonl if extension == "jsonl" else human),
                                        "url": "/api/runs/" + current_id + "/logs?format=" + extension} for extension in ["log", "jsonl"]],
                            "stages": stages}
                self._atomic_artifact(self._artifact_path(current_id, "manifest.json"), json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")
                manifests.append(manifest)
            return manifests

    def describe_artifacts(self, run_id):
        manifests = self.sync_production_artifacts(run_id)
        if not manifests:
            raise self.problem("제작 실행을 찾을 수 없습니다.", 404)
        manifest = manifests[0]
        manifest["synced_at"] = datetime.fromtimestamp(self._artifact_path(run_id, "manifest.json").stat().st_mtime, timezone.utc).isoformat()
        return manifest

    def export_log(self, run_id, format="log"):
        if format not in ["log", "jsonl"]:
            raise self.problem("로그 형식은 log 또는 jsonl이어야 합니다.")
        self.describe_artifacts(run_id)
        filename = run_id + "-events." + format
        data = self._artifact_path(run_id, "events." + format).read_bytes()
        return data, filename, "application/x-ndjson; charset=utf-8" if format == "jsonl" else "text/plain; charset=utf-8"

    def list_stage_results(self, run_id):
        return self.describe_artifacts(run_id)["stages"]

    def read_stage_result(self, run_id, cycle_id, stage):
        self._artifact_id(run_id, "실행")
        self._artifact_id(cycle_id, "제작 순환")
        if stage not in STAGE_LABELS:
            raise self.problem("제작 단계를 찾을 수 없습니다.", 404)
        manifest = self.describe_artifacts(run_id)
        if not any(entry["cycle_id"] == cycle_id and entry["stage"] == stage for entry in manifest["stages"]):
            raise self.problem("실행에 속한 단계 결과를 찾을 수 없습니다.", 404)
        return self.add_stage_previews(json.loads(self._artifact_path(run_id, "cycles", cycle_id, stage + ".json").read_text()))
