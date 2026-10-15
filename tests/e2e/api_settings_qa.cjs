// Standalone regression runner; uses a fresh browser profile and disposable API server.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});const failures=[];
 page.on('pageerror',e=>failures.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8879/');await page.getByRole('button',{name:'设置与用量',exact:true}).click();
  await page.getByRole('heading',{name:'API 服务商',exact:true}).waitFor();
  assert.equal(await page.locator('[name="api_enabled"]').isChecked(),false);
  await page.getByRole('button',{name:'＋ 添加服务商',exact:true}).click();
  assert.equal(await page.locator('#api-protocol').inputValue(),'chat');
  assert.equal(await page.locator('#api-json-mode').inputValue(),'object');
  assert.equal((await page.locator('#api-protocol option[value="responses"]').getAttribute('disabled'))!==null,true);
  const createdName='Gemini 界面测试配置 '+Date.now();
  await page.locator('#api-vendor').selectOption('gemini');await page.locator('#api-name').fill(createdName);
  assert.equal((await page.locator('#api-protocol option[value="responses"]').getAttribute('disabled'))!==null,false);
  assert.equal(await page.locator('#api-base').inputValue(),'https://generativelanguage.googleapis.com/v1beta/openai');
  await page.getByRole('button',{name:'保存配置',exact:true}).click();await page.locator('#dialog').waitFor({state:'hidden'});
  await page.locator('#api-profile-list').getByText(createdName,{exact:true}).waitFor();
  let card=page.locator('.api-profile').filter({hasText:'界面验收服务商（模拟）'});
  await card.getByRole('button',{name:'读取账户模型',exact:true}).click();
  await page.getByText('2 个账户模型',{exact:false}).waitFor();
  card=page.locator('.api-profile').filter({hasText:'界面验收服务商（模拟）'});
  await card.getByRole('button',{name:'模型与价格',exact:true}).click();
  await page.locator('#price-model').selectOption('fixture-translate');await page.locator('#price-input').fill('0.5');
  await page.locator('#price-output').fill('1');await page.locator('#price-date').fill(new Date().toLocaleDateString('en-CA'));
  await page.locator('[name="make_default"]').check();await page.getByRole('button',{name:'保存此模型价格',exact:true}).click();
  await page.locator('#dialog').waitFor({state:'hidden'});await page.getByText('默认 fixture-translate',{exact:false}).waitFor();
  const catalog=await (await page.request.get('http://127.0.0.1:8879/api/api-profiles')).json();
  const profile=catalog.profiles.find(p=>p.name==='界面验收服务商（模拟）');
  await page.locator('[data-edit-usage]').nth(1).click();
  await page.locator('#dialog summary').click();await page.locator('#dialog [name="api_translate"]').selectOption('fixture-translate');
  await page.getByRole('button',{name:'保存模型配置',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.usage-config-row')[1]?.textContent.includes('fixture-translate'));
  const settings=await (await page.request.get('http://127.0.0.1:8879/api/settings')).json();
  assert.equal(settings.usage_configs[1].api_role_models.translate.model,'fixture-translate');assert.equal(settings.api_enabled,false);assert.equal(settings.provider,'codex');
  await page.reload();await page.getByRole('button',{name:'设置与用量',exact:true}).click();await page.getByRole('heading',{name:'API 服务商',exact:true}).waitFor();
  await page.locator('[data-edit-usage]').nth(1).click();await page.locator('#dialog summary').click();
  assert.equal(await page.locator('#dialog [name="api_translate"]').inputValue(),'fixture-translate');await page.getByRole('button',{name:'关闭',exact:true}).click();
  assert.equal(await page.locator('[name="api_enabled"]').isChecked(),false);
  await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v080_api_settings.png',fullPage:true});
  assert.deepEqual(failures,[]);console.log(JSON.stringify({passed:true,checks:11,apiEnabled:settings.api_enabled,paidRequests:0,screenshot:'acceptance/v080_api_settings.png'}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
