import asyncio,json
import pytest
from fastapi.testclient import TestClient
from waypoint.server import create_app
from test_workflow import FakeProvider

BASE='https://www.reddit.com/r/AskAMechanic/'
URLS=[BASE]+[BASE+f'comments/post{i}/sample/' for i in range(3)]

def answer():
    return {'rules_zh':'标题需描述具体问题，禁止广告和 AI 内容。','culture_zh':'三个样本侧重具体故障与排查步骤，不能代表整个社群。',
            'sources':[{'url':url,'kind':'rules' if i==0 else 'posts','evidence':'来自该页面的测试摘要。'} for i,url in enumerate(URLS)]}

class SearchProvider(FakeProvider):
    supports_web_research=True
    async def generate(self,request):
        self.requests.append(request)
        yield {'kind':'completed','text':json.dumps(answer()),'web_sources':[{'url':u,'title':'Official Reddit source','snippet':'Retrieved page'} for u in URLS]}

def client_app(tmp_path,monkeypatch,provider):
    import waypoint.routes.communities as routes
    async def blocked(name):return {'name':name,'status':'unavailable','sources':[],'http_status':403,'message':'Reddit HTTP 403','checked_at':'2026-09-29'}
    monkeypatch.setattr(routes,'fetch_evidence',blocked)
    app=create_app(tmp_path,provider,accounts_enabled=False)
    async def selected(role):return provider,{'model':'test','effort':None}
    app.state.engine.select_provider=selected
    return app

def test_blocked_json_uses_explicit_subscription_research_and_keeps_plan(tmp_path,monkeypatch):
    provider=SearchProvider();app=client_app(tmp_path,monkeypatch,provider)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token']
        pid=c.post('/api/projects',json={'name':'Private brand'}).json()['id']
        tid=c.post('/api/tasks',json={'project_id':pid,'raw_input':'private draft must not go to web search'}).json()['id']
        before=app.state.repo.task(tid).copy()
        response=c.post(f'/api/tasks/{tid}/communities/research',json={'name':'r/AskAMechanic'})
        assert response.status_code==200
        data=response.json();assert data['status']=='web_retrieved' and data['sample_count']==3
        assert data['retrieval']=='codex_web_search' and data['direct_failure']['http_status']==403
        assert data['rules_zh'] and data['culture_zh'] and len(data['sources'])==4
        assert provider.requests[0]['web_research'] is True
        assert 'private draft' not in provider.requests[0]['prompt'] and 'Private brand' not in provider.requests[0]['prompt']
        after=app.state.repo.task(tid)
        assert after.get('community_plan')==before.get('community_plan') and after['raw_input']==before['raw_input']
        assert after['community_evidence'][-1]['status']=='web_retrieved'
        assert app.state.repo.settings()['api_enabled'] is False

def test_sources_must_be_observed_by_tool_and_belong_to_exact_community():
    from waypoint.community_research import web_evidence
    data=answer();trace=[{'url':u,'title':'Actual title','snippet':'Tool snippet'} for u in URLS]
    for urls in [[],[{'url':'https://www.reddit.com/r/Other/'}],[{'url':'https://www.reddit.com.evil.test/r/AskAMechanic/'}]]:
        with pytest.raises(ValueError):web_evidence('r/AskAMechanic',data,urls)
    only_rules=web_evidence('r/AskAMechanic',data,trace[:1])
    assert only_rules['status']=='partial' and only_rules['rules_zh'] and not only_rules['culture_zh']
    assert only_rules['sample_count']==0
    invented=answer();invented['sources']=[{'url':BASE+'wiki/invented','kind':'rules','evidence':'Unsupported'}]
    with pytest.raises(ValueError):web_evidence('r/AskAMechanic',invented,trace)

def test_unsupported_provider_never_receives_web_or_paid_call(tmp_path,monkeypatch):
    provider=FakeProvider();app=client_app(tmp_path,monkeypatch,provider)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token']
        pid=c.post('/api/projects',json={'name':'Test'}).json()['id']
        tid=c.post('/api/tasks',json={'project_id':pid,'raw_input':'Original'}).json()['id']
        data=c.post(f'/api/tasks/{tid}/communities/research',json={'name':'r/AskAMechanic'}).json()
        assert data['status']=='unavailable' and 'rules_zh' not in data
        assert not provider.requests and '联网' in data['message']

def test_provider_scopes_web_search_and_retains_tool_metadata(tmp_path):
    from waypoint.providers.codex import CodexProvider
    class Protocol(CodexProvider):
        async def start(self):pass
        async def call(self,method,params=None,ready=True):
            if method=='account/read':return {'account':{'type':'chatgpt'}}
            if method=='account/rateLimits/read':return {'rateLimits':{'primary':{'usedPercent':1}}}
            if method=='thread/start':self.started=params;return {'thread':{'id':'t'}}
            if method=='turn/start':
                for queue in self.notifications:
                    queue.put_nowait({'method':'item/completed','params':{'threadId':'t','item':{'type':'webSearch','results':[{'url':BASE,'title':'Actual page','snippet':'Rule source','thumbnail_url':'do not collect'}]}}})
                    queue.put_nowait({'method':'item/completed','params':{'threadId':'t','item':{'type':'agentMessage','text':'{}'}}})
                    queue.put_nowait({'method':'turn/completed','params':{'threadId':'t','turn':{'id':'turn','status':'completed'}}})
                return {'turn':{'id':'turn'}}
    async def run():
        p=Protocol(tmp_path)
        request={'job_id':'j','model':'test','prompt':'Read public rules','schema':{},'stage':'community_research','web_research':True}
        events=[x async for x in p.generate(request)]
        assert p.started['config']['web_search']=='live' and p.started['config']['features.shell_tool'] is False
        assert events[-1]['web_sources']==[{'url':BASE,'title':'Actual page','snippet':'Rule source'}]
        events=[x async for x in p.generate(request|{'web_research':False,'stage':'english'})]
        assert p.started['config']['web_search']=='disabled' and not events[-1].get('web_sources')
        with pytest.raises(ValueError):[x async for x in p.generate(request|{'stage':'english'})]
    asyncio.run(run())
