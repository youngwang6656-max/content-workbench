"""Transient read failures may recover; generation and billing never retry."""
import asyncio
import pytest
from waypoint.providers.codex import CodexProvider,require_subscription_quota

GOOD={'rateLimits':{'primary':{'usedPercent':3}}}

class Scripted(CodexProvider):
    def __init__(self,root,replies,account='chatgpt'):
        super().__init__(root);self.replies=iter(replies);self.calls=[];self.account=account
    async def start(self):pass
    async def call(self,method,params=None,ready=True):
        self.calls.append((method,params))
        if method=='account/read':return {'account':{'type':self.account,'planType':'plus'}}
        if method=='model/list':return {'data':[{'model':'test'}]}
        if method=='account/rateLimits/read':
            reply=next(self.replies)
            if isinstance(reply,Exception):raise reply
            return reply
        raise AssertionError('Unexpected or paid operation: '+method)

def rpc_error(message,code=-32603):
    from waypoint.providers.codex import CodexRpcError
    return CodexRpcError({'code':code,'message':message})

def test_transient_quota_fetch_does_not_mean_exhausted():
    error=rpc_error('failed to fetch current rate limits: error sending request sk-secret')
    assert error.retryable and error.kind=='network'
    assert 'sk-secret' not in str(error)
    assert '额度暂不可用' not in str(error)

def test_capabilities_recovers_transient_read_only(tmp_path,monkeypatch):
    async def run():
        p=Scripted(tmp_path,[rpc_error('failed to fetch current rate limits: error sending request'),GOOD])
        report=await p.capabilities()
        assert report['auth_state']=='chatgpt' and report['generation_allowed']
        assert sum(m=='account/rateLimits/read' for m,_ in p.calls)==2
        assert report['quota_check']['attempts']==2
    asyncio.run(run())

def test_permanent_network_failure_keeps_login_but_stops(tmp_path):
    async def run():
        p=Scripted(tmp_path,[rpc_error('error sending request') for _ in range(4)])
        report=await p.capabilities()
        assert report['auth_state']=='chatgpt' and not report['generation_allowed']
        assert report['quota'] is None and report['quota_check']['attempts']==4
        assert report['quota_check']['error_kind']=='network'
        assert '重试' in report['message']
        from waypoint.usage import mode_decision
        with pytest.raises(ValueError,match='重试 3 次'):mode_decision({'switch_policy':'auto','usage_mode':'codex'},report)
    asyncio.run(run())

def test_official_auth_refresh_is_once_and_checks_account(tmp_path):
    async def run():
        p=Scripted(tmp_path,[rpc_error('HTTP 401 Unauthorized'),GOOD])
        report=await p.capabilities()
        assert report['generation_allowed']
        assert [params for m,params in p.calls if m=='account/read' and params.get('refreshToken')]==[{'refreshToken':True}]
    asyncio.run(run())

def test_refresh_cannot_switch_to_api_key(tmp_path):
    async def run():
        p=Scripted(tmp_path,[rpc_error('HTTP 401 Unauthorized'),GOOD])
        original=p.call
        async def switched(method,params=None,ready=True):
            if method=='account/read' and params.get('refreshToken'):return {'account':{'type':'apiKey'}}
            return await original(method,params,ready)
        p.call=switched
        with pytest.raises(ValueError,match='ChatGPT'):await p.read_subscription_quota()
        assert sum(m=='account/rateLimits/read' for m,_ in p.calls)==1
    asyncio.run(run())

@pytest.mark.parametrize('reply',[
    {'ordinaryUsageAllowed':False},
    {'rateLimits':{'primary':{'usedPercent':100}}},
    {},'unsupported'
])
def test_no_retry_for_depleted_malformed_or_unsupported_quota(tmp_path,reply):
    async def run():
        nonlocal reply
        if reply=='unsupported':reply=rpc_error('Unsupported method',-32601)
        p=Scripted(tmp_path,[reply,GOOD])
        with pytest.raises(ValueError):require_subscription_quota(await p.read_subscription_quota())
        assert len(p.calls)==1
    asyncio.run(run())

def test_exhausted_response_is_preserved_for_authorized_switch(tmp_path):
    async def run():
        quota={'rateLimits':{'primary':{'usedPercent':100}}}
        p=Scripted(tmp_path,[quota])
        report=await p.capabilities()
        assert report['quota']==quota and not report['generation_allowed']
        from waypoint.usage import mode_decision
        assert mode_decision({'switch_policy':'auto','usage_mode':'codex'},report)==('api',True)
    asyncio.run(run())

def test_generation_never_retries_turn_start(tmp_path):
    async def run():
        p=Scripted(tmp_path,[rpc_error('error sending request'),GOOD])
        original=p.call
        async def generate_call(method,params=None,ready=True):
            if method=='thread/start':p.calls.append((method,params));return {'thread':{'id':'t'}}
            if method=='turn/start':p.calls.append((method,params));raise rpc_error('error sending request')
            return await original(method,params,ready)
        p.call=generate_call
        with pytest.raises(ValueError):
            async for _ in p.generate({'model':'test','job_id':'j','prompt':'test','schema':{}}):pass
        assert sum(m=='account/rateLimits/read' for m,_ in p.calls)==2
        assert sum(m=='turn/start' for m,_ in p.calls)==1
        assert not p.notifications and not p.active
    asyncio.run(run())
