"""Disposable update server; public HTTPS requests are all MockTransport."""
import tempfile,sys,json,zipfile
from pathlib import Path
import uvicorn,httpx
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from waypoint.server import create_app
from waypoint.distribution import build_release
from waypoint.contracts import TaskSpec
from test_workflow import FakeProvider
scratch=Path(tempfile.mkdtemp(prefix='waypoint_updates_qa_'))
release=build_release(root,scratch/'original')
with zipfile.ZipFile(release['package']) as z:
    z.extractall(scratch/'local');z.extractall(scratch/'remote')
local=scratch/'local/waypoint_workbench';remote=scratch/'remote/waypoint_workbench'
(local/'waypoint/local_patch.py').write_text('# simulated user modification')
version=release['version'];parts=version.split('.');parts[-1]=str(int(parts[-1])+1);next_version='.'.join(parts)
for name in ('waypoint/__init__.py','pyproject.toml','waypoint/web/index.html'):
    p=remote/name;p.write_bytes(p.read_bytes().replace(version.encode(),next_version.encode()))
new=build_release(remote,scratch/'new',download_url='https://updates.example.com/waypoint.zip',notes_zh='隔离模拟更新。保留本地源码修改，未发布外网。')
manifest=json.loads(Path(new['manifest']).read_text(encoding='utf-8'));package=Path(new['package']).read_bytes()
app=create_app(scratch/'data',FakeProvider(),accounts_enabled=False)
repo=app.state.repo;project=repo.create_project('图标与更新验收（模拟）')
for kind,name in [('post','帖文图标 A'),('comment','评论图标 c'),('cb','CB 图标 B')]:
    repo.create_task(TaskSpec(project_id=project,kind=kind,name=name,raw_input='仅为界面测试，不生成',target_stage='cb' if kind=='cb' else 'english'))
repo.put('connection',{'id':'connection','auth_state':'unverified','models':[],'message':'隔离测试库，未连接真实模型'})
service=app.state.updates;service.app_root=local
def handle(request):
    assert request.method=='GET' and 'authorization' not in request.headers and 'cookie' not in request.headers
    if request.url.path.endswith('latest.json'):return httpx.Response(200,json=manifest)
    if request.url.path.endswith('waypoint.zip'):return httpx.Response(200,content=package)
    return httpx.Response(404)
check=service.check;download=service.download
async def checked():return await check(transport=httpx.MockTransport(handle))
async def downloaded(id):return await download(id,transport=httpx.MockTransport(handle))
service.check=checked;service.download=downloaded
uvicorn.run(app,host='127.0.0.1',port=8880,log_level='warning')
