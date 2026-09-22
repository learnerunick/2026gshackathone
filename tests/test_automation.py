"""Durable automation behavior; all media, sources, and storage are temporary."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import importlib.util
import json
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
spec = importlib.util.spec_from_file_location("boca_automation_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem
STAGES = ("sources", "planning", "storyboard", "copy", "images", "quality", "register")


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        self.reference_time = datetime.now(timezone.utc)
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["ai_quality_review_enabled"] = True  # Legacy seven-stage policy.
        config.update(
            specialist_agents_enabled=False,  # Legacy coordinator fixtures; mandatory delegation has its own tests.
            source_research_enabled=False,  # Legacy run fixtures; new policy is covered in test_source_research.
            start_at=(self.reference_time - timedelta(minutes=5)).isoformat(),
            generation_end_at=(self.reference_time + timedelta(hours=12)).isoformat(),
            publish_not_before=(self.reference_time - timedelta(minutes=5)).isoformat(),
            max_attempts_per_job=2,
            max_pending_contents=100,
            target_posts=10,
            instagram={"account": "fixture_account", "connection": "verified"},
        )
        config_path.write_text(json.dumps(config))
        (self.root / "fixture.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII="))
        self.store = Store(self.root)
        self.source = self.store.upsert_source({
            "affiliate": "GS SHOP", "title": "가상 소품 자료", "url": "https://example.com/fixture",
            "verified_at": (self.reference_time - timedelta(hours=1)).isoformat(),
            "expires_at": (self.reference_time + timedelta(days=3)).isoformat(),
            "claims": ["테스트용 가상 자료"], "visibility": "internal",
        })

    def tearDown(self):
        self.tmp.cleanup()

    @contextmanager
    def at_time(self, value):
        """Move time without sleeping or editing persisted scheduler records."""
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)

        namespace = Store.worker_next.__globals__
        with patch.dict(namespace, {"datetime": FrozenDatetime, "now": lambda: value.isoformat()}):
            yield

    def claim(self, expected_stage=None):
        claim = self.store.worker_next("fixture-worker")
        self.assertTrue(claim["should_work"], claim)
        if expected_stage:
            self.assertEqual(expected_stage, claim["job"]["stage"])
            self.assertEqual(expected_stage, claim["cycle"]["stage"])
        return claim

    def payload(self, claim):
        number = claim["cycle"]["number"]
        return {
            "id": claim["cycle"]["content_id"], "title": "가상 일상 %s" % number,
            "topic_key": "fixture-topic-%s" % number, "persona_version": self.store.persona()["version"],
            "caption": "오늘의 작은 기록.\n" + module.DISCLOSURE,
            "hashtags": ["#가상인플루언서"],
            "cards": [{"media": "fixture.png", "alt": "테스트 이미지"}],
            "sources": [{"url": self.source["url"], "checked_at": self.source["verified_at"],
                         "expires_at": self.source["expires_at"]}],
            "review_notes": ["외부 API를 호출하지 않는 자동화 검증"],
        }

    def result_for(self, claim):
        stage = claim["job"]["stage"]
        number = claim["cycle"]["number"]
        results = {
            "sources": {"source_ids": [self.source["id"]]},
            "planning": {"title": "가상 일상 %s" % number, "topic_key": "fixture-topic-%s" % number,
                         "source_ids": [self.source["id"]]},
            "storyboard": {"cards": [{"scene": "목동 집의 아침"}]},
            "copy": {"caption": module.DISCLOSURE, "hashtags": ["#가상인플루언서"]},
            "images": {"media": ["fixture.png"]},
            "quality": {"passed": True},
        }
        if stage == "register":
            imported = self.store.ingest(self.payload(claim))
            return {"content_id": imported["id"], "version": imported["version"]}
        return results[stage]

    def complete(self, claim, result=None, **kwargs):
        return self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"],
                                          result if result is not None else self.result_for(claim), **kwargs)

    def finish_cycle(self):
        cycle_id = None
        for stage in STAGES:
            claim = self.claim(stage)
            if cycle_id is None:
                cycle_id = claim["cycle"]["id"]
            self.assertEqual(cycle_id, claim["cycle"]["id"])
            self.complete(claim)
        return cycle_id

    def test_double_start_reuses_one_live_run_across_store_instances(self):
        first = self.store.start_run({})
        second = Store(self.root).start_run({})
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["id"], self.store.automation_state()["run"]["id"])

    def test_concurrent_start_and_claim_create_only_one_running_stage(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            runs = list(pool.map(lambda _: self.store.start_run({}), range(4)))
        self.assertEqual(1, len({run["id"] for run in runs}))
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda index: self.store.worker_next("worker-%s" % index), range(4)))
        active = [claim for claim in claims if claim["should_work"]]
        self.assertEqual(1, len(active))
        self.assertEqual(1, active[0]["job"]["attempts"])

    def test_continuous_generation_exceeds_ten_and_leaves_approval_to_human(self):
        self.store.start_run({})
        cycle_ids = {self.finish_cycle() for _ in range(11)}
        self.assertEqual(11, len(cycle_ids))
        contents = self.store.state()["contents"]
        self.assertEqual(11, len(contents))
        self.assertTrue(all(content["status"] == "ready" for content in contents))
        self.assertTrue(all(content["publication"] is None for content in contents))
        self.assertIsNone(self.store.claim_publication("fixture_account"))
        next_claim = self.claim("sources")
        self.assertEqual(12, next_claim["cycle"]["number"])

    def test_pause_retains_inflight_completion_and_resumes_same_cycle(self):
        run = self.store.start_run({})
        first = self.claim("sources")
        self.store.control_run(run["id"], "pause")
        self.complete(first)
        self.store = Store(self.root)
        self.assertFalse(self.store.worker_next("fixture-worker")["should_work"])
        self.store.control_run(run["id"], "resume")
        resumed = self.claim("planning")
        self.assertEqual(first["cycle"]["id"], resumed["cycle"]["id"])
        self.assertEqual([self.source["id"]], resumed["cycle"]["result"]["sources"]["source_ids"])

    def test_stop_prevents_further_stage_claims_after_inflight_result(self):
        run = self.store.start_run({})
        current = self.claim("sources")
        self.store.control_run(run["id"], "stop")
        self.complete(current)
        self.assertFalse(Store(self.root).worker_next("fixture-worker")["should_work"])

    def test_stopped_quality_cannot_invalidate_saved_results_with_late_repair(self):
        run = self.store.start_run({"end_at": None})
        for stage in STAGES[:5]:
            self.complete(self.claim(stage))
        quality = self.claim("quality")
        self.store.control_run(run["id"], "stop")
        before = self.store.worker_inspect(quality["cycle"]["id"])
        with self.assertRaises(Problem):
            self.store.worker_repair(quality["cycle"]["id"], quality["lease_token"], "images", ["late repair"])
        after = self.store.worker_inspect(quality["cycle"]["id"])
        self.assertEqual(before["cycle"]["result"], after["cycle"]["result"])
        self.assertEqual(before["jobs"], after["jobs"])

    def test_scheduled_run_does_not_start_before_its_window(self):
        start = self.reference_time + timedelta(hours=1)
        self.store.start_run({"start_at": start.isoformat(), "end_at": (start + timedelta(hours=2)).isoformat()})
        self.assertFalse(self.store.worker_next("fixture-worker")["should_work"])
        with self.at_time(start + timedelta(seconds=1)):
            self.claim("sources")

    def test_deadline_blocks_new_work(self):
        end = self.reference_time + timedelta(minutes=2)
        self.store.start_run({"end_at": end.isoformat()})
        current = self.claim("sources")
        self.complete(current)
        with self.at_time(end + timedelta(seconds=1)):
            self.assertFalse(self.store.worker_next("fixture-worker")["should_work"])

    def test_second_worker_cannot_claim_an_inflight_stage(self):
        self.store.start_run({})
        self.claim("sources")
        self.assertFalse(Store(self.root).worker_next("another-worker")["should_work"])

    def test_duplicate_completion_does_not_advance_twice(self):
        self.store.start_run({})
        current = self.claim("sources")
        result = self.result_for(current)
        self.complete(current, result)
        next_stage = self.claim("planning")
        self.complete(current, result)
        self.assertFalse(self.store.worker_next("other-worker")["should_work"])
        self.complete(next_stage)
        after = self.claim("storyboard")
        self.assertEqual(current["cycle"]["id"], after["cycle"]["id"])

    def test_wrong_lease_cannot_complete_or_ping_a_job(self):
        self.store.start_run({})
        current = self.claim("sources")
        with self.assertRaises(Problem):
            self.store.worker_complete(current["cycle"]["id"], "wrong-token", self.result_for(current))
        with self.assertRaises(Problem):
            self.store.worker_ping(current["cycle"]["id"], "wrong-token")
        self.complete(current)
        self.claim("planning")

    def test_late_failure_from_previous_stage_cannot_fail_current_stage(self):
        self.store.start_run({})
        previous = self.claim("sources")
        self.complete(previous)
        current = self.claim("planning")
        with self.assertRaises(Problem):
            self.store.worker_fail(previous["cycle"]["id"], previous["lease_token"], "늦게 도착한 오류")
        self.complete(current)
        self.claim("storyboard")

    def test_registration_requires_actual_content(self):
        self.store.start_run({})
        for stage in STAGES[:-1]:
            self.complete(self.claim(stage))
        registration = self.claim("register")
        with self.assertRaises(Problem):
            self.complete(registration, {"content_id": registration["cycle"]["content_id"], "version": 1})
        self.complete(registration)
        self.assertEqual(1, len(self.store.state()["contents"]))

    def test_external_job_id_is_recorded_before_result_and_survives_restart(self):
        self.store.start_run({})
        for stage in STAGES[:4]:
            self.complete(self.claim(stage))
        images = self.claim("images")
        self.store.worker_ping(images["cycle"]["id"], images["lease_token"],
                               external_job_id="fixture-provider-job")
        self.store = Store(self.root)
        job = next(job for job in self.store.state()["jobs"] if job["id"] == images["job"]["id"])
        self.assertEqual("fixture-provider-job", job["external_job_id"])
        self.complete(images, external_job_id="fixture-provider-job")
        self.claim("quality")
        job = next(job for job in Store(self.root).state()["jobs"] if job["id"] == images["job"]["id"])
        self.assertEqual("fixture-provider-job", job["external_job_id"])

    def test_expired_lease_with_external_job_never_silently_reissues_call(self):
        self.store.start_run({})
        for stage in STAGES[:4]:
            self.complete(self.claim(stage))
        images = self.claim("images")
        self.store.worker_ping(images["cycle"]["id"], images["lease_token"],
                               external_job_id="fixture-provider-pending")
        with self.store.db() as db:
            db.execute("UPDATE production_cycles SET lease_expires_at=? WHERE id=?",
                       ((self.reference_time - timedelta(minutes=1)).isoformat(), images["cycle"]["id"]))
        self.store = Store(self.root)
        self.assertFalse(self.store.worker_next("replacement-worker")["should_work"])
        self.assertFalse(self.store.worker_next("replacement-worker")["should_work"])
        job = next(job for job in self.store.state()["jobs"] if job["id"] == images["job"]["id"])
        self.assertEqual(1, job["attempts"])
        self.assertEqual("fixture-provider-pending", job["external_job_id"])
        self.assertEqual("uncertain", job["status"])

    def test_explicit_uncertain_failure_does_not_retry(self):
        self.store.start_run({})
        claim = self.claim("sources")
        self.store.worker_fail(claim["cycle"]["id"], claim["lease_token"],
                               "외부 결과 확인 필요", retryable=True, uncertain=True)
        for _ in range(3):
            self.assertFalse(Store(self.root).worker_next("replacement-worker")["should_work"])
        job = next(job for job in self.store.state()["jobs"] if job["id"] == claim["job"]["id"])
        self.assertEqual(1, job["attempts"])

    def test_repair_limit_does_not_leave_a_ghost_running_job(self):
        self.store.start_run({})
        for stage in STAGES[:5]:
            self.complete(self.claim(stage))
        first_review = self.claim("quality")
        repaired = self.store.worker_repair(first_review["cycle"]["id"], first_review["lease_token"],
                                            "images", ["첫 이미지 표정 수정"])
        self.assertTrue(repaired["retryable"])
        self.complete(self.claim("images"))
        final_review = self.claim("quality")
        exhausted = self.store.worker_repair(final_review["cycle"]["id"], final_review["lease_token"],
                                             "images", ["재생성 결과도 검수 실패"])
        self.assertFalse(exhausted["retryable"])
        jobs = [job for job in self.store.state()["jobs"] if job["cycle_id"] == final_review["cycle"]["id"]]
        self.assertFalse(any(job["status"] == "running" for job in jobs), jobs)
        next_cycle = self.claim("sources")
        self.assertNotEqual(final_review["cycle"]["id"], next_cycle["cycle"]["id"])

    def test_checkpoint_survives_pause_restart_and_resumes_without_new_attempt(self):
        run = self.store.start_run({})
        for stage in STAGES[:4]:
            self.complete(self.claim(stage))
        images = self.claim("images")
        partial = {"completed_media": ["fixture.png"], "remaining_card_indexes": [1, 2]}
        self.store.control_run(run["id"], "pause")
        self.store.worker_checkpoint(images["cycle"]["id"], images["lease_token"], partial, release=True)
        self.store = Store(self.root)
        self.assertFalse(self.store.worker_next("replacement-worker")["should_work"])
        self.store.control_run(run["id"], "resume")
        resumed = self.claim("images")
        self.assertEqual(images["cycle"]["id"], resumed["cycle"]["id"])
        self.assertEqual(images["job"]["id"], resumed["job"]["id"])
        self.assertEqual(1, resumed["job"]["attempts"])
        self.assertNotEqual(images["lease_token"], resumed["lease_token"])
        job = next(job for job in self.store.state()["jobs"] if job["id"] == images["job"]["id"])
        self.assertEqual(partial, job["result"])
        with self.assertRaises(Problem):
            self.complete(images)
        self.complete(resumed)
        self.claim("quality")

    def test_checkpoint_without_release_keeps_exclusive_lease(self):
        self.store.start_run({})
        current = self.claim("sources")
        partial = {"checked_source_ids": [self.source["id"]]}
        self.store.worker_checkpoint(current["cycle"]["id"], current["lease_token"], partial)
        self.assertFalse(Store(self.root).worker_next("replacement-worker")["should_work"])
        job = next(job for job in self.store.state()["jobs"] if job["id"] == current["job"]["id"])
        self.assertEqual(partial, job["result"])
        self.complete(current)
        self.claim("planning")

    def test_uncertain_checkpoint_cannot_release_and_bypass_reconciliation(self):
        self.store.start_run({})
        for stage in STAGES[:4]:
            self.complete(self.claim(stage))
        images = self.claim("images")
        self.store.worker_fail(images["cycle"]["id"], images["lease_token"],
                               "외부 이미지 작업 결과 불확실", uncertain=True)
        with self.assertRaises(Problem):
            self.store.worker_checkpoint(images["cycle"]["id"], images["lease_token"],
                                         {"remaining_card_indexes": [0]}, release=True)
        self.assertFalse(self.store.worker_next("replacement-worker")["should_work"])

    def test_uncertain_external_result_can_be_recovered_through_worker_inspection(self):
        run = self.store.start_run({})
        for stage in STAGES[:4]:
            self.complete(self.claim(stage))
        images = self.claim("images")
        self.store.worker_ping(images["cycle"]["id"], images["lease_token"],
                               external_job_id="fixture-recoverable-job")
        with self.store.db() as db:
            db.execute("UPDATE production_cycles SET lease_expires_at=? WHERE id=?",
                       ((self.reference_time - timedelta(minutes=1)).isoformat(), images["cycle"]["id"]))
        self.assertFalse(self.store.worker_next("replacement-worker")["should_work"])
        self.store = Store(self.root)
        recovered = self.store.worker_inspect(images["cycle"]["id"])
        self.assertEqual("uncertain", recovered["cycle"]["status"])
        self.assertEqual(images["lease_token"], recovered["cycle"]["lease_token"])
        job = next(job for job in recovered["jobs"] if job["id"] == images["job"]["id"])
        self.assertEqual("fixture-recoverable-job", job["external_job_id"])
        self.store.worker_complete(recovered["cycle"]["id"], recovered["cycle"]["lease_token"],
                                   {"media": ["fixture.png"]}, external_job_id="fixture-recoverable-job")
        self.store.control_run(run["id"], "resume")
        next_stage = self.claim("quality")
        self.assertEqual(images["cycle"]["id"], next_stage["cycle"]["id"])

    def test_retry_limit_persists_after_restart(self):
        self.store.start_run({})
        first = self.claim("sources")
        self.store.worker_fail(first["cycle"]["id"], first["lease_token"], "일시적인 오류", retryable=True)
        self.store = Store(self.root)
        with self.at_time(self.reference_time + timedelta(minutes=10)):
            retry = self.claim("sources")
            self.assertEqual(first["cycle"]["id"], retry["cycle"]["id"])
            self.assertEqual(first["job"]["id"], retry["job"]["id"])
            self.assertNotEqual(first["lease_token"], retry["lease_token"])
            self.store.worker_fail(retry["cycle"]["id"], retry["lease_token"], "반복된 오류", retryable=True)
        self.store = Store(self.root)
        with self.at_time(self.reference_time + timedelta(minutes=20)):
            after = self.store.worker_next("replacement-worker")
        if after["should_work"]:
            self.assertNotEqual(first["job"]["id"], after["job"]["id"])
            self.assertNotEqual(first["cycle"]["id"], after["cycle"]["id"])
        failed_job = next(job for job in self.store.state()["jobs"] if job["id"] == first["job"]["id"])
        self.assertEqual(2, failed_job["attempts"])

    def test_expired_source_cannot_be_used_by_a_cycle(self):
        expired = self.store.upsert_source({
            "affiliate": "GS건설", "title": "만료된 테스트 소재", "url": "https://example.com/expired",
            "verified_at": (self.reference_time - timedelta(days=2)).isoformat(),
            "expires_at": (self.reference_time - timedelta(days=1)).isoformat(),
            "claims": ["만료된 정보"], "visibility": "subtle",
        })
        self.store.start_run({})
        claim = self.claim("sources")
        with self.assertRaises(Problem):
            self.complete(claim, {"source_ids": [expired["id"]]})
        self.complete(claim)
        self.claim("planning")

    def test_planning_cannot_reuse_a_recent_topic(self):
        self.store.start_run({})
        self.finish_cycle()
        self.complete(self.claim("sources"))
        planning = self.claim("planning")
        duplicate_topic = {"title": "제목만 바꾼 같은 이야기", "topic_key": "fixture-topic-1",
                           "source_ids": [self.source["id"]]}
        with self.assertRaises(Problem):
            self.complete(planning, duplicate_topic)
        self.complete(planning)
        self.claim("storyboard")

    def test_stale_registration_version_cannot_be_marked_complete(self):
        self.store.start_run({})
        for stage in STAGES[:-1]:
            self.complete(self.claim(stage))
        registration = self.claim("register")
        imported = self.store.ingest(self.payload(registration))
        self.store.edit(imported["id"], {"base_version": imported["version"], "title": "사람이 수정한 제목"})
        with self.assertRaises(Problem):
            self.complete(registration, {"content_id": imported["id"], "version": imported["version"]})
        content = self.store.state()["contents"][0]
        self.assertEqual("사람이 수정한 제목", content["payload"]["title"])
        self.assertEqual("ready", content["status"])

    def test_logs_are_ordered_incremental_and_persist_after_restart(self):
        run = self.store.start_run({})
        self.complete(self.claim("sources"))
        self.store.control_run(run["id"], "pause")
        before = self.store.logs(run_id=run["id"], limit=100)
        self.assertGreaterEqual(len(before), 3)
        ids = [entry["id"] for entry in before]
        self.assertEqual(sorted(set(ids)), ids)
        restarted = Store(self.root)
        self.assertEqual(before, restarted.logs(run_id=run["id"], limit=100))
        cursor = ids[len(ids) // 2]
        expected = [entry for entry in before if entry["id"] > cursor]
        self.assertEqual(expected, restarted.logs(run_id=run["id"], after_id=cursor, limit=100))
        self.assertEqual(before[:2], restarted.logs(run_id=run["id"], limit=2))


if __name__ == "__main__":
    unittest.main()
