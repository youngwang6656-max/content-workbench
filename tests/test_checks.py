from waypoint.contracts import GenerationResult
import asyncio,json
from test_workflow import setup

def test_language_name_and_unknown_number():
    from waypoint.checks import validate_result
    snap={'target_stage':'cb','materials':[],'raw_input':'','rules':[]}
    assert any(i['code']=='language' for i in validate_result({'body':'English only','title':''},snap))
    snap['target_stage']='english';snap['raw_input']='D-Log M'
    issues=validate_result({'body':'D-Log M lasts 99 hours.','title':''},snap)
    assert any(i['code']=='fact' for i in issues)
    assert not any(i['code']=='punctuation' for i in issues)
    assert any(i['code']=='copy' for i in validate_result({'body':'老细，Here it is.','title':''},snap))

def test_auto_repair_at_most_once(tmp_path):
    r,p,t,f,e=setup(tmp_path);r.update_task(t,{'target_stage':'cb'})
    async def invalid(req):
        f.requests.append(req)
        yield {'kind':'completed','text':json.dumps({'title':'','body':'English only','note_zh':'','questions':[],'citations':[]})}
    f.generate=invalid
    asyncio.run(e.run_and_wait(t))
    assert len(f.requests)==2 and r.task(t)['status']=='paused'
