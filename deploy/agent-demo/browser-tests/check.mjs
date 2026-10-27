// Real local HTTP/UI checks. No model requests, no user browser profile.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../..');
const require=createRequire(import.meta.url);
const {chromium,request}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const passwords=JSON.parse(fs.readFileSync(path.join(root,'.agent-demo/users.json'),'utf8'));
const api=await request.newContext({baseURL:'http://127.0.0.1:18927'});
const login=await api.post('/api/auth/login/',{data:{email:'agent-eval-administrator',password:passwords.administrator}});
assert.equal(login.status(),200);
const session=await login.json();
const headers={Authorization:`Bearer ${session.accessToken}`};
const control=async(action,caseId)=>{
 const response=await api.post('/api/assistant/demo/session/',{headers,data:{action,...(caseId?{caseId}:{})}});
 assert.equal(response.status(),200);return response.json();
};
const state=async()=>{const response=await api.get('/api/assistant/demo/session/',{headers});return (await response.json()).session;};
await control('reset','INS-01');await control('start');
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1100}});
await context.addInitScript(({token,user})=>{
 sessionStorage.setItem('ut-django-token',token);sessionStorage.setItem('ut-vue-user',JSON.stringify(user));sessionStorage.setItem('ut-session-mode','api');
},{token:session.accessToken,user:session.user});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
try {
 await page.goto('http://127.0.0.1:5187/agent-workbench');
 await page.getByRole('heading',{name:'多Agent工作台'}).waitFor();
 await page.getByRole('button',{name:'重置场景'}).waitFor();
 assert.match(await page.locator('.source').innerText(),/模拟测试/);
 await page.getByRole('button',{name:'计算模拟情景'}).click();
 await page.locator('dl').waitFor();
 assert.match(await page.locator('dl').innerText(),/工时当量/);
 await page.getByRole('button',{name:'检索依据'}).click();
 await page.getByText('检索方式：',{exact:false}).waitFor({timeout:65000});
 fs.mkdirSync(path.join(root,'.agent-demo/browser'),{recursive:true});
 await page.screenshot({path:path.join(root,'.agent-demo/browser/desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.waitForTimeout(400); // wait for the shell's 280ms sidebar transition
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 assert.ok(await page.locator('.agent-workbench').evaluate(e=>{const b=e.getBoundingClientRect();return b.left>=0 && b.right<=innerWidth+1;}));
 await page.screenshot({path:path.join(root,'.agent-demo/browser/mobile.png'),fullPage:true});
 await control('pause');const before=await state();
 await new Promise(resolve=>setTimeout(resolve,65000));
 const paused=await state();assert.equal(paused.tick,before.tick);assert.equal(paused.lastTickAt,before.lastTickAt);
 await control('start');await new Promise(resolve=>setTimeout(resolve,2600));
 const resumed=await state();assert.ok(resumed.tick>paused.tick);assert.ok(resumed.lastTickAt>paused.lastTickAt);
 for(let i=0;i<3;i++) await control('advance');
 await new Promise(resolve=>setTimeout(resolve,2600));
 const recovered=await state();assert.equal(recovered.phase,3);
 const runs=await api.get('/api/assistant/runs/',{headers});assert.equal(runs.status(),200);
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(root,'.agent-demo/browser/result.json'),JSON.stringify({status:'passed',modelCalls:0,
   source:'SIMULATED_TEST',desktop:true,mobile:true,noHorizontalOverflow:true,pauseSeconds:65,
   pausePreservedOldTimestamp:true,resumeProducedNewObservation:true,phaseAdvance:true,pageErrors:errors},null,2));
 console.log('Local browser checks passed; no model or hardware calls.');
} finally {await control('pause');await browser.close();await api.dispose();}
