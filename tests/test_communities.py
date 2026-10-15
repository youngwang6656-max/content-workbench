import asyncio
import pytest
from waypoint.communities import save_plan, prepare_variants, validate_leaf
from waypoint.contracts import TaskSpec, Opinion
from test_repository import make
from test_workflow import FakeProvider
from waypoint.workflow import Engine

def plan(count=3):
    return [{'name':f'r/test{i}', 'variants':i%3+1, 'rules_zh':'只讨论相关主题，禁止广告。',
             'culture_zh':'偏好具体问题和有依据的讨论。', 'confirmed':True} for i in range(count)]

def setup_group(tmp_path):
    r,p,t=make(tmp_path);save_plan(r,t,plan(),0)
    r.save_settings({'model_roles':{'write':'test','translate':'test'}})
    f=FakeProvider();return r,p,t,f,Engine(r,f)

@pytest.mark.parametrize('items',[plan(0),plan(6),[plan()[0],plan()[0]],plan()[:1]+[dict(plan()[1],variants=4)], [dict(x,confirmed=False) for x in plan()]])
def test_bad_plan_never_generates(tmp_path,items):
    r,p,t=make(tmp_path)
    try:save_plan(r,t,items,0)
    except ValueError:
        assert not r.list('task',post_group_id=t) and not r.list('revision');return
    f=FakeProvider();e=Engine(r,f);asyncio.run(e.run_and_wait(t))
    assert not f.requests and r.task(t)['status']=='paused'

def test_three_communities_six_independent_translations(tmp_path):
    r,p,t,f,e=setup_group(tmp_path);asyncio.run(e.run_and_wait(t))
    children=r.list('task',post_group_id=t)
    assert len(children)==6 and len(f.requests)==7
    english_requests=[x for x in f.requests if x['stage']=='english']
    for child in children:
        assert r.revision(child['active']['backtranslation'])['source_revision_id']==child['active']['english']
        assert child['community']['name'] in english_requests[children.index(child)]['prompt']

def test_one_community_preserves_version_and_translation_links(tmp_path):
    r,p,t=make(tmp_path);save_plan(r,t,plan(1),0)
    r.save_settings({'model_roles':{'write':'test','translate':'test'}})
    f=FakeProvider();e=Engine(r,f);asyncio.run(e.run_and_wait(t))
    children=r.list('task',post_group_id=t)
    assert len(children)==1 and len(f.requests)==2
    child=children[0];assert child['community']['name']=='r/test0'
    assert r.revision(child['active']['backtranslation'])['source_revision_id']==child['active']['english']
    assert r.task(t)['status']=='completed'

def test_reconfigure_preserves_history_and_reuses_ids(tmp_path):
    r,p,t,f,e=setup_group(tmp_path);asyncio.run(e.run_and_wait(t))
    old=r.list('task',post_group_id=t);before=len(r.list('revision'))
    save_plan(r,t,plan(2),r.task(t)['input_epoch']);new=prepare_variants(r,t)
    assert len(new)==3 and {x['id'] for x in new}<={x['id'] for x in old}
    assert len(r.list('revision'))==before
    assert len([x for x in r.list('task',post_group_id=t) if x.get('retired')])==3

def test_input_change_during_generation_invalidates_leaf(tmp_path):
    r,p,t,f,e=setup_group(tmp_path)
    f.hook=lambda:r.update_task(t,{'raw_input':'新的真实要求'})
    asyncio.run(e.run_and_wait(t))
    assert r.list('revision')[0]['candidate'] and len(f.requests)==1

def test_missing_plan_cannot_bypass_via_batch(tmp_path):
    r,p,t=make(tmp_path);f=FakeProvider();e=Engine(r,f)
    async def run():
        jobs=e.start_batch([t]);await e.jobs[jobs[0]['job_id']]
    asyncio.run(run());assert not f.requests and r.task(t)['status']=='paused'

def test_leaf_feedback_does_not_change_siblings(tmp_path):
    r,p,t,f,e=setup_group(tmp_path);asyncio.run(e.run_and_wait(t))
    a,b,*_=r.list('task',post_group_id=t);old=b['active'].copy()
    r.add_opinion(Opinion(task_id=a['id'],stage='english',raw_text='只改这一稿'))
    asyncio.run(e.run_and_wait(a['id'],resume=True))
    assert r.task(b['id'])['active']==old

def test_native_roundtrip_retains_group_and_selected_revision(tmp_path):
    from waypoint.transfer import ProjectTransfer
    from waypoint.repository import Repository
    r,p,t,f,e=setup_group(tmp_path/'a');asyncio.run(e.run_and_wait(t))
    child=r.list('task',post_group_id=t)[0];g=r.task(t)
    g['chosen_variants']={child['community']['name'].lower():{'task_id':child['id'],'revision_id':child['active']['english']}}
    r.put('task',g)
    archive=ProjectTransfer(r).export(p);dest=Repository(tmp_path/'b');transfer=ProjectTransfer(dest)
    preview=transfer.preview([('brand.zip',archive)]);pid=transfer.commit(preview['token'],accept_rules=True)['project_id']
    group=next(x for x in dest.list('task',project_id=pid) if not x.get('post_group_id'))
    children=dest.list('task',post_group_id=group['id']);assert len(children)==6
    choice=next(iter(group['chosen_variants'].values()))
    assert dest.revision(choice['revision_id'])['task_id']==choice['task_id']
    assert {x['id'] for x in children}.isdisjoint({x['id'] for x in r.list('task')})

def test_http_plan_gate_and_choice_are_not_approval(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    app=create_app(tmp_path,FakeProvider(),accounts_enabled=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.headers['X-Waypoint-Token']=client.get('/api/session').json()['token']
        pid=client.post('/api/projects',json={'name':'DJI'}).json()['id']
        tid=client.post('/api/tasks',json={'project_id':pid,'raw_input':'用户明确给定的想法'}).json()['id']
        assert client.post(f'/api/tasks/{tid}/communities/prepare').status_code==400
        assert client.put(f'/api/tasks/{tid}/communities',json={'items':plan(),'expected_epoch':0}).status_code==200
        child=client.post(f'/api/tasks/{tid}/communities/prepare').json()[0]
        rev=client.post(f'/api/tasks/{child["id"]}/revisions',json={'stage':'english','body':'Original text.','expected_epoch':0}).json()
        assert client.post(f'/api/tasks/{child["id"]}/choose',json={'revision_id':rev['id']}).status_code==200
        assert app.state.repo.approvals(rev['id'])==[]

def test_reddit_blocked_is_not_verified(tmp_path,monkeypatch):
    import httpx
    from waypoint.routes.communities import fetch_evidence
    async def blocked(self,url):raise httpx.ConnectError('blocked')
    monkeypatch.setattr(httpx.AsyncClient,'get',blocked)
    evidence=asyncio.run(fetch_evidence('r/drones'))
    assert evidence['status']=='unavailable' and 'rules_zh' not in evidence

def test_group_stop_preserves_completed_children(tmp_path):
    r,p,t,f,e=setup_group(tmp_path)
    original=f.generate
    async def slow(request):
        if len(f.requests)>=2:await asyncio.sleep(60)
        async for result in original(request):yield result
    f.generate=slow
    async def run():
        jid=e.start_task(t)
        while len(f.requests)<2:await asyncio.sleep(.01)
        await e.stop_job(jid);await e.jobs[jid]
    asyncio.run(run())
    assert r.task(t)['status']=='interrupted'
    assert len(r.list('revision'))==2

def test_noop_plan_save_keeps_finished_outputs_valid(tmp_path):
    r,p,t,f,e=setup_group(tmp_path);asyncio.run(e.run_and_wait(t))
    epoch=r.task(t)['input_epoch'];save_plan(r,t,plan(),epoch)
    assert r.task(t)['input_epoch']==epoch and not any(x['stale'] for x in r.list('revision'))
