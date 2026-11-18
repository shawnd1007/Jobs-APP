"""V2 orchestration acceptance tests, isolated fictional profiles and feeds."""
import json
import base64
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
import recruiter
from fixtures.recruiter_fixture import environment, MARA, JULES, strategy, fake_ai

REAL_AI = recruiter.ai

PREFS = dict(salary=70000, currency='USD', period='year', flexible=False,
             commute='Portland, Oregon', remote_region='Oregon, United States', modes=['remote', 'onsite', 'hybrid'])


class RecruiterTests(unittest.TestCase):
    def test_master_file_is_saved_replaced_and_reset_without_touching_tracking(self):
        file = base64.b64encode(b'%PDF-1.4 fictional resume').decode()
        status, _ = recruiter.start(self.a, dict(action='analyze', version=0, resume=MARA,
            file_name='fictional.pdf', file_data=file))
        self.assertEqual(status, 202)
        self.wait()
        self.assertEqual(recruiter.resume(self.a), dict(text=MARA, name='fictional.pdf', file=file))
        self.assertNotIn('resume', recruiter.read(self.a))
        version = recruiter.read(self.a)['version']
        status, _ = recruiter.start(self.a, dict(action='analyze', version=version, resume=JULES))
        self.assertEqual(status, 202)
        self.wait()
        self.assertEqual(recruiter.resume(self.a)['file'], '')
        self.assertEqual(recruiter.start(self.a, dict(action='reset', version=recruiter.read(self.a)['version']))[0], 200)
        self.assertEqual(recruiter.resume(self.a)['text'], '')

    def test_tailored_draft_is_separate_versioned_and_detects_changed_resume(self):
        self.analyze(); self.search()
        job = self.a.records()[0]
        code, initial = recruiter.tailored_resume(self.a, job['id'])
        self.assertEqual(code, 200)
        payload = dict(action='generate', version=initial['version'], resume_hash=initial['resume_hash'], posting_hash=initial['posting_hash'])
        with patch.object(recruiter, 'ai', return_value={'sections': ['Fictional tailored draft']}) as mock:
            code, generated = recruiter.tailor(self.a, job['id'], payload)
        self.assertEqual(code, 200)
        self.assertEqual(mock.call_args.args[2]['resume'], MARA)
        self.assertEqual(recruiter.tailored_resume(self.a, job['id'])[1]['draft'], '')
        payload.update(action='save', draft=generated['draft'])
        self.assertEqual(recruiter.tailor(self.a, job['id'], payload)[0], 200)
        self.assertEqual(recruiter.tailor(self.a, job['id'], payload)[0], 409)
        self.assertEqual(recruiter.resume(self.a)['text'], MARA)
        self.analyze(JULES)
        self.assertTrue(recruiter.tailored_resume(self.a, job['id'])[1]['stale'])
        self.assertEqual(recruiter.tailor(self.a, job['id'], payload)[0], 409)

    def test_reset_clears_recruiter_only_and_rejects_stale_requests(self):
        self.analyze()
        self.search()
        before = recruiter.read(self.a)
        records = self.a.records()
        settings = dict(self.a.config())
        status, _ = recruiter.start(self.a, dict(action='reset', version=before['version']))
        self.assertEqual(status, 200)
        self.assertEqual(recruiter.read(self.a, True)['stage'], 'empty')
        self.assertNotIn('resume', recruiter.read(self.a, True))
        self.assertEqual(self.a.records(), records)
        self.assertEqual(self.a.config(), settings)
        self.assertEqual(recruiter.start(self.a, dict(action='analyze', version=before['version'], resume=MARA))[0], 409)
        with self.a.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM recruiter_match_cache').fetchone()[0], 0)

    def test_evidence_accepts_formatting_but_not_changed_claims(self):
        source = 'Mara managed 80 billing projects and resolved client issues.'
        self.assertTrue(recruiter.quote_in('“managed 80 billing projects”', source))
        self.assertTrue(recruiter.quote_in('managed 80\n billing projects', source))
        self.assertFalse(recruiter.quote_in('managed 800 billing projects', source))
        self.assertFalse(recruiter.quote_in('managed billing projects and hired staff', source))
        self.assertFalse(recruiter.quote_in('""', source))

    def setUp(self):
        self.context = environment()
        self.a, self.calls = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def wait(self):
        until = time.monotonic() + 10
        while recruiter.LOCK.locked() and time.monotonic() < until:
            time.sleep(.01)
        self.assertFalse(recruiter.LOCK.locked())
        return recruiter.read(self.a)

    def analyze(self, resume=MARA):
        state = recruiter.read(self.a)
        code, _ = recruiter.start(self.a, dict(action='analyze', resume=resume, version=state['version']))
        self.assertEqual(code, 202)
        state = self.wait()
        self.assertEqual(state['stage'], 'ready', state.get('error'))
        return state

    def search(self):
        state = recruiter.read(self.a)
        self.assertEqual(recruiter.start(self.a, dict(action='search', version=state['version'], preferences=PREFS))[0], 202)
        state = self.wait()
        self.assertEqual(state['stage'], 'complete', state.get('error'))
        return state

    def test_complete_retrieval_changes_with_resume_and_preserves_owner_settings(self):
        before = dict(self.a.config())
        self.assertEqual(self.a.records(), [])
        self.analyze()
        state = self.search()
        self.assertTrue(any('bing.com' in url for url in self.calls))
        self.assertTrue(any('api.lever.co' in url for url in self.calls))
        self.assertEqual(len(self.a.records()), 6)
        self.assertEqual(len(state['matches']), 6)
        groups = {m['title'] + m['location']: m['group'] for m in state['matches']}
        self.assertEqual(groups['Revenue Cycle SupervisorRemote — Oregon, United States'], 'close')
        self.assertEqual(groups['Medical Billing SpecialistRemote — United States'], 'close')
        self.assertEqual(groups['Medical Billing SpecialistRemote — United States, excluding Oregon'], 'avoid')
        self.assertEqual(groups['Clinical Laboratory ScientistRemote — Oregon, United States'], 'avoid')
        self.assertEqual(groups['Patient Accounts LeadPortland, Oregon'], 'review')
        self.analyze(JULES)
        other = self.search()
        close = [m['title'] for m in other['matches'] if m['group'] == 'close']
        self.assertEqual(close, ['CNC Machinist'])
        self.assertEqual(self.a.config(), before)
        self.assertNotIn('resume', recruiter.read(self.a))

    def test_duplicate_taps_and_stale_versions_cannot_replay(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set(); release.wait(3); return strategy(MARA)
        with patch.object(recruiter, 'strategy', side_effect=slow):
            self.assertEqual(recruiter.start(self.a, dict(action='analyze', version=0, resume=MARA))[0], 202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(recruiter.start(self.a, dict(action='analyze', version=0, resume=MARA))[0], 409)
            release.set(); self.wait()
        self.assertEqual(recruiter.start(self.a, dict(action='analyze', version=0, resume=MARA))[0], 409)

    def test_invalid_evidence_never_becomes_profile(self):
        bad = strategy(MARA)
        bad['skills'][0]['evidence'] = 'Invented clinical license'
        with patch.object(recruiter, 'ai', return_value=bad):
            recruiter.start(self.a, dict(action='analyze', version=0, resume=MARA))
            state = self.wait()
        self.assertEqual(state['stage'], 'ready')
        self.assertNotIn('Invented clinical license', [s['evidence'] for s in state['strategy']['skills']])
        self.assertEqual(state['strategy']['omitted_unverified'], 1)

    def test_unverified_caution_is_omitted(self):
        response = strategy(MARA)
        response['cautions'] = [dict(title='Pilot', reason='Training needed', evidence='Invented flight license')]
        with patch.object(recruiter, 'ai', return_value=response):
            result = recruiter.strategy(self.a, MARA)
        self.assertEqual(result['cautions'], [])
        self.assertEqual(result['omitted_unverified'], 1)
        self.assertTrue(result['skills'])
        self.assertTrue(result['roles'])

    def test_interrupted_analysis_keeps_resume_for_retry(self):
        recruiter.write(self.a, dict(version=1, stage='analyzing', resume=MARA, matches=[], error=''))
        with self.a.connect() as c: recruiter.init(c, self.a.now)
        self.assertEqual(recruiter.read(self.a)['stage'], 'interrupted')
        recruiter.start(self.a, dict(action='analyze', version=1))
        self.assertEqual(self.wait()['stage'], 'ready')
        activity = recruiter.activity(self.a)['entries']
        self.assertEqual([(event['operation'], event['progress']['stage']) for event in activity],
                         [(2, 'Career profile ready'), (2, 'Understanding your experience'),
                          (1, 'Interrupted by a server restart')])

    def test_current_search_progress_and_failed_attempt_history_survive_retry(self):
        state = self.analyze()
        board_progress, comparison_progress = [], []
        board_jobs = self.a.board_jobs
        actual_match = recruiter.match

        def observed_board(platform, board):
            board_progress.append(recruiter.read(self.a)['progress'])
            return board_jobs(platform, board)

        def fail_second_comparison(a, state, job):
            comparison_progress.append(recruiter.read(a)['progress'])
            if len(comparison_progress) == 2:
                raise recruiter.AIRequestError('The AI service timed out.')
            return actual_match(a, state, job)

        with patch.object(self.a, 'board_jobs', side_effect=observed_board), \
             patch.object(recruiter, 'match', side_effect=fail_second_comparison):
            status, _ = recruiter.start(self.a, dict(action='search', version=state['version'], preferences=PREFS))
            self.assertEqual(status, 202)
            failed = self.wait()
        self.assertEqual(failed['stage'], 'failed')
        self.assertEqual(board_progress[0]['stage'], 'Checking employer boards')
        self.assertEqual(board_progress[0]['source'], 'fictional-clinic')
        self.assertEqual([p['completed'] for p in comparison_progress], [0, 1])
        self.assertEqual(comparison_progress[1]['total'], 6)

        completed = self.search()
        events = list(reversed(recruiter.activity(self.a)['entries']))
        failed_events = [entry for entry in events if entry['operation'] == failed['version']]
        self.assertEqual(failed_events[0]['progress']['stage'], 'Preparing search')
        self.assertEqual(failed_events[-1]['progress']['reason'], 'The AI service timed out.')
        self.assertEqual(events[-1]['operation'], completed['version'])
        self.assertEqual(events[-1]['progress']['stage'], 'Search complete')
        self.assertEqual(events[-1]['progress']['completed'], 6)
        self.assertNotIn(MARA, json.dumps(events))
        earlier = recruiter.activity(self.a, before=failed_events[-1]['id'])['entries']
        self.assertEqual(earlier[0]['id'], failed_events[-2]['id'])

    def test_recruiter_status_loads_settings_once_for_the_shortlist(self):
        self.analyze()
        expected = self.search()
        self.assertGreater(len(expected['matches']), 1)
        with patch.object(self.a, 'config', wraps=self.a.config) as load_settings:
            refreshed = recruiter.read(self.a)
        self.assertEqual(refreshed['matches'], expected['matches'])
        load_settings.assert_called_once_with()
        with patch.object(self.a, 'records', side_effect=AssertionError('Status must not load jobs')), \
             patch.object(self.a, 'config', side_effect=AssertionError('Status must not load settings')):
            status = recruiter.read(self.a, status_only=True)
        self.assertEqual(status, {key: expected.get(key) for key in ('version', 'stage', 'progress')})

    def test_us_location_is_portable_across_customer_regions(self):
        from us_locations import is_us_location, remote_eligibility

        for region in ('Florida, United States', 'Colorado, United States', 'Oregon, United States'):
            self.assertEqual(remote_eligibility('United States - Remote',
                                                'Only shortlisted applicants will be contacted.', region)[0], 'pass')
        self.assertEqual(remote_eligibility('Remote — United States', 'Excluding Florida and Colorado.',
                                            'Florida, United States')[0], 'avoid')
        self.assertEqual(remote_eligibility('Remote — United States', 'Must reside in Oregon or Washington.',
                                            'Colorado, United States')[0], 'avoid')
        self.assertEqual(remote_eligibility('Remote — Denver, CO, United States', '',
                                            'Florida, United States')[0], 'avoid')
        self.assertEqual(remote_eligibility('Remote — Denver, CO, United States', '',
                                            'Colorado, United States')[0], 'pass')
        self.assertEqual(remote_eligibility('Remote — Colorado', '',
                                            'Florida, United States')[0], 'avoid')
        self.assertEqual(remote_eligibility('Remote — Ontario, Canada', '',
                                            'Colorado, United States')[0], 'avoid')
        self.assertFalse(is_us_location('Toronto, CA, Canada'))
        self.assertFalse(is_us_location('Worldwide'))
        self.assertFalse(is_us_location('Worldwide except the United States'))
        self.assertTrue(is_us_location('Denver, CO'))
        cfg = dict(target_locations=['Denver, Colorado, United States'], remote_hiring_locations=[],
                   workplace_types=['onsite'])
        job = dict(location='Denver, CO', workplace_type='onsite', description='')
        self.assertEqual(self.a.location_eligibility(job, cfg)[0], 'Eligible')
        self.assertEqual(self.a.location_eligibility(dict(job, location='Dallas, TX'), cfg)[0], 'Rejected')

    def test_saved_discovery_and_alerts_filter_location_without_touching_tracking(self):
        self.analyze()
        self.search()
        state = recruiter.read(self.a, True)
        template = next(job for job in self.a.records() if job['requisition'] == 'unknown')
        examples = (
            ('foreign', 'Bogotá, CO', 'onsite', 'Review denial queues.', 'review'),
            ('regional', 'Remote – US', 'remote', 'Location\nThis role will be remote and based in the Bay Area.', 'close'),
            ('domestic', 'Remote – US', 'remote', 'Review denial queues.', 'avoid'),
        )
        ids = {}
        with self.a.connect() as c:
            search_id = c.execute('INSERT INTO saved_searches(criteria,version) VALUES(?,0) RETURNING id',
                                  (json.dumps(dict(name='Fictional search', enabled=True, skills=['billing'],
                                   locations=['Oregon, United States'], workplace_types=['remote'],
                                   salary_min=70000, salary_max=None)),)).fetchone()[0]
            for key, location, mode, description, group in examples:
                job = dict(template, title='Fictional Billing ' + key.title(), requisition=key,
                           url='https://jobs.lever.co/fictional-clinic/' + key, location=location,
                           description=description, workplace_type=mode, remote=mode == 'remote')
                job_id, _ = self.a.upsert(c, job)
                ids[key] = job_id
                c.execute("UPDATE tracking SET notes='Keep the fictional application',status='Applied' WHERE job_id=?", (job_id,))
                self.a.prototype.record_match_alerts(c, job_id, [search_id], self.a.now())
                state['matches'].append(dict(state['matches'][0], job_id=job_id, fit_group=group, group=group,
                                             listing_fingerprint=recruiter.listing_fingerprint(job)))
        recruiter.write(self.a, state)
        with patch.object(self.a, 'config', return_value=dict(self.a.config(), us_postings_only=True)), \
             patch.object(recruiter, 'ai', side_effect=AssertionError('Existing results require no AI call')):
            matches = {item['job_id'] for item in recruiter.read(self.a)['matches']}
            snapshot = self.a.snapshot()
            jobs = {item['id']: item for item in snapshot['jobs']}
            for key in ('foreign', 'regional'):
                self.assertNotIn(ids[key], matches)
                self.assertTrue(jobs[ids[key]]['hidden_from_discovery'])
                self.assertEqual(jobs[ids[key]]['status'], 'Applied')
                self.assertEqual(jobs[ids[key]]['notes'], 'Keep the fictional application')
                self.assertFalse(any(alert['job_id'] == ids[key] for alert in snapshot['match_alerts']))
            self.assertIn(ids['domestic'], matches)
            self.assertFalse(jobs[ids['domestic']]['hidden_from_discovery'])
            self.assertEqual(snapshot['unread_match_count'], 1)
        self.assertEqual(recruiter.remote_eligibility('Remote – US', examples[1][3], 'California')[0], 'review')
        self.assertEqual(recruiter.remote_eligibility('Remote – US', examples[1][3], 'San Francisco Bay Area, CA')[0], 'pass')
        self.assertEqual(recruiter.remote_eligibility('Remote – US',
            'Compensation\nBased in the Bay Area: $110,000 to $125,000.', 'Oregon')[0], 'pass')

    def test_saved_adjacent_duty_evidence_is_reused_and_director_stays_in_review(self):
        self.analyze()
        self.search()
        state = recruiter.read(self.a, True)
        state['resume'] += ' Reconciled billing records for multiple clinics. Documented reports for supervisors.'
        state['strategy']['skills'] += [dict(label='billing'), dict(label='reports')]
        job = next(job for job in self.a.records() if job['requisition'] == 'unknown')
        job['description'] = 'Responsibilities\nReconcile billing records.\nDocument reports for supervisors.'
        result = dict(group='review', reason='Transferable billing duties.', gaps=['The vendor tool is preferred.'],
                      resume_evidence='Reconciled billing records for multiple clinics.',
                      job_evidence='Reconcile billing records.', emphasis=[])
        director = dict(job, title='Director of Billing Experience', requisition='director',
                        url='https://jobs.lever.co/fictional-clinic/director',
                        description=job['description'] + '\nManage managers and lead multiple teams.')
        with self.a.connect() as c:
            self.a.upsert(c, job)
            director['id'], _ = self.a.upsert(c, director)
        with patch.object(recruiter, 'ai', side_effect=[result, dict(result, group='close', gaps=[])]):
            adjacent = recruiter.match(self.a, state, job)
            senior = recruiter.match(self.a, state, director)
        self.assertEqual(adjacent['group'], 'adjacent')
        self.assertEqual(senior['group'], 'review')
        # Simulate a pre-upgrade shortlist with the original comparison retained.
        state['matches'] = [dict(adjacent, group='review', fit_group='review'), senior]
        recruiter.write(self.a, state)
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Existing results require no AI call')), \
             patch.object(self.a, 'run_pipeline', side_effect=AssertionError('Existing results require no search')):
            saved = {item['job_id']: item for item in recruiter.read(self.a)['matches']}
        self.assertEqual(saved[job['id']]['group'], 'adjacent')
        self.assertEqual(saved[director['id']]['group'], 'review')
        self.assertIn('Experience managing managers or team leads needs confirmation.', saved[director['id']]['checks'])
        self.assertIn('Leadership at the scale described by the employer needs confirmation.', saved[director['id']]['checks'])

    def test_exact_posting_can_supply_missing_remote_restrictions(self):
        title = 'Fictional Support Coordinator'
        job = dict(title=title, url='https://jobs.lever.co/fictional-clinic/regional', requisition='regional',
                   location='Remote - USA', description='Help clients troubleshoot.', workplace_type='remote')
        html = b'<h1>Fictional Support Coordinator</h1><h2>Location</h2><p>This role will be remote and based in the Bay Area.</p>'
        with patch.object(self.a, 'read_response', return_value=(html, job['url'])):
            self.a.verify_application(job, render_form=False)
        self.assertEqual(self.a.location_description(job),
                         'Help clients troubleshoot.\nRemote restricted to the Bay Area')
        self.assertFalse(self.a.discovery_location_allowed(job, dict(us_postings_only=True), remote_region='Florida'))
        self.assertTrue(self.a.discovery_location_allowed(job, dict(us_postings_only=True),
                                                        remote_region='San Francisco Bay Area, CA'))

    def test_usajobs_search_uses_official_posting_and_keeps_credentials_on_api_host(self):
        import usajobs
        from urllib.parse import parse_qs, urlsplit

        descriptor = dict(PositionURI='https://www.usajobs.gov/GetJob/ViewDetails/12345678',
                          PositionTitle='Fictional Support Specialist', OrganizationName='Fictional Agency',
                          PositionLocation=[dict(LocationName='Denver, Colorado', CountryCode='United States')],
                          PositionRemuneration=[dict(MinimumRange='80000', MaximumRange='95000',
                                                    RateIntervalCode='PA')],
                          QualificationSummary='Resolve fictional technical requests.')
        response = {'SearchResult': {'SearchResultItems': [
            {'MatchedObjectDescriptor': descriptor},
            {'MatchedObjectDescriptor': dict(descriptor, PositionURI='https://example.com/job/12345678')},
        ]}}
        reader = MagicMock(return_value=(json.dumps(response).encode(), usajobs.ENDPOINT))
        jobs = list(usajobs.search(reader, email='fixture@example.com', key='fictional-key',
                                  title='support', location='Denver, Colorado', remote=False))
        request = reader.call_args.args[0]
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query['HiringPath'], ['public'])
        self.assertEqual(query['RemoteIndicator'], ['false'])
        self.assertEqual(query['LocationName'], ['Denver, Colorado'])
        self.assertIn('Authorization-key', request.unredirected_hdrs)
        self.assertNotIn('Authorization-key', request.headers)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['url'], 'https://www.usajobs.gov/job/12345678')
        self.assertEqual(jobs[0]['salary_min'], 80000)
        self.assertEqual(jobs[0]['availability'], 'Needs Verification')

    def test_pay_leaves_fit_intact_and_posting_constraints_still_apply(self):
        self.analyze(); self.search()
        job = next(j for j in self.a.records() if j['title'] == 'Revenue Cycle Supervisor')
        for change, expected in [({'salary_max': 60000, 'salary_min': 50000}, 'close'),
                                 ({'salary_min': 60000}, 'close'), ({'salary_currency': 'CAD'}, 'close'),
                                 ({'availability': 'Closed'}, 'avoid'), ({'posting_verified': None}, 'review')]:
            with self.subTest(change=change):
                result = recruiter.match(self.a, recruiter.read(self.a, True), dict(job, **change))
                self.assertEqual(result['group'], expected)
                self.assertFalse(any('pay' in reason.lower() or 'salary' in reason.lower()
                                     for reason in result['checks']))

    def test_pay_only_review_can_be_restored_from_legacy_comparison(self):
        self.analyze(); self.search()
        job = next(j for j in self.a.records() if j['title'] == 'Revenue Cycle Supervisor')
        job.update(salary_min=None, salary_max=None, salary_text='Salary not published')
        with self.a.connect() as c:
            self.a.upsert(c, job)
        state = recruiter.read(self.a, True)
        match = recruiter.match(self.a, state, job)
        self.assertEqual(match['group'], 'close')
        match.pop('fit_group')
        match['pay_notes'] = ['Salary check needed.']
        match['group'] = 'review'
        state['matches'] = [match]
        recruiter.write(self.a, state)
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Unexpected AI request')), \
             patch.object(self.a, 'run_pipeline', side_effect=AssertionError('Unexpected employer search')):
            restored = recruiter.read(self.a)['matches'][0]
            self.assertEqual(restored['group'], 'close')
            self.assertNotIn('pay_notes', restored)
            state['matches'][0]['evidence_checks'] = ['Résumé evidence could not be verified.']
            recruiter.write(self.a, state)
            self.assertEqual(recruiter.read(self.a)['matches'][0]['group'], 'review')

    def test_market_pay_uses_public_job_facts_and_reuses_researched_sources(self):
        self.analyze(); self.search()
        job = next(j for j in self.a.records() if j['title'] == 'Revenue Cycle Supervisor')
        cfg = dict(self.a.config(), ai_enabled=True, ai_daily_limit=10)
        self.assertEqual(recruiter.market_pay(self.a, job['id'])[0], 400)
        with self.a.connect() as c:
            job.update(salary_min=None, salary_max=None, salary_text='Salary not published')
            self.a.upsert(c, job)
            comparable = dict(job, url='https://jobs.lever.co/fictional-clinic/comparable',
                              requisition='comparable', employer='Second Fictional Clinic',
                              title='revenue cycle supervisor', location='Oregon, United States')
            comparable_id, _ = self.a.upsert(c, comparable)
        text = 'Geography: Oregon, U.S.\nData period: May 2025\nRange: USD 75,000–95,000 per year.'
        body = {'status': 'completed', 'output': [
            {'type': 'web_search_call', 'status': 'completed', 'action': {'type': 'search'}},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': text, 'annotations': [
                {'type': 'url_citation', 'url': 'https://example.com/fictional-wages',
                 'title': 'Fictional wage data', 'start_index': 0, 'end_index': len(text)},
            ]}]},
        ]}
        self.assertEqual(recruiter.market_pay(self.a, job['id']), (200, {'research': None}))
        with patch.object(recruiter, 'ai', side_effect=REAL_AI), \
             patch.object(self.a, 'config', return_value=cfg), \
             patch.object(recruiter.prototype, 'ai_key', return_value='fictional-test-token'), \
             patch('urllib.request.urlopen') as network, \
             patch.object(recruiter.json, 'load', return_value=body):
            code, result = recruiter.market_pay(self.a, job['id'], research=True)
            self.assertEqual(code, 200)
            self.assertEqual(result['research']['summary'], text)
            self.assertTrue(result['research']['citations'][0]['url'].startswith('https://'))
            self.assertEqual(recruiter.market_pay(self.a, job['id'], research=True), (200, result))
            self.assertEqual(recruiter.market_pay(self.a, comparable_id, research=True), (200, result))
            self.assertEqual(result['research']['geography'], 'Oregon, U.S.')
            self.assertEqual(result['research']['data_period'], 'May 2025')
            self.assertEqual(result['research']['salary_min'], 75000)
            network.assert_called_once()
            payload = json.loads(network.call_args.args[0].data)
            self.assertEqual(payload['tools'][0]['type'], 'web_search')
            self.assertFalse(payload['store'])
            self.assertEqual(set(json.loads(payload['input'])), {'title', 'location', 'work_arrangement', 'period'})
        self.assertEqual(recruiter.market_pay(self.a, job['id']), (200, result))
        self.assertEqual(recruiter.researched_pay(body['output'][1:]), {'summary': None, 'citations': []})
        body['output'][1]['content'][0]['annotations'] = []
        self.assertEqual(recruiter.researched_pay(body['output']), {'summary': None, 'citations': []})

    def test_market_pay_promotes_only_qualified_saved_matches_at_the_target(self):
        self.analyze()
        self.search()
        state = recruiter.read(self.a, True)
        job = next(job for job in self.a.records() if job['requisition'] == 'billing')
        job.update(salary_min=None, salary_max=None, salary_text='Pay not disclosed',
                   description='Responsibilities\nReview medical billing records.')
        state['resume'] += ' Reviewed medical billing records.'
        comparison = dict(group='review', reason='Related billing experience.', gaps=[],
                          resume_evidence='Reviewed medical billing records.',
                          job_evidence='Review medical billing records.', emphasis=[])

        with self.a.connect() as c:
            self.a.upsert(c, job)
            unchecked = dict(job, requisition='unverified-billing',
                             url='https://jobs.lever.co/fictional-clinic/unverified-billing', posting_verified=None)
            unchecked['id'], _ = self.a.upsert(c, unchecked)
            unsupported = dict(job, requisition='unsupported-billing',
                               url='https://jobs.lever.co/fictional-clinic/unsupported-billing',
                               description='Responsibilities\nSupport customer escalations.')
            unsupported['id'], _ = self.a.upsert(c, unsupported)
        with patch.object(recruiter, 'ai', side_effect=[comparison, dict(comparison, job_evidence='Support customer escalations.')]) as provider:
            state['matches'] = [recruiter.match(self.a, state, candidate) for candidate in (job, unchecked, unsupported)]
            self.assertNotIn('salary_text', provider.call_args.args[2]['job'])
        recruiter.write(self.a, state)

        def saved_groups():
            return {item['job_id']: item['group'] for item in recruiter.read(self.a)['matches']}

        self.assertEqual(set(saved_groups().values()), {'review'})
        estimate = dict(summary='A sourced fictional market range.', geography='Oregon', data_period='2025',
                        salary_min=60000, salary_max=70000, salary_period='year',
                        citations=[dict(title='Fictional wage data', url='https://example.com/wages', end=20)])
        key = recruiter.market_pay_key(recruiter.market_pay_facts(self.a, job, state['preferences']))
        for price in (69000, 70000):
            with self.a.connect() as c:
                c.execute('DELETE FROM recruiter_match_cache WHERE fingerprint=?', (key,))
            with patch.object(recruiter, 'ai', return_value=dict(estimate, salary_max=price)) as provider:
                code, report = recruiter.market_pay(self.a, job['id'], research=True)
                self.assertEqual(code, 200)
                self.assertEqual(report['research']['target_match'], price == 70000)
                self.assertEqual(saved_groups(), {job['id']: 'adjacent' if price == 70000 else 'review',
                                                 unchecked['id']: 'review', unsupported['id']: 'review'})
                provider.assert_called_once()
        with self.a.connect() as c:
            stale = dict(estimate, researched_at='2020-01-01T00:00:00+00:00')
            c.execute('UPDATE recruiter_match_cache SET value=? WHERE fingerprint=?', (json.dumps(stale), key))
        self.assertEqual(set(saved_groups().values()), {'review'})

    def test_unverified_match_is_reviewed_without_stopping_other_matches(self):
        self.analyze()
        def one_bad_quote(a, name, inputs, schema):
            result = fake_ai(a, name, inputs, schema)
            if inputs['job']['title'] == 'Revenue Cycle Supervisor':
                result['resume_evidence'] = 'Invented management certification'
            return result
        with patch.object(recruiter, 'ai', side_effect=one_bad_quote):
            state = self.search()
        self.assertEqual(len(state['matches']), 6)
        candidate = next(m for m in state['matches'] if m['title'] == 'Revenue Cycle Supervisor')
        self.assertEqual(candidate['group'], 'review')
        self.assertEqual(candidate['resume_evidence'], '')
        self.assertTrue(any('could not be verified' in check for check in candidate['checks']))

    def test_failure_keeps_progress_and_does_not_touch_tracking(self):
        self.analyze(); self.search()
        job = self.a.records()[0]
        with self.a.connect() as c:
            c.execute("UPDATE tracking SET notes='Fictional preserved note',status='Applied' WHERE job_id=?", (job['id'],))
        with self.a.connect() as c: c.execute('DELETE FROM recruiter_match_cache')
        with patch.object(recruiter, 'ai', side_effect=ValueError('Service temporarily unavailable')):
            s = recruiter.read(self.a)
            recruiter.start(self.a, dict(action='search', version=s['version'], preferences=PREFS))
            state = self.wait()
        self.assertEqual(state['stage'], 'failed')
        self.assertEqual(next(j for j in self.a.records() if j['id'] == job['id'])['notes'], 'Fictional preserved note')

    def test_repeated_search_reuses_ai_but_rechecks_constraints(self):
        self.analyze(); self.search()
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Paid analysis replayed')):
            state = self.search()
        self.assertTrue(state['matches'])
        state = recruiter.read(self.a, True)
        state['preferences']['salary'] = 999999
        job = next(j for j in self.a.records() if j['title'] == 'Revenue Cycle Supervisor')
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Cached advice ignored')):
            self.assertEqual(recruiter.match(self.a, state, job)['group'], 'close')
            state['preferences']['remote_region'] = 'Florida, United States'
            self.assertEqual(recruiter.match(self.a, state, job)['group'], 'avoid')

    def test_provider_failure_is_redacted_and_reserves_budget(self):
        cfg = dict(self.a.config(), ai_enabled=True, ai_daily_limit=1)
        with patch.object(self.a, 'config', return_value=cfg), \
             patch.object(recruiter.prototype, 'ai_key', return_value='fictional-test-token'), \
             patch('urllib.request.urlopen', side_effect=RuntimeError('sensitive provider body')) as network:
            with self.assertRaisesRegex(ValueError, 'AI analysis could not finish'):
                REAL_AI(self.a, 'career_strategy', {'resume': MARA}, recruiter.STRATEGY)
            with self.assertRaisesRegex(ValueError, 'allowance'):
                REAL_AI(self.a, 'career_strategy', {'resume': MARA}, recruiter.STRATEGY)
            self.assertEqual(network.call_count, 1)
            payload = json.loads(network.call_args.args[0].data)
            self.assertFalse(payload['store'])
            self.assertTrue(payload['text']['format']['strict'])

    def test_records_reported_tokens_even_when_response_is_incomplete(self):
        cfg = dict(self.a.config(), ai_enabled=True, ai_daily_limit=10)
        response = MagicMock()
        response.__enter__.return_value = response
        body = {'status': 'incomplete', 'usage': {'input_tokens': 120, 'output_tokens': 30,
                 'input_tokens_details': {'cached_tokens': 20}}}
        with patch.object(self.a, 'config', return_value=cfg), \
             patch.object(recruiter.prototype, 'ai_key', return_value='fictional-test-token'), \
             patch('urllib.request.urlopen', return_value=response), \
             patch.object(recruiter.json, 'load', return_value=body):
            token = recruiter.OPERATION.set(42)
            try:
                with self.assertRaisesRegex(ValueError, 'could not finish'):
                    REAL_AI(self.a, 'career_strategy', {'resume': MARA}, recruiter.STRATEGY)
            finally:
                recruiter.OPERATION.reset(token)
        with self.a.connect() as c:
            row = c.execute('SELECT operation,kind,status,input_tokens,output_tokens,cached_input_tokens FROM recruiter_ai_calls').fetchone()
        self.assertEqual(tuple(row), (42, 'career_strategy', 'reported', 120, 30, 20))

    def test_usage_report_prices_known_usage_and_identifies_unknown(self):
        with self.a.connect() as c:
            c.execute('INSERT INTO recruiter_ai_calls(operation,kind,model,started,status,input_tokens,output_tokens,cached_input_tokens) VALUES(?,?,?,?,?,?,?,?)',
                      (7, 'candidate_match', 'gpt-5.4-mini', '2026-11-16', 'reported', 1000000, 1000000, 200000))
            c.execute('INSERT INTO recruiter_ai_calls(operation,kind,model,started,status) VALUES(?,?,?,?,?)',
                      (7, 'candidate_match', 'gpt-5.4-mini', '2026-11-16', 'unknown'))
        entry = recruiter.usage_report(self.a)['operations'][0]
        self.assertEqual(entry['calls'], 2)
        self.assertEqual(entry['unknown_calls'], 1)
        self.assertAlmostEqual(entry['estimated_cost_usd'], 5.115)
        self.assertEqual(entry['input_tokens'], 1000000)

    def test_usage_report_keeps_token_counts_for_unknown_model_pricing(self):
        with self.a.connect() as c:
            c.execute('INSERT INTO recruiter_ai_calls(operation,kind,model,started,status,input_tokens,output_tokens,cached_input_tokens) VALUES(?,?,?,?,?,?,?,?)',
                      (8, 'candidate_match', 'fictional-new-model', '2026-11-16', 'reported', 120, 30, 20))
        entry = recruiter.usage_report(self.a)['operations'][0]
        self.assertEqual((entry['input_tokens'], entry['output_tokens'], entry['cached_input_tokens']), (120, 30, 20))
        self.assertEqual(entry['unknown_calls'], 1)

    def test_personal_override_records_attempts_without_daily_cap(self):
        cfg = dict(self.a.config(), ai_enabled=True, ai_daily_limit=1)
        with patch.dict('os.environ', {'JOBS_PERSONAL_UNLIMITED_AI': '1'}), \
             patch.object(self.a, 'config', return_value=cfg), \
             patch.object(recruiter.prototype, 'ai_key', return_value='fictional-test-token'), \
             patch('urllib.request.urlopen', side_effect=RuntimeError('offline fixture')) as network:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'AI analysis could not finish'):
                    REAL_AI(self.a, 'career_strategy', {'resume': MARA}, recruiter.STRATEGY)
            self.assertEqual(network.call_count, 2)
            with self.a.connect() as c:
                self.assertEqual(c.execute('SELECT attempts FROM ai_usage').fetchone()[0], 2)

    def test_personal_override_compares_more_than_twelve(self):
        self.analyze()
        state = recruiter.read(self.a)
        jobs = [dict(id=i, updated=str(i), availability='Open') for i in range(15)]
        def finish_search(*args, **kwargs):
            self.a.LOCK.release()
            return {'state': 'success'}
        with patch.dict('os.environ', {'JOBS_PERSONAL_UNLIMITED_AI': '1'}), \
             patch.object(self.a, 'run_pipeline', side_effect=finish_search), \
             patch.object(self.a, 'records', return_value=jobs), \
             patch.object(recruiter, 'match', side_effect=lambda a, s, j: {'job_id': j['id'], 'group': 'avoid'}):
            self.assertEqual(recruiter.start(self.a, dict(action='search', version=state['version'], preferences=PREFS))[0], 202)
            until = time.monotonic() + 10
            while recruiter.LOCK.locked() and time.monotonic() < until:
                time.sleep(.01)
            self.assertFalse(recruiter.LOCK.locked())
            result = recruiter.read(self.a, True)
        self.assertEqual(result['stage'], 'complete')
        self.assertEqual(len(result['matches']), 15)
        self.assertEqual(result['deferred'], 0)

    def test_disabled_ai_does_not_call_provider(self):
        with patch('urllib.request.urlopen') as network:
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                REAL_AI(self.a, 'career_strategy', {'resume': MARA}, recruiter.STRATEGY)
            network.assert_not_called()

    def test_changed_posting_invalidates_saved_recommendation(self):
        self.analyze(); self.search()
        job = next(j for j in self.a.records() if j['title'] == 'Revenue Cycle Supervisor')
        job['description'] = 'Employer changed the duties after matching.'
        with self.a.connect() as c: self.a.upsert(c, job)
        result = next(m for m in recruiter.read(self.a)['matches'] if m['job_id'] == job['id'])
        self.assertEqual(result['group'], 'review')
        self.assertTrue(any('changed' in c for c in result['checks']))

    def test_invalid_preferences_and_input_do_not_mutate_state(self):
        with self.assertRaises(ValueError): recruiter.start(self.a, dict(action='analyze', version=0, resume='tiny'))
        self.assertEqual(recruiter.read(self.a)['version'], 0)
        for change in ({'remote_region': ''}, {'commute': ''}, {'modes': []}, {'salary': True}, {'currency': 'FAKE'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                recruiter.preferences({'preferences': dict(PREFS, **change)})


if __name__ == '__main__': unittest.main()
