"""Fictional qualification evidence and résumé-bound comparison cache regressions."""
import json
import unittest
from unittest.mock import patch

import recruiter
from fixtures.recruiter_fixture import environment


SERVICE_DUTY = 'Resolve ServiceNow incidents for outpatient clinics.'
DEVICE_DUTY = 'Troubleshoot Microsoft Intune enrollment on Windows laptops.'
DESCRIPTION = f'Responsibilities:\n{SERVICE_DUTY}\n{DEVICE_DUTY}'
RESUME_EVIDENCE = 'Resolved ServiceNow incidents for outpatient clinics.'
RESUME = f'{RESUME_EVIDENCE} Troubleshot Microsoft Intune enrollment on Windows laptops.'
LICENSE = 'A current Florida electrical contractor license is required.'


def gap(detail, quote='', kind='required'):
    return dict(detail=detail, employer_quote=quote, kind=kind)


def comparison(*gaps, group='review', job_evidence=SERVICE_DUTY):
    return dict(group=group, reason='Fictional support duties have transferable evidence.', gaps=list(gaps),
                resume_evidence=RESUME_EVIDENCE, job_evidence=job_evidence, emphasis=[])


class RecruiterRequirementTests(unittest.TestCase):
    def setUp(self):
        self.a, _ = self.enterContext(environment())
        self.assertEqual(self.a.records(), [])
        self.assertEqual(recruiter.read(self.a)['stage'], 'empty')
        self.state = dict(resume=RESUME, strategy=dict(skills=[{'label': 'ServiceNow'}, {'label': 'Microsoft Intune'}]),
                          preferences=dict(modes=['onsite'], commute='Portland, Oregon', salary=65000,
                                           currency='USD', period='year', flexible=False))
        self.job = dict(id=1, title='Technical Support Specialist', employer='Fictional Help Desk',
                        description=DESCRIPTION, location='Portland, Oregon', workplace_type='onsite',
                        availability='Open', posting_verified=self.a.now(), url='https://example.com/role')

    def assess(self, result, **job_changes):
        job = dict(self.job, **job_changes)
        checks = recruiter.comparison_evidence(result, self.state['resume'], job)
        return recruiter.fit_assessment(self.a, result, checks, job, self.state)

    def test_employer_context_overrides_ai_required_or_preferred_labels(self):
        security = gap('The résumé does not show CompTIA Security+ certification.', 'CompTIA Security+ certification.')
        preferred = f'{DESCRIPTION}\nPreferred Qualifications:\n- CompTIA Security+ certification.'
        required = f'{DESCRIPTION}\nMinimum Qualifications:\n- CompTIA Security+ certification.'
        self.assertEqual(self.assess(comparison(security), description=preferred), ('adjacent', []))
        self.assertEqual(self.assess(comparison(security, group='close'), description=preferred), ('close', []))
        self.assertEqual(self.assess(comparison(dict(security, kind='preferred')), description=required)[0], 'review')

    def test_optional_negated_and_unrelated_text_is_not_a_requirement(self):
        examples = (
            ('CompTIA Security+ certification is not required.', 'CompTIA Security+ certification',
             'CompTIA Security+ certification is missing.'),
            ('Preferred Qualifications: A minimum of 5 years of payroll experience.', '5 years of payroll experience',
             'The résumé lacks payroll experience.'),
            ('Benefits:\nAn electrician license is required for our reimbursement program.', 'An electrician license is required',
             'An electrician license is missing.'),
            ('No CompTIA Security+ certification is necessary.', 'CompTIA Security+ certification',
             'CompTIA Security+ certification is missing.'),
            (LICENSE, LICENSE, 'The résumé does not show a bar license in Oregon.'),
            ("A bachelor's degree or equivalent experience is required.", "a bachelor's degree", "No bachelor's degree is shown."),
        )
        for posting_text, quote, detail in examples:
            with self.subTest(posting_text=posting_text, detail=detail):
                result = comparison(gap(detail, quote))
                self.assertEqual(self.assess(result, description=f'{DESCRIPTION}\n{posting_text}'), ('adjacent', []))

    def test_explicit_license_and_years_are_preserved_as_hard_checks(self):
        examples = (
            (LICENSE, 'Florida electrical contractor license', 'Florida electrical contractor license is not documented.'),
            ('At least 5 years of server administration experience.', '5 years of server administration experience',
             'The résumé does not document enough server administration experience.'),
            ('Requirements: CCNA.', 'Requirements: CCNA', 'CCNA is absent.'),
        )
        for employer_text, quote, detail in examples:
            with self.subTest(employer_text=employer_text):
                group, checks = self.assess(comparison(gap(detail, quote, kind='unclear'), group='close'),
                                            description=f'{DESCRIPTION}\n{employer_text}')
                self.assertEqual(group, 'review')
                self.assertIn('requirement or scope gap', ' '.join(checks))

    def test_unconfirmed_gap_does_not_block_a_close_match(self):
        result = comparison(gap('A server certification may be missing.', 'Server certification is required.'))
        self.assertEqual(self.assess(result), ('adjacent', []))
        group, checks = self.assess(result, description=SERVICE_DUTY)
        self.assertEqual(group, 'review')
        self.assertIn('too little verified overlap', ' '.join(checks))
        self.assertEqual(self.assess(dict(result, group='close'), description=SERVICE_DUTY), ('close', []))
        result['job_evidence'] = 'Invented employer duty.'
        self.assertEqual(self.assess(result)[0], 'review')
        self.assertEqual(self.assess(comparison(group='avoid')), ('avoid', []))

    def test_leadership_scope_must_come_from_required_employer_work(self):
        leadership = gap('The résumé does not state experience managing managers.', 'Manage managers and lead multiple teams.')
        result = comparison(leadership)
        title = 'Director of IT Support'
        self.assertEqual(self.assess(result, title=title), ('adjacent', []))
        preferred = f'{DESCRIPTION}\nPreferred Qualifications:\nManage managers and lead multiple teams.'
        self.assertEqual(self.assess(result, title=title, description=preferred), ('adjacent', []))
        actual = f'{DESCRIPTION}\nManage managers and lead multiple teams.'
        self.state['resume'] += ' Never managed managers or led multiple teams.'
        group, checks = self.assess(result, title=title, description=actual)
        self.assertEqual(group, 'review')
        self.assertEqual(len(checks), 2)

    def test_public_gaps_and_cached_schema_keep_verified_posting_gate(self):
        result = comparison(gap('An unverified certification gap.', 'Certification is mandatory.'), group='close')
        self.job.pop('posting_verified')
        with patch.object(recruiter, 'ai', return_value=result) as provider:
            match = recruiter.match(self.a, self.state, self.job)
            self.assertEqual(recruiter.match(self.a, self.state, self.job), match)
        provider.assert_called_once()
        self.assertIs(provider.call_args.args[-1], recruiter.MATCH)
        self.assertEqual(match['gaps'], ['An unverified certification gap.'])
        self.assertEqual(match['gap_evidence'], [gap('An unverified certification gap.', kind='unclear')])
        self.assertEqual(match['fit_group'], 'close')
        self.assertEqual(match['group'], 'review')
        self.assertIn('The exact employer posting needs verification.', match['checks'])

    def test_older_cache_reused_only_if_bound_to_current_resume(self):
        self.job['description'] += f'\n{LICENSE}'
        old_result = comparison('The résumé does not document a Florida electrical contractor license.', group='close')
        digest, legacy, unbound = recruiter.match_cache_keys(
            self.state['strategy'], recruiter.match_facts(self.job), self.a.config()['ai_model'], RESUME)
        self.assertEqual(len({digest, legacy, unbound}), 3)
        with self.a.connect() as c:
            c.execute('INSERT INTO recruiter_match_cache VALUES(?,?)', (legacy, json.dumps(old_result)))
            c.execute('INSERT INTO recruiter_match_cache VALUES(?,?)', (unbound, json.dumps(comparison(group='avoid'))))
        with patch.object(recruiter, 'ai', side_effect=AssertionError('Matching cache needs no provider call')):
            self.assertEqual(recruiter.match(self.a, self.state, self.job)['fit_group'], 'review')

        revised = dict(self.state, resume=RESUME + ' Documented new fictional duties.')
        with patch.object(recruiter, 'ai', return_value=comparison(group='close')) as provider:
            self.assertEqual(recruiter.match(self.a, revised, self.job)['fit_group'], 'close')
        provider.assert_called_once()
