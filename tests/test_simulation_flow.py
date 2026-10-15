import asyncio
import json

import pytest

from waypoint.communities import prepare_variants, save_plan
from waypoint.contracts import TaskSpec
from waypoint.workflow import Engine
from test_repository import make


class SimulationProvider:
    supports_web_research = True

    def __init__(self):
        self.requests = []

    async def capabilities(self):
        return {'auth_state': 'chatgpt', 'models': [{'model': 'test'}]}

    async def generate(self, request):
        self.requests.append(request)
        if request['stage'] == 'community_auto':
            yield {'kind': 'completed', 'text': json.dumps({'items': [
                {'name': 'r/first', 'variants': 2, 'reason_zh': '讨论相关设备',
                 'culture_zh': '偏好具体问题'}]}), 'usage': {}}
            return
        if request['stage'] == 'fact_research':
            answer = {'summary_zh': '厂商规格仍待核对', 'claims': [
                {'claim_zh': '续航 90 小时', 'status': 'supported',
                 'source_urls': ['https://example.com/specs']}]
            }
            yield {'kind': 'completed', 'text': json.dumps(answer), 'web_sources': []}
            return
        answer = {'title': 'Question about a scanner' if request['stage'] == 'english' else '',
                  'body': 'This scanner lasts 90 hours.' if request['stage'] == 'english' else '这是一份中文回译。',
                  'note_zh': '老细，按想法完成。', 'questions': ['续航仍待核对'] if request['stage'] == 'english' else [],
                  'citations': []}
        yield {'kind': 'completed', 'text': json.dumps(answer), 'usage': {}}

    async def interrupt(self, job_id):
        pass


def plan():
    return [{'name': 'r/first', 'variants': 2, 'rules_zh': '禁止广告',
             'culture_zh': '喜欢具体问题', 'confirmed': True}]


def test_selected_community_keeps_unverified_rules_and_history(tmp_path):
    r, _, group_id = make(tmp_path)
    save_plan(r, group_id, plan(), 0)
    children = prepare_variants(r, group_id)
    assert len(children) == 2
    assert all(child['community']['confirmed'] is True for child in children)


def test_pass_is_per_candidate_and_abandon_only_when_multiple_active(tmp_path):
    r, _, group_id = make(tmp_path)
    save_plan(r, group_id, plan(), 0)
    first, second = prepare_variants(r, group_id)
    a = r.save_revision(first['id'], 'english', 'First.', expected_epoch=first['input_epoch'])
    b = r.save_revision(second['id'], 'english', 'Second.', expected_epoch=second['input_epoch'])
    r.save_revision(first['id'], 'backtranslation', '第一篇。', expected_epoch=first['input_epoch'], source_revision_id=a['id'])
    r.save_revision(second['id'], 'backtranslation', '第二篇。', expected_epoch=second['input_epoch'], source_revision_id=b['id'])
    r.pass_simulation(a['id'])
    r.pass_simulation(b['id'])
    assert len(r.approvals(a['id'])) == len(r.approvals(b['id'])) == 1
    r.set_task_state(first['id'], status='completed')
    r.set_task_state(second['id'], status='completed')
    r.abandon_variant(first['id'])
    assert r.task(first['id'])['abandoned'] is True
    assert r.revision(a['id'])['body'] == 'First.'
    assert [child['id'] for child in prepare_variants(r, group_id)] == [second['id']]
    with pytest.raises(ValueError, match='最后'):
        r.abandon_variant(second['id'])


def test_unverified_claim_is_kept_outside_english_and_does_not_pause(tmp_path):
    r, _, group_id = make(tmp_path)
    save_plan(r, group_id, plan(), 0)
    child = prepare_variants(r, group_id)[0]
    r.save_settings({'model_roles': {'write': 'test', 'translate': 'test'}})
    provider = SimulationProvider()
    engine = Engine(r, provider)
    asyncio.run(engine.run_and_wait(child['id']))
    task = r.task(child['id'])
    assert task['status'] == 'completed'
    revision = r.revision(task['active']['english'])
    assert revision['body'] == 'This scanner lasts 90 hours.'
    assert revision['fact_check']['claims'][0]['status'] == 'unverified'
    assert '续航仍待核对' in revision['questions']
    assert any(request['stage'] == 'fact_research' for request in provider.requests)
    assert r.revision(task['active']['backtranslation'])['source_revision_id'] == revision['id']


def test_ai_communities_wait_for_human_selection_before_candidates(tmp_path):
    r, _, group_id = make(tmp_path)
    r.save_settings({'model_roles': {'write': 'test', 'translate': 'test', 'complex': 'test'}})
    provider = SimulationProvider()
    engine = Engine(r, provider)
    asyncio.run(engine.run_and_wait(group_id))
    assert r.task(group_id)['status'] == 'paused'
    assert r.task(group_id)['community_selection_pending']
    children = r.list('task', post_group_id=group_id)
    assert not children and len(provider.requests)==1
    assert any(request['stage'] == 'community_auto' for request in provider.requests)


def test_http_pass_and_remove_require_current_revision_and_multiple_candidates(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app

    app = create_app(tmp_path, SimulationProvider(), accounts_enabled=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.headers['X-Waypoint-Token'] = client.get('/api/session').json()['token']
        r = app.state.repo
        brand = r.create_project('TOPDON')
        group = r.create_task(TaskSpec(project_id=brand, raw_input='讨论扫描仪'))
        save_plan(r, group, plan(), 0)
        first, second = prepare_variants(r, group)
        rev = r.save_revision(first['id'], 'english', 'First.', expected_epoch=first['input_epoch'])
        r.save_revision(first['id'], 'backtranslation', '第一篇。', expected_epoch=first['input_epoch'], source_revision_id=rev['id'])
        r.set_task_state(first['id'], status='completed')
        r.set_task_state(second['id'], status='completed')
        assert client.post(f'/api/revisions/{rev["id"]}/pass').status_code == 200
        assert client.post(f'/api/tasks/{first["id"]}/abandon').status_code == 200
        assert client.post(f'/api/tasks/{second["id"]}/abandon').status_code == 400
        assert client.post(f'/api/revisions/{rev["id"]}/pass').status_code == 400


def test_comment_source_can_be_selected_for_simulation_without_claiming_user_confirmation(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    app=create_app(tmp_path,SimulationProvider(),accounts_enabled=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.headers['X-Waypoint-Token']=client.get('/api/session').json()['token']
        brand=app.state.repo.create_project('70mai')
        source=client.post('/api/comment-sources',json={'project_id':brand,'mode':'text','text':'Original user question.'}).json()
        result=client.post('/api/comments',json={'project_id':brand,'source_id':source['id'],
            'source_text':source['text'],'raw_input':'给出有用回答','selection_mode':'automatic_simulation'})
        assert result.status_code==200
        task=app.state.repo.task(result.json()['id'])
        material=app.state.repo.get(task['comment_source_id'],'material')
        assert material['trust']=='simulation_selected'
