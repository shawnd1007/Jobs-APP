"""V2 orchestration acceptance tests, isolated fictional profiles and feeds."""
import json
import base64
from http.client import HTTPConnection
from io import BytesIO
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

    def test_first_search_can_recommend_and_research_an_opening_without_saving_it(self):
        import recruiter_openings

        self.assertEqual(self.a.records(), [])
        self.assertEqual(recruiter_openings.page(self.a)['openings'], [])
        self.assertEqual(recruiter.read(self.a)['stage'], 'empty')
        with self.a.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM recruiter_match_cache').fetchone()[0], 0)
        self.analyze()
        cfg = dict(self.a.config(), max_new_candidates=0)
        board_jobs = self.a.board_jobs

        def without_pay(*args):
            jobs = board_jobs(*args)
            for job in jobs:
                if job['requisition'] == 'unknown':
                    for field in ('salary_min', 'salary_max', 'salary_period', 'salary_currency', 'salary_type'):
                        job.pop(field, None)
                    job['salary_text'] = 'Pay not disclosed'
            return jobs

        def provider(a, kind, inputs, schema):
            if kind == 'market_pay':
                return dict(summary='Fictional annual pay estimate.', geography='United States', data_period='May 2025',
                            salary_min=75000, salary_max=95000, salary_period='year',
                            citations=[dict(url='https://example.com/fictional-pay', title='Fictional wage data', end=30)])
            result = fake_ai(a, kind, inputs, schema)
            if kind == 'candidate_match' and inputs['job']['title'] == 'Medical Billing Specialist':
                result['resume_evidence'] = ('"Supervised eight billing specialists supporting outpatient clinics."\n'
                                             '"Built monthly Excel reports on accounts receivable and payer turnaround."')
                result['job_evidence'] = ('"Fictional employer opening."\n'
                                          '"Review denial queues and coach billing specialists."')
            return result

        with patch.object(self.a, 'config', return_value=cfg), patch.object(self.a, 'board_jobs', side_effect=without_pay), \
             patch.object(recruiter, 'ai', side_effect=provider) as ai:
            result = self.search()
        match = next(m for m in result['matches'] if m['posting_url'].endswith('/unknown'))
        self.assertEqual(match['group'], 'close')
        self.assertIn('\n', match['resume_evidence'])
        self.assertIn('\n', match['job_evidence'])
        self.assertIsNone(match['job_id'])
        self.assertRegex(match['opening_id'], r'^[a-f0-9]{64}$')
        self.assertTrue(match['market_pay_target_match'])
        self.assertEqual(sum(call.args[1] == 'market_pay' for call in ai.call_args_list), 1)
        self.assertEqual(self.a.records(), [])

        with self.a.ThreadingHTTPServer(('127.0.0.1', 0), self.a.Handler) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                def get(path):
                    with_connection = HTTPConnection(*server.server_address, timeout=2)
                    try:
                        with_connection.request('GET', path)
                        response = with_connection.getresponse()
                        self.assertEqual(response.status, 200)
                        return json.load(response)
                    finally:
                        with_connection.close()

                self.assertEqual(get('/api/recruiter')['matches'], [])
                self.assertIn(match['opening_id'], {m['opening_id'] for m in get('/api/recruiter?openings=1')['matches']})
                pay = get(f"/api/recruiter/openings/{match['opening_id']}/market-pay")
                self.assertEqual(pay['research']['salary_max'], 95000)
            finally:
                server.shutdown()
                thread.join()

    def test_fresh_openings_fill_the_comparison_budget_before_older_saved_jobs(self):
        import recruiter_openings

        self.analyze()
        state = dict(recruiter.read(self.a, private=True), preferences=PREFS)
        cfg = recruiter.search_config(self.a, state)
        fictional = dict(title='Revenue Cycle Supervisor', employer='Fictional Clinic',
                         location='Remote — Oregon, United States', workplace_type='remote',
                         availability='Open', description='Review denial queues and coach billing specialists.')
        recruiter_openings.capture(self.a, [dict(fictional, url=f'https://example.com/current/{i}')
                                           for i in range(26)], 1)
        older = dict(fictional, id=30, url='https://example.com/older', score=100)
        with patch.object(self.a, 'saved_comparison_jobs', return_value=[older]), \
             patch.object(self.a, 'assess', wraps=self.a.assess) as assess, \
             patch.object(recruiter.prototype, 'unlimited_personal_testing', return_value=False):
            queue, deferred = recruiter.comparison_queue(self.a, state, cfg, 1)
        self.assertEqual(len(queue), 24)
        self.assertEqual(deferred, 3)
        self.assertTrue(all(job['url'].startswith('https://example.com/current/') for job in queue))
        self.assertTrue(all(call.args[0]['id'] != 30 for call in assess.call_args_list))
        self.assertEqual(self.a.records(), [])

    def test_search_queries_project_saved_facts_and_keep_legacy_filters(self):
        facts = dict(title='Fictional Analyst', employer='Fictional Clinic', description='Fictional details',
                     queue='Review', pending_match_alert=True, posting_location_terms=['Remote, U.S.'])
        cases = {
            'old': {},
            'empty-flag': {'external_application': {}},
            'external': {'external_application': '0'},
            'closed': {'availability': 'Closed'},
            'held': {'identity_review': True},
            'reused': {'recruitee_offer_changed': True},
            'untracked': {},
        }
        ids = {}
        with self.a.connect() as c:
            for name, fields in cases.items():
                url = f'https://example.com/{name}'
                listing = json.dumps(dict(facts, url=url, **fields))
                ids[name] = c.execute('INSERT INTO jobs(identity,listing,created,updated) VALUES(?,?,?,?) RETURNING id',
                                      (url, listing, self.a.now(), self.a.now())).fetchone()[0]
                if name != 'untracked':
                    c.execute('INSERT INTO tracking(job_id,updated) VALUES (?,?)', (ids[name], self.a.now()))

        with patch.object(self.a, 'records', side_effect=AssertionError('Broad listing read')):
            headers = self.a.discovery_job_headers()
            self.assertEqual(self.a.manual_review_count(), 4)
            candidates = self.a.saved_comparison_jobs()
        self.assertEqual([job['id'] for job in headers], [ids[key] for key in ('old', 'empty-flag', 'closed', 'held', 'reused')])
        self.assertEqual([job['id'] for job in candidates], [ids['old'], ids['empty-flag']])
        self.assertEqual(headers[0]['posting_location_terms'], facts['posting_location_terms'])
        self.assertIs(headers[0]['pending_match_alert'], True)
        self.assertNotIn('description', headers[0])
        self.assertEqual(candidates[0]['description'], facts['description'])

    def test_repeat_search_uses_scoped_saved_job_reads(self):
        self.analyze()
        self.search()
        with patch.object(self.a, 'records', wraps=self.a.records) as records:
            result = self.search()
        self.assertTrue(result['matches'])
        self.assertTrue(all(call.kwargs.get('job_ids') is not None for call in records.call_args_list))

    def test_evidence_accepts_formatting_but_not_changed_claims(self):
        source = 'Mara managed 80 billing projects and resolved client issues.'
        self.assertTrue(recruiter.quote_in('“managed 80 billing projects”', source))
        self.assertTrue(recruiter.quote_in('managed 80\n billing projects', source))
        self.assertFalse(recruiter.quote_in('managed 800 billing projects', source))
        self.assertFalse(recruiter.quote_in('managed billing projects and hired staff', source))
        self.assertFalse(recruiter.quote_in('""', source))

    def test_comparison_verifies_each_separately_quoted_passage(self):
        source = "Managed 80 claims. Reviewed policies and recorded the team's results. Used HCPT2 exports."
        for text in (
            '“Managed 80 claims.”\n“recorded the team’s results.”',
            '1. "Managed 80 claims."\n2. "recorded the team\'s results."',
            '["Managed 80 claims.", "Used HCPT2 exports."]',
            "'Managed 80 claims.'; 'recorded the team\'s results.'",
            '- "Managed 80 claims."',
        ):
            with self.subTest(text=text):
                self.assertTrue(recruiter.comparison_quote_in(text, source))
        for text in (
            '"Managed 80 claims."\n"Processed payroll."',
            'Managed 80 claims.\nProcessed payroll.',
            '"Managed 80 claims." and fired the staff.',
            '"Managed 80 claims."\n"CPT"',
            '"Managed 80 claims."\n"Recorded the team\'s results.',
        ):
            with self.subTest(text=text):
                self.assertFalse(recruiter.comparison_quote_in(text, source))

    def test_legacy_gap_cannot_establish_a_requirement_unsupported_by_the_posting(self):
        self.analyze()
        state = recruiter.read(self.a, True)
        job = dict(title='Billing Specialist', description='Review billing records.')
        optional = dict(group='close', gaps=['Preferred: CRM experience is not required.'])
        self.assertEqual(recruiter.fit_assessment(self.a, optional, [], job, state)[0], 'close')
        for gap in ('Required: CRM experience is preferred but a license is required.',
                    'Preferred: CRM experience is not required, but clearance is mandatory.',
                    'Preferred: The posting lists this as a minimum qualification.'):
            with self.subTest(gap=gap):
                self.assertEqual(recruiter.fit_assessment(self.a, dict(group='close', gaps=[gap]),
                                                          [], job, state)[0], 'close')

    def test_comparison_uses_complete_resume_and_invalidates_cache_when_it_changes(self):
        self.analyze()
        self.search()
        state = recruiter.read(self.a, True)
        job = next(j for j in self.a.records() if j['requisition'] == 'billing')
        state['resume'] += ' Built a patient payment reconciliation tool. Email: mara@example.com'
        response = dict(group='close', reason='The applicant has matching experience.', gaps=[],
                        resume_evidence='Built a patient payment reconciliation tool.',
                        job_evidence='Review denial queues and coach billing specialists.', emphasis=[])
        with patch.object(recruiter, 'ai', return_value=response) as provider:
            match = recruiter.match(self.a, state, job)
            self.assertEqual(match['group'], 'close')
            supplied = provider.call_args.args[2]
            self.assertIn('Built a patient payment reconciliation tool.', supplied['resume'])
            self.assertNotIn('mara@example.com', supplied['resume'])
            recruiter.match(self.a, state, job)
            self.assertEqual(provider.call_count, 1)
            state['resume'] += ' Documented a separate reporting workflow.'
            recruiter.match(self.a, state, job)
            self.assertEqual(provider.call_count, 2)

    def test_employer_accepted_spreadsheet_alternative_is_not_a_required_gap(self):
        self.analyze()
        self.search()
        state = recruiter.read(self.a, private=True)
        job = next(job for job in self.a.records() if job['requisition'] == 'billing')
        requirement = 'Experience with Excel or Google Sheets.'
        duty = 'Review denial queues and coach billing specialists.'
        job['description'] = f'{duty}\nRequired:\n{requirement}'
        response = dict(
            group='close', reason='The candidate lacks Google Sheets.', emphasis=[],
            resume_evidence='Built monthly Excel reports on accounts receivable and payer turnaround.',
            job_evidence=duty, gaps=[
                dict(detail='No Google Sheets experience.', kind='required', employer_quote=requirement),
            ],
        )
        with self.a.connect() as c:
            self.a.upsert(c, job)
        with patch.object(recruiter, 'ai', return_value=response):
            match = recruiter.match(self.a, state, job)
        self.assertEqual(match['group'], 'close')
        self.assertEqual(match['gaps'], [])
        self.assertIn('a tool the employer accepts', match['reason'])

        state['matches'] = [dict(match, group='review', fit_group='review', gaps=['No Google Sheets experience.'],
                                 gap_evidence=response['gaps'])]
        recruiter.write(self.a, state)
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Refresh should use recorded evidence')):
            refreshed = recruiter.read(self.a)['matches'][0]
        self.assertEqual(refreshed['group'], 'close')
        self.assertEqual(refreshed['gaps'], [])

        required = 'An active medical coding license.'
        job['description'] += f'\n{required}'
        response['gaps'].append(dict(detail='Missing medical coding license.', kind='required', employer_quote=required))
        with patch.object(recruiter, 'ai', return_value=response):
            checked = recruiter.match(self.a, state, job)
        self.assertEqual(checked['group'], 'review')
        self.assertEqual(checked['gaps'], ['Missing medical coding license.'])
        self.assertIn(required, checked['confirmation_reasons'][0]['reason'])

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

    def test_pulled_openings_http_comparison_reuses_cache_without_changing_shortlist(self):
        import recruiter_openings

        opening = dict(title='Fictional Revenue Recovery Specialist', employer='Fictional Benefits Group',
                       location='Remote — United States', workplace_type='remote', availability='Open',
                       url='https://jobs.lever.co/fictional-benefits/recovery',
                       description='Review denial queues and coach billing specialists.')
        recruiter_openings.capture(self.a, [opening], run_id=0)
        opening_id = recruiter_openings.opening_id(self.a, opening['url'])
        listing_path = '/api/recruiter/openings'
        compare_path = f'{listing_path}/{opening_id}/compare'

        def request(method, path, body=b'{}', trusted=True):
            handler = object.__new__(self.a.Handler)
            handler.path = path
            handler.headers = {'Content-Length': str(len(body))}
            if trusted:
                handler.headers['X-Jobs-Client'] = 'dashboard'
            handler.rfile = BytesIO(body)
            with patch.object(handler, 'send') as response:
                getattr(handler, f'do_{method}')()
                response.assert_called_once()
                return response.call_args.args

        with patch.object(recruiter, 'ai', side_effect=fake_ai) as provider:
            status, listed = request('GET', listing_path + '?q=Recovery')
            self.assertEqual(status, 200)
            self.assertEqual([item['id'] for item in listed['openings']], [opening_id])
            self.assertEqual(request('GET', listing_path + '?q=one&q=two')[0], 400)
            self.assertEqual(request('POST', compare_path, body=b'[]')[0], 400)
            self.assertEqual(request('POST', compare_path, trusted=False)[0], 403)
            self.assertEqual(request('POST', compare_path)[0], 409)
            provider.assert_not_called()

        self.analyze()
        before = self.search()
        records_before = self.a.records()
        ineligible = dict(opening, url='https://jobs.lever.co/fictional-benefits/other-state',
                          location='Remote — United States, excluding Oregon')
        recruiter_openings.capture(self.a, [ineligible], run_id=0)
        ineligible_id = recruiter_openings.opening_id(self.a, ineligible['url'])

        with patch.object(recruiter, 'ai', side_effect=recruiter.AIRequestError('Fictional timeout')) as provider:
            status, error = request('POST', compare_path)
            self.assertEqual(status, 502)
            self.assertIn('Trying again may use another AI request.', error['error'])
            provider.assert_called_once()

        with patch.object(recruiter, 'ai', side_effect=fake_ai) as provider:
            self.assertEqual(request('POST', f'{listing_path}/{ineligible_id}/compare')[0], 422)
            self.assertEqual(request('POST', f'{listing_path}/' + '0' * 64 + '/compare')[0], 404)
            with recruiter.LOCK:
                self.assertEqual(request('POST', compare_path)[0], 409)
            provider.assert_not_called()

            status, result = request('POST', compare_path)
            self.assertEqual(status, 200)
            self.assertEqual(result['match']['job_id'], opening_id)
            self.assertEqual(result['match']['group'], 'review')
            self.assertIn('The exact employer posting needs verification.', result['match']['checks'])
            self.assertEqual(result['match']['job_evidence'], opening['description'])
            repeat_status, repeat = request('POST', compare_path)
            self.assertEqual(repeat_status, 200)
            self.assertEqual(repeat['match']['reason'], result['match']['reason'])
            self.assertEqual(repeat['match']['job_evidence'], result['match']['job_evidence'])
            provider.assert_called_once()
            self.assertEqual(provider.call_args.args[1], 'candidate_match')

        self.assertEqual(recruiter.read(self.a), before)
        self.assertEqual(self.a.records(), records_before)

    def test_complete_retrieval_changes_with_resume_and_preserves_owner_settings(self):
        before = dict(self.a.config())
        self.assertEqual(self.a.records(), [])
        self.analyze()
        state = self.search()
        self.assertTrue(any('bing.com' in url for url in self.calls))
        self.assertTrue(any('api.lever.co' in url for url in self.calls))
        self.assertEqual(len(self.a.records()), 6)
        self.assertEqual(len(state['matches']), 5)
        groups = {m['title'] + m['location']: m['group'] for m in state['matches']}
        self.assertEqual(groups['Revenue Cycle SupervisorRemote — Oregon, United States'], 'close')
        self.assertEqual(groups['Medical Billing SpecialistRemote — United States'], 'close')
        self.assertNotIn('Medical Billing SpecialistRemote — United States, excluding Oregon', groups)
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
        def unknown_passage(a, name, inputs, schema):
            result = fake_ai(a, name, inputs, schema)
            result['skills'][0]['evidence_id'] = 9999
            return result

        with patch.object(recruiter, 'ai', side_effect=unknown_passage):
            recruiter.start(self.a, dict(action='analyze', version=0, resume=MARA))
            state = self.wait()
        self.assertEqual(state['stage'], 'ready')
        self.assertEqual([s['label'] for s in state['strategy']['skills']], ['Team coaching'])
        self.assertEqual(state['strategy']['omitted_unverified'], 1)

    def test_unverified_caution_is_omitted(self):
        def unknown_passage(a, name, inputs, schema):
            result = fake_ai(a, name, inputs, schema)
            result['cautions'][0]['evidence_id'] = -1
            return result

        with patch.object(recruiter, 'ai', side_effect=unknown_passage):
            result = recruiter.strategy(self.a, MARA)
        self.assertEqual(result['cautions'], [])
        self.assertEqual(result['omitted_unverified'], 1)
        self.assertTrue(result['skills'])
        self.assertTrue(result['roles'])

    def test_strategy_resolves_numbered_passages_from_both_pdf_pages(self):
        first = '• Reviewed 80 medical billing claims weekly\n  and corrected denials before resubmission.'
        second = '• Reconciled payer remittances and documented patient payment plans.'
        resume = f'Fictional candidate\nsample@example.com\n\n{first}\fPAGE TWO\n{second}'

        def provider(request, **kwargs):
            payload = json.loads(request.data)
            inputs = json.loads(payload['input'])
            self.assertNotIn('sample@example.com', payload['input'])
            self.assertIn('set evidence_id', payload['instructions'])
            self.assertNotIn('For job matching', payload['instructions'])
            passages = {passage['text']: passage['id'] for passage in inputs['resume_passages']}
            fields = payload['text']['format']['schema']['properties']
            for section in ('skills', 'roles', 'adjacent_roles', 'cautions'):
                self.assertEqual(fields[section]['items']['properties']['evidence_id'],
                                 {'type': 'integer', 'enum': list(passages.values())})
            result = dict(summary='Fictional medical billing experience.',
                          skills=[dict(label='Denial management', kind='stated', evidence_id=passages[first])],
                          roles=[dict(title='Patient Accounts Specialist', reason='Reconciles payer remittances.',
                                      evidence_id=passages[second])], adjacent_roles=[], cautions=[])
            return BytesIO(json.dumps(dict(status='completed', output=[dict(content=[
                dict(type='output_text', text=json.dumps(result))])])).encode())

        cfg = dict(self.a.config(), ai_enabled=True)
        with patch.object(self.a, 'config', return_value=cfg), \
             patch.object(recruiter, 'ai', side_effect=REAL_AI), \
             patch.object(recruiter.prototype, 'ai_key', return_value='fictional-test-token'), \
             patch('urllib.request.urlopen', side_effect=provider) as network:
            result = self.analyze(resume)['strategy']
        network.assert_called_once()
        self.assertEqual(result['skills'][0]['evidence'], first)
        self.assertEqual(result['roles'][0]['evidence'], second)
        self.assertNotIn('evidence_id', json.dumps(result))
        self.assertEqual(result['omitted_unverified'], 0)

    def test_fragmented_resume_keeps_passages_beyond_enum_limit(self):
        early = '\n'.join(f'• Verified transaction batch {index}.' for index in range(120))
        late = '• Reconciled patient billing and payer remittances.'

        def provider(a, name, inputs, schema):
            last = inputs['resume_passages'][-1]
            self.assertEqual(last, {'id': 121, 'text': late})
            self.assertEqual(schema['properties']['skills']['items']['properties']['evidence_id'],
                             {'type': 'integer'})
            return dict(summary='Fictional medical billing experience.',
                        skills=[dict(label='Payment reconciliation', kind='stated', evidence_id=last['id'])],
                        roles=[dict(title='Medical Biller', reason='Reconciles payments.', evidence_id=last['id'])],
                        adjacent_roles=[], cautions=[])

        with patch.object(recruiter, 'ai', side_effect=provider):
            result = self.analyze(f'{early}\f{late}')['strategy']
        self.assertEqual(result['skills'][0]['evidence'], late)

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
        board_progress, compact_progress, comparison_progress = [], [], []
        board_jobs = self.a.board_jobs
        actual_match = recruiter.match

        def observed_board(platform, board):
            board_progress.append(recruiter.read(self.a)['progress'])
            compact_progress.append(recruiter.read(self.a, status_only=True))
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
        self.assertEqual(compact_progress[0], dict(version=failed['version'], stage='discovering',
                                                    progress=board_progress[0], stop_requested=False))
        self.assertGreaterEqual(len(comparison_progress), 2)
        self.assertTrue(all(p['stage'] == 'Comparing jobs with your experience' for p in comparison_progress))
        self.assertTrue(all(p['total'] == 5 for p in comparison_progress))
        self.assertEqual(failed['progress']['completed'], len(failed['matches']))

        completed = self.search()
        events = list(reversed(recruiter.activity(self.a)['entries']))
        failed_events = [entry for entry in events if entry['operation'] == failed['version']]
        self.assertEqual(failed_events[0]['progress']['stage'], 'Preparing search')
        self.assertEqual(failed_events[-1]['progress']['reason'], 'The AI service timed out.')
        self.assertEqual(events[-1]['operation'], completed['version'])
        self.assertEqual(events[-1]['progress']['stage'], 'Search complete')
        self.assertEqual(events[-1]['progress']['completed'], 5)
        self.assertNotIn(MARA, json.dumps(events))
        earlier = recruiter.activity(self.a, before=failed_events[-1]['id'])['entries']
        self.assertEqual(earlier[0]['id'], failed_events[-2]['id'])

    def test_search_compares_in_parallel_with_operation_context(self):
        state = self.analyze()
        barrier = threading.Barrier(recruiter.MATCH_WORKERS, timeout=5)
        lock = threading.Lock()
        started = []
        actual_match = recruiter.match

        def observed_match(a, search_state, job):
            with lock:
                started.append((job['id'], recruiter.OPERATION.get()))
                initial_batch = len(started) <= recruiter.MATCH_WORKERS
            if initial_batch:
                barrier.wait()
            return actual_match(a, search_state, job)

        with patch.object(recruiter, 'match', side_effect=observed_match):
            result = self.search()
        self.assertEqual(len(started), len(result['matches']))
        self.assertEqual(len({job_id for job_id, _ in started}), len(started))
        self.assertTrue(all(operation == result['version'] for _, operation in started))
        self.assertEqual(result['progress']['completed'], len(result['matches']))

    def test_stop_during_comparison_preserves_completed_and_previous_results(self):
        self.analyze(); previous = self.search()
        entered = threading.Event()
        release = threading.Event()
        actual_match = recruiter.match
        calls = []
        lock = threading.Lock()

        def delayed_match(a, state, job):
            with lock:
                calls.append(job['id'])
                should_fail = len(calls) == 1
                if len(calls) == recruiter.MATCH_WORKERS:
                    entered.set()
            if not release.wait(5):
                raise AssertionError('Test timed out waiting for release')
            if should_fail:
                raise recruiter.AIRequestError('Fictional provider error')
            return actual_match(a, state, job)

        with patch.object(recruiter, 'match', side_effect=delayed_match):
            self.assertEqual(recruiter.start(self.a, dict(action='search', version=previous['version'], preferences=PREFS))[0], 202)
            self.assertTrue(entered.wait(5))
            current = recruiter.read(self.a, True)
            self.assertEqual(recruiter.start(self.a, dict(action='stop', version=current['version']))[0], 202)
            self.assertTrue(recruiter.read(self.a, status_only=True)['stop_requested'])
            self.assertEqual(recruiter.start(self.a, dict(action='stop', version=previous['version']))[0], 409)
            token = recruiter.OPERATION.set(current['version'])
            try:
                cfg = dict(self.a.config(), ai_enabled=True)
                with patch.object(self.a.prototype, 'ai_key', return_value='fictional'), \
                     patch.object(self.a, 'config', return_value=cfg):
                    with self.assertRaises(recruiter.SearchStopped):
                        REAL_AI(self.a, 'candidate_match', {}, recruiter.MATCH)
            finally:
                recruiter.OPERATION.reset(token)
                release.set()
            stopped = self.wait()
        self.assertEqual(stopped['stage'], 'stopped')
        self.assertEqual(len(calls), recruiter.MATCH_WORKERS)
        self.assertEqual({m['job_id'] for m in stopped['matches']}, {m['job_id'] for m in previous['matches']})
        self.assertEqual(self.search()['stage'], 'complete')

    def test_stop_during_discovery_retains_prior_shortlist(self):
        self.analyze(); previous = self.search()
        entered, release = threading.Event(), threading.Event()
        original_board_jobs = self.a.board_jobs

        def delayed_board(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError('Test timed out waiting for release')
            return original_board_jobs(*args, **kwargs)

        with patch.object(self.a, 'board_jobs', side_effect=delayed_board):
            self.assertEqual(recruiter.start(self.a, dict(action='search', version=previous['version'], preferences=PREFS))[0], 202)
            self.assertTrue(entered.wait(5))
            current = recruiter.read(self.a, True)
            self.assertEqual(recruiter.start(self.a, dict(action='stop', version=current['version']))[0], 202)
            release.set()
            stopped = self.wait()
        self.assertEqual(stopped['stage'], 'stopped')
        self.assertEqual([m['job_id'] for m in stopped['matches']], [m['job_id'] for m in previous['matches']])

    def test_http_stop_returns_before_stalled_employer_and_keeps_results(self):
        self.analyze()
        previous = self.search()
        entered, release = threading.Event(), threading.Event()

        def stall(seconds):
            entered.set()
            release.wait(5)

        def request(method, path, body=None):
            with_connection = HTTPConnection(*server.server_address, timeout=2)
            try:
                with_connection.request(method, path, json.dumps(body) if body is not None else None,
                                        {'X-Jobs-Client': 'dashboard'})
                response = with_connection.getresponse()
                return response.status, json.load(response)
            finally:
                with_connection.close()

        with self.a.ThreadingHTTPServer(('127.0.0.1', 0), self.a.Handler) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with patch.object(self.a, 'board_jobs', side_effect=lambda *_: self.a.network_call(stall)):
                    self.assertEqual(request('POST', '/api/recruiter', dict(
                        action='search', version=previous['version'], preferences=PREFS))[0], 202)
                    self.assertTrue(entered.wait(2))
                    _, current = request('GET', '/api/recruiter?status=1')
                    self.assertEqual(current['stage'], 'discovering')
                    self.assertEqual(request('POST', '/api/recruiter', dict(
                        action='stop', version=current['version']))[0], 202)
                    self.assertTrue(recruiter.LOCK.acquire(timeout=2))
                    recruiter.LOCK.release()
                    _, result = request('GET', '/api/recruiter')
                    self.assertEqual(result['stage'], 'stopped')
                    self.assertEqual(result['matches'], previous['matches'])
                    self.assertEqual(request('GET', '/api/v1/search-status')[1]['run']['state'], 'stopped')
                    self.assertFalse(self.a.LOCK.locked())
                with patch.object(self.a, 'connect', side_effect=self.a.postgres_store.Unavailable):
                    self.assertEqual(request('GET', '/api/v1/dashboard')[0], 503)
                    self.assertEqual(request('GET', '/api/v1/health')[0], 200)
            finally:
                release.set()
                server.shutdown()
                thread.join()

    def test_restart_distinguishes_an_accepted_stop_and_recovers_prior_shortlist(self):
        self.analyze()
        previous = self.search()
        for stop_requested, expected in ((False, 'interrupted'), (True, 'stopped')):
            with self.subTest(expected=expected):
                state = recruiter.read(self.a, True)
                state.update(version=state['version'] + 1, stage='matching',
                             previous_matches=state['matches'], matches=[])
                recruiter.write(self.a, state)
                with self.a.connect() as c:
                    c.execute('INSERT INTO runs(started,state,report,trigger) VALUES(?,?,?,?)',
                              (self.a.now(), 'running', json.dumps({'recruiter_version': state['version']}), 'recruiter'))
                if stop_requested:
                    self.assertEqual(recruiter.stop(self.a, {'version': state['version']})[0], 202)
                self.a.init()
                current = recruiter.read(self.a)
                self.assertEqual(current['stage'], expected)
                self.assertEqual(recruiter.read(self.a, status_only=True), dict(
                    version=current['version'], stage=expected, progress=current['progress']))
                self.assertEqual(self.a.search_status()['run']['state'], expected)
                self.assertEqual(current['matches'], previous['matches'])
                self.assertNotIn('previous_matches', current)

    def test_comparison_limit_prioritizes_relevant_eligible_jobs_with_comparable_pay(self):
        self.analyze()
        self.search()
        job = next(j for j in self.a.records() if j['requisition'] == 'billing')
        low = dict(job, requisition='low', url='https://jobs.lever.co/fictional-clinic/low',
                   salary_min=55000, salary_max=65000, salary_text='USD 55,000–65,000 per year')
        with self.a.connect() as c:
            low_id, _ = self.a.upsert(c, low)
            for index in range(26):
                self.a.upsert(c, dict(job, title='Fictional Office Analyst', description='Handle office inventory.',
                                     requisition=f'office-{index}',
                                     url=f'https://jobs.lever.co/fictional-clinic/office-{index}'))

        def no_new_jobs(*args, **kwargs):
            self.a.LOCK.release()
            return {'state': 'success'}

        with patch.object(self.a, 'run_pipeline', side_effect=no_new_jobs), \
             patch.object(recruiter.prototype, 'unlimited_personal_testing', return_value=False):
            result = self.search()
            state = recruiter.read(self.a)
            self.assertEqual(recruiter.start(self.a, dict(action='search', version=state['version'],
                preferences=dict(PREFS, flexible=True)))[0], 202)
            flexible = {match['job_id']: match for match in self.wait()['matches']}
        self.assertGreater(result['deferred'], 0)
        by_id = {match['job_id']: match for match in result['matches']}
        self.assertEqual(by_id[job['id']]['group'], 'close')
        self.assertTrue(by_id[job['id']]['published_pay_target_match'])
        self.assertNotIn(low_id, by_id)
        self.assertIn(low_id, {record['id'] for record in self.a.records()})
        self.assertEqual(flexible[low_id]['group'], 'close')
        self.assertFalse(flexible[low_id]['published_pay_target_match'])

    def test_recruiter_status_loads_settings_once_for_the_shortlist(self):
        self.analyze()
        expected = self.search()
        self.assertGreater(len(expected['matches']), 1)
        with patch.object(self.a, 'config', wraps=self.a.config) as load_settings:
            refreshed = recruiter.read(self.a)
        self.assertEqual(refreshed['matches'], expected['matches'])
        load_settings.assert_called_once()
        self.assertIn('connection', load_settings.call_args.kwargs)
        with patch.object(self.a, 'records', side_effect=AssertionError('Status must not load jobs')), \
             patch.object(self.a, 'config', side_effect=AssertionError('Status must not load settings')):
            status = recruiter.read(self.a, status_only=True)
        self.assertEqual(status, {key: expected.get(key) for key in ('version', 'stage', 'progress')})

    def test_recruiter_reads_reuse_one_database_connection(self):
        self.analyze()
        expected = self.search()
        with patch.object(self.a, 'connect', wraps=self.a.connect) as connect:
            refreshed = recruiter.read(self.a)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(refreshed['matches'], expected['matches'])
        state = recruiter.read(self.a, True)
        state['stage'] = 'matching'
        recruiter.write(self.a, state)
        with patch.object(self.a, 'connect', wraps=self.a.connect) as connect:
            status = recruiter.read(self.a, status_only=True)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(status['stage'], 'matching')
        self.assertFalse(status['stop_requested'])

    def test_compact_status_reads_one_query_without_resumes_or_run_reports(self):
        initial = recruiter.read(self.a, status_only=True)
        self.assertEqual(initial, dict(version=0, stage='empty', progress=None))
        state = recruiter.read(self.a, private=True)
        state.update(version=3, stage='discovering', resume=MARA)
        recruiter.write(self.a, state)
        progress = {'stage': 'Checking employer boards', 'completed': 1, 'total': 3}
        with self.a.connect() as connection:
            recruiter.update_discovery_progress(connection, state['version'], progress)
            recruiter.update_discovery_progress(connection, state['version'] - 1, {'stage': 'Older search'})
        with self.assertRaisesRegex(RuntimeError, 'rollback marker'):
            with self.a.connect() as connection:
                recruiter.update_discovery_progress(connection, state['version'], {'stage': 'Uncommitted'})
                raise RuntimeError('rollback marker')
        self.assertEqual(recruiter.stop(self.a, {'version': state['version']})[0], 202)

        statements = []
        original_connect = self.a.connect

        def traced_connect():
            connection = original_connect()
            connection.set_trace_callback(statements.append)
            return connection

        with patch.object(self.a, 'connect', side_effect=traced_connect):
            status = recruiter.read(self.a, status_only=True)
        self.assertEqual(status, dict(version=3, stage='discovering', progress=progress, stop_requested=True))
        self.assertEqual(len(statements), 1)
        self.assertIn('recruiter_status', statements[0])
        self.assertNotIn('recruiter_state', statements[0])
        self.assertNotIn('runs', statements[0])

    def test_startup_backfills_compact_status_without_changing_existing_recruiter_state(self):
        self.analyze()
        self.search()
        state = recruiter.read(self.a, private=True)
        with self.a.connect() as connection:
            connection.execute('DROP TABLE recruiter_status')
        self.a.init()
        self.assertEqual(recruiter.read(self.a, private=True), state)
        self.assertEqual(recruiter.read(self.a, status_only=True), {
            key: state.get(key) for key in ('version', 'stage', 'progress')})

    def test_saved_match_refresh_reads_only_referenced_listings(self):
        self.analyze()
        expected = self.search()
        job = self.a.records()[0]
        with self.a.connect() as c:
            selected = recruiter.saved_match_listings(self.a, [job['id'], *range(10000, 10210)], connection=c)
        self.assertEqual(list(selected), [job['id']])
        self.assertEqual(selected[job['id']]['title'], job['title'])
        with patch.object(self.a, 'records', side_effect=AssertionError('Unrelated jobs should not be loaded')):
            refreshed = recruiter.read(self.a)
        self.assertEqual(refreshed['matches'], expected['matches'])
        with self.a.connect() as c:
            c.execute('DELETE FROM tracking WHERE job_id=?', (job['id'],))
        self.assertNotIn(job['id'], recruiter.saved_match_listings(self.a, [job['id']]))
        self.assertNotIn(job['id'], [match['job_id'] for match in recruiter.read(self.a)['matches']])

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
        self.assertIn({
            'reason': 'Experience managing managers or team leads needs confirmation.',
            'what_to_check': 'Check whether your résumé documents responsibility for managing managers or team leads.',
        }, saved[director['id']]['confirmation_reasons'])

    def test_confirmation_explains_the_posting_blocker_without_repeating_passed_checks(self):
        self.analyze(); self.search()
        state = recruiter.read(self.a, private=True)
        job = next(job for job in self.a.records() if job['requisition'] == 'billing')
        stale = dict(job, posting_verified=False)
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Cached matches need no AI call')):
            match = recruiter.match(self.a, state, stale)
        self.assertEqual(match['group'], 'review')
        self.assertIn('The exact employer posting needs verification.', match['checks'])
        self.assertGreater(len(match['checks']), 1)
        self.assertEqual(match['confirmation_reasons'], [{
            'reason': 'The exact employer posting needs verification.',
            'what_to_check': 'Open the employer’s careers page and confirm the same job is still open and accepting applications.',
        }])

    def test_required_confirmation_uses_the_posting_and_is_rebuilt_from_cache(self):
        self.analyze(); self.search()
        state = recruiter.read(self.a, private=True)
        job = next(job for job in self.a.records() if job['requisition'] == 'billing')
        job['description'] = ('Review denial queues and coach billing specialists.\n'
                              'Required qualifications: An active medical coding license.\n'
                              'Preferred qualifications: A healthcare analytics certificate.')
        with self.a.connect() as connection:
            self.a.upsert(connection, job)
        response = dict(
            group='close', reason='Billing and coaching duties are documented.', emphasis=[],
            resume_evidence='Reviewed denial queues',
            job_evidence='Review denial queues and coach billing specialists.',
            gaps=[
                {'detail': 'Active medical coding license is unverified.', 'kind': 'preferred',
                 'employer_quote': 'An active medical coding license.'},
                {'detail': 'Healthcare analytics certificate is unverified.', 'kind': 'required',
                 'employer_quote': 'A healthcare analytics certificate.'},
                {'detail': 'PMP certification is unverified.', 'kind': 'required', 'employer_quote': ''},
            ],
        )
        with patch.object(recruiter, 'ai', return_value=response):
            match = recruiter.match(self.a, state, job)
        self.assertEqual(match['group'], 'review')
        expected = [{
            'reason': 'The employer’s requirement needs confirmation. “An active medical coding license.”',
            'what_to_check': 'Check whether your résumé documents this qualification or an alternative the employer accepts.',
        }]
        self.assertEqual(match['confirmation_reasons'], expected)
        self.assertEqual([gap['kind'] for gap in match['gap_evidence']], ['required', 'preferred', 'unclear'])
        match.pop('confirmation_reasons')
        state['matches'] = [match]
        recruiter.write(self.a, state)
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Refreshing matches needs no AI call')):
            refreshed = recruiter.read(self.a)['matches'][0]
        self.assertEqual(refreshed['confirmation_reasons'], expected)

    def test_cached_quote_lists_remove_only_reverified_evidence_checks(self):
        self.analyze()
        self.search()
        state = recruiter.read(self.a, private=True)
        job = next(j for j in self.a.records() if j['requisition'] == 'billing')
        job['description'] = 'Review denial queues. Follow privacy rules. Coach billing specialists.'
        with self.a.connect() as c:
            self.a.upsert(c, job)

        response = dict(group='close', reason='Documented billing and coaching work.', gaps=[], emphasis=[],
                        resume_evidence='"15 years in medical billing and revenue cycle."\n"Reviewed denial queues"',
                        job_evidence='"Review denial queues."\n"Coach billing specialists."')
        with patch.object(recruiter, 'ai', return_value=response):
            match = recruiter.match(self.a, state, job)
        self.assertEqual(match['group'], 'close')

        stale_checks = list(recruiter.COMPARISON_EVIDENCE_ERRORS.values())
        old_match = dict(match, group='review', fit_group='review', resume_evidence='', job_evidence='',
                         evidence_checks=stale_checks)
        state['matches'] = [old_match]
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Unexpected paid comparison')):
            recruiter.write(self.a, state)
            restored = recruiter.read(self.a)['matches'][0]
            self.assertEqual(restored['group'], 'close')
            self.assertEqual(restored['evidence_checks'], [])
            self.assertEqual(restored['confirmation_reasons'], [])
            for field in recruiter.COMPARISON_EVIDENCE_ERRORS:
                self.assertEqual(restored[field], response[field])

            old_match['evidence_checks'] = stale_checks + ['An unrelated evidence check.']
            recruiter.write(self.a, state)
            restored = recruiter.read(self.a)['matches'][0]
            self.assertEqual(restored['group'], 'review')
            self.assertEqual(restored['evidence_checks'], ['An unrelated evidence check.'])

            key, _, _ = recruiter.match_cache_keys(state['strategy'], recruiter.match_facts(job),
                                                    self.a.config()['ai_model'], state['resume'])
            with self.a.connect() as c:
                c.execute('UPDATE recruiter_match_cache SET value=? WHERE fingerprint=?',
                          (json.dumps(dict(response, job_evidence='"Review denial queues."\n"Fabricated duty."')), key))
            old_match['evidence_checks'] = stale_checks
            recruiter.write(self.a, state)
            restored = recruiter.read(self.a)['matches'][0]
            self.assertEqual(restored['group'], 'review')
            self.assertEqual(restored['resume_evidence'], response['resume_evidence'])
            self.assertEqual(restored['job_evidence'], '')
            self.assertEqual(restored['evidence_checks'], [recruiter.COMPARISON_EVIDENCE_ERRORS['job_evidence']])

    def test_search_rechecks_the_employer_posting_for_a_strong_match(self):
        self.analyze()
        self.search()
        job = next(j for j in self.a.records() if j['requisition'] == 'billing')
        job.update(availability='Needs Verification', posting_check_failed=True)
        job.pop('posting_verified', None)
        with self.a.connect() as c:
            self.a.upsert(c, job)

        def pipeline(*_args, **_kwargs):
            self.a.LOCK.release()
            return {'state': 'success'}

        def recheck(job_ids, _cfg, *, should_stop):
            self.assertIn(job['id'], job_ids)
            self.assertFalse(should_stop())
            checked = dict(job, availability='Open', posting_verified=self.a.now(), posting_check_failed=False)
            with self.a.connect() as c:
                self.a.upsert(c, checked)
            return {job['id']: checked}

        with patch.object(self.a, 'run_pipeline', side_effect=pipeline), \
             patch.object(self.a, 'recheck_recruiter_postings', side_effect=recheck):
            results = self.search()
        saved = next(item for item in results['matches'] if item['job_id'] == job['id'])
        self.assertEqual(saved['group'], 'close')
        self.assertNotIn('The exact employer posting needs verification.', saved['checks'])

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

    def test_market_pay_accepts_common_cited_range_formats_without_inventing_sources(self):
        text = 'Market research\nGeography: Virginia, U.S.\nData period: May 2025\nRange: $55,000 to $78,000 per year.'
        note = dict(type='url_citation', url='https://example.com/wages', title='Fictional data',
                    start_index=text.index('$55,000'), end_index=len(text))
        output = [dict(type='web_search_call', status='completed', action={'type': 'search'}),
                  dict(type='message', content=[dict(type='output_text', text=text, annotations=[note])])]
        result = recruiter.researched_pay(output)
        self.assertEqual((result['salary_min'], result['salary_max']), (55000, 78000))
        self.assertEqual(result['citations'][0]['url'], 'https://example.com/wages')
        note.update(start_index=0, end_index=text.index('Range:'))
        self.assertEqual(recruiter.researched_pay(output), {'summary': None, 'citations': []})
        note.update(start_index=text.index('$55,000'), end_index=len(text), url='http://example.com/wages')
        self.assertEqual(recruiter.researched_pay(output), {'summary': None, 'citations': []})

    def test_search_researches_comparable_pay_once_and_keeps_matches_on_failure(self):
        self.analyze(); self.search()
        job = next(j for j in self.a.records() if j['requisition'] == 'billing')
        job.update(salary_min=None, salary_max=None, salary_text='Pay not disclosed')
        with self.a.connect() as c:
            self.a.upsert(c, job)
            twin = dict(job, requisition='billing-twin',
                        url='https://jobs.lever.co/fictional-clinic/billing-twin')
            twin['id'], _ = self.a.upsert(c, twin)
            unverified = dict(job, requisition='unverified', title='Medical Billing Coordinator',
                              url='https://jobs.lever.co/fictional-clinic/unverified', posting_verified=None)
            unverified_id, _ = self.a.upsert(c, unverified)

        def pipeline(*args, **kwargs):
            self.a.LOCK.release()
            return {'state': 'complete'}

        estimate = dict(summary='Fictional estimate', geography='Oregon', data_period='2025',
                        salary_min=70000, salary_max=90000, salary_period='year',
                        citations=[dict(title='Wages', url='https://example.com/wages', end=1)])

        def provider(a, name, inputs, schema):
            if name == 'market_pay':
                return estimate
            return fake_ai(a, name, inputs, schema)

        with patch.object(self.a, 'run_pipeline', side_effect=pipeline), \
             patch.object(self.a, 'recheck_recruiter_postings', return_value={}), \
             patch.object(recruiter, 'ai', side_effect=provider) as mock:
            result = self.search()
        self.assertEqual(sum(call.args[1] == 'market_pay' for call in mock.call_args_list), 1)
        matched = [m for m in result['matches'] if m['job_id'] in (job['id'], twin['id'])]
        self.assertEqual(len(matched), 2)
        self.assertTrue(all(m['market_pay_target_match'] for m in matched))
        unchecked, = (m for m in result['matches'] if m['job_id'] == unverified_id)
        self.assertEqual(unchecked['group'], 'review')
        self.assertIsNone(unchecked['market_pay_target_match'])

        with self.a.connect() as c:
            c.execute("DELETE FROM recruiter_match_cache WHERE fingerprint LIKE 'market-pay:%'")

        def failure(a, name, inputs, schema):
            if name == 'market_pay':
                raise recruiter.AIRequestError('Fictional outage')
            return fake_ai(a, name, inputs, schema)

        with patch.object(self.a, 'run_pipeline', side_effect=pipeline), \
             patch.object(self.a, 'recheck_recruiter_postings', return_value={}), \
             patch.object(recruiter, 'ai', side_effect=failure):
            result = self.search()
        self.assertEqual(result['stage'], 'complete')
        self.assertEqual(len([m for m in result['matches'] if m['job_id'] in (job['id'], twin['id'])]), 2)
        self.assertTrue(any(entry['progress']['stage'] == 'Some market pay research could not finish'
                            for entry in recruiter.activity(self.a)['entries']))

    def test_search_researches_pay_for_review_match_eligible_for_promotion(self):
        self.analyze(); self.search()
        state = recruiter.read(self.a, True)
        state['resume'] += ' Reviewed medical billing records.'
        recruiter.write(self.a, state)
        job = next(j for j in self.a.records() if j['requisition'] == 'billing')
        job.update(salary_min=None, salary_max=None, salary_text='Pay not disclosed',
                   description='Responsibilities\nReview medical billing records.')
        with self.a.connect() as c:
            self.a.upsert(c, job)
        comparison = dict(group='review', reason='Related billing experience.', gaps=[],
                          resume_evidence='Reviewed medical billing records.',
                          job_evidence='Review medical billing records.', emphasis=[])
        estimate = dict(summary='Fictional estimate', geography='Oregon', data_period='2025',
                        salary_min=70000, salary_max=90000, salary_period='year',
                        citations=[dict(title='Wages', url='https://example.com/wages', end=1)])
        def pipeline(*args, **kwargs):
            self.a.LOCK.release()
            return {'state': 'complete'}
        def provider(a, name, inputs, schema):
            if name == 'market_pay':
                return estimate
            if inputs['job']['title'] == job['title']:
                return comparison
            return fake_ai(a, name, inputs, schema)
        with patch.object(self.a, 'run_pipeline', side_effect=pipeline), \
             patch.object(recruiter, 'ai', side_effect=provider) as mock:
            result = self.search()
        found = next(m for m in result['matches'] if m['job_id'] == job['id'])
        self.assertEqual(found['group'], 'adjacent')
        self.assertTrue(found['market_pay_target_match'])
        self.assertEqual(sum(call.args[1] == 'market_pay' for call in mock.call_args_list), 1)

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
        self.assertEqual(len(state['matches']), 5)
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
        with self.a.connect() as c:
            for index in range(15):
                self.a.upsert(c, dict(url=f'https://example.com/fictional/{index}', title='Fictional Analyst',
                                    employer='Fictional Employer', location='Portland, Oregon',
                                    workplace_type='onsite', availability='Open'))
        def finish_search(*args, **kwargs):
            self.a.LOCK.release()
            return {'state': 'success'}
        with patch.dict('os.environ', {'JOBS_PERSONAL_UNLIMITED_AI': '1'}), \
             patch.object(self.a, 'run_pipeline', side_effect=finish_search), \
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

    def test_optional_position_levels_and_maximum_pay_preferences(self):
        self.assertEqual(recruiter.preferences({'preferences': PREFS}), PREFS)
        for change in (
            {'levels': [], 'salary_ceiling': None},
            {'levels': ['entry', 'mid', 'senior', 'management', 'executive'], 'salary_ceiling': 90000},
            {'salary_ceiling': PREFS['salary']},
            {'period': 'hour', 'salary': 25, 'salary_ceiling': 40},
        ):
            with self.subTest(change=change):
                saved = dict(PREFS, **change)
                self.assertEqual(recruiter.preferences({'preferences': saved}), saved)
        for change in (
            {'levels': 'entry'}, {'levels': [None]}, {'levels': [[]]}, {'levels': ['associate']},
            {'salary_ceiling': 0}, {'salary_ceiling': -1}, {'salary_ceiling': True},
            {'salary_ceiling': 90_000.0}, {'salary_ceiling': '90000'},
            {'salary_ceiling': PREFS['salary'] - 1, 'flexible': True},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                recruiter.preferences({'preferences': dict(PREFS, **change)})

    def test_position_level_uses_explicit_job_evidence_and_keeps_ambiguity_eligible(self):
        selected = dict(PREFS, levels=['entry', 'mid'])
        examples = (
            ('Junior Help Desk Technician', '', 'entry'),
            ('Billing Analyst', 'Experience level: Mid-level', 'mid'),
            ('Sr. Billing Analyst', '', 'senior'),
            ('Director of Customer Support', '', 'management'),
            ('Vice President, Billing Operations', '', 'executive'),
            ('Senior Project Manager', 'Manage customer deadlines.', 'senior'),
            ('Project Manager', 'You will have seven direct reports.', 'management'),
            ('Account Manager', 'You will have no direct reports.', None),
            ('Project Manager', 'Manage timelines, vendors, and deliverables.', None),
            ('Billing Analyst II', 'Reports to the senior billing director.', None),
            ('Senior Living Account Manager', 'Manage accounts for retirement homes.', None),
            ('Junior Analyst', 'Seniority: Senior', None),
        )
        for title, description, level in examples:
            with self.subTest(title=title, description=description):
                job = dict(title=title, description=description)
                self.assertEqual(recruiter.position_level(self.a, job), level)
                checks = recruiter.comparison_guardrails(self.a, job, selected)
                expected = 'avoid' if level and level not in selected['levels'] else 'close'
                self.assertEqual(recruiter.checked_group('close', checks), expected)
                if level is None:
                    self.assertTrue(any('did not clearly indicate' in reason for _, reason in checks))

    def test_maximum_pay_uses_comparable_employer_minimum_even_when_flexible(self):
        selected = dict(PREFS, salary_ceiling=90000, flexible=True)
        job = dict(title='Billing Analyst', salary_min=92000, salary_max=105000,
                   salary_currency='USD', salary_period='year', salary_type='base')
        for change, expected in (
            ({}, 'avoid'), ({'salary_max': None}, 'avoid'),
            ({'salary_min': 90000}, 'close'), ({'salary_min': 80000}, 'close'),
            ({'salary_min': None}, 'close'), ({'salary_currency': 'CAD'}, 'close'),
            ({'salary_period': 'hour'}, 'close'), ({'salary_type': 'total'}, 'close'),
            ({'salary_min': None, 'salary_max': None, 'market_pay': {'salary_min': 95000}}, 'close'),
        ):
            with self.subTest(change=change):
                checks = recruiter.comparison_guardrails(self.a, dict(job, **change), selected)
                self.assertEqual(recruiter.checked_group('close', checks), expected)
        hourly = dict(PREFS, salary=28, period='hour', salary_ceiling=40)
        self.assertIs(recruiter.published_pay_ceiling_match(
            self.a, dict(job, salary_min=42, salary_max=47, salary_period='hour'), hourly), False)
        self.assertIs(recruiter.published_pay_ceiling_match(
            self.a, dict(job, salary_min=40, salary_max=47, salary_period='hour'), hourly), True)
        self.assertIsNone(recruiter.published_pay_ceiling_match(
            self.a, dict(job, salary_min=None, salary_max=47, salary_period='hour'), hourly))
        self.assertIsNone(recruiter.published_pay_ceiling_match(
            self.a, dict(job, salary_min=42, salary_max=47, salary_period='hour'), PREFS))

    def test_ranking_prioritizes_eligible_jobs_without_dropping_guardrail_misses(self):
        posting = dict(title='Billing Analyst', employer='Fictional Employer', description='Review denial queues.',
                       location_eligibility='Eligible', category='Billing', matched_duty_count=1,
                       score=80, salary_min=80000, salary_max=100000, salary_currency='USD',
                       salary_period='year', salary_type='base')
        senior = dict(posting, id=1, title='Senior Billing Analyst', score=100)
        above_maximum = dict(posting, id=2, salary_min=95000, score=100)
        eligible = dict(posting, id=3, title='Mid-level Billing Analyst')
        unknown_level = dict(posting, id='fictional-opening-hash', title='Billing Account Manager')
        cfg = dict(categories=['Billing Analyst'], salary_floor=PREFS['salary'],
                   recruiter_pay=dict(PREFS, levels=['mid'], salary_ceiling=90000))
        ordered = recruiter.rank_openings(self.a, [senior, above_maximum, eligible, unknown_level], cfg)
        self.assertEqual({job['id'] for job in ordered[:2]}, {3, 'fictional-opening-hash'})
        self.assertEqual({job['id'] for job in ordered[2:]}, {1, 2})


    def test_ranking_varies_target_roles_employers_and_arrangements_at_similar_fit(self):
        common = dict(description='Review denial queues.', category='Billing', location_eligibility='Eligible',
                      matched_duty_count=2, score=75, salary_min=80000, salary_max=90000,
                      salary_currency='USD', salary_period='year', salary_type='base', workplace_type='remote')
        postings = [dict(common, id=1, title='Revenue Cycle Denials Analyst', employer='Fictional Health', posted='2026-10-31'),
                    dict(common, id=2, title='Healthcare Revenue Cycle Analyst', employer='Fictional Clinic', posted='2026-10-30'),
                    dict(common, id=3, title='Patient Accounts Analyst', employer='Fictional Health', posted='2026-10-29'),
                    dict(common, id=4, title='Claims Operations Analyst', employer='Fictional Insurer', posted='2026-10-28'),
                    dict(common, id=5, title='Medical Billing Analyst', employer='Fictional Local', posted='2026-10-27',
                         workplace_type='hybrid'),
                    dict(common, id=6, title='Payment Processing Analyst', employer='Fictional Other', posted='2026-10-31',
                         workplace_type='onsite', matched_duty_count=1, score=100)]
        cfg = dict(salary_floor=PREFS['salary'], recruiter_pay=PREFS,
                   categories=['Revenue Cycle Analyst', 'Patient Accounts Analyst', 'Claims Operations Analyst',
                               'Medical Billing Analyst', 'Payment Processing Analyst'])
        ranked = recruiter.rank_openings(self.a, postings, cfg)
        self.assertEqual([job['id'] for job in ranked[:3]], [1, 5, 4])
        self.assertEqual(ranked[-1]['id'], 6)

    def test_comparison_queue_skips_known_misses_and_keeps_them_browsable(self):
        self.analyze()
        state = recruiter.read(self.a, private=True)
        state['preferences'] = dict(PREFS, modes=['remote', 'onsite'], levels=['mid'], salary_ceiling=100000)
        base = dict(title='Revenue Cycle Supervisor', employer='Fictional Clinic', location='Remote - United States',
                    workplace_type='remote', availability='Open', description='Review denial queues and coach billing staff.')
        comparable = dict(salary_currency='USD', salary_period='year', salary_type='base')
        changes = {
            'eligible': {},
            'unknown': dict(workplace_type=None, location='Portland, Oregon'),
            'conflict': dict(workplace_type='onsite'),
            'wrong-city': dict(workplace_type='onsite', location='Denver, Colorado'),
            'wrong-arrangement': dict(workplace_type='hybrid', location='Portland, Oregon'),
            'wrong-state': dict(location='Remote - United States, excluding Oregon'),
            'wrong-country': dict(location='Remote - Canada'),
            'low-pay': dict(comparable, salary_min=40000, salary_max=50000),
            'low-pay-text': dict(description='Review denial queues. Annual base salary: $40,000 to $50,000.'),
            'high-pay': dict(comparable, salary_min=110000, salary_max=150000),
            'wrong-level': dict(title='Senior Revenue Cycle Supervisor'),
            'closed': dict(availability='Closed'),
        }
        recruiter.recruiter_openings.capture(self.a, [dict(base, **fields, url=f'https://example.com/{name}')
                                                    for name, fields in changes.items()], 1)

        def queued():
            cfg = recruiter.search_config(self.a, state)
            queue, deferred = recruiter.comparison_queue(self.a, state, cfg, 1)
            self.assertEqual(deferred, 0)
            return {job['url'].rsplit('/', 1)[-1]: job['location_eligibility'] for job in queue}

        strict = queued()
        self.assertEqual(strict, {'eligible': 'Eligible', 'unknown': 'Review', 'conflict': 'Review'})
        state['preferences']['flexible'] = True
        self.assertEqual(set(queued()), {*strict, 'low-pay', 'low-pay-text'})
        browsable = recruiter.recruiter_openings.page(self.a)['openings']
        self.assertEqual({job['posting_url'].rsplit('/', 1)[-1] for job in browsable}, set(changes))

    def test_comparison_queue_expands_fresh_coverage_with_fixed_caps(self):
        self.analyze()
        state = dict(recruiter.read(self.a, private=True), preferences=PREFS)
        cfg = recruiter.search_config(self.a, state)
        base = dict(title='Revenue Cycle Supervisor', employer='Fictional Clinic', location='Remote - United States',
                    workplace_type='remote', availability='Open', description='Review denial queues and coach billing staff.')
        recruiter.recruiter_openings.capture(self.a, [dict(base, url=f'https://example.com/{index}')
                                                    for index in range(120)], 1)
        for personal, maximum in ((False, 24), (True, 100)):
            with self.subTest(personal=personal), \
                    patch.object(recruiter.prototype, 'unlimited_personal_testing', return_value=personal), \
                    patch.object(recruiter, 'ai', side_effect=AssertionError('Queue cannot call the provider')):
                selected, deferred = recruiter.comparison_queue(self.a, state, cfg, 1)
            self.assertEqual(len(selected), maximum)
            self.assertEqual(deferred, 120 - maximum)

    def test_standard_comparison_keeps_cached_jobs_after_daily_headroom_is_used(self):
        self.analyze()
        state = dict(recruiter.read(self.a, private=True), preferences=PREFS)
        cfg = dict(recruiter.search_config(self.a, state), ai_enabled=True, ai_daily_limit=3)
        base = dict(title='Revenue Cycle Supervisor', employer='Fictional Clinic', location='Remote - United States',
                    workplace_type='remote', availability='Open', description='Review denial queues and coach billing staff.')
        first = dict(base, url='https://example.com/first', posted='2026-10-31')
        second = dict(base, description='Review denial queues and record claims.', posted='2026-10-30',
                      url='https://example.com/second')
        cached = dict(base, description='Review denial queues and track aged claims.', posted='2026-10-29',
                      url='https://example.com/cached')
        duplicate = dict(first, url='https://example.com/duplicate', posted='2026-10-28')
        recruiter.recruiter_openings.capture(self.a, [first, second, cached, duplicate], 1)
        previous_key = recruiter.match_cache_keys(state['strategy'], recruiter.match_facts(cached),
                                                  cfg['ai_model'], state['resume'])[1]
        comparison = dict(group='close', reason='Fictional comparison.', resume_evidence='', job_evidence='',
                          gaps=[], emphasis=[])
        with self.a.connect() as c:
            c.execute('INSERT INTO ai_usage VALUES(?,?)', (self.a.now()[:10], 2))
            c.execute('INSERT INTO recruiter_match_cache VALUES(?,?)', (previous_key, json.dumps(comparison)))
        with patch.object(recruiter.prototype, 'unlimited_personal_testing', return_value=False):
            selected, deferred = recruiter.comparison_queue(self.a, state, cfg, 1)
        self.assertEqual([job['url'] for job in selected], [first['url'], cached['url'], duplicate['url']])
        self.assertEqual(deferred, 1)

    def test_search_explains_an_exhausted_allowance_and_keeps_the_previous_shortlist(self):
        self.analyze()
        first = self.search()
        with patch.object(recruiter, 'comparison_queue', return_value=([], 2)), \
                patch.object(recruiter, 'ai', side_effect=AssertionError('Exhausted daily allowance')):
            retry = self.search()
        self.assertEqual(retry['progress']['stage'], 'Daily comparison limit reached')
        self.assertEqual(retry['deferred'], 2)
        self.assertEqual([recruiter.match_reference(item) for item in retry['matches']],
                         [recruiter.match_reference(item) for item in first['matches']])


if __name__ == '__main__': unittest.main()
