import asyncio,json
import pytest
from test_repository import make
from test_workflow import FakeProvider
from waypoint.materials import Materials
from waypoint.workflow import Engine


class Reader(FakeProvider):
    missing=[]
    async def generate(self,request):
        self.requests.append(request)
        source=json.loads(request['prompt'].split('资料数据：\n',1)[1])
        yield {'kind':'completed','text':json.dumps({'summary_zh':'资料摘要','facts_zh':['[文字段 1] 参数 42'],'missing_zh':self.missing,
            'unit_notes_zh':[{'number':unit['number'],'note_zh':f"{unit['label']}：已读取"} for unit in source['units']]})}


def setup(tmp_path,units=None):
    r,p,t=make(tmp_path);r.save_settings({'model_roles':{'write':'test'}})
    m=Materials(r).add_text(p,'资料','Original',**({'units':units} if units else {}))
    reader=Reader();return r,p,t,m,reader,Engine(r,reader)


def test_batch_reads_long_material_in_bounded_chunks_and_resumes_without_cost(tmp_path):
    from waypoint.material_batch import read_next
    units=[{'label':f'段 {i}','text':'x'*12000} for i in range(10)]
    r,p,t,m,f,e=setup(tmp_path,units)
    async def run():
        statuses=[]
        for _ in range(4):statuses.append(await read_next(e,m['id'],{'project_id':p}))
        return statuses
    results=asyncio.run(run())
    assert [x['status'] for x in results]==['working','working','working','complete']
    saved=r.get(m['id'],'material')
    assert [(x['start'],x['end']) for x in saved['analysis_history']]==[(1,3),(4,6),(7,9),(10,10)]
    assert len(saved['adopted_analysis_ids'])==4 and saved['text']=='Original'
    assert saved['trust']=='unverified'
    assert asyncio.run(read_next(e,m['id'],{'project_id':p}))['status']=='complete'
    assert len(f.requests)==4


def test_batch_does_not_mark_unmentioned_pages_as_read(tmp_path):
    from waypoint.material_batch import read_next
    units=[{'label':f'第 {i} 页','text':f'第 {i} 页参数'} for i in range(1,7)]
    r,p,t,m,f,e=setup(tmp_path,units)
    class PartialReader(Reader):
        async def generate(self,request):
            self.requests.append(request)
            yield {'kind':'completed','text':json.dumps({'summary_zh':'只看了前两页','facts_zh':['[第 1 页] 参数'],'missing_zh':[],
                'unit_notes_zh':[{'number':1,'note_zh':'第 1 页参数'},{'number':2,'note_zh':'第 2 页参数'}]})}
    e.provider=PartialReader()
    result=asyncio.run(read_next(e,m['id'],{'project_id':p}))
    assert result['status']=='needs_attention'
    assert result['covered']==0 and result['total_units']==6
    assert '3' in result['message'] and '6' in result['message']
    saved=r.get(m['id'],'material')
    assert len(saved['analysis_history'])==1
    assert not saved['analysis_history'][0]['complete']
    assert not saved.get('adopted_analysis_ids')


def test_thirty_two_page_document_reaches_last_page(tmp_path):
    from waypoint.material_batch import read_next
    units=[{'label':f'第 {i} 页','text':f'第 {i} 页的独立内容'} for i in range(1,33)]
    r,p,t,m,f,e=setup(tmp_path,units)
    results=[asyncio.run(read_next(e,m['id'],{'project_id':p})) for _ in range(4)]
    assert [x['covered'] for x in results]==[8,16,24,32]
    assert results[-1]['status']=='complete'
    saved=r.get(m['id'],'material')
    assert [(x['start'],x['end']) for x in saved['analysis_history']]==[(1,8),(9,16),(17,24),(25,32)]
    assert saved['analysis_history'][-1]['unit_notes_zh'][-1]['number']==32


def test_uncertain_facts_do_not_stop_page_coverage(tmp_path):
    from waypoint.material_batch import read_next
    r,p,t,m,f,e=setup(tmp_path);f.missing=['单位无法确认']
    result=asyncio.run(read_next(e,m['id'],{'project_id':p}))
    assert result['status']=='complete' and result['covered']==1
    saved=r.get(m['id'],'material')
    assert len(saved['analysis_history'])==1 and len(saved.get('adopted_analysis_ids',[]))==1
    assert saved['analysis_history'][0]['missing_zh']==['单位无法确认']
    assert len(f.requests)==1


def test_unreadable_first_range_does_not_prevent_later_pages(tmp_path):
    from waypoint.material_batch import read_next
    units=[{'label':f'第 {i} 页','text':f'第 {i} 页内容'} for i in range(1,13)]
    r,p,t,m,f,e=setup(tmp_path,units)
    class UnreadableReader(Reader):
        async def generate(self,request):
            self.requests.append(request)
            source=json.loads(request['prompt'].split('资料数据：\n',1)[1])
            first=source['range'][0]
            yield {'kind':'completed','text':json.dumps({'summary_zh':'逐页摘要','facts_zh':[],'missing_zh':['图表细节待核实'] if first==1 else [],
                'unreadable_units':[3] if first==1 else [],
                'unit_notes_zh':[{'number':u['number'],'note_zh':f"{u['label']}内容"} for u in source['units']]})}
    e.provider=UnreadableReader()
    first=asyncio.run(read_next(e,m['id'],{'project_id':p}))
    second=asyncio.run(read_next(e,m['id'],{'project_id':p}))
    assert first['status']=='working' and first['covered']==0
    assert second['status']=='needs_attention' and second['covered']==4
    assert len(e.provider.requests)==2
    saved=r.get(m['id'],'material')
    assert [(a['start'],a['end']) for a in saved['analysis_history']]==[(1,8),(9,12)]
    assert len(saved.get('adopted_analysis_ids',[]))==1


def test_batch_reuses_complete_history_and_preserves_stale_history(tmp_path):
    from waypoint.material_reading import analyze,supplement
    from waypoint.material_batch import read_next
    r,p,t,m,f,e=setup(tmp_path)
    result=asyncio.run(analyze(e,m['id'],{}))
    assert asyncio.run(read_next(e,m['id'],{'project_id':p}))['reused']
    assert len(f.requests)==1
    supplement(r,m['id'],'新条件')
    assert asyncio.run(read_next(e,m['id'],{'project_id':p}))['status']=='complete'
    saved=r.get(m['id'],'material')
    assert len(saved['analysis_history'])==2 and saved['analysis_history'][0]['id']==result['id']
    assert len(f.requests)==2


def test_batch_scope_and_archive_validation_prevents_partial_changes(tmp_path):
    from waypoint.material_batch import read_next
    r,p,t,m,f,e=setup(tmp_path)
    global_m=Materials(r).add_text(None,'全局','global')
    with pytest.raises(ValueError,match='范围'):asyncio.run(read_next(e,m['id'],{'project_id':None}))
    with pytest.raises(ValueError,match='范围'):Materials(r).archive_batch([m['id'],global_m['id']],p)
    assert not r.get(m['id'],'material')['archived']
    assert f.requests==[]
    epoch=r.task(t)['input_epoch']
    Materials(r).archive_batch([m['id'],m['id']],p)
    assert r.get(m['id'],'material')['archived'] and r.get(m['id'],'material')['text']=='Original'
    assert r.task(t)['input_epoch']==epoch+1


def test_batch_limits_visual_count_without_paid_retry(tmp_path):
    from waypoint.material_batch import next_range
    units=[{'text':'x','visual':True,'media':['r1','r2','r3']} for _ in range(8)]
    assert next_range(units,list(range(1,9)))==(1,8)
    assert next_range([{'text':'x','visual':True,'media':[str(i) for i in range(12)]}],[1])==(1,1)
    assert next_range([{'text':'x'}]*10,[1,2,5,6])==(1,2)


def test_batch_scope_change_during_reading_keeps_history_without_adoption(tmp_path):
    from waypoint.material_batch import read_next
    r,p,t,m,f,e=setup(tmp_path);target=r.create_project('合并目标')
    class MovingReader(Reader):
        async def generate(self,request):
            current=r.get(m['id'],'material');current['project_id']=target;r.put('material',current)
            async for event in super().generate(request):yield event
    e.provider=MovingReader()
    with pytest.raises(ValueError,match='范围'):asyncio.run(read_next(e,m['id'],{'project_id':p}))
    current=r.get(m['id'],'material')
    assert current['project_id']==target and len(current['analysis_history'])==1
    assert not current.get('adopted_analysis_ids')
