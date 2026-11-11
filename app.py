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
import urllib.error
import urllib.parse as up
import urllib.request as ur
import xml.etree.ElementTree as ET
import prototype
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
def norm(s): return re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
def identity(url):
    u=up.urlsplit(url); host=(u.hostname or '').lower(); path=u.path.rstrip('/'); parts=path.split('/')
    if host in ('boards.greenhouse.io','job-boards.greenhouse.io') and len(parts)>=4:
        return 'greenhouse:'+parts[1].lower()+':'+parts[3]
    if host=='jobs.ashbyhq.com' and len(parts)>=3: return 'ashby:'+parts[1].lower()+':'+parts[2]
    if host=='jobs.lever.co' and len(parts)>=3: return 'lever:'+parts[1].lower()+':'+parts[2]
    query=up.urlencode([(k,v) for k,v in up.parse_qsl(u.query) if k in ('gh_jid','jobId','requisitionId')])
    return up.urlunsplit(('https',host,path,query,''))
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
def fetch(url, payload=None, key=None):
    safe_url(url)
    headers={'User-Agent':'PersonalJobDashboard/1.0','Accept':'application/json'}
    if payload is not None: headers['Content-Type']='application/json'
    if key: headers['Authorization']='Bearer '+key
    for attempt in range(3):
        try:
            req=ur.Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
            with OPENER.open(req,timeout=35) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==2: raise
        except (TimeoutError,urllib.error.URLError):
            if attempt==2: raise
        time.sleep(2**attempt*2)
    raise RuntimeError('Request retries exhausted')
def init():
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, fallback TEXT, listing TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS jobs_fallback ON jobs(fallback);
        CREATE TABLE IF NOT EXISTS tracking(job_id INTEGER PRIMARY KEY REFERENCES jobs(id),status TEXT NOT NULL DEFAULT 'Needs Verification',application_date TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',follow_up TEXT NOT NULL DEFAULT '',updated TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,started TEXT NOT NULL,finished TEXT,state TEXT NOT NULL,report TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,job_id INTEGER,at TEXT NOT NULL,detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY,requests INTEGER NOT NULL DEFAULT 0,credits REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS job_interests(job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
            state TEXT NOT NULL, version INTEGER NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews(job_id INTEGER PRIMARY KEY REFERENCES jobs(id),decision TEXT NOT NULL DEFAULT 'Pending',note TEXT NOT NULL DEFAULT '',reviewer TEXT NOT NULL DEFAULT '',checks TEXT NOT NULL DEFAULT '{}',updated TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0);
        PRAGMA user_version=1;''')
        if 'reserved' not in [r[1] for r in c.execute('PRAGMA table_info(usage)')]:c.execute('ALTER TABLE usage ADD COLUMN reserved INTEGER NOT NULL DEFAULT 0')
        c.execute('PRAGMA user_version=3')
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
        for row in c.execute('SELECT id,listing FROM jobs').fetchall():
            j=json.loads(row['listing']);eligible,reason,area=location_eligibility(j,config())
            j.update(location_eligibility=eligible,location_reason=reason,area=area)
            if eligible!='Eligible':j['queue']='Excluded' if eligible=='Rejected' else 'Location Review'
            c.execute('UPDATE jobs SET listing=? WHERE id=?',(json.dumps(j),row['id']))
def upsert(c,j):
    ident=identity(j['url']); fallback='|'.join(norm(str(j.get(k,''))) for k in ('employer','title','location'))
    row=c.execute('SELECT * FROM jobs WHERE identity=?',(ident,)).fetchone()
    if not row: row=c.execute('SELECT * FROM jobs WHERE fallback=?',(fallback,)).fetchone()
    stamp=now()
    if row:
        old=json.loads(row['listing'])
        # A fresh employer response owns these facts, including their absence.
        for field in ('salary_min','salary_max','salary_currency','salary_period','salary_type','compensation_details','application_verified'):
            old.pop(field,None)
        old.update(j)
        c.execute('UPDATE jobs SET listing=?,updated=? WHERE id=?',(json.dumps(old),stamp,row['id']))
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
def review_blockers(j):
    cfg=config();geo=location_eligibility(j,cfg)[0];problems=[]
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
                      if re.search(r'(?<![\w+#])' + re.escape(skill) + r'(?![\w+#])', text)]
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
    gaps = [] if desc.strip() else ['Employer description missing. Review the posting for duties and requirements.']
    j.update(
        category=category, score=score, eligibility=eligible, score_breakdown=breakdown,
        matched_skills=matched_skills, matched_groups=[group['label'] for group in matched_groups],
        match_gaps=gaps,
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
        out=[]
        for x in data.get('jobs',[]):
            out.append({'title':x['title'],'employer':board,'url':x['absolute_url'],'location':x.get('location',{}).get('name',''),'description':clean(x.get('content','')),'posted':x.get('updated_at',''),'remote': 'remote' in x.get('location',{}).get('name','').lower(),'availability':'Open','last_verified':now(),'source':'Greenhouse public live board','requisition':str(x['id']),'application_evidence':'Listed in employer live board with absolute application URL','salary_text':'Salary not yet verified'})
        return out
    if platform=='ashby':
        data=fetch('https://api.ashbyhq.com/posting-api/job-board/'+up.quote(board,safe='')+'?includeCompensation=true');out=[]
        for x in data.get('jobs',[]):
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
            j={'title':x['text'],'employer':board,'url':x['applyUrl'],'location':loc,'description':x.get('descriptionPlain','')+' '+clean(' '.join(z.get('content','') for z in x.get('lists',[]))),'posted':dt.datetime.fromtimestamp(x['createdAt']/1000,dt.timezone.utc).isoformat() if x.get('createdAt') else '', 'remote':x.get('workplaceType')=='remote','availability':'Open','last_verified':now(),'source':'Lever public live board','requisition':x['id'],'application_evidence':'Employer live posting and applyUrl','salary_text':x.get('salaryDescriptionPlain') or 'Salary Not Published'}
            if salary.get('currency')=='USD' and salary.get('interval')=='per-year':j.update(salary_min=salary.get('min'),salary_max=salary.get('max'),salary_currency='USD',salary_period='year',salary_type='base')
            out.append(j)
        return out
    raise ValueError('Unsupported board')
def board_identity(url):
    u=up.urlsplit(url);parts=u.path.strip('/').split('/')
    platform={'boards.greenhouse.io':'greenhouse','job-boards.greenhouse.io':'greenhouse','jobs.ashbyhq.com':'ashby','jobs.lever.co':'lever'}.get((u.hostname or '').lower())
    return (platform,parts[0].lower()) if platform and parts[0] else None
def verify_application(j,report=None):
    """A live board record alone is insufficient: check job-specific application evidence."""
    url=j['url'];safe_url(url)
    try:
        with OPENER.open(ur.Request(url,headers={'User-Agent':'Mozilla/5.0 PersonalJobDashboard'}),timeout=25) as response:
            raw=response.read(3000000).decode('utf-8',errors='replace');final=response.url
    except Exception:
        key=firecrawl_key()
        if not key or not config()['firecrawl_enabled'] or report is None:raise
        data=firecrawl('scrape',{'url':url,'formats':['html','markdown'],'maxAge':0,'waitFor':3000},report)
        raw=data.get('html','')+'\n'+data.get('markdown','');final=data.get('metadata',{}).get('url',url)
    if identity(final)!=identity(url):raise ValueError('Application redirected away from the requisition')
    content=html.unescape(raw).lower()
    if re.search(r'(no longer accepting applications|position has been filled|job is (?:closed|expired)|job not found)',clean(content)):raise ValueError('Application page says unavailable')
    tokens=[t for t in norm(j['title']).split() if len(t)>3]
    if tokens and sum(t in content for t in tokens)<max(1,len(tokens)//2):raise ValueError('Job title not confirmed on application page')
    if not re.search(r'(<form|applicationform|application_form|apply for this job|submit application|ashby-application-form)',content):
        raise ValueError('Application form not confirmed in accessible page content')
    j['application_evidence']+='; direct requisition page and application-form evidence checked'
    j['application_verified']=now()
    return j
def finalize(j,cfg,report):
    j=assess(j,cfg)
    if j['queue']=='Confirmed':
        try:verify_application(j,report)
        except Exception as e:
            j['queue']='Review';j['application_evidence']='Needs Verification: '+str(e)[:160]
            report['log'].append(j['url']+': application requires review')
    return j
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
    safe_url(url)
    host=up.urlsplit(url).hostname
    if any(host==d or host.endswith('.'+d) for d in ('indeed.com','linkedin.com','ziprecruiter.com','glassdoor.com','talent.com','jooble.org','remotive.com')):raise ValueError('Aggregator application URL excluded')
    if key:
        data=firecrawl('scrape',{'url':url,'formats':['html'],'maxAge':0},report)
        raw=data.get('html','');final=data.get('metadata',{}).get('url',url)
    else:
        with OPENER.open(ur.Request(url,headers={'User-Agent':'Mozilla/5.0 PersonalJobDashboard'}),timeout=30) as r:raw=r.read(3000000).decode('utf-8',errors='replace');final=r.url
    parser=PostingParser();parser.feed(raw);postings=[x for s in parser.scripts for x in jsonld_jobs(s)]
    if len(postings)!=1:raise ValueError('No unique job-specific employer structured posting; needs manual verification')
    x=postings[0];org=x.get('hiringOrganization') or {};employer=org.get('name','');org_host=up.urlsplit(org.get('sameAs') or org.get('url') or '').hostname
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
    j={'title':x.get('title',''),'employer':employer,'url':final,'location':'; '.join(locations),'remote':x.get('jobLocationType')=='TELECOMMUTE','description':clean(x.get('description','')),'posted':x.get('datePosted',''),'availability':availability,'last_verified':now(),'source':'Live employer JobPosting structured data','application_evidence':'Unique JobPosting, employer domain relationship and application link' if availability=='Open' else 'Application availability requires review','salary_text':'Salary Not Published'}
    salary=x.get('baseSalary') or {};value=salary.get('value') or {}
    if salary.get('currency')=='USD' and value.get('unitText')=='YEAR':j.update(salary_min=value.get('minValue'),salary_max=value.get('maxValue') or value.get('value'),salary_currency='USD',salary_period='year',salary_type='base',salary_text=json.dumps(salary))
    return j
def backup():
    folder=DATA/'backups';folder.mkdir(exist_ok=True)
    dest=folder/('jobs-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
    with connect() as src, sqlite3.connect(dest, factory=Connection) as target:src.backup(target)
    for old in sorted(folder.glob('*.sqlite3'))[:-config()['backup_retention']]:old.unlink()
def firecrawl(endpoint,payload,report):
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
    with ur.urlopen(req,timeout=70) as r: result=json.load(r)
    if not result.get('success'):raise ValueError('Firecrawl request failed')
    credits=result.get('creditsUsed')
    if credits is not None:
        report['firecrawl_credits_reported']+=credits
        with connect() as c:c.execute('UPDATE usage SET credits=credits+? WHERE day=?',(credits,day))
    report['firecrawl_requests']+=1
    return result.get('data',{})
def run_pipeline():
    report={'new_qualified':0,'new_review':0,'reverified':0,'newly_closed':0,'duplicates':0,'failures':[],'top_new':[],'firecrawl_requests':0,'firecrawl_credits_reported':0,'log':[]}
    run_id=None
    try:
        cfg=config();backup()
        with connect() as c:
            searches = prototype.saved_searches(c)
            cur=c.execute('INSERT INTO runs(started,state,report) VALUES(?,?,?)',(now(),'running',json.dumps(report)));run_id=cur.lastrowid
        existing=records(); boards=set()
        for j in existing:
            b=board_identity(j['url'])
            if b:boards.add(b)
        for platform,names in cfg['additional_boards'].items():boards.update((platform,n.lower()) for n in names)
        with connect() as c:
            for row in c.execute('SELECT source FROM source_health'):
                if re.fullmatch(r'(ashby|greenhouse|lever)/[a-z0-9._-]+',row['source']):boards.add(tuple(row['source'].split('/',1)))
        discoveries=[]
        key=firecrawl_key()
        if cfg.get('public_web_search_enabled'):
            start=dt.date.today().toordinal()*cfg.get('public_web_queries_per_run',3)
            for offset in range(cfg.get('public_web_queries_per_run',3)):
                category=cfg['categories'][(start+offset)%len(cfg['categories'])]
                domains=['jobs.ashbyhq.com','job-boards.greenhouse.io','jobs.lever.co','myworkdayjobs.com','jobs.smartrecruiters.com']
                regions=cfg.get('target_locations') or ['remote United States','Jacksonville Florida','Buford Suwanee Duluth Georgia']
                query='"'+category+'" jobs '+regions[offset%len(regions)]+' site:'+domains[(start+offset)%len(domains)]
                try:
                    url='https://www.bing.com/search?format=rss&q='+up.quote(query)
                    with OPENER.open(ur.Request(url,headers={'User-Agent':'PersonalJobDashboard/1.0'}),timeout=25) as response:feed=ET.fromstring(response.read(1000000))
                    for item in feed.findall('./channel/item'):
                        url=item.findtext('link','');b=board_identity(url)
                        if b:boards.add(b)
                        elif url.startswith('https://') and re.search(r'(myworkdayjobs\.com|smartrecruiters\.com|/careers?/|/jobs?/)',url):discoveries.append(url)
                    report['log'].append('Public web discovery: '+category)
                except Exception as e:report['failures'].append('Public web discovery: '+type(e).__name__)
                time.sleep(cfg['request_delay_seconds'])
        if cfg['firecrawl_enabled'] and key:
            # Rotate categories over days so all categories receive coverage within a week.
            start=dt.date.today().toordinal()*cfg['firecrawl_searches_per_run']
            for offset in range(cfg['firecrawl_searches_per_run']):
                category=cfg['categories'][(start+offset)%len(cfg['categories'])]
                try:
                    hits=firecrawl('search',{'query':category+' jobs remote United States OR Jacksonville OR Suwanee OR Buford employer careers','limit':cfg['search_results'],'sources':['web'],'tbs':'qdr:w'},report)
                    for hit in hits.get('web',[]):
                        b=board_identity(hit.get('url',''))
                        if b:boards.add(b)
                        elif hit.get('url'): discoveries.append(hit['url'])
                except Exception as e:report['failures'].append('Firecrawl discovery: '+type(e).__name__+': '+str(e)[:160])
        else:report['log'].append('Public board mode: Firecrawl is disabled or no key is configured.')
        new_count=0;seen=set();successful=0
        for platform,board in sorted(boards):
            if platform+'/'+board in cfg.get('disabled_sources',[]):continue
            try:
                live=board_jobs(platform,board);successful+=1; by_id={identity(j['url']):j for j in live}
                prototype.source_result(service(),platform+'/'+board,'ok',len(live))
                current=[j for j in existing if board_identity(j['url'])==(platform,board)]
                current.sort(key=lambda j:j.get('last_verified',''))
                with connect() as c:
                    for old in current[:cfg['max_rechecks']]:
                        ident=identity(old['url']);fresh=by_id.get(ident)
                        if fresh:
                            # Keep original human readable employer names; ATS slugs are identifiers.
                            fresh['employer']=old['employer'];fresh['history_confirmation']=old.get('history_confirmation',False)
                            j=finalize(fresh,cfg,report);upsert(c,j);c.commit();report['reverified']+=1
                        else:
                            old['availability']='Closed';old['queue']='Review';old['last_verified']=now()
                            if old.get('application_evidence')!='Absent from employer live board':report['newly_closed']+=1
                            old['application_evidence']='Absent from employer live board';upsert(c,old);c.commit()
                    for j in live:
                        ident=identity(j['url'])
                        if ident in seen:report['duplicates']+=1;continue
                        seen.add(ident)
                        if any(x['identity']==ident for x in existing):continue
                        if new_count>=cfg['max_new_candidates']:continue
                        j = assess(j, cfg)
                        matched = prototype.matching_searches(service(), j, searches)
                        role_match = j['category'] != 'Other / Review'
                        location_match = j['location_eligibility'] in discovery_locations(cfg)
                        if not matched:
                            if role_match and not location_match:
                                report['skipped_location'] = report.get('skipped_location', 0) + 1
                            if not role_match or not location_match or j['queue'] == 'Excluded':
                                continue
                        if j['queue'] == 'Confirmed':
                            j = finalize(j, cfg, report)
                        job_id, added = upsert(c, j)
                        if added:
                            prototype.record_match_alerts(c, job_id, matched, now())
                        c.commit()
                        if added:
                            new_count+=1;report['new_qualified' if j['queue']=='Confirmed' else 'new_review']+=1
                            if j['queue']=='Confirmed':report['top_new'].append({k:j[k] for k in ('title','employer','url','score')})
                        else:report['duplicates']+=1
                report['log'].append(platform+'/'+board+': '+str(len(live))+' live postings')
            except Exception as e:
                prototype.source_result(service(),platform+'/'+board,'error',error=type(e).__name__+': '+str(e))
                report['failures'].append(platform+'/'+board+': '+type(e).__name__+': '+str(e)[:160]);logging.exception('Board failed %s/%s',platform,board)
                # Failures never imply closure; queue freshness expires independently.
            if run_id:
                with connect() as c:c.execute('UPDATE runs SET report=? WHERE id=?',(json.dumps(report),run_id))
            time.sleep(cfg['request_delay_seconds'])
        with connect() as c:known_urls=[r['source'] for r in c.execute("SELECT source FROM source_health WHERE source LIKE 'https://%'")]
        extra=list(dict.fromkeys([j['url'] for j in existing if not board_identity(j['url'])]+discoveries+cfg['additional_employer_urls']+known_urls))
        extra=[u for u in extra if u not in cfg.get('disabled_sources',[])]
        # Least recently attempted first: failed pages cannot starve the rest.
        with connect() as c:checked={r['source']:r['checked'] for r in c.execute('SELECT source,checked FROM source_health')}
        extra.sort(key=lambda u:checked.get(u,''))
        for url in extra[:cfg.get('generic_urls_per_run',5)]:
            try:
                j=finalize(generic_posting(url,report,key if cfg['firecrawl_enabled'] else ''),cfg,report)
                prototype.source_result(service(),url,'ok',1);successful+=1
                matched = prototype.matching_searches(service(), j, searches)
                if not matched and (j.get('location_eligibility')!='Eligible' or j['queue']=='Excluded'):continue
                if new_count>=cfg['max_new_candidates'] and not any(identity(url)==x['identity'] for x in existing):continue
                with connect() as c:
                    job_id, added = upsert(c, j)
                    if added:
                        prototype.record_match_alerts(c, job_id, matched, now())
                if added:
                    new_count+=1
                    report['new_qualified' if j['queue']=='Confirmed' else 'new_review']+=1
                    if j['queue']=='Confirmed':report['top_new'].append({k:j[k] for k in ('title','employer','url','score')})
                else:report['duplicates']+=1
            except Exception as e:
                prototype.source_result(service(),url,'manual review',error=type(e).__name__+': '+str(e))
                report['log'].append('Employer URL needs manual review: '+url+' ('+type(e).__name__+': '+str(e)[:100]+')')
            time.sleep(cfg['request_delay_seconds'])
        report['unprocessed_employer_urls']=extra[cfg.get('generic_urls_per_run',5):][:50]
        report['top_new']=sorted(report['top_new'],key=lambda j:-j['score'])[:10]
        report['manual_review']=sum(j.get('queue')!='Confirmed' for j in records())
        report['state']='partial' if report['failures'] else 'success' if successful else 'failed'
    except Exception as e:
        logging.exception('Search failed');report['failures'].append(type(e).__name__+': '+str(e)[:180]);report['state']='failed'
    finally:
        if run_id:
            with connect() as c:c.execute('UPDATE runs SET finished=?,state=?,report=? WHERE id=?',(now(),report.get('state','failed'),json.dumps(report),run_id))
        LOCK.release()
    return report
def start_run():
    if not LOCK.acquire(False):return False
    threading.Thread(target=run_pipeline,daemon=True).start();return True
def schedule():
    while True:
        try:
            cfg=config();utc=dt.datetime.now(dt.timezone.utc)
            with connect() as c:last=c.execute('SELECT started FROM runs ORDER BY id DESC LIMIT 1').fetchone()
            if cfg['schedule_enabled'] and utc.hour>=cfg['schedule_hour_utc'] and (not last or last[0][:10]!=now()[:10]):start_run()
        except Exception:logging.exception('Scheduler')
        time.sleep(30)
def snapshot():
    cfg=config();jobs=records();stamp=dt.datetime.now(dt.timezone.utc)
    for j in jobs:
        previous_queue=j.get('queue');previous_application=j.get('application_verified')
        assess(j,cfg)
        if j.get('queue')=='Confirmed' and (previous_queue!='Confirmed' or not previous_application):j['queue']='Review'
        eligible,reason,area=location_eligibility(j,cfg)
        j.update(location_eligibility=eligible,location_reason=reason,area=area)
        j['review_blockers']=review_blockers(j)
        if eligible!='Eligible':j['queue']='Excluded' if eligible=='Rejected' else 'Location Review'
        if j.get('queue')=='Confirmed':
            verified=j.get('last_verified')
            if not verified or (stamp-dt.datetime.fromisoformat(verified)).total_seconds()>cfg['verification_valid_hours']*3600:j['queue']='Review';j['stale']=True
        j['match_label']='Excellent Match' if j.get('score',0)>=85 else 'Strong Match' if j.get('score',0)>=70 else 'Reasonable Match' if j.get('score',0)>=55 else 'Stretch Opportunity'
    with connect() as c:
        interests = {r['job_id']: dict(r) for r in c.execute('SELECT * FROM job_interests')}
        for job in jobs:
            job['interest'] = interests.get(job['id'])
        runs=[dict(r) for r in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 30')]
        for r in runs:r['report']=json.loads(r['report'])
    return prototype.enrich_snapshot(service(),{'jobs':jobs,'runs':runs,'statuses':STATUSES,'running':LOCK.locked(),'firecrawl_configured':False,'schedule_hour_utc':cfg['schedule_hour_utc']})
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
        self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        path=up.urlsplit(self.path).path
        if path=='/api/dashboard':return self.send(200,snapshot())
        if path=='/api/v1/health':return self.send(200,{'status':'ok','api_version':1})
        if path=='/api/v1/dashboard':return self.send(200,snapshot())
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
