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
  with app.connect() as c:
   c.execute("UPDATE tracking SET status='Applied',notes='Wife applied',application_date='2026-11-06' WHERE job_id=?",(j['id'],))
   j['availability']='Closed';app.upsert(c,j)
  current=app.records()[0];self.assertEqual(current['status'],'Applied');self.assertEqual(current['notes'],'Wife applied');self.assertEqual(current['availability'],'Closed')
  with app.connect() as c:j['availability']='Open';app.upsert(c,j)
  self.assertEqual(app.records()[0]['application_date'],'2026-11-06');self.assertEqual(len(app.records()),50)
 def test_tracking_parameters_deduplicate(self):
  j=app.records()[0];j['url']+='?utm_source=test#apply'
  with app.connect() as c:_,added=app.upsert(c,j)
  self.assertFalse(added);self.assertEqual(len(app.records()),50)
 def test_unknown_salary_not_qualified(self):
  j={'title':'Financial Analyst','location':'Remote - United States','remote':True,'description':'Excel financial reconciliation','availability':'Open'}
  self.assertEqual(app.assess(j,app.config())['queue'],'Review')
 def test_restricted_remote_needs_review(self):
  j={'title':'Financial Analyst','location':'Remote United States','remote':True,'description':'Must reside in California only','availability':'Open','salary_min':85000,'salary_max':100000,'salary_currency':'USD','salary_period':'year','salary_type':'base'}
  self.assertEqual(app.assess(j,app.config())['eligibility'],'Review')
 def test_below_floor_excluded(self):
  j={'title':'Financial Analyst','location':'Jacksonville','description':'Excel financial','availability':'Open','salary_max':65000,'salary_currency':'USD','salary_period':'year','salary_type':'base'}
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
 def test_overlapping_run_rejected(self):
  app.LOCK.acquire()
  try:self.assertFalse(app.start_run())
  finally:app.LOCK.release()
 def test_only_requested_locations_pass(self):
  cases=[('London, UK',True,'Rejected'),('Remote - Colombia',True,'Rejected'),('Texas',True,'Rejected'),('Bangalore, India',False,'Rejected'),('Atlanta, GA',False,'Rejected'),('Duluth, MN',False,'Review'),('Jacksonville, NC',False,'Review'),('Jacksonville, FL',False,'Eligible'),('Buford, GA Hybrid',False,'Eligible'),('Suwanee, Georgia',False,'Eligible'),('Remote - United States',True,'Eligible'),('U.S. Remote',True,'Eligible'),('Remote',True,'Review'),('Remote USA Hybrid',True,'Review')]
  for loc,remote,expected in cases:
   with self.subTest(location=loc):self.assertEqual(app.location_eligibility({'location':loc,'remote':remote},app.config())[0],expected)
 def test_remote_restricted_state_not_eligible(self):
  j={'location':'Remote - US','remote':True,'description':'You must reside in Virginia.'}
  self.assertNotEqual(app.location_eligibility(j,app.config())[0],'Eligible')
 def test_unrelated_word_only_does_not_disqualify_us_remote(self):
  j={'location':'Remote - US','remote':True,'description':'Only shortlisted candidates will be contacted.'}
  self.assertEqual(app.location_eligibility(j,app.config())[0],'Eligible')
 def test_discovery_does_not_insert_foreign_remote_jobs(self):
  j,cfg=self.pipeline_fixture()
  bad={'title':'Financial Analyst','employer':'Binance.US','url':'https://jobs.ashbyhq.com/binance.us/outside-location-test/application','location':'London, UK','remote':True,'description':'Financial reporting and Excel','availability':'Open'}
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
