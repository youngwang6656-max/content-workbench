const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage();await page.goto('http://127.0.0.1:8880/');
  await page.locator('[data-page="materials"]').click();
  const prefix='quota-'+Date.now();
  await page.locator('#material-drop').evaluate((zone,names)=>{
   const transfer=new DataTransfer();
   for(const name of names)transfer.items.add(new File(['Saved source text'],name,{type:'text/plain'}));
   zone.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));
  },[prefix+'-first.txt',prefix+'-second.txt']);
  await page.getByRole('button',{name:'导入所选文件',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#upload-summary')?.textContent.includes('2 个成功'));
  await page.getByRole('button',{name:'查看已导入资料',exact:true}).click();
  await page.locator('article.material h3').filter({hasText:prefix+'-first.txt'}).waitFor();
  const cards=page.locator('article.material').filter({hasText:prefix});
  assert.equal(await cards.count(),2);
  assert.match(await cards.first().innerText(),/本机已收录 1 \/ 1 页\/段文字/);
  for(const card of await cards.all())await card.locator('[data-select-material]').check();
  let calls=0;
  await page.route('**/api/materials/*/batch-read',route=>{calls++;return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({detail:'无法核实订阅额度，已暂停生成；未使用 credits 或付费 API'})})});
  await page.locator('#batch-read-materials').click();
  await page.getByRole('button',{name:'开始本批 AI 精读',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#batch-reading-summary')?.textContent.includes('1 份 AI 暂停'));
  assert.equal(calls,1);
  assert.match(await page.locator('#batch-reading-results').innerText(),/本地已提取的文字仍可用于写作/);
  console.log('PASS: upload is locally ready; Plus quota failure pauses AI once without marking remaining files broken.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
