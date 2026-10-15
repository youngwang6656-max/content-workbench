import asyncio,json
from datetime import datetime,timezone,timedelta
import pytest
from fastapi.testclient import TestClient
from waypoint.server import create_app
from waypoint.contracts import TaskSpec

class Reader:
    supports_web_research=True
    def __init__(self):self.requests=[];self.answer={'title':'原帖译读','body':'这是一段中文译读。','note_zh':'仅供理解','questions':[],'citations':[]}
    async def generate(self,request):
        self.requests.append(request)
        yield {'kind':'completed','text':json.dumps(self.answer),'web_sources':self.trace if hasattr(self,'trace') else []}

def setup(tmp_path):
    p=Reader();app=create_app(tmp_path,p,accounts_enabled=False)
    async def select(role):return p,{'model':'test'}
    app.state.engine.select_provider=select
    c=TestClient(app,base_url='http://127.0.0.1');c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token']
    pid=c.post('/api/projects',json={'name':'Brand'}).json()['id']
    return c,app.state.repo,p,pid

def test_confirmed_source_required_and_brand_isolation(tmp_path):
    c,r,p,pid=setup(tmp_path)
    source=c.post('/api/comment-sources',json={'project_id':pid,'mode':'text','text':'My car has a warning light.'}).json()
    assert 'id' in source
    data={'project_id':pid,'source_id':source['id'],'confirmed':False,'raw_input':'帮他排查，不编造经历'}
    assert c.post('/api/comments',json=data).status_code==400
    data['confirmed']=True
    result=c.post('/api/comments',json=data);assert result.status_code==200,result.text
    task=r.task(result.json()['id']);assert task['comment_source_id'] in task['source_ids']
    assert r.get(task['comment_source_id'],'material')['text']=='My car has a warning light.'
    other=r.create_project('Other');data['project_id']=other
    assert c.post('/api/comments',json=data).status_code==400

def test_project_source_exact_version_and_translation_does_not_advance(tmp_path):
    c,r,p,pid=setup(tmp_path)
    tid=r.create_task(TaskSpec(project_id=pid,raw_input='Idea'))
    rev=r.save_revision(tid,'idea','An early English idea.',0,title='Early')
    before=r.task(tid)
    data={'project_id':pid,'revision_id':rev['id']}
    a=c.post('/api/reading-translation',json=data);assert a.status_code==200,a.text
    b=c.post('/api/reading-translation',json=data);assert b.json()['id']==a.json()['id'];assert len(p.requests)==1
    assert r.task(tid)==before and len(r.list('revision'))==1 and not r.list('approval')
    source=c.post('/api/comment-sources',json={'project_id':pid,'mode':'project','revision_id':rev['id']}).json()
    made=c.post('/api/comments',json={'project_id':pid,'source_id':source['id'],'confirmed':True}).json()
    assert r.task(made['id'])['parent_revision_id']==rev['id']
    r.save_manual_revision(tid,'idea','Changed',0)
    assert c.post('/api/comments',json={'project_id':pid,'source_id':source['id'],'confirmed':True}).status_code==400

def test_search_filters_unobserved_old_duplicate_and_unproved_date():
    from waypoint.comment_sources import verified_posts
    today=datetime.now(timezone.utc);date=today.isoformat();url='https://www.reddit.com/r/cars/comments/abc123/question/'
    row={'url':url,'published_at':date,'date_evidence':date[:10],'original_text':'Need advice','title':'Question','recommendation':'high','reason_zh':'问题相关','angle_zh':'先询问需求','caution_zh':'规则待核对'}
    observed=[{'url':url,'title':'Question','snippet':'Published '+date[:10]+' Need advice'}]
    result=verified_posts([row,row,row|{'url':'https://evil.test/x'}],observed,10,5)
    assert len(result)==1 and result[0]['recommendation']=='high'
    assert not verified_posts([row|{'published_at':(today-timedelta(days=20)).isoformat()}],observed,10,5)
    assert not verified_posts([row],[],10,5)
    assert not verified_posts([row],observed[:1][0:0]+[{'url':url,'snippet':'No date'}],10,5)

def test_search_count_and_unsupported_provider_no_invocation(tmp_path):
    c,r,p,pid=setup(tmp_path)
    assert c.post('/api/comment-sources/search',json={'project_id':pid,'count':6}).status_code==400
    p.supports_web_research=False
    result=c.post('/api/comment-sources/search',json={'project_id':pid,'count':1})
    assert result.status_code==400 and not p.requests

def test_link_scheme_and_image_cross_brand_rejected(tmp_path):
    c,r,p,pid=setup(tmp_path)
    for url in ['http://127.0.0.1/','https://reddit.com.evil.test/r/a/comments/a/x','file:///a']:
        assert c.post('/api/comment-sources',json={'project_id':pid,'mode':'link','url':url}).status_code==400
    from waypoint.materials import Materials
    mid=Materials(r).add_text(r.create_project('Other'),'image','text')['id']
    assert c.post('/api/comment-sources',json={'project_id':pid,'mode':'screenshot','material_id':mid}).status_code==400
    assert not p.requests
