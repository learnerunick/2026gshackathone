import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/backend"))
import instagram_connection as ig


class InstagramConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.token, self.status = ig.paths(self.root)
        self.token.parent.mkdir(parents=True)
        self.token.write_text("fixture-secret")
        self.profile = {"username": "everyday_boca", "user_id": "123", "account_type": "MEDIA_CREATOR"}
        self.quota = {"data": [{"quota_usage": 0, "config": {"quota_total": 100}}]}

    def verify(self):
        with patch.object(ig, "get", side_effect=[self.profile, self.quota]):
            return ig.verify(self.root, "everyday_boca")

    def test_verifies_identity_and_quota_without_exposing_credentials(self):
        result = self.verify()
        self.assertEqual(result["connection"], "verified")
        self.assertFalse(result["publisher_ready"])
        self.assertEqual(result["quota_total"], 100)
        self.assertNotIn("fixture-secret", json.dumps(result))
        self.assertNotIn(hashlib.sha256(b"fixture-secret").hexdigest(), json.dumps(result))
        self.assertEqual(self.status.stat().st_mode & 0o777, 0o600)

    def test_wrong_account_or_rotated_token_is_not_connected(self):
        self.verify()
        self.assertEqual(ig.public_status(self.root, "other")["connection"], "not-connected")
        self.token.write_text("rotated-secret")
        self.assertEqual(ig.public_status(self.root, "everyday_boca")["connection"], "not-connected")

    def test_failed_permission_check_invalidates_previous_success(self):
        self.verify()
        with patch.object(ig, "get", side_effect=[self.profile, ig.ConnectionError("denied")]):
            with self.assertRaises(ig.ConnectionError):
                ig.verify(self.root, "everyday_boca")
        self.assertEqual(ig.public_status(self.root, "everyday_boca")["connection"], "not-connected")

    def test_old_verification_requires_recheck(self):
        self.verify()
        status = json.loads(self.status.read_text())
        status["verified_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        ig.write_private(self.status, status)
        self.assertEqual(ig.public_status(self.root, "everyday_boca")["connection"], "recheck-required")

    def test_account_mismatch_stops_before_permission_probe(self):
        with patch.object(ig, "get", return_value=dict(self.profile, username="other")) as request:
            with self.assertRaises(ig.ConnectionError):
                ig.verify(self.root, "everyday_boca")
            self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
