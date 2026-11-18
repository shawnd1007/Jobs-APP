"""Fictional network and AI responses; never selectable from production settings."""
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

MARA = ('Mara Ellery — fictional applicant. 15 years in medical billing and revenue cycle. '
        'Supervised eight billing specialists supporting outpatient clinics. '
        'Reviewed denial queues and coached staff on correcting rejected claims. '
        'Built monthly Excel reports on accounts receivable and payer turnaround.')
JULES = ('Jules Mercer — fictional applicant. 15 years in manufacturing operations. '
         'Operated CNC machines and inspected parts against engineering drawings. '
         'Trained operators on safe machine setup and documented quality checks.')


def strategy(resume):
    medical = 'billing' in resume.lower()
    evidence = ('Supervised eight billing specialists supporting outpatient clinics.' if medical else
                'Operated CNC machines and inspected parts against engineering drawings.')
    secondary = ('Reviewed denial queues and coached staff on correcting rejected claims.' if medical else
                 'Trained operators on safe machine setup and documented quality checks.')
    role = 'Revenue Cycle Supervisor' if medical else 'CNC Machinist'
    return dict(summary='Your experience centers on ' + ('medical billing, payer follow-up and team leadership.' if medical else 'manufacturing, machining and quality inspection.'),
        skills=[dict(label='Medical Billing' if medical else 'CNC Machining', evidence=evidence, kind='stated'),
                dict(label='Team coaching', evidence=secondary, kind='transferable')],
        roles=[dict(title=role, reason='Your responsibilities directly support this role.', evidence=evidence)],
        adjacent_roles=[dict(title='Patient Accounts Lead' if medical else 'Quality Inspector', reason='Your experience transfers; check the specific requirements.', evidence=secondary)],
        cautions=[dict(title='Clinical Laboratory Scientist' if medical else 'Manufacturing Engineer', reason='The résumé does not establish the required professional qualification.', evidence=evidence)])


SPECS = [
    ('billing', 'Revenue Cycle Supervisor', 'Remote — Oregon, United States', 'remote', 'Review denial queues and coach billing specialists.', 80000, 95000),
    ('unknown', 'Medical Billing Specialist', 'Remote — United States', 'remote', 'Review denial queues and coach billing specialists.', 75000, 85000),
    ('excluded', 'Medical Billing Specialist', 'Remote — United States, excluding Oregon', 'remote', 'Review denial queues and coach billing specialists.', 80000, 90000),
    ('hybrid', 'Patient Accounts Lead', 'Portland, Oregon', 'hybrid', 'Review denial queues and coach billing specialists.', 80000, 90000),
    ('lab', 'Clinical Laboratory Scientist', 'Remote — Oregon, United States', 'remote', 'Analyze laboratory specimens. A clinical laboratory license is required.', 90000, 110000),
    ('cnc', 'CNC Machinist', 'Portland, Oregon', 'onsite', 'Operate CNC machines and inspect parts against engineering drawings.', 80000, 95000),
]


def fake_ai(a, name, inputs, schema):
    if name == 'career_strategy':
        return strategy(inputs['resume'])
    candidate, job = inputs['candidate'], inputs['job']
    medical = 'billing' in candidate['summary']
    fits = ('denial' in job['description']) if medical else ('CNC' in job['description'])
    return dict(group='close' if fits else 'avoid', reason='Your documented responsibilities support this work.' if fits else 'These duties require experience not established by your résumé.',
                resume_evidence=candidate['skills'][0]['evidence'],
                job_evidence=job['description'].split('\n')[-1], gaps=[] if fits else ['Relevant professional experience is not established.'],
                emphasis=[candidate['skills'][0]['label']] if fits else [])


@contextmanager
def environment():
    import app
    import recruiter
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='jobs-v2-qa-') as directory, ExitStack() as stack:
        root = Path(directory)
        cfg = json.loads((source / 'config.example.json').read_text())
        cfg.update(profile='', categories=[], preferred_skills=[], skill_groups=[], legacy_geography=False,
                   remote_hiring_locations=[], target_locations=[], workplace_types=[],
                   public_web_search_enabled=False, firecrawl_enabled=False, schedule_enabled=False,
                   request_delay_seconds=0, generic_urls_per_run=0, max_new_candidates=30)
        stack.enter_context(patch.object(app, 'DATA', root))
        stack.enter_context(patch.object(app, 'DB', root / 'qa.sqlite3'))
        stack.enter_context(patch.object(app, 'SEED', source / 'seed.empty.html'))
        stack.enter_context(patch.object(app, 'config', side_effect=lambda **_: dict(cfg)))
        stack.enter_context(patch.object(recruiter, 'ai', side_effect=fake_ai))
        feed = [dict(id=key, text=title, applyUrl=f'https://jobs.lever.co/fictional-clinic/{key}',
                     categories={'location': location}, workplaceType=mode,
                     descriptionPlain='Fictional employer opening.', lists=[{'text': 'Responsibilities', 'content': duty}],
                     salaryRange={'currency': 'USD', 'interval': 'per-year', 'min': low, 'max': high},
                     salaryDescriptionPlain=f'${low:,}–${high:,} annual base')
                for key, title, location, mode, duty, low, high in SPECS]
        calls = []

        def response(request, **kwargs):
            url = request.full_url
            calls.append(url)
            if url.startswith('https://www.bing.com/search?'):
                return b'<rss><channel><item><link>https://jobs.lever.co/fictional-clinic/billing</link></item></channel></rss>', url
            if url.startswith('https://api.lever.co/v0/postings/fictional-clinic?'):
                return json.dumps(feed).encode(), url
            for item in feed:
                if url == item['applyUrl']:
                    return f'<html><h1>{item["text"]}</h1><form><input name="resume"/></form></html>'.encode(), url
            raise AssertionError('Unexpected network request: ' + url)

        stack.enter_context(patch.object(app, 'read_response', side_effect=response))
        # No external network is permitted by this fixture; any bypass fails.
        stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected paid or external request')))
        app.init()
        yield app, calls
