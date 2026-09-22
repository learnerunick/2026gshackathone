"""Production repair/recovery integration; provider calls and storage are fake."""
import json
import unittest
from unittest.mock import patch

import test_specialists as fixtures
import test_production_media as legacy_fixtures
from test_video import Provider


class VideoRepairTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SpecialistTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.store = self.fixture.store
        with patch("segmind_video.SegmindClient.verify", return_value=True):
            self.store.connect_video({"api_key": "fixture-repair-not-a-real-key"})
        persona = self.store.persona()
        self.store.save_persona_references(persona["id"], {"version": persona["version"], "mother": "fixture.png"})
        self.fixture.start(media_mode="mixed")
        self.images = self.fixture.advance_to("images")
        self.assignment = self.fixture.assign(self.images, agent_id="/root/fixture_visual_producer")

    def video(self, claim):
        return self.store.worker_video(claim["cycle"]["id"], claim["lease_token"])

    def finish_video(self, queued, provider):
        self.store.process_video(queued["job_id"], provider)
        self.store.process_video(queued["job_id"], provider)
        self.assertEqual("completed", self.store.video_job(queued["job_id"])["status"])

    def repair(self):
        quality = self.fixture.claim("quality")
        self.fixture.assign(quality, agent_id="/root/fixture_independent_reviewer")
        result = self.store.worker_repair(quality["cycle"]["id"], quality["lease_token"], "images", ["인물 외형을 기준 이미지에 맞춰 수정"])
        self.assertTrue(result["retryable"])
        images = self.fixture.claim("images")
        assigned = self.fixture.assign(images, agent_id="/root/fixture_visual_producer")
        return images, assigned

    def count_videos(self):
        with self.store.db() as db:
            return db.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]

    def test_quality_repair_creates_one_new_video_and_old_result_cannot_complete_it(self):
        first = self.video(self.images)
        provider = Provider()
        self.finish_video(first, provider)
        images, assignment = self.repair()
        self.assertNotEqual(self.assignment["assignment_id"], assignment["assignment_id"])
        repaired = self.video(images)
        self.assertNotEqual(first["job_id"], repaired["job_id"])
        self.assertEqual(repaired["job_id"], self.video(images)["job_id"])
        self.store._production_video_changed(first["job_id"])
        current = self.store.worker_inspect(images["cycle"]["id"])["cycle"]
        self.assertEqual(("images", "running"), (current["stage"], current["status"]))
        self.finish_video(repaired, provider)
        current = self.store.worker_inspect(images["cycle"]["id"])["cycle"]
        self.assertEqual(("quality", "pending"), (current["stage"], current["status"]))
        self.assertEqual(assignment["assignment_id"], current["result"]["images"]["specialist_assignment_id"])
        self.assertEqual(repaired["job_id"], current["result"]["images"]["video_job_id"])
        self.assertEqual((2, 2), (len(provider.submissions), self.count_videos()))

    def test_lease_reassignment_cannot_make_a_duplicate_paid_request(self):
        queued = self.video(self.images)
        self.store.worker_checkpoint(self.images["cycle"]["id"], self.images["lease_token"], {"video_job_id": queued["job_id"]}, release=True)
        resumed = self.fixture.claim("images")
        self.fixture.assign(resumed, agent_id="/root/fixture_recovery_visual")
        self.assertEqual(self.images["job"]["attempts"], resumed["job"]["attempts"])
        with self.assertRaises(fixtures.Problem):
            self.video(resumed)
        provider = Provider()
        self.store.process_video(queued["job_id"], provider)
        self.assertEqual(1, self.count_videos())
        self.assertEqual([], provider.submissions)

    def test_repair_does_not_resubmit_an_unresolved_earlier_video(self):
        queued = self.video(self.images)
        # Even an erroneous early completion by a coordinator must not allow
        # a quality repair to produce another billable request while pending.
        self.fixture.complete(self.images, self.assignment)
        images, _ = self.repair()
        with self.assertRaises(fixtures.Problem) as caught:
            self.video(images)
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(1, self.count_videos())
        self.assertEqual("queued", self.store.video_job(queued["job_id"])["status"])

    def test_repair_retains_shared_video_budget_and_falls_back_to_images(self):
        config_path = self.fixture.root / "config/video.json"
        config = json.loads(config_path.read_text())
        config["daily_estimated_budget_usd"] = 3
        config_path.write_text(json.dumps(config))
        first = self.video(self.images)
        provider = Provider()
        self.finish_video(first, provider)
        images, _ = self.repair()
        fallback = self.video(images)
        self.assertEqual(("skipped", "images"), (fallback["status"], fallback["fallback"]))
        self.assertEqual((1, 1), (len(provider.submissions), self.count_videos()))

    def test_legacy_run_old_video_cannot_complete_a_quality_repair(self):
        legacy = legacy_fixtures.ProductionMediaTests()
        legacy.setUp()
        self.addCleanup(legacy.doCleanups)
        self.addCleanup(legacy.tearDown)
        images = legacy.claim_images()
        first = legacy.request_video(images)
        provider = Provider()
        legacy.store.process_video(first["job_id"], provider)
        legacy.store.process_video(first["job_id"], provider)
        quality = legacy.store.worker_next("fixture-legacy-reviewer")
        legacy.store.worker_repair(quality["cycle"]["id"], quality["lease_token"], "images", ["이미지 재검수 필요"])
        repaired_images = legacy.store.worker_next("fixture-legacy-visual")
        legacy.store._production_video_changed(first["job_id"])
        current = legacy.store.worker_inspect(images["cycle"]["id"])["cycle"]
        self.assertEqual(("images", "running"), (current["stage"], current["status"]))
        second = legacy.request_video(repaired_images)
        self.assertNotEqual(first["job_id"], second["job_id"])
        legacy.store.process_video(second["job_id"], provider)
        legacy.store.process_video(second["job_id"], provider)
        current = legacy.store.worker_inspect(images["cycle"]["id"])["cycle"]
        self.assertEqual("quality", current["stage"])
        self.assertEqual(second["job_id"], current["result"]["images"]["video_job_id"])
        self.assertEqual(2, len(provider.submissions))


if __name__ == "__main__":
    unittest.main()
