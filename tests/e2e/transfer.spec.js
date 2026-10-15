const {test,expect}=require('@playwright/test');
function bundle(){return {format:'waypoint-handoff',version:1,project_key:'browser-'+Date.now(),part:1,total_parts:1,
 project:{name:'迁移验收项目',description:'摄影社群',summary:'保留用户的转折',rules:['品牌名小写']},
 coverage:{sources:['测试对话'],missing:['产品附件尚未提供'],uncertain:[]},materials:[],
 tasks:[{key:'t1',name:'导入的英文稿',raw_input:'想法不丢失',versions:[{key:'v1',stage:'english',title:'My original title',body:'This is the exact original draft.',current:true}],opinions:[]}],
 history:[{role:'user',text:'请保留我的原话 <img src=x onerror=alert(1)>',record_type:'original',source:'对话 A'}]};}
test('复制固定提示词、预览导入并继续编辑迁入任务',async({page,context})=>{
 await context.grantPermissions(['clipboard-read','clipboard-write']);await page.goto('/');
 await page.getByRole('button',{name:'项目迁移',exact:true}).click();
 await page.getByRole('button',{name:'复制固定提示词',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>navigator.clipboard.readText())).toContain('waypoint-handoff');
 await page.getByLabel('或粘贴 GPT 输出').fill(JSON.stringify(bundle()));
 await page.getByRole('button',{name:'校验并预览',exact:true}).click();
 await expect(page.getByRole('heading',{name:'核对迁入内容'})).toBeVisible();
 await expect(page.getByText('产品附件尚未提供',{exact:true})).toBeVisible();
 await page.getByRole('checkbox').check();
 await page.getByRole('button',{name:'确认导入为新项目',exact:true}).click();
 await expect(page.getByRole('button',{name:/导入的英文稿/})).toBeVisible();
 await page.getByRole('button',{name:/导入的英文稿/}).click();
 await expect(page.getByText('This is the exact original draft.',{exact:true})).toBeVisible();
 await page.getByLabel('我的意见',{exact:true}).fill('这一版只改结尾');await page.getByRole('button',{name:'保存意见',exact:true}).click();
 await expect(page.getByText('这一版只改结尾',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'项目迁移',exact:true}).click();await page.getByRole('button',{name:'查阅迁入历史',exact:true}).click();
 await page.getByLabel('搜索历史记录').fill('原话');await page.getByRole('button',{name:'搜索',exact:true}).click();
 await expect(page.locator('.history-message pre')).toContainText('<img src=x onerror=alert(1)>');
 expect(await page.locator('.history-message img').count()).toBe(0);
});
test('外观选择持久化，深色迁移页窄屏不溢出',async({page})=>{
 await page.goto('/');await page.locator('#theme-toggle').click();await page.locator('#theme-toggle').click();
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');await page.reload();
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 await page.getByRole('button',{name:'项目迁移',exact:true}).click();await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
test('不完整 JSON 在页面显示错误且不写入项目',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'项目迁移',exact:true}).click();
 await page.getByLabel('或粘贴 GPT 输出').fill('{"format":');await page.getByRole('button',{name:'校验并预览',exact:true}).click();
 await expect(page.locator('#transfer-error')).toContainText('不是完整');
 await expect(page.getByRole('heading',{name:'核对迁入内容'})).toHaveCount(0);
});
