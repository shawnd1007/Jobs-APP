"""Employer openings pulled during recruiter discovery."""
import hashlib
import json
import re
from contextlib import nullcontext

PAGE_SIZE = 40
CURSOR = re.compile(r'([0-9]{1,19}):([0-9]{1,9}):([a-f0-9]{64})')
EMPLOYER_FIELDS = (
    'title', 'employer', 'location', 'url', 'description', 'workplace_type', 'remote',
    'availability', 'posted', 'source', 'requisition', 'salary_text', 'salary_min',
    'salary_max', 'salary_currency', 'salary_period', 'salary_type', 'posting_verified',
    'posting_check_failed', 'posting_check_attempted', 'posting_location_terms', 'location_conflict',
    'application_evidence', 'last_verified', 'recruitee_offer_id', 'recruitee_offer_changed',
)
MATCH_LISTINGS = '''SELECT o.id, o.listing, o.discovered_at, j.id AS saved_id, j.listing AS checked
                    FROM recruiter_openings o LEFT JOIN jobs j ON j.identity=o.identity'''


def init(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS recruiter_openings (
        id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL, listing TEXT NOT NULL,
        search_text TEXT NOT NULL, run_id BIGINT NOT NULL, rank INTEGER NOT NULL,
        discovered_at TEXT NOT NULL)''')
    connection.execute('''CREATE INDEX IF NOT EXISTS recruiter_openings_order
        ON recruiter_openings(run_id DESC, rank ASC, id ASC)''')


def opening_id(a, url):
    return hashlib.sha256(a.identity(url).encode()).hexdigest()


def capture(a, listings, run_id):
    if not listings:
        return 0
    now = a.now()
    with a.connect() as connection:
        connection.executemany('''INSERT INTO recruiter_openings
            (id, identity, listing, search_text, run_id, rank, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET listing=excluded.listing, search_text=excluded.search_text,
                run_id=excluded.run_id, rank=excluded.rank, discovered_at=excluded.discovered_at
            WHERE excluded.run_id >= recruiter_openings.run_id''', (
            (opening_id(a, job['url']), a.identity(job['url']),
             json.dumps({key: job[key] for key in EMPLOYER_FIELDS if key in job}),
             ' '.join(str(job.get(key) or '') for key in ('title', 'employer')).casefold(),
             run_id, rank, now)
            for rank, job in enumerate(listings)
        ))
    return len(listings)


def row_listing(row):
    return dict(json.loads(row['checked'] or row['listing']), id=row['id'])


def match_listing(row):
    return dict(row_listing(row), id=row['saved_id'] if row['saved_id'] is not None else row['id'],
                opening_id=row['id'], discovered_at=row['discovered_at'])


def for_run(a, run_id):
    with a.connect() as connection:
        return [match_listing(row) for row in connection.execute(
            MATCH_LISTINGS + ' WHERE o.run_id=? ORDER BY o.rank, o.id', (run_id,))]


def for_matches(a, opening_ids, *, connection=None):
    if not opening_ids:
        return {}
    listings = {}
    with (a.connect() if connection is None else nullcontext(connection)) as c:
        for start in range(0, len(opening_ids), 200):
            batch = opening_ids[start:start + 200]
            placeholders = ','.join('?' for _ in batch)
            for row in c.execute(MATCH_LISTINGS + f' WHERE o.id IN ({placeholders})', batch):
                listings[row['id']] = match_listing(row)
    return listings


def get(a, opening_id):
    with a.connect() as connection:
        row = connection.execute('''SELECT o.id, o.listing, j.listing AS checked
            FROM recruiter_openings o LEFT JOIN jobs j ON j.identity=o.identity WHERE o.id=?''',
                                 (opening_id,)).fetchone()
    return row_listing(row) if row else None


def page(a, cursor=None, query=''):
    query = ' '.join(query.split()).casefold()
    if len(query) > 120:
        raise ValueError('Search openings with 120 characters or fewer.')
    pattern = query.replace('!', '!!').replace('%', '!%').replace('_', '!_')
    filters = []
    values = []
    if query:
        filters.append("o.search_text LIKE ? ESCAPE '!'")
        values.append('%' + pattern + '%')
    if cursor is not None:
        parsed = CURSOR.fullmatch(cursor)
        if not parsed or int(parsed[1]) > 9223372036854775807:
            raise ValueError('Refresh Pulled Openings and try again.')
        run_id, rank, opening_id = int(parsed[1]), int(parsed[2]), parsed[3]
        filters.append('(o.run_id < ? OR (o.run_id = ? AND (o.rank > ? OR (o.rank = ? AND o.id > ?))))')
        values.extend((run_id, run_id, rank, rank, opening_id))
    where = ' WHERE ' + ' AND '.join(filters) if filters else ''
    with a.connect() as connection:
        rows = connection.execute('''SELECT o.id, o.listing, o.discovered_at, o.run_id, o.rank, j.listing AS checked
            FROM recruiter_openings o LEFT JOIN jobs j ON j.identity=o.identity''' + where +
            ' ORDER BY o.run_id DESC, o.rank ASC, o.id ASC LIMIT ?', (*values, PAGE_SIZE + 1)).fetchall()

    openings = []
    for row in rows[:PAGE_SIZE]:
        job = row_listing(row)
        openings.append(dict(id=row['id'], title=job.get('title') or 'Untitled opening',
                             employer=job.get('employer') or 'Employer unknown',
                             location=job.get('location') or '', work_arrangement=a.work_arrangement(job),
                             salary=job.get('salary_text') or 'Pay not disclosed', posting_url=job.get('url') or '',
                             discovered_at=row['discovered_at']))
    next_before = None
    if len(rows) > PAGE_SIZE:
        last = rows[PAGE_SIZE - 1]
        next_before = f"{last['run_id']}:{last['rank']}:{last['id']}"
    return dict(openings=openings, next_before=next_before)
