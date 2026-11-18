"""Isolated PostgreSQL checks; never connect to an application database."""
import os
import threading
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import postgres_store


class RowTests(unittest.TestCase):
    def test_timing_summary_is_bounded_and_uses_fixed_labels(self):
        from collections import deque
        import app
        timings = {name: deque(maxlen=100) for name in postgres_store._timings}
        with patch.object(postgres_store, '_timings', timings):
            for seconds in range(101):
                postgres_store.record_timing('identity', seconds)
            handler = types.SimpleNamespace(path='/api/recruiter?status=1&private=fictional')
            with patch.object(app.time, 'monotonic', side_effect=[2, 2.5]):
                app.timed_request(lambda _: None)(handler)
            summary = postgres_store.timing_summary()
            self.assertEqual(summary['identity'], {'samples': 100, 'mean_seconds': 50.5, 'max_seconds': 100})
            self.assertEqual(summary['recruiter_status']['samples'], 1)
            self.assertNotIn('fictional', str(summary))
            with self.assertRaises(ValueError):
                postgres_store.record_timing('private', 1)
            raw = MagicMock()
            postgres_store.Connection(raw).execute("SELECT 'fictional secret'")
            summary = postgres_store.timing_summary()
            self.assertEqual(summary['sql_select']['samples'], 1)
            self.assertNotIn('fictional secret', str(summary))

    def test_immediate_transaction_acquires_transaction_scoped_lock(self):
        raw = MagicMock()
        connection = postgres_store.Connection(raw)
        connection.execute('BEGIN IMMEDIATE')
        raw.execute.assert_called_once_with('SELECT pg_advisory_xact_lock(754086278)')

    def test_managed_identity_credential_reused_and_token_requested_each_time(self):
        identity = types.ModuleType('azure.identity')
        credential = MagicMock()
        credential.get_token.side_effect = [types.SimpleNamespace(token='first'),
                                            types.SimpleNamespace(token='renewed')]
        identity.ManagedIdentityCredential = MagicMock(return_value=credential)
        azure = types.ModuleType('azure')
        azure.identity = identity
        psycopg = types.ModuleType('psycopg')
        psycopg.connect = MagicMock()
        conninfo = types.ModuleType('psycopg.conninfo')
        conninfo.conninfo_to_dict = MagicMock(return_value={
            'host': 'example.postgres.database.azure.com', 'dbname': 'jobs',
            'user': 'identity', 'sslmode': 'verify-full'})
        with tempfile.NamedTemporaryFile() as root, \
             patch.object(postgres_store, '_managed_identity_credential', None), \
             patch.dict('sys.modules', {'azure': azure, 'azure.identity': identity,
                                       'psycopg': psycopg, 'psycopg.conninfo': conninfo}):
            postgres_store.connect_azure('fictional', root.name)
            postgres_store.connect_azure('fictional', root.name)
        identity.ManagedIdentityCredential.assert_called_once_with()
        self.assertEqual(credential.get_token.call_count, 2)
        self.assertEqual([call.kwargs['password'] for call in psycopg.connect.call_args_list],
                         ['first', 'renewed'])

    def test_row_supports_named_and_positional_access(self):
        row = postgres_store.Row(('id', 'note'), (12, 'fictional note'))
        self.assertEqual((row[0], row['note']), (12, 'fictional note'))
        self.assertEqual(dict(row), {'id': 12, 'note': 'fictional note'})
        self.assertEqual(tuple(row), (12, 'fictional note'))

    def test_parameter_conversion_preserves_literals(self):
        self.assertEqual(postgres_store.parameterize("SELECT '?' AS marker WHERE value LIKE ? AND label='100%'"),
                         "SELECT '?' AS marker WHERE value LIKE %s AND label='100%%'")
        with self.assertRaises(ValueError):
            postgres_store.parameterize("SELECT 'unfinished")

    def test_postgres_search_requires_managed_backup_confirmation(self):
        import app
        with patch.dict(os.environ, {'JOBS_POSTGRES_DSN': 'fictional'}, clear=False):
            with patch.dict(os.environ, {'JOBS_POSTGRES_MANAGED_BACKUPS': '0'}):
                with self.assertRaisesRegex(RuntimeError, 'backups'):
                    app.backup()
            with patch.dict(os.environ, {'JOBS_POSTGRES_MANAGED_BACKUPS': '1'}):
                self.assertIsNone(app.backup())


@unittest.skipUnless(os.environ.get('JOBS_RUN_LOCAL_POSTGRES_TESTS') == '1',
                     'requires the isolated local PostgreSQL test server')
class LocalPostgresTests(unittest.TestCase):
    def setUp(self):
        # Deliberately fixed to the temporary test cluster, never an app DSN.
        self.connection = postgres_store.connect(
            'host=/private/tmp/jobs-pg-socket port=15432 dbname=postgres')
        self.schema = 'fictional_' + uuid4().hex
        self.connection.execute('CREATE SCHEMA ' + self.schema)
        self.connection.execute('SET LOCAL search_path TO ' + self.schema)
        postgres_store.initialize_empty_schema(self.connection)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)

    def test_schema_is_repeatable_and_preserves_tracking(self):
        c = self.connection
        postgres_store.initialize_empty_schema(c)
        job_id = c.execute('INSERT INTO jobs(identity,listing,created,updated) VALUES (%s,%s,%s,%s) RETURNING id',
                           ('fictional', '{}', 'today', 'today')).fetchone()[0]
        c.execute('INSERT INTO tracking(job_id,notes,updated) VALUES (%s,%s,%s)',
                  (job_id, 'fictional note', 'today'))
        c.execute('UPDATE jobs SET listing=%s WHERE id=%s', ('{"updated":true}', job_id))
        result = c.execute('SELECT notes FROM tracking WHERE job_id=%s', (job_id,)).fetchone()
        self.assertEqual(result['notes'], 'fictional note')

    def test_duplicate_identity_is_rejected(self):
        import psycopg
        c = self.connection
        statement = 'INSERT INTO jobs(identity,listing,created,updated) VALUES (%s,%s,%s,%s)'
        c.execute(statement, ('fictional', '{}', 'today', 'today'))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            c.execute(statement, ('fictional', '{}', 'today', 'today'))

    def test_adapter_preserves_quoted_text_and_transaction_lock(self):
        c = postgres_store.Connection(self.connection)
        self.assertTrue(c.in_transaction)
        c.execute('BEGIN IMMEDIATE')
        row = c.execute("SELECT '?' AS marker, ? AS value, '100%' AS percentage", ('fictional',)).fetchone()
        self.assertEqual((row['marker'], row['value'], row['percentage']), ('?', 'fictional', '100%'))

    def test_preferences_are_saved_without_changing_tracking(self):
        c = postgres_store.Connection(self.connection)
        self.assertEqual(postgres_store.read_preferences(c), {})
        prefs = {'additional_boards': {'lever': ['fictional-company']}, 'profile': 'fictional'}
        postgres_store.write_preferences(c, prefs)
        self.assertEqual(postgres_store.read_preferences(c), prefs)
        prefs['profile'] = 'updated fictional profile'
        postgres_store.write_preferences(c, prefs)
        self.assertEqual(postgres_store.read_preferences(c), prefs)

    def test_azure_connection_requires_verified_tls_and_approved_host(self):
        import psycopg
        identity = types.ModuleType('azure.identity')
        credential = MagicMock()
        credential.get_token.return_value.token = 'fictional-token'
        identity.ManagedIdentityCredential = MagicMock(return_value=credential)
        azure = types.ModuleType('azure')
        azure.identity = identity
        with tempfile.NamedTemporaryFile() as root, \
             patch.dict('sys.modules', {'azure': azure, 'azure.identity': identity}), \
             patch.object(psycopg, 'connect', return_value=MagicMock()) as driver:
            base = 'host=example.postgres.database.azure.com dbname=jobs user=identity'
            with self.assertRaises(ValueError):
                postgres_store.connect_azure(base + ' sslmode=require', root.name)
            with self.assertRaises(ValueError):
                postgres_store.connect_azure('host=attacker.example dbname=jobs user=identity sslmode=verify-full', root.name)
            with self.assertRaises(ValueError):
                postgres_store.connect_azure(base + ' sslmode=verify-full password=fictional', root.name)
            self.assertFalse(credential.get_token.called)
            postgres_store.connect_azure(base + ' sslmode=verify-full', root.name)
            self.assertEqual(driver.call_args.kwargs['password'], 'fictional-token')
            self.assertEqual(driver.call_args.kwargs['sslrootcert'], root.name)
    def test_app_upsert_keeps_existing_tracking(self):
        import app
        c = postgres_store.Connection(self.connection)
        job = {'url': 'https://jobs.lever.co/fictional/123', 'employer': 'Fictional Co',
               'title': 'Analyst', 'location': 'Remote', 'description': 'Fictional first listing'}
        job_id, created = app.upsert(c, job)
        self.assertTrue(created)
        c.execute('UPDATE tracking SET notes=? WHERE job_id=?', ('fictional note', job_id))
        job['description'] = 'Updated fictional listing'
        self.assertEqual(app.upsert(c, job), (job_id, False))
        self.assertEqual(c.execute('SELECT notes FROM tracking WHERE job_id=?', (job_id,)).fetchone()[0],
                         'fictional note')

    def test_app_starts_empty_and_records_survive_reconnect(self):
        import app
        import json
        import recruiter
        import time
        from pathlib import Path
        from fixtures.recruiter_fixture import MARA, fake_ai
        from test_recruiter import PREFS

        self.connection.commit()  # commit only this randomly named, fictional test schema
        self.addCleanup(self.drop_committed_test_schema)
        dsn = ('host=/private/tmp/jobs-pg-socket port=15432 dbname=postgres '
               "options='-c search_path=" + self.schema + "'")
        def connect_test():
            return postgres_store.Connection(postgres_store.connect(dsn))

        base = json.loads((Path(__file__).parent / 'config.example.json').read_text())
        cfg = app.prototype.settings(base, app.DATA)
        with patch.object(app, 'connect', side_effect=connect_test), patch.object(app, 'config', return_value=cfg):
            app.init()
            self.assertEqual(app.records(), [])
            job = {'url': 'https://jobs.lever.co/fictional/456', 'employer': 'Fictional Co',
                   'title': 'Analyst', 'location': 'Remote', 'description': 'Fictional listing'}
            with app.connect() as c:
                job_id, _ = app.upsert(c, job)
                c.execute('UPDATE tracking SET notes=? WHERE job_id=?', ('fictional note', job_id))
            self.assertEqual(app.records()[0]['notes'], 'fictional note')
            app.init()
            self.assertEqual(app.records()[0]['notes'], 'fictional note')
            with patch.object(recruiter, 'ai', side_effect=fake_ai):
                status, _ = recruiter.start(app, {'action': 'analyze', 'version': 0, 'resume': MARA})
                self.assertEqual(status, 202)
                until = time.monotonic() + 10
                while recruiter.LOCK.locked() and time.monotonic() < until:
                    time.sleep(.01)
                self.assertFalse(recruiter.LOCK.locked())
                self.assertEqual(recruiter.read(app)['stage'], 'ready')
                app.init()
                self.assertEqual(recruiter.read(app)['stage'], 'ready')
                def fictional_pipeline(*args, **kwargs):
                    app.LOCK.release()
                    return {'state': 'complete'}
                with patch.object(app, 'run_pipeline', side_effect=fictional_pipeline):
                    state = recruiter.read(app)
                    status, _ = recruiter.start(app, dict(action='search', version=state['version'], preferences=PREFS))
                    self.assertEqual(status, 202)
                    until = time.monotonic() + 10
                    while recruiter.LOCK.locked() and time.monotonic() < until:
                        time.sleep(.01)
                    self.assertFalse(recruiter.LOCK.locked())
                    state = recruiter.read(app)
                    self.assertEqual(state['stage'], 'complete', state.get('error'))
                    self.assertEqual(len(state['matches']), 1)
                current = recruiter.read(app)
                self.assertEqual(recruiter.start(app, {'action': 'reset', 'version': current['version']})[0], 200)
                self.assertEqual(recruiter.read(app)['stage'], 'empty')
                self.assertEqual(app.records()[0]['notes'], 'fictional note')

            response = MagicMock()
            response.__enter__.return_value = response
            result = {'status': 'incomplete', 'usage': {'input_tokens': 120, 'output_tokens': 30,
                      'input_tokens_details': {'cached_tokens': 20}}}
            ai_cfg = dict(cfg, ai_enabled=True, ai_daily_limit=10, ai_model='gpt-5.4-mini')
            with patch.object(app, 'config', return_value=ai_cfg), \
                 patch.object(recruiter.prototype, 'ai_key', return_value='fictional-test-token'), \
                 patch('urllib.request.urlopen', return_value=response), \
                 patch.object(recruiter.json, 'load', return_value=result):
                with self.assertRaises(ValueError):
                    recruiter.ai(app, 'career_strategy', {'resume': MARA}, recruiter.STRATEGY)
            usage = recruiter.usage_report(app)['operations']
            self.assertEqual((usage[0]['input_tokens'], usage[0]['output_tokens']), (120, 30), usage)

    def test_concurrent_saves_do_not_duplicate_job(self):
        import app
        self.connection.commit()
        self.addCleanup(self.drop_committed_test_schema)
        dsn = ('host=/private/tmp/jobs-pg-socket port=15432 dbname=postgres '
               "options='-c search_path=" + self.schema + "'")
        barrier = threading.Barrier(2)
        outcomes, failures = [], []
        job = {'url': 'https://jobs.lever.co/fictional/789', 'employer': 'Fictional Co',
               'title': 'Analyst', 'location': 'Remote', 'description': 'Fictional listing'}

        def save():
            try:
                with postgres_store.Connection(postgres_store.connect(dsn)) as c:
                    barrier.wait(timeout=5)
                    c.execute('SELECT 1')  # a previous read has already opened a transaction
                    outcomes.append(app.upsert(c, dict(job)))
            except Exception as exc:
                failures.append(exc)

        threads = [threading.Thread(target=save) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(outcomes[0][0], outcomes[1][0])
        self.assertEqual(sorted(created for _, created in outcomes), [False, True])

    def test_app_preferences_survive_restart(self):
        import app
        import hashlib
        import json
        self.connection.rollback()
        self.connection.execute('CREATE SCHEMA ' + self.schema)
        self.connection.commit()
        self.addCleanup(self.drop_committed_test_schema)
        dsn = ('host=/private/tmp/jobs-pg-socket port=15432 dbname=postgres '
               "options='-c search_path=" + self.schema + "'")
        def connect_test():
            return postgres_store.Connection(postgres_store.connect(dsn))
        with patch.dict(os.environ, {'JOBS_POSTGRES_DSN': 'fictional-test-enabled'}), \
             patch.object(app, 'connect', side_effect=connect_test):
            app.init()
            before = app.config()
            revision = hashlib.sha256(json.dumps(app.prototype.public_preferences(before), sort_keys=True).encode()).hexdigest()
            changed = {'profile': 'Fictional analyst profile', 'additional_boards': {'lever': ['fictional']}}
            self.assertEqual(app.prototype.save_preferences(app, {'preferences': changed, 'revision': revision})[0], 200)
            app.init()
            self.assertEqual(app.config()['profile'], changed['profile'])
            self.assertEqual(app.config()['additional_boards'], changed['additional_boards'])

    def test_full_pipeline_uses_fictional_feed_and_retains_tracking(self):
        import app
        import json
        from pathlib import Path
        self.connection.commit()
        self.addCleanup(self.drop_committed_test_schema)
        dsn = ('host=/private/tmp/jobs-pg-socket port=15432 dbname=postgres '
               "options='-c search_path=" + self.schema + "'")
        def connect_test():
            return postgres_store.Connection(postgres_store.connect(dsn))
        cfg = app.prototype.settings(json.loads((Path(__file__).parent / 'config.example.json').read_text()), app.DATA)
        cfg.update(additional_boards={'lever': ['fictional-company']}, additional_employer_urls=[],
                   public_web_search_enabled=False, firecrawl_enabled=False, request_delay_seconds=0,
                   recruiter_discovery=True, generic_urls_per_run=0)
        feed = [dict(id='fictional-id', text='Financial Analyst',
                     applyUrl='https://jobs.lever.co/fictional-company/fictional-id',
                     categories={'location': 'Remote - United States'}, workplaceType='remote',
                     descriptionPlain='Fictional responsibilities in accounting and analysis.')]
        def response(request, **kwargs):
            url = request.full_url
            if url.startswith('https://api.lever.co/v0/postings/fictional-company?'):
                return json.dumps(feed).encode(), url
            if url == feed[0]['applyUrl']:
                return b'<html><h1>Financial Analyst</h1><form><input name="resume"/></form></html>', url
            raise AssertionError('Unexpected network request: ' + url)
        with patch.object(app, 'connect', side_effect=connect_test), \
             patch.object(app, 'config', return_value=cfg), \
             patch.object(app, 'backup'), \
             patch.object(app, 'read_response', side_effect=response), \
             patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected external request')):
            app.init()
            app.LOCK.acquire()
            report = app.run_pipeline('fictional-test', config_override=cfg)
            self.assertEqual(report['failures'], [])
            self.assertEqual(len(app.records()), 1)
            job_id = app.records()[0]['id']
            with app.connect() as c:
                c.execute('UPDATE tracking SET notes=? WHERE job_id=?', ('fictional note', job_id))
            app.LOCK.acquire()
            report = app.run_pipeline('fictional-test', config_override=cfg)
            self.assertEqual(report['failures'], [])
            self.assertEqual(app.records()[0]['notes'], 'fictional note')

    def drop_committed_test_schema(self):
        self.connection.rollback()
        self.connection.execute('DROP SCHEMA IF EXISTS ' + self.schema + ' CASCADE')
        self.connection.commit()
