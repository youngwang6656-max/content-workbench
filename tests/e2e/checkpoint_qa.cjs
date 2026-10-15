const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require('playwright');

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const output=path.resolve('..','acceptance','flow_tests');
 try{
  await page.goto('http://127.0.0.1:8890/');
  await page.locator('.task-card').filter({hasText:'先看思路的多稿帖文'}).click();
  await page.getByRole('button',{name:'生成模拟稿'}).click();
  await page.locator('[data-continue]').last().waitFor({timeout:15000});
  assert.equal(await page.locator('[data-continue]').count(),2);
  assert.equal(await page.locator('[data-pass]').count(),0);
  assert((await page.locator('.flow-panel').textContent()).includes('查看中文思路 → 英文成品'));
  await page.locator('[data-continue]').first().click();
  await page.locator('[data-pass]').waitFor({timeout:15000});
  assert.equal(await page.locator('[data-continue]').count(),1);
  assert((await page.locator('.variant-card').first().textContent()).includes('The scanner lasts 90 hours.'));
  assert((await page.locator('.variant-card').first().textContent()).includes('对应中文回译'));
  await page.screenshot({path:path.join(output,'checkpoint-post.png'),fullPage:true});
  await page.locator('[data-abandon]').last().click();
  await page.getByText('1 篇当前候选').waitFor();
  assert.equal(await page.locator('[data-continue]').count(),0);
  await page.locator('[data-pass]').click();
  await page.getByText('已通过 · 已完成').waitFor();
  await page.locator('#post-back').click();
  assert((await page.locator('.task-card').filter({hasText:'先看思路的多稿帖文'}).textContent()).includes('已完成'));

  await page.locator('.task-card').filter({hasText:'先看中文的评论'}).click();
  await page.locator('#run').click();
  await page.locator('[data-continue]').waitFor({timeout:15000});
  assert.equal(await page.locator('#approve').textContent(),'通过并直达英文成品');
  await page.locator('[data-continue]').click();
  await page.waitForFunction(()=>document.querySelector('#approve')?.textContent==='通过'&&!document.querySelector('#approve')?.disabled,null,{timeout:15000});
  assert((await page.locator('#body-content').textContent()).includes('The scanner lasts 90 hours.'));
  assert((await page.locator('.translation').textContent()).includes('扫描仪续航九十小时'));
  await page.locator('#approve').click();
  await page.getByText('已完成',{exact:true}).first().waitFor();
  await page.locator('#opinion-form #opinion').fill('把开头写得自然一些');
  await page.locator('#opinion-form button.primary').click();
  await page.waitForFunction(()=>document.querySelector('#approve')?.textContent==='通过'&&!document.querySelector('#approve')?.disabled,null,{timeout:15000});
  assert((await page.locator('#live-state').textContent()).includes('英文成品待通过'));
  await page.screenshot({path:path.join(output,'checkpoint-comment.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,model:'simulated',postCheckpoint:true,independentVariants:true,
      commentCheckpoint:true,newRevisionRequiresPass:true,historyPreserved:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
