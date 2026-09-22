"""Persistent video history and safe playback, using only temporary local data."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("boca_video_library_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem
from test_video import Provider


class VideoLibraryTests(unittest.TestCase):
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
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir()
        shutil.copytree(ROOT / "config", self.root / "config")
        self.store = Store(self.root)
        self.persona = self.store.persona()
        self.output = self.root / "output/fixture"
        self.output.mkdir(parents=True)
        self.video_bytes = b"0123456789-video-library-fixture"
        self.video = self.output / "completed.mp4"
        self.video.write_bytes(self.video_bytes)

    def tearDown(self):
        self.tmp.cleanup()

    def relative(self, path):
        return str(path.relative_to(self.root))

    def add_job(self, number=1, status="queued", result=None, production=None):
        job_id = "video-fixture-%03d" % number
        snapshot = {
            "id": job_id, "title": "영상 이력 %d" % number,
            "caption": "제작 당시 문안. " + module.DISCLOSURE,
            "storyboard": "0–15초: 창가. 15–30초: 현관.",
            "persona_id": self.persona["id"], "persona_version": self.persona["version"],
            "duration": 30, "resolution": "720p", "cards": [], "sources": [],
        }
        if production:
            snapshot["production"] = production
        timestamp = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=number)).isoformat()
        with self.store.db() as db:
            db.execute("""INSERT INTO video_jobs
                (id,request_key,input_hash,status,input_json,external_id,result_json,error,
                 poll_errors,estimated_cost,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (job_id, "library-request-%03d" % number, "fixture-hash-%d" % number,
                        status, json.dumps(snapshot), "external-%d" % number,
                        json.dumps(result) if result is not None else None, None,
                        0, 7.17, timestamp, timestamp))
        return job_id

    def item(self, job_id):
        return next(item for item in self.store.video_library()["items"] if item["job_id"] == job_id)

    def database_snapshot(self):
        with sqlite3.connect(str(self.store.db_path)) as db:
            return tuple(db.iterdump())

    def ingest_video(self, content_id="imported-fixture", path=None):
        return self.store.ingest({
            "id": content_id, "title": "이전에 등록된 영상", "topic_key": content_id,
            "persona_id": self.persona["id"], "persona_version": self.persona["version"],
            "caption": "등록한 영상 문안. " + module.DISCLOSURE, "sources": [],
            "cards": [{"media": self.relative(path or self.video), "alt": "저장된 일상 영상"}],
        })

    @contextmanager
    def http(self):
        handler = module.handler(self.store)
        handler.log_message = lambda *args: None
        server = module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield "http://127.0.0.1:" + str(server.server_port)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_history_over_fifty_jobs_survives_restart_and_reads_do_not_mutate(self):
        expected = {self.add_job(number, status="failed") for number in range(1, 56)}
        self.store = Store(self.root)
        before = self.database_snapshot()
        library = self.store.video_library()
        self.assertEqual(55, library["total"])
        self.assertEqual(expected, {item["job_id"] for item in library["items"]})
        self.assertEqual(55, len(self.store.video_library()["items"]))
        self.assertEqual(before, self.database_snapshot())

    def test_live_job_phase_is_reflected_without_advancing_or_resubmitting(self):
        job_id = self.add_job()
        phases = ("queued", "preparing", "submitting", "running", "downloading", "attention", "uncertain", "failed", "cancelled")
        with patch.object(self.store, "process_video", side_effect=AssertionError("read must not process video")):
            for phase in phases:
                with self.subTest(phase=phase):
                    with self.store.db() as db:
                        db.execute("UPDATE video_jobs SET status=?,error=? WHERE id=?",
                                   (phase, "검토가 필요한 상태" if phase == "attention" else None, job_id))
                    before = self.database_snapshot()
                    item = self.item(job_id)
                    self.assertEqual(phase, item["status"])
                    self.assertEqual("external-1", item["external_id"])
                    self.assertEqual(30, item["duration_requested"])
                    self.assertEqual("720p", item["resolution"])
                    self.assertFalse(item["media_available"])
                    self.assertIsNone(item["media_url"])
                    if phase == "attention":
                        self.assertEqual("검토가 필요한 상태", item["error"])
                    self.assertEqual(before, self.database_snapshot())

    def test_completed_automatic_video_is_playable_before_content_registration(self):
        job_id = self.add_job(status="completed", result={"media_path": self.relative(self.video), "metrics": {"cost": 7.17}},
                              production={"run_id": "run-fixture", "cycle_id": "cycle-fixture", "content_id": "not-registered"})
        before = self.database_snapshot()
        item = self.item(job_id)
        self.assertEqual("completed", item["status"])
        self.assertTrue(item["media_available"])
        self.assertEqual("/api/video/jobs/%s/media" % job_id, item["media_url"])
        self.assertEqual(self.video.resolve(), Path(self.store.video_job_media_file(job_id)).resolve())
        self.assertEqual(7.17, item["metrics"]["cost"])
        with sqlite3.connect(str(self.store.db_path)) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM contents").fetchone()[0])
        self.assertEqual(before, self.database_snapshot())

    def test_manual_job_keeps_recorded_revision_caption_and_video_after_edit(self):
        with patch("segmind_video.SegmindClient.verify", return_value=True):
            self.store.connect_video({"api_key": "fixture-video-library-key-only"})
        image = self.output / "reference.png"
        image.write_bytes(b"fixture-reference-image")
        self.store.ingest({"id": "source-fixture", "title": "참고 이미지", "topic_key": "source-fixture",
                           "persona_id": self.persona["id"], "persona_version": self.persona["version"],
                           "caption": module.DISCLOSURE,
                           "cards": [{"media": self.relative(image), "alt": "가상 인물 참고"}]})
        job = self.store.create_video({
            "request_key": "library-manual-request", "accept_estimated_cost": True,
            "persona_id": self.persona["id"], "persona_version": self.persona["version"],
            "source_content_id": "source-fixture", "source_version": 1,
            "title": "처음 제작한 영상 제목", "caption": "처음 제작한 영상 문안",
            "storyboard": "0–15초: 창가. 15–30초: 현관.", "duration": 30, "resolution": "720p",
        })
        provider = Provider()
        self.store.process_video(job["id"], provider)
        self.store.process_video(job["id"], provider)
        first = self.item(job["id"])
        first_bytes = Path(self.store.video_job_media_file(job["id"])).read_bytes()
        changed_caption = "검수자가 다음 버전에서 수정한 문안. " + module.DISCLOSURE
        self.store.edit(job["id"], {"base_version": 1, "title": "다음 버전 제목", "caption": changed_caption})
        before = self.database_snapshot()
        item = self.item(job["id"])
        self.assertEqual(1, item["content_version"])
        self.assertEqual(2, item["current_content_version"])
        self.assertEqual(job["id"], item["content_id"])
        self.assertEqual("처음 제작한 영상 제목", item["title"])
        self.assertEqual(first["caption"], item["caption"])
        self.assertNotEqual(changed_caption, item["caption"])
        self.assertEqual("ready", item["content_status"])
        self.assertEqual(first_bytes, Path(self.store.video_job_media_file(job["id"])).read_bytes())
        self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), item["media_sha256"])
        self.assertEqual(first["media_sha256"], item["media_sha256"])
        self.assertEqual(1, len([row for row in self.store.video_library()["items"] if row["content_id"] == job["id"]]))
        self.assertEqual(1, len(provider.submissions))
        self.assertEqual(before, self.database_snapshot())

    def test_imported_videos_have_fallback_rows_without_duplicate_revision_media(self):
        self.ingest_video()
        first = self.store.video_library()["items"][0]
        self.assertEqual(1, first["content_version"])
        self.assertEqual(hashlib.sha256(self.video_bytes).hexdigest(), first["media_sha256"])
        self.store.edit("imported-fixture", {"base_version": 1, "title": "같은 영상의 새 문안"})
        items = self.store.video_library()["items"]
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertIsNone(item["job_id"])
        self.assertEqual("completed", item["status"])
        self.assertEqual("imported-fixture", item["content_id"])
        self.assertEqual(2, item["content_version"])
        self.assertEqual("같은 영상의 새 문안", item["title"])
        self.assertTrue(item["media_available"])
        self.assertEqual(first["id"], item["id"])
        self.assertEqual(first["media_sha256"], item["media_sha256"])
        self.assertNotEqual(first["media_url"], item["media_url"])
        self.assertEqual(self.video_bytes, Path(self.store.imported_video_media_file("imported-fixture", 2, 0)).read_bytes())
        with self.assertRaises(Problem):
            self.store.imported_video_media_file("imported-fixture", 2, 1)

    def test_missing_video_remains_in_history_without_a_playable_url(self):
        job_id = self.add_job(status="completed", result={"media_path": "output/fixture/missing.mp4"})
        item = self.item(job_id)
        self.assertEqual("completed", item["status"])
        self.assertFalse(item["media_available"])
        self.assertIsNone(item["media_url"])
        with self.assertRaises(Problem) as caught:
            self.store.video_job_media_file(job_id)
        self.assertEqual(404, caught.exception.status)
        self.ingest_video()
        imported = next(row for row in self.store.video_library()["items"] if row["content_id"] == "imported-fixture")
        Path(self.store.imported_video_media_file("imported-fixture", 1, 0)).unlink()
        missing = next(row for row in self.store.video_library()["items"] if row["id"] == imported["id"])
        self.assertFalse(missing["media_available"])
        self.assertIsNone(missing["media_url"])

    def test_unsafe_paths_symlinks_extensions_and_unknown_jobs_cannot_be_served(self):
        outside = Path(self.tmp.name) / "outside.mp4"
        outside.write_bytes(b"outside-private-video")
        link = self.output / "outside-link.mp4"
        link.symlink_to(outside)
        candidates = ("../outside.mp4", str(outside), self.relative(link), ".runtime/segmind-api-key",
                      ".runtime/boca.sqlite3", "config/persona.json", "https://example.com/clip.mp4", "file:///etc/passwd")
        for number, path in enumerate(candidates, 1):
            with self.subTest(path=path):
                job_id = self.add_job(number, status="completed", result={"media_path": path})
                item = self.item(job_id)
                self.assertFalse(item["media_available"])
                self.assertIsNone(item["media_url"])
                with self.assertRaises(Problem) as caught:
                    self.store.video_job_media_file(job_id)
                self.assertEqual(404, caught.exception.status)
        for unknown in ("no-such-job", "../outside.mp4", str(outside)):
            with self.subTest(job_id=unknown), self.assertRaises(Problem):
                self.store.video_job_media_file(unknown)

    def test_http_library_and_range_playback_are_read_only_and_ignore_query_paths(self):
        job_id = self.add_job(status="completed", result={"media_path": str(self.video)})
        imported_file = self.output / "separate-import.mp4"
        imported_bytes = self.video_bytes + b"-separate-import"
        imported_file.write_bytes(imported_bytes)
        self.ingest_video(path=imported_file)
        library = self.store.video_library()
        job = next(item for item in library["items"] if item["job_id"] == job_id)
        imported = next(item for item in library["items"] if item["job_id"] is None)
        before = self.database_snapshot()
        with self.http() as base:
            with urlopen(base + "/api/video-library") as response:
                body = json.load(response)
                self.assertEqual(library["total"], body["total"])
                self.assertEqual({item["id"] for item in library["items"]}, {item["id"] for item in body["items"]})
            for item in (job, imported):
                with self.subTest(url=item["media_url"]):
                    expected_bytes = self.video_bytes if item["job_id"] else imported_bytes
                    request = Request(base + item["media_url"] + "?path=../../outside.mp4", headers={"Range": "bytes=2-5"})
                    with urlopen(request) as response:
                        self.assertEqual(206, response.status)
                        self.assertEqual("video/mp4", response.headers["Content-Type"])
                        self.assertEqual("bytes 2-5/%d" % len(expected_bytes), response.headers["Content-Range"])
                        self.assertEqual(b"2345", response.read())
                    request = Request(base + item["media_url"], headers={"Range": "bytes=999-"})
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request)
                    self.assertEqual(416, caught.exception.code)
            for route in ("/api/video/jobs/no-such-job/media", "/api/video/jobs/../media", "/api/video-library/imported/imported-fixture/1/999/media"):
                with self.subTest(route=route), self.assertRaises(HTTPError) as caught:
                    urlopen(base + route)
                self.assertEqual(404, caught.exception.code)
        self.assertEqual(before, self.database_snapshot())


if __name__ == "__main__":
    unittest.main()
