import asyncio,socket,json
import httpx,pytest
from waypoint import api_profiles as profiles

def dns(addresses):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(x,443)) for x in addresses]

def test_fake_ip_requires_effective_proxy_and_public_dns(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:dns(['198.18.0.164']))
    monkeypatch.setattr(profiles,'https_proxy',lambda url:'http://127.0.0.1:7897',raising=False)
    called=[]
    async def public(host,proxy):called.append((host,proxy));return ['3.173.21.63']
    monkeypatch.setattr(profiles,'public_dns',public,raising=False)
    route=asyncio.run(profiles.check_public_host('https://api.deepseek.com/v1'))
    assert route=={'proxy':'http://127.0.0.1:7897','trust_env':False}
    assert called==[('api.deepseek.com','http://127.0.0.1:7897')]
    monkeypatch.setattr(profiles,'https_proxy',lambda url:None)
    with pytest.raises(ValueError,match='Fake-IP'):asyncio.run(profiles.check_public_host('https://api.deepseek.com/v1'))

@pytest.mark.parametrize('ip',['127.0.0.1','192.168.1.20','169.254.169.254','::1','0.0.0.0'])
def test_private_addresses_never_treated_as_fake_ip(monkeypatch,ip):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:dns([ip]))
    monkeypatch.setattr(profiles,'https_proxy',lambda url:'http://127.0.0.1:7897',raising=False)
    async def forbidden(*args):pytest.fail('DoH must not allow ordinary private destinations')
    monkeypatch.setattr(profiles,'public_dns',forbidden,raising=False)
    with pytest.raises(ValueError,match='内网'):asyncio.run(profiles.check_public_host('https://api.deepseek.com/v1'))

def test_fake_ip_bad_public_dns_stays_blocked(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:dns(['198.18.0.164']))
    monkeypatch.setattr(profiles,'https_proxy',lambda url:'http://127.0.0.1:7897',raising=False)
    async def bad(*args):return ['127.0.0.1']
    monkeypatch.setattr(profiles,'public_dns',bad,raising=False)
    with pytest.raises(ValueError):asyncio.run(profiles.check_public_host('https://api.deepseek.com/v1'))

def test_proxy_bypass_is_respected(monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:7897');monkeypatch.setenv('NO_PROXY','api.deepseek.com')
    assert profiles.https_proxy('https://api.deepseek.com/v1') is None
    monkeypatch.setenv('NO_PROXY','localhost,127.0.0.1')
    assert profiles.https_proxy('https://api.deepseek.com/v1')=='http://127.0.0.1:7897'

def test_deepseek_protocol_guard_and_key_rebinding(tmp_path):
    from waypoint.repository import Repository
    r=Repository(tmp_path);service=profiles.ApiProfiles(r)
    with pytest.raises(ValueError,match='Chat Completions'):
        service.save({'vendor':'deepseek','protocol':'responses','api_key':'fake-private-key'})
    p=service.save({'vendor':'deepseek','api_key':'fake-private-key'})
    old=dict(p,protocol='responses');r.put('api_profile',old)
    service.vault.set(p['id'],'fake-private-key',profiles.binding(old))
    changed=service.save({'protocol':'chat'},p['id'])
    assert changed['has_key'] and service.vault.get(p['id'],profiles.binding(changed))=='fake-private-key'
    # The key must not follow a change to a different host or protocol family.
    foreign=service.save({'base_url':'https://elsewhere.example.com/v1'},p['id'])
    assert not foreign['has_key']

def test_public_dns_sends_no_credentials_and_keeps_tls(monkeypatch):
    calls=[];factory=httpx.AsyncClient
    def handle(request):
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        host=request.url.params['name'];kind=request.url.params['type']
        return httpx.Response(200,json={'Status':0,'Question':[{'name':host+'.'}],
            'Answer':[{'type':1,'data':'3.173.21.63'}] if kind=='A' else []})
    def client(**kwargs):
        calls.append(dict(kwargs));kwargs.pop('proxy');return factory(**kwargs,transport=httpx.MockTransport(handle))
    monkeypatch.setattr(httpx,'AsyncClient',client)
    result=asyncio.run(profiles.public_dns('api.deepseek.com','http://127.0.0.1:7897'))
    assert result==['3.173.21.63'] and calls[0]['trust_env'] is False
    assert calls[0]['proxy']=='http://127.0.0.1:7897' and calls[0].get('verify',True) is True
    assert calls[0]['follow_redirects'] is False

def test_model_request_reuses_the_verified_proxy_route(tmp_path,monkeypatch):
    from waypoint.repository import Repository
    service=profiles.ApiProfiles(Repository(tmp_path));p=service.save({'vendor':'deepseek','key_env':'WAYPOINT_TEST_API_KEY'})
    monkeypatch.setenv('WAYPOINT_TEST_API_KEY','fake-private-key');calls=[];factory=httpx.AsyncClient
    async def check(url):return {'proxy':'http://127.0.0.1:7897','trust_env':False}
    monkeypatch.setattr(profiles,'check_public_host',check)
    def handle(request):
        assert request.method=='GET' and request.url.path=='/v1/models'
        return httpx.Response(200,json={'data':[{'id':'account-model'}]})
    def client(**kwargs):
        calls.append(dict(kwargs));kwargs.pop('proxy');kwargs['transport']=httpx.MockTransport(handle);return factory(**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',client)
    result=asyncio.run(service.read_models(p['id']))
    assert result['models'][0]['id']=='account-model' and calls[0]['proxy']=='http://127.0.0.1:7897'
    assert calls[0]['trust_env'] is False and calls[0].get('verify',True) is True
    assert not service.repo.settings()['api_enabled']
