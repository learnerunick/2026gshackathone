"""Interrupted text stages recover without paid calls or production storage."""
import fcntl
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/backend'))
from server import Store, Problem, DISCLOSURE
from local_worker import LocalProductionWorker, TIMEOUT_MESSAGE, NETWORK_MESSAGE, RESTART_MESSAGE, classify_worker_error


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'config', self.root / 'config')
        path = self.root / 'config/overnight.json'
        config = json.loads(path.read_text())
        config.update(specialist_agents_enabled=False, source_research_enabled=False,
                      start_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                      generation_end_at=None, max_attempts_per_job=2)
        path.write_text(json.dumps(config))
        self.store = Store(self.root)
        self.run = self.store.start_run({'end_at': None})
        self.worker = LocalProductionWorker(self.store, poll_seconds=.01)

    def tearDown(self):
        self.temp.cleanup()

    def claim(self, stage='storyboard'):
        results = {'sources': {'source_ids': []},
                   'planning': {'title': 'Fixture', 'topic_key': 'fixture', 'source_ids': []},
                   'storyboard': {'cards': [{'scene': 'fixture'}]},
                   'copy': {'caption': DISCLOSURE, 'hashtags': []}}
        while True:
            claim = self.store.worker_next(self.worker.worker_id)
            self.assertTrue(claim['should_work'], claim)
            if claim['job']['stage'] == stage:
                return claim
            self.store.worker_complete(claim['cycle']['id'], claim['lease_token'], results[claim['job']['stage']])

    def expire(self, cycle_id):
        with self.store.db() as db:
            db.execute('UPDATE production_cycles SET lease_expires_at=?,retry_after=? WHERE id=?',
                       ((datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                        (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(), cycle_id))

    def test_timeout_preserves_previous_results_and_fences_old_token(self):
        claim = self.claim()
        before = claim['cycle']['result']
        self.assertTrue(self.worker._finished(self.run['id'], -15, TIMEOUT_MESSAGE, TIMEOUT_MESSAGE))
        current = self.store.worker_inspect()
        self.assertEqual('running', current['run']['status'])
        self.assertEqual('pending', current['cycle']['status'])
        self.assertEqual(before, current['cycle']['result'])
        self.assertEqual('retry_backoff', self.store.worker_next(self.worker.worker_id)['reason'])
        self.assertFalse(self.worker._runnable(*self.worker._snapshot()))
        with self.assertRaises(Problem):
            self.store.worker_complete(claim['cycle']['id'], claim['lease_token'], {'cards': [{'scene': 'late'}]})
        self.expire(claim['cycle']['id'])
        second = self.store.worker_next(self.worker.worker_id)
        self.assertEqual('storyboard', second['job']['stage'])
        self.assertEqual(2, second['job']['attempts'])
        self.assertNotEqual(claim['lease_token'], second['lease_token'])

    def test_exhausted_retries_skip_cycle_and_three_failures_trip_circuit(self):
        for index in range(3):
            claim = self.claim('sources')
            self.worker._finished(self.run['id'], 1, NETWORK_MESSAGE, NETWORK_MESSAGE)
            self.expire(claim['cycle']['id'])
            second = self.claim('sources')
            self.worker._finished(self.run['id'], 1, NETWORK_MESSAGE, NETWORK_MESSAGE)
            snapshot = self.store.worker_inspect()
            self.assertEqual('failed', snapshot['cycle']['status'])
            self.assertEqual(index + 1, snapshot['run']['failed_count'])
        self.assertEqual('blocked', snapshot['run']['status'])
        self.assertIn('3회', snapshot['run']['pause_reason'])

    def test_abandoned_recovery_requires_expiry_and_known_failure(self):
        claim = self.claim()
        self.store.worker_fail(claim['cycle']['id'], claim['lease_token'], TIMEOUT_MESSAGE, uncertain=True)
        successor = LocalProductionWorker(self.store)
        self.assertFalse(successor._recover_abandoned(*successor._snapshot()))
        self.expire(claim['cycle']['id'])
        self.assertTrue(successor._recover_abandoned(*successor._snapshot()))
        self.assertFalse(successor._recover_abandoned(*successor._snapshot()))
        self.assertEqual('running', self.store.worker_inspect()['run']['status'])

    def test_unknown_failure_and_wrong_owner_do_not_recover(self):
        claim = self.claim()
        self.assertIsNone(self.store.recover_interrupted_text_stage(claim['cycle']['id'], 'other', TIMEOUT_MESSAGE))
        self.store.worker_fail(claim['cycle']['id'], claim['lease_token'], 'unknown failure', uncertain=True)
        self.expire(claim['cycle']['id'])
        self.assertFalse(self.worker._recover_abandoned(*self.worker._snapshot()))
        self.assertEqual('blocked', self.store.worker_inspect()['run']['status'])

    def test_committed_stage_survives_connection_failure_at_exit(self):
        claim = self.claim('sources')
        self.store.worker_complete(claim['cycle']['id'], claim['lease_token'], {'source_ids': []})
        self.worker._finished(self.run['id'], 1, NETWORK_MESSAGE, NETWORK_MESSAGE, committed_progress=True)
        snapshot = self.store.worker_inspect()
        self.assertEqual('running', snapshot['run']['status'])
        self.assertEqual('planning', snapshot['cycle']['stage'])
        self.assertEqual('completed', snapshot['jobs'][0]['status'])

    def test_failure_before_new_claim_does_not_loop_on_older_saved_result(self):
        claim = self.claim('sources')
        self.store.worker_complete(claim['cycle']['id'], claim['lease_token'], {'source_ids': []})
        self.worker._finished(self.run['id'], 1, NETWORK_MESSAGE, NETWORK_MESSAGE)
        snapshot = self.store.worker_inspect()
        self.assertEqual('blocked', snapshot['run']['status'])
        self.assertEqual('planning', snapshot['cycle']['stage'])

    def test_single_stage_invocation_cannot_claim_next_stage(self):
        self.worker._status(status='running', run_id=self.run['id'], single_stage=True, stage_event_cursor=0)
        claim = self.claim('sources')
        self.store.worker_complete(claim['cycle']['id'], claim['lease_token'], {'source_ids': []})
        self.assertEqual('stage_limit', self.store.worker_next(self.worker.worker_id)['reason'])
        self.assertEqual('planning', self.store.worker_inspect()['cycle']['stage'])

    def test_verified_server_exit_does_not_reset_exhausted_attempts(self):
        first = self.claim()
        self.worker._finished(self.run['id'], 1, NETWORK_MESSAGE, NETWORK_MESSAGE)
        self.expire(first['cycle']['id'])
        second = self.claim()
        result = self.store.recover_interrupted_text_stage(second['cycle']['id'], self.worker.worker_id, RESTART_MESSAGE)
        self.assertTrue(result['exhausted'])
        snapshot = self.store.worker_inspect()
        self.assertEqual('failed', snapshot['cycle']['status'])
        self.assertEqual(1, snapshot['run']['failed_count'])
        self.assertIn('planning', snapshot['cycle']['result'])

    def test_user_pause_stop_and_new_run_are_preserved(self):
        for action in ('pause', 'stop'):
            with self.subTest(action=action):
                claim = self.claim('sources')
                run_id = claim['run']['id']
                self.store.control_run(run_id, action)
                self.worker._finished(run_id, 1, TIMEOUT_MESSAGE, TIMEOUT_MESSAGE)
                self.expire(claim['cycle']['id'])
                self.assertFalse(self.worker._recover_abandoned(*self.worker._snapshot()))
                self.assertEqual('paused' if action == 'pause' else 'stopped', self.store.worker_inspect()['run']['status'])
                self.store.control_run(run_id, 'stop')
                self.store.start_run({'end_at': None})
                self.assertIsNone(self.store.recover_interrupted_text_stage(claim['cycle']['id'], self.worker.worker_id, TIMEOUT_MESSAGE, abandoned=True))

    def test_media_stage_and_external_id_remain_uncertain(self):
        claim = self.claim('images')
        self.worker._finished(self.run['id'], 1, TIMEOUT_MESSAGE, TIMEOUT_MESSAGE)
        self.assertEqual('uncertain', self.store.worker_inspect()['cycle']['status'])
        self.expire(claim['cycle']['id'])
        self.assertFalse(self.worker._recover_abandoned(*self.worker._snapshot()))

    def test_text_stage_with_external_id_is_not_retried(self):
        claim = self.claim()
        self.store.worker_ping(claim['cycle']['id'], claim['lease_token'], 'existing-provider-id')
        self.worker._finished(self.run['id'], 1, NETWORK_MESSAGE, NETWORK_MESSAGE)
        self.assertEqual('uncertain', self.store.worker_inspect()['cycle']['status'])
        self.expire(claim['cycle']['id'])
        self.assertFalse(self.worker._recover_abandoned(*self.worker._snapshot()))

    def fixture(self, events, finish=False):
        script = self.root / 'fixture.py'
        script.write_text('''import json,re,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from server import Store
store=Store(Path(sys.argv[2]))
owner=re.search(r'Worker ID: (.+)',sys.stdin.read()).group(1)
claim=store.worker_next(owner)
assert claim['should_work']
for event in json.loads(sys.argv[3]): print(json.dumps(event),flush=True)
if sys.argv[4]=='yes':
 store.worker_complete(claim['cycle']['id'],claim['lease_token'],{'source_ids':[]})
 print(json.dumps({'type':'turn.completed'}),flush=True)
else:
 while True: time.sleep(.01)
''')
        command = [sys.executable, str(script), str(ROOT / 'apps/backend'), str(self.root), json.dumps(events), 'yes' if finish else 'no']
        self.worker.network_grace_seconds = .05
        with (self.worker.directory / 'worker.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            with patch.object(self.worker, '_command', return_value=command):
                self.worker._run_once(self.worker._snapshot()[0], lock)
        return self.store.worker_inspect()

    def test_real_subprocess_network_failure_schedules_retry_without_no_progress_block(self):
        result = self.fixture([{'type':'error','message':'Reconnecting... waiting for network'}])
        self.assertEqual('running', result['run']['status'])
        self.assertEqual('pending', result['cycle']['status'])
        self.assertTrue(result['cycle']['retry_after'])
        self.assertEqual(NETWORK_MESSAGE, result['jobs'][0]['error'])

    def test_recovered_network_warning_does_not_block_success(self):
        result = self.fixture([{'type':'error','message':'stream disconnected before completion'}], finish=True)
        self.assertEqual('running', result['run']['status'])
        self.assertEqual('planning', result['cycle']['stage'])

    def test_auth_and_quota_are_not_retried(self):
        for message in ('authentication failed', 'quota exceeded', 'rate limit 429'):
            self.assertEqual('fatal', classify_worker_error({'message': message})[0])
        result = self.fixture([{'type':'error','message':'quota exceeded'}])
        self.assertEqual('blocked', result['run']['status'])
        self.assertEqual('uncertain', result['cycle']['status'])
        self.assertIsNone(result['cycle']['retry_after'])

    def test_real_subprocess_stage_timeout_schedules_retry(self):
        self.worker.max_stage_seconds = .2
        result = self.fixture([])
        self.assertEqual('running', result['run']['status'])
        self.assertEqual('pending', result['cycle']['status'])
        self.assertEqual(TIMEOUT_MESSAGE, result['jobs'][0]['error'])


if __name__ == '__main__':
    unittest.main()
