"""Segmind contract, persistence and approval tests. All external I/O is faked."""
import copy
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("boca_video_server", ROOT / "apps/backend/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
from segmind_video import ProviderError, SegmindClient, output_url, public_url


class Provider:
    def __init__(self):
        self.submissions = []
        self.downloads = 0
        self.polls = 0
        self.fail_submit = False
        self.fail_poll = False
        self.fail_download = False
        self.state = "COMPLETED"

    def upload(self, paths):
        return ["https://images.segmind.com/test/" + p.name for p in paths]

    def submit(self, payload):
        self.submissions.append(payload)
        if self.fail_submit:
            raise ProviderError("응답 유실")
        return "external-123"

    def status(self, request_id):
        self.polls += 1
        if self.fail_poll:
            raise ProviderError("일시적 조회 실패", 503)
        return {"status": self.state}

    def result(self, request_id):
        return {"status": "COMPLETED", "output": {"video": {"url": "https://images.segmind.com/result.mp4"}},
                "metrics": {"cost": 7.17, "remaining_credits": 42.83}}

    def download(self, url, path):
        self.downloads += 1
        if self.fail_download:
            raise ProviderError("다운로드 실패")
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"sample")


class VideoTests(unittest.TestCase):
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
        self.store = server.Store(self.root)
        self.key = "test-key-not-real-12345"
        with patch("segmind_video.SegmindClient.verify", return_value=True):
            self.store.connect_video({"api_key": self.key})
        (self.root / "image.png").write_bytes(b"fixture-image")
        p = self.store.persona()
        self.source = {"id": "source", "title": "퇴근 후 일상", "topic_key": "evening",
                       "caption": "창작 일상. " + server.DISCLOSURE, "persona_id": p["id"], "persona_version": p["version"],
                       "cards": [{"media": "image.png", "alt": "집에 들어오는 가상 인물"}]}
        self.store.ingest(self.source)
        self.body = {"request_key": "request-123", "accept_estimated_cost": True, "persona_id": p["id"],
                     "persona_version": p["version"], "source_content_id": "source", "source_version": 1,
                     "title": "30초 일상", "caption": "작은 취향의 발견", "storyboard": "0–15초: 현관. 15–30초: 창가에서 쉬는 모습.",
                     "duration": 30, "resolution": "720p"}

    def tearDown(self):
        self.tmp.cleanup()

    def enqueue(self, **changes):
        body = dict(self.body, **changes)
        return self.store.create_video(body)

    def retry_now(self, job_id):
        # Advance the persisted retry clock without contacting a real provider.
        with self.store.db() as db:
            db.execute("UPDATE video_jobs SET next_retry_at=? WHERE id=?",
                       ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), job_id))

    def bind_portrait(self):
        profile = self.store.persona()
        profile.update(display_name="검증용 페르소나", age_description="30대 중반",
                       appearance={"makeup": "연한 피치 핑크와 내추럴 메이크업"})
        updated = self.store.update_persona(profile["id"], {"base_version": profile["version"], "profile": profile})
        (self.root / "portrait.png").write_bytes(b"fixed-persona-portrait-fixture")
        registered = self.store.save_persona_references(profile["id"], {
            "version": updated["version"], "mother": "portrait.png"})
        self.body["persona_version"] = updated["version"]
        return registered["references"]["mother"]

    def test_registered_identity_is_first_even_with_upload_and_survives_profile_change(self):
        portrait = self.bind_portrait()
        raw = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6b5sAAAAASUVORK5CYII=")
        uploaded = self.store.upload_video_reference({"data": base64.b64encode(raw).decode()})
        job = self.enqueue(reference_media=uploaded["media"])
        self.assertEqual(portrait["sha256"], job["input"]["identity_reference"]["sha256"])
        self.assertEqual(2, job["input"]["identity_reference"]["persona_version"])
        self.assertEqual([portrait["media"], uploaded["media"]], [c["media"] for c in job["input"]["cards"][:2]])

        profile = self.store.persona()
        profile["appearance"] = {"makeup": "다음 버전의 별도 메이크업"}
        updated = self.store.update_persona(profile["id"], {"base_version": 2, "profile": profile})
        (self.root / "later.png").write_bytes(b"later-identity-fixture")
        self.store.save_persona_references(profile["id"], {"version": updated["version"], "mother": "later.png"})
        client = Provider()
        server.Store(self.root).process_video(job["id"], client)
        request = client.submissions[0]
        self.assertEqual("https://images.segmind.com/test/" + portrait["media"], request["reference_images"][0])
        self.assertIn("@Image 1 is the fixed identity reference", request["prompt"])
        self.assertIn("30대 중반", request["prompt"])
        self.assertIn("연한 피치 핑크와 내추럴 메이크업", request["prompt"])
        self.assertNotIn("다음 버전의 별도 메이크업", request["prompt"])

    def test_registered_identity_cannot_be_omitted_by_text_only(self):
        self.bind_portrait()
        with self.assertRaisesRegex(server.Problem, "반드시"):
            self.enqueue(source_content_id=None, text_only=True)
        self.assertEqual([], self.store.video_state()["jobs"])

    def test_uploading_same_portrait_does_not_duplicate_reference(self):
        portrait = self.bind_portrait()
        job = self.enqueue(source_content_id=None, reference_media=portrait["media"])
        self.assertEqual([portrait["media"]], [c["media"] for c in job["input"]["cards"]])
        client = Provider()
        self.store.process_video(job["id"], client)
        self.assertEqual(["https://images.segmind.com/test/" + portrait["media"]], client.submissions[0]["reference_images"])

    def test_key_stays_server_side_and_has_private_permissions(self):
        self.assertEqual(0o600, (self.root / ".runtime/segmind-api-key").stat().st_mode & 0o777)
        self.assertTrue(self.store.video_connection()["verified"])
        self.assertNotIn(self.key, json.dumps(self.store.state()))
        self.assertNotIn(self.key, json.dumps(self.store.video_state()))
        (self.root / ".runtime/segmind-api-key").write_text("different-key")
        self.assertFalse(self.store.video_connection()["verified"])

    def test_invalid_key_does_not_replace_good_key(self):
        with patch("segmind_video.SegmindClient.verify", side_effect=ProviderError("인증 실패", 401)):
            with self.assertRaises(server.Problem):
                self.store.connect_video({"api_key": "invalid-key"})
        self.assertEqual(self.key, self.store._video_key())

    def test_unverified_and_unconfirmed_requests_cannot_generate(self):
        with self.assertRaises(server.Problem):
            self.enqueue(accept_estimated_cost=False)
        (self.root / ".runtime/segmind-api-key").unlink()
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(server.Problem):
            self.enqueue()

    def test_click_retries_and_parallel_requests_create_one_job(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.enqueue(), range(4)))
        self.assertEqual(1, len({r["id"] for r in results}))
        restarted = server.Store(self.root)
        self.assertEqual(results[0]["id"], restarted.create_video(self.body)["id"])
        with self.assertRaises(server.Problem):
            self.enqueue(title="요청 키 재사용 금지")

    def test_submission_contract_and_import_into_review(self):
        job = self.enqueue()
        client = Provider()
        self.store.process_video(job["id"], client)
        self.assertEqual("external-123", self.store.video_job(job["id"])["external_id"])
        request = client.submissions[0]
        self.assertEqual((30, "720p", "9:16", False), (request["duration"], request["resolution"], request["aspect_ratio"], request["skip_moderation"]))
        self.assertTrue(request["reference_images"])
        server.Store(self.root).process_video(job["id"], client)
        result = self.store.video_job(job["id"])
        self.assertEqual("completed", result["status"])
        contents = {c["id"]: c for c in self.store.state()["contents"]}
        video = contents[job["id"]]
        self.assertEqual("ready", video["status"])
        self.assertIn(server.DISCLOSURE, video["payload"]["caption"])
        self.assertTrue(video["payload"]["cards"][0]["media"].endswith(".mp4"))
        self.assertEqual(7.17, result["result"]["metrics"]["cost"])
        self.store.process_video(job["id"], client)
        self.assertEqual(1, len(client.submissions))
        self.assertEqual(1, client.downloads)

    def test_late_result_preserves_human_source_edit_and_approval(self):
        job = self.enqueue()
        client = Provider()
        self.store.process_video(job["id"], client)
        self.store.edit("source", {"base_version": 1, "title": "사람의 새 제목"})
        self.store.decide("source", 2, True)
        self.store.process_video(job["id"], client)
        source = next(c for c in self.store.state()["contents"] if c["id"] == "source")
        self.assertEqual("사람의 새 제목", source["payload"]["title"])
        self.assertEqual("approved", source["status"])
        self.store.decide(job["id"], 1, True)
        video = self.store.edit(job["id"], {"base_version": 1, "title": "영상 문안 수정"})
        self.assertEqual("ready", video["status"])
        self.assertEqual("superseded", video["publication"]["status"])

    def test_lost_submit_response_never_resubmits(self):
        job = self.enqueue()
        client = Provider()
        client.fail_submit = True
        self.store.process_video(job["id"], client)
        self.assertEqual("uncertain", self.store.video_job(job["id"])["status"])
        restarted = server.Store(self.root)
        restarted.process_video(job["id"], client)
        self.assertEqual(1, len(client.submissions))
        with self.assertRaises(server.Problem):
            restarted.resume_video(job["id"], {})
        restarted.resume_video(job["id"], {"external_id": "external-123"})
        restarted.process_video(job["id"], client)
        self.assertEqual("completed", restarted.video_job(job["id"])["status"])
        self.assertEqual(1, len(client.submissions))

    def test_poll_errors_are_bounded_and_resume_is_read_only(self):
        job, client = self.enqueue(), Provider()
        self.store.process_video(job["id"], client)
        client.fail_poll = True
        for _ in range(8):
            self.retry_now(job["id"])
            self.store.process_video(job["id"], client)
        self.assertEqual(5, client.polls)
        self.assertEqual("attention", self.store.video_job(job["id"])["status"])
        client.fail_poll = False
        self.store.resume_video(job["id"], {})
        self.store.process_video(job["id"], client)
        self.assertEqual("completed", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, len(client.submissions))

    def test_download_recovery_uses_saved_result(self):
        job, client = self.enqueue(), Provider()
        self.store.process_video(job["id"], client)
        client.fail_download = True
        self.store.process_video(job["id"], client)
        self.assertEqual("downloading", self.store.video_job(job["id"])["status"])
        client.fail_download = False
        self.retry_now(job["id"])
        server.Store(self.root).process_video(job["id"], client)
        self.assertEqual("completed", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, client.polls)

    def test_retry_backoff_survives_restart_and_does_not_poll_early(self):
        job, client = self.enqueue(), Provider()
        self.store.process_video(job["id"], client)
        client.fail_poll = True
        delays = []
        for attempt in range(1, 5):
            self.retry_now(job["id"])
            self.store.process_video(job["id"], client)
            saved = self.store.video_job(job["id"])
            self.assertEqual(attempt, saved["poll_errors"])
            delays.append(round((datetime.fromisoformat(saved["next_retry_at"]) - datetime.fromisoformat(saved["updated_at"])).total_seconds()))
            server.Store(self.root).process_video(job["id"], client)
            self.assertEqual(attempt, client.polls)
        self.assertEqual([10, 20, 40, 80], delays)
        self.assertEqual(1, len(client.submissions))

    def test_download_attention_resume_uses_saved_url_without_expired_status(self):
        job, client = self.enqueue(), Provider()
        self.store.process_video(job["id"], client)
        client.fail_download = True
        for _ in range(5):
            self.retry_now(job["id"])
            self.store.process_video(job["id"], client)
        self.assertEqual("attention", self.store.video_job(job["id"])["status"])
        self.assertFalse((self.store.runtime / "video-results" / (job["id"] + ".part")).exists())
        client.fail_download = False
        resumed = self.store.resume_video(job["id"], {})
        self.assertEqual("downloading", resumed["status"])
        with patch.object(client, "status", side_effect=AssertionError("provider result expired")), patch.object(client, "result", side_effect=AssertionError("do not requery")):
            server.Store(self.root).process_video(job["id"], client)
        self.assertEqual("completed", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, len(client.submissions))

    def test_expired_download_url_refresh_is_bounded_without_resubmission(self):
        job, client = self.enqueue(), Provider()
        self.store.process_video(job["id"], client)
        with patch.object(client, "download", side_effect=ProviderError("expired CDN URL", 403)):
            for _ in range(5):
                self.retry_now(job["id"])
                self.store.process_video(job["id"], client)
        saved = self.store.video_job(job["id"])
        self.assertEqual(("attention", 5), (saved["status"], saved["poll_errors"]))
        self.assertEqual(5, client.polls)
        self.assertEqual(1, len(client.submissions))

    def test_resume_starts_new_bounded_observation_window(self):
        job, client = self.enqueue(), Provider()
        self.store.process_video(job["id"], client)
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with self.store.db() as db:
            db.execute("UPDATE video_jobs SET poll_started_at=?,created_at=? WHERE id=?", (old, old, job["id"]))
        client.state = "PROCESSING"
        self.store.process_video(job["id"], client)
        self.assertEqual("attention", self.store.video_job(job["id"])["status"])
        self.store.resume_video(job["id"], {})
        self.store.process_video(job["id"], client)
        self.assertEqual("running", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, len(client.submissions))

    def test_upload_transient_failure_retries_before_any_paid_submission(self):
        job, client = self.enqueue(), Provider()
        with patch.object(client, "upload", side_effect=ProviderError("upload unavailable", 503)):
            self.store.process_video(job["id"], client)
        self.assertEqual([], client.submissions)
        self.assertEqual("queued", self.store.video_job(job["id"])["status"])
        self.retry_now(job["id"])
        self.store.process_video(job["id"], client)
        self.store.process_video(job["id"], client)
        self.assertEqual("completed", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, len(client.submissions))

    def test_truncated_mp4_download_is_not_accepted(self):
        response = io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"truncated")
        response.headers = {"Content-Length": "1000"}
        with patch("segmind_video.public_url", side_effect=lambda url: url), patch("segmind_video.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ProviderError, "일부만"):
                SegmindClient("fake-key").download("https://example.com/result.mp4", self.root / "video.part")

    def test_standby_video_worker_takes_over_when_original_server_exits(self):
        self.enqueue()
        other = server.Store(self.root)
        first_seen, second_seen = threading.Event(), threading.Event()
        workers = []
        with patch.object(self.store, "process_video", side_effect=lambda *args: first_seen.set()), patch.object(other, "process_video", side_effect=lambda *args: second_seen.set()):
            try:
                workers.append(self.store.start_video_worker())
                self.assertTrue(first_seen.wait(3))
                workers.append(other.start_video_worker())
                self.assertFalse(second_seen.wait(.15))
                workers[0][0].set()
                workers[0][1].join(3)
                self.assertTrue(second_seen.wait(3))
            finally:
                for stop, thread in workers:
                    stop.set()
                for stop, thread in workers:
                    thread.join(3)

    def test_failed_generation_does_not_register_or_retry(self):
        job, client = self.enqueue(), Provider()
        self.store.process_video(job["id"], client)
        client.state = "FAILED"
        self.store.process_video(job["id"], client)
        self.assertEqual("failed", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, len(self.store.state()["contents"]))

    def test_queue_and_daily_budget_limits(self):
        one = self.enqueue()
        two = self.enqueue(request_key="request-456")
        with self.assertRaises(server.Problem):
            self.enqueue(request_key="request-789")
        self.store._video_update(one["id"], status="failed")
        self.store._video_update(two["id"], status="failed")
        with self.assertRaises(server.Problem):
            self.enqueue(request_key="request-789")

    def test_stale_source_and_persona_versions_rejected(self):
        with self.assertRaises(server.Problem):
            self.enqueue(source_version=2)
        with self.assertRaises(server.Problem):
            self.enqueue(persona_version=99)

    def test_no_reference_or_mutated_reference_rejected(self):
        with self.assertRaises(server.Problem):
            self.enqueue(source_content_id=None)
        job = self.enqueue()
        (self.store.media / job["input"]["cards"][0]["media"]).write_bytes(b"changed")
        client = Provider()
        self.store.process_video(job["id"], client)
        self.assertEqual("failed", self.store.video_job(job["id"])["status"])
        self.assertFalse(client.submissions)

    def test_text_only_requires_explicit_choice_and_skips_upload(self):
        job = self.enqueue(source_content_id=None, text_only=True)
        client = Provider()
        with patch.object(client, "upload", side_effect=AssertionError("no reference upload")):
            self.store.process_video(job["id"], client)
        self.assertNotIn("reference_images", client.submissions[0])
        self.assertNotIn("@Image", client.submissions[0]["prompt"])
        self.store.process_video(job["id"], client)
        self.assertEqual("completed", self.store.video_job(job["id"])["status"])
        content = next(c for c in self.store.state()["contents"] if c["id"] == job["id"])
        self.assertTrue(any("기준 이미지 없이" in n for n in content["payload"]["review_notes"]))
        empty = dict(self.source, cards=[])
        with self.assertRaises(server.Problem):
            self.store._validate(empty)
        with self.assertRaises(server.Problem):
            self.enqueue(request_key="not-bool-123", source_content_id=None, text_only="true")

    def test_uploaded_reference_is_local_immutable_and_usable(self):
        raw = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6b5sAAAAASUVORK5CYII=")
        result = self.store.upload_video_reference({"data": base64.b64encode(raw).decode()})
        self.assertEqual(hashlib.sha256(raw).hexdigest() + ".png", result["media"])
        self.assertEqual(raw, (self.store.media / result["media"]).read_bytes())
        self.assertEqual([], self.store.video_state()["jobs"])
        job = self.enqueue(source_content_id=None, reference_media=result["media"])
        client = Provider()
        self.store.process_video(job["id"], client)
        self.assertTrue(client.submissions[0]["reference_images"])
        for encoded in ("bad data", base64.b64encode(b"not an image").decode()):
            with self.assertRaises(server.Problem):
                self.store.upload_video_reference({"data": encoded})
        for media in ("../image.png", "0" * 64 + ".png"):
            with self.assertRaises(server.Problem):
                self.enqueue(request_key="invalid-ref-123", source_content_id=None, reference_media=media)

    def test_output_contract_shapes_and_private_urls(self):
        url = "https://images.segmind.com/test.mp4"
        for output in (url, [url], {"url": url}, {"video_url": url}, {"video": {"url": url}}):
            self.assertEqual(url, output_url({"output": output}))
        for url in ("file:///etc/passwd", "http://localhost/test", "https://127.0.0.1/test", "https://user:secret@example.com/test"):
            with self.assertRaises(ProviderError):
                public_url(url)

    def test_guides_persist_and_jobs_freeze_exact_prompt_before_updates(self):
        guide = self.store.save_video_guide({"filename": "일상.md", "content": "# 촬영\n손떨림과 생활 소음", "base_version": 0})
        self.assertTrue(guide["enabled"])
        self.assertEqual(guide, server.Store(self.root).video_state()["guides"][0])
        job = self.enqueue(guide_versions={guide["id"]: guide["version"]})
        original_prompt = job["input"]["generation_prompt"]
        self.assertIn("손떨림과 생활 소음", original_prompt)
        updated = self.store.save_video_guide({"filename": "일상.md", "content": "바뀐 연출", "base_version": 1})
        self.assertEqual(guide["id"], updated["id"])
        self.assertEqual(2, updated["version"])
        self.assertEqual(job["id"], self.enqueue(guide_versions={guide["id"]: 1})["id"])
        self.store.change_video_guide(guide["id"], {"base_version": 2}, delete=True)
        restarted, client = server.Store(self.root), Provider()
        restarted.process_video(job["id"], client)
        self.assertEqual(original_prompt, client.submissions[0]["prompt"])
        restarted.process_video(job["id"], client)
        video = next(c for c in restarted.state()["contents"] if c["id"] == job["id"])
        self.assertEqual([guide], video["payload"]["video_guides"])

    def test_low_influence_policy_is_in_actual_provider_prompt(self):
        self.store.save_video_guide({"filename": "example.md", "content": "Always start with coffee, then use exactly five kitchen shots.", "base_version": 0})
        job = self.enqueue()
        policy = job["input"]["guide_policy"]
        self.assertEqual(("low", 2), (policy["influence"], policy["max_optional_cues"]))
        client = Provider()
        self.store.process_video(job["id"], client)
        prompt = client.submissions[0]["prompt"]
        self.assertLess(prompt.index(self.body["storyboard"]), prompt.index("Always start with coffee"))
        self.assertIn("at most two", prompt)
        self.assertIn("or none when unsuitable", prompt)
        self.assertIn("even when they say must or always", prompt)
        self.assertIn(policy["instructions"], prompt)
        self.assertEqual(self.body["storyboard"], job["input"]["storyboard"])
        self.assertEqual(policy, server.Store(self.root).video_job(job["id"])["input"]["guide_policy"])

    def test_legacy_cycle_guides_schema_migration_preserves_records(self):
        with self.store.db() as db:
            db.execute("DROP TABLE production_cycle_video_guides")
            db.execute("CREATE TABLE production_cycle_video_guides (cycle_id TEXT PRIMARY KEY,guides_json TEXT NOT NULL)")
            db.execute("INSERT INTO production_cycle_video_guides VALUES ('legacy','[]')")
        restarted = server.Store(self.root)
        with restarted.db() as db:
            self.assertEqual([], restarted.cycle_video_guides(db, "legacy", "mixed"))
            self.assertEqual("low", restarted.cycle_video_guide_policy(db, "legacy")["influence"])

    def test_disabled_guides_excluded_and_stale_changes_rejected(self):
        guide = self.store.save_video_guide({"filename": "style.md", "content": "soft light", "base_version": 0})
        with self.assertRaises(server.Problem):
            self.enqueue(guide_versions={})
        disabled = self.store.change_video_guide(guide["id"], {"base_version": 1, "enabled": False})
        job = self.enqueue(guide_versions={})
        self.assertEqual([], job["input"]["guides"])
        self.assertNotIn("soft light", job["input"]["generation_prompt"])
        with self.assertRaises(server.Problem):
            self.store.change_video_guide(guide["id"], {"base_version": 1, "enabled": True})
        with self.assertRaises(server.Problem):
            self.store.save_video_guide({"filename": "style.md", "content": "stale edit", "base_version": 1})
        self.assertEqual(disabled, self.store.video_state()["guides"][0])

    def test_guide_validation_limits_and_concurrent_replacement(self):
        for name, content in [("../style.md", "a"), ("a.html", "a"), ("a.md", "  "), ("a.md", "a" * 12001), ("a.md", "\x00"), ("a.md", "\ud800")]:
            with self.subTest(name=name, size=len(content)), self.assertRaises(server.Problem):
                self.store.save_video_guide({"filename": name, "content": content, "base_version": 0})
        guide = self.store.save_video_guide({"filename": "first.md", "content": "a" * 11999, "base_version": 0})
        with self.assertRaises(server.Problem):
            self.store.save_video_guide({"filename": "second.md", "content": "more", "base_version": 0})
        disabled = self.store.change_video_guide(guide["id"], {"base_version": 1, "enabled": False})
        self.store.save_video_guide({"filename": "second.md", "content": "more", "base_version": 0})
        with self.assertRaises(server.Problem):
            self.store.change_video_guide(guide["id"], {"base_version": disabled["version"], "enabled": True})
        def update(_):
            try:
                self.store.save_video_guide({"filename": "second.md", "content": "new", "base_version": 1})
                return True
            except server.Problem:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(1, sum(pool.map(update, range(2))))
        self.assertEqual([], self.store.video_state()["jobs"])

    def test_http_video_routes_auth_and_playback_ranges(self):
        shutil.copytree(ROOT / "apps/dashboard", self.root / "apps/dashboard")
        handler = server.handler(self.store)
        handler.log_message = lambda *args: None
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(httpd.server_port)
        try:
            with urlopen(base + "/api/video") as response:
                data = response.read().decode()
                self.assertNotIn(self.key, data)
                self.assertTrue(json.loads(data)["connection"]["verified"])
            with urlopen(base + "/video") as response:
                self.assertIn(b"video-form", response.read())
            guide_body = {"filename": "reference.md", "content": "# Sound\nRoom tone.", "base_version": 0}
            guide_req = Request(base + "/api/video/guides", data=json.dumps(guide_body).encode(), headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as exc:
                urlopen(guide_req)
            self.assertEqual(403, exc.exception.code)
            guide_req.add_header("X-BOCA-Token", self.store.token)
            with urlopen(guide_req) as response:
                guide = json.load(response)
                self.assertTrue(guide["enabled"])
            with urlopen(base + "/api/video") as response:
                self.assertEqual([guide], json.load(response)["guides"])
            req = Request(base + "/api/video/jobs", data=json.dumps(self.body).encode(), headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as exc:
                urlopen(req)
            self.assertEqual(403, exc.exception.code)
            req.add_header("X-BOCA-Token", self.store.token)
            with urlopen(req) as response:
                self.assertEqual("queued", json.load(response)["status"])
            req.add_header("Origin", "https://example.com")
            with self.assertRaises(HTTPError) as exc:
                urlopen(req)
            self.assertEqual(403, exc.exception.code)
            name = "a" * 64 + ".mp4"
            (self.store.media / name).write_bytes(b"0123456789")
            req = Request(base + "/media/" + name, headers={"Range": "bytes=2-5"})
            with urlopen(req) as response:
                self.assertEqual(206, response.status)
                self.assertEqual("bytes 2-5/10", response.headers["Content-Range"])
                self.assertEqual(b"2345", response.read())
            req = Request(base + "/media/" + name, headers={"Range": "bytes=99-"})
            with self.assertRaises(HTTPError) as exc:
                urlopen(req)
            self.assertEqual(416, exc.exception.code)
        finally:
            httpd.shutdown()
            thread.join()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
