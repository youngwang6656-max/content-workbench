import asyncio
import json

from test_material_batch import Reader, setup
from waypoint.material_auto import AutoMaterialProcessor
from waypoint.materials import Materials


def test_uploaded_material_is_read_through_and_adopted_without_more_clicks(tmp_path):
    r, p, _, _, reader, engine = setup(tmp_path)
    units = [{'label': f'第 {i} 页', 'text': f'内容 {i}'} for i in range(1, 18)]
    material = Materials(r).add_text(p, '品牌资料', '原文', kind='attachment', units=units)

    async def run():
        processor = AutoMaterialProcessor(engine)
        processor.enqueue(material['id'])
        await processor.wait()

    asyncio.run(run())
    saved = r.get(material['id'], 'material')
    assert saved['auto_processing']['status'] == 'complete'
    assert saved['auto_processing']['covered'] == 17
    assert len(saved['adopted_analysis_ids']) == 3
    assert saved['text'] == '原文' and saved['trust'] == 'unverified'
    assert len(reader.requests) == 3


def test_quota_failure_pauses_without_retry_or_changing_config(tmp_path):
    r, p, _, _, reader, engine = setup(tmp_path)
    material = Materials(r).add_text(p, '资料', '原文', kind='attachment')
    second = Materials(r).add_text(p, '资料2', '原文2', kind='attachment')
    calls = []
    async def denied(role, *, allow_api=True):
        calls.append(role)
        assert role == 'read'
        raise ValueError('订阅额度暂不可核实')
    engine.select_provider = denied

    async def run():
        processor = AutoMaterialProcessor(engine)
        processor.enqueue(material['id'])
        processor.enqueue(second['id'])
        await processor.wait()

    asyncio.run(run())
    saved = r.get(material['id'], 'material')
    assert saved['auto_processing']['status'] == 'paused'
    assert '订阅额度' in saved['auto_processing']['message']
    assert saved.get('adopted_analysis_ids', []) == []
    assert r.get(second['id'], 'material')['auto_processing']['status'] == 'paused'
    assert calls == ['read']
    assert reader.requests == []


def test_old_materials_are_not_queued_or_changed_implicitly(tmp_path):
    r, p, _, old, reader, engine = setup(tmp_path)
    async def run():
        processor = AutoMaterialProcessor(engine)
        await processor.wait()
    asyncio.run(run())
    assert 'auto_processing' not in r.get(old['id'], 'material')
    assert reader.requests == []


def test_restart_pauses_inflight_material_without_reissuing_model_call(tmp_path):
    r, p, _, material, reader, engine = setup(tmp_path)
    material['auto_processing'] = {'status': 'running', 'covered': 2, 'total_units': 8}
    r.put('material', material)
    worker = AutoMaterialProcessor(engine)
    worker.recover()
    saved = r.get(material['id'], 'material')
    assert saved['auto_processing']['status'] == 'paused'
    assert saved['auto_processing']['covered'] == 2
    assert reader.requests == []


def test_upload_http_returns_before_background_read_and_preserves_original(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    reader = Reader()
    app = create_app(tmp_path / 'server', reader, accounts_enabled=False)
    project = app.state.repo.create_project('TOPDON')
    app.state.repo.save_settings({'model_roles': {'write': 'test'}})
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.headers['X-Waypoint-Token'] = client.get('/api/session').json()['token']
        response = client.post('/api/materials/upload', data={'project_id': project},
                               files={'file': ('facts.txt', b'Brand supplied source', 'text/plain')})
        assert response.status_code == 200
        material_id = response.json()['id']
        assert response.json()['auto_processing']['status'] in {'queued', 'running', 'complete'}
        # The upload response never waits on or asserts a successful model link.
        assert (app.state.repo.db.root / 'attachments' / response.json()['path']).read_bytes() == b'Brand supplied source'
        client.portal.call(app.state.material_auto.wait)
        saved = app.state.repo.get(material_id, 'material')
        assert saved['auto_processing']['status'] == 'complete'
        assert saved['trust'] == 'unverified'


def test_public_check_uses_only_open_questions_and_preserves_source_status(tmp_path):
    from waypoint.material_reading import context_material
    class PublicReader(Reader):
        supports_web_research = True
        async def generate(self, request):
            if request['stage'] == 'material_research':
                self.requests.append(request)
                assert request['web_research'] is True
                assert 'Brand secret body' not in request['prompt']
                yield {'kind': 'completed', 'text': json.dumps({
                    'summary_zh': '公开摘录显示一项待核信息', 'findings_zh': ['公开页面列出型号'],
                    'unverified_zh': ['价格无法确认']}),
                    'web_sources': [{'url': 'https://example.com/product', 'snippet': 'Product model', 'title': 'Product'}]}
            else:
                async for event in super().generate(request):
                    yield event
    r, p, _, _, _, engine = setup(tmp_path)
    reader = PublicReader(); reader.missing = ['型号是否公开']
    engine.provider = reader
    material = Materials(r).add_text(p, '品牌资料', 'Brand secret body', kind='attachment')
    async def run():
        worker = AutoMaterialProcessor(engine)
        worker.enqueue(material['id'])
        await worker.wait()
    asyncio.run(run())
    saved = r.get(material['id'], 'material')
    assert saved['auto_processing']['status'] == 'complete'
    assert saved['web_verification']['status'] == 'sources_found'
    assert saved['trust'] == 'unverified'
    assert '未构成独立事实认证' in context_material(saved)['text']
    assert len(reader.requests) == 2
