const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage();
  await page.route('**/api/session',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({token:'',version:'0.9.4',auth:{enabled:true,configured:true,user:null}})}));
  await page.goto('http://127.0.0.1:8765/');
  await page.locator('#main .attention-label').waitFor();
  const message=await page.locator('#main').innerText();
  assert.match(message,/页面文件版本 0\.9\.7/);
  assert.match(message,/正在运行的后台版本 0\.9\.4/);
  assert.match(message,/重新启动工作台/);
  console.log('PASS: frontend/backend version mismatch is explicit before loading workspace data.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
