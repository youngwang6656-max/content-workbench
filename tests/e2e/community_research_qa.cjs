const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.emulateMedia({colorScheme:'dark'});await page.goto('http://127.0.0.1:8880/');
  await page.locator('.task-card').first().click();await page.locator('[data-research]').click();
  await page.locator('#research-status').filter({hasText:'已通过 ChatGPT 订阅联网取得规则与样本摘要'}).waitFor();
  assert((await page.locator('[data-field="rules_zh"]').inputValue()).includes('禁止广告和 AI 内容'));
  assert((await page.locator('[data-field="culture_zh"]').inputValue()).includes('三个样本'));
  assert.equal(await page.locator('[data-field="confirmed"]').isChecked(),false);
  await page.getByText('查看查询记录与来源',{exact:true}).click();assert.equal(await page.locator('.community-evidence a').count(),4);
  const fs=require('node:fs'),path=require('node:path');const output=path.resolve(__dirname,'../../../acceptance');fs.mkdirSync(output,{recursive:true});
  await page.screenshot({path:path.join(output,'v061_community_research.png'),fullPage:true});
  await page.locator('[data-research]').click();await page.locator('[data-field="rules_zh"]').fill('用户在查询期间的新编辑');
  await page.locator('#research-status').filter({hasText:'查询期间的新编辑已保留'}).waitFor();
  assert.equal(await page.locator('[data-field="rules_zh"]').inputValue(),'用户在查询期间的新编辑');
  assert.equal(await page.locator('[data-field="confirmed"]').isChecked(),false);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,network:'simulated',sources:4,confirmationAutomatic:false,concurrentEditPreserved:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
