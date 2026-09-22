"""Optional deadlines preserve live work and expose results at stage completion."""
from datetime import timedelta
import json
import sqlite3
import unittest

import test_automation as fixtures
import test_source_research as sources
import test_specialists as specialists


class ProductionDeadlineTests(unittest.TestCase):
    setUp = fixtures.AutomationTests.setUp
    tearDown = fixtures.AutomationTests.tearDown
    claim = fixtures.AutomationTests.claim
    complete = fixtures.AutomationTests.complete
    result_for = fixtures.AutomationTests.result_for
    payload = fixtures.AutomationTests.payload
    finish_cycle = fixtures.AutomationTests.finish_cycle
    at_time = fixtures.AutomationTests.at_time

    def test_no_deadline_survives_former_deadline_and_target_still_stops_run(self):
        run = self.store.start_run({"end_at": None, "stop_after_posts": 1})
        self.assertIsNone(run["end_at"])
        self.assertIsNone(run["settings"]["generation_end_at"])
        with self.at_time(self.reference_time + timedelta(hours=13)):
            self.assertTrue(self.store.worker_next("fixture")["should_work"])
        # Preserve lease and complete all stages without waiting for an end time.
        inspected = self.store.worker_inspect()
        self.complete({"cycle": inspected["cycle"], "job": inspected["jobs"][0],
                       "lease_token": inspected["cycle"]["lease_token"]})
        for stage in fixtures.STAGES[1:]:
            self.complete(self.claim(stage))
        saved = self.store.automation_state()["run"]
        self.assertEqual(("completed", 1), (saved["status"], saved["completed_count"]))
        self.assertEqual("ready", self.store.state()["contents"][0]["status"])

    def test_default_null_and_queued_brief_have_no_implicit_eight_hour_limit(self):
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["generation_end_at"] = None
        config_path.write_text(json.dumps(config))
        run = self.store.start_run({})
        self.assertIsNone(run["end_at"])
        self.store.control_run(run["id"], "stop")
        brief = self.store.create_brief({"persona_id": self.store.persona()["id"], "title": "fixture", "brief": "fixture story", "format": "carousel", "affiliate": "GS SHOP"})
        queued = self.store.produce_brief(brief["id"])
        self.assertIsNone(queued["run"]["end_at"])

    def test_clear_live_deadline_preserves_claim_and_immediate_stage_handoff(self):
        run = self.store.start_run({"stop_after_posts": 2})
        claim = self.claim("sources")
        before = self.store.worker_inspect()
        changed = self.store.update_run_deadline(run["id"], {"end_at": None})
        after = self.store.worker_inspect()
        self.assertEqual(before["cycle"], after["cycle"])
        self.assertEqual(before["jobs"], after["jobs"])
        self.assertEqual(2, changed["settings"]["stop_after_posts"])
        self.assertIsNone(changed["end_at"])
        self.store.update_run_deadline(run["id"], {"end_at": None})
        self.assertEqual(1, sum(event["event"] == "run.deadline_updated" for event in self.store.logs(run_id=run["id"])))
        self.assertTrue(self.store.worker_ping(claim["cycle"]["id"], claim["lease_token"])["can_continue"])
        self.complete(claim)
        traces = self.store.describe_artifacts(run["id"])["stages"]
        self.assertEqual("completed", next(t for t in traces if t["stage"] == "sources")["status"])
        self.assertEqual("planning", self.claim()["job"]["stage"])

    def test_invalid_deadlines_and_terminal_runs_are_not_restarted(self):
        for value in ("", False, 0, [], {}, self.reference_time.isoformat()):
            with self.subTest(value=value), self.assertRaises(fixtures.Problem):
                self.store.start_run({"end_at": value})
        run = self.store.start_run({"end_at": None})
        with self.assertRaises(fixtures.Problem):
            self.store.update_run_deadline(run["id"], {})
        self.store.control_run(run["id"], "stop")
        with self.assertRaises(fixtures.Problem):
            self.store.update_run_deadline(run["id"], {"end_at": None})
        self.assertEqual("stopped", self.store.automation_state()["run"]["status"])

    def test_legacy_database_migration_keeps_run_lease_jobs_and_unique_index(self):
        run = self.store.start_run({})
        self.claim("sources")
        before = self.store.worker_inspect()
        with self.store.db() as db:
            schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='production_runs'").fetchone()[0]
            schema = schema.replace('production_runs', 'legacy_runs', 1).replace('end_at TEXT,', 'end_at TEXT NOT NULL,')
            db.execute(schema)
            db.execute('INSERT INTO legacy_runs SELECT * FROM production_runs')
            db.execute('DROP TABLE production_runs')
            db.execute('ALTER TABLE legacy_runs RENAME TO production_runs')
            db.execute("CREATE UNIQUE INDEX one_active_persona_run ON production_runs(persona_id) WHERE status IN ('scheduled','running','paused','blocked')")
        self.store = fixtures.Store(self.root)
        after = self.store.worker_inspect()
        self.assertEqual(before["cycle"], after["cycle"])
        self.assertEqual(before["jobs"], after["jobs"])
        self.assertEqual(before["run"], after["run"])
        self.store.update_run_deadline(run["id"], {"end_at": None})
        with self.store.db() as db:
            columns = {r['name']: r for r in db.execute('PRAGMA table_info(production_runs)')}
            self.assertEqual(0, columns['end_at']['notnull'])
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='one_active_persona_run'").fetchone())
        self.store = fixtures.Store(self.root)
        self.assertIsNone(self.store.automation_state()["run"]["end_at"])


class SourceDeadlineTests(unittest.TestCase):
    setUp = sources.SourceResearchTests.setUp
    tearDown = sources.SourceResearchTests.tearDown
    batch = sources.SourceResearchTests.batch
    material = sources.SourceResearchTests.material

    def test_source_research_accepts_no_deadline(self):
        self.store.start_run({"end_at": None})
        claim = self.store.worker_next("fixture")
        receipt = self.store.worker_sources(claim["cycle"]["id"], claim["lease_token"], self.batch())
        self.assertEqual(1, len(receipt["source_ids"]))


class SpecialistDeadlineTests(unittest.TestCase):
    setUp = specialists.SpecialistTests.setUp
    tearDown = specialists.SpecialistTests.tearDown

    def test_specialist_assignment_accepts_no_deadline(self):
        self.store.start_run({"end_at": None})
        claim = self.store.worker_next("fixture")
        result = self.store.worker_agent(claim["cycle"]["id"], claim["lease_token"], "/root/deadline_fixture", "source_researcher")
        self.assertEqual("assigned", result["status"])
