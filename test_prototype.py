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
        base = json.loads((Path(__file__).resolve().parent / "config.example.json").read_text())
        config = patch.object(app, "config", side_effect=lambda: app.prototype.settings(dict(base), app.DATA))
        config.start()
        self.addCleanup(config.stop)
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

    def test_personalized_preferences_persist_and_affect_matching(self):
        state = app.snapshot()
        payload = dict(revision=state['preferences_revision'], preferences={
            'target_locations': ['Austin, TX', 'United States'],
            'workplace_types': ['onsite', 'remote'],
            'preferred_skills': ['SQL', 'Python'],
            'salary_floor': 85000,
            'salary_policy': 'minimum',
        })
        self.assertEqual(prototype.save_preferences(app, payload)[0], 200)
        cfg = app.config()
        self.assertEqual(cfg['target_locations'], ['Austin, TX', 'United States'])
        self.assertEqual(cfg['preferred_skills'], ['SQL', 'Python'])
        job = dict(title='Financial Analyst', location='Austin, TX', availability='Open', workplace_type='onsite',
                   description='Experience with SQL and Python.')
        match = app.assess(job.copy(), cfg)
        self.assertEqual(match['location_eligibility'], 'Eligible')
        self.assertEqual(match['queue'], 'Review')
        self.assertIn('Selected skills: sql, python', match['explanation'])
        near_match = app.assess(dict(job, description='Experience with MySQL.'), cfg)
        self.assertNotIn('Selected skills', near_match['explanation'])

    def test_custom_geography_keeps_ambiguous_remote_work_for_review(self):
        cfg = dict(app.config(), target_locations=['United States', 'Austin, TX'],
                   workplace_types=['remote'])
        self.assertEqual(app.location_eligibility(dict(location='Remote - U.S.'), cfg)[0], 'Eligible')
        self.assertEqual(app.location_eligibility(dict(location='Remote - US (California only)'), cfg)[0], 'Review')
        self.assertEqual(app.location_eligibility(dict(location='Remote'), cfg)[0], 'Review')
        self.assertEqual(app.location_eligibility(dict(location='Hybrid Austin, TX'), cfg)[0], 'Rejected')
        self.assertIn('Review', app.discovery_locations(cfg))

    def test_saved_search_alerts_are_independent_and_deduplicated(self):
        criteria = dict(name='Austin SQL', skills=['SQL'], locations=['Austin, TX'],
                        workplace_types=['onsite'], salary_min=80000, salary_max=105000, enabled=True)
        for patch_values in ({}, {'name': 'Second search', 'salary_min': 100000},
                             {'name': 'Paused', 'enabled': False}, {'name': 'Higher salary', 'salary_min': 130000,
                                                                    'salary_max': None}):
            self.assertEqual(prototype.change_saved_search(app, {
                'action': 'save', 'criteria': dict(criteria, **patch_values),
            })[0], 200)
        cfg = app.config()
        cfg.update(additional_boards={'greenhouse': ['fictional']}, public_web_search_enabled=False,
                   firecrawl_enabled=False, request_delay_seconds=0, generic_urls_per_run=0)
        job = dict(title='Fictional Engineer', employer='Fictional', url='https://job-boards.greenhouse.io/fictional/jobs/98765',
                   location='Austin, TX', availability='Open', description='SQL reporting', workplace_type='onsite',
                   salary_min=90000, salary_max=110000, salary_currency='USD', salary_period='year',
                   salary_type='base')
        def board(*_):
            return [dict(job)]

        def run():
            self.assertTrue(app.LOCK.acquire(False))
            return app.run_pipeline()

        with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_jobs', side_effect=board), \
             patch.object(app, 'read_response') as page:
            page.side_effect = TimeoutError('Fictional posting timeout')
            self.assertEqual(run()['state'], 'partial')
            initial = app.snapshot()
            self.assertEqual(initial['match_alerts'], [])
            retained = next(item for item in initial['jobs'] if item['url'] == job['url'])
            self.assertEqual(retained['availability'], 'Needs Verification')
            with app.connect() as c:
                c.execute("UPDATE tracking SET notes='Fictional reminder' WHERE job_id=?", (retained['id'],))

            page.side_effect = None
            page.return_value = (b'<title>Fictional Engineer</title>', job['url'])
            self.assertEqual(run()['state'], 'success')
            dashboard = app.snapshot()
            checked = next(item for item in dashboard['jobs'] if item['id'] == retained['id'])
            self.assertTrue(checked['posting_link_verified'])
            self.assertIsNone(checked.get('application_verified'))
            self.assertEqual(checked['notes'], 'Fictional reminder')
            self.assertEqual(run()['state'], 'success')
            self.assertEqual(app.snapshot()['match_alerts'], dashboard['match_alerts'])
            self.assertEqual(page.call_count, 2)
            with app.connect() as c:
                c.execute("UPDATE jobs SET listing=json_set(listing,'$.posting_verified',?) WHERE id=?",
                          ('2000-01-01T00:00:00+00:00', retained['id']))
            stale_dashboard = app.snapshot()
            stale = next(item for item in stale_dashboard['jobs'] if item['id'] == retained['id'])
            self.assertFalse(stale['posting_link_verified'])
            self.assertEqual({a['current_state'] for a in stale_dashboard['match_alerts']}, {'recheck'})
            self.assertEqual(run()['state'], 'success')
            recovered = app.snapshot()
            self.assertEqual(recovered['match_alerts'], dashboard['match_alerts'])

            search = dashboard['saved_searches'][0]
            for version, changes, expected in (
                (search['version'], {'enabled': False}, 'paused'),
                (search['version'] + 1, {'salary_min': 130000, 'salary_max': None}, 'changed'),
                (search['version'] + 2, {}, 'current'),
            ):
                self.assertEqual(prototype.change_saved_search(app, {
                    'action': 'save', 'id': search['id'], 'version': version,
                    'criteria': dict(search, **changes),
                })[0], 200)
                updated_alert = next(item for item in app.snapshot()['match_alerts']
                                     if item['search_id'] == search['id'])
                self.assertEqual(updated_alert['current_state'], expected)
                self.assertTrue(updated_alert['unread'])

            with app.connect() as c:
                c.execute("UPDATE jobs SET listing=json_set(listing,'$.availability','Closed') WHERE id=?",
                          (retained['id'],))
            closed = app.snapshot()
            self.assertEqual({a['current_state'] for a in closed['match_alerts']}, {'closed'})
            self.assertEqual([a['id'] for a in closed['match_alerts']],
                             [a['id'] for a in dashboard['match_alerts']])
            self.assertEqual(closed['unread_match_count'], 2)
        alerts = dashboard['match_alerts']
        self.assertEqual({item['search_name'] for item in alerts}, {'Austin SQL', 'Second search'})
        self.assertEqual(len(alerts), 2)
        self.assertEqual(dashboard['unread_match_count'], 2)
        self.assertEqual(prototype.change_saved_search(app, {'action': 'read', 'through': alerts[0]['id']})[0], 200)
        self.assertEqual(app.snapshot()['unread_match_count'], 0)
        search = app.snapshot()['saved_searches'][0]
        stale = {'action': 'delete', 'id': search['id'], 'version': search['version'] + 1}
        self.assertEqual(prototype.change_saved_search(app, stale)[0], 409)
        self.assertEqual(prototype.change_saved_search(app, dict(stale, version=search['version']))[0], 200)
        self.assertEqual(len(app.snapshot()['match_alerts']), 1)

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

    def test_role_fit_is_portable_and_independent_of_eligibility(self):
        cfg = app.config()
        cfg.update(categories=['lab technician'], preferred_skills=['microscopy', 'c'],
                   skill_groups=[dict(label='Sample preparation', terms=['sample preparation'], points=25)])
        listing = dict(title='Lab-Technician', description='Microscopy, sample preparation, C++.',
                       location='Remote United States', availability='Open')
        eligible = app.assess(dict(listing), cfg)
        other_location = app.assess(dict(listing, location='Berlin, Germany'), cfg)
        self.assertEqual(eligible['score_breakdown'],
                         dict(target_role=45, selected_skills=8, skill_groups=25))
        self.assertEqual(eligible['matched_skills'], ['microscopy'])
        self.assertEqual(eligible['score'], other_location['score'])
        unrelated = app.assess(dict(listing, title='Lab Technicianship Coordinator'), cfg)
        self.assertEqual(unrelated['score_breakdown']['target_role'], 0)

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
