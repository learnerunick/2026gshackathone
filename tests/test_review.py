import base64
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("boca_server", ROOT / "apps/backend/server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        (self.root / "fixture.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII="))
        self.store = Store(self.root)
        self.payload = {"id": "test-story", "title": "작은 취향", "topic_key": "small-taste",
                        "persona_version": 1, "caption": "오늘의 작은 기록.\n" + module.DISCLOSURE,
                        "hashtags": ["#가상인플루언서"], "cards": [{"media": "fixture.png", "alt": "검증용 이미지"}],
                        "sources": [], "review_notes": ["테스트 데이터"]}
        self.store.ingest(self.payload)

    def tearDown(self):
        self.tmp.cleanup()

    def current(self):
        return self.store.state()["contents"][0]

    def connect(self):
        path = self.root / "config/overnight.json"
        config = json.loads(path.read_text())
        config["instagram"] = {"account": "test_account", "connection": "verified"}
        config["publish_not_before"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(config))

    def test_idempotent_import_survives_restart(self):
        self.assertTrue(Store(self.root).ingest(self.payload)["duplicate"])
        self.assertEqual(1, self.current()["current_version"])

    def test_late_ai_result_is_proposal_not_overwrite(self):
        self.store.edit("test-story", {"base_version": 1, "title": "사람이 수정한 제목"})
        late = copy.deepcopy(self.payload)
        late["title"] = "뒤늦은 AI 제목"
        result = self.store.ingest(late, expected_version=1)
        self.assertTrue(result["proposal"])
        self.assertEqual("사람이 수정한 제목", self.current()["payload"]["title"])
        self.assertEqual(2, self.current()["current_version"])
        self.assertEqual(1, self.current()["proposals"])

    def test_approval_is_version_bound_and_edit_requires_reapproval(self):
        self.connect()
        self.store.decide("test-story", 1, True)
        self.store.edit("test-story", {"base_version": 1, "title": "새 버전"})
        self.assertEqual("ready", self.current()["status"])
        self.assertIsNone(self.store.claim_publication("test_account"))
        with self.assertRaises(Problem):
            self.store.decide("test-story", 1, True)
        self.store.decide("test-story", 2, True)
        self.assertEqual(2, self.store.claim_publication("test_account")["content"]["current_version"])

    def test_stale_human_edit_is_rejected(self):
        self.store.edit("test-story", {"base_version": 1, "title": "먼저 저장"})
        with self.assertRaises(Problem):
            self.store.edit("test-story", {"base_version": 1, "title": "늦게 저장"})
        self.assertEqual("먼저 저장", self.current()["payload"]["title"])

    def test_approved_ai_results_stay_separate(self):
        self.store.decide("test-story", 1, True)
        late = copy.deepcopy(self.payload)
        late["title"] = "자동 개선"
        self.assertTrue(self.store.ingest(late, expected_version=1)["proposal"])
        self.assertEqual("approved", self.current()["status"])

    def test_unconnected_account_cannot_publish(self):
        self.store.decide("test-story", 1, True)
        with self.assertRaises(Problem):
            self.store.claim_publication("test_account")
        self.assertEqual("approved", self.current()["status"])

    def test_claim_is_single_use_and_publication_is_not_duplicated(self):
        self.connect()
        self.store.decide("test-story", 1, True)
        claim = self.store.claim_publication("test_account")
        self.assertIsNone(Store(self.root).claim_publication("test_account"))
        self.store.finish_publication(claim["claim_id"], "published", "https://www.instagram.com/p/test-id/")
        self.assertIsNone(self.store.claim_publication("test_account"))
        with self.assertRaises(Problem):
            self.store.decide("test-story", 1, True)

    def test_uncertain_publication_cannot_be_retried_blindly(self):
        self.connect()
        self.store.decide("test-story", 1, True)
        claim = self.store.claim_publication("test_account")
        self.store.finish_publication(claim["claim_id"], "uncertain")
        self.assertIsNone(self.store.claim_publication("test_account"))
        with self.assertRaises(Problem):
            self.store.finish_publication(claim["claim_id"], "failed_before_publish")
        self.store.finish_publication(claim["claim_id"], "published", "https://www.instagram.com/p/confirmed/")
        self.assertEqual("published", self.current()["status"])

    def test_media_hash_changes_block_publication(self):
        self.connect()
        self.store.decide("test-story", 1, True)
        card = self.current()["payload"]["cards"][0]
        (self.store.media / card["media"]).write_bytes(b"changed")
        self.assertIsNone(self.store.claim_publication("test_account"))
        self.assertEqual("ready", self.current()["status"])
        self.assertEqual("blocked", self.current()["publication"]["status"])
        self.assertIn("미디어", self.current()["publication"]["detail"])
        with self.assertRaises(Problem):
            self.store.decide("test-story", 1, True)

    def test_retry_limit_and_external_job_id_are_durable(self):
        self.store.add_job("story:card-1", "image", {"base_version": 0})
        self.store.update_job("story:card-1", "claim")
        self.store.update_job("story:card-1", "external", external_id="provider-job-123")
        with self.assertRaises(Problem):
            self.store.update_job("story:card-1", "claim")
        self.store.update_job("story:card-1", "fail", error="confirmed failure")
        self.store.update_job("story:card-1", "claim")
        self.store.update_job("story:card-1", "fail", error="confirmed failure")
        with self.assertRaises(Problem):
            self.store.update_job("story:card-1", "claim")
        self.assertEqual("provider-job-123", Store(self.root).state()["jobs"][0]["external_job_id"])

    def test_disclosure_and_retailer_rules(self):
        for caption in ["가상 표시 없는 문안", "GS SHOP 추천!\n" + module.DISCLOSURE]:
            with self.assertRaises(Problem):
                self.store.edit("test-story", {"base_version": 1, "caption": caption})

    def test_approval_does_not_block_other_content(self):
        self.store.decide("test-story", 1, True)
        another = copy.deepcopy(self.payload)
        another.update(id="second-story", topic_key="other-day")
        self.store.ingest(another)
        self.assertEqual(2, len(self.store.state()["contents"]))

    def test_source_expiry_is_checked_again_before_publishing(self):
        expiration = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = copy.deepcopy(self.payload)
        payload["sources"] = [{"url": "https://www.gsshop.com/example", "checked_at": module.now(),
                              "expires_at": expiration.isoformat()}]
        self.store.ingest(payload, expected_version=1)
        self.connect()
        self.store.decide("test-story", 2, True)
        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return expiration + timedelta(hours=1)
        with patch.object(module, "datetime", Later):
            self.assertIsNone(self.store.claim_publication("test_account"))
            with self.assertRaises(Problem):
                self.store.decide("test-story", 2, True)
        self.assertEqual("ready", self.current()["status"])
        self.assertEqual("blocked", self.current()["publication"]["status"])

    def test_expired_publication_does_not_block_next_approved_content(self):
        expiration = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = copy.deepcopy(self.payload)
        payload["sources"] = [{"url": "https://www.gsshop.com/example", "checked_at": module.now(),
                              "expires_at": expiration.isoformat()}]
        self.store.ingest(payload, expected_version=1)
        self.connect()
        self.store.decide("test-story", 2, True)
        with self.store.db() as db:
            prior_approval = dict(db.execute("SELECT * FROM approvals WHERE content_id='test-story'").fetchone())
        other = copy.deepcopy(self.payload)
        other["id"] = "second-story"
        self.store.ingest(other)
        self.store.decide("second-story", 1, True)

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return expiration + timedelta(hours=1)

        with patch.object(module, "datetime", Later):
            claim = self.store.claim_publication("test_account")
            self.assertEqual("second-story", claim["content"]["id"])
            self.assertIsNone(Store(self.root).claim_publication("test_account"))
        with self.store.db() as db:
            blocked = self.store._content(db, "test-story")
            self.assertEqual("ready", blocked["status"])
            self.assertEqual(2, blocked["current_version"])
            self.assertEqual("blocked", blocked["publication"]["status"])
            self.assertIsNone(blocked["publication"]["claim_id"])
            self.assertEqual(prior_approval, dict(db.execute("SELECT * FROM approvals WHERE content_id='test-story'").fetchone()))
        events = [event for event in self.store.logs() if event["event"] == "publication.blocked"]
        self.assertEqual(1, len(events))
        self.assertEqual("test-story", events[0]["detail"]["content_id"])
        self.assertEqual(2, events[0]["detail"]["version"])
        self.assertEqual(prior_approval["fingerprint"], events[0]["detail"]["fingerprint"])

    def test_publication_unexpected_errors_still_propagate_without_changes(self):
        self.connect()
        self.store.decide("test-story", 1, True)
        with patch.object(self.store, "_validate", side_effect=RuntimeError("unexpected validation failure")):
            with self.assertRaisesRegex(RuntimeError, "unexpected validation failure"):
                self.store.claim_publication("test_account")
        self.assertEqual("approved", self.current()["status"])
        self.assertEqual("queued", self.current()["publication"]["status"])
        self.assertIsNone(self.current()["publication"]["claim_id"])
        self.assertFalse([event for event in self.store.logs() if event["event"] == "publication.blocked"])

    def test_malformed_source_items_return_structured_http_errors(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), module.handler(self.store))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for source in [None, [], "https://www.gsshop.com/example", {"url": 42}, {"url": "https://[invalid"}]:
                with self.subTest(source=source):
                    payload = copy.deepcopy(self.payload)
                    payload.update(id="malformed-source", sources=[source])
                    request = Request("http://127.0.0.1:%d/api/contents/import" % server.server_port,
                                      data=json.dumps({"content": payload}).encode(),
                                      headers={"Content-Type": "application/json", "X-BOCA-Token": self.store.token})
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request, timeout=3)
                    self.assertEqual(400, error.exception.code)
                    self.assertTrue(json.loads(error.exception.read())["error"])
            self.assertEqual(["test-story"], [content["id"] for content in self.store.state()["contents"]])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
