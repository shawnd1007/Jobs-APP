"""Track dashboard changes in the same transactions as the underlying records."""
import hashlib
import re
from uuid import uuid4


MAX_PATCH_JOBS = 100
INSTANCE = uuid4().hex
CURSOR = re.compile(r'([a-f0-9]{24})\.([0-9]{1,19})\.([0-9]{1,16})(?:\.([01]))?')
JOB_TABLES = ('tracking', 'reviews', 'job_interests', 'ai_reviews')
GLOBAL_TABLES = ('source_health', 'saved_searches', 'match_alerts', 'ai_usage',
                 'workspace_preferences', 'recruiter_state')
# These listing fields determine which sources appear in prototype.source_snapshot.
SOURCE_FIELDS = ('url', 'external_application', 'identity_review')


def init(c):
    c.execute('''CREATE TABLE IF NOT EXISTS dashboard_revision (id INTEGER PRIMARY KEY CHECK(id=1),
              revision BIGINT NOT NULL, global_revision BIGINT NOT NULL)''')
    c.execute('INSERT INTO dashboard_revision VALUES(1,0,0) ON CONFLICT(id) DO NOTHING')
    c.execute('''CREATE TABLE IF NOT EXISTS dashboard_metadata_revision (id INTEGER PRIMARY KEY CHECK(id=1),
              runs_revision BIGINT NOT NULL, listings_revision BIGINT NOT NULL)''')
    c.execute('INSERT INTO dashboard_metadata_revision VALUES(1,0,0) ON CONFLICT(id) DO NOTHING')
    c.execute('''CREATE TABLE IF NOT EXISTS dashboard_job_revision (
              job_id BIGINT PRIMARY KEY, revision BIGINT NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS dashboard_job_revision_order ON dashboard_job_revision(revision)')
    if getattr(c, 'postgres_connection', False):
        init_postgres(c)
    else:
        init_sqlite(c)


def init_postgres(c):
    new_source = ', '.join(f"new_listing->'{field}'" for field in SOURCE_FIELDS)
    old_source = ', '.join(f"old_listing->'{field}'" for field in SOURCE_FIELDS)
    c.execute(f'''CREATE OR REPLACE FUNCTION jobs_update_dashboard_revision() RETURNS trigger
              LANGUAGE plpgsql AS $$
              DECLARE changed_job BIGINT; next_revision BIGINT;
                      scope TEXT := TG_ARGV[0]; old_listing JSONB; new_listing JSONB;
              BEGIN
                  IF TG_TABLE_NAME = 'recruiter_state' AND TG_OP = 'UPDATE' THEN
                      IF NEW.value::jsonb->'preferences' IS NOT DISTINCT FROM OLD.value::jsonb->'preferences' THEN
                          RETURN NULL;
                      END IF;
                  END IF;
                  IF scope = 'listing' THEN
                      scope := 'global';
                      IF TG_OP = 'UPDATE' THEN
                          IF NEW.id = OLD.id THEN
                              BEGIN
                                  old_listing := OLD.listing::jsonb;
                                  new_listing := NEW.listing::jsonb;
                                  IF ({new_source}) IS NOT DISTINCT FROM ({old_source}) THEN
                                      scope := 'listing';
                                      changed_job := NEW.id;
                                  END IF;
                              EXCEPTION WHEN data_exception THEN
                                  scope := 'global';
                              END;
                          END IF;
                      END IF;
                  ELSIF TG_TABLE_NAME = 'tracking' AND TG_OP <> 'UPDATE' THEN
                      scope := 'global';
                  ELSIF scope = 'job' THEN
                      IF TG_OP = 'DELETE' THEN changed_job := OLD.job_id;
                      ELSE changed_job := NEW.job_id; END IF;
                  END IF;
                  UPDATE dashboard_revision
                      SET revision=revision+1,
                          global_revision=CASE WHEN scope='global' THEN revision+1 ELSE global_revision END
                      WHERE id=1 RETURNING revision INTO next_revision;
                  IF scope = 'runs' THEN
                      UPDATE dashboard_metadata_revision SET runs_revision=next_revision WHERE id=1;
                  ELSIF scope IN ('job', 'listing') THEN
                      INSERT INTO dashboard_job_revision VALUES(changed_job, next_revision)
                      ON CONFLICT(job_id) DO UPDATE SET revision=excluded.revision;
                      IF scope = 'listing' THEN
                          UPDATE dashboard_metadata_revision SET listings_revision=next_revision WHERE id=1;
                      END IF;
                  END IF;
                  RETURN NULL;
              END;
              $$''')
    scopes = [(table, 'global') for table in GLOBAL_TABLES] + [(table, 'job') for table in JOB_TABLES]
    for table, kind in scopes + [('jobs', 'listing'), ('runs', 'runs')]:
        c.execute(f'''CREATE OR REPLACE TRIGGER dashboard_change_{table}
                  AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW
                  EXECUTE FUNCTION jobs_update_dashboard_revision('{kind}')''')


def init_sqlite(c):
    for table in GLOBAL_TABLES + JOB_TABLES + ('jobs', 'runs'):
        if table == 'workspace_preferences':  # SQLite preferences live in a file.
            continue
        for operation, row in (('INSERT', 'NEW'), ('UPDATE', 'NEW'), ('DELETE', 'OLD')):
            when = ''
            name = f'dashboard_change_{table}_{operation.lower()}'
            if table == 'runs':
                c.execute(f'DROP TRIGGER IF EXISTS {name}')
                change = '''UPDATE dashboard_revision SET revision=revision+1 WHERE id=1;
                            UPDATE dashboard_metadata_revision SET runs_revision=
                                (SELECT revision FROM dashboard_revision WHERE id=1) WHERE id=1;'''
            elif table == 'jobs' and operation == 'UPDATE':
                c.execute(f'DROP TRIGGER IF EXISTS {name}')
                same_source = ' AND '.join(
                    f"json_extract(NEW.listing,'$.{field}') IS json_extract(OLD.listing,'$.{field}')"
                    for field in SOURCE_FIELDS
                )
                change = f'''UPDATE dashboard_revision SET revision=revision+1, global_revision=
                              CASE WHEN CASE WHEN json_valid(NEW.listing) AND json_valid(OLD.listing)
                                        THEN NEW.id=OLD.id AND {same_source} ELSE 0 END
                                   THEN global_revision ELSE revision+1 END
                              WHERE id=1;
                             INSERT INTO dashboard_job_revision
                             SELECT NEW.id,revision FROM dashboard_revision WHERE id=1 AND global_revision<>revision
                             ON CONFLICT(job_id) DO UPDATE SET revision=excluded.revision;
                             UPDATE dashboard_metadata_revision SET listings_revision=
                                 (SELECT revision FROM dashboard_revision WHERE id=1)
                                 WHERE id=1 AND EXISTS(SELECT 1 FROM dashboard_revision
                                                        WHERE id=1 AND global_revision<>revision);'''
            elif table in GLOBAL_TABLES or table == 'jobs' or (table == 'tracking' and operation != 'UPDATE'):
                change = 'UPDATE dashboard_revision SET revision=revision+1, global_revision=revision+1 WHERE id=1;'
                if table == 'recruiter_state' and operation == 'UPDATE':
                    when = "WHEN json_extract(NEW.value,'$.preferences') IS NOT json_extract(OLD.value,'$.preferences')"
            else:
                change = f'''UPDATE dashboard_revision SET revision=revision+1 WHERE id=1;
                             INSERT INTO dashboard_job_revision
                             VALUES({row}.job_id, (SELECT revision FROM dashboard_revision WHERE id=1))
                             ON CONFLICT(job_id) DO UPDATE SET revision=excluded.revision;'''
            c.execute(f'''CREATE TRIGGER IF NOT EXISTS {name}
                       AFTER {operation} ON {table} {when} BEGIN {change} END''')


def environment(a, stamp, *, running):
    # A restart or a change to external configuration invalidates an old cursor.
    parts = [INSTANCE, stamp.date().isoformat(), str(running)]
    files = [a.ROOT / 'secrets' / f'{name}.key' for name in ('openai', 'firecrawl')]
    files.append(a.ROOT / ('config.example.json' if a.postgres_enabled() else 'config.json'))
    if not a.postgres_enabled():
        files.append(a.DATA / 'preferences.json')
    for path in files:
        try:
            info = path.stat()
            parts.extend((str(info.st_ino), str(info.st_mtime_ns), str(info.st_size)))
        except FileNotFoundError:
            parts.append('-')
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:24]


def parse_cursor(token, key, stamp, revision, global_revision):
    parsed = CURSOR.fullmatch(token or '')
    if not parsed or parsed[1] != key:
        return None
    after, expiry = int(parsed[2]), int(parsed[3])
    if not global_revision <= after <= revision or (expiry and stamp.timestamp() * 1000 >= expiry):
        return None
    return after, expiry, None if parsed[4] is None else parsed[4] == '1'


def cursor(key, revision, expiry, *, running=None):
    token = f'{key}.{revision}.{expiry}'
    return token if running is None else f'{token}.{int(running)}'


def changed_jobs(c, after):
    return [row[0] for row in c.execute('''SELECT job_id FROM dashboard_job_revision WHERE revision > ?
                                       ORDER BY revision LIMIT ?''', (after, MAX_PATCH_JOBS + 1))]
