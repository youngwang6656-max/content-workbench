import asyncio, json
import pytest
from fastapi.testclient import TestClient
from waypoint.server import create_app
from waypoint.contracts import TaskSpec
from waypoint.context import build_context, prompt_for


class Writer:
    supports_web_research = False
    def __init__(self): self.requests = []; self.fail = None
    async def generate(self, request):
        self.requests.append(request)
        if self.fail: raise ValueError(self.fail)
        body = ('I would start with the power connection before replacing the camera. '
                'A new unit will not help if the hardwire kit cuts power too early. '
                'Try checking the cutoff setting and saving a clip while the car is parked, '
                'then compare that with what happens overnight.') if request['stage']=='english' else '先检查电源连接，再考虑更换设备。'
        yield {'kind':'completed','text':json.dumps({'title':'','body':body,'note_zh':'','questions':[],'citations':[]}), 'usage':{}}
    async def interrupt(self, id): pass


def setup(tmp_path):
    p=Writer(); app=create_app(tmp_path,p,accounts_enabled=False); r=app.state.repo
    async def select(role, **kwargs): return p, {'model':'test','provider':'codex','provider_name':'Test'}
    app.state.engine.select_provider=select
    c=TestClient(app,base_url='http://127.0.0.1')
    c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token']
    pid=r.create_project('70mai')
    return c,app,r,p,pid


def endpoint(app,path): return next(x.endpoint for x in app.routes if getattr(x,'path','')==path)
def source(c,pid,text='Which camera should I buy?'):
    return c.post('/api/comment-sources',json={'project_id':pid,'mode':'text','text':text}).json()['id']


def test_bound_source_cannot_be_replaced_or_modified(tmp_path):
    c,app,r,p,pid=setup(tmp_path); sid=source(c,pid); sid2=source(c,pid,'Another post.')
    tid=c.post('/api/comments',json={'project_id':pid,'source_id':sid,'confirmed':True}).json()['id']
    t=r.task(tid); before=r.get(t['comment_source_id'])
    for data in ({'source_id':sid2},{'source_id':sid,'source_text':'Changed source.'}):
        response=c.post('/api/comments',json={'project_id':pid,'task_id':tid,'expected_epoch':0,'confirmed':True,**data})
        assert response.status_code==400 and '新建' in response.json()['detail']
    for patch in ({'source_ids':[]},{'parent_revision_id':'other'}):
        assert c.patch('/api/tasks/'+tid,json=patch).status_code==400
    changed=c.post('/api/comments',json={'project_id':pid,'task_id':tid,'source_id':before['id'],'expected_epoch':0,'confirmed':True,'raw_input':'回应停车问题'})
    assert changed.status_code==200,changed.text
    assert r.task(tid)['comment_source_id']==before['id'] and r.get(before['id'])==before
    assert c.post('/api/materials/'+before['id']+'/supplement',json={'text':'Replacement','complete':True}).status_code==400


@pytest.mark.parametrize('count',[1,3,5])
def test_batch_independent_fixed_sources_idempotent_and_translation(tmp_path,count):
    c,app,r,p,pid=setup(tmp_path); ids=[source(c,pid,f'Original post {i}.') for i in range(count)]
    async def run():
        call=endpoint(app,'/api/comments/batch'); data={'project_id':pid,'source_ids':ids,'request_id':'test-request','raw_input':'回应原帖，简洁自然'}
        first=await call(data); second=await call(data)
        assert [x['task_id'] for x in first['results']]==[x['task_id'] for x in second['results']]
        await asyncio.gather(*list(app.state.engine.jobs.values()))
        # This fixture deliberately produces identical English; exact same-brand
        # translations are reused while every task retains its own version link.
        tasks=r.list('task'); assert len(tasks)==count and len(p.requests)==count+1
        assert len({t['comment_source_id'] for t in tasks})==count
        for t in tasks:
            assert t['status']=='completed'
            tr=r.revision(t['active']['backtranslation']); assert tr['source_revision_id']==t['active']['english']
    asyncio.run(run())


def test_batch_validates_every_source_before_mutation(tmp_path):
    c,app,r,p,pid=setup(tmp_path); sid=source(c,pid); other=r.create_project('Other'); bad=source(c,other)
    async def run():
        with pytest.raises(ValueError): await endpoint(app,'/api/comments/batch')({'project_id':pid,'source_ids':[sid,bad],'request_id':'invalid'})
    asyncio.run(run()); assert not r.list('task') and not p.requests


@pytest.mark.parametrize('failure',['无法核实订阅额度，请检查连接','本次生成超时，结果未知，未自动重复请求'])
def test_shared_connection_failure_pauses_later_batch_calls(tmp_path,failure):
    c,app,r,p,pid=setup(tmp_path); ids=[source(c,pid,str(i)) for i in range(3)]; p.fail=failure
    async def run():
        await endpoint(app,'/api/comments/batch')({'project_id':pid,'source_ids':ids,'request_id':'fail'})
        await asyncio.gather(*list(app.state.engine.jobs.values()))
    asyncio.run(run()); assert len(p.requests)==1
    assert all(t['status']=='paused' for t in r.list('task'))


def test_shared_failure_during_repair_also_stops_later_tasks(tmp_path):
    c,app,r,p,pid=setup(tmp_path);ids=[source(c,pid,str(i)) for i in range(3)]
    async def faulty(request):
        p.requests.append(request)
        if len(p.requests)>1:raise ValueError('无法核实订阅额度，请检查连接')
        yield {'kind':'completed','text':json.dumps({'title':'','body':'中文错误回复','note_zh':'','questions':[],'citations':[]})}
    p.generate=faulty
    async def run():
        await endpoint(app,'/api/comments/batch')({'project_id':pid,'source_ids':ids,'request_id':'repair'})
        await asyncio.gather(*list(app.state.engine.jobs.values()))
    asyncio.run(run());assert len(p.requests)==2
    assert all(t['status']=='paused' for t in r.list('task'))


def test_backup_restore_rejects_running_search(tmp_path):
    from waypoint.backup import Backup
    c,app,r,p,pid=setup(tmp_path)
    backup=Backup(r);path=backup.create_backup(tmp_path/'backups')
    r.put('comment_search_job',{'id':'running-search','project_id':pid,'status':'running'})
    with pytest.raises(ValueError):backup.restore_backup(path)
    assert r.get('running-search')['status']=='running'


def test_missing_attachment_completion_cannot_rewrite_bound_snapshot(tmp_path):
    c,app,r,p,pid=setup(tmp_path);sid=source(c,pid)
    original=r.get(sid);original['missing_attachment']=True;r.put('material',original)
    tid=c.post('/api/comments',json={'project_id':pid,'source_id':sid,'confirmed':True}).json()['id']
    mid=r.task(tid)['comment_source_id'];before=r.get(mid)
    response=c.post('/api/materials/'+mid+'/complete-file',files={'file':('post.txt',b'Changed post','text/plain')})
    assert response.status_code==400 and r.get(mid)==before


def test_background_search_persists_reopens_stops_and_recovers(tmp_path):
    from waypoint.comment_jobs import CommentSearchJobs
    c,app,r,p,pid=setup(tmp_path)
    async def run():
        started=asyncio.Event(); finish=asyncio.Event(); calls=[]
        async def search(data,job_id=None,lock_held=False):
            calls.append(data); started.set(); await finish.wait()
            return {'items':[r.get(source(c,pid),'material')],'message':'Found'}
        jobs=CommentSearchJobs(app.state.engine,search)
        data={'project_id':pid,'count':3,'days':10,'keywords':'parking','request_id':'search-one'}
        first=jobs.start(data); await started.wait()
        assert jobs.start(data)['id']==first['id']
        assert jobs.latest(pid)['status']=='running' and not r.list('task')
        finish.set(); await jobs.wait()
        done=jobs.get(first['id']); assert done['status']=='completed'
        jobs.update(first['id'],{'selected_source_ids':[],'raw_input':'我的意图'})
        assert CommentSearchJobs(app.state.engine,search).latest(pid)['raw_input']=='我的意图'
        assert len(calls)==1 and jobs.latest(pid)['selected_source_ids']==[]
        finish.clear();second=jobs.start(data|{'request_id':'search-two'}); await asyncio.sleep(0)
        await jobs.stop(second['id']); assert jobs.get(second['id'])['status']=='interrupted'
        r.put('comment_search_job',second|{'status':'running'})
        recovered=CommentSearchJobs(app.state.engine,search); recovered.recover()
        assert recovered.get(second['id'])['status']=='interrupted' and not recovered.tasks
    asyncio.run(run())


def test_comment_style_peers_do_not_mix_sources_or_translation(tmp_path):
    c,app,r,p,pid=setup(tmp_path)
    first=r.create_task(TaskSpec(project_id=pid,kind='comment',raw_input='回复'))
    second=r.create_task(TaskSpec(project_id=pid,kind='comment',raw_input='回复'))
    for tid in (first,second):r.set_task_state(tid,comment_batch_id='batch')
    r.save_revision(first,'english','A different opening.',0)
    context=build_context(r,second,'english')
    assert context['peer_drafts']==[{'title':'','body':'A different opening.'}]
    assert '40–90' in prompt_for(context)
    assert not build_context(r,second,'backtranslation')['peer_drafts']


def test_batch_transaction_rolls_back_snapshots_tasks_and_receipt(tmp_path):
    c,app,r,p,pid=setup(tmp_path);ids=[source(c,pid,str(i)) for i in range(3)]
    count=len(r.list('material'));create=r._create_task;attempts=[]
    def fail_second(spec):
        attempts.append(spec)
        if len(attempts)==2:raise OSError('simulated disk write failure')
        return create(spec)
    r._create_task=fail_second
    async def run():
        with pytest.raises(OSError):await endpoint(app,'/api/comments/batch')({'project_id':pid,'source_ids':ids,'request_id':'rollback'})
    asyncio.run(run());assert not r.list('task') and not r.list('comment_batch')
    assert len(r.list('material'))==count and not p.requests


def test_batch_transfer_remaps_group_and_preserves_fixed_originals(tmp_path):
    from waypoint.repository import Repository
    from waypoint.transfer import ProjectTransfer
    c,app,r,p,pid=setup(tmp_path/'from');ids=[source(c,pid,str(i)) for i in range(3)]
    async def run():
        await endpoint(app,'/api/comments/batch')({'project_id':pid,'source_ids':ids,'request_id':'export'})
        await asyncio.gather(*list(app.state.engine.jobs.values()))
    asyncio.run(run())
    r.put('comment_search_job',{'id':'search-history','project_id':pid,'status':'completed'})
    dest=Repository(tmp_path/'to');transfer=ProjectTransfer(dest);preview=transfer.preview([('brand.zip',ProjectTransfer(r).export(pid))])
    newpid=transfer.commit(preview['token'],accept_rules=True)['project_id'];tasks=dest.list('task',project_id=newpid)
    assert len(tasks)==3 and len({t['comment_source_id'] for t in tasks})==3
    assert {t['comment_batch_id'] for t in tasks}<={t['id'] for t in tasks}
    assert not dest.list('comment_search_job') and not dest.list('comment_batch')
    for t in tasks:
        from waypoint.comment_sources import validate_source
        validate_source(dest,t)
        assert dest.revision(t['active']['backtranslation'])['source_revision_id']==t['active']['english']


def test_committed_batch_without_scheduled_jobs_recovers_without_call(tmp_path):
    c,app,r,p,pid=setup(tmp_path);ids=[source(c,pid,str(i)) for i in range(2)]
    def unscheduled(task_ids):return [{'task_id':id} for id in task_ids]
    app.state.engine.start_batch=unscheduled
    asyncio.run(endpoint(app,'/api/comments/batch')({'project_id':pid,'source_ids':ids,'request_id':'crash'}))
    app.state.engine.recover()
    assert all(t['status']=='interrupted' for t in r.list('task')) and not p.requests
