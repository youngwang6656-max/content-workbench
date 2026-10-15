const assert=require('node:assert/strict'),{chromium}=require('playwright'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.emulateMedia({colorScheme:'dark'});await page.goto('http://127.0.0.1:8881');
  await page.locator('[data-brand-kind="comment"]').click();await page.locator('#sidebar-new-task').click();
  assert.equal(await page.locator('#source-mode option').count(),5);
  await page.locator('#source-mode').selectOption('search');await page.locator('#search-days').fill('0');await page.locator('#search-count').selectOption('5');await page.locator('#load-source').click();
  await page.locator('[data-pick-source]').waitFor();assert((await page.locator('#source-status').textContent()).includes('1 / 5'));
  assert((await page.locator('#source-results').textContent()).includes('推荐程度：高'));
  await page.screenshot({path:path.resolve(__dirname,'../../../acceptance/v070_search_candidates.png'),fullPage:true});
  await page.locator('[data-pick-source]').click();assert.equal(await page.locator('#save-comment').isDisabled(),true);
  await page.locator('#source-reading button').click();await page.locator('#source-reading .draft').waitFor();
  assert((await page.locator('#source-text').inputValue()).startsWith('I need'));
  await page.locator('#source-confirmed').check();await page.locator('[name="name"]').fill('搜索原帖评论');await page.locator('[name="raw_input"]').fill('先问清停车时长');
  await page.screenshot({path:path.resolve(__dirname,'../../../acceptance/v070_source_translation.png'),fullPage:true});
  await page.locator('#save-comment').click();await page.getByRole('heading',{name:'评论围绕的原帖'}).waitFor();
  await page.locator('#change-comment-source').click();await page.locator('#source-mode').selectOption('project');
  const value=await page.locator('#source-revision option').nth(1).getAttribute('value');await page.locator('#source-revision').selectOption(value);await page.locator('#load-source').click();await page.locator('#source-preview').waitFor();
  assert.equal(await page.locator('#source-text').getAttribute('readonly'),'');await page.locator('#source-confirmed').check();await page.locator('#save-comment').click();
  await page.locator('#quick-reading').click();await page.locator('#reading-input').fill('An English draft before final delivery.');await page.locator('#reading-tool button').click();await page.locator('#reading-tool .draft').waitFor();await page.locator('#dialog .close').click();
  // Text and screenshot paths use the same source-confirmation gate.
  await page.locator('#change-comment-source').click();await page.locator('#source-mode').selectOption('text');await page.locator('#source-paste').fill('What should I consider before buying?');await page.locator('#load-source').click();await page.locator('#source-preview').waitFor();
  await page.locator('#source-reading button').click();await page.locator('#source-reading .draft').waitFor();await page.locator('#source-text').fill('Edited original text.');assert.equal(await page.locator('#source-reading .reading-result').isVisible(),false);
  await page.locator('#source-mode').selectOption('link');await page.locator('#source-url').fill('https://www.reddit.com/r/dashcams/comments/abc123/parking/');await page.locator('#load-source').click();await page.locator('#source-preview').waitFor();assert((await page.locator('#source-meta').textContent()).includes('摘录'));
  await page.locator('#source-mode').selectOption('screenshot');await page.locator('#source-file').setInputFiles(path.resolve(__dirname,'../../../acceptance/v070_search_candidates.png'));await page.locator('#load-source').click();await page.locator('#source-preview').waitFor();assert.equal(await page.locator('.source-image').count(),1);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,paths:5,days:0,requested:5,returned:1,translationBeforeDraft:true,model:'simulated'}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
