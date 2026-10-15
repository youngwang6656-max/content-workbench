"""Isolated browser fixture: blocked Reddit + simulated subscription research."""
import sys,tempfile,asyncio
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path[:0]=[str(root),str(root/'tests')]
import uvicorn
from waypoint.server import create_app
from waypoint.contracts import TaskSpec
from waypoint.communities import save_plan
from test_community_research import SearchProvider
import waypoint.routes.communities as routes

class DelayedSearch(SearchProvider):
    async def generate(self,request):
        await asyncio.sleep(.8)
        async for event in super().generate(request):yield event

async def blocked(name):return {'name':name,'status':'unavailable','sources':[],'http_status':403,'message':'Reddit HTTP 403','checked_at':'2026-09-29'}
routes.fetch_evidence=blocked
provider=DelayedSearch();app=create_app(Path(tempfile.mkdtemp(prefix='waypoint_research_qa_')),provider,accounts_enabled=False)
async def selected(role):return provider,{'model':'test','effort':None}
app.state.engine.select_provider=selected
r=app.state.repo;pid=r.create_project('社群查询界面验收（模拟）')
tid=r.create_task(TaskSpec(project_id=pid,name='查询规则与近期生态',raw_input='界面验收数据，不发布'))
save_plan(r,tid,[{'name':'r/AskAMechanic','variants':1,'rules_zh':'','culture_zh':'','confirmed':False}],0)
uvicorn.run(app,host='127.0.0.1',port=8880,log_level='warning')
