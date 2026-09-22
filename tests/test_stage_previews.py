"""Safe previews of saved stage outputs, using temporary files and local HTTP."""
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("boca_stage_preview_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem


class StagePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir()
        shutil.copytree(ROOT / "config", self.root / "config")
        current = datetime.now(timezone.utc)
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["ai_quality_review_enabled"] = True  # Legacy seven-stage policy.
        # Preserve legacy stage fixtures; mandatory research has its own integration tests.
        config.update(specialist_agents_enabled=False, source_research_enabled=False, start_at=(current - timedelta(minutes=1)).isoformat(),
                      generation_end_at=(current + timedelta(hours=2)).isoformat())
        config_path.write_text(json.dumps(config))
        self.output = self.root / "output/fixture"
        self.output.mkdir(parents=True)
        self.image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=")
        self.first = self.output / "first.png"
        self.first.write_bytes(self.image_bytes)
        self.second = self.output / "second.png"
        self.second.write_bytes(self.image_bytes + b"second-fixture")
        self.video = self.output / "clip.mp4"
        self.video_bytes = b"0123456789-video-fixture"
        self.video.write_bytes(self.video_bytes)
        self.store = Store(self.root)
        self.run = self.store.start_run({"media_mode": "images"})
        self.claim = self.claim_images()

    def tearDown(self):
        self.tmp.cleanup()

    def relative(self, path):
        return str(path.relative_to(self.root))

    def claim_images(self):
        results = {
            "sources": {"source_ids": []},
            "planning": {"title": "미리보기 검증용 일상", "topic_key": "preview-fixture", "source_ids": []},
            "storyboard": {"cards": [{"scene": "창가 선반"}]},
            "copy": {"caption": module.DISCLOSURE, "hashtags": []},
        }
        for stage in ("sources", "planning", "storyboard", "copy"):
            claim = self.store.worker_next("preview-fixture-worker")
            self.assertEqual(stage, claim["job"]["stage"])
            self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], results[stage])
        claim = self.store.worker_next("preview-fixture-worker")
        self.assertEqual("images", claim["job"]["stage"])
        return claim

    def checkpoint(self, value):
        self.store.worker_checkpoint(self.claim["cycle"]["id"], self.claim["lease_token"], value)

    def complete_images(self, value):
        self.store.worker_complete(self.claim["cycle"]["id"], self.claim["lease_token"], value)

    def read_stage(self, stage="images"):
        return self.store.read_stage_result(self.run["id"], self.claim["cycle"]["id"], stage)

    def file(self, index, stage="images"):
        return self.store.stage_media_file(self.run["id"], self.claim["cycle"]["id"], stage, index)

    def database_snapshot(self):
        with sqlite3.connect(str(self.store.db_path)) as db:
            return tuple(db.iterdump())

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

    def test_saved_relative_and_absolute_files_have_safe_image_and_video_urls(self):
        self.complete_images({"media": [self.relative(self.first), str(self.video)]})
        previews = self.read_stage()["previews"]
        self.assertEqual(2, len(previews))
        self.assertEqual({"image", "video"}, {preview["kind"] for preview in previews})
        prefix = "/api/runs/%s/stages/%s/images/media/" % (self.run["id"], self.claim["cycle"]["id"])
        for index, preview in enumerate(previews):
            self.assertTrue(preview["available"])
            self.assertTrue(preview["url"].startswith(prefix))
            self.assertTrue(preview["name"])
            self.assertTrue(preview["origin"])
            self.assertIn(Path(self.file(index)).resolve(), {self.first.resolve(), self.video.resolve()})
        self.assertNotIn(str(self.root), json.dumps(previews))

    def test_checkpoint_completed_cards_remain_previewable_after_final_result(self):
        self.checkpoint({"completed_cards": [{"media": self.relative(self.first), "alt": "첫 카드의 생성 결과"}]})
        before = self.read_stage()["previews"]
        self.assertTrue(any(preview["available"] and preview["alt"] == "첫 카드의 생성 결과" for preview in before))
        self.complete_images({"media": [self.relative(self.second)]})
        after = self.read_stage()["previews"]
        paths = {Path(self.file(index)).resolve() for index, item in enumerate(after) if item["available"]}
        self.assertEqual({self.first.resolve(), self.second.resolve()}, paths)
        self.assertTrue(any("checkpoint" in item["origin"] for item in after))

    def test_missing_file_has_unavailable_metadata_without_download_url(self):
        self.checkpoint({"media": [{"media_path": "output/fixture/not-created.png", "alt": "아직 저장되지 않은 카드"}]})
        previews = self.read_stage()["previews"]
        self.assertEqual(1, len(previews))
        self.assertFalse(previews[0]["available"])
        self.assertIsNone(previews[0]["url"])
        self.assertEqual("not-created.png", previews[0]["name"])
        with self.assertRaises(Problem) as caught:
            self.file(0)
        self.assertEqual(404, caught.exception.status)

    def test_native_call_receipt_previews_completed_card_before_final_media_list(self):
        receipt = {"card": 1, "status": "completed", "result_path": str(self.first),
                   "source_output_path": "/outside/generated_images/original.png",
                   "sha256": hashlib.sha256(self.image_bytes).hexdigest()}
        self.checkpoint({"completed_cards": [1], "calls": [receipt]})
        preview = self.read_stage()["previews"]
        self.assertEqual(1, len(preview))
        self.assertTrue(preview[0]["available"])
        self.assertEqual("running", self.read_stage()["status"])
        with self.http() as base:
            self.assertEqual(self.image_bytes, urlopen(base + preview[0]["url"]).read())
        self.first.write_bytes(b"changed after checkpoint")
        self.assertFalse(self.read_stage()["previews"][0]["available"])
        with self.assertRaises(Problem):
            self.file(0)

    def test_native_call_previews_exclude_unfinished_and_external_outputs(self):
        outside = Path(self.tmp.name) / "outside.png"
        outside.write_bytes(self.image_bytes)
        self.checkpoint({"calls": [
            {"status": "starting", "result_path": str(self.first)},
            {"status": "failed", "result_path": str(self.second)},
            {"status": "completed", "result_path": str(outside)},
            {"status": "completed", "result_path": "https://example.com/image.png"},
            {"status": "completed", "source_output_path": str(self.first)},
            {"status": "completed", "result_path": ".runtime/access-token"},
        ]})
        self.assertEqual([], self.read_stage()["previews"])

    def test_completed_card_file_path_receipt_preserves_hash_and_path_checks(self):
        outside = Path(self.tmp.name) / "outside.png"
        outside.write_bytes(self.image_bytes)
        receipt = {"card_order": 1, "file_path": str(self.first),
                   "tool_source_path": str(outside),
                   "sha256": hashlib.sha256(self.image_bytes).hexdigest()}
        self.checkpoint({"completed_cards": [receipt,
                         {"file_path": str(outside)},
                         {"file_path": "https://example.com/remote.png"},
                         {"file_path": ".runtime/access-token"}]})
        previews = self.read_stage()["previews"]
        self.assertEqual(1, len(previews))
        self.assertTrue(previews[0]["available"])
        self.assertEqual("running", self.read_stage()["status"])
        with self.http() as base:
            self.assertEqual(self.image_bytes, urlopen(base + previews[0]["url"]).read())
        self.first.write_bytes(b"changed after saved file receipt")
        self.assertFalse(self.read_stage()["previews"][0]["available"])
        with self.assertRaises(Problem):
            self.file(0)

    def test_traversal_external_urls_symlinks_and_sensitive_extensions_are_excluded(self):
        outside = Path(self.tmp.name) / "outside.png"
        outside.write_bytes(b"outside-private-marker")
        (self.output / "escape.png").symlink_to(outside)
        unsafe = ["../outside.png", str(outside), self.relative(self.output / "escape.png"),
                  "https://example.com/remote.png", "file:///etc/passwd", ".runtime/access-token",
                  ".runtime/boca.sqlite3", "config/persona.json"]
        self.checkpoint({"media": [self.relative(self.first)] + unsafe})
        previews = self.read_stage()["previews"]
        self.assertEqual(1, len(previews))
        self.assertEqual(self.first.resolve(), Path(self.file(0)).resolve())
        for index in (-1, 1, 999, "../outside.png"):
            with self.subTest(index=index), self.assertRaises(Problem):
                self.file(index)
        with self.assertRaises(Problem):
            self.store.stage_media_file("../outside", self.claim["cycle"]["id"], "images", 0)
        with self.assertRaises(Problem):
            self.store.stage_media_file(self.run["id"], "../outside", "images", 0)

    def test_register_preview_uses_recorded_revision_after_content_changes(self):
        self.complete_images({"media": [self.relative(self.first)]})
        quality = self.store.worker_next("preview-fixture-worker")
        self.store.worker_complete(quality["cycle"]["id"], quality["lease_token"], {"passed": True})
        registration = self.store.worker_next("preview-fixture-worker")
        content_id = registration["cycle"]["content_id"]
        registered_caption = "등록 전에 검수자가 다듬은 첫 문안.\n" + module.DISCLOSURE
        later_caption = "등록 이후 새 버전으로 수정한 문안.\n" + module.DISCLOSURE
        payload = {"id": content_id, "title": "등록 당시 콘텐츠", "topic_key": "preview-fixture",
                   "persona_id": self.run["persona_id"], "persona_version": self.run["persona_version"],
                   "caption": registered_caption, "hashtags": ["#등록본취향"], "sources": [],
                   "internal_metadata": {"api_key": "fixture-register-private-key", "note": "검토 기록은 유지"},
                   "cards": [{"media": self.relative(self.first), "alt": "등록 당시 첫 이미지"}]}
        first = self.store.ingest(payload)
        self.store.worker_complete(registration["cycle"]["id"], registration["lease_token"],
                                   {"content_id": content_id, "version": first["version"]})
        payload["title"] = "이후 수정된 콘텐츠"
        payload["caption"] = later_caption
        payload["hashtags"] = ["#나중에수정"]
        payload["cards"] = [{"media": self.relative(self.second), "alt": "나중의 새 이미지"}]
        second = self.store.ingest(payload, expected_version=first["version"])
        self.assertEqual(2, second["version"])
        stage = self.read_stage("register")
        previews = stage["previews"]
        self.assertEqual(1, len(previews))
        self.assertEqual(self.image_bytes, Path(self.file(0, "register")).read_bytes())
        self.assertEqual("등록 당시 첫 이미지", previews[0]["alt"])
        registered = stage["registered_content"]
        self.assertEqual(content_id, registered["id"])
        self.assertEqual(1, registered["version"])
        self.assertEqual(registered_caption, registered["payload"]["caption"])
        self.assertEqual(["#등록본취향"], registered["payload"]["hashtags"])
        self.assertNotEqual(module.DISCLOSURE, registered["payload"]["caption"])
        self.assertNotIn("fixture-register-private-key", json.dumps(registered))
        self.assertEqual("검토 기록은 유지", registered["payload"]["internal_metadata"]["note"])
        current = self.store.state()["contents"][0]
        self.assertEqual(2, current["current_version"])
        self.assertEqual(later_caption, current["payload"]["caption"])
        self.assertEqual(["#나중에수정"], current["payload"]["hashtags"])

    def test_http_preview_and_range_playback_do_not_change_database_or_accept_paths(self):
        self.complete_images({"media": [self.relative(self.first), self.relative(self.video)]})
        previews = self.read_stage()["previews"]
        video = next(item for item in previews if item["kind"] == "video")
        image = next(item for item in previews if item["kind"] == "image")
        before = self.database_snapshot()
        with self.http() as base:
            with urlopen(base + image["url"] + "?path=../../outside.png") as response:
                self.assertEqual(self.image_bytes, response.read())
                self.assertTrue(response.headers["Content-Type"].startswith("image/"))
            request = Request(base + video["url"], headers={"Range": "bytes=2-5"})
            with urlopen(request) as response:
                self.assertEqual(206, response.status)
                self.assertEqual("bytes 2-5/%s" % len(self.video_bytes), response.headers["Content-Range"])
                self.assertEqual(b"2345", response.read())
                self.assertEqual("video/mp4", response.headers["Content-Type"])
            request = Request(base + video["url"], headers={"Range": "bytes=999-"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(416, caught.exception.code)
            unknown = "/api/runs/%s/stages/%s/images/media/999" % (self.run["id"], self.claim["cycle"]["id"])
            with self.assertRaises(HTTPError) as caught:
                urlopen(base + unknown)
            self.assertEqual(404, caught.exception.code)
        self.assertEqual(before, self.database_snapshot())

    def test_saving_plain_prompt_paths_does_not_create_downloadable_previews(self):
        self.checkpoint({"prompt": "참고 지침 output/fixture/first.png", "notes": str(self.first),
                         "request": {"api_key_file": ".runtime/segmind-api-key"}})
        self.assertEqual([], self.read_stage()["previews"])
        with self.assertRaises(Problem) as caught:
            self.file(0)
        self.assertEqual(404, caught.exception.status)


if __name__ == "__main__":
    unittest.main()
