"""Isolated deterministic UI acceptance; not evidence of live model access."""
import sys,tempfile,json,asyncio
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
import uvicorn
from waypoint.server import create_app
from waypoint.contracts import TaskSpec
class Provider:
    supports_web_research=True
    async def generate(self,request):
        await asyncio.sleep(.2)
        url='https://www.reddit.com/r/dashcams/comments/abc123/parking/'
        date=datetime.now(timezone.utc).isoformat();trace=[{'url':url,'title':'Parking camera question','snippet':date[:10]+' I need a camera for parking.'}]
        if request['schema'].get('properties',{}).get('items'):
            answer={'items':[{'url':url,'title':'Parking camera question','original_text':'I need a camera for parking. What should I consider?',
                'published_at':date,'date_evidence':date[:10],'recommendation':'high','reason_zh':'需求与已知资料相关','angle_zh':'先询问停车时长和预算','caution_zh':'社区规则待核对，须如实说明品牌关系'}],'message_zh':'模拟检索，只找到一篇有证据的候选。'}
        else:answer={'title':'原帖译读' if request['stage']=='reading_translation' else 'Parking camera question','body':'我需要停车时使用的相机，应该考虑哪些因素？' if request['stage']=='reading_translation' else 'I need a camera for parking. What should I consider?','note_zh':'模拟结果，仅供界面验收。','questions':[],'citations':[]}
        yield {'kind':'completed','text':json.dumps(answer),'web_sources':trace}
provider=Provider();app=create_app(Path(tempfile.mkdtemp(prefix='waypoint_comments_qa_')),provider,accounts_enabled=False)
async def select(role):return provider,{'model':'test'}
app.state.engine.select_provider=select
r=app.state.repo;pid=r.create_project('评论流程验收（模拟）');tid=r.create_task(TaskSpec(project_id=pid,name='项目中正在写的帖文',raw_input='Parking camera',kind='post'))
r.save_revision(tid,'idea','An early draft about parking cameras.',0,title='Early idea')
uvicorn.run(app,host='127.0.0.1',port=8881,log_level='warning')
