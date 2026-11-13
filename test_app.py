"""Regression tests with fictional listings, profiles, and tracking records."""
import json
import tempfile
import threading
import time
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
 def test_external_application_keeps_owner_notes_and_promotes_only_exact_posting(self):
  payload = dict(title='Quality Operations Analyst', employer='Fictional Cedar', location='Remote - United States',
                 url='https://jobs.lever.co/fictional/req-a?utm_source=example', status='Interview Scheduled',
                 application_date='2030-04-10', follow_up='2030-04-22', notes='Bring fictional work samples.')
  code, saved = app.add_external_application(payload)
  self.assertEqual(code, 201)
  job_id = saved['job_id']
  duplicate = dict(payload, title='Different title on a board', notes='Overwrite attempt',
                   url='https://jobs.lever.co/fictional/req-a/apply')
  self.assertEqual(app.add_external_application(duplicate)[0], 409)
  current = next(j for j in app.snapshot()['jobs'] if j['id'] == job_id)
  self.assertTrue(current['external_application'])
  self.assertEqual(current['queue'], 'Tracking')
  self.assertEqual(current['match_label'], 'Added by you')
  self.assertNotIn('lever/fictional', [x['source'] for x in app.snapshot()['sources']])
  self.assertEqual(app.save_review(job_id, {'decision':'Approved', 'version':0})[0], 400)
  with app.connect() as c:
   listing = dict(title=payload['title'], employer=payload['employer'], location=payload['location'],
                  url='https://jobs.lever.co/fictional/req-b/apply', source='Lever public live board',
                  description='Fictional employer duties.', availability='Open')
   other_id, added = app.upsert(c, listing)
   self.assertTrue(added)
   self.assertNotEqual(other_id, job_id)
   found_id, added = app.upsert(c, dict(listing, url='https://jobs.lever.co/fictional/req-a/apply'))
   self.assertEqual(found_id, job_id)
   self.assertFalse(added)
  promoted = next(j for j in app.records() if j['id'] == job_id)
  self.assertNotIn('external_application', promoted)
  self.assertEqual(promoted['source'], 'Lever public live board')
  self.assertEqual(promoted['status'], 'Interview Scheduled')
  self.assertEqual(promoted['application_date'], '2030-04-10')
  self.assertEqual(promoted['follow_up'], '2030-04-22')
  self.assertEqual(promoted['notes'], payload['notes'])

 def test_external_application_accepts_no_link_and_validates_fields(self):
  payload = dict(title='Payroll Coordinator', employer='Fictional Wren', status='Applied')
  for changes in ({'application_date':'2030-02-30'}, {'url':'javascript:alert(1)'},
                  {'url':'https://someone:password@example.com/role'}, {'status':'Unknown'}, {'title':'   '}):
   with self.subTest(changes=changes), self.assertRaises(ValueError):
    app.add_external_application(dict(payload, **changes))
  self.assertEqual(app.add_external_application(payload)[0], 201)
  self.assertEqual(app.add_external_application(dict(payload, title=' Payroll   Coordinator '))[0], 409)
  self.assertEqual(app.add_external_application(dict(payload, location='Toronto'))[0], 201)
  self.assertEqual(app.external_link_key('https://example.com/careers?id=7&utm_source=board'),
                   'https://example.com/careers?id=7')
  self.assertNotEqual(app.external_link_key('https://example.com/careers?id=8'),
                      app.external_link_key('https://example.com/careers?id=7'))
  self.assertEqual(app.snapshot()['match_alerts'], [])

 def test_tracking_parameters_deduplicate(self):
  j=app.records()[0];j['url']+='?utm_source=test#apply'
  with app.connect() as c:_,added=app.upsert(c,j)
  self.assertFalse(added);self.assertEqual(len(app.records()),50)

 def test_recruitee_feed_preserves_duties_and_checks_published_links(self):
  feed = (Path(__file__).resolve().parent/'fixtures'/'recruitee.xml').read_bytes()
  job, = app.recruitee_offers('fictional',feed)
  self.assertEqual(job['recruitee_offer_id'],'12345')
  self.assertIn('Responsibilities\nReconcile incoming payments in Excel.',job['description'])
  self.assertIn('Qualifications\nExperience using fictional accounting software.',job['description'])
  self.assertEqual(app.posting_reference(job['url']),app.posting_reference(job['url']+'/c/new?utm_source=example'))
  self.assertNotEqual(app.identity(job['url']),app.identity(job['url'].replace('fictional.','other.')))
  self.assertEqual(app.work_arrangement(job),'remote')
  altered, = app.recruitee_offers('fictional',feed.replace(b'<hybrid>false',b'<hybrid>true')
                                 .replace(b'<min/>',b'<min>90000</min>'))
  self.assertEqual(app.work_arrangement(altered),'unknown')
  self.assertEqual(app.annual_base_bounds(altered),(None,None))
  self.assertIn('confirm base salary',altered['salary_text'])
  for invalid in (
   feed.replace(b'fictional.recruitee.com',b'other.recruitee.com'),
   feed.replace(b'</offers>',feed[feed.index(b'<offer>'):feed.index(b'</offers>')]+b'</offers>'),
   b'<offers><error/></offers>',
  ):
   with self.subTest(prefix=invalid[:35]), self.assertRaises(ValueError):
    app.recruitee_offers('fictional',invalid)

 def test_recruitee_retry_alerts_once_and_preserves_tracking_on_removal_or_reuse(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(categories=['Payment Operations Specialist'], target_locations=['United States'],
             workplace_types=['remote'], preferred_skills=['Excel'], skill_groups=[],
             salary_floor=85000, additional_boards={'recruitee':['fictional']})
  criteria = dict(name='Fictional payments', title_terms=['Payment Operations'], skills=['Excel'],
                  locations=['United States'], workplace_types=['remote'], salary_min=90000,
                  salary_max=None, enabled=True)
  self.assertEqual(app.prototype.change_saved_search(app,{'action':'save','criteria':criteria})[0],200)
  feed = (Path(__file__).resolve().parent/'fixtures'/'recruitee.xml').read_bytes().replace(
   b'<h2>Responsibilities', b'<p>Annual base salary: $95,000 to $105,000.</p><h2>Responsibilities')
  current_feed = feed
  feed_url = 'https://fictional.recruitee.com/api/feeds/offers.xml'
  posting_url = 'https://fictional.recruitee.com/o/payment-operations-specialist'
  heading = 'Different opening'

  def public_response(request, **kwargs):
   if request.full_url == feed_url:
    if current_feed is None:
     raise TimeoutError('Fictional board timeout')
    return current_feed, feed_url
   self.assertEqual(request.full_url,posting_url)
   return f'<h1>{heading}</h1>'.encode(),posting_url

  def run():
   app.LOCK.acquire()
   return app.run_pipeline()

  def listing():
   return next(j for j in app.records() if j['url']==posting_url)

  with patch.object(app,'config',return_value=cfg), patch.object(app,'read_response',side_effect=public_response), \
       patch.object(app,'fetch',return_value={'jobs':[]}):
   run()
   job_id = listing()['id']
   self.assertEqual(listing()['availability'],'Needs Verification')
   self.assertEqual(app.snapshot()['match_alerts'],[])
   with app.connect() as c:
    c.execute("UPDATE tracking SET notes='Keep this fictional note' WHERE job_id=?",(job_id,))
   heading = 'Payment Operations Specialist'
   run()
   self.assertTrue(listing()['posting_verified'])
   self.assertNotIn('application_verified',listing())
   self.assertEqual([alert['job_id'] for alert in app.snapshot()['match_alerts']],[job_id])
   current_feed = None
   self.assertTrue(run()['failures'])
   self.assertEqual(listing()['availability'],'Open')
   current_feed = b'<offers/>'
   run()
   self.assertEqual(listing()['availability'],'Needs Verification')
   self.assertNotIn('posting_verified',listing())
   current_feed = feed.replace(b'<id>12345</id>',b'<id>54321</id>')
   run()
   self.assertTrue(listing()['recruitee_offer_changed'])
   self.assertIn('reused',app.review_blockers(listing(),cfg)[0])
   current_feed = feed
   run()
   self.assertEqual(listing()['id'],job_id)
   self.assertEqual(listing()['notes'],'Keep this fictional note')
   self.assertTrue(listing()['posting_verified'])
   self.assertFalse(listing()['recruitee_offer_changed'])
   self.assertEqual([alert['job_id'] for alert in app.snapshot()['match_alerts']],[job_id])

 def test_personio_feed_preserves_official_requisition_and_duties(self):
  feed = (Path(__file__).resolve().parent/'fixtures'/'personio.xml').read_bytes()
  with patch.object(app,'safe_url',side_effect=lambda url:url), patch.object(app.PERSONIO_OPENER,'open') as request:
   response = request.return_value.__enter__.return_value
   response.url = 'https://fictional.jobs.personio.com/xml?language=en'
   response.read.return_value = feed
   job, = app.board_jobs('personio','fictional')
   response.read.assert_called_once_with(4_000_001)
  self.assertEqual(job['url'],'https://fictional.jobs.personio.com/job/12345')
  self.assertEqual(app.identity('https://fictional.jobs.personio.de/job/12345/?language=en#apply'),app.identity(job['url']))
  self.assertNotEqual(app.identity('https://another.jobs.personio.com/job/12345'),app.identity(job['url']))
  self.assertIn('Responsibilities\nBuild SQL reports.',job['description'])
  self.assertEqual(job['location'],'Remote - United States')
  self.assertNotIn('application_verified',job)

 def test_personio_feed_rejects_ambiguous_or_truncated_data(self):
  position = b'<position><id>123</id><name>Fictional role</name></position>'
  for data in (b'<html></html>', b'<workzag-jobs>', b'<!DOCTYPE workzag-jobs><workzag-jobs/>',
               b'<workzag-jobs><error/></workzag-jobs>', b'<workzag-jobs>'+position*2+b'</workzag-jobs>',
               b' ' * 4_000_001):
   with self.subTest(prefix=data[:24]), self.assertRaises((ValueError,app.ET.ParseError)):
    app.personio_positions('fictional',data)

 def test_personio_checks_page_and_form_separately(self):
  cfg = dict(app.config(), request_delay_seconds=0)
  feed = (Path(__file__).resolve().parent/'fixtures'/'personio.xml').read_bytes()
  job, = app.personio_positions('fictional',feed)
  report = {'log': []}
  with patch.object(app,'safe_url',side_effect=lambda url:url), patch.object(app.PERSONIO_OPENER,'open') as request:
   response = request.return_value.__enter__.return_value
   response.url = job['url']
   response.read.return_value = b'<h1>Payment Operations Specialist</h1>'
   checked = app.finalize(dict(job),cfg,report)
   self.assertEqual(checked['availability'],'Open')
   self.assertNotIn('application_verified',checked)
   response.read.return_value = b'<h1>Payment Operations Specialist</h1><form><button>Submit application</button></form>'
   self.assertIn('application_verified',app.finalize(dict(job),cfg,report))
   request.side_effect = app.urllib.error.HTTPError(job['url'],404,'Not Found',None,None)
   missing = app.finalize(dict(job),cfg,report)
   self.assertEqual(missing['availability'],'Needs Verification')
   self.assertIn('HTTP 404',missing['application_evidence'])
   request.side_effect = app.urllib.error.HTTPError(job['url'],429,'Rate limited',None,None)
   app.finalize(dict(job),cfg,report)
   request.reset_mock()
   self.assertEqual(app.finalize(dict(job),cfg,report)['availability'],'Needs Verification')
   request.assert_not_called()

 def test_personio_missing_or_failed_feed_preserves_tracking(self):
  _, cfg = self.pipeline_fixture()
  job = dict(title='Fictional role',employer='Fictional Employer',location='Remote - United States',
             availability='Open',url='https://fictional.jobs.personio.de/job/123',application_verified=app.now())
  with app.connect() as c:
   job_id,_ = app.upsert(c,job)
   c.execute('UPDATE jobs SET identity=? WHERE id=?',(job['url'],job_id))
   c.execute("UPDATE tracking SET status='Applied',notes='Fictional confirmation' WHERE job_id=?",(job_id,))
  def missing(platform,board):
   if platform == 'personio': raise TimeoutError('Fictional feed timeout')
   return []
  with patch.object(app,'config',return_value=cfg), patch.object(app,'board_jobs',side_effect=missing):
   app.LOCK.acquire(); result=app.run_pipeline()
  self.assertTrue(any('personio/fictional' in failure for failure in result['failures']))
  self.assertEqual(next(j for j in app.records() if j['id']==job_id)['availability'],'Open')
  with patch.object(app,'config',return_value=cfg), patch.object(app,'board_jobs',return_value=[]):
   app.LOCK.acquire(); app.run_pipeline()
  saved=next(j for j in app.records() if j['id']==job_id)
  self.assertEqual((saved['status'],saved['notes']),('Applied','Fictional confirmation'))
  self.assertEqual(saved['availability'],'Needs Verification')
  self.assertEqual(saved['identity'],'personio:fictional:123')
  self.assertNotIn('application_verified',saved)
  self.assertEqual(len(app.records()),2)
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

 def test_same_title_and_location_do_not_merge_distinct_posting_urls(self):
  job = dict(title='Fictional Billing Analyst', employer='Fictional Employer', location='Remote')
  first = 'https://example.com/careers?posting=101'
  second = 'https://example.com/careers?posting=102'
  with app.connect() as c:
   first_id, added = app.upsert(c, dict(job, url=first))
   self.assertTrue(added)
   c.execute("UPDATE tracking SET status='Applied',notes='First opening only' WHERE job_id=?",(first_id,))
   second_id, added = app.upsert(c, dict(job, url=second))
   self.assertTrue(added)
   third_id, added = app.upsert(c, dict(job, url='https://example.com/careers/new-role'))
   self.assertTrue(added)
   repeat_id, added = app.upsert(c, dict(job, url=first+'&utm_source=test#apply'))
   self.assertFalse(added)
  self.assertEqual(first_id, repeat_id)
  self.assertEqual(len({first_id, second_id, third_id}), 3)
  first_row, = (row for row in app.records() if row['id']==first_id)
  self.assertEqual((first_row['status'],first_row['notes']),('Applied','First opening only'))
  self.assertEqual(app.identity('https://example.com/careers?b=2&posting=101&a=1'),
                   app.identity('https://example.com/careers?a=1&posting=101&b=2'))
  self.assertNotEqual(app.identity('https://example.com/careers?posting=101&posting=102'),
                      app.identity('https://example.com/careers?posting=102&posting=101'))

 def test_legacy_generic_keys_rekey_in_place_and_hold_conflicts(self):
  job = dict(title='Fictional Billing Analyst', employer='Fictional Employer', location='Remote')
  url = 'https://example.com/careers?posting=101'
  conflicted = 'https://example.com/careers?posting=201'
  with app.connect() as c:
   first_id,_ = app.upsert(c,dict(job,url=url))
   conflict_id,_ = app.upsert(c,dict(job,url=conflicted))
   c.execute('UPDATE jobs SET identity=? WHERE id=?',(app.legacy_page_identity(url),first_id))
   c.execute('UPDATE jobs SET identity=? WHERE id=?',('https://example.com/other-opening',conflict_id))
   c.execute("UPDATE tracking SET status='Applied',notes='Original application' WHERE job_id=?",(first_id,))
  self.assertEqual(app.save_application_draft(first_id,{'draft':'Keep my fictional draft','version':0})[0],200)
  app.init()
  app.init()
  records = {record['id']:record for record in app.records()}
  self.assertEqual(records[first_id]['identity'],url)
  self.assertTrue(records[first_id]['history_confirmation'])
  self.assertEqual(records[first_id]['notes'],'Original application')
  self.assertEqual(app.application_prep(first_id)[1]['draft'],'Keep my fictional draft')
  self.assertTrue(records[conflict_id]['identity_review'])
  self.assertEqual(records[conflict_id]['url'],conflicted)
  self.assertEqual(records[conflict_id]['identity'],'https://example.com/other-opening')
  self.assertIn(app.IDENTITY_REVIEW,app.review_blockers(records[conflict_id]))
  from import_history import import_history
  history = app.DATA/'fictional-history.csv'
  history.write_text(f'url,status\n{conflicted},Applied\n',encoding='utf-8')
  self.assertEqual(import_history(history)[0]['result'],'no unique requisition match')

 def test_migration_keeps_both_rows_when_legacy_links_normalize_to_one_posting(self):
  first = 'https://example.com/careers?jobId=7&requisitionId=R7'
  second = 'https://example.com/careers?requisitionId=R7&jobId=7'
  self.assertEqual(app.identity(first),app.identity(second))
  ids = []
  with app.connect() as c:
   for url in (first,second):
    job = dict(title='Fictional Analyst',employer='Fictional Employer',url=url,availability='Open')
    job_id = c.execute(
        'INSERT INTO jobs(identity,listing,created,updated) VALUES(?,?,?,?)',
        (app.legacy_page_identity(url),json.dumps(job),app.now(),app.now()),
    ).lastrowid
    c.execute('INSERT INTO tracking(job_id,notes,updated) VALUES(?,?,?)',
              (job_id,f'Original record {job_id}',app.now()))
    ids.append(job_id)
  app.init()
  retained = {job['id']:job for job in app.records()}
  for job_id in ids:
   self.assertTrue(retained[job_id]['identity_review'])
   self.assertEqual(retained[job_id]['availability'],'Needs Verification')
   self.assertEqual(retained[job_id]['notes'],f'Original record {job_id}')
  with app.connect() as c, self.assertRaisesRegex(ValueError,'Retained records disagree'):
   app.upsert(c,dict(title='Fictional Analyst',employer='Fictional Employer',url=first))

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

 def test_prep_uses_real_excerpts_and_keeps_gaps_honest(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(preferred_skills=['Excel','SQL','Python','Tableau','C','C++'], profile=(
      'Reconciled monthly payments using Excel.\n'
      'Did not use SQL.\nLearning Python.\n'
      'My team built dashboards in Tableau.\nUsed C++ to build a practice tool.\n'
      'Used to learn SQL.'))
  job = dict(title='Fictional Billing Analyst',employer='Fictional Employer',url='https://example.com/prep',
             description=('Responsibilities:\nReconcile payments using Excel.\nBuild SQL reports.\n'
                          'Build Python dashboards.\nMaintain Tableau dashboards.\n'
                          'Develop C++ tools.\nMaintain reports without using C.\n'
                          'Qualifications:\nCertification is required.'))
  with app.connect() as c:
   job_id,_ = app.upsert(c,job)
  with patch.object(app,'config',return_value=cfg):
   status, prep = app.application_prep(job_id)
  self.assertEqual(status,200)
  examples={item['skill']:item['profile_excerpt'] for item in prep['examples']}
  self.assertEqual(examples,{'Excel':'Reconciled monthly payments using Excel.',
                             'C++':'Used C++ to build a practice tool.'})
  self.assertEqual(prep['skills_to_document'],['SQL','Python','Tableau'])
  self.assertTrue(prep['qualification_checks'])
  self.assertEqual(prep['draft'],'')
  self.assertEqual(prep['version'],0)

 def test_prep_draft_retries_without_overwrite_and_survives_listing_refresh(self):
  job = dict(title='Fictional Analyst',employer='Fictional Employer',url='https://example.com/worksheet',
             description='Responsibilities:\nBuild reports in Excel.')
  with app.connect() as c:
   job_id,_ = app.upsert(c,job)
   c.execute("UPDATE tracking SET notes='Fictional tracking note' WHERE job_id=?", (job_id,))
  body = {'draft':'Fictional draft from the owner.', 'version':0}
  first = app.save_application_draft(job_id,body)
  self.assertEqual(first[0],200)
  self.assertEqual(first,app.save_application_draft(job_id,body))
  self.assertEqual(app.save_application_draft(job_id,dict(body,draft='Older client edit'))[0],409)
  self.assertEqual(app.save_application_draft(job_id,dict(body,version=True))[0],400)
  self.assertEqual(app.save_application_draft(job_id,dict(body,draft='x'*8001))[0],400)
  with app.connect() as c:
   app.upsert(c,dict(job,description='Updated employer details.',availability='Closed'))
  loaded = app.application_prep(job_id)[1]
  self.assertEqual(loaded['draft'],body['draft'])
  self.assertEqual(loaded['version'],1)
  self.assertEqual(next(j for j in app.records() if j['id']==job_id)['notes'],'Fictional tracking note')
  self.assertNotIn('application_drafts',app.snapshot())
  self.assertEqual(app.save_application_draft(job_id,{'draft':'','version':1})[1]['version'],2)
  self.assertEqual(app.application_prep(job_id)[1]['draft'],'')
  self.assertEqual(app.application_prep(999999)[0],404)

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
 def test_saved_searches_distinguish_employer_remote_hybrid_and_unclear_arrangements(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(categories=['Billing Analyst'], target_locations=['Austin, TX'], workplace_types=['remote'],
             preferred_skills=['Excel'], skill_groups=[], salary_floor=80000,
             additional_boards={'ashby':['fictional']})
  for mode in ('remote','hybrid'):
   criteria = dict(name='Fictional '+mode, title_terms=['Billing'], skills=['Excel'], locations=['Austin, TX'],
                   workplace_types=[mode], salary_min=85000, salary_max=None, enabled=True)
   self.assertEqual(app.prototype.change_saved_search(app,{'action':'save','criteria':criteria})[0],200)
  def listing(key, workplace=None):
   post = dict(id=key,title='Fictional Billing Analyst',location='Austin, TX',descriptionPlain='Reconcile in Excel.',
               isRemote=True,applyUrl=f'https://jobs.ashbyhq.com/fictional/{key}/application')
   post['compensation'] = {'compensationTiers':[{'components':[
       {'compensationType':'Salary','currencyCode':'USD','interval':'1 YEAR','minValue':90000,'maxValue':110000}
   ]}]}
   if workplace:
    post['workplaceType']=workplace
   return post
  posts = [listing('remote-job','Remote'),listing('hybrid-job','Hybrid'),listing('old-flag')]
  base_board_jobs=app.board_jobs
  def boards(platform, name):
   return base_board_jobs(platform,name) if name=='fictional' else []
  def page(request, **kwargs):
   return b'<h1>Fictional Billing Analyst</h1>',request.full_url
  with patch.object(app,'config',return_value=cfg), patch.object(app,'board_jobs',side_effect=boards), \
       patch.object(app,'fetch') as feed, patch.object(app,'read_response',side_effect=page):
   feed.return_value={'jobs':posts}
   app.LOCK.acquire()
   self.assertEqual(app.run_pipeline()['state'],'success')
   dashboard = app.snapshot()
   records = {row.get('requisition'):row for row in dashboard['jobs']}
   alerts = {alert['search_name']:alert['job_id'] for alert in dashboard['match_alerts']}
   self.assertEqual(alerts,{'Fictional remote':records['remote-job']['id'],'Fictional hybrid':records['hybrid-job']['id']})
   self.assertEqual(records['old-flag']['work_arrangement'],'unknown')
   self.assertEqual(records['old-flag']['location_eligibility'],'Review')
   job_id = records['remote-job']['id']
   with app.connect() as c:
    c.execute("UPDATE tracking SET notes='Fictional application note' WHERE job_id=?",(job_id,))
   feed.side_effect=TimeoutError('Fictional feed timeout')
   app.LOCK.acquire()
   interrupted = app.run_pipeline()
   self.assertEqual(interrupted['state'],'partial')
   self.assertTrue(any('ashby/fictional' in failure for failure in interrupted['failures']))
   self.assertEqual(next(row for row in app.snapshot()['jobs'] if row['id']==job_id)['work_arrangement'],'remote')
   feed.side_effect=None
   posts[0].pop('workplaceType')
   app.LOCK.acquire()
   self.assertEqual(app.run_pipeline()['state'],'success')
   refreshed = next(row for row in app.snapshot()['jobs'] if row['id']==job_id)
   self.assertEqual((refreshed['work_arrangement'],refreshed['location_eligibility']),('unknown','Review'))
   self.assertEqual(refreshed['notes'],'Fictional application note')
   self.assertEqual(len(app.snapshot()['match_alerts']),2)

 def test_lever_workplace_values_and_conflicting_posting_text(self):
  postings = [dict(id=mode,text='Fictional Specialist',categories={'location':'Austin, TX'},workplaceType=mode,
                   applyUrl=f'https://jobs.lever.co/fictional/{mode}/apply')
              for mode in ('remote','hybrid','on-site','unspecified')]
  with patch.object(app,'fetch',return_value=postings):
   jobs = app.board_jobs('lever','fictional')
  self.assertEqual([app.work_arrangement(job) for job in jobs],['remote','hybrid','onsite','unknown'])
  criteria = dict(target_locations=['Austin, TX'],workplace_types=['remote'])
  self.assertEqual(app.location_eligibility(jobs[1],criteria)[0],'Rejected')
  conflicting = dict(jobs[0],description='You must work from the office three days per week.')
  self.assertEqual(app.location_eligibility(conflicting,criteria),
                   ('Review','Employer details disagree about the work arrangement','Other'))
  onsite = dict(jobs[2],workplace_type=None)
  self.assertEqual(app.location_eligibility(onsite,dict(workplace_types=['onsite']))[0],'Review')
  self.assertEqual(app.location_eligibility(jobs[2],dict(workplace_types=['onsite']))[0],'Eligible')

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
 def test_generic_search_keeps_distinct_requisitions_through_failure_and_retry(self):
  _, cfg = self.pipeline_fixture()
  base = 'https://example.com/careers?posting='
  cfg.update(categories=['Billing Analyst'], preferred_skills=['Excel'], skill_groups=[],
             target_locations=['Austin, TX'], workplace_types=['onsite'], salary_floor=95000,
             salary_policy='minimum', additional_boards={},
             additional_employer_urls=[base+'101',base+'102',base+'101&utm_source=example'],
             generic_urls_per_run=5)
  criteria = dict(name='Fictional billing', title_terms=['Billing'], skills=['Excel'],
                  locations=['Austin, TX'], workplace_types=['onsite'], salary_min=85000,
                  salary_max=None, enabled=True)
  self.assertEqual(app.prototype.change_saved_search(app,{'action':'save','criteria':criteria})[0],200)
  attempts = []
  fail = False

  def public_fixture(request, **kwargs):
   url = request.full_url
   self.assertIn(url,(base+'101',base+'102'))
   attempts.append(url)
   if fail and url == base+'102':
    raise TimeoutError('Fictional employer timeout')
   posting = {'@type':'JobPosting','title':'Fictional Billing Analyst','description':'This role is on-site. Reconcile payments in Excel.',
              'hiringOrganization':{'name':'Fictional Employer','sameAs':'https://example.com/'},
              'jobLocation':{'address':{'addressLocality':'Austin','addressRegion':'TX'}},
              'baseSalary':{'currency':'USD','value':{'minValue':90000,'maxValue':110000,'unitText':'YEAR'}}}
   if url == base+'102':
    posting['baseSalary']['value'] = {'value':100000,'unitText':'YEAR'}
   html = ('<h1>Fictional Billing Analyst</h1><a href="/apply">Apply</a>'
           '<script type="application/ld+json">'+json.dumps(posting)+'</script>')
   return html.encode(),url

  with patch.object(app,'config',return_value=cfg), patch.object(app,'board_jobs',return_value=[]), \
       patch.object(app,'read_response',side_effect=public_fixture):
   app.LOCK.acquire()
   first = app.run_pipeline()
   self.assertEqual(first['new_review'],2)
   self.assertEqual(len(attempts),4)
   records={j['url']:j for j in app.records() if j['url'].startswith(base)}
   self.assertEqual(set(records),{base+'101',base+'102'})
   self.assertEqual(app.annual_base_bounds(records[base+'102']),(100000,100000))
   self.assertEqual(app.salary_assessment(records[base+'101'],cfg)[0],'Rejected')
   self.assertEqual(app.salary_assessment(records[base+'102'],cfg)[0],'Eligible')
   ids={j['id'] for j in records.values()}
   with app.connect() as c:
    c.execute("UPDATE tracking SET notes='Keep this application' WHERE job_id=?",(records[base+'102']['id'],))
   fail = True
   app.LOCK.acquire()
   self.assertEqual(app.run_pipeline()['state'],'partial')
   fail = False
   app.LOCK.acquire()
   app.run_pipeline()
   dashboard = app.snapshot()
  self.assertEqual({j['id'] for j in dashboard['jobs'] if j['url'].startswith(base)},ids)
  self.assertEqual({a['job_id'] for a in dashboard['match_alerts']},ids)
  self.assertEqual(len(dashboard['match_alerts']),2)
  self.assertEqual(next(j for j in dashboard['jobs'] if j['url']==base+'102')['notes'],'Keep this application')

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
  postings[0].update(title='Billing Specialist', description='This role is on-site. Reconciliation duties.', posted='2026-11-01',
                     salary_min=90000, salary_max=110000, salary_currency='USD', salary_period='year',
                     salary_type='base')
  def board(platform, slug):
   return postings if (platform, slug) == ('smartrecruiters', 'fictional') else []
  with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_jobs', side_effect=board), \
       patch.object(app, 'read_response', return_value=(b'<h1>Billing Specialist</h1>', postings[0]['url'])):
   app.LOCK.acquire()
   report = app.run_pipeline()
   self.assertEqual(app.snapshot()['unread_match_count'], 1)
  self.assertEqual(report['new_review'], 1)
  self.assertEqual(report['deferred_source_details'], 4)

 def test_employer_search_enriches_an_external_application_without_creating_alert(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(additional_boards={'lever': ['fictional']})
  criteria = dict(name='Fictional billing search', title_terms=['Billing'], skills=['Reconciliation'],
                  locations=['Austin, TX'], workplace_types=['onsite'], salary_min=85000,
                  salary_max=None, enabled=True)
  self.assertEqual(app.prototype.change_saved_search(app, {'action': 'save', 'criteria': criteria})[0], 200)
  url = 'https://jobs.lever.co/fictional/req-22'
  _, saved = app.add_external_application(dict(title='Billing Analyst', employer='Fictional Employer',
                                                url=url, status='Applied', notes='Fictional application note.'))
  posting = dict(title='Billing Analyst', employer='Fictional Employer', location='Austin, TX', workplace_type='onsite',
                 url=url+'/apply', requisition='req-22', source='Lever public live board',
                 description='Responsibilities: Reconciliation.', availability='Open',
                 salary_min=90000, salary_max=110000, salary_currency='USD', salary_period='year',
                 salary_type='base')
  def board(platform, slug):
   return [posting] if (platform, slug) == ('lever', 'fictional') else []
  with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_jobs', side_effect=board), \
       patch.object(app, 'verify_application', side_effect=ValueError('Fictional form not verified')):
   app.LOCK.acquire()
   report = app.run_pipeline()
  self.assertEqual(report['duplicates'], 1)
  matching = [job for job in app.records() if job['title'] == 'Billing Analyst']
  self.assertEqual(len(matching), 1)
  self.assertEqual(matching[0]['id'], saved['job_id'])
  self.assertFalse(matching[0].get('external_application'))
  self.assertEqual(matching[0]['notes'], 'Fictional application note.')
  self.assertEqual(app.snapshot()['unread_match_count'], 0)

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
       patch.object(app.POSTING_OPENER, 'open') as request, patch.object(app, 'firecrawl') as render:
   response = request.return_value.__enter__.return_value
   response.url = url
   response.read.return_value = b'<title>Financial Analyst</title>'
   render.return_value = {'html': '<title>Financial Analyst</title><form><button>Submit application</button></form>',
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

 def test_direct_posting_rejects_wrong_role_redirect_and_fake_form(self):
  url = 'https://jobs.lever.co/fictional/billing-22/apply'
  job = {'url': url, 'title': 'Billing Analyst'}
  form = '<form><button>Submit application</button></form>'
  with patch.object(app,'read_response') as read:
   with self.assertRaisesRegex(ValueError, 'feed requisition'):
    app.verify_application(dict(job, requisition='different-requisition'), render_form=False)
   read.assert_not_called()
  with self.assertRaisesRegex(ValueError, 'redirected'):
   app.application_form_visible(job, '<h1>Billing Analyst</h1>'+form, url.replace('billing-22', 'billing-23'))
  with self.assertRaisesRegex(ValueError, 'single requisition'):
   app.application_form_visible(job, '<h1>Billing Analyst</h1>'+form, url.replace('/apply', '/careers'))
  with self.assertRaisesRegex(ValueError, 'title'):
   app.application_form_visible(job, '<h1>Senior Billing Analyst</h1>'+form, url)
  with self.assertRaisesRegex(ValueError, 'title'):
   app.application_form_visible(job, '<script>"<h1>Billing Analyst</h1>"</script>'+form, url)
  with self.assertRaisesRegex(ValueError, 'unavailable'):
   app.application_form_visible(job, '<h1>Billing Analyst</h1><p>This job is no longer available.</p>'+form, url)
  self.assertFalse(app.application_form_visible(job, '<h1>Billing Analyst</h1><form>Submit application</form>', url))
  self.assertTrue(app.application_form_visible(job, '<title>Fictional Employer - Billing Analyst</title>'+form, url))
  self.assertEqual(app.posting_reference('https://boards.greenhouse.io/fictional/jobs/12?utm_source=test'),
                   app.posting_reference('https://job-boards.greenhouse.io/fictional/jobs/12'))
  self.assertNotEqual(app.posting_reference('https://example.com/careers?posting=1'),
                      app.posting_reference('https://example.com/careers?posting=2'))

 def test_generic_posting_refuses_requisition_substitution(self):
  url = 'https://example.com/careers?posting=1'
  with patch.object(app,'read_response',return_value=(b'<title>Billing Analyst</title>',url.replace('=1','=2'))):
   with self.assertRaisesRegex(ValueError,'redirected'):
    app.generic_posting(url,{},'')

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

 def test_search_continues_after_network_timeout_and_allows_retry(self):
  cfg = dict(app.config(), additional_boards={'ashby':['slow','working']}, generic_urls_per_run=0,
             firecrawl_enabled=False, public_web_search_enabled=False, request_delay_seconds=0)
  before = {j['id']: j['availability'] for j in app.records()}
  slow_started = threading.Event()
  allow_slow_completion = threading.Event()
  retry = False

  def board(platform, slug):
   if slug == 'slow' and not retry:
    def stalled(_):
     slow_started.set()
     allow_slow_completion.wait(4)
     return []
    return app.network_call(stalled, seconds=0.35)
   return []

  try:
   with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_identity', return_value=None), \
        patch.object(app, 'board_jobs', side_effect=board):
    self.assertTrue(app.start_run())
    self.assertTrue(slow_started.wait(2))
    current = app.search_status()
    self.assertTrue(current['running'])
    self.assertEqual(current['run']['progress']['source'], 'slow')
    self.assertFalse(app.start_run())
    self.assertTrue(app.LOCK.acquire(timeout=3))
    app.LOCK.release()
    status = app.search_status()
    self.assertFalse(status['running'])
    self.assertEqual(status['run']['state'], 'partial')
    self.assertEqual(status['run']['failures'], 1)
    self.assertEqual({j['id']: j['availability'] for j in app.records()}, before)
    retry = True
    self.assertTrue(app.start_run())
    self.assertTrue(app.LOCK.acquire(timeout=3))
    app.LOCK.release()
    result = app.search_status()
    self.assertEqual(result['run']['state'], 'success')
    self.assertGreater(result['run']['id'], status['run']['id'])
  finally:
   allow_slow_completion.set()

 def test_search_time_limit_defers_sources_without_discarding_results(self):
  cfg = dict(app.config(), additional_boards={'ashby':['first','second','third']}, generic_urls_per_run=0,
             firecrawl_enabled=False, public_web_search_enabled=False, request_delay_seconds=0)
  visited = []
  release = threading.Event()

  def board(platform, slug):
   visited.append(slug)
   if slug == 'second':
    app.network_call(lambda _: release.wait(4))
   return []

  try:
   with patch.object(app, 'config', return_value=cfg), patch.object(app, 'board_identity', return_value=None), \
        patch.object(app, 'board_jobs', side_effect=board), patch.object(app, 'SEARCH_SECONDS', 0.5):
    app.LOCK.acquire()
    report = app.run_pipeline()
   self.assertEqual(visited, ['first', 'second'])
   self.assertEqual(report['state'], 'partial')
   self.assertTrue(any('1 employer boards deferred' in error for error in report['failures']))
   self.assertFalse(app.search_status()['running'])
  finally:
   release.set()

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
 def test_separate_commute_and_remote_geography(self):
  cfg = dict(app.config(), target_locations=['Portland, OR'], remote_hiring_locations=['United States'],
             workplace_types=['remote', 'hybrid'])
  cases = [
      ('Portland, OR', 'hybrid', '', 'Eligible'),
      ('Portland', 'hybrid', '', 'Review'),
      ('Seattle, WA', 'hybrid', '', 'Rejected'),
      ('Portland, OR', 'remote', '', 'Review'),
      ('United States', 'remote', '', 'Eligible'),
      ('United States', 'remote', 'Applicants must reside in Virginia.', 'Review'),
      ('Portland, OR', 'onsite', '', 'Rejected'),
  ]
  for location, mode, description, expected in cases:
   with self.subTest(location=location, mode=mode, description=description):
    job = dict(location=location, workplace_type=mode, description=description)
    self.assertEqual(app.location_eligibility(job, cfg)[0], expected)
  self.assertEqual(app.discovery_regions(cfg), ['remote United States', 'Portland, OR'])

 def test_new_geography_has_no_personal_defaults(self):
  cfg = dict(legacy_geography=False, remote_hiring_locations=[])
  self.assertEqual(app.discovery_regions(cfg), ['remote'])
  self.assertEqual(app.location_eligibility({'location': 'Portland, OR', 'workplace_type': 'onsite'}, cfg)[0], 'Eligible')
  self.assertEqual(app.location_eligibility({'location': 'Remote - United States'}, cfg)[0], 'Review')

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
 def test_entire_range_policy_blocks_approval_and_keeps_prior_review_history(self):
  _, cfg = self.pipeline_fixture()
  cfg.update(salary_floor=90000,salary_policy='minimum',target_locations=['United States'],
             workplace_types=['remote'],categories=['Billing Analyst'])
  job = dict(title='Fictional Billing Analyst',employer='Fictional Employer',url='https://example.com/billing',
             location='Remote - United States',availability='Open',
             description='Annual base salary: $75,000 – $110,000.')
  with app.connect() as c:
   job_id,_ = app.upsert(c,job)
   c.execute("UPDATE tracking SET notes='Fictional application note' WHERE job_id=?",(job_id,))
  def stored():
   return next(row for row in app.records() if row['id']==job_id)
  def shown():
   return next(row for row in app.snapshot()['jobs'] if row['id']==job_id)
  with patch.object(app,'config',return_value=cfg):
   self.assertEqual(shown()['queue'],'Excluded')
   self.assertIn('Published minimum',shown()['review_blockers'][0])
   code, result = app.save_review(job_id,self.review_payload(stored()))
   self.assertEqual(code,400)
   self.assertIn('Published minimum',result['error'])
   cfg['salary_policy']='overlap'
   self.assertEqual(shown()['salary_eligibility'],'Eligible')
   self.assertEqual(app.save_review(job_id,self.review_payload(stored()))[0],200)
   cfg['salary_policy']='minimum'
   self.assertEqual(shown()['queue'],'Excluded')
   self.assertEqual(shown()['review_decision'],'Approved')
   self.assertEqual(shown()['notes'],'Fictional application note')

 def test_unusable_or_partial_pay_stays_in_review(self):
  cfg = dict(app.config(),salary_floor=90000,salary_policy='minimum')
  base = dict(salary_currency='USD',salary_period='year',salary_type='base',location='Remote - United States')
  for low,high in (('95000',110000),(True,110000),(120000,110000),(90000,float('inf')),(None,110000)):
   with self.subTest(low=low,high=high):
    job = app.assess(dict(base,salary_min=low,salary_max=high),cfg)
    self.assertEqual(job['salary_eligibility'],'Review')
    self.assertFalse(app.salary_qualifies(job,cfg))
  unrelated = dict(base,salary_currency='CAD',salary_min=95000,salary_max=110000,
                   description='Annual base salary: $95,000 – $110,000.')
  self.assertEqual(app.assess(unrelated,cfg)['salary_eligibility'],'Review')
  self.assertEqual(unrelated['salary_currency'],'CAD')

 def test_description_pay_needs_annual_period_attached_to_range(self):
  cfg = dict(app.config(),salary_floor=90000)
  for description, expected in (
   ('Base pay: $95,000 to $110,000. Includes annual leave.', 'Review'),
   ('Base pay: $95,000 to $110,000 per year.', 'Eligible'),
   ('Base salary (annual): $95,000 – $110,000.', 'Eligible'),
   ('Annual base salary: $,,, to $110,000.', 'Review'),
  ):
   with self.subTest(description=description):
    self.assertEqual(app.assess({'description':description},cfg)['salary_eligibility'],expected)

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
