"""Verified video recovery continues without submitting a second paid request."""
import json
import unittest
import test_production_media as media
from test_video import Provider


class ContinuityRecoveryTests(unittest.TestCase):
    def fixture(self):
        fixture = media.ProductionMediaTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        path = fixture.root / 'config/overnight.json'
        config = json.loads(path.read_text())
        config['ai_quality_review_enabled'] = False
        path.write_text(json.dumps(config))
        claim = fixture.claim_images(mode='video_only')
        job_id = fixture.request_video(claim)['job_id']
        provider = Provider()
        fixture.store.process_video(job_id, provider)
        return fixture.store, claim, job_id, provider

    def test_verified_video_completion_unblocks_and_claims_registration_once(self):
        store, claim, job_id, provider = self.fixture()
        store.worker_fail(claim['cycle']['id'], claim['lease_token'], 'interrupted polling', uncertain=True)
        store.process_video(job_id, provider)
        store._sync_video_progress(job_id)
        next_claim = store.worker_next('fixture-recovery')
        self.assertEqual('register', next_claim['job']['stage'])
        self.assertEqual('running', next_claim['run']['status'])
        self.assertIsNone(next_claim['run']['pause_reason'])
        self.assertEqual(1, len(provider.submissions))
        with store.db() as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM production_events WHERE event='run.video_resolved'").fetchone()[0])

    def test_definitive_provider_failure_resolves_uncertainty_and_allows_next_story(self):
        store, claim, job_id, provider = self.fixture()
        store.worker_fail(claim['cycle']['id'], claim['lease_token'], 'polling unknown', uncertain=True)
        provider.state = 'FAILED'
        store.process_video(job_id, provider)
        inspected = store.worker_inspect(claim['cycle']['id'])
        self.assertEqual('failed', inspected['cycle']['status'])
        self.assertEqual('running', inspected['run']['status'])
        self.assertEqual(0, store.video_job(job_id)['sync_pending'])
        next_claim = store.worker_next('fixture-recovery')
        self.assertEqual('sources', next_claim['job']['stage'])
        self.assertNotEqual(claim['cycle']['id'], next_claim['cycle']['id'])
        self.assertEqual(1, len(provider.submissions))

    def test_video_recovery_respects_user_pause_stop_and_unrelated_block(self):
        for state in ('paused', 'stopped', 'unrelated_block'):
            with self.subTest(state=state):
                store, claim, job_id, provider = self.fixture()
                if state == 'paused':
                    store.control_run(claim['run']['id'], 'pause')
                store.worker_fail(claim['cycle']['id'], claim['lease_token'], 'polling unknown', uncertain=True)
                if state == 'stopped':
                    store.control_run(claim['run']['id'], 'stop')
                if state == 'unrelated_block':
                    with store.db() as db:
                        db.execute("UPDATE production_runs SET pause_reason='fixture authentication issue' WHERE id=?", (claim['run']['id'],))
                store.process_video(job_id, provider)
                self.assertEqual('completed', store.video_job(job_id)['status'])
                expected = 'blocked' if state == 'unrelated_block' else state
                self.assertEqual(expected, store.automation_state()['run']['status'])
                self.assertFalse(store.worker_next('fixture-recovery')['should_work'])
                self.assertEqual(1, len(provider.submissions))

    def test_unconfirmed_video_cannot_be_declared_failed_to_bypass_uncertainty(self):
        store, claim, job_id, provider = self.fixture()
        store.worker_fail(claim['cycle']['id'], claim['lease_token'], 'polling unknown', uncertain=True)
        with self.assertRaises(media.Problem):
            store.worker_fail(claim['cycle']['id'], claim['lease_token'], 'invented failure', retryable=False,
                              resolved_video_job_id=job_id)
        self.assertEqual('blocked', store.automation_state()['run']['status'])
        self.assertEqual('running', store.video_job(job_id)['status'])
        self.assertEqual(1, len(provider.submissions))


if __name__ == '__main__':
    unittest.main()
