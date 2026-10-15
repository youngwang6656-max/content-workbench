# 把内容工作台通用版交给你的 AI 启动

你可以直接把此文件和整个程序文件夹交给自己的 AI，再发送：

遇到使用或生成问题时，把 [智能体使用手册](waypoint/manuals/智能体使用手册.md)、报错文字和当前版本一并交给 AI。用户操作可读 [用户使用手册](waypoint/manuals/用户使用手册.md)。两份文件随源码发布，也可以在侧栏“使用手册”下载。

> 请在我的 Windows 电脑启动这个文件夹里的 waypoint。先读本文件、waypoint/manuals/智能体使用手册.md、README.md 和 AGENTS.md，确认实际目录；优先运行“启动内容工作台.cmd”，不要重新建一个程序。允许你在本机准备免费的 Python 和项目依赖，使用官方源；禁止付费 API、充值、云部署。已有资料先备份；保留原稿、账号、密钥、附件和我的源码修改。读取 startup_logs 的真实报错后最小修复。最后打开正确版本网页。我的个人账号密码和官方 ChatGPT 登录由我自行完成。测试模型不能当成真实生成成功。

## 实际处理顺序

1. ZIP 先完整解压，工作目录是带 waypoint/ 和 scripts/ 的 content_workbench，不在 ZIP 内启动。普通用户可双击“启动内容工作台.cmd”，不需要输入命令。
2. Windows 启动器先复用当前目录有效的 .venv；再查电脑上 Python 3.12+。缺少 Python 时才从 Python 官方 NuGet 源获取已核对固定 SHA-512 和 PSF 签名的免费免安装环境；解压到当前用户 LOCALAPPDATA/content-workbench-runtime，不使用 MSI，不修改全局 PATH 或文件关联。依赖在该程序的 .venv，从官方 PyPI 安装，具体报错在 startup_logs。
3. AI 可执行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1 -PrepareOnly` 只准备环境，再用 `.venv\Scripts\python.exe -m waypoint.launcher` 运行。不要把管理员权限作为默认；不要关闭 TLS/签名校验。
4. 8766 被占用先读 `/api/session` 的版本并核实进程路径，不杀不认识的进程。需要测试时指定独立 data-dir 和端口，不用真实业务库制造测试稿。
5. 本地资料默认在 `%LOCALAPPDATA%\content-workbench`；应用目录不包含这些资料。程序更新解压到新文件夹，保留旧文件夹，迁移代码改动时按 release-files.json 文件基线核对。账号和密钥继续留在自己的本机，不从开发者或别人的电脑复制。
6. 每套安装由使用者设置自己的个人账号。“设置与用量”里使用自己的官方 ChatGPT 登录或自己明确配置的 API；API 默认关闭。不要读取、打印或复制浏览器 Cookie、账号会话和 API 密钥。

## 用户自行修改

界面在 waypoint/web/，业务在 waypoint/，启动在 scripts/。修改可本地生效，不需要开发者批准或上传云端。修改后先测试，重启再查看；联网更新不覆盖旧程序。发布包附源码和测试，可把你的修改及问题交给自己的 AI 继续处理。

通用版默认数据目录与原版独立，环境覆盖变量为CONTENT_WORKBENCH_DATA_DIR；Cookie为content_workbench_session。不得为了登录而清空账号数据库或设置固定后门密码。
