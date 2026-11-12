"""Regression tests with fictional listings, profiles, and tracking records."""
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import app

class PersistenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=app.DB;self.olddata=app.DATA;self.oldseed=app.SEED;app.SEED=Path(__file__).resolve().parent/'fixtures'/'seed.html';app.DATA=Path(self.tmp.name);app.DB=app.DATA/'test.sqlite3';app.init()
 def tearDown(self):app.DB=self.old;app.DATA=self.olddata;app.SEED=self.oldseed;self.tmp.cleanup()
 def test_import_and_reimport(self):
  self.assertEqual(len(app.records()),50);app.init();self.assertEqual(len(app.records()),50)
 def test_tracking_survives_closed_and_reopened(self):
  j=app.records()[0]
  note='Fictional fixture application note'
  applied_on='2030-01-02'
  with app.connect() as c:
   c.execute("UPDATE tracking SET status='Applied',notes=?,application_date=? WHERE job_id=?",(note,applied_on,j['id']))
   j['availability']='Closed';app.upsert(c,j)
  current=app.records()[0];self.assertEqual(current['status'],'Applied');self.assertEqual(current['notes'],note);self.assertEqual(current['availability'],'Closed')
  with app.connect() as c:j['availability']='Open';app.upsert(c,j)
  self.assertEqual(app.records()[0]['application_date'],applied_on);self.assertEqual(len(app.records()),50)
 def test_tracking_parameters_deduplicate(self):
  j=app.records()[0];j['url']+='?utm_source=test#apply'
  with app.connect() as c:_,added=app.upsert(c,j)
  self.assertFalse(added);self.assertEqual(len(app.records()),50)
 def test_distinct_requisitions_do_not_share_application_history(self):
  first = dict(title='Billing Analyst', employer='Fictional Employer',
               location='Remote - United States',
               url='https://jobs.ashbyhq.com/fictional/job-one/application', requisition='job-one')
  second = dict(first, url='https://jobs.ashbyhq.com/fictional/job-two/application', requisition='job-two')
  with app.connect() as c:
   first_id, _ = app.upsert(c, first)
   c.execute("UPDATE tracking SET status='Applied' WHERE job_id=?", (first_id,))
   second_id, added = app.upsert(c, second)
   same_id, repeated = app.upsert(c, dict(second, url=second['url']+'?utm_source=sample'))
  self.assertTrue(added)
  self.assertFalse(repeated)
  self.assertNotEqual(first_id, second_id)
  self.assertEqual(second_id, same_id)
  jobs = {j['id']: j for j in app.records()}
  self.assertEqual(jobs[first_id]['status'], 'Applied')
  self.assertEqual(jobs[second_id]['status'], 'Needs Verification')

 def test_legacy_requisition_mismatch_restores_link_without_moving_tracking(self):
  first = dict(title='Billing Analyst', employer='Fictional Employer', location='Remote - United States',
               url='https://jobs.lever.co/fictional/job-one/apply', requisition='job-one')
  overwritten = dict(first, url='https://jobs.lever.co/fictional/job-two/apply', requisition='job-two',
                     availability='Open', application_verified=app.now(), salary_max=99000)
  with app.connect() as c:
   first_id, _ = app.upsert(c, first)
   c.execute('UPDATE jobs SET listing=? WHERE id=?', (json.dumps(overwritten), first_id))
   c.execute("UPDATE tracking SET status='Applied',notes='Preserve this' WHERE job_id=?", (first_id,))
  app.init()
  repaired = next(job for job in app.records() if job['id'] == first_id)
  self.assertEqual(repaired['url'], first['url'])
  self.assertEqual(repaired['requisition'], 'job-one')
  self.assertEqual(repaired['availability'], 'Needs Verification')
  self.assertNotIn('application_verified', repaired)
  self.assertNotIn('salary_max', repaired)
  self.assertEqual((repaired['status'], repaired['notes']), ('Applied', 'Preserve this'))

 def test_smartrecruiters_rejects_partial_pages_and_hydrates_exact_posting(self):
  row = {'id': '123', 'name': 'Billing Analyst', 'location': {'country': 'us', 'remote': True}}
  with patch.object(app, 'fetch', return_value={'totalFound': 101, 'content': [row]}):
   with self.assertRaisesRegex(ValueError, 'Incomplete'):
    app.board_jobs('smartrecruiters', 'fictional')
  detail = {**row, 'applyUrl': 'https://jobs.smartrecruiters.com/Fictional/123-billing-analyst?oga=true',
            'jobAd': {'sections': {'jobDescription': {'text': 'Reconcile invoices.'}}}}
  with patch.object(app, 'fetch', side_effect=[{'totalFound': 1, 'content': [row]}, detail]):
   summary, = app.board_jobs('smartrecruiters', 'fictional')
   job = app.hydrate_board_listing('fictional', summary)
  self.assertEqual(app.identity(summary['url']), app.identity(job['url']))
  self.assertEqual(job['location'], 'United States')
  self.assertIn('Reconcile invoices.', job['description'])
  self.assertNotIn('detail_url', job)

 def test_duty_match_requires_profile_evidence_and_keeps_qualifications_separate(self):
  result = app.experience_evidence('Build Excel reports. SQL proficiency required.',
                                   'Used Excel to create monthly reports.', ['excel', 'sql'])
  self.assertEqual(result, [{'skill': 'excel', 'duty': 'Build Excel reports.'}])
  self.assertEqual(app.qualification_checks('degree or equivalent work experience'),
                   ['Posting mentions a degree and equivalent experience.'])

 def test_greenhouse_description_keeps_qualifications_out_of_duties(self):
  posting = {'id': 41, 'title': 'Operations Specialist', 'absolute_url': 'https://job-boards.greenhouse.io/example/jobs/41',
             'content': ('&lt;h3&gt;Responsibilities&lt;/h3&gt;'
                         '&lt;ul&gt;&lt;li&gt;Reconcile payments using Excel&lt;/li&gt;'
                         '&lt;li&gt;Build reports using Python&lt;/li&gt;&lt;/ul&gt;'
                         '&lt;h3&gt;Qualifications&lt;/h3&gt;&lt;p&gt;Build dashboards with SQL&lt;/p&gt;')}
  cfg = app.config()
  cfg.update(preferred_skills=['Excel', 'SQL', 'Python'], profile='Worked with Excel and SQL. Learning Python.')
  with patch.object(app, 'fetch', return_value={'jobs': [posting]}):
   job, = app.board_jobs('greenhouse', 'example')
  app.assess(job, cfg)
  self.assertEqual(job['matched_duty_count'], 1)
  self.assertEqual(job['duty_evidence'], [{'skill': 'excel', 'duty': 'Reconcile payments using Excel'}])
  self.assertEqual(set(job['matched_skills']), {'excel', 'sql', 'python'})

 def test_lever_list_labels_distinguish_duties_from_requirements(self):
  posting = {'id': 'test-41', 'text': 'Systems Specialist', 'applyUrl': 'https://jobs.lever.co/example/test-41/apply',
             'descriptionPlain': 'Join our team.', 'additionalPlain': 'Support Azure customers in a future role.',
             'lists': [{'text': 'What you’ll do', 'content': '<li>Maintain systems using Linux</li>'},
                       {'text': 'What you bring', 'content': '<li>Manage deployments with Azure</li>'}]}
  cfg = app.config()
  cfg.update(preferred_skills=['Linux', 'Azure'], profile='Used Linux and Azure for systems operations.')
  with patch.object(app, 'fetch', return_value=[posting]):
   job, = app.board_jobs('lever', 'example')
  app.assess(job, cfg)
  self.assertEqual(job['duty_evidence'], [{'skill': 'linux', 'duty': 'Maintain systems using Linux'}])

 def test_two_skills_in_one_duty_are_not_two_distinct_duties(self):
  cfg = app.config()
  cfg.update(preferred_skills=['Excel', 'SQL'], profile='Used Excel and SQL in finance operations.')
  job = app.assess({'description': 'Build reports using Excel and SQL. Build reports using Excel and SQL.'}, cfg)
  self.assertEqual(len(job['duty_evidence']), 2)
  self.assertEqual(job['matched_duty_count'], 1)
  job = app.assess({'description': 'Build reports using Excel and SQL. Reconcile payments using Excel.'}, cfg)
  self.assertEqual(job['matched_duty_count'], 2)

 def test_history_import_previews_matches_and_preserves_manual_tracking(self):
  import csv
  from import_history import import_history
  jobs = app.records()[:2]
  with app.connect() as c:
   c.execute("UPDATE tracking SET notes='Keep this' WHERE job_id=?", (jobs[1]['id'],))
  path = app.DATA / 'fictional-history.csv'
  with path.open('w', newline='') as file:
   writer = csv.DictWriter(file, fieldnames=['url', 'status', 'application_date'])
   writer.writeheader()
   for job in jobs:
    writer.writerow(dict(url=job['url'], status='Applied', application_date='2026-11-10'))
  self.assertEqual([row['result'] for row in import_history(path)],
                   ['ready to import', 'existing tracking preserved'])
  self.assertEqual([row['result'] for row in import_history(path, apply=True)],
                   ['imported', 'existing tracking preserved'])
  records = {job['id']: job for job in app.records()}
  self.assertEqual(records[jobs[0]['id']]['status'], 'Applied')
  self.assertEqual(records[jobs[1]['id']]['notes'], 'Keep this')

 def test_unknown_salary_not_qualified(self):
  j={'title':'Financial Analyst','location':'Remote - United States','remote':True,'description':'Excel financial reconciliation','availability':'Open'}
  self.assertEqual(app.assess(j,app.config())['queue'],'Review')
 def test_restricted_remote_needs_review(self):
  j={'title':'Financial Analyst','location':'Remote United States','remote':True,'description':'Must reside in California only','availability':'Open','salary_min':85000,'salary_max':100000,'salary_currency':'USD','salary_period':'year','salary_type':'base'}
  self.assertEqual(app.assess(j,app.config())['eligibility'],'Review')
 def test_below_floor_excluded(self):
  j={'title':'Financial Analyst','location':'Remote - United States','description':'Excel financial','availability':'Open','salary_max':65000,'salary_currency':'USD','salary_period':'year','salary_type':'base'}
  self.assertEqual(app.assess(j,app.config())['queue'],'Excluded')
 def test_original_unverified(self):self.assertTrue(all(j['availability']=='Needs Verification' for j in app.records()))
 def test_backup(self):
  before=app.DATA;app.DATA=Path(self.tmp.name)
  try:app.backup();self.assertEqual(len(list((app.DATA/'backups').glob('*.sqlite3'))),1)
  finally:app.DATA=before
 def pipeline_fixture(self):
  j=app.records()[0]
  with app.connect() as c:
   c.execute('DELETE FROM tracking WHERE job_id!=?',(j['id'],));c.execute('DELETE FROM jobs WHERE id!=?',(j['id'],))
   c.execute("UPDATE tracking SET status='Applied',notes='Keep this history' WHERE job_id=?",(j['id'],))
  cfg=app.config();cfg.update(public_web_search_enabled=False,firecrawl_enabled=False,request_delay_seconds=0,generic_urls_per_run=0)
  return j,cfg
 def test_live_feed_absence_closes_without_deleting_application(self):
  j,cfg=self.pipeline_fixture()
  with patch.object(app,'config',return_value=cfg),patch.object(app,'board_jobs',return_value=[]):
   app.LOCK.acquire();report=app.run_pipeline()
  self.assertEqual(report['newly_closed'],1);self.assertEqual(len(app.records()),1)
  saved=app.records()[0];self.assertEqual(saved['availability'],'Closed');self.assertEqual(saved['status'],'Applied');self.assertEqual(saved['notes'],'Keep this history')
 def test_provider_failure_retains_records(self):
  j,cfg=self.pipeline_fixture()
  with patch.object(app,'config',return_value=cfg),patch.object(app,'board_jobs',side_effect=TimeoutError('Test timeout')):
   app.LOCK.acquire();report=app.run_pipeline()
  self.assertTrue(report['failures']);self.assertEqual(app.records()[0]['availability'],'Needs Verification');self.assertEqual(app.records()[0]['status'],'Applied')
 def test_new_listing_limit_applies_after_ranking_all_boards(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(categories=['financial analyst'], preferred_skills=['Excel', 'Reconciliation'],
             skill_groups=[], target_locations=[], workplace_types=[], max_new_candidates=1,
             additional_boards={'ashby': ['aardvark', 'zebra']})
  def board(_platform, slug):
   if slug not in ('aardvark', 'zebra'):
    return []
   return [dict(title='Financial Analyst', employer=slug, location='Remote - United States',
                url=f'https://jobs.ashbyhq.com/{slug}/test/application',
                description='Excel and reconciliation' if slug == 'zebra' else 'Office support',
                availability='Open')]
  with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_jobs', side_effect=board):
   app.LOCK.acquire()
   report = app.run_pipeline()
  self.assertEqual(report['new_review'], 1)
  self.assertEqual(report['deferred_candidates'], 1)
  self.assertIn('zebra', [job['employer'] for job in app.records()])
  self.assertNotIn('aardvark', [job['employer'] for job in app.records()])

 def test_search_ranks_distinct_duties_and_filters_weak_direct_candidates(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(categories=['Financial Analyst'], preferred_skills=['Excel', 'SQL', 'Python'],
             profile='Used Excel, SQL and Python in finance operations.', skill_groups=[],
             target_locations=[], workplace_types=[], max_new_candidates=1, generic_urls_per_run=2,
             additional_boards={'ashby': ['fictional']},
             additional_employer_urls=['https://example.com/weak', 'https://example.com/transferable'])
  board_job = dict(title='Financial Analyst', employer='Fictional Board', location='Remote - United States',
                   description='Qualifications:\nExperience with Excel, SQL and Python.', availability='Open',
                   url='https://jobs.ashbyhq.com/fictional/req-1/application')
  def board(platform, slug):
   return [board_job] if (platform, slug) == ('ashby', 'fictional') else []
  def direct(url, *_):
   description = ('Build dashboards using Excel and SQL.' if url.endswith('/weak')
                  else 'Responsibilities:\nBuild SQL reports.\nReconcile payments in Excel.')
   return dict(board_job, title='Operations Specialist', employer='Fictional Direct', url=url, description=description)
  with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_jobs', side_effect=board), \
       patch.object(app, 'generic_posting', side_effect=direct):
   app.LOCK.acquire()
   report = app.run_pipeline()
  self.assertEqual(report['new_review'], 1)
  self.assertEqual(report['deferred_candidates'], 1)
  chosen, = (job for job in app.records() if job['employer'] == 'Fictional Direct')
  self.assertTrue(chosen['url'].endswith('/transferable'))
  self.assertEqual(chosen['matched_duty_count'], 2)
  self.assertEqual(chosen['queue'], 'Review')

 def test_smartrecruiters_checks_saved_search_titles_before_general_postings(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(categories=['Financial Analyst'], additional_boards={'smartrecruiters': ['fictional']})
  criteria = dict(name='Billing in Austin', title_terms=['Billing'], skills=['Reconciliation'],
                  locations=['Austin, TX'], workplace_types=['onsite'], salary_min=85000,
                  salary_max=None, enabled=True)
  self.assertEqual(app.prototype.change_saved_search(app, {'action': 'save', 'criteria': criteria})[0], 200)
  postings = [dict(title='Operations Assistant', employer='Fictional', location='Austin, TX',
                   url=f'https://jobs.smartrecruiters.com/fictional/{number}', requisition=str(number),
                   posted='2026-11-11', availability='Open') for number in range(1, 21)]
  postings[0].update(title='Billing Specialist', description='Reconciliation duties.', posted='2026-11-01',
                     salary_min=90000, salary_max=110000, salary_currency='USD', salary_period='year',
                     salary_type='base')
  def board(platform, slug):
   return postings if (platform, slug) == ('smartrecruiters', 'fictional') else []
  with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_jobs', side_effect=board):
   app.LOCK.acquire()
   report = app.run_pipeline()
   self.assertEqual(app.snapshot()['unread_match_count'], 1)
  self.assertEqual(report['new_review'], 1)
  self.assertEqual(report['deferred_source_details'], 4)

 def test_overlapping_run_rejected(self):
  app.LOCK.acquire()
  try:self.assertFalse(app.start_run())
  finally:app.LOCK.release()
 def test_dynamic_application_uses_rendered_evidence_only_when_needed(self):
  url = 'https://jobs.ashbyhq.com/fictional/job-1/application'
  job = {'url': url, 'title': 'Financial Analyst', 'application_evidence': ''}
  cfg = app.config()
  cfg['firecrawl_enabled'] = True
  with patch.object(app, 'safe_url'), patch.object(app, 'config', return_value=cfg), \
       patch.object(app, 'firecrawl_key', return_value='fictional-key'), \
       patch.object(app.OPENER, 'open') as request, patch.object(app, 'firecrawl') as render:
   response = request.return_value.__enter__.return_value
   response.url = url
   response.read.return_value = b'<title>Financial Analyst</title>'
   render.return_value = {'html': '<title>Financial Analyst</title><form>Submit application</form>',
                          'metadata': {'url': url}}
   report = {}
   self.assertTrue(app.verify_application(dict(job), report)['application_verified'])
   render.assert_called_once()
   render.reset_mock()
   response.read.return_value = b'<title>Financial Analyst</title><p>Job is closed</p>'
   with self.assertRaisesRegex(ValueError, 'unavailable'):
    app.verify_application(dict(job), report)
   render.assert_not_called()

 def test_application_evidence_ignores_newsletters_and_hidden_text(self):
  url = 'https://jobs.lever.co/fictional/financial-analyst'
  job = {'url': url, 'title': 'Financial Analyst'}
  listing = '<h1>Financial Analyst</h1><a href="/apply">Apply for this job</a>'
  newsletter = '<form><input name="email"><button>Subscribe</button></form>'
  self.assertFalse(app.application_form_visible(job, listing + newsletter, url))
  self.assertFalse(app.application_form_visible(job, listing + '<script>"<form>Submit application</form>"</script>', url))
  self.assertTrue(app.application_form_visible(job, listing + '<form><input name="resume" type="file"></form>', url))

 def test_daily_search_ignores_manual_runs_and_bounds_failed_retries(self):
  utc = app.dt.datetime(2026, 11, 12, 13, tzinfo=app.dt.timezone.utc)
  with app.connect() as c:
   insert = 'INSERT INTO runs(started,finished,state,report,trigger) VALUES(?,?,?,?,?)'
   stamp = (utc - app.dt.timedelta(hours=1)).isoformat()
   c.execute(insert, (stamp, stamp, 'success', '{}', 'manual'))
   self.assertFalse(app.scheduled_run_due(c, utc, 14))
   self.assertTrue(app.scheduled_run_due(c, utc, 12))
   c.execute(insert, (stamp, utc.isoformat(), 'failed', '{}', 'scheduled'))
   self.assertFalse(app.scheduled_run_due(c, utc, 12))
   later = utc + app.dt.timedelta(minutes=30)
   self.assertTrue(app.scheduled_run_due(c, later, 12))
   c.execute(insert, (later.isoformat(), later.isoformat(), 'partial', '{}', 'scheduled'))
   self.assertFalse(app.scheduled_run_due(c, later + app.dt.timedelta(hours=1), 12))
   c.execute("UPDATE runs SET state='failed' WHERE trigger='scheduled'")
   c.execute(insert, (later.isoformat(), later.isoformat(), 'interrupted', '{}', 'scheduled'))
   self.assertFalse(app.scheduled_run_due(c, later + app.dt.timedelta(hours=1), 12))
   self.assertTrue(app.scheduled_run_due(c, utc + app.dt.timedelta(days=1), 12))

 def test_scheduled_backup_failure_is_reported_and_releases_run_lock(self):
  with patch.object(app, 'backup', side_effect=OSError('Test backup failure')):
   app.LOCK.acquire()
   result = app.run_pipeline('scheduled')
  self.assertFalse(app.LOCK.locked())
  self.assertEqual(result['state'], 'failed')
  with app.connect() as c:
   run = c.execute('SELECT trigger,state,finished FROM runs').fetchone()
  self.assertEqual((run['trigger'], run['state']), ('scheduled', 'failed'))
  self.assertIsNotNone(run['finished'])
  self.assertEqual(len(app.records()), 50)

 def test_only_requested_locations_pass(self):
  cfg=dict(app.config(),target_locations=[],workplace_types=[],local_areas={
      'Fictional East': {'cities': ['Cedar Point'], 'states': ['me', 'maine']},
      'Fictional West': {'cities': ['Pine Harbor', 'Juniper Cove'], 'states': ['or', 'oregon']},
  })
  cases=[('London, UK',True,'Rejected'),('Remote - Colombia',True,'Rejected'),('Texas',True,'Rejected'),('Bangalore, India',False,'Rejected'),('Example City, NY',False,'Rejected'),('Cedar Point',False,'Review'),('Cedar Point, WA',False,'Review'),('Cedar Point, ME',False,'Eligible'),('Pine Harbor, OR Hybrid',False,'Eligible'),('Juniper Cove, Oregon',False,'Eligible'),('Remote - United States',True,'Eligible'),('U.S. Remote',True,'Eligible'),('Remote',True,'Review'),('Remote USA Hybrid',True,'Review')]
  for loc,remote,expected in cases:
   with self.subTest(location=loc):self.assertEqual(app.location_eligibility({'location':loc,'remote':remote},cfg)[0],expected)
 def test_remote_restricted_state_not_eligible(self):
  j={'location':'Remote - US','remote':True,'description':'You must reside in Virginia.'}
  self.assertNotEqual(app.location_eligibility(j,app.config())[0],'Eligible')
 def test_unrelated_word_only_does_not_disqualify_us_remote(self):
  j={'location':'Remote - US','remote':True,'description':'Only shortlisted candidates will be contacted.'}
  self.assertEqual(app.location_eligibility(j,app.config())[0],'Eligible')
 def test_discovery_does_not_insert_foreign_remote_jobs(self):
  j,cfg=self.pipeline_fixture()
  bad={'title':'Financial Analyst','employer':'Fictional Employer','url':'https://jobs.ashbyhq.com/fictional/outside-location-test/application','location':'London, UK','remote':True,'description':'Financial reporting and Excel','availability':'Open'}
  with patch.object(app,'config',return_value=cfg),patch.object(app,'board_jobs',return_value=[bad]):
   app.LOCK.acquire();report=app.run_pipeline()
  self.assertEqual(len(app.records()),1);self.assertEqual(report['skipped_location'],1)
 def review_payload(self,j,decision='Approved'):
  return {'decision':decision,'version':j['review_version'],'tracking_version':j['version'],'checks':{k:True for k in ('location','salary','application','history')},'note':'Checked employer posting, pay eligibility, location and specific application history.','reviewer':'Test reviewer'}
 def test_approval_requires_all_checks(self):
  j=app.records()[0];d=self.review_payload(j);d['checks']['salary']=False
  code,_=app.save_review(j['id'],d);self.assertEqual(code,400);self.assertEqual(app.records()[0]['review_decision'],'Pending')
 def test_approval_preserves_notes_dates_and_sets_not_applied(self):
  j=app.records()[0]
  with app.connect() as c:c.execute("UPDATE tracking SET notes='Keep notes',follow_up='2026-12-01' WHERE job_id=?",(j['id'],))
  code,_=app.save_review(j['id'],self.review_payload(j));self.assertEqual(code,200)
  saved=app.records()[0];self.assertEqual(saved['status'],'Not Applied');self.assertEqual(saved['notes'],'Keep notes');self.assertEqual(saved['follow_up'],'2026-12-01');self.assertEqual(saved['review_decision'],'Approved')
 def test_discovery_never_resets_approval(self):
  j=app.records()[0];app.save_review(j['id'],self.review_payload(j))
  with app.connect() as c:j['availability']='Closed';app.upsert(c,j)
  saved=app.records()[0];self.assertEqual(saved['review_decision'],'Approved');self.assertEqual(saved['review_reviewer'],'Test reviewer');self.assertEqual(saved['status'],'Not Applied')
 def test_review_optimistic_concurrency(self):
  j=app.records()[0];d=self.review_payload(j,'Hold');self.assertEqual(app.save_review(j['id'],d)[0],200)
  self.assertEqual(app.save_review(j['id'],d)[0],409)
 def test_approval_does_not_reset_applied_status(self):
  j=app.records()[0]
  with app.connect() as c:c.execute("UPDATE tracking SET status='Applied',version=version+1 WHERE job_id=?",(j['id'],))
  self.assertEqual(app.save_review(j['id'],self.review_payload(j))[0],409);self.assertEqual(app.records()[0]['status'],'Applied')
 def test_cannot_approve_out_of_area(self):
  j=app.records()[0];j['location']='Remote - Mexico';j['remote']=True
  with app.connect() as c:app.upsert(c,j)
  self.assertEqual(app.save_review(j['id'],self.review_payload(j))[0],400)
 def test_hold_and_dismiss_preserve_tracking(self):
  j=app.records()[0]
  for decision in ('Hold','Dismissed','Pending'):
   self.assertEqual(app.save_review(j['id'],self.review_payload(j,decision))[0],200)
   j=app.records()[0];self.assertEqual(j['status'],'Needs Verification');self.assertEqual(j['review_decision'],decision)
if __name__=='__main__':unittest.main()
