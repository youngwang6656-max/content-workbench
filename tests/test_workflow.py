import asyncio,json
from waypoint.contracts import TaskSpec,Opinion
from test_repository import make
class FakeProvider:
    def __init__(self):self.requests=[];self.hook=None
    async def capabilities(self):return {'auth_state':'chatgpt','models':[{'model':'test'}],'image':'supported'}
    async def generate(self,request):
        self.requests.append(request)
        if self.hook:self.hook();self.hook=None
        text='I use this on my commute.' if request['stage']=='english' else '这是中文内容，保留用户原意。'
        yield {'kind':'completed','text':json.dumps({'title':'','body':text,'note_zh':'老细，已保留原意。','questions':[],'citations':[]}), 'usage':{}}
    async def interrupt(self,id):pass

def setup(tmp_path):
    from waypoint.workflow import Engine
    r,p,t=make(tmp_path);r.save_settings({'model_roles':{'write':'test','translate':'test'}})
    # Existing stage/review tests operate on one valid community alternative.
    # Group validation and fan-out are covered independently in test_communities.
    from waypoint.communities import save_plan,prepare_variants
    save_plan(r,t,[{'name':name,'variants':1,'rules_zh':'测试规则','culture_zh':'测试生态','confirmed':True}
                   for name in ('r/testA','r/testB')],0)
    t=prepare_variants(r,t)[0]['id']
    provider=FakeProvider();return r,p,t,provider,Engine(r,provider)

def test_direct_english_and_translation(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    asyncio.run(e.run_and_wait(t))
    task=r.task(t);assert set(task['active'])=={'english','backtranslation'}
    tr=r.revision(task['active']['backtranslation'])
    assert tr['source_revision_id']==task['active']['english']
    assert not r.approvals(task['active']['english'])

def test_only_idea_and_five_cb(tmp_path):
    r,p,t,f,e=setup(tmp_path);r.update_task(t,{'target_stage':'idea'})
    async def run():
        await e.run_and_wait(t)
        ids=[r.create_task(TaskSpec(project_id=p,kind='cb',raw_input='我给定的人设')) for _ in range(5)]
        await asyncio.gather(*(e.run_and_wait(i) for i in ids))
        assert all(list(r.task(i)['active'])==['cb'] for i in ids)
    asyncio.run(run());assert list(r.task(t)['active'])==['idea']

def test_mid_generation_opinion_preserves_candidate(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    f.hook=lambda:r.add_opinion(Opinion(task_id=t,stage='english',raw_text='刚补充的要求'))
    asyncio.run(e.run_and_wait(t));assert r.task(t)['active']=={}
    assert r.list('revision',task_id=t)[0]['candidate'] is True

def test_one_bad_batch_entry_does_not_block(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    ids=[t,r.create_task(TaskSpec(project_id=p,kind='comment',raw_input='')),r.create_task(TaskSpec(project_id=p,kind='comment',raw_input='原帖内容'))]
    async def run():await asyncio.gather(*(e.run_and_wait(i) for i in ids))
    asyncio.run(run());assert [r.task(i)['status'] for i in ids]==['completed','paused','completed']

def test_legacy_pause_setting_does_not_interrupt_simulation(tmp_path):
    r,p,t,f,e=setup(tmp_path);r.update_task(t,{'pause_at':'idea'})
    async def run():
        await e.run_and_wait(t);assert r.task(t)['status']=='completed'
        await e.run_and_wait(t,resume=True)
    asyncio.run(run());assert [x['stage'] for x in f.requests]==['english','backtranslation']

def test_resume_does_not_skip_unresolved_issue(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    r.save_revision(t,'english','Bad 900.',expected_epoch=0,issues=[{'code':'fact'}])
    asyncio.run(e.run_and_wait(t,resume=True))
    assert f.requests[0]['stage']=='english'

def test_stale_parent_requires_relink(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    old=r.save_revision(t,'english','Original.',expected_epoch=0)
    child=r.create_task(TaskSpec(project_id=p,kind='comment',comment_kind='own',raw_input='补充评论',parent_revision_id=old['id']))
    r.save_revision(t,'english','Updated.',expected_epoch=0)
    asyncio.run(e.run_and_wait(child))
    assert len(f.requests)==0 and r.task(child)['status']=='paused'

def test_processed_feedback_stays_processed_after_translation(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    r.add_opinion(Opinion(task_id=t,stage='english',raw_text='保留转折'))
    asyncio.run(e.run_and_wait(t))
    assert all(o['status']=='processed' for o in r.list('opinion',task_id=t))
