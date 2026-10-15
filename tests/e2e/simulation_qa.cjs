const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8890/');
  await page.locator('.task-card').filter({hasText:'模拟扫描仪帖文'}).click();
  await page.getByRole('button',{name:'生成模拟稿'}).click();
  await page.locator('.variant-card').first().waitFor({timeout:15000});
  await page.getByText('2 篇当前候选').waitFor({timeout:15000});
  assert.equal(await page.locator('[data-pass]').count(),2);
  assert.equal(await page.locator('[data-opinion]').count(),2);
  assert.equal(await page.locator('[data-abandon]').count(),2);
  assert((await page.locator('.flow-panel').textContent()).includes('等待你的决定'));
  assert((await page.locator('.variant-card').first().textContent()).includes('续航未能通过公开来源核实'));
  await page.locator('[data-pass]').first().click();
  await page.getByText('已通过 ·',{exact:false}).first().waitFor();
  await page.locator('[data-abandon]').last().click();
  await page.getByText('1 篇当前候选').waitFor();
  assert.equal(await page.locator('[data-abandon]').count(),0);
  assert.equal(await page.locator('[data-pass]').count(),1);
  await page.locator('.abandoned-list').evaluate(el=>el.open=true);
  await page.locator('[data-restore]').click();
  await page.getByText('2 篇当前候选').waitFor();
  await page.locator('[data-opinion]').first().click();
  await page.locator('#dialog textarea[name="raw_text"]').fill('换一个更自然的开头');
  await page.getByRole('button',{name:'添加意见并重写'}).click();
  await page.locator('.variant-card').first().waitFor();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,model:'simulated',multiDraftActions:true,historyPreserved:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
