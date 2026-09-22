"""Committed, recoverable production files; no real data or provider requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("boca_artifacts_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem


class ProductionArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        current = datetime.now(timezone.utc)
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["ai_quality_review_enabled"] = True  # Legacy seven-stage policy.
        # Preserve legacy stage fixtures; mandatory research has its own integration tests.
        config.update(specialist_agents_enabled=False, source_research_enabled=False, start_at=(current - timedelta(minutes=1)).isoformat(),
                      generation_end_at=(current + timedelta(hours=2)).isoformat())
        config_path.write_text(json.dumps(config))
        self.store = Store(self.root)
        self.run = self.store.start_run({})
        self.run_dir = self.root / ".runtime/production" / self.run["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def claim(self):
        claim = self.store.worker_next("artifact-fixture-worker")
        self.assertTrue(claim["should_work"], claim)
        return claim

    def event_ids(self, data):
        rows = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
        return [row["id"] for row in rows]

    def test_committed_run_and_stage_outputs_are_immediately_written(self):
        self.assertTrue((self.run_dir / "events.jsonl").is_file())
        self.assertTrue((self.run_dir / "events.log").is_file())
        claim = self.claim()
        result = {"source_ids": [], "notes": "공식 자료를 확인하고 일상 장면으로 연결할 준비"}
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], result)
        stage_path = self.run_dir / "cycles" / claim["cycle"]["id"] / "sources.json"
        stored = json.loads(stage_path.read_text())
        self.assertEqual(result, stored["result"])
        self.assertEqual("completed", stored["status"])
        self.assertEqual(claim["cycle"]["id"], stored["cycle_id"])
        self.assertEqual(self.run["id"], stored["run_id"])
        queried = self.store.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources")
        self.assertEqual(stored["result"], queried["result"])
        described = json.dumps(self.store.describe_artifacts(self.run["id"]), ensure_ascii=False)
        self.assertIn(self.run["id"], described)
        stages = self.store.list_stage_results(self.run["id"])
        self.assertTrue(any(row["cycle_id"] == claim["cycle"]["id"] and row["stage"] == "sources"
                            for row in stages))

    def test_rollback_never_exports_a_ghost_event_even_during_transaction(self):
        baseline = self.store.export_log(self.run["id"], "jsonl")[0]
        with self.assertRaisesRegex(RuntimeError, "rollback fixture"):
            with self.store.db() as db:
                self.store._event(db, self.run["id"], None, "sources", "fixture.rollback",
                                  "ghost-event-that-must-never-be-exported")
                self.store.sync_production_artifacts(self.run["id"])
                self.assertNotIn(b"ghost-event", (self.run_dir / "events.jsonl").read_bytes())
                raise RuntimeError("rollback fixture")
        self.store.sync_production_artifacts(self.run["id"])
        exported = self.store.export_log(self.run["id"], "jsonl")[0]
        self.assertEqual(self.event_ids(baseline), self.event_ids(exported))
        self.assertNotIn(b"ghost-event", exported)

    def test_restart_rebuilds_deleted_files_from_committed_database(self):
        claim = self.claim()
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"source_ids": []})
        before = self.store.export_log(self.run["id"], "jsonl")[0]
        shutil.rmtree(self.run_dir)
        restarted = Store(self.root)
        self.assertTrue((self.run_dir / "events.jsonl").is_file())
        self.assertEqual(self.event_ids(before), self.event_ids((self.run_dir / "events.jsonl").read_bytes()))
        self.assertEqual("completed", restarted.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources")["status"])

    def test_repeated_sync_and_export_do_not_duplicate_events(self):
        claim = self.claim()
        for index in range(3):
            self.store.worker_log(claim["cycle"]["id"], claim["lease_token"],
                                  "fixture.note", "단계 메모 %s" % index, {"index": index})
        first = self.store.export_log(self.run["id"], "jsonl")[0]
        for _ in range(4):
            self.store.sync_production_artifacts(self.run["id"])
            self.store.export_log(self.run["id"], "log")
        final, filename, content_type = self.store.export_log(self.run["id"], "jsonl")
        ids = self.event_ids(final)
        self.assertEqual(self.event_ids(first), ids)
        self.assertEqual(sorted(set(ids)), ids)
        self.assertTrue(filename.endswith(".jsonl"))
        self.assertIn("json", content_type)
        text, log_name, log_type = self.store.export_log(self.run["id"], "log")
        self.assertIn("단계 메모 2", text.decode())
        self.assertTrue(log_name.endswith(".log"))
        self.assertTrue(log_type.startswith("text/"))

    def test_checkpoints_and_external_job_history_remain_after_stage_completion(self):
        claim = self.claim()
        self.store.worker_ping(claim["cycle"]["id"], claim["lease_token"], "external-fixture-first")
        checkpoint = {"checked_count": 1, "note": "checkpoint-first-fixture"}
        self.store.worker_checkpoint(claim["cycle"]["id"], claim["lease_token"], checkpoint)
        pending = self.store.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources")
        self.assertEqual(checkpoint, pending["result"])
        self.store.worker_ping(claim["cycle"]["id"], claim["lease_token"], "external-fixture-second")
        completed = {"source_ids": [], "note": "completed-fixture"}
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], completed)
        saved = self.store.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources")
        self.assertEqual(completed, saved["result"])
        self.assertIn("checkpoint-first-fixture", json.dumps(saved["checkpoints"]))
        self.assertIn("external-fixture-first", saved["external_job_ids"])
        self.assertIn("external-fixture-second", saved["external_job_ids"])
        self.assertEqual("external-fixture-second", saved["external_job_id"])

    def test_raw_persisted_secrets_are_redacted_in_every_public_artifact(self):
        claim = self.claim()
        secret_values = ["fixture-access-private", "fixture-api-private", "fixture-nested-private",
                         "fixture-bearer-private", "sk-fixture-provider-private"]
        unsafe = {"access_token": secret_values[0], "api_key": secret_values[1],
                  "nested": {"password": secret_values[2]},
                  "note": "Authorization: Bearer " + secret_values[3] + " provider=" + secret_values[4],
                  "safe_note": "일반 제작 설명은 보존"}
        # Legacy/provider rows may not have passed through the normal event
        # sanitizer. Exports must still sanitize the committed source rows.
        with self.store.db() as db:
            db.execute("UPDATE jobs SET input_json=?,result_json=? WHERE id=?",
                       (json.dumps(unsafe), json.dumps(unsafe), claim["job"]["id"]))
            db.execute("INSERT INTO production_events (run_id,cycle_id,stage,level,event,message,detail_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                       (self.run["id"], claim["cycle"]["id"], "sources", "info", "stage.checkpoint",
                        unsafe["note"], json.dumps({"result": unsafe}), datetime.now(timezone.utc).isoformat()))
        self.store.sync_production_artifacts(self.run["id"])
        outputs = [self.store.export_log(self.run["id"], "log")[0],
                   self.store.export_log(self.run["id"], "jsonl")[0],
                   json.dumps(self.store.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources"), ensure_ascii=False).encode()]
        outputs.extend(path.read_bytes() for path in self.run_dir.rglob("*") if path.is_file())
        joined = b"\n".join(outputs).decode()
        self.assertIn("일반 제작 설명은 보존", joined)
        for value in secret_values:
            self.assertNotIn(value, joined)
        self.assertNotIn(claim["lease_token"], joined)
        self.assertNotIn(self.store.token, joined)

    def test_concurrent_file_refresh_keeps_json_complete_and_events_unique(self):
        claim = self.claim()
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"source_ids": []})
        another = Store(self.root)
        barrier = threading.Barrier(4)
        def refresh(index):
            barrier.wait()
            store = self.store if index % 2 else another
            for _ in range(6):
                store.sync_production_artifacts(self.run["id"])
                ids = self.event_ids((self.run_dir / "events.jsonl").read_bytes())
                self.assertEqual(sorted(set(ids)), ids)
                saved = json.loads((self.run_dir / "cycles" / claim["cycle"]["id"] / "sources.json").read_text())
                self.assertEqual({"source_ids": []}, saved["result"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(refresh, range(4)))

    def test_archive_lock_does_not_block_constructor_ping_or_completion(self):
        claim = self.claim()
        old = self.store.describe_artifacts(self.run["id"])
        lock_path = self.root / ".runtime/production/.mirror.lock"
        with ThreadPoolExecutor(max_workers=1) as pool:
            with lock_path.open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    def write_while_busy():
                        store = Store(self.root)
                        store.worker_ping(claim["cycle"]["id"], claim["lease_token"])
                        store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"source_ids": []})
                        return store.describe_artifacts(self.run["id"])
                    cached = pool.submit(write_while_busy).result(timeout=2)
                    self.assertTrue(cached["sync_pending"])
                    self.assertEqual(old["last_event_id"], cached["last_event_id"])
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        fresh = self.store.describe_artifacts(self.run["id"])
        self.assertGreater(fresh["last_event_id"], cached["last_event_id"])
        self.assertEqual("completed", self.store.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources")["status"])

    def test_busy_archive_without_cached_manifest_returns_retryable_error(self):
        (self.run_dir / "manifest.json").unlink()
        with (self.root / ".runtime/production/.mirror.lock").open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                with self.assertRaises(Problem) as caught:
                    self.store.describe_artifacts(self.run["id"])
                self.assertEqual(503, caught.exception.status)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        self.assertEqual(self.run["id"], self.store.describe_artifacts(self.run["id"])["run_id"])

    def test_invalid_ids_and_unknown_runs_cannot_read_arbitrary_files(self):
        claim = self.claim()
        outside = self.root / "outside-marker.txt"
        outside.write_text("must-not-be-returned")
        for run_id in ("../outside-marker.txt", str(outside), "run/../../outside-marker.txt"):
            with self.subTest(run_id=run_id), self.assertRaises(Problem):
                self.store.export_log(run_id, "log")
        for cycle_id, stage in (("../../outside-marker.txt", "sources"),
                                (claim["cycle"]["id"], "../../outside-marker.txt"),
                                (claim["cycle"]["id"], "unknown-stage")):
            with self.subTest(cycle_id=cycle_id, stage=stage), self.assertRaises(Problem):
                self.store.read_stage_result(self.run["id"], cycle_id, stage)
        for operation in (lambda: self.store.describe_artifacts("run-does-not-exist"),
                          lambda: self.store.export_log("run-does-not-exist", "jsonl"),
                          lambda: self.store.read_stage_result("run-does-not-exist", claim["cycle"]["id"], "sources")):
            with self.assertRaises(Problem) as caught:
                operation()
            self.assertEqual(404, caught.exception.status)
        with self.assertRaises(Problem):
            self.store.export_log(self.run["id"], "unsupported-format")


if __name__ == "__main__":
    unittest.main()
