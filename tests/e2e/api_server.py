"""Disposable UI fixture: all model-directory requests use MockTransport."""
import tempfile,sys,json
from pathlib import Path
import uvicorn,httpx
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from waypoint.server import create_app
from test_workflow import FakeProvider
class QuotaFixture(FakeProvider):
    async def capabilities(self):
        result=await super().capabilities()
        return result|{'quota':{'rateLimits':{'primary':{'usedPercent':92,'windowDurationMins':300}}},'plan':'plus'}
app=create_app(tempfile.mkdtemp(prefix='waypoint_api_qa_'),QuotaFixture(),accounts_enabled=False)
repo=app.state.repo;repo.create_project('界面验收品牌（模拟）')
repo.save_settings({'model_roles':{'write':'test','translate':'test'},'api_enabled':False,'provider':'codex'})
repo.put('connection',{'id':'connection','auth_state':'chatgpt','models':[{'model':'test','displayName':'模拟订阅模型'}],
    'quota':{'rateLimits':{'primary':{'usedPercent':92,'windowDurationMins':300}}},'plan':'plus',
    'message':'隔离界面测试，未连接真实 ChatGPT 或第三方模型'})
profiles=app.state.engine.api_profiles
profiles.save({'vendor':'deepseek','name':'界面验收服务商（模拟）','api_key':'disposable-fixture-key-2026'})
original=profiles.read_models
def handle(request):
    if request.method!='GET' or not request.url.path.endswith('/models'):raise AssertionError('UI fixture permits only mocked model listing')
    return httpx.Response(200,json={'data':[{'id':'fixture-write','display_name':'模拟写作模型'},{'id':'fixture-translate','display_name':'模拟回译模型'}]})
async def read_models(id):return await original(id,transport=httpx.MockTransport(handle))
profiles.read_models=read_models
uvicorn.run(app,host='127.0.0.1',port=8879,log_level='warning')
