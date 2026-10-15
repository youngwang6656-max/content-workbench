# 内容工作台通用版交接

基于原版0.12.0的源码，独立版本1.0.0。原版在另一个目录，禁止覆盖。用户要求：移除公司Logo，原标识位置支持上传图片，先预览后准备GitHub，保留本机管理员与仓库所有者youngwang6656-max，不需要管理其他使用者的后台。

新标识功能：waypoint/branding.py、web/branding.js、web/workbench-mark.svg。PNG/JPEG/WebP输入校验、静态图片、5MB/1600万像素上限、1600px等比缩小、原子落盘，只有已登录所有者可上传/移除。中性默认图标无公司标记。后台图片只保存在数据目录branding/logo.png，不进入源码或品牌迁移。

通用版数据为LOCALAPPDATA/content-workbench，默认8766，Cookie为content_workbench_session。原版数据、API开关和模型配置不迁入；本机预览账号按用户授权单独保留所有者，认证及密码不会进入Git仓库。

Python依赖与测试运行可复用本机已有环境，但交付的源码不带虚拟环境。首次启动仍由启动器准备环境。保留内部waypoint模块和原项目迁移格式。

完成状态以本次验证记录和实际运行版本为准。GitHub尚待用户看过预览后决定是否推送，不要把准备源码说成已发布。
