import asyncio,threading,time
import pytest
from waypoint.contracts import Opinion,TaskSpec
from test_workflow import setup
from test_repository import make

def test_restore_preserves_cash_already_spent(tmp_path):
    from waypoint.backup import Backup
    from waypoint.budget import Budget
    r,p,t=make(tmp_path);b=Budget(r);b.add_external(1_000_000,'首次支出');backup=Backup(r).create_backup(tmp_path/'archives')
    b.add_external(16_000_000,'后续支出');Backup(r).restore_backup(backup)
    assert b.summary()['used_microusd']==17_000_000
    with pytest.raises(ValueError):b.reserve('next',10_000_000)
    assert not r.settings()['api_enabled']

def test_parent_update_during_generation_becomes_candidate(tmp_path):
    r,p,t,f,e=setup(tmp_path);parent=r.save_revision(t,'english','First.',expected_epoch=0)
    child=r.create_task(TaskSpec(project_id=p,kind='comment',comment_kind='own',parent_revision_id=parent['id'],raw_input='铺评'))
    f.hook=lambda:r.save_revision(t,'english','New parent.',expected_epoch=0)
    asyncio.run(e.run_and_wait(child))
    assert r.task(child)['status']=='paused'
    assert not r.task(child)['active']
    assert r.list('revision',task_id=child)[0]['candidate']

def test_upstream_invalidation_cascades(tmp_path):
    r,p,t,f,e=setup(tmp_path);parent=r.save_revision(t,'english','First.',expected_epoch=0)
    child=r.create_task(TaskSpec(project_id=p,kind='comment',comment_kind='own',parent_revision_id=parent['id'],raw_input='铺评'))
    cr=r.save_revision(child,'english','Reply.',expected_epoch=0)
    r.update_task(t,{'raw_input':'上游思路改变'})
    assert r.revision(cr['id'])['stale']
    assert r.task(child)['input_epoch']>0

def test_manual_save_is_atomic_against_new_opinion(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    entered=threading.Event();continue_edit=threading.Event();original=r._get
    def intercept(id,kind=None):
        value=original(id,kind)
        if id==t and kind=='task' and threading.current_thread().name=='manual':
            entered.set();continue_edit.wait(2)
        return value
    r._get=intercept;errors=[]
    def edit():
        try:r.save_manual_revision(t,'english','My edit.',0)
        except Exception as ex:errors.append(ex)
    th=threading.Thread(target=edit,name='manual');th.start()
    if not entered.wait(.3):th.join();raise AssertionError('atomic manual operation not implemented: '+str(errors))
    op=threading.Thread(target=lambda:r.add_opinion(Opinion(task_id=t,stage='english',raw_text='新意见')))
    op.start();continue_edit.set();th.join();op.join()
    assert not errors and r.task(t)['input_epoch']==2
    assert r.revision(r.task(t)['active']['english'])['stale']

def test_new_opinion_between_stages_blocks_translation(tmp_path):
    r,p,t,f,e=setup(tmp_path);original=r.save_revision;inserted=False
    def save(*args,**kwargs):
        nonlocal inserted
        result=original(*args,**kwargs)
        if args[1]=='english' and not inserted:
            inserted=True;r.add_opinion(Opinion(task_id=t,stage='english',raw_text='新要求'))
        return result
    r.save_revision=save
    asyncio.run(e.run_and_wait(t))
    assert r.task(t)['status']=='paused'
    assert 'backtranslation' not in r.task(t)['active']
    assert len(f.requests)==1

@pytest.mark.parametrize('source',['user','supervisor'])
def test_explicit_local_scope_for_every_reviewer(tmp_path,source):
    r,p,t,f,e=setup(tmp_path);a=r.save_revision(t,'english','First.\n\nSecond.',0)
    r.add_opinion(Opinion(task_id=t,stage='english',source=source,scope='selection',selection='Second.',base_revision_id=a['id'],raw_text='只改选中句'))
    asyncio.run(e.run_and_wait(t));rev=r.revision(r.task(t)['active']['english'])
    assert rev['body']=='First.\n\nI use this on my commute.'

def test_client_scope_preserves_unselected_title_characters(tmp_path):
    r,p,t,f,e=setup(tmp_path);a=r.save_revision(t,'english','First.\n\nSecond.',0,title='Driver’s commute')
    r.add_opinion(Opinion(task_id=t,stage='english',source='client',scope='selection',selection='Second.',base_revision_id=a['id'],raw_text='只改选中句'))
    asyncio.run(e.run_and_wait(t));assert r.revision(r.task(t)['active']['english'])['title']=='Driver’s commute'

def test_manual_english_enters_translation_resume(tmp_path):
    from waypoint.server import create_app
    from fastapi.testclient import TestClient
    from test_workflow import FakeProvider
    f=FakeProvider()
    with TestClient(create_app(tmp_path,f,accounts_enabled=False),base_url='http://127.0.0.1:8765') as c:
        h={'X-Waypoint-Token':c.get('/api/session').json()['token']}
        p=c.post('/api/projects',headers=h,json={'name':'项目'}).json()['id']
        t=c.post('/api/tasks',headers=h,json={'project_id':p,'raw_input':'想法'}).json()['id']
        c.post('/api/tasks/'+t+'/revisions',headers=h,json={'stage':'english','body':'My exact words.','expected_epoch':0})
        d=c.get('/api/tasks/'+t).json()
        assert d['task']['status']=='paused'

def test_project_strategy_in_actual_request(tmp_path):
    r,p,t,f,e=setup(tmp_path);project=r.get(p,'project');project['description']='面向家庭用户，避免专业长文';r.put('project',project)
    asyncio.run(e.run_and_wait(t))
    assert '面向家庭用户，避免专业长文' in f.requests[0]['prompt']

def test_unknown_old_cost_blocks_new_paid_calls(tmp_path):
    from waypoint.budget import Budget
    r,p,t=make(tmp_path);r.put('budget',{'id':'old','month':'2000-01','job_id':'old','state':'unknown','actual':None,'reserved':100})
    with pytest.raises(ValueError,match='待核实'):Budget(r).reserve('new',1)

def test_adopting_preference_keeps_previous_custom_rules(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    r.add_rule(p,'保持简洁')
    r.add_rule(p,'人物动机必须保留',append=True)
    current=next(x for x in r.rules(p) if x['project_id']==p)
    assert '保持简洁' in current['text'] and '人物动机必须保留' in current['text']

def test_parent_link_cannot_form_cycle(tmp_path):
    r,p,t,f,e=setup(tmp_path);a=r.save_revision(t,'english','Parent.',0)
    child=r.create_task(TaskSpec(project_id=p,kind='comment',raw_input='回复',parent_revision_id=a['id']))
    b=r.save_revision(child,'english','Child.',0)
    with pytest.raises(ValueError):r.update_task(t,{'parent_revision_id':b['id']})
