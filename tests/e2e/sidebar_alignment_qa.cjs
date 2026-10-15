const assert=require('node:assert/strict');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 try{await page.goto('http://127.0.0.1:8879/');await page.locator('.brand-categories button').first().waitFor();
 const item=await page.locator('.project-item.active').boundingBox(),tabs=await page.locator('.brand-categories').boundingBox();
 assert.ok(Math.abs(item.x-tabs.x)<1);assert.ok(Math.abs(item.x+item.width-tabs.x-tabs.width)<1);
 const add=await page.locator('#new-project').boundingBox(),menu=await page.locator('.project-manage').first().boundingBox();
 assert.ok(Math.abs(add.x+add.width/2-menu.x-menu.width/2)<1);
 assert.equal(await page.locator('#quick-reading svg').count(),1);assert.equal(await page.locator('#quick-reading').getAttribute('aria-label'),'中文译读');
 await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v080_sidebar.png'});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'D:/waypoint_codex_handoff/acceptance/v080_mobile.png'});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 console.log('PASS: brand tabs align on both edges, plus/menu centers align, reading icon, mobile has no horizontal overflow.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
