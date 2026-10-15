import asyncio,json
import pytest
from waypoint.server import create_app
from waypoint.contracts import TaskSpec
from waypoint.communities import save_plan,prepare_variants
from test_workflow import FakeProvider

class Recommender(FakeProvider):
    async def generate(self,request):
        if request['stage']=='community_auto':
            self.requests.append(request)
            yield {'kind':'completed','text':json.dumps({'items':[{'name':'r/test1','variants':1,'reason_zh':'相关话题','culture_zh':''},{'name':'r/test2','variants':1,'reason_zh':'另一切入','culture_zh':''}]})}
        else:
            async for event in super().generate(request):yield event

def setup(tmp_path):
    p=Recommender();app=create_app(tmp_path,p,accounts_enabled=False);r=app.state.repo;e=app.state.engine
    async def selected(role,**kwargs):return p,{'model':'test','provider':'codex','provider_name':'Test','effort':'high'}
    e.select_provider=selected;pid=r.create_project('Brand');tid=r.create_task(TaskSpec(project_id=pid,raw_input='模拟讨论'))
    return app,r,e,p,tid

def test_recommendation_waits_for_selected_communities_and_counts(tmp_path):
    app,r,e,p,tid=setup(tmp_path)
    async def run():
        await e.run_and_wait(tid);t=r.task(tid)
        assert t.get('community_selection_pending') and t['status']=='paused'
        assert len(p.requests)==1 and not r.list('task',post_group_id=tid)
        with pytest.raises(ValueError):prepare_variants(r,tid)
        await e.run_and_wait(tid,resume=True);assert len(p.requests)==1
        selected=[dict(t['community_plan'][1],variants=2,confirmed=True)]
        save_plan(r,tid,selected,r.task(tid)['input_epoch'])
        await e.run_and_wait(tid,resume=True)
        children=r.list('task',post_group_id=tid)
        assert len(children)==2 and all(x['community']['name']=='r/test2' for x in children)
        assert all(x['status']=='completed' for x in children)
        assert not r.task(tid).get('community_selection_pending')
        count=len(p.requests);await e.run_and_wait(tid,resume=True);assert len(p.requests)==count
    asyncio.run(run())

def test_unconfirmed_replacement_cannot_generate_via_old_child(tmp_path):
    app,r,e,p,tid=setup(tmp_path)
    plan=[{'name':'r/test1','variants':1,'confirmed':True,'rules_zh':'','culture_zh':''}]
    save_plan(r,tid,plan,0);child=prepare_variants(r,tid)[0]
    save_plan(r,tid,[dict(plan[0],variants=2,confirmed=False)],r.task(tid)['input_epoch'])
    asyncio.run(e.run_and_wait(child['id'],resume=True))
    assert not p.requests and r.task(child['id'])['status']=='paused'

def test_invalid_confirmed_quantity_does_not_clear_pending_plan(tmp_path):
    app,r,e,p,tid=setup(tmp_path);asyncio.run(e.run_and_wait(tid));t=r.task(tid)
    with pytest.raises(ValueError):save_plan(r,tid,[dict(t['community_plan'][0],variants=4,confirmed=True)],t['input_epoch'])
    assert r.task(tid)==t
