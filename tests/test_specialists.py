"""Stage specialist attribution and ownership; no live agents or paid calls."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("boca_specialists_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem
from test_video import Provider


ROLES = {"sources": "source_researcher", "planning": "lifestyle_planner", "storyboard": "storyboard_director",
         "copy": "persona_copywriter", "images": "visual_producer", "quality": "quality_reviewer", "register": "feed_editor"}


class SpecialistTests(unittest.TestCase):
    def setUp(self):
        # These provider fixtures contain synthetic bytes. Real caption rendering
        # and mandatory voice checks are exercised by test_video_delivery.py.
        media_tools = patch("segmind_video.ensure_delivery_tools")
        media_finish = patch("segmind_video.finish_video_delivery", side_effect=lambda root, snapshot, path: (path, {"fixture": True}))
        media_tools.start()
        media_finish.start()
        self.addCleanup(media_tools.stop)
        self.addCleanup(media_finish.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        self.current = datetime.now(timezone.utc)
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["ai_quality_review_enabled"] = True  # Legacy seven-stage policy.
        # Source receipts have independent coverage; specialist policy keeps its real default.
        config.update(source_research_enabled=False, start_at=(self.current - timedelta(minutes=1)).isoformat(),
                      generation_end_at=(self.current + timedelta(hours=2)).isoformat(), media_mode="images")
        config.pop("specialist_agents_enabled", None)
        config_path.write_text(json.dumps(config))
        (self.root / "fixture.png").write_bytes(b"specialist-reference-image")
        self.store = Store(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, **changes):
        self.run = self.store.start_run(dict({"media_mode": "images"}, **changes))
        return self.run

    def claim(self, stage):
        claim = self.store.worker_next("fixture-specialist-coordinator")
        self.assertTrue(claim["should_work"], claim)
        self.assertEqual(stage, claim["job"]["stage"])
        return claim

    def assign(self, claim, agent_id=None, role_id=None, token=None):
        stage = claim["job"]["stage"]
        return self.store.worker_agent(claim["cycle"]["id"], token or claim["lease_token"],
                                       agent_id or "/root/fixture_" + stage, role_id or ROLES[stage])

    def result(self, claim):
        stage, number = claim["job"]["stage"], claim["cycle"]["number"]
        return {"sources": {"source_ids": []},
                "planning": {"title": "전문가 제작 일상 %d" % number, "topic_key": "specialist-%d" % number, "source_ids": []},
                "storyboard": {"cards": [{"scene": "집의 선반을 정리하는 가상 일상"}],
                               "video_prompt": "0~15초: 창가의 선반. 15~30초: 현관의 작은 소품."},
                "copy": {"caption": "하루의 작은 정리. " + module.DISCLOSURE, "hashtags": []},
                "images": {"media": ["fixture.png"]}, "quality": {"passed": True}}[stage]

    def complete(self, claim, assignment, result=None):
        result = dict(result if result is not None else self.result(claim))
        result["specialist_assignment_id"] = assignment["assignment_id"]
        return self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], result)

    def advance_to(self, stage, creative_agent="/root/fixture_creator"):
        for current in ROLES:
            claim = self.claim(current)
            if current == stage:
                return claim
            agent = "/root/fixture_researcher" if current == "sources" else creative_agent
            self.complete(claim, self.assign(claim, agent_id=agent))
        self.fail("Requested stage is absent")

    def database_snapshot(self):
        with sqlite3.connect(str(self.store.db_path)) as db:
            return tuple(db.iterdump())

    def test_default_required_role_pack_is_frozen_and_body_cannot_disable_delegation(self):
        pack_path = self.root / "config/specialists.json"
        original = json.loads(pack_path.read_text())
        run = self.start(specialist_agents_enabled=False)
        self.assertIs(True, run["settings"]["specialist_agents_enabled"])
        self.assertEqual(original, run["settings"]["specialist_pack"])
        self.assertEqual(original["version"], run["settings"]["specialist_pack_version"])
        expected_roles = [dict(role, version=role.get("version", original["version"])) for role in original["roles"]]
        self.assertEqual(expected_roles, run["settings"]["specialist_roles"])
        original_source_role = json.loads(json.dumps(next(role for role in original["roles"] if "sources" in role["stages"])))
        for role in original["roles"]:
            role["name"] = "CHANGED-AFTER-RUN-FIXTURE"
            role["instructions"] = ["Changed instruction after the run started"]
        pack_path.write_text(json.dumps(original))
        self.store = Store(self.root)
        claim = self.claim("sources")
        specialist = json.loads(claim["job"]["input_json"])["specialist"]
        self.assertEqual(ROLES["sources"], specialist["role_id"])
        self.assertEqual(original_source_role["name"], specialist["name"])
        self.assertEqual(original_source_role["instructions"], specialist["instructions"])
        for field in ("expertise", "instructions", "output_contract", "delegation"):
            self.assertTrue(specialist[field])

    def test_unassigned_and_wrong_assignment_completion_cannot_advance(self):
        self.start()
        claim = self.claim("sources")
        for result in (self.result(claim), dict(self.result(claim), specialist_assignment_id="invented-assignment")):
            with self.subTest(result=result), self.assertRaises(Problem):
                self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], result)
        assignment = self.assign(claim)
        completed = self.complete(claim, assignment)
        self.assertEqual("planning", completed["cycle"]["stage"])
        self.assertEqual(assignment["assignment_id"], completed["cycle"]["result"]["sources"]["specialist_assignment_id"])
        planning = self.claim("planning")
        self.assign(planning)
        with self.assertRaises(Problem):
            self.complete(planning, assignment)

    def test_same_agent_assignment_is_idempotent_and_cannot_be_rebound(self):
        self.start()
        claim = self.claim("sources")
        assigned = self.assign(claim)
        self.assertEqual("assigned", assigned["status"])
        self.assertEqual("/root/fixture_sources", assigned["agent_id"])
        self.assertEqual(ROLES["sources"], assigned["role_id"])
        self.assertEqual(claim["cycle"]["id"], assigned["cycle_id"])
        before = self.database_snapshot()
        repeated = self.assign(claim)
        self.assertEqual(assigned["assignment_id"], repeated["assignment_id"])
        self.assertEqual(before, self.database_snapshot())
        with self.assertRaises(Problem):
            self.assign(claim, agent_id="/root/different_researcher")
        self.assertEqual(before, self.database_snapshot())

    def test_wrong_role_noncanonical_identity_wrong_token_and_expired_lease_are_denied(self):
        self.start()
        claim = self.claim("sources")
        for agent in ("display-name-only", "/root", "/root/name with spaces", "https://example.com/agent"):
            with self.subTest(agent=agent), self.assertRaises(Problem):
                self.assign(claim, agent_id=agent)
        with self.assertRaises(Problem):
            self.assign(claim, role_id=ROLES["copy"])
        with self.assertRaises(Problem):
            self.assign(claim, token="wrong-fixture-token")
        with self.store.db() as db:
            db.execute("UPDATE production_cycles SET lease_expires_at=? WHERE id=?",
                       ((self.current - timedelta(minutes=1)).isoformat(), claim["cycle"]["id"]))
        before = self.database_snapshot()
        with self.assertRaises(Problem):
            self.assign(claim)
        self.assertEqual(before, self.database_snapshot())

    def test_retry_has_a_new_assignment_and_rejects_the_previous_attempt_reference(self):
        self.start()
        first = self.claim("sources")
        old = self.assign(first)
        self.store.worker_fail(first["cycle"]["id"], first["lease_token"], "검증용 일시적 작업 실패", retryable=True)
        retried = self.claim("sources")
        self.assertNotEqual(first["lease_token"], retried["lease_token"])
        with self.assertRaises(Problem):
            self.assign(first)
        current = self.assign(retried)
        self.assertNotEqual(old["assignment_id"], current["assignment_id"])
        self.assertEqual(2, current["attempt"])
        with self.assertRaises(Problem):
            self.complete(retried, old)
        self.complete(retried, current)
        assignments = {item["assignment_id"]: item for item in self.store.automation_state()["specialists"]["assignments"]}
        self.assertEqual("failed", assignments[old["assignment_id"]]["status"])
        self.assertEqual("completed", assignments[current["assignment_id"]]["status"])

    def test_paused_and_stopped_runs_cannot_assign_new_specialists(self):
        self.start()
        claim = self.claim("sources")
        self.store.control_run(self.run["id"], "pause")
        with self.assertRaises(Problem):
            self.assign(claim)
        self.store.control_run(self.run["id"], "resume")
        assigned = self.assign(claim)
        self.assertEqual("assigned", assigned["status"])
        self.store.control_run(self.run["id"], "stop")
        with self.assertRaises(Problem):
            self.assign(claim, agent_id="/root/new_after_stop")
        saved = next(item for item in self.store.automation_state()["specialists"]["assignments"]
                     if item["assignment_id"] == assigned["assignment_id"])
        self.assertEqual("interrupted", saved["status"])

    def test_quality_agent_is_independent_from_actual_creative_author_identity(self):
        self.start()
        quality = self.advance_to("quality")
        with self.assertRaises(Problem):
            self.assign(quality, agent_id="/root/fixture_creator")
        reviewer = self.assign(quality, agent_id="/root/independent_quality_reviewer")
        self.complete(quality, reviewer)
        registration = self.claim("register")
        editor = self.assign(registration, agent_id="/root/fixture_feed_editor")
        imported = self.store.ingest({"id": registration["cycle"]["content_id"], "title": "검수 후 등록한 가상 일상",
                                      "topic_key": "specialist-1", "persona_id": self.run["persona_id"],
                                      "persona_version": self.run["persona_version"], "caption": module.DISCLOSURE,
                                      "cards": [{"media": "fixture.png", "alt": "임시 검증 이미지"}], "sources": []})
        self.complete(registration, editor, {"content_id": imported["id"], "version": imported["version"]})
        content = next(row for row in self.store.state()["contents"] if row["id"] == imported["id"])
        self.assertEqual("ready", content["status"])
        self.assertIsNone(content["publication"])

    def test_completion_records_readable_agent_attribution_in_artifacts_and_logs(self):
        self.start()
        claim = self.claim("sources")
        assignment = self.assign(claim)
        self.complete(claim, assignment)
        stage = self.store.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources")
        recorded = stage["specialist_assignment"]
        self.assertEqual("completed", recorded["status"])
        self.assertEqual(assignment["assignment_id"], recorded["assignment_id"])
        self.assertEqual("coordinator", recorded["recorded_by"])
        self.assertIs(False, recorded["runtime_verified"])
        self.assertTrue(recorded["result_summary"])
        self.assertEqual("/api/runs/%s/stages/%s/sources" % (self.run["id"], claim["cycle"]["id"]), recorded["result_artifact"])
        self.assertEqual(recorded, stage["result"]["specialist_assignment"])
        state_record = next(item for item in self.store.automation_state()["specialists"]["assignments"]
                            if item["assignment_id"] == assignment["assignment_id"])
        self.assertEqual(recorded, state_record)
        serialized = json.dumps(stage, ensure_ascii=False)
        for value in (assignment["assignment_id"], assignment["agent_id"], assignment["role_id"], assignment["role_name"]):
            self.assertIn(value, serialized)
        log, _, _ = self.store.export_log(self.run["id"], "jsonl")
        self.assertIn(assignment["agent_id"], log.decode())
        self.assertIn(assignment["assignment_id"], log.decode())
        self.assertNotIn(claim["lease_token"], log.decode())

    def test_live_team_state_survives_handoff_without_artifact_loading(self):
        self.start()
        idle = self.store.automation_state()
        self.assertEqual("waiting", idle["worker_status"])
        self.assertIsNone(idle["specialists"]["cycle"])
        claim = self.claim("sources")
        unassigned = self.store.automation_state()["specialists"]
        self.assertEqual(claim["cycle"]["id"], unassigned["cycle"]["id"])
        self.assertEqual("running", unassigned["stage_jobs"][0]["status"])
        self.assertIsNone(unassigned["current"])
        assignment = self.assign(claim)
        self.assertEqual(assignment["assignment_id"], self.store.automation_state()["specialists"]["current"]["assignment_id"])
        self.complete(claim, assignment)
        # No lease is held between stages; completed badges still have a cycle.
        handoff = self.store.automation_state()["specialists"]
        self.assertIsNone(handoff["current"])
        self.assertEqual("pending", handoff["cycle"]["status"])
        self.assertEqual(claim["cycle"]["id"], handoff["cycle"]["id"])
        self.assertEqual("completed", handoff["stage_jobs"][0]["status"])
        self.assertNotIn(claim["lease_token"], json.dumps(handoff))
        next_claim = self.claim("planning")
        next_assignment = self.assign(next_claim)
        self.store = Store(self.root)
        live = self.store.automation_state()["specialists"]
        self.assertEqual(next_assignment["assignment_id"], live["current"]["assignment_id"])
        self.assertEqual({"sources": "completed", "planning": "running"}, {job["stage"]: job["status"] for job in live["stage_jobs"]})

    def test_asynchronous_video_keeps_visual_specialist_attribution_before_quality_review(self):
        with patch("segmind_video.SegmindClient.verify", return_value=True):
            self.store.connect_video({"api_key": "fixture-specialist-video-key"})
        persona = self.store.persona()
        self.store.save_persona_references(persona["id"], {"version": persona["version"], "mother": "fixture.png"})
        self.start(media_mode="mixed")
        images = self.advance_to("images")
        with self.assertRaises(Problem):
            self.store.worker_video(images["cycle"]["id"], images["lease_token"])
        assignment = self.assign(images, agent_id="/root/fixture_video_director")
        queued = self.store.worker_video(images["cycle"]["id"], images["lease_token"])
        job = self.store.video_job(queued["job_id"])
        self.assertEqual(assignment["assignment_id"], job["input"]["production"]["specialist_assignment_id"])
        provider = Provider()
        self.store.process_video(job["id"], provider)
        self.store.process_video(job["id"], provider)
        current = self.store.worker_inspect(images["cycle"]["id"])
        self.assertEqual("quality", current["cycle"]["stage"])
        self.assertEqual("pending", current["cycle"]["status"])
        result = current["cycle"]["result"]["images"]
        self.assertEqual(assignment["assignment_id"], result["specialist_assignment_id"])
        self.assertTrue(result["review_required"])
        self.assertEqual(1, len(provider.submissions))
        self.assertEqual([], self.store.state()["contents"])
        stage = self.store.read_stage_result(self.run["id"], images["cycle"]["id"], "images")
        self.assertEqual("completed", stage["specialist_assignment"]["status"])
        self.assertEqual(assignment["assignment_id"], stage["specialist_assignment"]["assignment_id"])
        self.assertIn(assignment["agent_id"], json.dumps(stage, ensure_ascii=False))

    def test_research_and_specialist_contracts_both_gate_sources_and_preserve_provenance(self):
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["source_research_enabled"] = True
        config_path.write_text(json.dumps(config))
        self.start()
        sources = self.claim("sources")
        inputs = json.loads(sources["job"]["input_json"])
        self.assertTrue(inputs["source_research"]["enabled"])
        self.assertTrue(inputs["specialist"]["delegation"]["required"])
        fact = "공식 페이지의 생활 소품 소개를 검증하는 임시 자료"
        research = {
            "queries": [{"affiliate": "GS SHOP", "query": "site:gsshop.com 생활 소품 소개"}],
            "materials": [{"affiliate": "GS SHOP", "title": "전문가 조사 임시 자료",
                           "url": "https://www.gsshop.com/fixture-specialist-research",
                           "verified_at": (self.current - timedelta(minutes=1)).isoformat(),
                           "expires_at": None, "validity_note": "기간 한정 혜택 없는 상시 브랜드 소개입니다.",
                           "material_type": "brand", "visibility": "internal", "claims": [fact],
                           "evidence": [{"claim": fact, "excerpt": "테스트용 페이지 본문: " + fact}]}],
            "rejected": [], "decision_summary": "공식 자료의 본문 근거를 확인한 뒤 제작에 연결합니다.",
        }
        before = self.database_snapshot()
        with self.assertRaises(Problem) as caught:
            self.store.worker_sources(sources["cycle"]["id"], sources["lease_token"], research)
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(before, self.database_snapshot())
        assignment = self.assign(sources, agent_id="/root/fixture_official_source_researcher")
        receipt = self.store.worker_sources(sources["cycle"]["id"], sources["lease_token"], research)
        result = {"research_id": receipt["research_id"], "source_ids": receipt["source_ids"],
                  "specialist_assignment_id": assignment["assignment_id"]}
        for missing in ("research_id", "source_ids", "specialist_assignment_id"):
            incomplete = {key: value for key, value in result.items() if key != missing}
            with self.subTest(missing=missing), self.assertRaises(Problem):
                self.store.worker_complete(sources["cycle"]["id"], sources["lease_token"], incomplete)
        completed = self.store.worker_complete(sources["cycle"]["id"], sources["lease_token"], result)
        saved = completed["cycle"]["result"]["sources"]
        self.assertEqual(receipt["research_id"], saved["source_research"]["research_id"])
        self.assertEqual(receipt["source_ids"], saved["source_research"]["source_ids"])
        self.assertEqual("codex-web", saved["source_research"]["provenance"]["provider"])
        self.assertEqual("worker", saved["source_research"]["provenance"]["verified_by"])
        self.assertEqual(assignment["assignment_id"], saved["specialist_assignment"]["assignment_id"])
        self.assertEqual("completed", saved["specialist_assignment"]["status"])
        self.assertEqual(assignment["agent_id"], saved["specialist_assignment"]["agent_id"])
        self.assertEqual("coordinator", saved["specialist_assignment"]["recorded_by"])
        self.assertFalse(saved["specialist_assignment"]["runtime_verified"])
        stage = self.store.read_stage_result(self.run["id"], sources["cycle"]["id"], "sources")
        self.assertEqual(saved, stage["result"])


if __name__ == "__main__":
    unittest.main()
