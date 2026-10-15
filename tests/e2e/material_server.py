"""Isolated fixture, synthetic model only; no external generation or user database."""
import sys,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from waypoint.server import create_app
from waypoint.materials import Materials
from waypoint.contracts import TaskSpec
from test_workflow import FakeProvider
class Reader(FakeProvider):
    async def capabilities(self):return {'auth_state':'chatgpt','plan':'plus','models':[{'model':'test'},{'model':'reader'}],'quota':{'rateLimits':{'primary':{'usedPercent':2,'windowDurationMins':300}}}}
    async def generate(self,request):
        if request['stage']=='material_reading':
            missing=['单位缺失，需补充'] if 'Batch incomplete' in request['prompt'] else []
            source=json.loads(request['prompt'].split('资料数据：\n',1)[1])
            yield {'kind':'completed','text':json.dumps({'summary_zh':'模拟资料摘要，用于 UI 验收','facts_zh':['[文字段 1] 重量 42 克'],'missing_zh':missing,
                'unreadable_units':[source['range'][0]] if missing else [],
                'unit_notes_zh':[{'number':unit['number'],'note_zh':f"{unit['label']}：模拟逐页记录"} for unit in source['units']]})}
        else:
            async for event in super().generate(request):yield event
app=create_app(tempfile.mkdtemp(prefix='waypoint_material_qa_'),Reader(),accounts_enabled=False)
r=app.state.repo;p=r.create_project('资料界面验收（模拟）');m=Materials(r).add_text(p,'产品说明测试资料','Weight: 42 g.')
missing=Materials(r).add_text(None,'缺失的全局资料','',extraction='needs_text')
t=r.create_task(TaskSpec(project_id=p,kind='cb',raw_input='使用资料写 CB',name='资料错误跳转验收'))
r.set_task_state(t,status='paused',message='资料无法提取文字，请补充文字或页面截图',attention={'page':'global-materials','material_id':missing['id'],'project_id':None})
r.save_settings({'model_roles':{'write':'test','translate':'test','read':'reader'},'api_enabled':False})
r.put('connection',{'id':'connection','auth_state':'chatgpt','models':[{'model':'test'},{'model':'reader'}],'message':'隔离模拟模型，仅验证程序行为','quota':{'rateLimits':{'primary':{'usedPercent':2,'windowDurationMins':300}}}})
uvicorn.run(app,host='127.0.0.1',port=8880,log_level='warning')
