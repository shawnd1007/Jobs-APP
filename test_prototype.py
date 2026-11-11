"""Regression checks using temporary data and mocked paid/network calls."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import prototype


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = app.DATA, app.DB
        self.oldseed = app.SEED
        app.SEED = Path(__file__).resolve().parent / 'fixtures' / 'seed.html'
        app.DATA = Path(self.tmp.name)
        app.DB = app.DATA / 'test.sqlite3'
        app.init()

    def tearDown(self):
        app.DATA, app.DB = self.old
        app.SEED = self.oldseed
        self.tmp.cleanup()

    def test_removed_salary_and_form_evidence_do_not_survive_refresh(self):
        j = app.records()[0]
        j.update(salary_min=75000, salary_max=95000, salary_type='base', salary_currency='USD', salary_period='year', application_verified=app.now())
        with app.connect() as c:
            app.upsert(c, j)
            fresh = {k: v for k, v in j.items() if not k.startswith('salary_') and k != 'application_verified'}
            fresh['salary_text'] = 'Salary Not Published'
            app.upsert(c, fresh)
        saved = app.records()[0]
        self.assertIsNone(app.base_salary(saved))
        self.assertNotIn('application_verified', saved)

    def test_hybrid_description_cannot_pass_as_remote(self):
        for description in ['This position is hybrid. Employees must work from our office three days per week.', 'You are required to attend our office weekly.']:
            self.assertNotEqual(app.location_eligibility(dict(location='Remote United States', remote=True, description=description), app.config())[0], 'Eligible')

    def test_salary_policy_distinguishes_overlap_from_minimum(self):
        cfg = app.config()
        j = dict(salary_min=60000, salary_max=80000, salary_type='base', salary_currency='USD', salary_period='year')
        self.assertTrue(app.salary_qualifies(j, cfg))
        cfg['salary_policy'] = 'minimum'
        self.assertFalse(app.salary_qualifies(j, cfg))

    def test_preferences_conflicts_and_validation(self):
        state = app.snapshot()
        payload = dict(revision=state['preferences_revision'], preferences={'salary_floor': 81000})
        self.assertEqual(prototype.save_preferences(app, payload)[0], 200)
        self.assertEqual(app.config()['salary_floor'], 81000)
        self.assertEqual(prototype.save_preferences(app, payload)[0], 409)
        payload['revision'] = app.snapshot()['preferences_revision']
        payload['preferences'] = {'salary_floor': -1}
        with self.assertRaises(ValueError): prototype.save_preferences(app, payload)

    def test_board_root_and_case_share_one_source(self):
        self.assertEqual(app.board_identity('https://jobs.ashbyhq.com/Deepgram'), ('ashby', 'deepgram'))
        self.assertEqual(app.identity('https://jobs.ashbyhq.com/Deepgram/123/application'), app.identity('https://jobs.ashbyhq.com/deepgram/123'))

    def test_custom_skills_and_title_exclusions_change_matching(self):
        cfg=app.config()
        j=dict(title='Technical Support Specialist',location='Remote United States',description='Linux troubleshooting',availability='Open')
        cfg['skill_groups']=[dict(label='Linux',terms=['linux'],points=20)]
        higher=app.assess(dict(j),cfg)['score']
        cfg['skill_groups'][0]['points']=2
        self.assertEqual(higher-app.assess(dict(j),cfg)['score'],18)
        cfg['excluded_title_terms']=['specialist']
        self.assertEqual(app.assess(dict(j),cfg)['queue'],'Excluded')

    def test_watched_board_is_retained_without_matching_jobs(self):
        cfg=app.config();cfg.update(additional_boards={},public_web_search_enabled=False,firecrawl_enabled=False,generic_urls_per_run=0,request_delay_seconds=0)
        with app.connect() as c:
            c.execute('DELETE FROM tracking');c.execute('DELETE FROM jobs')
        prototype.source_result(app,'ashby/example','ok',0)
        with patch.object(app,'config',return_value=cfg),patch.object(app,'board_jobs',return_value=[]) as feed:
            app.LOCK.acquire();app.run_pipeline()
        feed.assert_called_once_with('ashby','example')

    def test_generic_queue_does_not_starve_later_urls(self):
        cfg = app.config()
        urls = ['https://example.com/a', 'https://example.com/b', 'https://example.com/c']
        cfg.update(additional_employer_urls=urls, additional_boards={}, public_web_search_enabled=False, firecrawl_enabled=False, generic_urls_per_run=1, request_delay_seconds=0)
        with app.connect() as c:
            c.execute('DELETE FROM tracking');c.execute('DELETE FROM jobs')
        attempted = []
        def failed(url, *args): attempted.append(url); raise ValueError('manual')
        with patch.object(app, 'config', return_value=cfg), patch.object(app, 'generic_posting', side_effect=failed):
            for _ in range(3):
                app.LOCK.acquire(); app.run_pipeline()
        self.assertEqual(attempted, urls)

    def test_ai_disabled_never_calls_provider(self):
        with patch('prototype.urllib.request.urlopen') as network:
            self.assertEqual(prototype.ai_review(app, 1)[0], 400)
        network.assert_not_called()

    def test_exported_project_needs_no_firecrawl_secret_file(self):
        with patch.object(app, 'ROOT', app.DATA):
            self.assertEqual(app.firecrawl_key(), '')

    def test_ai_cached_separate_and_budgeted(self):
        cfg = app.config();cfg.update(ai_enabled=True, ai_daily_limit=1)
        advice = dict(summary='Consider this role', strengths=['Customer ownership'], gaps=[], questions=['Confirm location'], next_steps=['Review posting'])
        response = dict(status='completed', output=[{'content': [{'type': 'output_text', 'text': json.dumps(advice)}]}], usage={'total_tokens': 50})
        with patch.object(app, 'config', return_value=cfg), patch.object(prototype, 'ai_key', return_value='fake-test-key'), patch('prototype.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as network:
            original = app.records()[0]
            self.assertEqual(prototype.ai_review(app, original['id'])[0], 200)
            self.assertEqual(prototype.ai_review(app, original['id'])[1], {'cached': True})
            self.assertEqual(network.call_count, 1)
            self.assertEqual(prototype.ai_review(app, app.records()[1]['id'])[0], 429)
            saved = app.records()[0]
            self.assertEqual(saved['status'], original['status'])
            self.assertEqual(saved['review_decision'], original['review_decision'])
            self.assertEqual(saved.get('queue'), original.get('queue'))
            request = json.loads(network.call_args.args[0].data)
            self.assertFalse(request['store'])
            self.assertNotIn('notes', json.loads(request['input'])['job'])

    def test_ai_failure_is_not_retried_or_leaked(self):
        cfg = app.config();cfg.update(ai_enabled=True)
        with patch.object(app, 'config', return_value=cfg), patch.object(prototype, 'ai_key', return_value='test'), patch('prototype.urllib.request.urlopen', side_effect=RuntimeError('SECRET-provider-body')) as network:
            code, body = prototype.ai_review(app, app.records()[0]['id'])
            self.assertEqual(code, 502);self.assertNotIn('SECRET', json.dumps(body));self.assertEqual(network.call_count, 1)


if __name__ == '__main__': unittest.main()
