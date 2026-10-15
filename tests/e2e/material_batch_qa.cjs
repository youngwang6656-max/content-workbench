const assert=require('node:assert/strict');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/batch-read'))calls.push(r.url())});
try{
 await page.goto('http://127.0.0.1:8880/');await page.locator('[data-page="materials"]').click();await page.locator('#material-drop').waitFor();
 const session=await (await page.request.get('http://127.0.0.1:8880/api/session')).json();const projects=await (await page.request.get('http://127.0.0.1:8880/api/projects')).json();const project=projects[0].id;const headers={'X-Waypoint-Token':session.token};
 const add=async(name,text,scope=project)=>{const response=await page.request.post('http://127.0.0.1:8880/api/materials',{headers,data:{project_id:scope,name,text}});assert.equal(response.status(),200);return response.json()};
 const first=await add('Batch first','First source'),bad=await add('Batch incomplete','Missing unit'),last=await add('Batch last','Last source');
 await page.locator('[data-page="materials"]').click();
 for(const item of [first,bad,last])await page.locator(`[data-select-material="${item.id}"]`).check();
 assert.equal(await page.locator('#material-selection-count').innerText(),'已选 3 份');assert.equal(await page.locator('#material-select-all').evaluate(x=>x.indeterminate),true);
 await page.locator('#batch-read-materials').click();await page.getByRole('button',{name:'开始本批 AI 精读',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#batch-reading-summary')?.textContent.includes('AI 精读 2 / 3 份完成 · 1 份资料待核对'));assert.equal(calls.length,3);
 const saved=await (await page.request.get(`http://127.0.0.1:8880/api/materials?project_id=${project}`)).json();
 for(const item of [first,last]){const m=saved.find(x=>x.id===item.id);assert.equal(m.adopted_analysis_ids.length,1);assert.equal(m.trust,'unverified');assert.equal(m.text,item.text)}
 assert.equal(saved.find(x=>x.id===bad.id).analysis_history.length,1);assert.equal(saved.find(x=>x.id===bad.id).adopted_analysis_ids?.length||0,0);
 // The primary action for one long material must continue through every segment.
 await page.getByRole('button',{name:'返回资料页',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#dialog')?.open);
 const long=await add('Full long reading','x'.repeat(12000*10));await page.locator('[data-page="materials"]').click();await page.locator(`[data-material="${long.id}"]`).waitFor();
 await page.locator(`[data-material="${long.id}"] [data-read-material]`).click();
 await page.getByRole('heading',{name:'AI 全文精读',exact:true}).waitFor();
 assert.match(await page.locator('#dialog').innerText(),/AI 全文精读/);
 await page.getByRole('button',{name:'开始 AI 精读',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#batch-reading-start')?.hidden===true);
 assert.match(await page.locator('#batch-reading-results').innerText(),/10 \/ 10 页\/段/);
 const full=(await (await page.request.get(`http://127.0.0.1:8880/api/materials?project_id=${project}`)).json()).find(x=>x.id===long.id);
 assert.equal(full.analysis_history.length,4);assert.equal(full.adopted_analysis_ids.length,4);
 await page.getByRole('button',{name:'返回资料页',exact:true}).click();
 await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v092_batch_read.png',fullPage:true});
 // Resume selected complete sources without making further generation calls.
 for(const item of [first,last])await page.locator(`[data-select-material="${item.id}"]`).check();await page.locator('#batch-read-materials').click();await page.getByRole('button',{name:'开始本批 AI 精读',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#batch-reading-start')?.hidden===true);await page.getByRole('button',{name:'返回资料页',exact:true}).click();
 // Pause after the in-flight step; the next source must not begin.
 const pause1=await add('Pause first','p1'),pause2=await add('Pause second','p2');await page.locator('[data-page="materials"]').click();
 for(const item of [pause1,pause2])await page.locator(`[data-select-material="${item.id}"]`).check();await page.locator('#batch-read-materials').click();
 await page.route('**/api/materials/*/batch-read',async route=>{const response=await route.fetch();await new Promise(resolve=>setTimeout(resolve,500));await route.fulfill({response})});
 const before=calls.length;await page.getByRole('button',{name:'开始本批 AI 精读',exact:true}).click();await page.getByRole('button',{name:'暂停',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#batch-reading-summary')?.textContent.includes('已暂停'));assert.equal(calls.length,before+1);await page.unroute('**/api/materials/*/batch-read');await page.getByRole('button',{name:'继续 AI 精读',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#batch-reading-start')?.hidden===true);await page.getByRole('button',{name:'返回资料页',exact:true}).click();
 // Drag upload creates the same multi-file queue and preserves the brand scope.
 await page.locator('#material-drop').evaluate(zone=>{const transfer=new DataTransfer();for(const name of ['drag-one.txt','drag-two.md'])transfer.items.add(new File(['Drag source'],name,{type:'text/plain'}));for(const type of ['dragenter','dragover','drop'])zone.dispatchEvent(new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:transfer}))});
 assert.equal(await page.locator('#upload-results .upload-result').count(),2);await page.getByRole('button',{name:'导入所选文件',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#upload-summary')?.textContent.includes('2 个成功，0 个未导入'));await page.getByRole('button',{name:'查看已导入资料',exact:true}).click();
 let brand=await (await page.request.get(`http://127.0.0.1:8880/api/materials?project_id=${project}`)).json();const drag=brand.filter(x=>x.name.startsWith('drag-'));assert.equal(drag.length,2);
 for(const item of drag)await page.locator(`[data-select-material="${item.id}"]`).check();await page.locator('#batch-archive-materials').click();await page.locator('#dialog').getByRole('button',{name:'归档所选资料',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#dialog').open);
 brand=await (await page.request.get(`http://127.0.0.1:8880/api/materials?project_id=${project}`)).json();for(const item of drag){const m=brand.find(x=>x.id===item.id);assert.equal(m.archived,true);assert.equal(m.path,item.path);assert.equal((await page.request.get(`http://127.0.0.1:8880/api/materials/${m.id}/file`)).status(),200)}
 // Global drag upload and batch actions are isolated from brand records.
 await page.locator('[data-page="global-materials"]').click();await page.getByRole('heading',{name:'全局规则与资料',exact:true}).waitFor();await page.locator('#material-drop').evaluate(zone=>{const transfer=new DataTransfer();transfer.items.add(new File(['Shared source'],'drag-global.txt',{type:'text/plain'}));zone.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}))});await page.getByRole('button',{name:'导入所选文件',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#upload-summary')?.textContent.includes('1 个成功，0 个未导入'));await page.getByRole('button',{name:'查看已导入资料',exact:true}).click();
 let globalRows=await (await page.request.get('http://127.0.0.1:8880/api/materials')).json();const global=globalRows.find(x=>x.name==='drag-global.txt');assert.equal(global.project_id,null);await page.locator(`[data-select-material="${global.id}"]`).check();await page.locator('#batch-read-materials').click();await page.getByRole('button',{name:'开始 AI 精读',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#batch-reading-start')?.hidden===true);await page.getByRole('button',{name:'返回资料页',exact:true}).click();await page.locator('#material-select-all').check();assert.equal(await page.locator('#material-selection-count').innerText(),`已选 ${globalRows.length} 份`);await page.locator('#material-select-all').uncheck();assert.equal(await page.locator('#batch-archive-materials').isDisabled(),true);
 await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v092_global_drop.png',fullPage:true});assert.deepEqual(errors,[]);console.log('PASS: scoped batch reading/adoption, incomplete result retained, complete ranges reused, pause/resume, drag multi-upload brand/global, archive keeps downloadable originals. Synthetic models only.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
