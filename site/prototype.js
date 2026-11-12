// Workspace screens share the existing dashboard state and guarded save helper.
let workspaceView='jobs', preferencesDirty=false;
const lines=value=>value.split(/\n/).map(s=>s.trim()).filter(Boolean);
function openWorkspace(view){
 if(!discardCheck())return;
 if(preferencesDirty&&!confirm('Discard unsaved preferences?'))return;
 preferencesDirty=false;workspaceView=view;
 document.querySelectorAll('[data-workspace]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.workspace===view)));
 document.querySelectorAll('.workspace-panel').forEach(p=>p.hidden=p.id!==`workspace-${view}`);
 render();
}
function renderPrototype(){
 if(!state)return;
 const p=state.preferences;
 document.querySelectorAll('[data-workspace]').forEach(b=>b.onclick=()=>openWorkspace(b.dataset.workspace));
 if(!preferencesDirty){
  for(const key of ['profile','salary_floor','salary_policy','ai_model','ai_daily_limit','schedule_hour_utc'])document.querySelector(`[data-pref="${key}"]`).value=p[key];
  for(const key of ['categories','excluded_title_terms','additional_employer_urls'])document.querySelector(`[data-pref="${key}"]`).value=p[key].join('\n');
  for(const key of ['ai_enabled','schedule_enabled'])document.querySelector(`[data-pref="${key}"]`).checked=p[key];
  for(const platform of ['ashby','greenhouse','lever','smartrecruiters','personio'])document.querySelector(`[data-board="${platform}"]`).value=(p.additional_boards[platform]||[]).join('\n');
  document.querySelector('[data-pref="skill_groups"]').value=p.skill_groups.map(g=>`${g.label} | ${g.points} | ${g.terms.join(', ')}`).join('\n');
 }
 document.querySelectorAll('#preferences-form input,#preferences-form textarea,#preferences-form select').forEach(e=>e.oninput=()=>preferencesDirty=true);
 $('preferences-form').onsubmit=savePreferences;
 $('ai-state').textContent=`${state.ai_configured?'Server key configured':'Server key not configured'}. ${state.ai_attempts_today}/${p.ai_daily_limit} AI attempts today. AI runs only when you request a job review.`;
 const sources=state.sources;
 $('source-summary').textContent=`${sources.length} sources · ${sources.filter(s=>s.state==='ok').length} healthy at last check · ${sources.filter(s=>['error','manual review'].includes(s.state)).length} need attention. Employer websites may require manual review; coverage is not exhaustive.`;
 $('source-list').innerHTML=sources.map(s=>`<div class="source-row ${s.disabled?'disabled':''}"><div><h3>${esc(s.source)}</h3><span class="tag">${esc(s.disabled?'Paused':s.state)}</span><p>${esc(s.kind)} · ${s.count} postings returned at last attempt · ${esc(date(s.checked))}</p>${s.error?`<p class="source-error">${esc(s.error)}</p>`:''}</div><button class="btn secondary" data-source="${esc(s.source)}">${s.disabled?'Resume':'Pause'}</button></div>`).join('');
 document.querySelectorAll('[data-source]').forEach(b=>b.onclick=async()=>{
  if(preferencesDirty){notify('Save or discard your preference edits before changing sources.');return;}
  const source=b.dataset.source,disabled=new Set(p.disabled_sources);disabled.has(source)?disabled.delete(source):disabled.add(source);
  try{await post('/api/preferences',{revision:state.preferences_revision,preferences:{disabled_sources:[...disabled]}});await load();notify('Employer source updated.');}catch(e){notify(e.message);}
 });
 document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{
  if(!discardCheck())return;
  $('search').value='';$('category').value='';$('status').value='';$('queue').value='all';
  if(b.dataset.preset==='technical')$('search').value='support';
  if(b.dataset.preset==='implementation')$('search').value='implementation';
  if(b.dataset.preset==='followup'){activeBucket='all';$('search').value='';}
  followupOnly=b.dataset.preset==='followup';render();
 });
}
let followupOnly=false;
async function savePreferences(event){
 event.preventDefault();const p={};
 for(const key of ['profile','salary_policy','ai_model'])p[key]=document.querySelector(`[data-pref="${key}"]`).value;
 for(const key of ['salary_floor','ai_daily_limit','schedule_hour_utc'])p[key]=Number(document.querySelector(`[data-pref="${key}"]`).value);
 for(const key of ['categories','excluded_title_terms','additional_employer_urls'])p[key]=lines(document.querySelector(`[data-pref="${key}"]`).value);
 for(const key of ['ai_enabled','schedule_enabled'])p[key]=document.querySelector(`[data-pref="${key}"]`).checked;
 p.additional_boards={};for(const platform of ['ashby','greenhouse','lever','smartrecruiters','personio'])p.additional_boards[platform]=lines(document.querySelector(`[data-board="${platform}"]`).value);
 p.skill_groups=lines(document.querySelector('[data-pref="skill_groups"]').value).map(line=>{const [label,weight,terms]=line.split('|');return {label:label?.trim(),points:Number(weight),terms:(terms||'').split(',').map(t=>t.trim()).filter(Boolean)};});
 const button=$('save-preferences');button.disabled=true;
 try{await post('/api/preferences',{revision:state.preferences_revision,preferences:p});preferencesDirty=false;await load();$('preferences-message').textContent='Preferences saved. Matching updates now; run a search to discover more jobs.';}catch(e){$('preferences-message').textContent=e.message;}finally{button.disabled=false;}
}
function aiPanel(j){
 const saved=j.ai_advice,advice=saved?.advice;
 return `<details class="ai-panel"><summary>AI career review ${saved?(saved.stale?'· refresh needed':'· saved'):''}</summary><p class="hint">Sends your profile and this posting to OpenAI. Advice is separate from employer verification and your approval.</p>${saved?`<p class="why">${esc(advice.summary)}</p>${['strengths','gaps','questions','next_steps'].map(key=>`<strong>${esc(key.replace('_',' '))}</strong><ul>${advice[key].map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`).join('')}<p class="hint">${esc(saved.model)} · ${esc(date(saved.created))}${saved.stale?' · Posting or preferences changed; review may be outdated.':''}</p>`:''}<button class="btn secondary ai-review" ${!state.ai_configured||!state.preferences.ai_enabled?'disabled':''}>${saved&&!saved.stale?'Load saved AI review':'Request AI review'}</button><div class="ai-message" role="status"></div></details>`;
}
function bindAI(){document.querySelectorAll('article .ai-review').forEach(button=>button.onclick=async()=>{
 if(!discardCheck()||preferencesDirty)return;
 const card=button.closest('article');button.disabled=true;card.querySelector('.ai-message').textContent='Reviewing…';
 try{await post(`/api/jobs/${card.dataset.id}/ai-review`,{});await load();const panel=document.querySelector(`article[data-id="${card.dataset.id}"] .ai-panel`);if(panel)panel.open=true;}catch(e){card.querySelector('.ai-message').textContent=e.message;button.disabled=false;}
});}
