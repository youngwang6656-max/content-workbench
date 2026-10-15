const assert=require('node:assert/strict');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto('http://127.0.0.1:8880/');await page.locator('[data-task]').first().click();await page.locator('#live-state .attention-label').waitFor();
 assert.match(await page.locator('#live-state').innerText(),/待你处理/);
 assert.match(await page.locator('#live-state .status-link').evaluate(x=>getComputedStyle(x).textDecorationLine),/underline/);
 await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v090_attention.png',fullPage:true});
 await page.emulateMedia({colorScheme:'dark'});await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v090_attention_dark.png',fullPage:true});await page.locator('#live-state .status-link').click();await page.locator('.material-focused').waitFor();assert.match(await page.locator('h1').innerText(),/全局/);
 await page.locator('[data-page="materials"]').click();await page.locator('[data-review-material]').first().click();
 await page.locator('#dialog [name="include_images"]').uncheck();await page.getByRole('button',{name:'读取并分析所选范围',exact:true}).click();
 await page.locator('[data-use-analysis]').waitFor();assert.match(await page.locator('#material-analyses').innerText(),/reader/);
 await page.locator('[data-use-analysis]').click();await page.waitForFunction(()=>document.querySelector('#dialog[open] #material-analyses .badge')?.textContent==='已采纳');
 await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v090_reading.png',fullPage:true});
 await page.locator('#dialog .close').click();await page.locator('[data-supplement]').first().click();await page.locator('#dialog [name="text"]').fill('补充：42 克是净重。');await page.getByRole('button',{name:'保存补充文字',exact:true}).click();
 await page.locator('[data-review-material]').first().click();await page.locator('#material-analyses').waitFor();assert.match(await page.locator('#material-analyses').innerText(),/依据已变化/);
 await page.locator('#dialog .close').click();await page.getByRole('button',{name:'设置与用量',exact:true}).click();await page.locator('[data-edit-usage]').first().click();
 assert.equal(await page.locator('#dialog [name="plus_read"]').count(),1);assert.equal(await page.locator('#dialog [name="plus_read"]').inputValue(),'reader');
 assert.deepEqual(errors,[]);console.log('PASS: highlighted status, underlined exact material jump, analysis/adoption/source-change history, independent read-model setting. Synthetic model only.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
