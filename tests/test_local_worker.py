"""Local runner integration without model calls, paid media, or production DB."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))
from server import Store, handler
from local_worker import LocalProductionWorker, worker_state


class LocalWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        config = json.loads((self.root / "config/overnight.json").read_text())
        now = datetime.now(timezone.utc)
        config.update(specialist_agents_enabled=False, source_research_enabled=False,
                      start_at=(now - timedelta(minutes=1)).isoformat(),
                      generation_end_at=(now + timedelta(hours=1)).isoformat())
        (self.root / "config/overnight.json").write_text(json.dumps(config))
        self.store = Store(self.root)
        self.runners = []

    def tearDown(self):
        for runner in self.runners:
            runner.stop.set()
            runner.wake.set()
        for runner in self.runners:
            runner.thread.join(timeout=5)
        self.temp.cleanup()

    def wait_for(self, condition, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return
            time.sleep(.02)
        self.fail("runner did not reach expected state")

    def runner(self, store=None):
        runner = LocalProductionWorker(store or self.store, poll_seconds=.03)
        self.runners.append(runner)
        runner.start()
        return runner

    def fixture_command(self):
        script = self.root / "fake_codex.py"
        script.write_text('''import json,re,sys,time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from server import Store
root=Path(sys.argv[2]); store=Store(root)
prompt=sys.stdin.read()
worker=re.search(r"Worker ID: (.+)",prompt).group(1)
with (root / "launches").open("a") as f: f.write("started\\n")
print(json.dumps({"type":"thread.started","thread_id":"fixture-runtime-id"}),flush=True)
time.sleep(.2)
claim=store.worker_next(worker)
assert claim["should_work"]
store.worker_complete(claim["cycle"]["id"],claim["lease_token"],{"source_ids":[]})
store.control_run(claim["run"]["id"],"pause")
print(json.dumps({"type":"turn.completed"}),flush=True)
''')
        return [sys.executable, str(script), str(ROOT / "apps/backend"), str(self.root)]

    def test_http_start_wakes_real_subprocess_and_records_stage_without_timer(self):
        with patch.object(LocalProductionWorker, "_command", return_value=self.fixture_command()):
            self.store.production_worker = self.runner()
            http = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.store))
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                started = time.monotonic()
                request = Request("http://127.0.0.1:%d/api/runs/start" % http.server_port,
                                  data=b'{"stop_after_posts":1}', method="POST",
                                  headers={"X-BOCA-Token": self.store.token, "Content-Type": "application/json"})
                with urlopen(request) as response:
                    run = json.load(response)
                self.wait_for(lambda: self.store.worker_inspect()["run"]["status"] == "paused")
                self.assertLess(time.monotonic() - started, 5)
                snapshot = self.store.worker_inspect()
                self.assertEqual(run["id"], snapshot["run"]["id"])
                self.assertIn("sources", snapshot["cycle"]["result"])
                self.assertEqual("completed", snapshot["jobs"][0]["status"])
                self.assertEqual(1, len((self.root / "launches").read_text().splitlines()))
                self.assertNotIn("lease_token", worker_state(self.store))
            finally:
                http.shutdown()
                http.server_close()
                thread.join()

    def test_two_servers_launch_only_one_coordinator(self):
        self.store.start_run({"stop_after_posts": 1})
        with patch.object(LocalProductionWorker, "_command", return_value=self.fixture_command()):
            self.runner()
            self.runner(Store(self.root))
            self.wait_for(lambda: self.store.worker_inspect()["run"]["status"] == "paused")
            self.assertEqual(1, len((self.root / "launches").read_text().splitlines()))

    def test_six_stage_runner_launches_next_cycles_while_all_contents_await_approval(self):
        script = self.root / "fake_full_cycle.py"
        script.write_text('''import json,re,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from server import Store,DISCLOSURE
root=Path(sys.argv[2]); store=Store(root)
worker=re.search(r"Worker ID: (.+)",sys.stdin.read()).group(1)
with (root / "launches").open("a") as f: f.write("started\\n")
print(json.dumps({"type":"thread.started","thread_id":"fixture-full-cycle"}),flush=True)
(root / "fixture.png").write_bytes(b"fixture-media")
for stage in ("sources","planning","storyboard","copy","images","register"):
    claim=store.worker_next(worker)
    assert claim["should_work"] and claim["job"]["stage"]==stage
    cycle=claim["cycle"]; token=claim["lease_token"]
    results={"sources":{"source_ids":[]},
        "planning":{"title":"Fixture story", "topic_key":cycle["id"], "source_ids":[]},
        "storyboard":{"cards":[{"scene":"fixture room"}]},
        "copy":{"caption":DISCLOSURE,"hashtags":[]},
        "images":{"media":["fixture.png"]}}
    if stage=="register":
        payload={"id":cycle["content_id"],"title":"Fixture story","topic_key":cycle["id"],
            "persona_id":claim["run"]["persona_id"],"persona_version":claim["run"]["persona_version"],
            "caption":DISCLOSURE,"hashtags":[],"sources":[],"cards":[{"media":"fixture.png","alt":"fixture"}]}
        registered=store.ingest(payload)
        result={"content_id":registered["id"],"version":registered["version"]}
    else: result=results[stage]
    store.worker_complete(cycle["id"],token,result)
print(json.dumps({"type":"turn.completed"}),flush=True)
''')
        self.store.start_run({"stop_after_posts": 3, "end_at": None})
        with patch.object(LocalProductionWorker, "_command", return_value=[sys.executable, str(script), str(ROOT / "apps/backend"), str(self.root)]):
            self.runner()
            self.wait_for(lambda: self.store.worker_inspect()["run"]["status"] == "completed", timeout=15)
            self.assertEqual(3, len((self.root / "launches").read_text().splitlines()))
            contents = self.store.state()["contents"]
            self.assertEqual(3, len(contents))
            self.assertTrue(all(item["status"] == "ready" and item["publication"] is None for item in contents))
            with self.store.db() as db:
                self.assertEqual(18, db.execute("SELECT COUNT(*) FROM jobs WHERE status='completed'").fetchone()[0])
                self.assertEqual(0, db.execute("SELECT COUNT(*) FROM jobs WHERE stage='quality'").fetchone()[0])

    def test_runtime_owns_new_claims_but_does_not_steal_existing_lease(self):
        self.store.start_run()
        claimed = self.store.worker_next("old-heartbeat")
        runner = LocalProductionWorker(self.store)
        runner._status()
        run, cycle = runner._snapshot()
        self.assertFalse(runner._runnable(run, cycle))
        self.assertEqual("managed_locally", self.store.worker_next("old-heartbeat")["reason"])
        self.assertEqual("in_flight", self.store.worker_next(runner.worker_id)["reason"])
        self.assertTrue(self.store.worker_ping(cycle["id"], claimed["lease_token"])["can_continue"])

    def test_missing_cli_blocks_once_instead_of_waiting_forever(self):
        self.store.start_run()
        with patch.object(LocalProductionWorker, "_command", side_effect=RuntimeError("Codex CLI를 찾을 수 없습니다.")) as command:
            self.runner()
            self.wait_for(lambda: self.store.worker_inspect()["run"]["status"] == "blocked")
            time.sleep(.1)
            self.assertEqual(1, command.call_count)
            self.assertIn("CLI", self.store.worker_inspect()["run"]["pause_reason"])

    def test_old_coordinator_cannot_claim_new_run_after_user_restarts(self):
        old = self.store.start_run()
        runner = LocalProductionWorker(self.store)
        runner._status(status="running", run_id=old["id"])
        self.store.control_run(old["id"], "stop")
        new = self.store.start_run()
        self.assertNotEqual(old["id"], new["id"])
        self.assertEqual("run_changed", self.store.worker_next(runner.worker_id)["reason"])
        self.assertIsNone(self.store.worker_inspect()["cycle"])

    def test_scheduled_paused_stopped_and_absent_runs_do_not_launch(self):
        runner = LocalProductionWorker(self.store)
        self.assertFalse(runner._runnable(None, None))
        for status in ("scheduled", "paused", "stopped", "blocked", "completed"):
            self.assertFalse(runner._runnable({"status": status}, None))

    def test_process_death_preserves_uncertain_generation(self):
        run = self.store.start_run()
        runner = LocalProductionWorker(self.store)
        claimed = self.store.worker_next(runner.worker_id)
        runner._finished(run["id"], 1, "fixture interrupted")
        result = self.store.worker_inspect()
        self.assertEqual("blocked", result["run"]["status"])
        self.assertEqual("uncertain", result["cycle"]["status"])
        self.assertEqual(claimed["lease_token"], result["cycle"]["lease_token"])

    def test_process_death_while_paused_records_uncertainty_without_resuming(self):
        run = self.store.start_run()
        runner = LocalProductionWorker(self.store)
        self.store.worker_next(runner.worker_id)
        self.store.control_run(run["id"], "pause")
        runner._finished(run["id"], 0, None)
        result = self.store.worker_inspect()
        self.assertEqual("paused", result["run"]["status"])
        self.assertEqual("uncertain", result["cycle"]["status"])

    def test_stop_terminates_live_coordinator_and_its_tool_process(self):
        script = self.root / "slow_fixture.py"
        child = self.root / "tool_fixture.py"
        child.write_text('''import signal,sys,time
from pathlib import Path
root=Path(sys.argv[1])
def stopped(*args):
    (root/"tool-stopped").touch()
    sys.exit(0)
signal.signal(signal.SIGTERM,stopped)
(root/"tool-ready").touch()
while True:time.sleep(.02)
''')
        script.write_text('''import re,sys,time,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from server import Store
root=Path(sys.argv[2]);store=Store(root)
worker=re.search(r"Worker ID: (.+)",sys.stdin.read()).group(1)
claim=store.worker_next(worker)
assert claim["should_work"]
subprocess.Popen([sys.executable,str(root/"tool_fixture.py"),str(root)])
while True:time.sleep(.02)
''')
        processes = []
        def factory(*args, **kwargs):
            process = subprocess.Popen(*args, **kwargs)
            processes.append(process)
            return process
        run = self.store.start_run({"end_at": None})
        runner = LocalProductionWorker(self.store, poll_seconds=.03, process_factory=factory)
        self.runners.append(runner)
        with patch.object(runner, "_command", return_value=[sys.executable, str(script), str(ROOT / "apps/backend"), str(self.root)]):
            runner.start()
            try:
                self.wait_for(lambda: (self.root / "tool-ready").exists())
                self.store.control_run(run["id"], "stop")
                self.wait_for(lambda: processes[0].poll() is not None and (self.root / "tool-stopped").exists())
                self.wait_for(lambda: self.store.worker_inspect()["cycle"]["status"] == "uncertain")
                self.assertEqual("stopped", self.store.worker_inspect()["run"]["status"])
                self.assertEqual(1, len(processes))
            finally:
                for process in processes:
                    if process.poll() is None:
                        runner._terminate_process(process)

    def test_finished_process_reconciles_old_run_without_touching_new_run(self):
        old = self.store.start_run()
        runner = LocalProductionWorker(self.store)
        claimed = self.store.worker_next(runner.worker_id)
        self.store.control_run(old["id"], "stop")
        new = self.store.start_run()
        runner._finished(old["id"], -15, None)
        with self.store.db() as db:
            cycle = db.execute("SELECT status FROM production_cycles WHERE id=?", (claimed["cycle"]["id"],)).fetchone()
        self.assertEqual("uncertain", cycle[0])
        self.assertEqual(new["id"], self.store.automation_state()["run"]["id"])
        self.assertEqual("running", self.store.automation_state()["run"]["status"])


if __name__ == "__main__":
    unittest.main()
