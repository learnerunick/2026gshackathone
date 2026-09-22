"""The first runtime command claims work without printing private credentials."""
import json
from pathlib import Path
import unittest
import test_automation as fixtures
from runtime_bootstrap import bootstrap


class RuntimeBootstrapTests(unittest.TestCase):
    setUp = fixtures.AutomationTests.setUp
    tearDown = fixtures.AutomationTests.tearDown

    def test_claim_immediately_saves_private_lease_and_public_input(self):
        run = self.store.start_run({"end_at": None})
        result = bootstrap(self.store, run["id"], "bootstrap-fixture")
        self.assertTrue(result["should_work"])
        self.assertEqual("sources", result["stage"])
        private = Path(result["claim_file"])
        self.assertEqual(0o600, private.stat().st_mode & 0o777)
        claim = json.loads(private.read_text())
        public = Path(result["input_file"]).read_text()
        self.assertNotIn(claim["lease_token"], public)
        self.assertNotIn(claim["lease_token"], json.dumps(result))
        self.assertNotIn(self.store.token, public)
        self.assertEqual(run["id"], json.loads(public)["run"]["id"])
        inspected = self.store.worker_inspect()
        self.assertEqual("sources", inspected["run"]["current_stage"])
        self.assertEqual("bootstrap-fixture", inspected["cycle"]["lease_owner"])
        self.assertEqual(1, inspected["jobs"][0]["attempts"])
        again = bootstrap(self.store, run["id"], "bootstrap-fixture")
        self.assertEqual({"should_work": False, "reason": "in_flight"}, again)
        self.assertEqual(1, len(list(private.parent.glob('*.json'))))

    def test_old_invocation_never_claims_replacement_run(self):
        old = self.store.start_run({"end_at": None})
        self.store.control_run(old["id"], "stop")
        new = self.store.start_run({"end_at": None})
        self.assertEqual({"should_work": False, "reason": "run_changed"}, bootstrap(self.store, old["id"], "fixture"))
        inspected = self.store.worker_inspect()
        self.assertEqual(new["id"], inspected["run"]["id"])
        self.assertIsNone(inspected["cycle"])

    def test_paused_run_has_no_claim_file_and_no_model_call(self):
        run = self.store.start_run({"end_at": None})
        self.store.control_run(run["id"], "pause")
        self.assertEqual({"should_work": False, "reason": "paused"}, bootstrap(self.store, run["id"], "fixture"))
        self.assertFalse((self.store.runtime/'ai-worker/claims').exists())
