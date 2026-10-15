"""One click derives a simulated comment from one exact active English post."""
import time
import pytest
from fastapi.testclient import TestClient
from waypoint.contracts import TaskSpec
from waypoint.server import create_app
from test_workflow import FakeProvider

def setup(root):
    provider=FakeProvider();app=create_app(root,provider,accounts_enabled=False)
    repo=app.state.repo;pid=repo.create_project('Brand')
    repo.save_settings({'model_roles':{'write':'test','translate':'test'}})
    tid=repo.create_task(TaskSpec(project_id=pid,name='当前帖文',raw_input='中文想法'))
    rev=repo.save_revision(tid,'english','I forgot the cable again.',0,title='A full battery, no cable')
    return app,repo,provider,pid,tid,rev

def client(app):
    c=TestClient(app,base_url='http://127.0.0.1')
    c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token']
    return c

def wait(repo,tid):
    for _ in range(200):
        if repo.task(tid)['status'] not in ('queued','running'):return
        time.sleep(.01)
    raise AssertionError('Fixture generation did not finish')

def test_one_action_creates_exact_source_and_english_with_translation(tmp_path):
    app,r,p,pid,tid,rev=setup(tmp_path);original=r.task(tid);settings=r.settings()
    with client(app) as c:
        response=c.post('/api/revisions/'+rev['id']+'/quick-comment',json={'project_id':pid})
        assert response.status_code==200,response.text
        result=response.json();assert result['created'] and result['job_id']
        wait(r,result['id']);child=r.task(result['id'])
        assert child['kind']=='comment' and child['comment_kind']=='own' and child['target_stage']=='english'
        assert child['parent_revision_id']==rev['id'] and child['project_id']==pid
        source=r.get(child['comment_source_id'],'material')
        assert source['id'] in child['source_ids'] and source['parent_revision_id']==rev['id']
        assert source['text']==rev['title']+'\n\n'+rev['body']
        assert set(child['active'])=={'english','backtranslation'}
        assert r.revision(child['active']['backtranslation'])['source_revision_id']==child['active']['english']
        assert rev['body'] in p.requests[0]['prompt']
        assert r.task(tid)==original and r.settings()==settings and not r.list('approval')
        calls=len(p.requests);count=len(r.list('material'))
        repeat=c.post('/api/revisions/'+rev['id']+'/quick-comment',json={'project_id':pid}).json()
        assert repeat['id']==result['id'] and not repeat['created']
        assert len(p.requests)==calls and len(r.list('material'))==count
        r.save_revision(tid,'english','I packed the cable this time.',0)
        assert r.revision(child['active']['english'])['stale']

@pytest.mark.parametrize('invalid',['other_brand','stale','candidate','incomplete','idea','abandoned','retired','comment'])
def test_invalid_parent_has_no_mutation_or_generation(tmp_path,invalid):
    app,r,p,pid,tid,rev=setup(tmp_path)
    if invalid=='other_brand':pid=r.create_project('Other')
    elif invalid in ('abandoned','retired'):r.set_task_state(tid,**{invalid:True})
    elif invalid=='comment':r.set_task_state(tid,kind='comment')
    elif invalid=='idea':rev=r.save_revision(tid,'idea','中文思路',0)
    else:
        rev[{'incomplete':'complete'}.get(invalid,invalid)]=invalid!='incomplete';r.put('revision',rev)
    before=len(r.list('task')),len(r.list('material'))
    with client(app) as c:
        response=c.post('/api/revisions/'+rev['id']+'/quick-comment',json={'project_id':pid})
        assert response.status_code==400,response.text
        assert before==(len(r.list('task')),len(r.list('material'))) and not p.requests

def test_double_click_while_running_does_not_queue_twice(tmp_path):
    app,r,p,pid,tid,rev=setup(tmp_path)
    import asyncio
    original=p.generate
    async def slow(request):
        await asyncio.sleep(.1)
        async for event in original(request):yield event
    p.generate=slow
    with client(app) as c:
        url='/api/revisions/'+rev['id']+'/quick-comment';data={'project_id':pid}
        first=c.post(url,json=data).json();second=c.post(url,json=data).json()
        assert first['id']==second['id'] and not second['created']
        assert len(r.list('job',task_id=first['id']))==1
        wait(r,first['id'])

def test_derived_comment_reference_survives_brand_export(tmp_path):
    from waypoint.transfer import ProjectTransfer
    from waypoint.repository import Repository
    app,r,p,pid,tid,rev=setup(tmp_path/'source')
    with client(app) as c:
        result=c.post('/api/revisions/'+rev['id']+'/quick-comment',json={'project_id':pid}).json()
        wait(r,result['id'])
        copied=Repository(tmp_path/'copy');transfer=ProjectTransfer(copied)
        preview=transfer.preview([('brand.zip',ProjectTransfer(r).export(pid))])
        transfer.commit(preview['token'],accept_rules=True)
        child=next(t for t in copied.list('task') if t['kind']=='comment')
        assert child['quick_comment_source_revision_id']==child['parent_revision_id']!=rev['id']

def test_changing_comment_parent_does_not_reuse_wrong_comment(tmp_path):
    app,r,p,pid,tid,rev=setup(tmp_path)
    with client(app) as c:
        url='/api/revisions/'+rev['id']+'/quick-comment';data={'project_id':pid}
        first=c.post(url,json=data).json();wait(r,first['id'])
        other=r.create_task(TaskSpec(project_id=pid,raw_input='另一个帖文'))
        other_rev=r.save_revision(other,'english','Another post.',0)
        with pytest.raises(ValueError,match='新建'):r.update_task(first['id'],{'parent_revision_id':other_rev['id']})
        second=c.post(url,json=data).json()
        assert not second['created'] and second['id']==first['id']
        wait(r,second['id'])
