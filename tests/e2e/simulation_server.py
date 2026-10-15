"""Local disposable browser fixture. Never connects to a real model or user data."""
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))

from waypoint.contracts import TaskSpec
from waypoint.server import create_app
from waypoint.materials import Materials


class Provider:
    supports_web_research=True

    async def capabilities(self):
        return {'auth_state':'chatgpt','models':[{'model':'test'}]}

    async def generate(self,request):
        await asyncio.sleep(.05)
        stage=request['stage']
        if stage=='community_auto':
            answer={'items':[{'name':'r/AskAMechanic','variants':2,'reason_zh':'设备相关讨论',
                              'culture_zh':'偏好具体问题'}]}
        elif stage=='fact_research':
            answer={'summary_zh':'续航未能通过公开来源核实','claims':[{'claim_zh':'续航 90 小时',
                      'status':'unverified','source_urls':[]}]}
        elif stage=='post_research':
            date=datetime.now(timezone.utc).date().isoformat()
            answer={'items':[{'url':'https://www.reddit.com/r/dashcams/comments/abc123/parking/',
                'title':'Parking camera question','original_text':'How should I choose a parking camera?',
                'published_at':date+'T12:00:00Z','date_evidence':date,'recommendation':'high',
                'reason_zh':'问题贴近产品','angle_zh':'先说明选择条件','caution_zh':'模拟评论，规则待核对'}],
                'message_zh':'隔离模拟搜索结果。'}
            yield {'kind':'completed','text':json.dumps(answer),'web_sources':[{
                'url':'https://www.reddit.com/r/dashcams/comments/abc123/parking/',
                'title':'Parking camera question','snippet':date+' How should I choose a parking camera?'}]}
            return
        else:
            answer={'title':'A scanner question' if stage=='english' else '',
                    'body':'The scanner lasts 90 hours.' if stage=='english' else '扫描仪续航九十小时。',
                    'note_zh':'老细，按用户意图改写。','questions':['续航仍待核对'] if stage=='english' else [],
                    'citations':[]}
        yield {'kind':'completed','text':json.dumps(answer),'web_sources':[],'usage':{}}

    async def interrupt(self,job_id):pass


data=Path(tempfile.mkdtemp(prefix='waypoint_simulation_e2e_'))
app=create_app(data,Provider(),accounts_enabled=False)
repo=app.state.repo
brand=repo.create_project('TOPDON')
repo.create_task(TaskSpec(project_id=brand,kind='post',name='模拟扫描仪帖文',
                          raw_input='讨论一款扫描仪的续航 90 小时',target_stage='english'))
repo.create_task(TaskSpec(project_id=brand,kind='post',name='先看思路的多稿帖文',
                          raw_input='先给中文思路，再生成英文',target_stage='idea'))
source=Materials(repo).add_text(brand,'自然用户原帖','How should I choose a scanner?',kind='thread',
    comment_source=True,source_mode='text')
source['trust']='simulation_selected';repo.put('material',source)
comment=repo.create_task(TaskSpec(project_id=brand,kind='comment',name='先看中文的评论',
    source_ids=[source['id']],raw_input='先给中文回答大意',target_stage='chinese'))
repo.set_task_state(comment,comment_source_id=source['id'],comment_source_required=True)
repo.save_settings({'model_roles':{'write':'test','complex':'test','translate':'test','extract':'test'}})
uvicorn.run(app,host='127.0.0.1',port=8890,log_level='warning')
