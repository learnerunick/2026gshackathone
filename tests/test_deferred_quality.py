"""Optional AI review must not block production or grant publication approval."""
import json
import unittest
import test_automation as automation
import test_specialists as specialists
import test_production_media as media
from test_video import Provider


class DeferredQualityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = automation.AutomationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.store = self.fixture.store

    def set_policy(self, enabled):
        path = self.fixture.root / 'config/overnight.json'
        config = json.loads(path.read_text())
        config['ai_quality_review_enabled'] = enabled
        path.write_text(json.dumps(config))

    def finish_media(self):
        for stage in ('sources', 'planning', 'storyboard', 'copy', 'images'):
            self.fixture.complete(self.fixture.claim(stage))

    def test_six_stage_default_registers_and_continues_without_approval(self):
        default = json.loads((automation.ROOT / 'config/overnight.json').read_text())
        self.assertIs(default['ai_quality_review_enabled'], False)
        self.set_policy(False)
        run = self.store.start_run({})
        self.finish_media()
        # A fresh Store resumes the committed stage without any AI review.
        self.store = self.fixture.store = automation.Store(self.fixture.root)
        claim = self.fixture.claim('register')
        self.assertFalse(json.loads(claim['job']['input_json'])['ai_quality_review_enabled'])
        self.assertNotIn('quality', claim['cycle']['result'])
        self.fixture.complete(claim)
        content = self.store.state()['contents'][0]
        self.assertEqual('ready', content['status'])
        self.assertIsNone(content['publication'])
        self.assertTrue(content['payload']['review_handoff']['human_review_required'])
        self.assertIn('AI 품질 검수', content['payload']['review_notes'][1])
        self.assertIsNone(self.store.claim_publication('fixture_account'))
        self.assertEqual(2, self.fixture.claim('sources')['cycle']['number'])
        self.assertEqual(['sources', 'planning', 'storyboard', 'copy', 'images', 'register'],
                         [s['key'] for s in self.store.automation_state()['stages']])
        with self.store.db() as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM jobs WHERE stage='quality'").fetchone()[0])

    def test_blocked_review_is_deferred_once_with_results_and_errors_preserved(self):
        run = self.store.start_run({})
        self.finish_media()
        quality = self.fixture.claim('quality')
        original = quality['cycle']['result']
        self.store.worker_fail(quality['cycle']['id'], quality['lease_token'], 'audio verification unavailable', uncertain=True)
        restored = self.store.defer_quality_review(run['id'])
        self.assertEqual(('running', 'register', None), (restored['status'], restored['current_stage'], restored['pause_reason']))
        self.store.defer_quality_review(run['id'])
        with self.assertRaises(automation.Problem):
            self.store.worker_complete(quality['cycle']['id'], quality['lease_token'], {'passed': True})
        claim = self.fixture.claim('register')
        for key, value in original.items():
            self.assertEqual(value, claim['cycle']['result'][key])
        self.fixture.complete(claim)
        content = self.store.state()['contents'][0]
        self.assertIn('audio verification unavailable', content['payload']['review_notes'])
        with self.store.db() as db:
            job = db.execute("SELECT status,error FROM jobs WHERE stage='quality'").fetchone()
            self.assertEqual(('skipped', 'audio verification unavailable'), tuple(job))
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM production_events WHERE event='stage.skipped'").fetchone()[0])

    def test_pause_other_uncertainty_and_active_review_are_not_overridden(self):
        run = self.store.start_run({})
        self.finish_media()
        quality = self.fixture.claim('quality')
        with self.assertRaises(automation.Problem):
            self.store.defer_quality_review(run['id'])
        self.store.control_run(run['id'], 'pause')
        self.store.worker_fail(quality['cycle']['id'], quality['lease_token'], 'audio unavailable', uncertain=True)
        self.assertEqual('paused', self.store.defer_quality_review(run['id'])['status'])
        self.assertFalse(self.store.worker_next('fixture-worker')['should_work'])
        self.store.control_run(run['id'], 'resume')
        self.fixture.complete(self.fixture.claim('register'))
        source = self.fixture.claim('sources')
        self.store.worker_fail(source['cycle']['id'], source['lease_token'], 'source worker lost', uncertain=True)
        self.assertEqual('blocked', self.store.defer_quality_review(run['id'])['status'])
        self.assertFalse(self.store.worker_next('fixture-worker')['should_work'])

    def test_missing_media_is_not_skipped_and_transaction_rolls_back(self):
        run = self.store.start_run({})
        self.finish_media()
        (self.fixture.root / 'fixture.png').unlink()
        with self.assertRaises(automation.Problem):
            self.store.defer_quality_review(run['id'])
        current = self.store.automation_state()['run']
        self.assertTrue(current['settings']['ai_quality_review_enabled'])
        self.assertEqual('quality', current['current_stage'])

    def test_target_and_human_version_approval_are_preserved(self):
        self.set_policy(False)
        self.store.start_run({'stop_after_posts': 1})
        self.finish_media()
        claim = self.fixture.claim('register')
        self.fixture.complete(claim)
        self.assertEqual('completed', self.store.automation_state()['run']['status'])
        content = self.store.state()['contents'][0]
        approved = self.store.decide(content['id'], content['current_version'], True)
        edited = self.store.edit(content['id'], {'base_version': approved['current_version'], 'title': 'Human edited title'})
        self.assertEqual('ready', edited['status'])
        self.assertIsNone(self.store.claim_publication('fixture_account'))

    def test_frozen_register_role_receives_override_and_quality_assignment_is_retained(self):
        fixture = specialists.SpecialistTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        fixture.start()
        quality = fixture.advance_to('quality')
        assignment = fixture.assign(quality, agent_id='/root/reviewer')
        fixture.store.worker_fail(quality['cycle']['id'], quality['lease_token'], 'cannot hear', uncertain=True)
        fixture.store.defer_quality_review(fixture.run['id'])
        register = fixture.claim('register')
        role = json.loads(register['job']['input_json'])['specialist']
        self.assertIn('보류', role['instructions'][0])
        state = fixture.store.automation_state()
        prior = next(a for a in state['specialists']['assignments'] if a['assignment_id'] == assignment['assignment_id'])
        self.assertEqual('skipped', prior['status'])
        self.assertEqual(6, len(state['stages']))

    def test_completed_video_moves_directly_to_register_without_second_submission(self):
        fixture = media.ProductionMediaTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        path = fixture.root / 'config/overnight.json'
        config = json.loads(path.read_text())
        config['ai_quality_review_enabled'] = False
        path.write_text(json.dumps(config))
        claim = fixture.claim_images(mode='video_only')
        job = fixture.request_video(claim)
        provider = Provider()
        fixture.store.process_video(job['job_id'], provider)
        fixture.store.process_video(job['job_id'], provider)
        self.assertEqual(1, len(provider.submissions))
        current = fixture.store.worker_next('fixture-ai-worker')
        self.assertEqual('register', current['job']['stage'])
        with fixture.store.db() as db:
            self.assertEqual(1, db.execute('SELECT COUNT(*) FROM video_jobs').fetchone()[0])
            self.assertEqual('completed', db.execute('SELECT status FROM video_jobs').fetchone()[0])


if __name__ == '__main__':
    unittest.main()
