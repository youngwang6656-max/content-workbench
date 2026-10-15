import asyncio
import json

import pytest

from waypoint.contracts import Opinion, TaskSpec
from waypoint.communities import prepare_variants, save_plan
from waypoint.repository import Repository
from waypoint.workflow import Engine
from test_simulation_flow import SimulationProvider


def setup(root, kind='comment', stage='idea'):
    repo = Repository(root)
    brand = repo.create_project('TOPDON')
    task = repo.create_task(TaskSpec(project_id=brand, kind=kind, raw_input='用户最初的想法', target_stage=stage))
    if kind == 'post':
        save_plan(repo, task, [{'name': 'r/test', 'variants': 2, 'confirmed':True}], 0)
        task = prepare_variants(repo, task)[0]['id']
    repo.save_settings({'model_roles': {'write': 'test', 'translate': 'test', 'complex': 'test'}})
    provider = SimulationProvider()
    return repo, task, provider, Engine(repo, provider)


@pytest.mark.parametrize('kind', ['post', 'comment'])
@pytest.mark.parametrize('stage', ['theme', 'idea', 'chinese', 'cb'])
def test_checkpoint_stops_then_one_action_reaches_english_without_final_approval(tmp_path, kind, stage):
    repo, tid, provider, engine = setup(tmp_path, kind, stage)
    asyncio.run(engine.run_and_wait(tid))
    task = repo.task(tid)
    checkpoint = repo.revision(task['active'][stage])
    assert 'english' not in task['active']
    with pytest.raises(ValueError, match='英文'):
        repo.pass_simulation(checkpoint['id'])
    result = repo.continue_to_english(tid, checkpoint['id'])
    assert result['changed']
    assert not repo.revision(checkpoint['id'])['stale']
    asyncio.run(engine.run_and_wait(tid, resume=True))
    task = repo.task(tid)
    english = repo.revision(task['active']['english'])
    assert english['checkpoint_revision_id'] == checkpoint['id']
    snapshot = repo.get(english['snapshot_id'], 'snapshot')
    assert snapshot['checkpoint']['id'] == checkpoint['id']
    assert repo.revision(task['active']['backtranslation'])['source_revision_id'] == english['id']
    assert not any(a.get('simulation_pass') for a in repo.approvals(checkpoint['id']))
    assert not repo.approvals(english['id'])
    repo.pass_simulation(english['id'])
    assert repo.approvals(english['id'])[0]['simulation_pass']
    assert [r['stage'] for r in provider.requests if r['stage'] != 'fact_research'] == [stage, 'english', 'backtranslation']


def test_continue_guards_exact_revision_pending_opinion_and_is_idempotent(tmp_path):
    repo, tid, _, engine = setup(tmp_path)
    asyncio.run(engine.run_and_wait(tid))
    old = repo.task(tid)['active']['idea']
    repo.add_opinion(Opinion(task_id=tid, stage='idea', base_revision_id=old, raw_text='改掉第二句'))
    with pytest.raises(ValueError):
        repo.continue_to_english(tid, old)
    asyncio.run(engine.run_and_wait(tid, resume=True))
    current = repo.task(tid)['active']['idea']
    with pytest.raises(ValueError):
        repo.continue_to_english(tid, old)
    assert repo.continue_to_english(tid, current)['changed']
    assert not repo.continue_to_english(tid, current)['changed']
    assert len(repo.approvals(current)) == 1


def test_group_resume_does_not_reset_candidate_that_has_advanced(tmp_path):
    repo, tid, _, engine = setup(tmp_path, 'post')
    asyncio.run(engine.run_and_wait(tid))
    task = repo.task(tid)
    group = task['post_group_id']
    repo.continue_to_english(tid, task['active']['idea'])
    prepare_variants(repo, group)
    assert repo.task(tid)['target_stage'] == 'english'
    asyncio.run(engine.run_and_wait(group, resume=True))
    assert repo.task(tid)['active'].get('english')
    sibling = next(t for t in repo.list('task', post_group_id=group) if t['id'] != tid)
    assert sibling['active'].get('idea') and 'english' not in sibling['active']


def test_checkpoint_dependency_and_project_round_trip(tmp_path):
    from waypoint.transfer import ProjectTransfer
    repo, tid, _, engine = setup(tmp_path / 'a')
    asyncio.run(engine.run_and_wait(tid))
    checkpoint = repo.task(tid)['active']['idea']
    repo.continue_to_english(tid, checkpoint)
    asyncio.run(engine.run_and_wait(tid, resume=True))
    repo.pass_simulation(repo.task(tid)['active']['english'])
    pid = repo.task(tid)['project_id']
    destination = Repository(tmp_path / 'b')
    transfer = ProjectTransfer(destination)
    preview = transfer.preview([('brand.zip', ProjectTransfer(repo).export(pid))])
    imported = transfer.commit(preview['token'], accept_rules=True)['project_id']
    task = destination.list('task', project_id=imported)[0]
    en = destination.revision(task['active']['english'])
    assert task['checkpoint_revision_id'] == task['active']['idea']
    assert en['checkpoint_revision_id'] == task['active']['idea']
    assert task['checkpoint_revision_id'] != checkpoint
    repo.save_manual_revision(tid, 'idea', '修改后的中文大意', repo.task(tid)['input_epoch'])
    assert repo.revision(repo.task(tid)['active']['english'])['stale']


def test_http_checkpoint_action_and_final_progress(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    import time
    provider = SimulationProvider()
    app = create_app(tmp_path, provider, accounts_enabled=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.headers['X-Waypoint-Token'] = client.get('/api/session').json()['token']
        repo = app.state.repo
        repo.save_settings({'model_roles': {'write': 'test', 'translate': 'test'}})
        pid = repo.create_project('TOPDON')
        source = client.post('/api/comment-sources', json={'project_id':pid, 'mode':'text', 'text':'A user asks for help.'}).json()
        tid = client.post('/api/comments', json={'project_id':pid, 'source_id':source['id'], 'raw_input':'中文思路先给我看',
            'target_stage':'idea', 'selection_mode':'automatic_simulation'}).json()['id']
        client.post(f'/api/tasks/{tid}/run')
        for _ in range(100):
            if repo.task(tid)['status']=='completed':break
            time.sleep(.01)
        detail = client.get(f'/api/tasks/{tid}').json()
        assert detail['task']['workflow_phase']=='checkpoint_ready'
        rid = detail['task']['active']['idea']
        response = client.post(f'/api/tasks/{tid}/to-english', json={'revision_id':rid})
        assert response.status_code==200
        for _ in range(100):
            if repo.task(tid)['status']=='completed':break
            time.sleep(.01)
        assert client.get(f'/api/tasks/{tid}').json()['task']['workflow_phase']=='final_ready'
        before = len(provider.requests)
        assert client.post(f'/api/tasks/{tid}/to-english', json={'revision_id':rid}).status_code==200
        assert len(provider.requests)==before
        en = repo.task(tid)['active']['english']
        assert client.post(f'/api/revisions/{en}/pass').status_code==200
        assert client.get(f'/api/tasks/{tid}').json()['task']['workflow_phase']=='finished'
        from waypoint.transfer import ProjectTransfer
        copied=Repository(tmp_path/'roundtrip');transfer=ProjectTransfer(copied)
        preview=transfer.preview([('comment.zip',ProjectTransfer(repo).export(pid))])
        imported=transfer.commit(preview['token'],accept_rules=True)['project_id']
        cloned=copied.list('task',project_id=imported)[0]
        assert copied.get(cloned['comment_source_id'],'material')['trust']=='simulation_selected'
        assert cloned['checkpoint_revision_id']==cloned['active']['idea']


def test_cb_task_remains_independent(tmp_path):
    repo, tid, _, engine = setup(tmp_path, 'cb', 'cb')
    asyncio.run(engine.run_and_wait(tid))
    rid = repo.task(tid)['active']['cb']
    with pytest.raises(ValueError):repo.continue_to_english(tid, rid)
    assert repo.pass_simulation(rid)['passed']


def test_final_opinion_keeps_checkpoint_valid_but_requires_new_final_pass(tmp_path):
    from waypoint.progress import task_view
    repo, tid, _, engine = setup(tmp_path)
    asyncio.run(engine.run_and_wait(tid))
    checkpoint=repo.task(tid)['active']['idea']
    repo.continue_to_english(tid,checkpoint)
    asyncio.run(engine.run_and_wait(tid,resume=True))
    english=repo.task(tid)['active']['english']
    repo.pass_simulation(english)
    repo.add_opinion(Opinion(task_id=tid,stage='english',base_revision_id=english,raw_text='开头更自然'))
    assert not repo.revision(checkpoint)['stale']
    asyncio.run(engine.run_and_wait(tid,resume=True))
    task=repo.task(tid)
    assert task['status']=='completed' and task['active']['english']!=english
    assert task_view(repo,task)['workflow_phase']=='final_ready'
    assert repo.approvals(english) and not repo.approvals(task['active']['english'])


def test_final_pass_rejects_incomplete_translation_and_running_generation(tmp_path):
    repo, tid, _, engine=setup(tmp_path,stage='english')
    asyncio.run(engine.run_and_wait(tid))
    task=repo.task(tid);english=task['active']['english']
    tr=repo.revision(task['active']['backtranslation']);tr['stale']=True;repo.put('revision',tr)
    with pytest.raises(ValueError):repo.pass_simulation(english)
    tr['stale']=False;repo.put('revision',tr)
    repo.put('job',{'id':'running','task_id':tid,'status':'running'})
    with pytest.raises(ValueError):repo.pass_simulation(english)
