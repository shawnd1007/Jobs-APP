// Read/write checks target a temporary QA database, never real applications.
const playwright=require('playwright');
const {spawn}=require('node:child_process'),assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const server=spawn(process.env.PYTHON||'python',[path.join(__dirname,'review-test-server.py')],{cwd:__dirname,windowsHide:true});let browser;
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('QA startup timed out')),15000);server.stdout.on('data',d=>{if(d.toString().includes('QA_READY')){clearTimeout(timer);resolve();}});server.stderr.on('data',d=>process.stderr.write(d));server.once('exit',c=>{if(c)reject(Error('QA exited '+c));});});
  browser=await playwright.chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18084');await page.locator('article').first().waitFor();
  assert.equal(await page.locator('.review-panel[open]').count(),0);
  await page.screenshot({path:path.join(__dirname,'tmp/prototype-desktop.png'),fullPage:true});
  await page.locator('[data-workspace="preferences"]').click();
  await page.locator('[data-pref="salary_floor"]').fill('82000');
  await page.locator('[data-board="ashby"]').fill('deepgram');
  await page.locator('[data-board="smartrecruiters"]').fill('qa-fictional');
  await page.locator('#save-preferences').click();await page.locator('#preferences-message').filter({hasText:'Preferences saved'}).waitFor();
  await page.reload();await page.locator('article').first().waitFor();await page.locator('[data-workspace="preferences"]').click();
  assert.equal(await page.locator('[data-pref="salary_floor"]').inputValue(),'82000');
  assert.equal(await page.locator('[data-board="ashby"]').inputValue(),'deepgram');
  assert.equal(await page.locator('[data-board="smartrecruiters"]').inputValue(),'qa-fictional');
  await page.locator('[data-workspace="sources"]').click();
  const source=page.locator('.source-row').filter({has:page.locator('h3',{hasText:'ashby/deepgram'})});
  await source.locator('button').click();await source.locator('button',{hasText:'Resume'}).waitFor();
  await source.locator('button').click();await source.locator('button',{hasText:'Pause'}).waitFor();
  await page.setViewportSize({width:390,height:844});
  for(const view of ['jobs','preferences','sources','guide']){
   await page.locator(`[data-workspace="${view}"]`).click();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,view+' overflow');
   await page.screenshot({path:path.join(__dirname,`tmp/prototype-mobile-${view}.png`),fullPage:true});
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({preferencesPersist:true,sourcePauseResume:true,compactReviews:true,allFourMobileScreens:true,errors}));
 }finally{if(browser)await browser.close();try{await fetch('http://127.0.0.1:18084/qa-stop',{method:'POST'});}catch{}setTimeout(()=>server.kill(),1000).unref();}
})().catch(e=>{console.error(e);process.exitCode=1;});
