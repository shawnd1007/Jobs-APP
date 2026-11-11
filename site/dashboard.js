const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=s=>s?new Date(s).toLocaleString():'Never';
const option=(v,label=v)=>`<option value="${esc(v)}">${esc(label)}</option>`;
const unapplied=['Not Applied','Planning to Apply','Needs Verification'];
const bucketInfo={review:['Review Inbox','Check details and decide what moves forward.'],ready:['Ready to Apply','Approved by you; no application recorded yet.'],applied:['Applied','Submitted applications and assessments.'],interviews:['Interviews','Scheduled or completed interviews.'],offers:['Offers','Offers received.'],hold:['On Hold','Waiting for more information or a later decision.'],archive:['Closed / Dismissed','Closed, rejected, withdrawn or dismissed jobs.'],all:['All History','Every record, including out-of-area jobs.']};
let state,activeBucket=bucketInfo[location.hash.slice(1)]?location.hash.slice(1):'review';
const drafts=new Set();
function bucket(j){
 if(j.availability==='Closed'||['Rejected','Withdrawn','Position Closed'].includes(j.status))return 'archive';
 if(j.status==='Offer Received')return 'offers';
 if(j.status.startsWith('Interview'))return 'interviews';
 if(['Applied','Assessment Received'].includes(j.status))return 'applied';
 if(j.review_decision==='Dismissed')return 'archive';
 if(j.location_eligibility==='Rejected'||j.queue==='Excluded')return 'excluded';
 if(j.review_decision==='Hold')return 'hold';
 if(j.review_decision==='Approved'&&unapplied.includes(j.status)&&!j.review_blockers.length)return 'ready';
 return 'review';
}
function notify(message){$('notice').textContent=message;}
function discardCheck(){if(drafts.size&&!confirm('Discard unsaved changes?'))return false;drafts.clear();return true;}
async function load(){const r=await fetch('/api/dashboard');if(!r.ok)throw Error('Could not load the shared job database.');state=await r.json();render();}
function selectBucket(key){if(!discardCheck())return;followupOnly=false;activeBucket=key;history.replaceState(null,'','#'+key);document.querySelectorAll('.controls input').forEach(e=>e.value='');document.querySelectorAll('.controls select').forEach(e=>e.selectedIndex=0);render();$('bucket-title').scrollIntoView({behavior:'smooth',block:'start'});}
function fillSelect(id,values,label){const old=$(id).value;$(id).innerHTML=option('',label)+values.map(v=>option(v)).join('');if([...$(id).options].some(o=>o.value===old))$(id).value=old;}
function render(){
 renderPrototype();const jobs=state.jobs,counts={};for(const key of Object.keys(bucketInfo))counts[key]=key==='all'?jobs.length:jobs.filter(j=>bucket(j)===key).length;
 $('buckets').innerHTML=Object.entries(bucketInfo).map(([key,[label]])=>`<button type="button" data-bucket="${key}" class="bucket ${activeBucket===key?'selected':''}" aria-pressed="${activeBucket===key}"><strong>${counts[key]}</strong><span>${esc(label)}</span></button>`).join('');
 $('buckets').querySelectorAll('button').forEach(b=>b.onclick=()=>selectBucket(b.dataset.bucket));
 $('bucket-title').textContent=bucketInfo[activeBucket][0];$('bucket-description').textContent=bucketInfo[activeBucket][1];
 $('summary').innerHTML=`<span class="tag">${jobs.length} historical jobs</span> <span class="tag">${jobs.filter(j=>j.queue==='Confirmed').length} employer-verified openings</span> <span class="tag">${counts.ready} approved and not applied</span>`;
 $('system').textContent=`Daily search: ${state.preferences.schedule_enabled?state.schedule_hour_utc+':00 UTC':'paused'}. ${state.firecrawl_configured?'Firecrawl configured':'Public board mode'}. Last fully successful run: ${date(state.runs.find(r=>r.state==='success')?.finished)}. ${state.running?'Search running…':''}`;
 $('run').disabled=state.running;
 fillSelect('status',state.statuses,'All application statuses');fillSelect('company',[...new Set(jobs.map(j=>j.employer))].sort(),'All companies');fillSelect('category',[...new Set(jobs.map(j=>j.category||'Imported'))].sort(),'All categories');
 $('reports').innerHTML=state.runs.map(r=>`<details><summary>${esc(date(r.started))} — ${esc(r.state)}: ${r.report.new_qualified||0} qualified new, ${r.report.new_review||0} review leads</summary><pre>${esc(JSON.stringify(r.report,null,2))}</pre>${(r.report.top_new||[]).map(j=>`<p><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${esc(j.employer+' — '+j.title)}</a></p>`).join('')}</details>`).join('')||'No search reports yet.';
 filter();
}
function reviewReasons(j){
 const reasons=[];
 if(j.location_eligibility!=='Eligible')reasons.push(j.location_reason||'Confirm Florida/Georgia remote eligibility or an approved local office.');
 if(!(j.salary_currency==='USD'&&j.salary_period==='year'&&j.salary_type==='base'&&j.salary_max))reasons.push('Base salary has not been independently confirmed.');
 if(j.queue!=='Confirmed')reasons.push(j.application_evidence||'Some employer or application checks are incomplete.');
 if(j.history_confirmation||j.status==='Needs Verification')reasons.push('Confirm whether this specific job has already been applied to.');
 return reasons;
}
function reviewPanel(j){
 const checks=j.review_checks||{},isOpen=false,blocked=j.review_blockers||[];
 return `<details class="review-panel" ${isOpen?'open':''}><summary>Review & approval · ${esc(j.review_decision)}</summary><div class="review-reasons"><strong>What to check</strong><ul>${reviewReasons(j).map(s=>`<li>${esc(s)}</li>`).join('')||'<li>Employer checks passed. Confirm fit and application history before approving.</li>'}</ul></div><p class="why">Read the employer posting and the match/gaps above. Your approval is saved separately from automatic verification.</p>${[
 ['location','I checked: remote work is eligible for FL/GA, or the office is in Jacksonville / the Buford area.'],['salary','I checked: the published base salary meets my saved salary policy; bonuses and OTE do not count.'],['application','I checked: this exact employer job is open and has an application available.'],['history','I checked: we have not already applied to this specific job.']
 ].map(([key,label])=>`<label class="check"><input type="checkbox" name="check_${key}" ${checks[key]?'checked':''}><span>${esc(label)}</span></label>`).join('')}<label>Reviewed by (optional)<input name="reviewer" maxlength="120" value="${esc(j.review_reviewer)}" placeholder="Your name"></label><label>Review notes <span class="hint">Explain any missing pay, location or application information you confirmed.</span><textarea name="review_note" placeholder="What I checked, remaining questions, or why this should be held or dismissed…">${esc(j.review_note)}</textarea></label>${blocked.length?`<p class="blocked">Approval blocked: ${esc(blocked.join(' '))}</p>`:''}<div class="decision-buttons"><button class="btn approve" data-decision="Approved" ${blocked.length?'disabled':''}>Approve for application</button><button class="btn secondary" data-decision="Hold">Hold / need information</button><button class="btn dismiss" data-decision="Dismissed">Dismiss</button>${j.review_decision!=='Pending'?'<button class="btn secondary" data-decision="Pending">Send back to review</button>':''}</div><p class="hint">Approval moves an unapplied job to Ready to Apply. It does not submit an application.</p>${j.review_updated?`<p class="hint">Last review: ${esc(date(j.review_updated))}${j.review_reviewer?' · '+esc(j.review_reviewer):''}</p>`:''}<div class="review-message" role="status"></div></details>`;
}
function trackingPanel(j){return `<details class="tracking-panel"><summary>Application tracking · ${esc(j.status)}</summary><label>Application status<select name="status">${state.statuses.map(s=>`<option ${s===j.status?'selected':''}>${esc(s)}</option>`).join('')}</select></label><label>Application date<input name="application_date" type="date" value="${esc(j.application_date)}"></label><label>Follow-up date<input name="follow_up" type="date" value="${esc(j.follow_up)}"></label><label>Application notes<textarea name="notes">${esc(j.notes)}</textarea></label><button class="btn save">Save tracking</button><div class="saved" role="status"></div></details>`;}
function filter(){
 const text=$('search').value.toLowerCase(),queue=$('queue').value;
 let list=state.jobs.filter(j=>(!followupOnly||(j.follow_up&&j.follow_up<=new Date().toLocaleDateString('en-CA')&&!['Rejected','Withdrawn','Position Closed'].includes(j.status)))&&(activeBucket==='all'||bucket(j)===activeBucket)&&(!text||[j.employer,j.title,j.description,j.notes,j.review_note].join(' ').toLowerCase().includes(text))&&(!$('status').value||j.status===$('status').value)&&(!$('company').value||j.employer===$('company').value)&&(!$('category').value||(j.category||'Imported')===$('category').value)&&(!$('area').value||j.area===$('area').value)&&(!$('score').value||j.score>=+$('score').value)&&(!$('salary').value||(j.salary_max||0)>=+$('salary').value)&&(!$('posted').value||(j.posted||'').slice(0,10)>=$('posted').value)&&(!$('verified').value||(j.last_verified||'').slice(0,10)>=$('verified').value)&&(queue==='all'||j.queue===queue));
 const sort=$('sort').value;list.sort((a,b)=>sort==='score'?b.score-a.score:sort==='salary'?(b.salary_max||0)-(a.salary_max||0):sort==='status'?a.status.localeCompare(b.status):String(b[sort]||'').localeCompare(String(a[sort]||''))||b.id-a.id);
 $('count').textContent=`${list.length} jobs in this view · ${state.jobs.length} retained in history. Human approval and employer verification are separate.`;
 $('jobs').innerHTML=list.map(j=>`<article data-id="${j.id}"><div class="top"><span class="tag">${esc(j.match_label)} · ${j.score}/100</span><em>#${j.id}</em></div><div class="company">${esc(j.employer)}</div><h2>${esc(j.title)}</h2><div class="salary">${esc(j.salary_text||'Salary Not Published')}</div><em>${esc(j.location)}</em><div class="note">${esc(j.location_reason)}</div><div class="badges"><span class="tag decision-${esc(j.review_decision.toLowerCase())}">${esc(j.review_decision==='Approved'?'Approved by you':j.review_decision==='Pending'?'Awaiting review':j.review_decision)}</span><span class="tag">${esc(j.status)}</span><span class="tag">${j.queue==='Confirmed'?'Employer verified':'Automatic checks incomplete'}</span>${j.availability==='Closed'?'<span class="tag">Closed</span>':''}</div><div class="why">${esc(j.explanation)}</div><details><summary>Employer description & verification</summary><p class="why">${esc(j.description)}</p><p class="note">${esc(j.application_evidence||'Not independently verified')}<br>Source: ${esc(j.source)}<br>Verified: ${esc(date(j.last_verified))}<br>Posted: ${esc(j.posted||'Unknown')}<br>Tracking updated: ${esc(date(j.tracking_updated))}</p></details><div class="actions"><a class="btn employer-link" href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">Open employer posting ↗</a>${unapplied.includes(j.status)?`<button class="btn secondary mark-applied">${bucket(j)==='ready'?'Mark as applied':'Already applied'}</button>`:''}</div>${aiPanel(j)}${reviewPanel(j)}${trackingPanel(j)}</article>`).join('')||`<div class="empty"><h2>No jobs in this bucket yet</h2><p>${activeBucket==='ready'?'Approve a job in Review Inbox to move it here.':activeBucket==='applied'?'Mark a job as applied to move it here.':'Try another bucket or clear your filters.'}</p></div>`;
 bindCards();bindAI();
}
async function post(url,payload){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Jobs-Client':'dashboard'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw Error(data.error||'Could not save');return data;}
function allowSave(key){return ![...drafts].some(k=>k!==key)||confirm('Other unsaved edits will be discarded after saving this decision. Continue?');}
function bindCards(){document.querySelectorAll('article').forEach(card=>{
 const j=state.jobs.find(j=>j.id===+card.dataset.id),review=card.querySelector('.review-panel'),tracking=card.querySelector('.tracking-panel');
 review.querySelectorAll('input,textarea').forEach(e=>e.oninput=()=>drafts.add(j.id+':review'));
 tracking.querySelectorAll('input,textarea,select').forEach(e=>e.oninput=()=>{drafts.add(j.id+':tracking');tracking.querySelector('.saved').textContent='Unsaved changes';});
 review.querySelectorAll('[data-decision]').forEach(button=>button.onclick=async()=>{
  if(!allowSave(j.id+':review'))return;
  const payload={decision:button.dataset.decision,version:j.review_version,tracking_version:j.version,note:review.querySelector('[name="review_note"]').value,reviewer:review.querySelector('[name="reviewer"]').value,checks:{}};
  for(const key of ['location','salary','application','history'])payload.checks[key]=review.querySelector(`[name="check_${key}"]`).checked;
  button.disabled=true;
  try{await post(`/api/jobs/${j.id}/review`,payload);drafts.clear();await load();notify(payload.decision==='Approved'?'Approved — moved to Ready to Apply.':payload.decision==='Hold'?'Moved to On Hold.':payload.decision==='Dismissed'?'Dismissed — retained in Closed / Dismissed.':'Moved back to Review Inbox.');}catch(e){review.querySelector('.review-message').textContent=e.message;button.disabled=false;}
 });
 async function saveTracking(markApplied=false){
  if(!allowSave(j.id+':tracking'))return;
  const payload={version:j.version};for(const key of ['status','application_date','follow_up','notes'])payload[key]=tracking.querySelector(`[name="${key}"]`).value;
  if(markApplied)payload.status='Applied';
  try{await post(`/api/jobs/${j.id}/tracking`,payload);drafts.clear();await load();notify(markApplied?'Moved to Applied. Set the application date in tracking if you know it.':'Tracking saved for all devices.');}catch(e){tracking.open=true;tracking.querySelector('.saved').textContent=e.message;}
 }
 tracking.querySelector('.save').onclick=()=>saveTracking();
 const quick=card.querySelector('.mark-applied');if(quick)quick.onclick=()=>saveTracking(true);
 });}
document.querySelectorAll('.controls input,.controls select').forEach(e=>e.oninput=()=>{if(discardCheck())filter();});
$('run').onclick=async()=>{try{await post('/api/run',{});state.running=true;$('run').disabled=true;notify('Search started. Review decisions and application tracking are preserved.');}catch(e){notify(e.message);}};
$('refresh').onclick=()=>{if(discardCheck())load().catch(e=>notify(e.message));};
window.onbeforeunload=e=>{if(drafts.size||preferencesDirty){e.preventDefault();e.returnValue='';}};
setInterval(()=>{if(!drafts.size&&!preferencesDirty&&state?.running)load().catch(()=>{});},15000);
load().catch(e=>notify(e.message));
