// Read-only smoke test: no reviews, preferences, applications or searches are changed.
const playwright=require('playwright');
const assert=require('node:assert/strict'),path=require('node:path');
(async()=>{const browser=await playwright.chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});try{
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.JOBS_URL||'http://localhost:8084');await page.locator('#buckets button').first().waitFor();
 assert.equal(await page.locator('#bucket-title').innerText(),'Review Inbox');assert.equal(await page.locator('#buckets button').count(),8);
 const d=await page.evaluate(async()=>await(await fetch('/api/v1/dashboard')).json());assert.equal(d.api_version,1);
 const visible=await page.locator('article').evaluateAll(cards=>cards.map(c=>+c.dataset.id));assert.ok(visible.every(id=>d.jobs.find(j=>j.id===id).location_eligibility!=='Rejected'));
 for(const bucket of ['ready','applied','interviews','offers','hold','archive','all','review'])await page.locator(`[data-bucket="${bucket}"]`).click();
 for(const view of ['jobs','sources','preferences','guide']){await page.locator(`[data-workspace="${view}"]`).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,view+' overflow');}
 await page.locator('[data-workspace="jobs"]').click();await page.screenshot({path:path.join(__dirname,'tmp/prototype-live-mobile.png'),fullPage:true});assert.deepEqual(errors,[]);
 console.log(JSON.stringify({api:1,jobs:d.jobs.length,reviewVisible:visible.length,buckets:8,workspaceScreens:4,mobileOverflow:false,errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
