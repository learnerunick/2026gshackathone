"""Studio workflows backed by real temporary SQLite state, without external calls."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("boca_studio_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        self.now = datetime.now(timezone.utc)
        path = self.root / "config/overnight.json"
        config = json.loads(path.read_text())
        config['ai_quality_review_enabled'] = True  # Legacy seven-stage policy.
        # Preserve legacy stage fixtures; mandatory research has its own integration tests.
        config.update(specialist_agents_enabled=False, source_research_enabled=False, start_at=(self.now - timedelta(minutes=5)).isoformat(),
                      generation_end_at=(self.now + timedelta(hours=12)).isoformat(),
                      publish_not_before=(self.now - timedelta(minutes=5)).isoformat())
        path.write_text(json.dumps(config))
        (self.root / "fixture.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII="))
        self.store = Store(self.root)
        self.original = self.store.persona()

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self, name="한서윤"):
        result = copy.deepcopy(self.original)
        for field in ("id", "version", "status"):
            result.pop(field, None)
        result.update(display_name=name, bio="AI 가상 인물의 서울 일상 기록")
        return result

    def new_persona(self, name="한서윤"):
        return self.store.create_persona({"profile": self.profile(name)})

    def new_brief(self, persona_id=None, **changes):
        body = {"persona_id": persona_id or self.original["id"],
                "title": "퇴근 후 다섯 살 아이와 정리하는 작은 선반",
                "brief": "물건을 사는 장면 없이 수납 취향을 발견하는 저녁 이야기. 조명과 색감을 따뜻하게.",
                "format": "carousel", "affiliate": "GS SHOP"}
        body.update(changes)
        return self.store.create_brief(body)

    def payload(self, identity=None, content_id="studio-story"):
        persona = identity or self.original
        return {"id": content_id, "title": "집의 작은 취향", "topic_key": content_id,
                "persona_id": persona["id"], "persona_version": persona["version"],
                "caption": "오늘의 작은 기록.\n" + module.DISCLOSURE,
                "hashtags": ["#가상인플루언서"],
                "cards": [{"media": "fixture.png", "alt": "실제 생성과 무관한 테스트 이미지"}],
                "sources": []}

    def studio(self):
        return self.store.state()["studio"]

    def test_existing_persona_is_migrated_and_creation_persists(self):
        before = self.studio()
        self.assertEqual(self.original["id"], before["active_persona_id"])
        self.assertIn(self.original["id"], {p["id"] for p in before["personas"]})
        created = self.new_persona()
        self.assertNotEqual(self.original["id"], created["id"])
        self.assertEqual(1, created["version"])
        self.store = Store(self.root)
        saved = next(p for p in self.studio()["personas"] if p["id"] == created["id"])
        self.assertEqual("한서윤", saved["display_name"])
        self.assertEqual(5, saved["profile"]["family"]["daughter"]["age"])
        self.assertEqual(self.original["id"], self.studio()["active_persona_id"])

    def test_persona_edit_is_versioned_and_stale_editor_cannot_overwrite(self):
        persona = self.new_persona()
        edited = self.profile("한서윤의 새 일상")
        result = self.store.update_persona(persona["id"], {"base_version": 1, "profile": edited})
        self.assertEqual(2, result["version"])
        with self.assertRaises(Problem):
            self.store.update_persona(persona["id"], {"base_version": 1, "profile": self.profile("오래된 수정")})
        self.assertEqual("한서윤의 새 일상", next(p for p in self.studio()["personas"]
                                              if p["id"] == persona["id"])["display_name"])

    def test_persona_selection_does_not_change_existing_content_identity(self):
        self.store.ingest(self.payload())
        other = self.new_persona()
        self.store.select_persona(other["id"])
        edited = self.store.edit("studio-story", {"base_version": 1, "title": "사람이 수정한 제목"})
        self.assertEqual(self.original["id"], edited["payload"]["persona_id"])
        self.assertEqual("approved", self.store.decide("studio-story", 2, True)["status"])
        self.assertEqual(other["id"], Store(self.root).state()["studio"]["active_persona_id"])

    def test_persona_revision_keeps_older_content_reviewable(self):
        self.store.ingest(self.payload())
        self.store.update_persona(self.original["id"], {"base_version": 1, "profile": self.profile("새 표시 이름")})
        self.assertEqual("approved", self.store.decide("studio-story", 1, True)["status"])
        self.assertEqual(1, self.store.state()["contents"][0]["payload"]["persona_version"])

    def test_unknown_persona_or_version_cannot_enter_review(self):
        for identity in ({"id": "missing-persona", "version": 1},
                         {"id": self.original["id"], "version": 999}):
            with self.subTest(identity=identity), self.assertRaises(Problem):
                self.store.ingest(self.payload(identity))
        self.assertEqual([], self.store.state()["contents"])

    def test_ai_revision_cannot_move_existing_content_to_another_persona(self):
        self.store.ingest(self.payload())
        other = self.new_persona()
        with self.assertRaises(Problem):
            self.store.ingest(self.payload(other), expected_version=1)
        content = self.store.state()["contents"][0]
        self.assertEqual(self.original["id"], content["payload"]["persona_id"])
        self.assertEqual(1, content["current_version"])

    def test_cycle_content_must_use_run_persona_and_frozen_version(self):
        self.store.start_run({})
        claim = self.store.worker_next("studio-test-worker")
        other = self.new_persona()
        self.store.update_persona(self.original["id"], {"base_version": 1, "profile": self.profile("새 프로필")})
        for identity in (other, {"id": self.original["id"], "version": 2}):
            with self.subTest(identity=identity["id"]), self.assertRaises(Problem):
                self.store.ingest(self.payload(identity, content_id=claim["cycle"]["content_id"]))
        self.assertEqual([], self.store.state()["contents"])
        valid = self.store.ingest(self.payload(content_id=claim["cycle"]["content_id"]))
        self.assertFalse(valid["proposal"])

    def test_legacy_content_without_persona_id_retains_original_identity(self):
        payload = self.payload()
        payload.pop("persona_id")
        self.store.ingest(payload)
        other = self.new_persona()
        self.store.select_persona(other["id"])
        self.store.decide("studio-story", 1, True)
        current = self.store.state()["contents"][0]
        self.assertEqual(self.original["id"], current["payload"]["persona_id"])

    def test_selecting_another_persona_does_not_interrupt_running_snapshot(self):
        run = self.store.start_run({})
        other = self.new_persona()
        self.store.select_persona(other["id"])
        claim = self.store.worker_next("studio-test-worker")
        self.assertTrue(claim["should_work"], claim)
        self.assertEqual(run["id"], claim["run"]["id"])
        self.assertEqual(self.original["id"], claim["run"]["persona_id"])
        self.assertEqual(1, claim["run"]["persona_version"])

    def test_creation_does_not_silently_start_another_persona_during_run(self):
        run = self.store.start_run({})
        other = self.new_persona()
        self.store.select_persona(other["id"])
        with self.assertRaises(Problem):
            self.store.start_run({})
        self.assertEqual(run["id"], self.store.automation_state()["run"]["id"])

    def test_active_run_keeps_persona_snapshot_after_profile_revision(self):
        run = self.store.start_run({})
        self.store.update_persona(self.original["id"], {"base_version": 1, "profile": self.profile("새 프로필 이름")})
        claim = self.store.worker_next("studio-test-worker")
        self.assertTrue(claim["should_work"], claim)
        self.assertEqual(run["id"], claim["run"]["id"])
        self.assertEqual(1, claim["run"]["persona_version"])
        self.assertEqual(self.original, claim["run"]["persona"])

    def test_brief_edit_is_versioned_and_inputs_survive_restart(self):
        brief = self.new_brief()
        changed = self.store.update_brief(brief["id"], {"base_version": brief["version"],
                                                       "title": "비 오는 날의 조명", "brief": "구매 경험 표현 없이 아늑한 집 이야기"})
        self.assertEqual(brief["version"] + 1, changed["version"])
        with self.assertRaises(Problem):
            self.store.update_brief(brief["id"], {"base_version": brief["version"], "title": "오래된 제목"})
        saved = next(b for b in Store(self.root).state()["studio"]["briefs"] if b["id"] == brief["id"])
        self.assertEqual("비 오는 날의 조명", saved["title"])
        self.assertEqual("구매 경험 표현 없이 아늑한 집 이야기", saved["brief"])

    def test_brief_accepts_parnas_and_preserves_legacy_shop_identifier(self):
        for affiliate, stored in (("파르나스 호텔", "파르나스 호텔"), ("GSSHOP", "GS SHOP"),
                                  ("GS SHOP", "GS SHOP"), ("GS리테일(편의점,수퍼)", "GS리테일")):
            with self.subTest(affiliate=affiliate):
                brief = self.new_brief(affiliate=affiliate)
                self.assertEqual(stored, brief["affiliate"])
                changed = self.store.update_brief(brief["id"], {"base_version": 1, "title": "다음 주말의 취향"})
                self.assertEqual(stored, changed["affiliate"])

    def test_produce_is_idempotent_and_worker_receives_real_brief(self):
        brief = self.new_brief()
        self.store.produce_brief(brief["id"])
        self.store.produce_brief(brief["id"])
        claim = self.store.worker_next("studio-test-worker")
        self.assertTrue(claim["should_work"], claim)
        self.assertEqual(brief["id"], claim["cycle"]["brief_id"])
        job_input = json.loads(claim["job"]["input_json"])
        actual = job_input["brief"]
        self.assertEqual(brief["title"], actual["title"])
        self.assertEqual(brief["brief"], actual["brief"])
        self.assertEqual(brief["format"], actual["format"])
        self.assertEqual(brief["persona_id"], actual["persona_id"])
        with self.store.db() as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM production_runs").fetchone()[0])
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM production_cycles").fetchone()[0])

    def test_single_brief_finishes_in_review_without_starting_unrequested_topics(self):
        brief = self.new_brief()
        self.store.produce_brief(brief["id"])
        content_id = None
        for stage in ("sources", "planning", "storyboard", "copy", "images", "quality", "register"):
            claim = self.store.worker_next("studio-test-worker")
            self.assertTrue(claim["should_work"], claim)
            self.assertEqual(stage, claim["job"]["stage"])
            self.assertEqual(brief["id"], claim["cycle"]["brief_id"])
            content_id = claim["cycle"]["content_id"]
            results = {
                "sources": {"source_ids": []},
                "planning": {"title": brief["title"], "topic_key": "evening-shelf", "source_ids": []},
                "storyboard": {"cards": [{"scene": "퇴근 후 선반을 정리하는 가상 일상"}]},
                "copy": {"caption": module.DISCLOSURE, "hashtags": []},
                "images": {"media": ["fixture.png"]},
                "quality": {"passed": True},
            }
            if stage == "register":
                registered = self.store.ingest(self.payload(content_id=content_id))
                result = {"content_id": registered["id"], "version": registered["version"]}
            else:
                result = results[stage]
            self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], result)
        current = next(b for b in self.studio()["briefs"] if b["id"] == brief["id"])
        self.assertEqual("completed", current["status"])
        self.assertEqual(content_id, current["content_id"])
        contents = self.store.state()["contents"]
        self.assertEqual(1, len(contents))
        self.assertEqual("ready", contents[0]["status"])
        self.assertIsNone(contents[0]["publication"])
        self.assertFalse(self.store.worker_next("studio-test-worker")["should_work"])

    def test_continuous_start_explicitly_upgrades_existing_brief_run(self):
        brief = self.new_brief()
        requested = self.store.produce_brief(brief["id"])
        automatic = self.store.start_run({})
        self.assertEqual(requested["run"]["id"], automatic["id"])
        self.assertEqual("continuous", automatic["settings"]["production_mode"])
        self.assertEqual(requested["run"]["start_at"], automatic["start_at"])
        self.assertEqual(requested["run"]["end_at"], automatic["end_at"])

    def test_scheduled_run_is_not_silently_moved_by_produce(self):
        start = self.now + timedelta(hours=1)
        scheduled = self.store.start_run({"start_at": start.isoformat(),
                                          "end_at": (start + timedelta(hours=3)).isoformat()})
        brief = self.new_brief()
        self.store.produce_brief(brief["id"])
        claim = self.store.worker_next("studio-test-worker")
        self.assertFalse(claim["should_work"])
        run = self.store.automation_state()["run"]
        self.assertEqual(scheduled["id"], run["id"])
        self.assertEqual(start.isoformat(), run["start_at"])

    def test_inflight_brief_does_not_accept_invisible_edits(self):
        brief = self.new_brief()
        self.store.produce_brief(brief["id"])
        claim = self.store.worker_next("studio-test-worker")
        self.assertTrue(claim["should_work"], claim)
        with self.assertRaises(Problem):
            self.store.update_brief(brief["id"], {"base_version": brief["version"], "brief": "제작 도중 달라진 지시"})

    def closed_brief_can_be_revised_and_reproduced(self, brief, old_run):
        saved = next(item for item in self.studio()["briefs"] if item["id"] == brief["id"])
        self.assertIn(saved["status"], ("draft", "failed"))
        changed = self.store.update_brief(brief["id"], {"base_version": saved["version"],
                                                       "brief": "중단 후 사람이 확인하고 다시 요청한 제작 지시"})
        reproduced = self.store.produce_brief(changed["id"])
        self.assertFalse(reproduced["duplicate"])
        self.assertNotEqual(old_run["id"], reproduced["run"]["id"])
        claimed = self.store.worker_next("confirmed-retry-worker")
        self.assertTrue(claimed["should_work"], claimed)
        self.assertEqual(brief["id"], claimed["cycle"]["brief_id"])

    def expire_run(self, run):
        with self.store.db() as db:
            db.execute("UPDATE production_runs SET end_at=? WHERE id=?",
                       ((self.now - timedelta(minutes=1)).isoformat(), run["id"]))
        self.store.automation_state()

    def test_stopped_brief_between_stages_can_be_revised_and_reproduced(self):
        brief = self.new_brief()
        run = self.store.produce_brief(brief["id"])["run"]
        claim = self.store.worker_next("studio-test-worker")
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"source_ids": []})
        self.store.control_run(run["id"], "stop")
        self.closed_brief_can_be_revised_and_reproduced(brief, run)

    def test_deadline_releases_unstarted_brief_for_revision_and_reproduction(self):
        brief = self.new_brief()
        run = self.store.produce_brief(brief["id"])["run"]
        self.expire_run(run)
        self.closed_brief_can_be_revised_and_reproduced(brief, run)

    def test_deadline_releases_brief_between_stages_for_revision_and_reproduction(self):
        brief = self.new_brief()
        run = self.store.produce_brief(brief["id"])["run"]
        claim = self.store.worker_next("studio-test-worker")
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"source_ids": []})
        self.expire_run(run)
        self.closed_brief_can_be_revised_and_reproduced(brief, run)

    def test_stopped_inflight_brief_is_not_automatically_reissued(self):
        brief = self.new_brief()
        run = self.store.produce_brief(brief["id"])["run"]
        claim = self.store.worker_next("studio-test-worker")
        self.store.worker_ping(claim["cycle"]["id"], claim["lease_token"], "unfinished-external-fixture")
        self.store.control_run(run["id"], "stop")
        with self.assertRaises(Problem):
            self.store.produce_brief(brief["id"])
        self.assertFalse(self.store.worker_next("replacement-worker")["should_work"])
        current = next(item for item in self.studio()["briefs"] if item["id"] == brief["id"])
        self.store.update_brief(brief["id"], {"base_version": current["version"],
                                            "brief": "사용자가 확인하고 명시적으로 새 제작 요청"})
        new_run = self.store.produce_brief(brief["id"])["run"]
        new_claim = self.store.worker_next("human-requested-worker")
        self.assertTrue(new_claim["should_work"], new_claim)
        # An old external result arriving after the explicit new request must
        # stay attached to the old cycle without changing the current brief.
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"source_ids": []})
        saved = next(item for item in self.studio()["briefs"] if item["id"] == brief["id"])
        self.assertEqual("producing", saved["status"])
        self.assertEqual(new_run["id"], saved["run_id"])
        self.assertEqual(new_claim["cycle"]["id"], saved["cycle_id"])

    def test_invalid_persona_and_brief_inputs_are_rejected(self):
        for body in ({"profile": {"display_name": "  "}}, {"profile": {"display_name": 12}}):
            with self.subTest(body=body), self.assertRaises(Problem):
                self.store.create_persona(body)
        for change in ({"persona_id": "missing-persona"}, {"title": ""}, {"format": "unsupported"}):
            with self.subTest(change=change), self.assertRaises(Problem):
                self.new_brief(**change)

    def test_settings_preserve_real_connection_and_limits(self):
        with self.assertRaises(Problem):
            self.store.update_settings({"instagram": {"account": "demo_fixture", "connection": "verified"}})
        self.store.update_settings({"workspace_name": "우리 팀의 일상 스튜디오",
                                    "instagram": {"account": "demo_fixture"},
                                    "generation": {"max_attempts_per_job": 2, "max_pending_requests": 12,
                                                   "default_format": "carousel", "video_enabled": False}})
        settings = Store(self.root).state()["studio"]["settings"]
        self.assertEqual("우리 팀의 일상 스튜디오", settings["workspace_name"])
        self.assertEqual("demo_fixture", settings["instagram"]["account"])
        self.assertNotEqual("verified", settings["instagram"]["connection"])
        self.assertEqual(12, settings["generation"]["max_pending_requests"])
        self.assertFalse(self.store.config()["paid_api_allowed"])
        for value in (0, 999):
            with self.subTest(value=value), self.assertRaises(Problem):
                self.store.update_settings({"generation": {"max_attempts_per_job": value}})

    def test_saved_queue_limit_controls_actual_production_requests(self):
        self.store.update_settings({"generation": {"max_pending_requests": 1}})
        first = self.new_brief(title="첫 번째 기획")
        second = self.new_brief(title="두 번째 기획")
        self.store.produce_brief(first["id"])
        with self.assertRaises(Problem):
            self.store.produce_brief(second["id"])
        statuses = {brief["id"]: brief["status"] for brief in self.studio()["briefs"]}
        self.assertEqual("queued", statuses[first["id"]])
        self.assertEqual("draft", statuses[second["id"]])

    def test_saved_default_format_is_used_when_brief_omits_format(self):
        self.store.update_settings({"generation": {"default_format": "image"}})
        brief = self.store.create_brief({"title": "한 장으로 담는 오후", "persona_id": self.original["id"]})
        self.assertEqual("image", brief["format"])

    def test_first_visual_reference_binding_reaches_frozen_run_and_survives_restart(self):
        config_path = self.root / "config/persona.json"
        original_config = config_path.read_bytes()
        (self.root / "daughter.png").write_bytes((self.root / "fixture.png").read_bytes())
        run = self.store.start_run({})
        body = {"version": 1, "mother": "fixture.png", "daughter": "daughter.png"}
        self.store.save_persona_references(self.original["id"], body)
        first = self.store.automation_state()["run"]
        self.assertEqual(run["id"], first["id"])
        self.assertEqual(1, first["persona_version"])
        references = first["persona"]["references"]
        self.assertEqual({"mother", "daughter"}, set(references))
        self.assertEqual(references["mother"]["path"], first["persona"]["visual_reference"])
        for reference in references.values():
            self.assertTrue(Path(reference["path"]).is_file())
            self.assertEqual(64, len(reference["sha256"]))
        self.store = Store(self.root)
        self.store.save_persona_references(self.original["id"], body)
        self.assertEqual(references, self.store.automation_state()["run"]["persona"]["references"])
        self.assertEqual(references, self.store.persona()["references"])
        self.assertEqual(original_config, config_path.read_bytes())

    def test_visual_reference_cannot_be_replaced_or_changed_after_binding(self):
        original_bytes = (self.root / "fixture.png").read_bytes()
        self.store.save_persona_references(self.original["id"], {"version": 1, "mother": "fixture.png"})
        reference = self.store.persona()["references"]["mother"]
        (self.root / "replacement.png").write_bytes(original_bytes + b"replacement-fixture")
        with self.assertRaises(Problem):
            self.store.save_persona_references(self.original["id"], {"version": 1, "mother": "replacement.png"})
        (self.root / "fixture.png").write_bytes(original_bytes + b"changed-fixture")
        with self.assertRaises(Problem):
            self.store.save_persona_references(self.original["id"], {"version": 1, "mother": "fixture.png"})
        self.assertEqual(original_bytes, Path(reference["path"]).read_bytes())
        self.assertEqual(reference, self.store.persona()["references"]["mother"])

    def test_reference_binding_is_scoped_to_persona_and_version(self):
        config_path = self.root / "config/persona.json"
        original_config = config_path.read_bytes()
        persona = self.new_persona()
        self.store.select_persona(persona["id"])
        self.store.save_persona_references(persona["id"], {"version": 1, "mother": "fixture.png"})
        first = self.store.persona_revision(persona["id"], 1)["references"]
        self.store.update_persona(persona["id"], {"base_version": 1, "profile": self.profile("새 외형 버전")})
        (self.root / "version2.png").write_bytes((self.root / "fixture.png").read_bytes() + b"version-two-fixture")
        self.store.save_persona_references(persona["id"], {"version": 2, "mother": "version2.png"})
        second = self.store.persona_revision(persona["id"], 2)["references"]
        self.assertNotEqual(first["mother"]["sha256"], second["mother"]["sha256"])
        self.assertEqual(first, self.store.persona_revision(persona["id"], 1)["references"])
        self.assertFalse(self.store.persona(self.original["id"]).get("references"))
        self.assertEqual(original_config, config_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
