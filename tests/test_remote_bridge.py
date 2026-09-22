"""Remote request recovery uses an isolated journal, never the production DB."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/backend'))
from remote_bridge import Bridge


class RemoteBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.secret = 'fixture-secret-' + 'x' * 32
        self.bridge = Bridge(self.root, self.secret)

    def tearDown(self):
        self.temp.cleanup()

    def test_pending_request_stays_uncertain_across_process_restart(self):
        request_id = str(uuid.uuid4())
        self.assertIsNone(self.bridge.begin(request_id, 'digest'))
        restarted = Bridge(self.root, self.secret)
        code, result = restarted.begin(request_id, 'digest')
        self.assertEqual(409, code)
        self.assertEqual('OUTCOME_UNCERTAIN', result['code'])
        self.assertFalse((self.root / '.runtime/boca.sqlite3').exists())

    def test_completed_response_is_replayed_after_restart_but_changed_input_is_rejected(self):
        request_id = str(uuid.uuid4())
        self.bridge.begin(request_id, 'digest')
        self.bridge.finish(request_id, 200, {'version': 2})
        restarted = Bridge(self.root, self.secret)
        self.assertEqual((200, {'version': 2}), restarted.begin(request_id, 'digest'))
        self.assertEqual(409, restarted.begin(request_id, 'other-content')[0])
        self.assertEqual(0o600, restarted.journal.stat().st_mode & 0o777)

    def test_completed_uploads_release_capacity_and_chunks_and_cannot_be_replaced(self):
        connection, response = Mock(), Mock()
        response.status = 200
        response.read.return_value = json.dumps({'media': 'fixture.png'}).encode()
        self.bridge.connect = Mock(return_value=(connection, response))
        data = base64.b64encode(b'fixture-image').decode()
        finish = {'parts': 1, 'sha256': hashlib.sha256(data.encode()).hexdigest()}
        for _ in range(10):
            path = '/api/remote/uploads/' + str(uuid.uuid4())
            self.assertEqual(200, self.bridge.upload(path + '/0', {'data': data})[0])
            self.assertEqual(200, self.bridge.upload(path + '/complete', finish)[0])
        self.assertEqual([], list(self.bridge.uploads.glob('*/*.part')))
        self.assertEqual(200, self.bridge.upload(path + '/complete', finish)[0])
        self.assertEqual(10, self.bridge.connect.call_count)
        self.assertEqual(409, self.bridge.upload(path + '/complete', dict(finish, sha256='changed'))[0])
        self.assertEqual(409, self.bridge.upload(path + '/0', {'data': data})[0])

    def test_incomplete_uploads_are_bounded(self):
        with self.assertRaises(ValueError):
            Bridge(self.root, 'replace-with-at-least-32-random-characters')
        for _ in range(8):
            path = '/api/remote/uploads/' + str(uuid.uuid4()) + '/0'
            self.assertEqual(200, self.bridge.upload(path, {'data': 'YQ=='})[0])
        self.assertEqual(429, self.bridge.upload('/api/remote/uploads/' + str(uuid.uuid4()) + '/0', {'data': 'YQ=='})[0])
