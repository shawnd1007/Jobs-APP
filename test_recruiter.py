import datetime as dt
import unittest
from unittest.mock import patch
import app
import recruiter

class EvidenceTests(unittest.TestCase):
    def config(self):
        return dict(salary_floor=70000, categories=['Analyst'], preferred_skills=['SQL', 'Python'],
                    resume_evidence={'SQL': 'Used SQL to reconcile synthetic accounts'}, verification_valid_hours=24)

    def test_missing_facts_and_truthful_preparation(self):
        result = recruiter.explain({'description': 'SQL and Python'}, self.config())
        self.assertEqual(result['resume_matches'], ['SQL'])
        self.assertEqual(result['selected_without_evidence'], ['Python'])
        self.assertEqual(len(result['unknowns']), 2)
        self.assertEqual(result['link_status'], 'unverified')
        self.assertNotIn('Python', str(result['preparation']))

    def test_profile_isolation(self):
        first = self.config()
        second = dict(first, resume_evidence={}, preferred_skills=['Python'])
        job = {'description': 'SQL Python'}
        self.assertTrue(recruiter.explain(job, first)['preparation'])
        self.assertEqual(recruiter.explain(job, second)['preparation'], [])
        self.assertNotIn('recruiter', job)

    def test_stale_closed_and_bad_timestamps(self):
        stamp = dt.datetime(2026, 1, 3, tzinfo=dt.timezone.utc)
        job = dict(application_verified='2026-01-01T00:00:00+00:00', verification_provenance={'scope': 'test'})
        self.assertEqual(recruiter.explain(job, self.config(), stamp)['link_status'], 'stale')
        job['availability'] = 'Closed'
        self.assertEqual(recruiter.explain(job, self.config(), stamp)['link_status'], 'unavailable')
        job = dict(application_verified='bad')
        self.assertEqual(recruiter.explain(job, self.config())['link_status'], 'unverified')

    def test_skill_boundary_and_unsubstantiated_excerpt(self):
        cfg = self.config(); cfg['resume_evidence']['Python'] = 'I enjoy learning'
        result = recruiter.explain({'description': 'NoSQL Python'}, cfg)
        self.assertEqual(result['resume_matches'], [])
        self.assertEqual(result['preparation'], [])

    def test_wrong_requisition_clears_prior_verification_without_network(self):
        job = dict(url='https://jobs.lever.co/fictional/other', requisition='expected', application_verified='old')
        with patch.object(app, 'safe_url'), patch.object(app.OPENER, 'open') as request:
            with self.assertRaisesRegex(ValueError, 'requisition'): app.verify_application(job)
            request.assert_not_called()
        self.assertNotIn('application_verified', job)

    def test_mismatched_employer_board(self):
        job = dict(url='https://jobs.lever.co/different/123', requisition='123', source_board=['lever', 'fictional'])
        with patch.object(app, 'safe_url'), patch.object(app.OPENER, 'open') as request:
            with self.assertRaisesRegex(ValueError, 'employer source'): app.verify_application(job)
            request.assert_not_called()

    def test_legacy_unscoped_verification_is_not_trusted(self):
        self.assertEqual(recruiter.explain({'application_verified': app.now()}, self.config())['link_status'], 'unverified')

    def test_exact_role_and_form_record_scoped_provenance(self):
        class Response:
            url = 'https://jobs.lever.co/fictional/123'
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b'<form>Junior Analyst</form>'
        job = dict(url=Response.url, requisition='123', title='Junior Analyst',
                   source_board=['lever', 'fictional'], application_evidence='Feed')
        with patch.object(app, 'safe_url'), patch.object(app.OPENER, 'open', return_value=Response()):
            app.verify_application(job)
        self.assertEqual(job['verification_provenance']['requisition'], '123')
        self.assertEqual(recruiter.explain(job, self.config())['link_status'], 'verified')

    def test_exact_title_required_and_redirect_rejected(self):
        class Response:
            url = 'https://jobs.lever.co/fictional/123'
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b'<form>Senior Analyst</form>'
        job = dict(url=Response.url, requisition='123', title='Junior Analyst', application_evidence='Feed')
        with patch.object(app, 'safe_url'), patch.object(app.OPENER, 'open', return_value=Response()):
            with self.assertRaisesRegex(ValueError, 'title'): app.verify_application(job)
        Response.url = 'https://jobs.lever.co/fictional/456'
        with patch.object(app, 'safe_url'), patch.object(app.OPENER, 'open', return_value=Response()):
            with self.assertRaisesRegex(ValueError, 'redirected'): app.verify_application(job)

if __name__ == '__main__': unittest.main()
