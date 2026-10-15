import json
from datetime import date
import httpx
import pytest
import asyncio
import functools
from waypoint.repository import Repository
from waypoint.budget import Budget
from waypoint.workflow import Engine,RESULT_SCHEMA
from waypoint.contracts import now
from test_workflow import FakeProvider

def run_async(fn):
    @functools.wraps(fn)
    def wrapped(*args,**kwargs):return asyncio.run(fn(*args,**kwargs))
    return wrapped


def setup(root,protocol='chat',vendor='custom'):
    from waypoint.api_profiles import ApiProfiles
    from waypoint.secrets import KeyVault
    r=Repository(root);profiles=ApiProfiles(r,KeyVault(root))
    p=profiles.save({'name':'测试服务商','vendor':vendor,'protocol':protocol,'base_url':'https://models.example.com/v1',
                     'key_env':'WAYPOINT_TEST_API_KEY','json_mode':'schema'})
    p.update(models=[{'id':'real-account-model','name':'账户返回模型'}],models_checked_at=now(),
             default_model='real-account-model',prices={'real-account-model':{'input':1,'output':2,'date':date.today().isoformat()}})
    r.put('api_profile',p);s=r.save_settings({'api_enabled':True,'provider':'api','api_default_profile_id':p['id']})
    return r,profiles,p,s


def test_vault_encrypts_and_binds_keys_excludes_business_backup(tmp_path):
    from waypoint.secrets import KeyVault
    from waypoint.backup import Backup
    import zipfile
    vault=KeyVault(tmp_path);vault.set('profile-a','fake-private-key-123','https://example.com/v1|chat')
    assert vault.get('profile-a','https://example.com/v1|chat')=='fake-private-key-123'
    assert vault.get('profile-a','https://other.example.com/v1|chat') is None
    assert b'fake-private-key-123' not in (tmp_path/'private'/'api_keys.json').read_bytes()
    with zipfile.ZipFile(Backup(Repository(tmp_path)).create_backup(tmp_path/'backups')) as z:
        assert not any('api_keys' in name or name.startswith('private/') for name in z.namelist())


def test_profile_address_and_secrets_never_returned(tmp_path):
    r,profiles,p,s=setup(tmp_path)
    for address in ['http://example.com/v1','https://localhost/v1','https://127.0.0.1/v1','https://169.254.169.254/v1','https://user:pass@example.com/v1','https://example.com/v1?key=secret']:
        with pytest.raises(ValueError):profiles.save({'name':'错误','base_url':address,'protocol':'chat','vendor':'custom'})
    p=profiles.save({'name':'私有密钥','base_url':'https://keys.example.com/v1','protocol':'chat','vendor':'custom','api_key':'fake-secret-key-123'})
    assert 'fake-secret-key-123' not in json.dumps(profiles.list())
    assert 'fake-secret-key-123' not in json.dumps(r.list('api_profile'))
    assert p['has_key'] is True


@run_async
async def test_read_models_is_get_and_never_enables_or_generates(tmp_path,monkeypatch):
    r,profiles,p,s=setup(tmp_path);r.save_settings({'api_enabled':False,'provider':'codex'})
    monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-environment-key')
    calls=[]
    def handle(req):
        calls.append(req);return httpx.Response(200,json={'data':[{'id':'account-only-id','display_name':'真实目录项'}]})
    result=await profiles.read_models(p['id'],transport=httpx.MockTransport(handle))
    assert result['models']==[{'id':'account-only-id','name':'真实目录项'}]
    assert len(calls)==1 and calls[0].method=='GET' and calls[0].url.path=='/v1/models'
    assert r.settings()['api_enabled'] is False and r.settings()['provider']=='codex'
    assert r.list('budget')==[] and 'fake-environment-key' not in json.dumps(result)


@run_async
@pytest.mark.parametrize('protocol',['responses','chat','anthropic'])
async def test_protocol_payload_and_usage_budget(tmp_path,monkeypatch,protocol):
    from waypoint.providers.api import ApiProvider
    r,profiles,p,s=setup(tmp_path,protocol);monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-api-key')
    body={'title':'Title','body':'English draft.','note_zh':'说明','questions':[],'citations':[]};calls=[]
    def handle(req):
        calls.append(req);data=json.loads(req.content)
        assert data['model']=='real-account-model'
        if protocol=='responses':
            assert data['text']['format']['schema']==RESULT_SCHEMA
            result={'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(body)}]}],'usage':{'input_tokens':10,'output_tokens':20}}
        elif protocol=='chat':
            assert data['response_format']['json_schema']['schema']==RESULT_SCHEMA
            result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(body)}}],'usage':{'prompt_tokens':10,'completion_tokens':20}}
        else:
            assert data['tools'][0]['input_schema']==RESULT_SCHEMA and data['tool_choice']['name']=='waypoint_result'
            assert req.headers['x-api-key']=='fake-api-key'
            result={'stop_reason':'tool_use','content':[{'type':'tool_use','name':'waypoint_result','input':body}],'usage':{'input_tokens':10,'output_tokens':20}}
        return httpx.Response(200,json=result)
    provider=ApiProvider(Budget(r),s,p,profiles.vault,transport=httpx.MockTransport(handle))
    events=[x async for x in provider.generate({'job_id':'test-call','model':'real-account-model','prompt':'中文原意','schema':RESULT_SCHEMA,'attachments':[]})]
    assert json.loads(events[-1]['text'])==body and len(calls)==1
    entry=r.list('budget')[0];assert entry['actual']==50 and entry['state']=='settled'
    assert entry['api_profile_id']==p['id'] and entry['model']=='real-account-model'


@run_async
async def test_missing_usage_or_failed_call_blocks_all_following_providers(tmp_path,monkeypatch):
    from waypoint.providers.api import ApiProvider
    r,profiles,p,s=setup(tmp_path);monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-api-key')
    calls=[]
    def handle(req):calls.append(req);return httpx.Response(500,json={'error':{'message':'fake-api-key secret echoed'}})
    provider=ApiProvider(Budget(r),s,p,profiles.vault,transport=httpx.MockTransport(handle))
    request={'job_id':'failure','model':'real-account-model','prompt':'想法','schema':RESULT_SCHEMA,'attachments':[]}
    with pytest.raises(ValueError) as e:[x async for x in provider.generate(request)]
    assert 'fake-api-key' not in str(e.value) and r.list('budget')[0]['state']=='unknown'
    with pytest.raises(ValueError,match='待核实'):[x async for x in provider.generate(request|{'job_id':'another'})]
    assert len(calls)==1


@run_async
async def test_disabled_images_unknown_models_and_expired_prices_send_nothing(tmp_path,monkeypatch):
    from waypoint.providers.api import ApiProvider
    r,profiles,p,s=setup(tmp_path);monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-api-key')
    def handle(req):pytest.fail('guard must run before network')
    request={'job_id':'guard','model':'real-account-model','prompt':'想法','schema':RESULT_SCHEMA,'attachments':[]}
    for settings,profile,req in [(s|{'api_enabled':False},p,request),(s,p,request|{'attachments':['screenshot.png']}),
        (s,p,request|{'model':'not-in-model-list'}),(s,p|{'models_checked_at':'2000-01-01T00:00:00+00:00'},request),
        (s,p|{'prices':{'real-account-model':{'input':1,'output':2,'date':'2000-01-01'}}},request)]:
        provider=ApiProvider(Budget(r),settings,profile,profiles.vault,transport=httpx.MockTransport(handle))
        with pytest.raises(ValueError):[x async for x in provider.generate(req)]
    assert r.list('budget')==[]


@run_async
async def test_per_role_api_and_plus_never_fallback(tmp_path,monkeypatch):
    r,profiles,p,s=setup(tmp_path);r.save_settings({'provider':'codex','model_roles':{'write':'test','translate':'test'},'role_routes':{'translate':{'provider':'api','profile_id':p['id'],'model':'real-account-model'}}})
    e=Engine(r,FakeProvider());provider,choice=await e.select_provider('translate')
    assert provider.profile['id']==p['id'] and choice['model']=='real-account-model'
    provider,choice=await e.select_provider('write');assert provider is e.provider
    r.save_settings({'api_enabled':False})
    with pytest.raises(ValueError,match='未启用'):await e.select_provider('translate')


def test_key_rotation_invalidates_account_models_and_prices(tmp_path):
    r,profiles,p,s=setup(tmp_path)
    updated=profiles.save({'api_key':'fake-new-key-123'},p['id'])
    assert updated['models']==[] and updated['prices']=={} and updated['default_model']==''
    assert updated['has_key'] is True
    # Stale role choices must never prevent switching API off.
    r.save_settings({'api_enabled':False});assert r.settings()['api_enabled'] is False


@run_async
async def test_screenshot_comment_translation_uses_role_model_and_preserves_english(tmp_path,monkeypatch):
    from waypoint.providers.api import ApiProvider
    from waypoint.contracts import TaskSpec
    from waypoint.materials import Materials
    r,profiles,p,s=setup(tmp_path);monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-api-key')
    p['models'].append({'id':'translation-model','name':'回译模型'})
    p['prices']['translation-model']={'input':3,'output':4,'date':date.today().isoformat()};r.put('api_profile',p)
    r.save_settings({'provider':'codex','model_roles':{'write':'test','translate':'test'},
        'role_routes':{'translate':{'provider':'api','profile_id':p['id'],'model':'translation-model'}}})
    project=r.create_project('测试品牌')
    image=Materials(r).import_bytes(project,'fixture.png',b'\x89PNG\r\n\x1a\nfixture')
    task=r.create_task(TaskSpec(project_id=project,kind='comment',raw_input='针对截图评论',source_ids=[image['id']]))
    calls=[]
    def handle(req):
        calls.append(req);data=json.loads(req.content)
        assert data['model']=='translation-model' and 'I use this on my commute.' in data['messages'][0]['content']
        assert isinstance(data['messages'][0]['content'],str) and 'image_url' not in req.content.decode()
        body={'title':'','body':'我在通勤时使用它。','note_zh':'回译','questions':[],'citations':[]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(body)}}],
            'usage':{'prompt_tokens':10,'completion_tokens':20}})
    monkeypatch.setattr('waypoint.workflow.ApiProvider',functools.partial(ApiProvider,transport=httpx.MockTransport(handle)))
    fake=FakeProvider();engine=Engine(r,fake);job=await engine.run_and_wait(task)
    assert job['status']=='completed',job['message']
    assert len(fake.requests)==1 and len(fake.requests[0]['attachments'])==1 and len(calls)==1
    active=r.task(task)['active'];english=r.revision(active['english']);translation=r.revision(active['backtranslation'])
    assert english['body']=='I use this on my commute.' and translation['source_revision_id']==english['id']
    assert translation['body']=='我在通勤时使用它。'
    assert r.list('budget')[0]['actual']==110 and r.list('budget')[0]['model']=='translation-model'


@run_async
async def test_invalid_api_output_is_saved_without_paid_auto_repair(tmp_path,monkeypatch):
    from waypoint.providers.api import ApiProvider
    from waypoint.contracts import TaskSpec
    r,profiles,p,s=setup(tmp_path);monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-api-key')
    project=r.create_project('测试品牌');task=r.create_task(TaskSpec(project_id=project,kind='cb',target_stage='cb',raw_input='需要中文 CB'))
    calls=[]
    def handle(req):
        calls.append(req);body={'title':'','body':'English instead of Chinese.','note_zh':'说明','questions':[],'citations':[]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(body)}}],
            'usage':{'prompt_tokens':10,'completion_tokens':20}})
    monkeypatch.setattr('waypoint.workflow.ApiProvider',functools.partial(ApiProvider,transport=httpx.MockTransport(handle)))
    job=await Engine(r,FakeProvider()).run_and_wait(task)
    assert job['status']=='paused' and len(calls)==1 and len(r.list('budget'))==1
    assert r.list('revision',task_id=task)[0]['body']=='English instead of Chinese.'


def test_profile_routes_require_owner_and_csrf(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    with TestClient(create_app(tmp_path,FakeProvider()),base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/api-profiles').status_code==401
        token=c.get('/api/session').json()['token']
        assert c.post('/api/auth/register',headers={'X-Waypoint-Token':token},json={
            'username':'qa_owner','display_name':'验收账号','password':'disposable-password-2026'}).status_code==200
        assert c.post('/api/api-profiles',json={}).status_code==403
        token=c.get('/api/session').json()['token']
        result=c.post('/api/api-profiles',headers={'X-Waypoint-Token':token},json={
            'name':'测试配置','vendor':'deepseek'}).json()
        assert result['models']==[] and result['has_key'] is False
        assert c.get('/api/settings').json()['api_enabled'] is False
