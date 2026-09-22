"""AI stage to bounded video queue integration; every provider call is fake."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("boca_production_media_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem
from test_video import Provider


class ProductionMediaTests(unittest.TestCase):
    def setUp(self):
        # These provider fixtures contain synthetic bytes. Real caption rendering
        # and mandatory voice checks are exercised by test_video_delivery.py.
        media_tools = patch("segmind_video.ensure_delivery_tools")
        media_finish = patch("segmind_video.finish_video_delivery", side_effect=lambda root, snapshot, path: (path, {"fixture": True}))
        media_tools.start()
        media_finish.start()
        self.addCleanup(media_tools.stop)
        self.addCleanup(media_finish.stop)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        self.now = datetime.now(timezone.utc)
        path = self.root / "config/overnight.json"
        config = json.loads(path.read_text())
        config["ai_quality_review_enabled"] = True  # Legacy seven-stage policy.
        # Preserve legacy stage fixtures; mandatory research has its own integration tests.
        config.update(specialist_agents_enabled=False, source_research_enabled=False, start_at=(self.now - timedelta(minutes=1)).isoformat(),
                      generation_end_at=(self.now + timedelta(hours=2)).isoformat())
        path.write_text(json.dumps(config))
        (self.root / "fixture.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII="))
        self.store = Store(self.root)
        self.persona = self.store.persona()
        self.caption = "AI가 기획한 오후의 가상 일상.\n" + module.DISCLOSURE
        self.video_prompt = "0~15초: 가상의 엄마가 창가 선반을 정리한다. 15~30초: 따뜻한 빛과 공간의 취향을 담는다."

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self):
        with patch("segmind_video.SegmindClient.verify", return_value=True):
            self.store.connect_video({"api_key": "fixture-segmind-key-not-real"})

    def bind_reference(self):
        self.store.save_persona_references(self.persona["id"], {"version": 1, "mother": "fixture.png"})

    def claim_images(self, mode="mixed", connect=True, reference=True):
        if connect:
            self.connect()
        if reference:
            self.bind_reference()
        self.store.start_run({"media_mode": mode})
        for stage in ("sources", "planning", "storyboard", "copy"):
            claim = self.store.worker_next("fixture-ai-worker")
            self.assertTrue(claim["should_work"], claim)
            self.assertEqual(stage, claim["job"]["stage"])
            number = claim["cycle"]["number"]
            result = {
                "sources": {"source_ids": []},
                "planning": {"title": "AI 기획 창가의 오후 %s" % number,
                             "topic_key": "fixture-window-%s" % number, "source_ids": [],
                             "content_format": "video" if mode == "video_only" else "carousel"},
                "storyboard": {"cards": [{"scene": "가상의 엄마와 창가 선반"}], "video_prompt": self.video_prompt},
                "copy": {"caption": self.caption, "hashtags": ["#가상일상"]},
            }[stage]
            self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], result)
        images = self.store.worker_next("fixture-ai-worker")
        self.assertTrue(images["should_work"], images)
        self.assertEqual("images", images["job"]["stage"])
        return images

    def request_video(self, claim):
        return self.store.worker_video(claim["cycle"]["id"], claim["lease_token"])

    def finish_review_registration(self, claim):
        quality = self.store.worker_next("fixture-ai-reviewer")
        self.assertTrue(quality["should_work"], quality)
        self.assertEqual("quality", quality["job"]["stage"])
        self.store.worker_complete(quality["cycle"]["id"], quality["lease_token"], {"passed": True})
        registration = self.store.worker_next("fixture-ai-reviewer")
        self.assertEqual("register", registration["job"]["stage"])
        outputs = registration["cycle"]["result"]
        payload = {"id": registration["cycle"]["content_id"],
                   "title": outputs["planning"]["title"], "topic_key": outputs["planning"]["topic_key"],
                   "persona_id": claim["run"]["persona_id"], "persona_version": claim["run"]["persona_version"],
                   "caption": self.caption, "hashtags": ["#가상일상"], "sources": [],
                   "cards": [{"media": path, "alt": "테스트용 가상 일상 영상"} for path in outputs["images"]["media"]]}
        imported = self.store.ingest(payload)
        self.store.worker_complete(registration["cycle"]["id"], registration["lease_token"],
                                   {"content_id": imported["id"], "version": imported["version"]})
        return imported

    def test_md_guides_reach_ai_stages_and_stay_fixed_until_next_content(self):
        guide = self.store.save_video_guide({"filename": "vlog.md", "content": "Handheld everyday video.", "base_version": 0})
        claim = self.claim_images()
        for job in self.store.worker_inspect(claim["cycle"]["id"])["jobs"]:
            self.assertEqual([guide], json.loads(job["input_json"])["video_guides"])
        policy = json.loads(claim["job"]["input_json"])["video_guide_policy"]
        self.assertEqual(("low", 2), (policy["influence"], policy["max_optional_cues"]))
        with self.store.db() as db, patch("segmind_video.video_guide_policy", return_value={"version": 999}):
            self.assertEqual(policy, self.store.cycle_video_guide_policy(db, claim["cycle"]["id"]))
        updated = self.store.save_video_guide({"filename": "vlog.md", "content": "New voice direction.", "base_version": 1})
        self.store = Store(self.root)
        first = self.request_video(claim)
        self.assertEqual([guide], self.store.video_job(first["job_id"])["input"]["guides"])
        self.assertEqual(policy, self.store.video_job(first["job_id"])["input"]["guide_policy"])
        client = Provider()
        self.store.process_video(first["job_id"], client)
        self.assertIn(guide["content"], client.submissions[0]["prompt"])
        self.assertNotIn(updated["content"], client.submissions[0]["prompt"])
        self.store.process_video(first["job_id"], client)
        self.finish_review_registration(claim)
        next_claim = self.store.worker_next("fixture-ai-worker")
        self.assertTrue(next_claim["should_work"])
        self.assertNotEqual(claim["cycle"]["id"], next_claim["cycle"]["id"])
        self.assertEqual([updated], json.loads(next_claim["job"]["input_json"])["video_guides"])

    def test_video_md_does_not_change_image_only_ai_input(self):
        self.store.save_video_guide({"filename": "vlog.md", "content": "Camera movement.", "base_version": 0})
        claim = self.claim_images(mode="images")
        for job in self.store.worker_inspect(claim["cycle"]["id"])["jobs"]:
            self.assertEqual([], json.loads(job["input_json"])["video_guides"])
            self.assertIsNone(json.loads(job["input_json"])["video_guide_policy"])

    def test_ai_storyboard_enters_video_queue_once_and_returns_to_quality_before_ingest(self):
        guide = self.store.save_video_guide({"filename": "style.md", "content": "Natural handheld framing and room tone.", "base_version": 0})
        claim = self.claim_images()
        first = self.request_video(claim)
        repeated = self.request_video(claim)
        self.assertEqual(first["job_id"], repeated["job_id"])
        job = self.store.video_job(first["job_id"])
        self.assertEqual({"run_id": claim["run"]["id"], "cycle_id": claim["cycle"]["id"],
                          "content_id": claim["cycle"]["content_id"]}, job["input"]["production"])
        self.assertEqual(self.video_prompt, job["input"]["storyboard"])
        self.assertEqual([guide], job["input"]["guides"])
        self.assertEqual(self.caption, job["input"]["caption"])
        self.assertEqual((20, "480p"), (job["input"]["duration"], job["input"]["resolution"]))
        self.assertEqual(2.13, job["estimated_cost"])
        client = Provider()
        self.store.process_video(job["id"], client)
        self.store = Store(self.root)
        self.store.process_video(job["id"], client)
        self.assertEqual("completed", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, len(client.submissions))
        self.assertEqual((20, "480p"), (client.submissions[0]["duration"], client.submissions[0]["resolution"]))
        self.assertIn(self.video_prompt, client.submissions[0]["prompt"])
        self.assertIn(guide["content"], client.submissions[0]["prompt"])
        self.assertEqual([], self.store.state()["contents"])
        cycle = self.store.worker_inspect(claim["cycle"]["id"])["cycle"]
        self.assertEqual("quality", cycle["stage"])
        self.assertEqual("pending", cycle["status"])
        self.assertEqual("external-123", self.store.read_stage_result(claim["run"]["id"], cycle["id"], "images")["external_job_id"])
        self.finish_review_registration(claim)
        content = self.store.state()["contents"][0]
        self.assertEqual("ready", content["status"])
        self.assertIsNone(content["publication"])
        with self.store.db() as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0])

    def test_image_only_run_cannot_request_video(self):
        claim = self.claim_images(mode="images")
        with self.assertRaises(Problem):
            self.request_video(claim)
        self.assertEqual([], self.store.video_state()["jobs"])

    def test_completed_video_handoff_recovers_after_restart_without_new_generation(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        provider = Provider()
        self.store.process_video(job_id, provider)
        with patch.object(self.store, "worker_complete", side_effect=OSError("fixture disk temporarily unavailable")):
            self.store.process_video(job_id, provider)
        saved = self.store.video_job(job_id)
        self.assertEqual("completed", saved["status"])
        self.assertEqual(1, saved["sync_pending"])
        self.assertTrue((self.root / saved["result"]["media_path"]).is_file())
        self.assertEqual("images", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["stage"])
        with self.store.db() as db:
            db.execute("UPDATE video_jobs SET next_retry_at=NULL WHERE id=?", (job_id,))
        self.store = Store(self.root)
        self.store.process_video(job_id, provider)
        self.store.process_video(job_id, provider)
        self.assertEqual("quality", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["stage"])
        self.assertEqual(0, self.store.video_job(job_id)["sync_pending"])
        self.assertEqual((1, 1), (len(provider.submissions), provider.downloads))

    def test_handoff_retries_are_bounded_and_manual_resume_only_reapplies_result(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        provider = Provider()
        self.store.process_video(job_id, provider)
        with patch.object(self.store, "worker_complete", side_effect=OSError("fixture handoff failure")) as complete:
            self.store.process_video(job_id, provider)
            for _ in range(8):
                with self.store.db() as db:
                    db.execute("UPDATE video_jobs SET next_retry_at=NULL WHERE id=?", (job_id,))
                self.store.process_video(job_id, provider)
            self.assertEqual(5, complete.call_count)
        self.assertEqual("completed", self.store.video_job(job_id)["status"])
        self.store.resume_video(job_id, {})
        self.store.process_video(job_id, provider)
        self.assertEqual("quality", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["stage"])
        self.assertEqual(1, len(provider.submissions))

    def test_transient_video_error_and_recovery_schedule_are_logged(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        provider = Provider()
        self.store.process_video(job_id, provider)
        provider.fail_poll = True
        self.store.process_video(job_id, provider)
        doc = self.store.read_stage_result(claim["run"]["id"], claim["cycle"]["id"], "images")
        retries = [e for e in doc["events"] if e["detail"].get("next_retry_at")]
        self.assertEqual(1, len(retries))
        self.assertEqual(1, retries[0]["detail"]["poll_errors"])
        self.assertEqual("warning", retries[0]["level"])
        self.assertEqual("running", self.store.automation_state()["run"]["status"])

    def test_uncertain_video_recovers_same_story_and_automatically_continues(self):
        claim = self.claim_images(mode="video_only")
        job_id = self.request_video(claim)["job_id"]
        provider = Provider()
        self.store.process_video(job_id, provider)
        provider.fail_poll = True
        for _ in range(5):
            with self.store.db() as db:
                db.execute("UPDATE video_jobs SET next_retry_at=NULL WHERE id=?", (job_id,))
            self.store.process_video(job_id, provider)
        self.assertEqual("blocked", self.store.automation_state()["run"]["status"])
        self.assertEqual("uncertain", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["status"])
        provider.fail_poll = False
        self.store = Store(self.root)
        self.store.resume_video(job_id, {})
        self.store.process_video(job_id, provider)
        self.assertEqual("completed", self.store.video_job(job_id)["status"])
        self.assertEqual("running", self.store.automation_state()["run"]["status"])
        recovered = self.store.worker_next("fixture-recovered-quality")
        self.assertEqual(claim["cycle"]["id"], recovered["cycle"]["id"])
        self.assertEqual("quality", recovered["job"]["stage"])
        self.assertEqual(1, len(provider.submissions))

    def test_stop_during_download_backoff_keeps_file_without_continuing_story(self):
        claim = self.claim_images(mode="video_only")
        job_id = self.request_video(claim)["job_id"]
        provider = Provider()
        self.store.process_video(job_id, provider)
        provider.fail_download = True
        self.store.process_video(job_id, provider)
        self.store.control_run(claim["run"]["id"], "stop")
        provider.fail_download = False
        with self.store.db() as db:
            db.execute("UPDATE video_jobs SET next_retry_at=NULL WHERE id=?", (job_id,))
        self.store = Store(self.root)
        self.store.process_video(job_id, provider)
        self.assertEqual("completed", self.store.video_job(job_id)["status"])
        self.assertEqual("stopped", self.store.automation_state()["run"]["status"])
        self.assertEqual("stopped", self.store.worker_next("fixture-should-not-start")["reason"])
        self.assertEqual(1, len(provider.submissions))

    def test_pre_submission_sync_failure_can_resume_without_an_external_id(self):
        claim = self.claim_images(mode="video_only")
        job_id = self.request_video(claim)["job_id"]
        provider = Provider()
        with patch.object(self.store, "_production_video_changed", side_effect=OSError("fixture bookkeeping failure")):
            for _ in range(5):
                with self.store.db() as db:
                    db.execute("UPDATE video_jobs SET next_retry_at=NULL WHERE id=?", (job_id,))
                self.store.process_video(job_id, provider)
        self.assertEqual([], provider.submissions)
        self.assertEqual(5, self.store.video_job(job_id)["sync_errors"])
        self.store.resume_video(job_id, {})
        self.store.process_video(job_id, provider)
        self.store.process_video(job_id, provider)
        self.assertEqual(1, len(provider.submissions))
        self.assertEqual("quality", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["stage"])

    def test_media_mode_is_frozen_and_omitted_restart_does_not_change_it(self):
        first = self.store.start_run({"media_mode": "mixed"})
        restarted = Store(self.root).start_run({})
        self.assertEqual(first["id"], restarted["id"])
        self.assertEqual("mixed", restarted["settings"]["media_mode"])
        with self.assertRaises(Problem) as caught:
            self.store.start_run({"media_mode": "images"})
        self.assertEqual(409, caught.exception.status)
        self.assertEqual("mixed", self.store.automation_state()["run"]["settings"]["media_mode"])

    def test_invalid_media_mode_cannot_create_a_run(self):
        with self.assertRaises(Problem) as caught:
            self.store.start_run({"media_mode": "unsupported"})
        self.assertEqual(400, caught.exception.status)
        self.assertIsNone(self.store.automation_state()["run"])

    def test_saved_video_defaults_survive_restart_and_explicit_run_options_reach_provider(self):
        options = {"duration": 25, "resolution": "720p"}
        self.store.update_settings({"generation": {"auto_video": options}})
        self.store = Store(self.root)
        self.assertEqual(options, self.store.studio_state()["settings"]["generation"]["auto_video"])
        run = self.store.start_run({"media_mode": "mixed"})
        self.assertEqual(options, self.store.run_video_settings(run["settings"]))
        self.store.control_run(run["id"], "stop")
        chosen = {"duration": 23, "resolution": "480p"}
        self.store.start_run({"media_mode": "mixed", "video": chosen})
        claim = self.claim_images()
        for job in self.store.worker_inspect(claim["cycle"]["id"])["jobs"]:
            self.assertEqual(chosen, json.loads(job["input_json"])["video_settings"])
        # Saving next-run defaults cannot alter the current storyboard or request.
        self.store.update_settings({"generation": {"auto_video": {"duration": 30, "resolution": "720p"}}})
        self.store = Store(self.root)
        self.assertEqual(chosen, self.store.run_video_settings(self.store.start_run({})["settings"]))
        with self.assertRaises(Problem) as caught:
            self.store.start_run({"video": options})
        self.assertEqual(409, caught.exception.status)
        request = self.request_video(claim)
        client = Provider()
        self.store.process_video(request["job_id"], client)
        self.assertEqual((23, "480p"), (client.submissions[0]["duration"], client.submissions[0]["resolution"]))
        self.assertEqual(2.45, request["estimated_cost"])
        self.assertIn("within 23 seconds", client.submissions[0]["prompt"])

    def test_invalid_video_options_cannot_change_defaults_or_start_a_run(self):
        for invalid in (None, [], {"duration": True}, {"duration": "20"}, {"duration": 19},
                        {"duration": 31}, {"duration": 20.5}, {"resolution": "1080p"},
                        {"daily_estimated_budget_usd": 100}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(Problem):
                    self.store.start_run({"video": invalid})
                with self.assertRaises(Problem):
                    self.store.update_settings({"generation": {"auto_video": invalid}})
        self.assertEqual({"duration": 20, "resolution": "480p"}, self.store.studio_state()["settings"]["generation"]["auto_video"])
        self.assertEqual(15, self.store.video_config()["daily_estimated_budget_usd"])
        self.assertIsNone(self.store.automation_state()["run"])

    def test_legacy_run_keeps_its_previous_video_options(self):
        run = self.store.start_run({"media_mode": "mixed"})
        settings = run["settings"]
        for key in ("duration", "resolution"):
            settings["video"].pop(key)
        with self.store.db() as db:
            db.execute("UPDATE production_runs SET settings_json=? WHERE id=?", (json.dumps(settings), run["id"]))
        claim = self.claim_images()
        result = self.request_video(claim)
        snapshot = self.store.video_job(result["job_id"])["input"]
        self.assertEqual((30, "720p"), (snapshot["duration"], snapshot["resolution"]))

    def test_paused_queue_does_not_upload_or_submit_until_resumed(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        self.store.control_run(claim["run"]["id"], "pause")
        client = Provider()
        with patch.object(client, "upload", side_effect=AssertionError("paused upload")):
            self.store.process_video(job_id, client)
        self.assertEqual([], client.submissions)
        self.assertEqual("queued", self.store.video_job(job_id)["status"])
        self.store.control_run(claim["run"]["id"], "resume")
        self.store.process_video(job_id, client)
        self.assertEqual(1, len(client.submissions))

    def test_stopping_during_reference_upload_cancels_before_billable_submission(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        client = Provider()
        upload = client.upload
        def stop_during_upload(paths):
            self.store.control_run(claim["run"]["id"], "stop")
            return upload(paths)
        with patch.object(client, "upload", side_effect=stop_during_upload):
            self.store.process_video(job_id, client)
        self.assertEqual([], client.submissions)
        self.assertEqual("cancelled", self.store.video_job(job_id)["status"])
        self.assertEqual([], self.store.state()["contents"])

    def test_stop_at_last_submission_boundary_never_sends_paid_request(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        client = Provider()
        record = self.store._production_video_request
        def stop_before_submission(job, payload):
            record(job, payload)
            self.store.control_run(claim["run"]["id"], "stop")
        with patch.object(self.store, "_production_video_request", side_effect=stop_before_submission):
            self.store.process_video(job_id, client)
        self.assertEqual([], client.submissions)
        self.assertEqual("cancelled", self.store.video_job(job_id)["status"])
        self.assertEqual("cancelled", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["status"])

    def test_pause_at_last_submission_boundary_waits_for_resume(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        client = Provider()
        record = self.store._production_video_request
        def pause_before_submission(job, payload):
            record(job, payload)
            self.store.control_run(claim["run"]["id"], "pause")
        with patch.object(self.store, "_production_video_request", side_effect=pause_before_submission):
            self.store.process_video(job_id, client)
        self.assertEqual([], client.submissions)
        self.assertEqual("queued", self.store.video_job(job_id)["status"])
        self.store.control_run(claim["run"]["id"], "resume")
        self.store.process_video(job_id, client)
        self.assertEqual(1, len(client.submissions))

    def test_stop_cancels_unsubmitted_queue_immediately_without_worker_poll(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        self.store.control_run(claim["run"]["id"], "stop")
        self.assertEqual("cancelled", self.store.video_job(job_id)["status"])
        state = self.store.worker_inspect(claim["cycle"]["id"])
        self.assertEqual("cancelled", state["cycle"]["status"])
        self.assertIsNone(state["cycle"]["lease_token"])
        self.assertIn("copy", state["cycle"]["result"])

    def test_stop_before_reference_upload_does_not_revive_cancelled_job(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        client = Provider()
        validate = self.store._validate
        def stop_after_validation(*args, **kwargs):
            value = validate(*args, **kwargs)
            self.store.control_run(claim["run"]["id"], "stop")
            return value
        with patch.object(self.store, "_validate", side_effect=stop_after_validation), patch.object(client, "upload") as upload:
            self.store.process_video(job_id, client)
        upload.assert_not_called()
        self.assertFalse(client.submissions)
        self.assertEqual("cancelled", self.store.video_job(job_id)["status"])

    def test_late_upload_error_keeps_user_cancelled_state(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        client = Provider()
        def interrupted_upload(paths):
            self.store.control_run(claim["run"]["id"], "stop")
            raise OSError("fixture interrupted upload")
        with patch.object(client, "upload", side_effect=interrupted_upload):
            self.store.process_video(job_id, client)
        self.assertEqual("cancelled", self.store.video_job(job_id)["status"])
        self.assertEqual([], client.submissions)

    def test_older_worker_cannot_overwrite_durable_cancellation(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        self.store.control_run(claim["run"]["id"], "stop")
        # An already-running older worker can still arrive at its error handler.
        # The shared database must protect the cancellation without a restart.
        with self.store.db() as db:
            db.execute("UPDATE video_jobs SET status='failed',error='late old worker error' WHERE id=?", (job_id,))
        saved = self.store.video_job(job_id)
        self.assertEqual("cancelled", saved["status"])
        self.assertNotEqual("late old worker error", saved["error"])

    def test_submitted_video_finishes_after_stop_without_next_stage_or_resubmission(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        client = Provider()
        submit = client.submit
        def stop_during_submit(payload):
            self.store.control_run(claim["run"]["id"], "stop")
            return submit(payload)
        with patch.object(client, "submit", side_effect=stop_during_submit):
            self.store.process_video(job_id, client)
        self.store = Store(self.root)
        self.store.process_video(job_id, client)
        self.assertEqual("completed", self.store.video_job(job_id)["status"])
        self.assertTrue((self.root / self.store.video_job(job_id)["result"]["media_path"]).is_file())
        self.assertEqual("stopped", self.store.worker_next("next-worker")["reason"])
        self.assertEqual("cancelled", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["status"])
        self.assertEqual(1, len(client.submissions))
        self.assertEqual([], self.store.state()["contents"])

    def test_deadline_cancels_queued_video_without_external_calls(self):
        claim = self.claim_images()
        job_id = self.request_video(claim)["job_id"]
        with self.store.db() as db:
            db.execute("UPDATE production_runs SET end_at=? WHERE id=?",
                       ((self.now - timedelta(minutes=1)).isoformat(), claim["run"]["id"]))
        client = Provider()
        with patch.object(client, "upload", side_effect=AssertionError("expired upload")):
            self.store.process_video(job_id, client)
        self.assertFalse(client.submissions)
        self.assertEqual("cancelled", self.store.video_job(job_id)["status"])

    def test_frozen_run_persona_version_is_used_after_profile_edit(self):
        claim = self.claim_images(mode="video")
        original_reference = claim["run"]["persona"]["references"]["mother"]
        profile = copy.deepcopy(self.persona)
        profile["display_name"] = "다음 실행의 새 이름"
        self.store.update_persona(self.persona["id"], {"base_version": 1, "profile": profile})
        (self.root / "future-persona.png").write_bytes(b"future-persona-fixture")
        self.store.save_persona_references(self.persona["id"], {"version": 2, "mother": "future-persona.png"})
        job_id = self.request_video(claim)["job_id"]
        self.assertEqual(2, self.store.persona()["version"])
        self.assertEqual(1, self.store.video_job(job_id)["input"]["persona_version"])
        client = Provider()
        self.store.process_video(job_id, client)
        self.assertEqual(original_reference["sha256"], self.store.video_job(job_id)["input"]["identity_reference"]["sha256"])
        self.assertEqual("https://images.segmind.com/test/" + original_reference["media"], client.submissions[0]["reference_images"][0])
        self.store.process_video(job_id, client)
        self.assertEqual("completed", self.store.video_job(job_id)["status"])
        self.assertEqual("quality", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["stage"])

    def test_missing_auth_falls_back_to_images_without_losing_stage_lease(self):
        claim = self.claim_images(connect=False)
        result = self.request_video(claim)
        self.assertEqual(("skipped", "images"), (result["status"], result["fallback"]))
        self.assertEqual([], self.store.video_state()["jobs"])
        self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"media": ["fixture.png"]})
        self.assertEqual("quality", self.store.worker_next("fixture-ai-worker")["job"]["stage"])

    def test_video_only_reaches_provider_and_registers_video_with_fixed_settings(self):
        guide = self.store.save_video_guide({"filename": "only.md", "content": "Subtle natural movement.", "base_version": 0})
        claim = self.claim_images(mode="video_only")
        inputs = json.loads(claim["job"]["input_json"])
        self.assertEqual("video_only", inputs["media_mode"])
        self.assertTrue(claim["run"]["settings"]["video"]["required"])
        self.assertEqual({"duration": 20, "resolution": "480p"}, inputs["video_settings"])
        self.assertEqual([guide], inputs["video_guides"])
        self.assertEqual("video_only", Store(self.root).start_run({})["settings"]["media_mode"])
        with self.assertRaises(Problem):
            self.store.start_run({"media_mode": "mixed"})
        request = self.request_video(claim)
        self.assertEqual(request["job_id"], self.request_video(claim)["job_id"])
        client = Provider()
        self.store.process_video(request["job_id"], client)
        self.store.process_video(request["job_id"], client)
        self.assertEqual(1, len(client.submissions))
        self.assertTrue(client.submissions[0]["reference_images"])
        self.assertEqual("completed", self.store.video_job(request["job_id"])["status"])
        imported = self.finish_review_registration(claim)
        self.assertEqual(1, imported["version"])
        self.assertEqual(1, self.store.automation_state()["run"]["completed_count"])

    def test_video_only_missing_auth_waits_and_resumes_same_story_without_retry_charge(self):
        claim = self.claim_images(mode="video_only", connect=False)
        result = self.request_video(claim)
        self.assertEqual(("blocked", None), (result["status"], result["fallback"]))
        self.assertEqual([], self.store.video_state()["jobs"])
        self.assertEqual("blocked", self.store.worker_next("fixture-worker")["reason"])
        self.store = Store(self.root)
        self.assertEqual("blocked", self.store.automation_state()["run"]["status"])
        self.connect()
        self.store.control_run(claim["run"]["id"], "resume")
        resumed = self.store.worker_next("fixture-resumed")
        self.assertEqual(claim["cycle"]["id"], resumed["cycle"]["id"])
        self.assertEqual("images", resumed["job"]["stage"])
        self.assertEqual(claim["job"]["attempts"], resumed["job"]["attempts"])
        self.assertEqual("queued", self.request_video(resumed)["status"])

    def test_video_only_missing_portrait_waits_without_image_fallback(self):
        claim = self.claim_images(mode="video_only", reference=False)
        self.assertEqual("blocked", self.request_video(claim)["status"])
        self.assertIn("기준 이미지", self.store.automation_state()["run"]["pause_reason"])
        self.assertEqual([], self.store.video_state()["jobs"])

    def test_video_only_budget_and_queue_limits_wait_without_submission(self):
        config_path = self.root / "config/video.json"
        original = json.loads(config_path.read_text())
        claim = self.claim_images(mode="video_only")
        for setting, value in (("daily_estimated_budget_usd", 0), ("max_pending", 0)):
            with self.subTest(setting=setting):
                config_path.write_text(json.dumps(dict(original, **{setting: value})))
                self.assertEqual("blocked", self.request_video(claim)["status"])
                self.assertEqual([], self.store.video_state()["jobs"])
                self.store.control_run(claim["run"]["id"], "resume")
                claim = self.store.worker_next("fixture-resumed")

    def test_video_only_rejects_image_completion_and_image_import(self):
        claim = self.claim_images(mode="video_only")
        with self.assertRaisesRegex(Problem, "MP4"):
            self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], {"media": ["fixture.png"]})
        self.assertEqual("images", self.store.worker_inspect(claim["cycle"]["id"])["cycle"]["stage"])
        with self.assertRaisesRegex(Problem, "MP4"):
            self.store.ingest({"id": claim["cycle"]["content_id"], "title": "이미지 대체 차단",
                               "topic_key": "image-fallback", "persona_id": self.persona["id"], "persona_version": 1,
                               "caption": self.caption, "hashtags": [], "sources": [],
                               "cards": [{"media": "fixture.png", "alt": "시안 이미지"}]})
        self.assertEqual([], self.store.state()["contents"])

    def test_video_only_rejects_carousel_planning(self):
        self.store.start_run({"media_mode": "video_only"})
        sources = self.store.worker_next("fixture-worker")
        self.store.worker_complete(sources["cycle"]["id"], sources["lease_token"], {"source_ids": []})
        planning = self.store.worker_next("fixture-worker")
        with self.assertRaisesRegex(Problem, "content_format"):
            self.store.worker_complete(planning["cycle"]["id"], planning["lease_token"],
                                       {"title": "그림 이야기", "topic_key": "bad-image", "content_format": "carousel"})

    def test_missing_persona_reference_falls_back_without_a_video_job(self):
        claim = self.claim_images(reference=False)
        result = self.request_video(claim)
        self.assertEqual(("skipped", "images"), (result["status"], result["fallback"]))
        self.assertEqual([], self.store.video_state()["jobs"])
        self.assertTrue(self.store.worker_ping(claim["cycle"]["id"], claim["lease_token"])["can_continue"])

    def test_daily_video_budget_remains_enforced_across_continuous_cycles(self):
        config_path = self.root / "config/video.json"
        config = json.loads(config_path.read_text())
        config["daily_estimated_budget_usd"] = 3
        config_path.write_text(json.dumps(config))
        first = self.claim_images()
        job_id = self.request_video(first)["job_id"]
        client = Provider()
        self.store.process_video(job_id, client)
        self.store.process_video(job_id, client)
        self.finish_review_registration(first)
        second = self.claim_images()
        result = self.request_video(second)
        self.assertEqual(("skipped", "images"), (result["status"], result["fallback"]))
        jobs = self.store.video_state()["jobs"]
        self.assertEqual(1, len(jobs))
        self.assertLessEqual(sum(job["estimated_cost"] for job in jobs), 3)
        self.assertEqual(1, len(client.submissions))
        self.assertTrue(self.store.worker_ping(second["cycle"]["id"], second["lease_token"])["can_continue"])


if __name__ == "__main__":
    unittest.main()
