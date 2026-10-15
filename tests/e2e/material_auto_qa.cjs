const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:8880/');
  await page.locator('[data-page="materials"]').click();
  await page.locator('#upload').click();
  const prefix='auto-'+Date.now();
  await page.locator('#dialog input[type="file"]').setInputFiles([
   {name:prefix+'-one.txt',mimeType:'text/plain',buffer:Buffer.from('First product source')},
   {name:prefix+'-two.txt',mimeType:'text/plain',buffer:Buffer.from('Second product source')}
  ]);
  await page.getByRole('button',{name:'放入工作台'}).click();
  await page.waitForFunction(prefix=>{
   const cards=[...document.querySelectorAll('article.material')].filter(x=>x.textContent.includes(prefix));
   return cards.length===2&&cards.every(x=>x.querySelector('[data-auto-material]')?.textContent.includes('模型已逐页分析并采纳'));
  },prefix);
  assert.equal(await page.locator('#dialog').evaluate(x=>x.open),false);
  const cards=page.locator('article.material').filter({hasText:prefix});
  assert.equal(await cards.count(),2);
  assert.equal(await cards.first().locator('summary').filter({hasText:'处理详情与人工修正'}).isVisible(),true);
  assert.equal(await cards.first().locator('[data-read-material]').isVisible(),false);
  const projectId=await page.locator('#project-select').inputValue();
  const materials=await (await page.request.get('http://127.0.0.1:8880/api/materials?project_id='+projectId)).json();
  const imported=materials.filter(m=>m.name.startsWith(prefix));
  assert.equal(imported.length,2);
  assert(imported.every(m=>m.analysis_history.length===1&&m.adopted_analysis_ids.length===1));
  assert(imported.every(m=>m.trust==='unverified'&&m.path&&m.text));
  assert.deepEqual(errors,[]);
  console.log('PASS: two uploads close the dialog and auto-read/adopt in background; originals and unverified provenance remain. Synthetic model only.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
