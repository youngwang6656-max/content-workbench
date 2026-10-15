import asyncio
import pytest
from test_multi_api import setup, run_async
from test_workflow import FakeProvider
from waypoint.workflow import Engine
from waypoint.usage import usage_status


class Subscription(FakeProvider):
    def __init__(self, quota): self.quota=quota; self.calls=0
    async def capabilities(self):
        self.calls+=1
        return {'auth_state':'chatgpt','plan':'plus','models':[{'model':'test'}],
                'quota':self.quota,'checked_at':'2026-09-29T00:00:00+00:00'}


@pytest.mark.parametrize('auth_state',['chatgpt','unverified'])
def test_status_distinguishes_subscription_login_from_generation_readiness(tmp_path,auth_state):
    r,p,e=configure(tmp_path,mode='codex')
    r.put('connection',{'id':'connection','auth_state':auth_state,'quota':None,'models':[]})
    status=usage_status(r)
    assert status['subscription_auth_state']==auth_state
    assert status['ready'] is False
    assert r.list('budget')==[]
    assert e.provider.calls==0


def configure(root, policy='manual', mode='api', quota=None):
    r,profiles,p,s=setup(root)
    r.save_settings({'usage_mode':mode,'switch_policy':policy,
        'model_roles':{'write':'test','translate':'test'},
        'role_routes':{role:{'provider':'codex'} for role in ('write','translate','extract','complex')}})
    provider=Subscription(quota)
    return r,p,Engine(r,provider)


@run_async
async def test_manual_api_overrides_old_plus_routes_without_plus_probe(tmp_path):
    r,p,e=configure(tmp_path)
    for role in ('write','translate','extract','complex'):
        provider,choice=await e.select_provider(role)
        assert provider.kind=='api' and choice['model']==p['default_model']
    assert e.provider.calls==0
    assert r.settings()['model_roles']['write']=='test'
    assert r.settings()['role_routes']['write']['provider']=='codex'


@run_async
async def test_manual_subscription_overrides_old_api_route(tmp_path):
    r,p,e=configure(tmp_path,mode='codex',quota={'rateLimits':{'primary':{'usedPercent':1}}})
    r.save_settings({'role_routes':{'write':{'provider':'api','profile_id':p['id'],'model':p['default_model']}}})
    provider,choice=await e.select_provider('write')
    assert provider is e.provider and choice['model']=='test'
    assert r.list('budget')==[]


@run_async
async def test_auto_checks_quota_each_stage_and_returns_to_subscription(tmp_path):
    r,p,e=configure(tmp_path,'auto',quota={'rateLimits':{'primary':{'usedPercent':100}}})
    provider,choice=await e.select_provider('write')
    assert provider.kind=='api' and choice['model']==p['default_model']
    assert usage_status(r)['switched'] is True
    e.provider.quota={'rateLimits':{'primary':{'usedPercent':2}}}
    provider,choice=await e.select_provider('translate')
    assert provider is e.provider and choice['model']=='test'
    assert usage_status(r)['effective_provider']=='codex'
    assert r.list('budget')==[]


@run_async
@pytest.mark.parametrize('quota',[None,{}, {'rateLimits':{'primary':{'usedPercent':'100'}}}])
async def test_auto_unknown_quota_never_uses_api(tmp_path,quota):
    r,p,e=configure(tmp_path,'auto',quota=quota)
    with pytest.raises(ValueError,match='无法核实'): await e.select_provider('write')
    assert r.list('budget')==[] and usage_status(r)['ready'] is False


@run_async
async def test_auto_api_off_does_not_enable_it(tmp_path):
    r,p,e=configure(tmp_path,'auto',quota={'ordinaryUsageAllowed':False})
    r.save_settings({'api_enabled':False})
    with pytest.raises(ValueError,match='API 未启用'): await e.select_provider('write')
    assert r.settings()['api_enabled'] is False and r.list('budget')==[]


def test_status_reports_price_and_budget_without_generating(tmp_path,monkeypatch):
    r,p,e=configure(tmp_path)
    p['prices']={};r.put('api_profile',p)
    status=usage_status(r)
    assert status['effective_provider']=='api' and status['model']==p['default_model']
    assert '价格' in status['message'] and status['ready'] is False
    p['prices']={p['default_model']:{'input':1,'output':2,'date':__import__('datetime').date.today().isoformat()}}
    r.put('api_profile',p);monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-key')
    assert usage_status(r)['ready'] is True
    from waypoint.budget import Budget
    b=Budget(r);entry=b.reserve('unknown',100);b.settle(entry['id'],None)
    assert '待核实' in usage_status(r)['message']


def test_invalid_policy_and_model_rejected_and_restore_disables_auto(tmp_path):
    r,p,e=configure(tmp_path)
    for patch in ({'switch_policy':'bad'},{'usage_mode':'bad'},{'api_default_model':'invented'}):
        with pytest.raises(ValueError):r.save_settings(patch)
    from waypoint.backup import Backup
    r.save_settings({'switch_policy':'auto'})
    backup=Backup(r).create_backup(tmp_path/'archives');Backup(r).restore_backup(backup)
    assert r.settings()['api_enabled'] is False
    assert r.settings()['switch_policy']=='manual' and r.settings()['usage_mode']=='codex'


@run_async
async def test_auto_never_retries_after_api_request_started(tmp_path,monkeypatch):
    r,p,e=configure(tmp_path,'auto',quota={'rateLimits':{'primary':{'usedPercent':100}}})
    from waypoint.providers.api import ApiProvider
    calls=[]
    async def fail(self,request):
        calls.append(request);raise ValueError('API 已发出，费用待核实')
        yield
    monkeypatch.setattr(ApiProvider,'generate',fail)
    monkeypatch.setattr('waypoint.workflow.prompt_for',lambda *args:'synthetic text')
    j={'id':'failure','partial':'','usage':[]}
    with pytest.raises(ValueError,match='费用待核实'):
        await e._generate(j,{'materials':[]},'english')
    assert len(calls)==1 and e.provider.calls==1


@run_async
async def test_named_configs_threshold_and_manual_selection(tmp_path):
    r,p,e=configure(tmp_path,'manual',quota={'rateLimits':{'primary':{'usedPercent':12,'windowDurationMins':300}}})
    configs=[{'id':'one','name':'配置 1','provider':'codex','model_roles':{'write':'test','translate':'test'}},
             {'id':'two','name':'配置 2','provider':'api','profile_id':p['id'],'model':p['default_model'],'api_role_models':{}}]
    r.save_settings({'usage_configs':configs,'active_usage_config_id':'one','fallback_usage_config_id':'two','auto_used_threshold':10})
    provider,choice=await e.select_provider('write');assert provider is e.provider
    r.save_settings({'switch_policy':'auto'})
    provider,choice=await e.select_provider('write');assert provider.kind=='api'
    assert usage_status(r)['config_name']=='配置 2' and '阈值' in usage_status(r)['message']
    e.provider.quota={'rateLimits':{'primary':{'usedPercent':4,'windowDurationMins':300}}}
    provider,choice=await e.select_provider('write');assert provider is e.provider
    r.save_settings({'switch_policy':'manual','active_usage_config_id':'two'})
    before=e.provider.calls;provider,choice=await e.select_provider('translate')
    assert provider.kind=='api' and e.provider.calls==before


@run_async
async def test_threshold_does_not_mistake_a_different_window_for_five_hours(tmp_path):
    r,p,e=configure(tmp_path,'auto',quota={'rateLimits':{'primary':{'usedPercent':12,'windowDurationMins':15}}})
    r.save_settings({'auto_used_threshold':10})
    provider,choice=await e.select_provider('write');assert provider is e.provider


def test_config_validation_and_deletion_preserve_selection(tmp_path):
    r,p,e=configure(tmp_path)
    configs=[{'id':'one','name':'配置 1','provider':'codex','model_roles':{'write':'test'}},
             {'id':'two','name':'配置 2','provider':'api','profile_id':p['id'],'model':p['default_model']}]
    r.save_settings({'usage_configs':configs,'active_usage_config_id':'one','fallback_usage_config_id':'two','switch_policy':'auto'})
    for patch in ({'auto_used_threshold':0},{'auto_used_threshold':101}, {'usage_configs':[configs[0]]},
                  {'auto_default_config_id':'two'},{'usage_configs':configs+[configs[0]]}):
        with pytest.raises(ValueError):r.save_settings(patch)
    assert r.settings()['usage_configs']==configs


@run_async
async def test_bad_subscription_draft_never_gets_automatic_paid_repair(tmp_path,monkeypatch):
    import json
    from waypoint.contracts import TaskSpec
    from waypoint.providers.api import ApiProvider
    r,p,e=configure(tmp_path,'auto',quota={'rateLimits':{'primary':{'usedPercent':50,'windowDurationMins':300}}})
    r.save_settings({'auto_used_threshold':90})
    project=r.create_project('synthetic');task=r.create_task(TaskSpec(project_id=project,kind='comment',raw_input='synthetic source and intent'))
    async def bad(request):
        e.provider.quota={'rateLimits':{'primary':{'usedPercent':95,'windowDurationMins':300}}}
        yield {'kind':'completed','text':json.dumps({'title':'','body':'错误的中文英文稿','note_zh':'待核对','questions':[],'citations':[]}), 'usage':{}}
    async def paid(self,request):
        pytest.fail('automatic repair must not call API')
        yield
    e.provider.generate=bad;monkeypatch.setattr(ApiProvider,'generate',paid)
    job=await e.run_and_wait(task)
    assert job['status']=='paused' and r.list('budget')==[]
    rev=r.revision(r.task(task)['active']['english']);assert rev['body']=='错误的中文英文稿' and rev['issues']


@run_async
async def test_named_subscription_translation_inherits_writing(tmp_path):
    r,p,e=configure(tmp_path,mode='codex',quota={'rateLimits':{'primary':{'usedPercent':1}}})
    r.save_settings({'usage_configs':[{'id':'one','name':'配置 1','provider':'codex','model_roles':{'write':'test'}}],'active_usage_config_id':'one'})
    provider,choice=await e.select_provider('translate');assert provider is e.provider and choice['model']=='test'


def test_config_id_cannot_inject_html(tmp_path):
    r,p,e=configure(tmp_path)
    config={'id':'bad" onclick="x','name':'bad','provider':'codex','model_roles':{'write':'test'}}
    with pytest.raises(ValueError):r.save_settings({'usage_configs':[config],'active_usage_config_id':config['id']})


def test_usage_status_requires_account_and_check_requires_csrf(tmp_path):
    from test_accounts import client,register
    app,c=client(tmp_path)
    assert c.get('/api/usage-status').status_code==401
    assert c.post('/api/usage-status/check').status_code==401
    token=register(c)
    assert c.get('/api/usage-status').status_code==200
    assert c.post('/api/usage-status/check').status_code==403
    assert c.post('/api/usage-status/check',headers={'X-Waypoint-Token':token}).status_code==200


def test_restore_named_configs_selects_subscription_and_keeps_original_choices(tmp_path):
    r,p,e=configure(tmp_path)
    configs=[{'id':'one','name':'配置 1','provider':'codex','model_roles':{'write':'test'}},
             {'id':'two','name':'配置 2','provider':'api','profile_id':p['id'],'model':p['default_model']}]
    r.save_settings({'usage_configs':configs,'active_usage_config_id':'two','auto_default_config_id':'one','fallback_usage_config_id':'two'})
    from waypoint.backup import Backup
    backup=Backup(r).create_backup(tmp_path/'archives');Backup(r).restore_backup(backup)
    assert r.settings()['active_usage_config_id']=='one'
    assert r.settings()['usage_configs']==configs and r.settings()['api_enabled'] is False
