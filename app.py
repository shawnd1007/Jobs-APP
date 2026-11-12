"""Personal LAN jobs dashboard. Python standard library only; SQLite is authoritative."""
import datetime as dt
import hashlib
import html
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import socket
import sqlite3
import threading
import time
import unicodedata
import urllib.error
import urllib.parse as up
import urllib.request as ur
import xml.etree.ElementTree as ET
from uuid import uuid4
import prototype
from contextvars import ContextVar
from queue import Empty, Queue
import sys
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
SEED = ROOT / 'original.html'
DATA = Path(os.environ.get('JOBS_DATA', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'jobs.sqlite3'
STATUSES = ['Not Applied','Planning to Apply','Applied','Assessment Received','Interview Scheduled','Interview Completed','Offer Received','Rejected','Withdrawn','Position Closed','Needs Verification']
LOCK = threading.Lock()
SEARCH_ACTIVE = threading.Event()
SEARCH_DEADLINE = ContextVar('search_deadline', default=None)
BOARD_DEADLINE = ContextVar('board_deadline', default=None)
NETWORK_SLOTS = threading.BoundedSemaphore(3)
SEARCH_SECONDS = 240
BOARD_SECONDS = 35
REQUEST_SECONDS = 12
logging.basicConfig(filename=DATA / 'errors.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
def config(): return prototype.settings(json.loads((ROOT / 'config.json').read_text(encoding='utf-8-sig')), DATA)

def service(): return sys.modules[__name__]

def firecrawl_key():
    path=ROOT/'secrets'/'firecrawl.key'
    return path.read_text().strip() if path.exists() else ''
class Connection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()
def connect():
    c=sqlite3.connect(DB, timeout=30, factory=Connection); c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=WAL'); return c
def clean(s): return html.unescape(re.sub('<[^>]+>', ' ', s or '')).strip()

def posting_text(value):
    """Keep section and bullet boundaries from employer HTML."""
    markup = html.unescape(value or '')
    markup = re.sub(r'<!--.*?-->|<(script|style)\b[^>]*>.*?</\1\s*>', '', markup, flags=re.I | re.S)
    markup = re.sub(r'</?(?:h[1-6]|p|div|li|ul|ol|section|br)\b[^>]*>', '\n', markup, flags=re.I)
    return '\n'.join(line for raw in clean(markup).splitlines() if (line := ' '.join(raw.split())))

def norm(s): return re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
BOARD_HOSTS = {
    'boards.greenhouse.io': 'greenhouse', 'job-boards.greenhouse.io': 'greenhouse',
    'jobs.ashbyhq.com': 'ashby', 'jobs.lever.co': 'lever',
    'jobs.smartrecruiters.com': 'smartrecruiters', 'careers.smartrecruiters.com': 'smartrecruiters',
}
BOARD_PLATFORMS = frozenset(BOARD_HOSTS.values()) | {'personio'}
PERSONIO_SLUG = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')
PERSONIO_HOST = re.compile(r'([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.jobs\.personio\.(?:com|de)')

def identity(url):
    u=up.urlsplit(url); host=(u.hostname or '').lower(); path=u.path.rstrip('/'); parts=path.split('/')
    if (board := PERSONIO_HOST.fullmatch(host)) and (job := re.fullmatch(r'/job/([0-9]+)', path)):
        return f'personio:{board[1]}:{job[1]}'
    if host in ('boards.greenhouse.io','job-boards.greenhouse.io') and len(parts)>=4:
        return 'greenhouse:'+parts[1].lower()+':'+parts[3]
    if host=='jobs.ashbyhq.com' and len(parts)>=3: return 'ashby:'+parts[1].lower()+':'+parts[2]
    if host=='jobs.lever.co' and len(parts)>=3: return 'lever:'+parts[1].lower()+':'+parts[2]
    if BOARD_HOSTS.get(host) == 'smartrecruiters' and len(parts) >= 3:
        posting = re.match(r'^(\d+)(?:-|$)', parts[2])
        if posting:
            return f'smartrecruiters:{parts[1].lower()}:{posting[1]}'
    query=up.urlencode([(k,v) for k,v in up.parse_qsl(u.query) if k in ('gh_jid','jobId','requisitionId')])
    return up.urlunsplit(('https',host,path,query,''))

def stored_board_posting(ident):
    platform, _, rest = ident.partition(':')
    board, _, posting = rest.partition(':')
    if platform not in BOARD_PLATFORMS or not board or not posting:
        return None
    path = up.quote(board, safe='') + '/'
    posting_path = up.quote(posting, safe='')
    urls = {
        'greenhouse': f'https://job-boards.greenhouse.io/{path}jobs/{posting_path}',
        'ashby': f'https://jobs.ashbyhq.com/{path}{posting_path}/application',
        'lever': f'https://jobs.lever.co/{path}{posting_path}/apply',
        'smartrecruiters': f'https://jobs.smartrecruiters.com/{path}{posting_path}',
        'personio': f'https://{board}.jobs.personio.com/job/{posting_path}',
    }
    return urls[platform], posting

def safe_url(url):
    u=up.urlsplit(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password: raise ValueError('Only public HTTPS employer URLs allowed')
    if u.port not in (None,443): raise ValueError('Unexpected port')
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(u.hostname,443)): raise ValueError('Private address rejected')
    return url
class SafeRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl); return super().redirect_request(req,fp,code,msg,headers,newurl)
OPENER=ur.build_opener(SafeRedirect())

class NoRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

PERSONIO_OPENER = ur.build_opener(NoRedirect())

def network_call(operation, seconds=REQUEST_SECONDS):
    """Bound the whole network operation, including DNS, redirects and response reads."""
    search_deadline = SEARCH_DEADLINE.get()
    if search_deadline is None:
        return operation(seconds)
    deadline = min(search_deadline, BOARD_DEADLINE.get() or search_deadline)
    remaining = min(seconds, deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError('Search time limit reached')
    if not NETWORK_SLOTS.acquire(blocking=False):
        raise TimeoutError('Previous employer requests are still timing out')
    result = Queue(1)

    def read():
        try:
            result.put((True, operation(remaining)))
        except Exception as error:
            result.put((False, error))
        finally:
            NETWORK_SLOTS.release()

    try:
        threading.Thread(target=read, daemon=True).start()
    except Exception:
        NETWORK_SLOTS.release()
        raise
    try:
        ok, value = result.get(timeout=remaining)
    except Empty:
        raise TimeoutError(f'Employer request exceeded {remaining:.0f} seconds') from None
    if not ok:
        raise value
    return value


def read_response(request, *, opener=OPENER, max_bytes=3_000_000, seconds=REQUEST_SECONDS,
                  check_url=True):
    def read(timeout):
        if check_url:
            safe_url(request.full_url)
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError('Employer response exceeds the supported size')
            return raw, response.url
    return network_call(read, seconds)


def fetch(url, payload=None, key=None):
    headers={'User-Agent':'PersonalJobDashboard/1.0','Accept':'application/json'}
    if payload is not None: headers['Content-Type']='application/json'
    if key: headers['Authorization']='Bearer '+key
    request=ur.Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
    raw, _ = read_response(request, max_bytes=16_000_000)
    return json.loads(raw)

def init():
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, fallback TEXT, listing TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS jobs_fallback ON jobs(fallback);
        CREATE TABLE IF NOT EXISTS tracking(job_id INTEGER PRIMARY KEY REFERENCES jobs(id),status TEXT NOT NULL DEFAULT 'Needs Verification',application_date TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',follow_up TEXT NOT NULL DEFAULT '',updated TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,started TEXT NOT NULL,finished TEXT,state TEXT NOT NULL,report TEXT NOT NULL,trigger TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,job_id INTEGER,at TEXT NOT NULL,detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY,requests INTEGER NOT NULL DEFAULT 0,credits REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS job_interests(job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
            state TEXT NOT NULL, version INTEGER NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews(job_id INTEGER PRIMARY KEY REFERENCES jobs(id),decision TEXT NOT NULL DEFAULT 'Pending',note TEXT NOT NULL DEFAULT '',reviewer TEXT NOT NULL DEFAULT '',checks TEXT NOT NULL DEFAULT '{}',updated TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0);
        PRAGMA user_version=1;''')
        if 'reserved' not in [r[1] for r in c.execute('PRAGMA table_info(usage)')]:c.execute('ALTER TABLE usage ADD COLUMN reserved INTEGER NOT NULL DEFAULT 0')
        if 'trigger' not in [r[1] for r in c.execute('PRAGMA table_info(runs)')]:
            c.execute('ALTER TABLE runs ADD COLUMN trigger TEXT')
        c.execute('PRAGMA user_version=4')
        prototype.init(c)
        c.execute("UPDATE runs SET state='interrupted',finished=? WHERE state='running'",(now(),))
        if not c.execute('SELECT 1 FROM jobs LIMIT 1').fetchone():
            source=SEED.read_text(encoding='utf-8-sig')
            for a in re.findall(r'<article\b.*?</article>',source,re.S):
                def field(cls):
                    m=re.search(r'class="'+cls+r'"[^>]*>(.*?)</',a,re.S); return clean(m.group(1)) if m else ''
                title=clean(re.search(r'<h2>(.*?)</h2>',a,re.S)[1]); url=html.unescape(re.search(r'class="btn" href="([^"]+)',a)[1])
                location=clean(re.findall(r'<em>(.*?)</em>',a,re.S)[-1]); posted=re.search(r'Posted (\d{4}-\d\d-\d\d)',location)
                job={'employer':field('company'),'title':title,'url':url,'salary_text':field('salary'),'location':location,'description':field('why'),'explanation':field('why')+' '+field('note'),'score':int(re.search(r'data-fit="(\d)',a)[1])*20,'category':'Imported','posted':posted[1] if posted else '', 'availability':'Needs Verification','eligibility':'Review','last_verified':'','source':'Original HTML, November 5, 2026','history_confirmation':True}
                upsert(c,job)
        cfg = config()
        for row in c.execute('SELECT id,identity,listing FROM jobs').fetchall():
            j = json.loads(row['listing'])
            if j.get('external_application'):
                continue
            stored = stored_board_posting(row['identity'])
            if stored and identity(j['url']) != row['identity']:
                # Older versions could replace a posting by title and retain the prior ID.
                j.update(url=stored[0], requisition=stored[1], availability='Needs Verification',
                         queue='Review', last_verified='', salary_text='Salary not yet verified',
                         description='', posted='', application_evidence='Stored requisition requires a fresh employer check.')
                for field in ('salary_min','salary_max','salary_currency','salary_period','salary_type',
                              'compensation_details','application_verified','posting_verified'):
                    j.pop(field, None)
            eligible,reason,area=location_eligibility(j,cfg)
            j.update(location_eligibility=eligible,location_reason=reason,area=area)
            if eligible!='Eligible':j['queue']='Excluded' if eligible=='Rejected' else 'Location Review'
            c.execute('UPDATE jobs SET listing=? WHERE id=?',(json.dumps(j),row['id']))
def external_role_key(employer, title, location):
    return tuple(' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold()))
                 for value in (employer, title, location))


def external_link_key(url):
    """Normalize an owner link without fetching it or dropping requisition parameters."""
    if not url:
        return ''
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char == chr(92) for char in url):
        raise ValueError('Enter a valid HTTPS posting link.')
    parts = up.urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.port not in (None, 443)):
        raise ValueError('Enter a valid HTTPS posting link.')
    canonical = identity(url)
    if not canonical.startswith('https:'):
        return canonical
    params = [(key, value) for key, value in up.parse_qsl(parts.query, keep_blank_values=True)
              if not key.lower().startswith('utm_')]
    host = parts.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    return up.urlunsplit(('https', host, parts.path.rstrip('/'), up.urlencode(sorted(params, key=lambda pair: pair[0])), ''))


def add_external_application(payload):
    if not isinstance(payload, dict):
        raise ValueError('Enter the job title and employer.')

    def field(name, limit):
        value = payload.get(name, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('One or more fields exceed their allowed length.')
        return value.strip()

    title, employer, location = field('title', 200), field('employer', 200), field('location', 200)
    if not title or not employer:
        raise ValueError('Enter the job title and employer.')
    url = field('url', 2048)
    link_key = external_link_key(url)
    status = field('status', 40)
    if status not in STATUSES or status in UNAPPLIED:
        raise ValueError('Choose an application status.')
    dates = {name: field(name, 10) for name in ('application_date', 'follow_up')}
    for value in dates.values():
        if not value:
            continue
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
                raise ValueError
            dt.date.fromisoformat(value)
        except ValueError:
            raise ValueError('Enter valid application and follow-up dates.') from None
    notes = field('notes', 10000)

    # The transaction serializes duplicate detection with other writers and search results.
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        fallback = '|'.join(norm(value) for value in (employer, title, location))
        role_key = external_role_key(employer, title, location)
        for row in c.execute('SELECT listing FROM jobs'):
            old = json.loads(row['listing'])
            existing_url = old.get('url', '')
            if link_key and existing_url:
                try:
                    same_link = external_link_key(existing_url) == link_key
                except ValueError:
                    continue
                if same_link:
                    return 409, {'error': 'This posting is already in Jobs. Search for it to update application tracking.'}
                continue
            if external_role_key(old['employer'], old['title'], old.get('location', '')) == role_key:
                return 409, {'error': 'This role is already in Jobs. Search for it to update application tracking.'}
        stamp = now()
        listing = dict(title=title, employer=employer, location=location, url=url,
                       external_application=True, source='Added by you',
                       availability='Needs Verification', last_verified='',
                       application_evidence='Posting details entered by you.')
        job_id = c.execute('INSERT INTO jobs(identity,fallback,listing,created,updated) VALUES(?,?,?,?,?)',
                           ('external:' + uuid4().hex, fallback, json.dumps(listing), stamp, stamp)).lastrowid
        c.execute("""INSERT INTO tracking(job_id,status,application_date,follow_up,notes,updated)
                     VALUES(?,?,?,?,?,?)""",
                  (job_id, status, dates['application_date'], dates['follow_up'], notes, stamp))
        return 201, {'saved': True, 'job_id': job_id}


def upsert(c,j):
    if not c.in_transaction:
        c.execute('BEGIN IMMEDIATE')
    ident=identity(j['url']); fallback='|'.join(norm(str(j.get(k,''))) for k in ('employer','title','location'))
    row=c.execute('SELECT * FROM jobs WHERE identity=?',(ident,)).fetchone()
    if not row and ident.startswith('personio:'):
        _, tenant, requisition = ident.split(':')
        aliases = [f'https://{tenant}.jobs.personio.{suffix}/job/{requisition}' for suffix in ('com', 'de')]
        prior = c.execute('SELECT * FROM jobs WHERE identity IN (?,?)', aliases).fetchall()
        if len(prior) > 1:
            raise ValueError('Multiple retained Personio records match this requisition; manual review needed')
        row = prior[0] if prior else None
    if not row and j.get('source') not in (None, 'Original HTML, November 5, 2026'):
        try:
            link_key = external_link_key(j['url'])
        except ValueError:
            link_key = ''
        if link_key:
            for external in c.execute("SELECT * FROM jobs WHERE identity LIKE 'external:%'"):
                if external_link_key(json.loads(external['listing'])['url']) == link_key:
                    row = external
                    break
    if not row:
        alternatives = c.execute('SELECT * FROM jobs WHERE fallback=?', (fallback,)).fetchall()
        if len(alternatives) == 1:
            previous = alternatives[0]
            old = json.loads(previous['listing'])
            old_board = board_identity(old['url'])
            new_board = board_identity(j['url'])
            # Distinct recruiting-platform IDs represent distinct openings.
            if not old.get('external_application') and not (old_board and new_board) and not (old.get('requisition') and j.get('requisition')):
                row = previous
    stamp=now()
    if row:
        old=json.loads(row['listing'])
        promoted = old.get('external_application', False)
        if promoted:
            old = {}
        # A fresh employer response owns these facts, including their absence.
        for field in ('salary_min','salary_max','salary_currency','salary_period','salary_type','compensation_details','application_verified','posting_verified'):
            old.pop(field,None)
        old.update(j)
        canonical = ident if promoted or board_identity(j['url']) else row['identity']
        c.execute('UPDATE jobs SET identity=?,fallback=?,listing=?,updated=? WHERE id=?',
                  (canonical, fallback, json.dumps(old), stamp, row['id']))
        return row['id'],False
    cur=c.execute('INSERT INTO jobs(identity,fallback,listing,created,updated) VALUES(?,?,?,?,?)',(ident,fallback,json.dumps(j),stamp,stamp))
    c.execute('INSERT INTO tracking(job_id,updated) VALUES(?,?)',(cur.lastrowid,stamp))
    return cur.lastrowid,True
def records():
    with connect() as c:
        result=[]
        for row in c.execute("SELECT jobs.*,tracking.status,tracking.application_date,tracking.notes,tracking.follow_up,tracking.updated tracking_updated,tracking.version,COALESCE(reviews.decision,'Pending') review_decision,COALESCE(reviews.note,'') review_note,COALESCE(reviews.reviewer,'') review_reviewer,COALESCE(reviews.checks,'{}') review_checks,COALESCE(reviews.updated,'') review_updated,COALESCE(reviews.version,0) review_version FROM jobs JOIN tracking ON jobs.id=tracking.job_id LEFT JOIN reviews ON reviews.job_id=jobs.id"):
            d=dict(row);d['review_checks']=json.loads(d['review_checks']);j=json.loads(d.pop('listing')); j.update(d); result.append(j)
        return result

UNAPPLIED={'Needs Verification','Not Applied','Planning to Apply'}
def review_blockers(j, cfg=None):
    cfg=config() if cfg is None else cfg;geo=location_eligibility(j,cfg)[0];problems=[]
    if geo=='Rejected':problems.append('Location is outside your saved preferences.')
    salary=base_salary(j)
    if salary is not None and salary<cfg['salary_floor']:problems.append('Published maximum base salary is below your minimum.')
    if j.get('availability')=='Closed':problems.append('Employer listing is closed.')
    if j.get('status') not in UNAPPLIED:problems.append('This job is already in application history; update application tracking instead.')
    return problems

def save_review(job_id,d):
    decision=d.get('decision');checks=d.get('checks',{});note=str(d.get('note',''))[:6000];reviewer=str(d.get('reviewer',''))[:120]
    if decision not in ('Pending','Approved','Hold','Dismissed') or not isinstance(checks,dict):return 400,{'error':'Invalid review decision'}
    checks={key:checks.get(key) is True for key in ('location','salary','application','history')}
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT jobs.listing,tracking.status,tracking.version FROM jobs JOIN tracking ON jobs.id=tracking.job_id WHERE jobs.id=?',(job_id,)).fetchone()
        if not row:return 404,{'error':'Job not found'}
        old=c.execute('SELECT version FROM reviews WHERE job_id=?',(job_id,)).fetchone()
        expected=old['version'] if old else 0
        if d.get('version')!=expected:return 409,{'error':'Another device changed this review. Refresh before making a decision.'}
        j=json.loads(row['listing']);j['status']=row['status']
        if j.get('external_application'):
            return 400, {'error': 'Use application tracking for jobs you add yourself.'}
        if decision=='Approved':
            if d.get('tracking_version')!=row['version']:return 409,{'error':'Application tracking changed. Refresh before approving.'}
            blockers=review_blockers(j)
            if blockers:return 400,{'error':' '.join(blockers)}
            if not all(checks.values()):return 400,{'error':'Check location, base salary, employer application availability, and prior application history before approving.'}
            if (j.get('queue')!='Confirmed' or location_eligibility(j,config())[0]!='Eligible') and not note.strip():return 400,{'error':'Add a review note explaining what you checked, including any previously missing pay, location or application information.'}
        stamp=now()
        c.execute('INSERT INTO reviews(job_id,decision,note,reviewer,checks,updated,version) VALUES(?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET decision=excluded.decision,note=excluded.note,reviewer=excluded.reviewer,checks=excluded.checks,updated=excluded.updated,version=excluded.version',(job_id,decision,note,reviewer,json.dumps(checks),stamp,expected+1))
        if decision=='Approved' and row['status']=='Needs Verification':
            c.execute("UPDATE tracking SET status='Not Applied',updated=?,version=version+1 WHERE job_id=?",(stamp,job_id))
        c.execute('INSERT INTO events(job_id,at,detail) VALUES(?,?,?)',(job_id,stamp,json.dumps({'type':'human_review','decision':decision,'reviewer':reviewer,'checks':checks,'note':note})))
    return 200,{'saved':True,'decision':decision}
def base_salary(j):
    # Only explicit structured annual USD base amounts count as salary qualified.
    return j.get('salary_max') if j.get('salary_currency')=='USD' and j.get('salary_period')=='year' and j.get('salary_type')=='base' else None

def salary_qualifies(j,cfg):
    salary=base_salary(j)
    if cfg.get('salary_policy')=='minimum':salary=j.get('salary_min') if salary is not None else None
    return salary is not None and salary>=cfg['salary_floor']
def preferred_location(loc, desc, remote, hybrid, cfg):
    targets = cfg.get('target_locations', [])
    modes = cfg.get('workplace_types', [])
    mode = 'hybrid' if hybrid else 'remote' if remote else 'onsite'
    area = {'hybrid': 'Hybrid', 'remote': 'Remote', 'onsite': 'On-site'}[mode]
    if not loc:
        return 'Review', 'Employer location is missing', area
    if modes and mode not in modes:
        if mode == 'onsite':
            return 'Review', 'Confirm whether the employer offers your preferred work arrangement', area
        return 'Rejected', 'Work arrangement is outside your preferences', area
    if remote and not hybrid and ('(' in loc or re.search(
            r'(?:must (?:reside|live|be based|be located)|only in|restricted to|'
            r'exclud(?:es|ing)|except for|(?:hiring|eligible|approved) states)', loc + ' ' + desc)):
        return 'Review', 'Check the employer’s remote residence restrictions', area
    def location_words(value):
        value = re.sub(r'\bu\.s\.(?:a\.)?', 'us', value.lower())
        value = re.sub(r'\b(?:united states|usa)\b', 'us', value)
        return ' '.join(re.findall(r'[^\W_]+', value))
    published = ' ' + location_words(loc) + ' '
    for target in targets:
        phrase = location_words(target)
        if phrase and phrase != 'remote' and f' {phrase} ' in published:
            return 'Eligible', f'Published location matches {target}', area
    if mode == 'remote':
        return 'Review', 'Confirm where the employer can hire remote workers', area
    if targets:
        return 'Rejected', 'Published office location is outside your preferences', area
    return 'Review', 'Add a location or verify the employer’s office location', area

def location_eligibility(j,cfg):
    loc=clean(j.get('location','')).lower()
    loc=re.sub(r'\bu\.s\.(?:a\.)?', 'us',loc)
    desc=clean(j.get('description','')).lower()
    remote=bool(j.get('remote')) or bool(re.search(r'\bremote\b',loc))
    hybrid=bool(re.search(r'\bhybrid\b',loc)) or bool(re.search(r'(?:position|role|work arrangement|schedule) (?:is|will be) hybrid|(?:required|must|expected)(?: to)? (?:work|be|attend|report).{0,60}(?:office|on.site)|(?:office|on.site).{0,40}\b[1-5a-z]+ days? (?:per|a|each) week',desc))
    if cfg.get('target_locations') or cfg.get('workplace_types'):
        return preferred_location(loc, desc, remote, hybrid, cfg)
    fl=bool(re.search(r'\b(florida|fl)\b',loc));ga=bool(re.search(r'\b(georgia|ga)\b',loc))
    us=bool(re.search(r'\b(united states|usa|us)\b',loc))
    states='alabama alaska arizona arkansas california colorado connecticut delaware hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota mississippi missouri montana nebraska nevada new hampshire new jersey new mexico new york north carolina north dakota ohio oklahoma oregon pennsylvania rhode island south carolina south dakota tennessee texas utah vermont virginia washington west virginia wisconsin wyoming'
    state_names=['alabama','alaska','arizona','arkansas','california','colorado','connecticut','delaware','hawaii','idaho','illinois','indiana','iowa','kansas','kentucky','louisiana','maine','maryland','massachusetts','michigan','minnesota','mississippi','missouri','montana','nebraska','nevada','new hampshire','new jersey','new mexico','new york','north carolina','north dakota','ohio','oklahoma','oregon','pennsylvania','rhode island','south carolina','south dakota','tennessee','texas','utah','vermont','virginia','washington','west virginia','wisconsin','wyoming']
    abbreviations='al ak az ar ca co ct de hi id il in ia ks ky la me md ma mi mn ms mo mt ne nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy'.split()
    restricted_state=any(re.search(r'\b'+s+r'\b',loc) for s in state_names) or bool(re.search(r'(?:,|remote\s*[-:/]?)\s*(?:'+ '|'.join(abbreviations)+r')\b',loc))
    if remote and not hybrid:
        for sentence in re.split(r'[\n.!?;]',desc):
            if re.search(r'(?:cannot|not|unable to|do not).{0,25}(?:hire|employ|accept).{0,70}\b(?:florida|georgia)\b|\b(?:excluding|except|excludes)\s+(?:florida|georgia)\b',sentence):
                return 'Rejected','Remote excludes Florida or Georgia','Other'
            if re.search(r'(?:must (?:reside|live|be based|be located)|residency (?:is )?required|(?:hiring|eligible|approved) states(?: are|:)|remote.{0,15}(?:only in|restricted to))',sentence):
                if not re.search(r'\b(florida|georgia|fl|ga|anywhere in the (?:us|united states))\b',sentence):
                    return 'Review','Residence restriction requires Florida/Georgia confirmation','Other'
        general_remote_alternative=bool(re.search(r'(?:or|;)\s*remote\s*[,/-]?\s*(?:usa|us|united states)\b',loc))
        if (fl or ga) or (us and (not restricted_state or general_remote_alternative)):
            return 'Eligible','Fully remote; employer location includes Florida/Georgia or the US','Remote'
        if loc and loc not in ('remote','fully remote'):
            return 'Rejected','Remote location is outside Florida/Georgia or is state-restricted','Other'
        return 'Review','Remote country/state eligibility is not published clearly','Other'
    areas=cfg.get('local_areas',{})
    for area,rule in areas.items():
        if re.search(r'\b(?:'+ '|'.join(re.escape(c.lower()) for c in rule['cities'])+r')\b',loc):
            if re.search(r'\b(?:'+ '|'.join(rule['states'])+r')\b',loc):
                return 'Eligible','Local office is in the approved '+area+' area',area
            return 'Review','Local city found; state needs confirmation','Other'
    if remote and hybrid:return 'Review','Hybrid or office attendance requirement: confirm the office is in an approved local area','Other'
    return 'Rejected' if loc else 'Review','Office location is outside Jacksonville or the Buford area' if loc else 'Office location missing','Other'
def discovery_locations(cfg):
    if cfg.get('target_locations') or cfg.get('workplace_types'):
        return ('Eligible', 'Review')
    return ('Eligible',)

def profile_candidate(job, cfg, report):
    role_match = job['category'] != 'Other / Review'
    location_match = job['location_eligibility'] in discovery_locations(cfg)
    if role_match and not location_match:
        report['skipped_location'] = report.get('skipped_location', 0) + 1
    return ((role_match or job['matched_duty_count'] >= 2) and location_match
            and job['queue'] != 'Excluded' and job['availability'] != 'Closed')


RESPONSIBILITY_HEADINGS = frozenset({
    'responsibilities', 'responsibilities include', 'key responsibilities', 'your responsibilities',
    'duties', 'key duties', 'what you will do', 'what you ll do', 'what you do',
    'what you will be doing', 'what you ll be doing', 'your impact',
})
NON_DUTY_HEADINGS = frozenset({
    'qualifications', 'required qualifications', 'minimum qualifications', 'basic qualifications',
    'preferred qualifications', 'requirements', 'job requirements', 'skills and experience',
    'what you bring', 'what you will bring', 'what you ll bring', 'who you are', 'nice to have',
    'what we are looking for', 'what we re looking for', 'who we are looking for',
    'about us', 'about the company', 'company description', 'additional information',
    'benefits', 'compensation', 'what we offer', 'equal opportunity',
})
DUTY_ACTION = re.compile(
    r'^(?:(?:you (?:will|would)|this role will)\s+)?'
    r'(?:analy[sz]e|audit|build|coordinate|create|design|develop|document|handle|implement|'
    r'investigate|lead|maintain|manage|monitor|own|prepare|process|reconcile|report|resolve|'
    r'review|support|track|train|troubleshoot|validate|verify)\b', re.I
)

def employer_duties(description):
    duties_section = False
    excluded_section = False
    for raw in re.split(r'[\r\n•]+', description):
        line = re.sub(r'^(?:[-–*]+|\d+[.)])\s*', '', raw.strip())
        heading, colon, tail = line.partition(':')
        label = norm(heading)
        if label in RESPONSIBILITY_HEADINGS or label in NON_DUTY_HEADINGS:
            duties_section = label in RESPONSIBILITY_HEADINGS
            excluded_section = not duties_section
            line = tail.strip() if colon else ''
        if excluded_section:
            continue
        for duty in re.split(r'(?<=[.!?;])\s+', line):
            if not duty or re.search(
                r'\b(?:required|qualifications|years of experience|proficien(?:cy|t)|preferred|'
                r'experience (?:in|with|using)|you (?:have|bring)|no (?:experience|knowledge)|'
                r'without (?:using|requiring)|instead of|(?:do|does) not (?:use|require))\b', duty, re.I
            ):
                continue
            if DUTY_ACTION.match(duty) or (duties_section and re.match(r'^[A-Za-z]+ing\b', duty)):
                yield ' '.join(duty.split())

PROFILE_ACTION = re.compile(
    r'^(?:I\s+)?(?:analy[sz]ed|audited|automated|built|coordinated|created|designed|developed|'
    r'documented|handled|implemented|investigated|led|maintained|managed|monitored|owned|'
    r'prepared|processed|reconciled|reported|resolved|reviewed|supported|tracked|trained|'
    r'troubleshot|used|validated|verified|worked\s+with)\b', re.I
)
PROFILE_UNCERTAINTY = re.compile(
    r"\b(?:learning|want(?:ed)? to|plan(?:ned)? to|hope(?:d)? to|interested in|"
    r"seeking|aim(?:ed)? to|never|not|without|no|lack(?:ed|ing)?|"
    r"new to|to learn|could|would|haven[’']t|hadn[’']t|didn[’']t)\b", re.I
)


def skill_pattern(skill):
    return re.compile(r'(?<![\w+#])' + re.escape(skill) + r'(?![\w+#])', re.I)


def profile_skill_examples(profile, skills):
    """Use only intact profile excerpts that describe affirmative work."""
    examples = {}
    patterns = {skill: skill_pattern(skill) for skill in skills if skill}
    for clause in re.split(r'[\r\n;•]+|(?<=[.!?])\s+', clean(profile)):
        line = ' '.join(re.sub(r'^(?:[-–*]+|\d+[.)])\s*', '', clause.strip()).split())
        if not 0 < len(line) <= 320 or not PROFILE_ACTION.match(line) or PROFILE_UNCERTAINTY.search(line):
            continue
        for skill, pattern in patterns.items():
            if skill not in examples and pattern.search(line):
                examples[skill] = line
    return examples


def experience_evidence(description, profile, skills, examples=None):
    """Quote employer duties that use selected skills supported by a profile excerpt."""
    examples = profile_skill_examples(profile, skills) if examples is None else examples
    supported = {skill: skill_pattern(skill) for skill in examples}
    if not supported:
        return []
    evidence = {}
    for duty in dict.fromkeys(employer_duties(description)):
        for skill, pattern in supported.items():
            if len(duty) <= 320 and pattern.search(duty):
                evidence.setdefault(skill, []).append(duty)

    # Give each skill one quote and prefer a different duty when several skills overlap.
    used = set()
    matches = []
    for skill, duties in sorted(evidence.items(), key=lambda item: len(item[1]))[:8]:
        duty = next((candidate for candidate in duties if norm(candidate) not in used), duties[0])
        used.add(norm(duty))
        matches.append({'skill': skill, 'duty': duty})
    return matches

def qualification_checks(description):
    description = description.casefold()
    checks = []
    if re.search(r'\b(?:bachelor|master|doctoral|doctorate|degree)\b', description):
        equivalent = re.search(r'\b(?:equivalent (?:work |professional )?experience|experience in lieu of)\b', description)
        checks.append('Posting mentions a degree and equivalent experience.' if equivalent
                      else 'Check the degree requirement and whether equivalent experience is accepted.')
    if re.search(r'\b(?:certification|licensure|license|clearance) (?:is )?required\b', description):
        checks.append('Check the employer’s required certification, license or clearance.')
    if re.search(r'\b\d+\+?\s*(?:years|yrs) of (?:professional |relevant )?experience\b', description):
        checks.append('Compare your experience with the employer’s stated years requirement.')
    return checks

def assess(j,cfg):
    title=j.get('title','').lower(); desc=clean(j.get('description','')); text=(title+' '+desc).lower()
    eligible,location_reason,area=location_eligibility(j,cfg)
    j.update(location_eligibility=eligible,location_reason=location_reason,area=area)
    if base_salary(j) is None:
        ranges=re.findall(r'(?:annual\s+(?:base\s+)?salary|base\s+(?:salary|pay))[^$\n]{0,65}\$([\d,]+)\s*(?:-|–|to)\s*\$([\d,]+)',desc,re.I)
        if len(ranges)==1 and re.search(r'annual|per year|yearly',desc,re.I) and not re.search(r'(tier [123]|geographic.*(?:range|band)|per hour|hourly|\bCAD\b|Canadian dollars)',desc,re.I):
            lo,hi=[int(v.replace(',','')) for v in ranges[0]]
            if 30000<=lo<=hi<=500000:j.update(salary_min=lo,salary_max=hi,salary_currency='USD',salary_period='year',salary_type='base',salary_text=f'${lo:,} – ${hi:,} annual base (employer description)')
    salary=base_salary(j)
    # Match complete terms while allowing common punctuation between words.
    def words(value):
        return " " + " ".join(re.findall(r"\w+|[+#]+", value.casefold())) + " "

    title_words = words(title)
    posting_words = words(title + " " + desc)
    category = next((term for term in cfg['categories']
                     if term.strip() and words(term) in title_words), 'Other / Review')
    relevant = category != 'Other / Review'
    selected = dict.fromkeys(skill.strip().lower() for skill in cfg.get('preferred_skills', [])
                             if skill.strip())
    # Keep literal skill boundaries so C, C++, and C# remain distinct.
    matched_skills = [skill for skill in selected
                      if skill in text and re.search(r'(?<![\w+#])' + re.escape(skill) + r'(?![\w+#])', text)]
    matched_groups = [group for group in cfg.get('skill_groups', [])
                      if any(term.strip() and words(term) in posting_words for term in group['terms'])]
    breakdown = {
        'target_role': 45 if relevant else 0,
        'selected_skills': min(30, len(matched_skills) * 8),
        'skill_groups': min(25, sum(group['points'] for group in matched_groups)),
    }
    score = sum(breakdown.values())
    reasons = [f"Target role: {category}"] if relevant else []
    if matched_skills:
        reasons.append("Selected skills: " + ", ".join(matched_skills))
    reasons.extend(group['label'] for group in matched_groups)
    evidence = experience_evidence(desc, cfg.get('profile', ''), matched_skills)
    matched_duty_count = len({norm(item['duty']) for item in evidence})
    gaps = qualification_checks(desc) if desc.strip() else [
        'Employer description missing. Review the posting for duties and requirements.'
    ]
    j.update(
        category=category, score=score, eligibility=eligible, score_breakdown=breakdown,
        matched_skills=matched_skills, matched_groups=[group['label'] for group in matched_groups],
        match_gaps=gaps, duty_evidence=evidence, matched_duty_count=matched_duty_count,
        explanation=(
            f"Profile fit {score}/100. Target role {breakdown['target_role']}/45, "
            f"selected skills {breakdown['selected_skills']}/30, "
            f"skill groups {breakdown['skill_groups']}/25. "
            + (". ".join(reasons) + "." if reasons else "No configured role or skills found in the posting.")
            + " Review duties and requirements in the employer posting."
        ),
    )
    j['queue']='Confirmed' if j.get('availability')=='Open' and eligible=='Eligible' and salary_qualifies(j,cfg) and relevant and j['score']>=55 else 'Review'
    if any(term.lower() in title for term in cfg.get('excluded_title_terms',[])):j['queue']='Excluded';j['eligibility']='Excluded title preference'
    if salary is not None and salary<cfg['salary_floor']: j['queue']='Excluded';j['eligibility']='Salary below minimum'
    if eligible!='Eligible' and j['queue']!='Excluded':j['queue']='Excluded' if eligible=='Rejected' else 'Location Review'
    return j
def board_jobs(platform,board):
    if platform=='greenhouse':
        data=fetch('https://boards-api.greenhouse.io/v1/boards/'+up.quote(board,safe='')+'/jobs?content=true')
        if not isinstance(data.get('jobs'), list): raise ValueError('Invalid Greenhouse feed')
        out=[]
        for x in data['jobs']:
            out.append({'title':x['title'],'employer':board,'url':x['absolute_url'],'location':x.get('location',{}).get('name',''),'description':posting_text(x.get('content')),'posted':x.get('updated_at',''),'remote': 'remote' in x.get('location',{}).get('name','').lower(),'availability':'Open','last_verified':now(),'source':'Greenhouse public live board','requisition':str(x['id']),'application_evidence':'Listed in employer live board with absolute application URL','salary_text':'Salary not yet verified'})
        return out
    if platform=='ashby':
        data=fetch('https://api.ashbyhq.com/posting-api/job-board/'+up.quote(board,safe='')+'?includeCompensation=true');out=[]
        if not isinstance(data.get('jobs'), list): raise ValueError('Invalid Ashby feed')
        for x in data['jobs']:
            if x.get('isListed') is False: continue
            j={'title':x['title'],'employer':board,'url':x.get('applyUrl') or x['jobUrl'],'location':x.get('location',''),'description':x.get('descriptionPlain',''),'posted':x.get('publishedAt',''),'remote':x.get('isRemote',False),'availability':'Open','last_verified':now(),'source':'Ashby public live board','requisition':x['id'],'application_evidence':'Listed employer job and application URL','salary_text':'Salary Not Published'}
            comp=x.get('compensation') or {}; tiers=comp.get('compensationTiers') or []
            components=[z for tier in tiers for z in tier.get('components',[]) if z.get('compensationType')=='Salary' and z.get('currencyCode')=='USD' and z.get('interval')=='1 YEAR']
            if len(components)==1:
                z=components[0]; j.update(salary_min=z.get('minValue'),salary_max=z.get('maxValue'),salary_currency='USD',salary_period='year',salary_type='base',salary_text=(comp.get('scrapeableCompensationSalarySummary') or str(z))+' annual USD base',compensation_details=comp.get('compensationTierSummary',''))
            elif comp: j['salary_text']=comp.get('scrapeableCompensationSalarySummary') or 'Compensation published; requires tier/base review'
            out.append(j)
        return out
    if platform=='lever':
        data=fetch('https://api.lever.co/v0/postings/'+up.quote(board,safe='')+'?mode=json');out=[]
        for x in data:
            loc=x.get('categories',{}).get('location',''); salary=x.get('salaryRange') or {}
            sections = [x.get('descriptionPlain') or '']
            for section in x.get('lists', []):
                sections.extend([posting_text(section.get('text')), posting_text(section.get('content'))])
            if x.get('additionalPlain'):
                sections.extend(['Additional information', x['additionalPlain']])
            j={'title':x['text'],'employer':board,'url':x['applyUrl'],'location':loc,'description':'\n'.join(filter(None, sections)),'posted':dt.datetime.fromtimestamp(x['createdAt']/1000,dt.timezone.utc).isoformat() if x.get('createdAt') else '', 'remote':x.get('workplaceType')=='remote','availability':'Open','last_verified':now(),'source':'Lever public live board','requisition':x['id'],'application_evidence':'Employer live posting and applyUrl','salary_text':x.get('salaryDescriptionPlain') or 'Salary Not Published'}
            if salary.get('currency')=='USD' and salary.get('interval')=='per-year':j.update(salary_min=salary.get('min'),salary_max=salary.get('max'),salary_currency='USD',salary_period='year',salary_type='base')
            out.append(j)
        return out
    if platform == 'smartrecruiters':
        return smartrecruiters_board(board)
    if platform == 'personio':
        return personio_board(board)
    raise ValueError('Unsupported board')

def personio_board(board):
    if not PERSONIO_SLUG.fullmatch(board):
        raise ValueError('Invalid Personio career-site slug')
    base = f'https://{board}.jobs.personio.com'
    request = ur.Request(base + '/xml?language=en', headers={'User-Agent': 'PersonalJobDashboard/1.0'})
    try:
        raw, final = read_response(request, opener=PERSONIO_OPENER, max_bytes=4_000_000)
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            raise ValueError('Personio feed redirected; use the employer career-site slug') from error
        raise
    if final != request.full_url:
        raise ValueError('Personio feed redirected; use the employer career-site slug')
    return personio_positions(board, raw)

def personio_positions(board, data):
    if len(data) > 4_000_000:
        raise ValueError('Personio feed exceeds the supported size')
    xml = data.decode('utf-8-sig')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', xml, re.I):
        raise ValueError('Unexpected declarations in Personio feed')
    root = ET.fromstring(xml)
    if root.tag != 'workzag-jobs' or len(root) > 2000 or any(node.tag != 'position' for node in root):
        raise ValueError('Unexpected Personio feed structure')

    jobs = []
    seen = set()
    for position in root:
        requisition = position.findtext('id', '').strip()
        title = position.findtext('name', '').strip()
        if not re.fullmatch(r'[1-9][0-9]{0,19}', requisition) or not title or requisition in seen:
            raise ValueError('Missing or duplicate Personio position identity')
        seen.add(requisition)
        sections = []
        for section in position.findall('./jobDescriptions/jobDescription'):
            heading = posting_text(section.findtext('name'))
            body = posting_text(section.findtext('value'))
            if body:
                sections.extend(filter(None, (heading, body)))
        office = position.findtext('office', '').strip()
        jobs.append(dict(
            title=title, employer=position.findtext('subcompany', '').strip() or board,
            url=f'https://{board}.jobs.personio.com/job/{requisition}', requisition=requisition, location=office,
            remote=bool(re.search(r'\bremote\b', office, re.I)), description='\n'.join(sections),
            posted=position.findtext('createdAt', '').strip(), availability='Open', last_verified=now(),
            source='Personio public employer feed', application_evidence='Published in the employer XML feed',
            salary_text='Salary Not Published',
        ))
    return jobs

def rotating_postings(listings, run_id, limit):
    if len(listings) <= limit:
        return listings
    ordered = sorted(listings, key=lambda job: (job['posted'], job['requisition']), reverse=True)
    offset = (run_id - 1) * limit % len(ordered)
    return (ordered[offset:] + ordered[:offset])[:limit]

def smartrecruiters_board(board):
    endpoint = 'https://api.smartrecruiters.com/v1/companies/' + up.quote(board, safe='') + '/postings'
    listings = []
    seen = set()
    for offset in range(0, 3000, 100):
        page = fetch(f'{endpoint}?destination=PUBLIC&limit=100&offset={offset}')
        total = page.get('totalFound')
        entries = page.get('content')
        if type(total) is not int or total < 0 or not isinstance(entries, list):
            raise ValueError('Invalid SmartRecruiters pagination response')
        if len(entries) != min(100, max(0, total - offset)):
            raise ValueError('Incomplete SmartRecruiters board response')
        for item in entries:
            posting = str(item.get('id', ''))
            if not posting.isascii() or not posting.isdigit() or posting in seen:
                raise ValueError('Invalid or repeated SmartRecruiters posting ID')
            seen.add(posting)
            listings.append(smartrecruiters_listing(board, item, f'{endpoint}/{posting}'))
        if len(listings) == total:
            return listings
    raise ValueError('SmartRecruiters board exceeds the safe pagination limit')

def smartrecruiters_listing(board, item, detail_url=None):
    posting = str(item['id'])
    location = item.get('location') or {}
    country = location.get('country') or ''
    if country.lower() == 'us':
        country = 'United States'
    parts = {}
    for part in (location.get('city'), location.get('region'), country):
        if part:
            parts.setdefault(part.casefold(), part)
    address = ', '.join(parts.values())
    if location.get('hybrid'):
        address = 'Hybrid · ' + address
    sections = (item.get('jobAd') or {}).get('sections') or {}
    text = posting_text((sections.get('jobDescription') or {}).get('text'))
    for field, heading in (('qualifications', 'Qualifications'), ('additionalInformation', 'Additional information')):
        section_text = posting_text((sections.get(field) or {}).get('text'))
        if section_text:
            text = '\n'.join(filter(None, (text, heading, section_text)))
    fallback_url = f'https://jobs.smartrecruiters.com/{board}/{posting}'
    link = item.get('applyUrl') or item.get('postingUrl') or fallback_url
    if identity(link) != identity(fallback_url):
        raise ValueError('SmartRecruiters application URL does not match its posting ID')
    result = {
        'title': item['name'], 'employer': (item.get('company') or {}).get('name') or board,
        'location': address, 'remote': location.get('remote') is True,
        'description': text, 'posted': item.get('releasedDate') or '',
        'url': link, 'requisition': posting,
        'availability': 'Closed' if item.get('active') is False else 'Open',
        'last_verified': now(), 'source': 'SmartRecruiters public employer board',
        'application_evidence': 'Employer posting returned by the public Posting API',
        'salary_text': 'Salary Not Published',
    }
    if detail_url:
        result['detail_url'] = detail_url
    return result

def hydrate_board_listing(board, listing):
    endpoint = listing.get('detail_url')
    if not endpoint:
        return listing
    detail = fetch(endpoint)
    if str(detail.get('id')) != listing['requisition']:
        raise ValueError('SmartRecruiters detail does not match its posting ID')
    return smartrecruiters_listing(board, {
        'name': listing['title'], 'releasedDate': listing['posted'], **detail,
    })

def board_identity(url):
    u=up.urlsplit(url);parts=u.path.strip('/').split('/')
    if board := PERSONIO_HOST.fullmatch((u.hostname or '').lower()):
        return 'personio', board[1]
    platform = BOARD_HOSTS.get((u.hostname or '').lower())
    return (platform,parts[0].lower()) if platform and parts[0] else None
POSTING_PATHS = {
    'greenhouse': r'/[^/]+/jobs/[0-9]+',
    'ashby': r'/[^/]+/[^/]+(?:/application)?',
    'lever': r'/[^/]+/[^/]+(?:/apply)?',
    'smartrecruiters': r'/[^/]+/[0-9]+(?:-[^/]+)?',
    'personio': r'/job/[0-9]+',
}


def posting_reference(url):
    """An ATS requisition or an exact employer page with its meaningful query intact."""
    reference = external_link_key(url)
    board = board_identity(url)
    if board and (reference.startswith('https:') or
                  not re.fullmatch(POSTING_PATHS[board[0]], up.urlsplit(url).path.rstrip('/'))):
        raise ValueError('The employer URL does not identify a single requisition')
    if not reference:
        raise ValueError('The employer posting URL is missing')
    return reference


class PostingRedirect(SafeRedirect):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if posting_reference(req.full_url) != posting_reference(newurl):
            raise ValueError('Posting redirected away from the requisition')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


POSTING_OPENER = ur.build_opener(PostingRedirect())


class PostingUnavailable(ValueError):
    pass


def heading_matches_title(heading, title):
    heading = clean(heading)
    candidates = [heading]
    # Providers wrap browser titles with the employer name or an application prefix.
    application = re.fullmatch(r'(?:Job application|Apply) for (.+) at .+', heading, flags=re.I)
    if application:
        candidates.append(application[1])
    for separator in (' - ', ' — ', ' | ', ' @ '):
        if separator in heading:
            candidates.extend((heading.split(separator, 1)[1], heading.rsplit(separator, 1)[0]))
    return any(external_role_key(value, '', '')[0] == title for value in candidates)


def checked_posting_html(job, raw, final):
    if posting_reference(final) != posting_reference(job['url']):
        raise ValueError('Posting redirected away from the requisition')
    page = re.sub(r'<!--.*?-->|<(script|style)\b[^>]*>.*?</\1\s*>', '', raw, flags=re.I | re.S)
    visible_text = ' '.join(clean(page).split()).lower()
    closed = (
        r'\bno longer accepting (?:new )?applications\b'
        r'|\b(?:job|position|posting|vacancy) (?:has been filled|has closed|is closed|is expired|is no longer available)\b'
        r'|\b(?:job|position|posting) not found\b'
    )
    if re.search(closed, visible_text):
        raise PostingUnavailable('Application page says unavailable')
    title = external_role_key(job['title'], '', '')[0]
    headings = re.findall(r'<(title|h1)\b[^>]*>(.*?)</\1\s*>', page, flags=re.I | re.S)
    if not title or not any(heading_matches_title(heading, title) for _, heading in headings):
        raise ValueError('Employer page title does not match the posting')
    return page


def application_form_visible(job, raw, final):
    page = checked_posting_html(job, raw, final)
    for form in re.findall(r'<form\b[^>]*>.*?</form\s*>', page, flags=re.I | re.S):
        controls = html.unescape(form).lower()
        form_text = ' '.join(clean(form).split()).lower()
        if re.search(r'<(?:button|input)\b', controls) and re.search(
            r'\b(?:submit (?:your )?application|apply for this job|send (?:your )?application)\b',
            form_text + ' ' + controls,
        ):
            return True
        if re.search(r'<(?:input|select|textarea)\b', controls) and re.search(
            r'\b(?:resume|résumé|cover[_ -]?letter|candidate[_ -]?first[_ -]?name)\b', controls
        ):
            return True
    return False


def verify_application(job, report=None, *, render_form=True):
    """Check the exact posting and record application-form evidence separately."""
    url = job['url']
    job.pop('posting_verified', None)
    job.pop('application_verified', None)
    reference = posting_reference(url)
    requisition = job.get('requisition')
    if requisition:
        if not reference.startswith('https:'):
            linked_ids = [reference.rsplit(':', 1)[1]]
        else:
            linked_ids = up.parse_qs(up.urlsplit(url).query).get('gh_jid', [])
        if any(linked_id != str(requisition) for linked_id in linked_ids):
            raise ValueError('The posting link does not match the feed requisition')
    request = ur.Request(url, headers={'User-Agent': 'Mozilla/5.0 PersonalJobDashboard'})
    personio = (board_identity(url) or ('', ''))[0] == 'personio'
    raw, final = read_response(request, opener=PERSONIO_OPENER if personio else POSTING_OPENER,
                               max_bytes=1_000_000 if personio else 3_000_000)
    has_form = application_form_visible(job, raw.decode('utf-8', errors='replace'), final)
    if (not has_form and render_form and not personio and report is not None
            and config()['firecrawl_enabled'] and firecrawl_key()):
        try:
            data = firecrawl('scrape', {'url': url, 'formats': ['html', 'markdown'], 'maxAge': 0,
                                       'waitFor': 3000}, report)
            rendered_url = (data.get('metadata') or {}).get('url') or ''
            has_form = application_form_visible(job, data.get('html') or '', rendered_url)
        except PostingUnavailable:
            raise
        except (ValueError, OSError):
            # A failed render cannot establish form evidence. The static page still proves the posting.
            report.setdefault('log', []).append('Application form could not be confirmed by rendering.')
    job['posting_verified'] = now()
    job['application_evidence'] = 'Exact employer posting checked'
    if has_form:
        job['application_verified'] = job['posting_verified']
        job['application_evidence'] += '. Application form checked.'
    else:
        job['application_evidence'] += '. Application form needs verification.'
    return job


POSTING_CHECKS_PER_RUN = 20
RETAINED_POSTING_CHECKS = 8


def posting_check_expiration(job, cfg):
    checked = job.get('posting_verified')
    if not checked:
        return None
    return dt.datetime.fromisoformat(checked) + dt.timedelta(hours=cfg['verification_valid_hours'])


def finalize(job, cfg, report, *, check_posting=False, previous=None):
    job = assess(job, cfg)
    wants_form = job['queue'] == 'Confirmed'
    if job.get('availability') == 'Closed' or not (
        wants_form or check_posting or job.get('source') == 'Personio public employer feed'
        or (previous and (previous.get('posting_verified') or previous.get('posting_check_failed')
                          or previous.get('pending_match_alert')))
    ):
        return job

    if previous and not previous.get('pending_match_alert') and previous.get('availability') == 'Open':
        expiry = posting_check_expiration(previous, cfg)
        same_posting = previous.get('url') == job['url'] and previous.get('title') == job['title']
        if (same_posting and expiry and expiry >= dt.datetime.now(dt.timezone.utc)
                and (not wants_form or previous.get('application_verified'))):
            for field in ('posting_verified', 'application_verified', 'application_evidence'):
                if previous.get(field):
                    job[field] = previous[field]
            job['posting_check_failed'] = False
            return job

    host = up.urlsplit(job['url']).hostname or 'employer'
    limit = RETAINED_POSTING_CHECKS if previous else POSTING_CHECKS_PER_RUN
    attempted = False
    try:
        if (report.get('posting_checks', 0) >= limit or host in report.get('throttled_posting_hosts', [])):
            report['posting_checks_deferred'] = report.get('posting_checks_deferred', 0) + 1
            raise ValueError('Direct posting check deferred until a later search')
        attempted = True
        report['posting_checks'] = report.get('posting_checks', 0) + 1
        job['posting_check_attempted'] = now()
        verify_application(job, report, render_form=wants_form)
    except (ValueError, OSError) as error:
        if isinstance(error, urllib.error.HTTPError):
            if error.code == 429:
                report.setdefault('throttled_posting_hosts', []).append(host)
            reason = f'Employer posting returned HTTP {error.code}'
        elif isinstance(error, TimeoutError):
            reason = 'Employer posting check timed out'
            report.setdefault('failures', []).append(reason + ': ' + host)
        elif isinstance(error, ValueError):
            reason = str(error)
        else:
            reason = 'Employer posting could not be reached'
        job.update(availability='Needs Verification', application_evidence=reason, posting_check_failed=True)
        job.pop('posting_verified', None)
        job.pop('application_verified', None)
        report.setdefault('log', []).append(host + ': ' + reason)
    finally:
        if attempted:
            deadline = SEARCH_DEADLINE.get()
            delay = cfg['request_delay_seconds']
            remaining = delay if deadline is None else deadline - time.monotonic()
            time.sleep(max(0, min(delay, remaining)))
    if job.get('posting_verified'):
        job['posting_check_failed'] = False
    if wants_form and not job.get('application_verified'):
        job['queue'] = 'Review'
    return job


class PostingParser(HTMLParser):
    def __init__(self):super().__init__();self.capture=False;self.scripts=[];self.links=[];self.chunks=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script' and a.get('type')=='application/ld+json':self.capture=True;self.chunks=[]
        if tag=='a' and a.get('href'):self.links.append(a['href'])
    def handle_data(self,data):
        if self.capture:self.chunks.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.capture:
            try:self.scripts.append(json.loads(''.join(self.chunks)))
            except ValueError:pass
            self.capture=False
def jsonld_jobs(value):
    if isinstance(value,list):return [x for item in value for x in jsonld_jobs(item)]
    if isinstance(value,dict):
        if value.get('@type')=='JobPosting':return [value]
        return jsonld_jobs(value.get('@graph',[]))
    return []
def generic_posting(url,report,key):
    host=up.urlsplit(url).hostname
    if any(host==d or host.endswith('.'+d) for d in ('indeed.com','linkedin.com','ziprecruiter.com','glassdoor.com','talent.com','jooble.org','remotive.com')):raise ValueError('Aggregator application URL excluded')
    if key:
        network_call(lambda _: safe_url(url))
        data=firecrawl('scrape',{'url':url,'formats':['html'],'maxAge':0},report)
        raw=data.get('html','');final=data.get('metadata',{}).get('url',url)
    else:
        raw, final = read_response(ur.Request(url, headers={'User-Agent': 'Mozilla/5.0 PersonalJobDashboard'}),
                                   opener=POSTING_OPENER)
        raw = raw.decode('utf-8', errors='replace')
    if posting_reference(final) != posting_reference(url):
        raise ValueError('Employer posting redirected away from the requested page')
    parser=PostingParser();parser.feed(raw);postings=[x for s in parser.scripts for x in jsonld_jobs(s)]
    if len(postings)!=1:raise ValueError('No unique job-specific employer structured posting; needs manual verification')
    x=postings[0];org=x.get('hiringOrganization') or {};employer=org.get('name','');org_host=up.urlsplit(org.get('sameAs') or org.get('url') or '').hostname
    host = up.urlsplit(final).hostname
    official=host.endswith(('.myworkdayjobs.com','.smartrecruiters.com')) or (org_host and (host==org_host or host.endswith('.'+org_host)))
    if not official:raise ValueError('Employer ownership of this domain not established')
    loc=x.get('jobLocation',[]);loc=loc if isinstance(loc,list) else [loc]
    locations=[]
    for z in loc:
        a=z.get('address',{}) if isinstance(z,dict) else {}
        if isinstance(a,dict):locations.append(', '.join(str(a.get(k,'')) for k in ('addressLocality','addressRegion','addressCountry') if a.get(k)))
    applicant=x.get('applicantLocationRequirements',[]);applicant=applicant if isinstance(applicant,list) else [applicant]
    locations.extend(str(a.get('name','')) for a in applicant if isinstance(a,dict))
    availability='Needs Verification';expires=x.get('validThrough','')
    if expires and expires[:10]<now()[:10]:availability='Closed'
    apply_links=[up.urljoin(final,s) for s in parser.links if re.search(r'apply|application',s,re.I)]
    if availability!='Closed' and apply_links and not re.search(r'(no longer accepting|position has been filled|job (?:is )?(?:closed|expired))',clean(raw),re.I):availability='Open'
    j={'title':x.get('title',''),'employer':employer,'url':final,'location':'; '.join(locations),'remote':x.get('jobLocationType')=='TELECOMMUTE','description':posting_text(x.get('description')),'posted':x.get('datePosted',''),'availability':availability,'last_verified':now(),'source':'Live employer JobPosting structured data','application_evidence':'Unique JobPosting, employer domain relationship and application link' if availability=='Open' else 'Application availability requires review','salary_text':'Salary Not Published'}
    salary=x.get('baseSalary') or {};value=salary.get('value') or {}
    if salary.get('currency')=='USD' and value.get('unitText')=='YEAR':j.update(salary_min=value.get('minValue'),salary_max=value.get('maxValue') or value.get('value'),salary_currency='USD',salary_period='year',salary_type='base',salary_text=json.dumps(salary))
    return j
def backup():
    folder=DATA/'backups';folder.mkdir(exist_ok=True)
    dest=folder/('jobs-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
    with connect() as src, sqlite3.connect(dest, factory=Connection) as target:src.backup(target)
    for old in sorted(folder.glob('*.sqlite3'))[:-config()['backup_retention']]:old.unlink()
def firecrawl(endpoint,payload,report):
    if (deadline := SEARCH_DEADLINE.get()) is not None and time.monotonic() >= deadline:
        raise TimeoutError('Search time limit reached')
    keyfile=ROOT/'secrets'/'firecrawl.key'; key=keyfile.read_text().strip() if keyfile.exists() else ''
    if not key: raise ValueError('Firecrawl key not configured; public board discovery remains available')
    day=now()[:10]
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO usage(day) VALUES(?)',(day,))
        usage=c.execute('SELECT requests,reserved FROM usage WHERE day=?',(day,)).fetchone();count=usage[0]
        if count>=config()['max_firecrawl_requests_per_day']:raise ValueError('Daily Firecrawl request budget reached')
        reserve=2*payload.get('limit',5)+2 if endpoint=='search' else 5
        if usage[1]+reserve>config()['max_firecrawl_credit_units_per_day']:raise ValueError('Daily conservative Firecrawl credit-unit budget reached')
        c.execute('UPDATE usage SET requests=requests+1,reserved=reserved+? WHERE day=?',(reserve,day))
    # No automatic billable retry: uncertain responses may already have consumed credits.
    req=ur.Request('https://api.firecrawl.dev/v2/'+endpoint,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    raw, _ = read_response(req, opener=PERSONIO_OPENER, max_bytes=6_000_000, seconds=45, check_url=False)
    result = json.loads(raw)
    if not result.get('success'):raise ValueError('Firecrawl request failed')
    credits=result.get('creditsUsed')
    if credits is not None:
        report['firecrawl_credits_reported']+=credits
        with connect() as c:c.execute('UPDATE usage SET credits=credits+? WHERE day=?',(credits,day))
    report['firecrawl_requests']+=1
    return result.get('data',{})
def set_pending_alert(connection, job_id, pending):
    connection.execute(
        "UPDATE jobs SET listing=json_set(listing, '$.pending_match_alert', ?) WHERE id=?",
        (int(pending), job_id),
    )


def release_pending_alert(connection, job_id, previous, current, searches):
    if not previous.get('pending_match_alert'):
        return
    if current['availability'] == 'Closed':
        set_pending_alert(connection, job_id, False)
    elif current['availability'] == 'Open' and current.get('posting_verified'):
        matches = prototype.matching_searches(service(), current, searches)
        prototype.record_match_alerts(connection, job_id, matches, now())
        set_pending_alert(connection, job_id, False)


def run_pipeline(trigger='manual'):
    report={'new_qualified':0,'new_review':0,'reverified':0,'newly_closed':0,'duplicates':0,'failures':[],'top_new':[],'firecrawl_requests':0,'firecrawl_credits_reported':0,'log':[]}
    run_id = None
    deadline = time.monotonic() + SEARCH_SECONDS
    token = SEARCH_DEADLINE.set(deadline)
    SEARCH_ACTIVE.set()
    report['progress'] = {'stage': 'Preparing search'}

    def progress(stage, completed=None, total=None, source=None):
        report['progress'] = dict(stage=stage, completed=completed, total=total, source=source)
        with connect() as c:
            c.execute('UPDATE runs SET report=? WHERE id=?', (json.dumps(report), run_id))

    def time_left(remaining, kind):
        if time.monotonic() < deadline:
            return True
        report['failures'].append(f'Search time limit reached; {remaining} {kind} deferred. Run again to continue.')
        return False

    def pause():
        time.sleep(max(0, min(cfg['request_delay_seconds'], deadline - time.monotonic())))

    try:
        with connect() as c:
            cursor = c.execute('INSERT INTO runs(started,state,report,trigger) VALUES(?,?,?,?)',
                               (now(), 'running', json.dumps(report), trigger))
            run_id = cursor.lastrowid
            searches = prototype.saved_searches(c)
        cfg = config()
        backup()
        existing = [job for job in records() if not job.get('external_application')]
        boards = set()
        for j in existing:
            b=board_identity(j['url'])
            if b:boards.add(b)
        for platform,names in cfg['additional_boards'].items():boards.update((platform,n.lower()) for n in names)
        with connect() as c:
            for row in c.execute('SELECT source FROM source_health'):
                platform, _, slug = row['source'].partition('/')
                if platform in BOARD_PLATFORMS and re.fullmatch(r'[a-z0-9._-]+', slug):
                    boards.add((platform, slug))
        discoveries=[]
        key=firecrawl_key()
        if cfg.get('public_web_search_enabled'):
            start=dt.date.today().toordinal()*cfg.get('public_web_queries_per_run',3)
            total = cfg.get('public_web_queries_per_run',3)
            for offset in range(total):
                if not time_left(total - offset, 'public discovery queries'):
                    break
                progress('Discovering employer sources', offset, total)
                category=cfg['categories'][(start+offset)%len(cfg['categories'])]
                domains=['jobs.ashbyhq.com','job-boards.greenhouse.io','jobs.lever.co','myworkdayjobs.com','jobs.smartrecruiters.com']
                regions=cfg.get('target_locations') or ['remote United States','Jacksonville Florida','Buford Suwanee Duluth Georgia']
                query='"'+category+'" jobs '+regions[offset%len(regions)]+' site:'+domains[(start+offset)%len(domains)]
                try:
                    url='https://www.bing.com/search?format=rss&q='+up.quote(query)
                    raw, _ = read_response(ur.Request(url, headers={'User-Agent':'PersonalJobDashboard/1.0'}),
                                           max_bytes=1_000_000)
                    feed = ET.fromstring(raw)
                    for item in feed.findall('./channel/item'):
                        url=item.findtext('link','');b=board_identity(url)
                        if b:boards.add(b)
                        elif url.startswith('https://') and re.search(r'(myworkdayjobs\.com|smartrecruiters\.com|/careers?/|/jobs?/)',url):discoveries.append(url)
                    report['log'].append('Public web discovery: '+category)
                except Exception as e:report['failures'].append('Public web discovery: '+type(e).__name__)
                pause()
        if cfg['firecrawl_enabled'] and key:
            # Rotate categories over days so all categories receive coverage within a week.
            start=dt.date.today().toordinal()*cfg['firecrawl_searches_per_run']
            total = cfg['firecrawl_searches_per_run']
            for offset in range(total):
                if not time_left(total - offset, 'provider discovery queries'):
                    break
                progress('Discovering employer sources', offset, total)
                category=cfg['categories'][(start+offset)%len(cfg['categories'])]
                try:
                    hits=firecrawl('search',{'query':category+' jobs remote United States OR Jacksonville OR Suwanee OR Buford employer careers','limit':cfg['search_results'],'sources':['web'],'tbs':'qdr:w'},report)
                    for hit in hits.get('web',[]):
                        b=board_identity(hit.get('url',''))
                        if b:boards.add(b)
                        elif hit.get('url'): discoveries.append(hit['url'])
                except Exception as e:report['failures'].append('Firecrawl discovery: '+type(e).__name__+': '+str(e)[:160])
        else:report['log'].append('Public board mode: Firecrawl is disabled or no key is configured.')
        retained_by_identity = {identity(job['url']): job for job in existing}
        known_identities = {job['identity'] for job in existing} | retained_by_identity.keys()
        candidates = {}
        seen = set()
        successful = 0
        with connect() as c:
            checked = {r['source']:r['checked'] for r in c.execute('SELECT source,checked FROM source_health')}
        disabled = set(cfg.get('disabled_sources', []))
        pending_boards = {}
        for job in existing:
            board = board_identity(job['url'])
            if board and job.get('pending_match_alert'):
                attempted = job.get('posting_check_attempted', '')
                pending_boards[board] = min(pending_boards.get(board, attempted), attempted)
        board_list = sorted((pair for pair in boards if '/'.join(pair) not in disabled),
                            key=lambda pair: (pair not in pending_boards, pending_boards.get(pair, ''),
                                              checked.get('/'.join(pair), ''), pair))
        for index, (platform, board) in enumerate(board_list):
            if not time_left(len(board_list) - index, 'employer boards'):
                break
            progress('Checking employer boards', index, len(board_list), board)
            try:
                board_token = BOARD_DEADLINE.set(time.monotonic() + BOARD_SECONDS)
                try:
                    live = board_jobs(platform, board)
                finally:
                    BOARD_DEADLINE.reset(board_token)
                successful += 1
                by_id = {identity(j['url']):j for j in live}
                prototype.source_result(service(),platform+'/'+board,'ok',len(live))
                current=[j for j in existing if board_identity(j['url'])==(platform,board)]
                current.sort(key=lambda job: (not job.get('pending_match_alert'),
                                              job.get('posting_check_attempted', ''), job.get('last_verified', '')))
                recheck_limit = min(cfg['max_rechecks'], 8) if platform == 'smartrecruiters' else cfg['max_rechecks']
                with connect() as c:
                    for old in current[:recheck_limit]:
                        if time.monotonic() >= deadline:
                            break
                        ident=identity(old['url']);fresh=by_id.get(ident)
                        if fresh:
                            fresh = hydrate_board_listing(board, fresh)
                            # Keep original human readable employer names; ATS slugs are identifiers.
                            fresh['employer']=old['employer'];fresh['history_confirmation']=old.get('history_confirmation',False)
                            j = finalize(fresh, cfg, report, previous=old)
                            job_id, _ = upsert(c, j)
                            release_pending_alert(c, job_id, old, j, searches)
                            c.commit()
                            report['reverified'] += 1
                        elif platform == 'personio':
                            if old['availability'] != 'Closed':
                                old.pop('application_verified', None)
                                old.pop('posting_verified', None)
                                old.update(availability='Needs Verification', queue='Review',
                                           last_verified=now(), application_evidence='Missing from Personio feed; check employer page')
                                upsert(c,old);c.commit()
                        else:
                            old.pop('posting_verified', None)
                            old.pop('application_verified', None)
                            old['pending_match_alert'] = False
                            old['availability']='Closed';old['queue']='Review';old['last_verified']=now()
                            if old.get('application_evidence')!='Absent from employer live board':report['newly_closed']+=1
                            old['application_evidence']='Absent from employer live board';upsert(c,old);c.commit()
                    new_listings = live
                    if platform == 'smartrecruiters':
                        fresh = [j for j in live if identity(j['url']) not in known_identities]
                        enabled_searches = [search for search in searches if search['enabled'] and search.get('title_terms')]
                        search_targets = [j for j in fresh if any(
                            prototype.search_title_matches(j['title'], search) and location_eligibility(j, {
                                'target_locations': search['locations'], 'workplace_types': search['workplace_types'],
                            })[0] != 'Rejected' for search in enabled_searches
                        )]
                        search_target_ids = {j['requisition'] for j in search_targets}
                        remaining = [j for j in fresh if j['requisition'] not in search_target_ids]
                        relevant = lambda j: any(phrase.lower() in j['title'].lower() for phrase in cfg['categories'])
                        target = [j for j in remaining if relevant(j) and location_eligibility(j, cfg)[0] != 'Rejected']
                        target_ids = {identity(j['url']) for j in target}
                        other = [j for j in remaining if identity(j['url']) not in target_ids]
                        new_listings = rotating_postings(search_targets, run_id, 12)
                        new_listings += rotating_postings(target, run_id, 12 - len(new_listings))
                        new_listings += rotating_postings(other, run_id, 16 - len(new_listings))
                        report['deferred_source_details'] = report.get('deferred_source_details', 0) + len(fresh) - len(new_listings)
                    for j in new_listings:
                        ident=identity(j['url'])
                        if ident in seen:report['duplicates']+=1;continue
                        seen.add(ident)
                        if ident in known_identities:continue
                        j = assess(hydrate_board_listing(board, j), cfg)
                        matched = prototype.matching_searches(service(), j, searches)
                        if not matched and not profile_candidate(j, cfg, report):
                            continue
                        candidates[ident] = (j, matched)
                report['log'].append(platform+'/'+board+': '+str(len(live))+' live postings')
            except Exception as e:
                prototype.source_result(service(),platform+'/'+board,'error',error=type(e).__name__+': '+str(e))
                report['failures'].append(platform+'/'+board+': '+type(e).__name__+': '+str(e)[:160]);logging.exception('Board failed %s/%s',platform,board)
                # Failures never imply closure; queue freshness expires independently.
            progress('Checking employer boards', index + 1, len(board_list))
            pause()
        with connect() as c:known_urls=[r['source'] for r in c.execute("SELECT source FROM source_health WHERE source LIKE 'https://%'")]
        extra=list(dict.fromkeys([j['url'] for j in existing if not board_identity(j['url'])]+discoveries+cfg['additional_employer_urls']+known_urls))
        extra=[u for u in extra if u not in cfg.get('disabled_sources',[])]
        # Least recently attempted first: failed pages cannot starve the rest.
        with connect() as c:checked={r['source']:r['checked'] for r in c.execute('SELECT source,checked FROM source_health')}
        extra.sort(key=lambda u:checked.get(u,''))
        page_limit = min(len(extra), cfg.get('generic_urls_per_run', 5))
        attempted_pages = 0
        for index, url in enumerate(extra[:page_limit]):
            if not time_left(page_limit - index, 'employer pages'):
                break
            attempted_pages += 1
            progress('Checking individual postings', index, page_limit, up.urlsplit(url).hostname)
            try:
                j = generic_posting(url, report, key if cfg['firecrawl_enabled'] else '')
                prototype.source_result(service(), url, 'ok', 1)
                successful += 1
                ident = identity(j['url'])
                if ident in known_identities:
                    old = retained_by_identity.get(ident, {})
                    j = finalize(j, cfg, report, previous=old)
                    with connect() as c:
                        job_id, _ = upsert(c, j)
                        release_pending_alert(c, job_id, old, j, searches)
                    report['reverified'] += 1
                    continue
                j = assess(j, cfg)
                matched = prototype.matching_searches(service(), j, searches)
                if not matched and not profile_candidate(j, cfg, report):
                    continue
                if ident in candidates:
                    report['duplicates'] += 1
                else:
                    candidates[ident] = (j, matched)
            except Exception as e:
                prototype.source_result(service(),url,'manual review',error=type(e).__name__+': '+str(e))
                if isinstance(e, TimeoutError) or (isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError)):
                    report['failures'].append('Employer page could not be reached: ' + (up.urlsplit(url).hostname or 'unknown employer'))
                report['log'].append('Employer URL needs manual review: '+url+' ('+type(e).__name__+': '+str(e)[:100]+')')
            finally:
                pause()
        progress('Ranking results')
        ranked = sorted(candidates.values(), key=lambda item: (
            item[0]['queue'] == 'Confirmed', bool(item[1]), item[0]['matched_duty_count'], item[0]['score'],
            item[0].get('posted') or '',
        ), reverse=True)
        limit = cfg['max_new_candidates']
        new_count = 0
        report['deferred_candidates'] = 0
        progress('Saving results', 0, min(len(ranked), limit))
        for index, (job, matched) in enumerate(ranked):
            if new_count >= limit:
                report['deferred_candidates'] = len(ranked) - index
                break
            progress('Saving results', new_count, min(len(ranked), limit))
            job = finalize(job, cfg, report, check_posting=bool(matched))
            with connect() as c:
                job_id, added = upsert(c, job)
                if added and matched:
                    if job.get('posting_verified') and job['availability'] == 'Open':
                        prototype.record_match_alerts(c, job_id, matched, now())
                    elif job['availability'] != 'Closed':
                        set_pending_alert(c, job_id, True)
            if not added:
                report['duplicates'] += 1
            else:
                new_count += 1
                if job['queue'] == 'Confirmed':
                    report['new_qualified'] += 1
                    report['top_new'].append({key: job[key] for key in ('title', 'employer', 'url', 'score')})
                else:
                    report['new_review'] += 1
        report['unprocessed_employer_urls']=extra[attempted_pages:][:50]
        report['top_new']=sorted(report['top_new'],key=lambda j:-j['score'])[:10]
        report['manual_review'] = sum(
            j.get('queue') in ('Review', 'Location Review') and j.get('availability') != 'Closed'
            for j in records() if not j.get('external_application')
        )
        if time.monotonic() >= deadline and not any('Search time limit' in issue for issue in report['failures']):
            report['failures'].append('Search time limit reached; some checks may have been deferred.')
        if not successful and not report['failures']:
            report['failures'].append('No configured employer sources returned usable postings.')
        report['state'] = ('partial' if report['failures'] else 'success') if successful else 'failed'
    except Exception as e:
        logging.exception('Search failed');report['failures'].append(type(e).__name__+': '+str(e)[:180]);report['state']='failed'
    finally:
        try:
            if run_id:
                with connect() as c:
                    c.execute('UPDATE runs SET finished=?,state=?,report=? WHERE id=?',
                              (now(), report.get('state', 'failed'), json.dumps(report), run_id))
        finally:
            SEARCH_DEADLINE.reset(token)
            SEARCH_ACTIVE.clear()
            LOCK.release()
    return report

def start_run(trigger='manual'):
    if not LOCK.acquire(False):
        return False
    SEARCH_ACTIVE.set()
    try:
        threading.Thread(target=run_pipeline, args=(trigger,), daemon=True).start()
    except Exception:
        SEARCH_ACTIVE.clear()
        LOCK.release()
        raise
    return True

def scheduled_run_due(c, utc, hour):
    if utc.hour < hour:
        return False
    start = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = c.execute(
        "SELECT state, finished FROM runs WHERE trigger='scheduled' AND started>=? ORDER BY id DESC LIMIT 3",
        (start.isoformat(timespec='seconds'),),
    ).fetchall()
    if not rows:
        return True
    if len(rows) >= 3 or any(row['state'] in ('running', 'success', 'partial') for row in rows):
        return False
    finished = rows[0]['finished']
    return bool(finished and utc - dt.datetime.fromisoformat(finished) >= dt.timedelta(minutes=30))

def schedule():
    while True:
        try:
            cfg = config()
            if cfg['schedule_enabled'] and not LOCK.locked():
                utc = dt.datetime.now(dt.timezone.utc)
                with connect() as c:
                    due = scheduled_run_due(c, utc, cfg['schedule_hour_utc'])
                if due:
                    start_run('scheduled')
        except Exception:
            logging.exception('Scheduler')
        time.sleep(30)

def search_status():
    running = SEARCH_ACTIVE.is_set()
    with connect() as c:
        row = c.execute('SELECT id,state,started,finished,report FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    if not row:
        return {'running': running, 'run': None}
    run = dict(row)
    report = json.loads(run.pop('report'))
    run.update(progress=report.get('progress') if running and run['state'] == 'running' else None,
               new_qualified=report.get('new_qualified', 0), new_review=report.get('new_review', 0),
               failures=len(report.get('failures', [])))
    return {'running': SEARCH_ACTIVE.is_set(), 'run': run}


def snapshot():
    cfg=config();jobs=records();stamp=dt.datetime.now(dt.timezone.utc)
    for j in jobs:
        if j.get('external_application'):
            j.update(score=0, match_label='Added by you', review_blockers=[], queue='Tracking')
            continue
        expires = posting_check_expiration(j, cfg)
        j['posting_link_verified'] = bool(j.get('availability') == 'Open' and expires and stamp <= expires)
        if expires:
            j['posting_verification_expires'] = expires.isoformat(timespec='seconds')
        previous_queue=j.get('queue');previous_application=j.get('application_verified')
        assess(j,cfg)
        if j.get('queue')=='Confirmed' and (previous_queue!='Confirmed' or not previous_application):j['queue']='Review'
        eligible,reason,area=location_eligibility(j,cfg)
        j.update(location_eligibility=eligible,location_reason=reason,area=area)
        j['review_blockers']=review_blockers(j,cfg)
        if eligible!='Eligible':j['queue']='Excluded' if eligible=='Rejected' else 'Location Review'
        if j.get('queue')=='Confirmed':
            verified=j.get('application_verified')
            if not verified or (stamp-dt.datetime.fromisoformat(verified)).total_seconds()>cfg['verification_valid_hours']*3600:j['queue']='Review';j['stale']=True
        j['match_label']='Excellent Match' if j.get('score',0)>=85 else 'Strong Match' if j.get('score',0)>=70 else 'Reasonable Match' if j.get('score',0)>=55 else 'Stretch Opportunity'
    with connect() as c:
        interests = {r['job_id']: dict(r) for r in c.execute('SELECT * FROM job_interests')}
        for job in jobs:
            job['interest'] = interests.get(job['id'])
        runs=[dict(r) for r in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 30')]
        for r in runs:r['report']=json.loads(r['report'])
    return prototype.enrich_snapshot(service(),{'jobs':jobs,'runs':runs,'statuses':STATUSES,'running':SEARCH_ACTIVE.is_set(),'external_application_tracking':True,'application_prep_available':True,'firecrawl_configured':bool(cfg['firecrawl_enabled'] and firecrawl_key()),'schedule_hour_utc':cfg['schedule_hour_utc']})
def application_prep(job_id):
    with connect() as connection:
        row = connection.execute(
            """SELECT jobs.listing, application_drafts.draft, application_drafts.version, application_drafts.updated
               FROM jobs LEFT JOIN application_drafts ON application_drafts.job_id=jobs.id WHERE jobs.id=?""",
            (job_id,),
        ).fetchone()
    if not row:
        return 404, {'error': 'Job not found.'}
    job = json.loads(row['listing'])
    if job.get('external_application'):
        return 400, {'error': 'Application prep needs an employer posting.'}

    cfg = config()
    profile = cfg.get('profile', '')
    description = clean(job.get('description'))
    skills = list({skill.strip().casefold(): skill.strip()
                   for skill in cfg.get('preferred_skills', []) if skill.strip()}.values())
    examples = profile_skill_examples(profile, skills)
    evidence = [
        dict(item, profile_excerpt=examples[item['skill']])
        for item in experience_evidence(description, profile, skills, examples)
    ]
    duties = list(employer_duties(description))
    missing_examples = [
        skill for skill in skills if skill not in examples and any(map(skill_pattern(skill).search, duties))
    ]
    return 200, {
        'draft': row['draft'] or '', 'version': row['version'] or 0, 'updated': row['updated'],
        'examples': evidence, 'skills_to_document': missing_examples[:12],
        'qualification_checks': qualification_checks(description),
        'has_profile': bool(profile.strip()), 'has_description': bool(description.strip()),
    }


def save_application_draft(job_id, payload):
    if not isinstance(payload, dict):
        return 400, {'error': 'Enter a valid application draft.'}
    draft, version = payload.get('draft'), payload.get('version')
    if not isinstance(draft, str) or len(draft) > 8000 or type(version) is not int or version < 0:
        return 400, {'error': 'Application drafts can contain up to 8,000 characters.'}
    try:
        draft.encode('utf-8')
    except UnicodeError:
        return 400, {'error': 'The draft contains invalid text.'}

    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        listing = connection.execute('SELECT listing FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not listing:
            return 404, {'error': 'Job not found.'}
        if json.loads(listing['listing']).get('external_application'):
            return 400, {'error': 'Application prep needs an employer posting.'}
        saved = connection.execute(
            'SELECT draft, version, updated FROM application_drafts WHERE job_id=?', (job_id,),
        ).fetchone()
        current_version = saved['version'] if saved else 0
        if saved and draft == saved['draft']:
            return 200, dict(saved)
        if version != current_version:
            return 409, {'error': 'The saved draft changed. Reload it before replacing it.'}

        updated = now()
        connection.execute(
            """INSERT INTO application_drafts(job_id,draft,version,updated) VALUES(?,?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET draft=excluded.draft,version=excluded.version,updated=excluded.updated""",
            (job_id, draft, version + 1, updated),
        )
    return 200, {'draft': draft, 'version': version + 1, 'updated': updated}


def save_interest(job_id, payload):
    state = payload.get('state')
    version = payload.get('version')
    if state not in ('saved', 'passed', 'none') or type(version) is not int:
        return 400, {'error': 'Invalid job action'}
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM jobs WHERE id=?', (job_id,)).fetchone():
            return 404, {'error': 'Job not found'}
        row = c.execute('SELECT version FROM job_interests WHERE job_id=?', (job_id,)).fetchone()
        if version != (row['version'] if row else 0):
            return 409, {'error': 'This job changed. Refresh and try again.'}
        c.execute("""INSERT INTO job_interests(job_id,state,version,updated) VALUES(?,?,?,?)
            ON CONFLICT(job_id) DO UPDATE SET state=excluded.state,version=excluded.version,updated=excluded.updated""",
                  (job_id, state, version + 1, now()))
    return 200, {'saved': True}


class Handler(BaseHTTPRequestHandler):
    def send(self,status,data,kind='application/json'):
        raw=json.dumps(data).encode() if kind=='application/json' else data.encode()
        self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass
    def do_GET(self):
        path=up.urlsplit(self.path).path
        if path=='/api/dashboard':return self.send(200,snapshot())
        if path=='/api/v1/health':return self.send(200,{'status':'ok','api_version':1})
        if path=='/api/v1/search-status':return self.send(200,search_status())
        if path=='/api/v1/dashboard':return self.send(200,snapshot())
        prep_match = re.fullmatch(r'/api/jobs/(\d+)/application-prep', path)
        if prep_match:
            return self.send(*application_prep(int(prep_match[1])))
        if path in ('/','/index.html'):return self.send(200,(ROOT/'site'/'index.html').read_text(encoding='utf-8-sig'),'text/html')
        if path=='/dashboard.js':return self.send(200,(ROOT/'site'/'dashboard.js').read_text(encoding='utf-8-sig'),'text/javascript')
        if path=='/prototype.js':return self.send(200,(ROOT/'site'/'prototype.js').read_text(encoding='utf-8-sig'),'text/javascript')
        if path=='/prototype.css':return self.send(200,(ROOT/'site'/'prototype.css').read_text(encoding='utf-8-sig'),'text/css')
        self.send(404,{'error':'Not found'})
    def do_POST(self):
        # Reject cross-site form/script mutations, including DNS rebinding origins.
        host=self.headers.get('Host','');origin=self.headers.get('Origin','')
        if self.headers.get('X-Jobs-Client')!='dashboard' or (origin and up.urlsplit(origin).netloc!=host):return self.send(403,{'error':'Same-origin dashboard required'})
        if self.path=='/api/run':return self.send(202 if start_run() else 409,{'running':True})
        if self.path == '/api/applications':
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 50000:
                    raise ValueError('The application form is too large or empty.')
                payload = json.loads(self.rfile.read(size))
                status, result = add_external_application(payload)
            except (json.JSONDecodeError, UnicodeError):
                return self.send(400, {'error': 'Could not read the application form.'})
            except ValueError as error:
                return self.send(400, {'error': str(error)})
            return self.send(status, result)
        if self.path=='/api/saved-searches':
            try:
                size = int(self.headers.get('Content-Length',0))
                if not 0 < size <= 20000:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(size))
                if isinstance(payload, dict) and payload.get('action') == 'read':
                    code, result = prototype.change_saved_search(service(), payload)
                    return self.send(code, result)
                if not LOCK.acquire(False):
                    return self.send(409, {'error': 'Wait for the current search to finish.'})
                try:
                    code, result = prototype.change_saved_search(service(), payload)
                    return self.send(code, result)
                finally:
                    LOCK.release()
            except (ValueError, TypeError) as e:
                return self.send(400, {'error': str(e)})
        if self.path=='/api/preferences':
            if not LOCK.acquire(False):return self.send(409,{'error':'Wait for the search to finish before changing preferences.'})
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=60000:raise ValueError('Invalid request size')
                code,result=prototype.save_preferences(service(),json.loads(self.rfile.read(size)))
                return self.send(code,result)
            except (ValueError,TypeError,KeyError) as e:return self.send(400,{'error':str(e)})
            finally:LOCK.release()
        prep_match = re.fullmatch(r'/api/jobs/(\d+)/application-prep', self.path)
        if prep_match:
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 100000:
                    raise ValueError
                payload = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeError):
                return self.send(400, {'error': 'Could not read the application draft.'})
            return self.send(*save_application_draft(int(prep_match[1]), payload))
        interest_match = re.fullmatch(r'/api/jobs/(\d+)/interest', self.path)
        if interest_match:
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 2000:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('Invalid request')
                code, result = save_interest(int(interest_match[1]), payload)
                return self.send(code, result)
            except (ValueError, TypeError) as error:
                return self.send(400, {'error': str(error)})
        ai_match=re.fullmatch(r'/api/jobs/(\d+)/ai-review',self.path)
        if ai_match:
            code,result=prototype.ai_review(service(),int(ai_match[1]));return self.send(code,result)
        review_match=re.fullmatch(r'/api/jobs/(\d+)/review',self.path)
        if review_match:
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=20000:raise ValueError('Invalid size')
                code,result=save_review(int(review_match[1]),json.loads(self.rfile.read(size)))
                return self.send(code,result)
            except (ValueError,TypeError):return self.send(400,{'error':'Invalid review fields'})
        m=re.fullmatch(r'/api/jobs/(\d+)/tracking',self.path)
        if not m:return self.send(404,{'error':'Not found'})
        try:
            size=int(self.headers.get('Content-Length',0))
            if size>20000:raise ValueError('Request too large')
            d=json.loads(self.rfile.read(size));status=d['status']
            if status not in STATUSES:raise ValueError('Invalid status')
            for field in ('application_date','follow_up'):
                if d.get(field):dt.date.fromisoformat(d[field])
            with connect() as c:
                result=c.execute('UPDATE tracking SET status=?,application_date=?,notes=?,follow_up=?,updated=?,version=version+1 WHERE job_id=? AND version=?',(status,d.get('application_date',''),str(d.get('notes',''))[:10000],d.get('follow_up',''),now(),int(m[1]),int(d['version'])))
                if not result.rowcount:return self.send(409,{'error':'This record changed on another device. Reload before editing.'})
                c.execute('INSERT INTO events(job_id,at,detail) VALUES(?,?,?)',(int(m[1]),now(),json.dumps(d)))
            self.send(200,{'saved':True})
        except (ValueError,KeyError):self.send(400,{'error':'Invalid tracking fields'})
    def log_message(self,*args):pass
if __name__=='__main__':
    init()
    if '--run' in __import__('sys').argv:
        LOCK.acquire();print(json.dumps(run_pipeline(),indent=2))
    else:
        threading.Thread(target=schedule,daemon=True).start()
        ThreadingHTTPServer((os.environ.get('JOBS_BIND_HOST', '0.0.0.0'), 8084), Handler).serve_forever()
