"""Isolated stale-directory fixture; model checks are synthetic and generation is forbidden."""
import sys,tempfile
from pathlib import Path
import uvicorn
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from waypoint.server import create_app
from test_workflow import FakeProvider

class Catalog(FakeProvider):
    async def capabilities(self):
        return {'auth_state':'chatgpt','plan':'plus','models':[
            {'model':'gpt-6.1-sol','displayName':'GPT-6.1 Sol','supportedReasoningEfforts':[{'reasoningEffort':'high'}]},
            {'model':'gpt-6-luna','displayName':'GPT-6 Luna','supportedReasoningEfforts':[{'reasoningEffort':'high'}]}],
            'quota':{'rateLimits':{'primary':{'usedPercent':2,'windowDurationMins':300}}}}
    async def generate(self,request):raise AssertionError('Model-config UI test must not generate')

app=create_app(tempfile.mkdtemp(prefix='waypoint_catalog_qa_'),Catalog(),accounts_enabled=False)
r=app.state.repo;r.create_project('模型目录验收（模拟）')
r.save_settings({'usage_configs':[{'id':'subscription-initial','name':'订阅配置','provider':'codex',
    'model_roles':{'write':'gpt-5.5','translate':'gpt-6-luna'}}],
    'active_usage_config_id':'subscription-initial'})
r.put('connection',{'id':'connection','auth_state':'chatgpt','plan':'plus',
    'models':[{'model':'gpt-5.5','displayName':'GPT-5.5'}],
    'quota':{'rateLimits':{'primary':{'usedPercent':2,'windowDurationMins':300}}}})
uvicorn.run(app,host='127.0.0.1',port=8878,log_level='warning')
