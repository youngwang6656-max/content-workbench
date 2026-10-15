const {test,expect}=require('@playwright/test');
test('中文任务、意见、手动版本和纯正文复制',async({page,context})=>{
 await context.grantPermissions(['clipboard-read','clipboard-write']);
 await page.goto('/');
 await page.getByRole('button',{name:'新建项目',exact:true}).click();
 await page.getByLabel('项目名称').fill('浏览器验收');
 await page.getByRole('button',{name:'创建项目',exact:true}).click();
 await page.getByRole('button',{name:'新建任务',exact:true}).click();
 await page.getByLabel('任务名称').fill('第一条想法');
 await page.getByLabel('原始想法与材料').fill('这里保存中文原始想法');
 await page.getByRole('button',{name:'保存任务',exact:true}).click();
 await expect(page.getByRole('heading',{name:'第一条想法'})).toBeVisible();
 await page.getByLabel('我的意见').fill('保留我的转折');
 await page.getByRole('button',{name:'保存意见',exact:true}).click();
 await expect(page.getByText('保留我的转折',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'手动保存稿件',exact:true}).click();
 await page.getByLabel('稿件正文').fill('I kept the original idea.');
 await page.getByRole('button',{name:'保存为新版本',exact:true}).click();
 await page.getByRole('button',{name:'复制正文',exact:true}).click();
 expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe('I kept the original idea.');
 await page.reload();await expect(page.getByText('I kept the original idea.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'项目资料',exact:true}).click();
 await expect(page.getByRole('heading',{name:'项目资料'})).toBeVisible();
 await page.getByRole('button',{name:'设置与用量',exact:true}).click();
 await expect(page.getByText('API 默认关闭',{exact:false}).first()).toBeVisible();
});
test('窄窗口没有横向溢出',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
test('界面一键开始本批三条任务',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'新建项目',exact:true}).click();await page.getByLabel('项目名称').fill('批次启动测试');await page.getByRole('button',{name:'创建项目',exact:true}).click();
 await page.getByRole('button',{name:'批量新建',exact:true}).click();
 for(let i=0;i<3;i++)await page.locator('.batch-card textarea').nth(i).fill('第'+i+'条独立想法');
 await expect(page.getByRole('button',{name:'保存并开始本批',exact:true})).toBeVisible({timeout:1000});
 await page.getByRole('button',{name:'保存并开始本批',exact:true}).click();
 await expect(page.getByText('本批进度',{exact:false})).toBeVisible();
});
