import asyncio,json
import pytest
from fastapi.testclient import TestClient
from waypoint.server import create_app
from waypoint.contracts import TaskSpec
from waypoint.repository import Repository
from waypoint.routing import choose_model


def test_local_english_word_counts():
    from waypoint.word_counts import word_counts
    assert word_counts("I'd use the A810-Lite.", 'About 3.5 hours at $100,000. https://example.com/a 中文')=={'title':4,'body':6,'total':10}
    assert word_counts('', '')=={'title':0,'body':0,'total':0}


def test_role_defaults_and_explicit_supported_efforts():
    settings={'model_roles':{x:'test' for x in ('write','translate','read','extract','complex')}}
    report={'models':[{'model':'test','supportedReasoningEfforts':[{'reasoningEffort':x} for x in ('low','medium','high')]}]}
    assert choose_model('write',report,settings)['effort']=='high'
    assert choose_model('read',report,settings)['effort']=='high'
    assert choose_model('translate',report,settings)['effort']=='low'
    assert choose_model('extract',report,settings)['effort']=='medium'
    settings['role_efforts']={'translate':'high'}
    assert choose_model('translate',report,settings)['effort']=='high'
    settings['role_efforts']['translate']='xhigh'
    with pytest.raises(ValueError):choose_model('translate',report,settings)


def test_config_efforts_validate_and_follow_active_config(tmp_path):
    from waypoint.usage import config_settings
    r=Repository(tmp_path)
    configs=[{'id':'one','name':'配置1','provider':'codex','model_roles':{'write':'test'},'role_efforts':{'translate':'low'}}]
    saved=r.save_settings({'usage_configs':configs,'active_usage_config_id':'one'})
    assert config_settings(saved,'one')['role_efforts']=={'translate':'low'}
    with pytest.raises(ValueError):r.save_settings({'role_efforts':{'translate':'invalid'}})


def test_brand_sort_activity_ignores_readonly_jobs(tmp_path):
    r=Repository(tmp_path);a=r.create_project('Old');b=r.create_project('New')
    for id,date in ((a,'2026-10-01T00:00:00+00:00'),(b,'2026-10-02T00:00:00+00:00')):
        p=r.get(id);p['created_at']=date;r.put('project',p)
    t=r.create_task(TaskSpec(project_id=a,raw_input='中文想法'));r.set_task_state(t,updated_at='2026-10-03T00:00:00+00:00')
    assert r.projects(sort='added')[0]['id']==b
    assert r.projects(sort='modified')[0]['id']==a
    r.put('comment_search_job',{'id':'search','project_id':b,'updated_at':'2026-10-04T00:00:00+00:00'})
    assert r.projects(sort='modified')[0]['id']==a


def test_user_and_agent_manuals_served_readonly_without_model(tmp_path):
    app=create_app(tmp_path,accounts_enabled=False)
    c=TestClient(app,base_url='http://127.0.0.1')
    user=c.get('/api/manual');agent=c.get('/api/manual/agent')
    assert user.status_code==200 and '一篇原帖' in user.json()['markdown']
    assert agent.status_code==200 and '不要' in agent.text and 'API' in agent.text
    assert not app.state.repo.list('job') and not app.state.repo.list('budget')


def test_same_english_reuses_exact_translation_without_new_call(tmp_path):
    from test_comment_jobs import setup,source
    c,app,r,p,pid=setup(tmp_path);sid=source(c,pid)
    tid=c.post('/api/comments',json={'project_id':pid,'source_id':sid,'confirmed':True}).json()['id']
    async def run():
        e=app.state.engine;await e.run_and_wait(tid)
        first=r.task(tid);en=r.revision(first['active']['english']);tr=r.revision(first['active']['backtranslation'])
        calls=len(p.requests)
        r.save_manual_revision(tid,'english',en['body'],first['input_epoch'],title=en['title'])
        await e.run_and_wait(tid,resume=True)
        latest=r.task(tid);new=r.revision(latest['active']['backtranslation'])
        assert new['source_revision_id']==latest['active']['english'] and new['id']!=tr['id']
        assert new['body']==tr['body'] and len(p.requests)==calls
    asyncio.run(run())


def test_recent_community_evidence_reused_and_force_refresh(tmp_path,monkeypatch):
    from test_community_research import SearchProvider,client_app
    p=SearchProvider();app=client_app(tmp_path,monkeypatch,p)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token']
        pid=c.post('/api/projects',json={'name':'Brand'}).json()['id']
        tid=c.post('/api/tasks',json={'project_id':pid,'raw_input':'主题'}).json()['id']
        path=f'/api/tasks/{tid}/communities/research';data={'name':'r/AskAMechanic'}
        first=c.post(path,json=data);assert first.status_code==200
        second=c.post(path,json=data).json()
        assert second['cache_hit'] and len(p.requests)==1
        c.post(path,json=data|{'refresh':True});assert len(p.requests)==2


def test_partial_ecology_preserves_visible_sample_summary():
    from waypoint.community_research import web_evidence
    from test_community_research import answer,URLS
    trace=[{'url':u,'title':'Source','snippet':'Retrieved'} for u in URLS[:2]]
    result=web_evidence('r/AskAMechanic',answer(),trace)
    assert result['sample_count']==1 and result['culture_zh'] and result['status']=='partial'
    assert result['culture_confidence']=='limited'


def test_direct_rule_failure_keeps_overview_and_recent_posts():
    import httpx
    from waypoint.routes.communities import fetch_evidence
    def handler(request):
        if 'rules.json' in request.url.path:return httpx.Response(403)
        if 'about.json' in request.url.path:return httpx.Response(200,json={'data':{'title':'Community','description':'Rules in sidebar'}})
        return httpx.Response(200,json={'data':{'children':[{'data':{'title':'Recent question','selftext':'Original content','permalink':'/r/test/comments/abc/post/'}}]}})
    result=asyncio.run(fetch_evidence('r/test',transport=httpx.MockTransport(handler)))
    assert result['status']=='partial' and len(result['sources'])==2
    assert result['failures'][0]['http_status']==403
    assert any('/new.json' in x['url'] for x in result['sources'])


def test_fallback_write_model_preserves_translate_low_role(tmp_path):
    from waypoint.workflow import Engine
    class Provider:
        async def capabilities(self):return {'auth_state':'chatgpt','quota':{'rateLimits':{'primary':{'usedPercent':1}}},'models':[{'model':'test','supportedReasoningEfforts':[{'reasoningEffort':x} for x in ('low','medium','high')]}]}
    r=Repository(tmp_path);r.save_settings({'usage_mode':'codex','model_roles':{'write':'test'}});e=Engine(r,Provider())
    # Legacy configurations without a dedicated translate model still use the
    # requested light role, rather than inheriting write's high effort.
    provider,choice=asyncio.run(e.select_provider('translate'))
    assert choice['model']=='test' and choice['effort']=='low'


def test_translation_reuse_preserves_manual_correction(tmp_path):
    from test_comment_jobs import setup,source
    c,app,r,p,pid=setup(tmp_path);sid=source(c,pid)
    tid=c.post('/api/comments',json={'project_id':pid,'source_id':sid,'confirmed':True}).json()['id']
    async def run():
        await app.state.engine.run_and_wait(tid)
        t=r.task(tid);en=r.revision(t['active']['english'])
        corrected=r.save_manual_revision(tid,'backtranslation','这是用户修正后的准确译文。',t['input_epoch'])
        t=r.task(tid);r.save_manual_revision(tid,'english',en['body'],t['input_epoch'],title=en['title'])
        calls=len(p.requests);await app.state.engine.run_and_wait(tid,resume=True)
        tr=r.revision(r.task(tid)['active']['backtranslation'])
        assert tr['body']==corrected['body'] and len(p.requests)==calls
    asyncio.run(run())


@pytest.mark.parametrize('count',[0,2])
def test_direct_ecology_requires_three_samples(tmp_path,monkeypatch,count):
    import waypoint.routes.communities as routes
    from test_community_research import SearchProvider,client_app
    p=SearchProvider();app=client_app(tmp_path,monkeypatch,p)
    async def direct(name):
        return {'name':name,'checked_at':'2026-10-13T00:00:00+00:00','status':'retrieved','message':'已读取',
            'sources':[{'url':'https://www.reddit.com/'+name+'/about/rules.json','content':[]},
            {'url':'https://www.reddit.com/'+name+'/about.json','content':{}},
            {'url':'https://www.reddit.com/'+name+'/new.json','content':[{'title':f'Question {i}','selftext':'Need advice'} for i in range(count)]}]}
    monkeypatch.setattr(routes,'fetch_evidence',direct)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token'];pid=app.state.repo.create_project('Brand')
        tid=app.state.repo.create_task(TaskSpec(project_id=pid,raw_input='主题'))
        data=c.post(f'/api/tasks/{tid}/communities/research',json={'name':'r/AskAMechanic'}).json()
        assert data['status']=='partial' and data['sample_count']==count
        assert ('不能代表整个社群' in data['culture_zh']) if count else not data['culture_zh']


def test_web_fallback_accepts_already_retrieved_rule_source(tmp_path,monkeypatch):
    import waypoint.routes.communities as routes
    from test_community_research import SearchProvider,client_app,BASE,URLS,answer
    class Provider(SearchProvider):
        async def generate(self,request):
            self.requests.append(request);data=answer();data['sources'][0]['url']=BASE+'about/rules.json'
            yield {'kind':'completed','text':json.dumps(data),'web_sources':[{'url':u,'title':'Post'} for u in URLS[1:]]}
    p=Provider();app=client_app(tmp_path,monkeypatch,p)
    async def partial(name):return {'name':name,'status':'partial','message':'部分资料','checked_at':'2026-10-13',
        'sources':[{'url':BASE+'about/rules.json','content':[{'name':'Titles','description':'Use meaningful titles'}]}]}
    monkeypatch.setattr(routes,'fetch_evidence',partial)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token'];pid=app.state.repo.create_project('Brand')
        tid=app.state.repo.create_task(TaskSpec(project_id=pid,raw_input='主题'))
        data=c.post(f'/api/tasks/{tid}/communities/research',json={'name':'r/AskAMechanic'}).json()
        assert data['rules_zh'] and data['sample_count']==3 and data['direct_sources']


def test_legacy_manual_translation_does_not_restore_superseded_text(tmp_path):
    from waypoint.translation_cache import cached_translation
    from waypoint.context import build_context
    from test_comment_jobs import setup,source
    c,app,r,p,pid=setup(tmp_path);sid=source(c,pid)
    tid=c.post('/api/comments',json={'project_id':pid,'source_id':sid,'confirmed':True}).json()['id']
    asyncio.run(app.state.engine.run_and_wait(tid));t=r.task(tid);en=r.revision(t['active']['english'])
    corrected=r.save_manual_revision(tid,'backtranslation','用户改过的译文',t['input_epoch']);corrected.pop('translation_rules');r.put('revision',corrected)
    r.save_manual_revision(tid,'english',en['body'],r.task(tid)['input_epoch'],title=en['title'])
    assert cached_translation(r,build_context(r,tid,'backtranslation',r.task(tid)['active']['english'])) is None


def test_brand_dates_sort_by_instant_not_timezone_text(tmp_path):
    r=Repository(tmp_path);a=r.create_project('Earlier');b=r.create_project('Later')
    for id,date in ((a,'2026-10-13T08:00:00+08:00'),(b,'2026-10-13T01:00:00+00:00')):
        p=r.get(id);p['created_at']=date;r.put('project',p)
    assert r.projects(sort='added')[0]['id']==b


def test_web_rules_fallback_keeps_already_read_api_post_samples(tmp_path,monkeypatch):
    import waypoint.routes.communities as routes
    from test_community_research import SearchProvider,client_app,BASE,URLS
    class Provider(SearchProvider):
        async def generate(self,request):
            from test_community_research import answer
            self.requests.append(request)
            yield {'kind':'completed','text':json.dumps(answer()),'web_sources':[{'url':BASE,'title':'Rules'}]}
    p=Provider();app=client_app(tmp_path,monkeypatch,p)
    async def partial(name):return {'name':name,'status':'partial','message':'规则读取失败','checked_at':'2026-10-13',
        'sources':[{'url':BASE+'new.json','content':[{'title':'Question','selftext':'Original text','permalink':u.replace('https://www.reddit.com','')} for u in URLS[1:]]}]}
    monkeypatch.setattr(routes,'fetch_evidence',partial)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token'];pid=app.state.repo.create_project('Brand')
        tid=app.state.repo.create_task(TaskSpec(project_id=pid,raw_input='主题'))
        data=c.post(f'/api/tasks/{tid}/communities/research',json={'name':'r/AskAMechanic'}).json()
        assert data['rules_zh'] and data['sample_count']==3 and data['culture_zh']


def test_archiving_material_updates_brand_order_without_existing_task(tmp_path):
    from waypoint.materials import Materials
    r=Repository(tmp_path);a=r.create_project('Older');b=r.create_project('Newer')
    for id,date in ((a,'2026-10-01T00:00:00+00:00'),(b,'2026-10-02T00:00:00+00:00')):
        p=r.get(id);p['created_at']=date;r.put('project',p)
    m=Materials(r).add_text(a,'Old material','Brand information');m['created_at']='2026-10-01T01:00:00+00:00';r.put('material',m)
    assert r.projects(sort='modified')[0]['id']==b
    Materials(r).archive(m['id'])
    assert r.projects(sort='modified')[0]['id']==a
