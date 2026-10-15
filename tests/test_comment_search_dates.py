from datetime import datetime,timezone,timedelta
from waypoint.comment_sources import verified_posts
import pytest

URL='https://www.reddit.com/r/dashcams/comments/abc123/buying_advice/'
def row(evidence,date=None):
 return {'url':URL,'title':'Buying advice','original_text':'Need front and rear coverage for parking.','published_at':date or datetime.now(timezone.utc).isoformat(),'date_evidence':evidence,'recommendation':'high','reason_zh':'停车监控需求匹配','angle_zh':'从供电与前后覆盖切入','caution_zh':''}
def trace(evidence):return [{'url':URL,'title':'Buying advice','snippet':evidence+' Need front and rear coverage for parking.'}]

@pytest.mark.parametrize('evidence,age,precision', [('3 days ago',3,'relative'),('9 hours ago',0,'relative'),('3天前',3,'relative'),('yesterday',1,'day')])
def test_sourced_relative_date_and_optional_caution(evidence,age,precision):
 result=verified_posts([row(evidence)],trace(evidence),10,3)
 assert len(result)==1
 assert result[0]['date_precision']==precision
 assert result[0]['date_evidence']==evidence
 assert result[0]['caution_zh']==''
 assert (datetime.now().astimezone().date()-datetime.fromisoformat(result[0]['published_at']).astimezone().date()).days in {max(0,age-1),age,age+1}

def test_calendar_boundary_day_is_kept_with_explicit_uncertainty():
 current=datetime.now().astimezone();date=(current-timedelta(days=10)).date().isoformat()
 result=verified_posts([row(date,date)],trace(date),10,3)
 assert len(result)==1
 assert result[0]['date_window_status']=='boundary'
 assert '边界' in result[0]['date_note_zh']

@pytest.mark.parametrize('format', ['%b %d %Y','%Y年%m月%d日','%d %B %Y'])
def test_other_public_day_formats(format):
 date=datetime.now().astimezone()-timedelta(days=2);evidence=date.strftime(format)
 result=verified_posts([row(evidence,date.date().isoformat())],trace(evidence),10,2)
 assert len(result)==1
 assert result[0]['date_precision']=='day'

@pytest.mark.parametrize('evidence', ['31 days ago','Tomorrow','recently','Oct 11, 1999'])
def test_unknown_future_and_old_date_still_rejected(evidence):
 assert not verified_posts([row(evidence)],trace(evidence),10,3)

def test_unobserved_relative_date_and_model_date_guess_rejected():
 assert not verified_posts([row('3 days ago')],trace('No date available'),10,3)
 date=(datetime.now().astimezone()-timedelta(days=3)).date().isoformat()
 result=verified_posts([row(date,'1999-01-01')],trace(date),10,3)
 assert not result

def test_exact_timestamp_outside_window_not_retained_as_boundary():
 value=(datetime.now(timezone.utc)-timedelta(days=10,hours=1)).isoformat()
 assert not verified_posts([row(value,value)],trace(value),10,3)

def test_duplicates_removed_and_recommendations_sorted():
 evidence='2 days ago';low=row(evidence)|{'recommendation':'low'};high=row(evidence)|{'url':URL.replace('abc123','def456')}
 observed=trace(evidence)+[trace(evidence)[0]|{'url':high['url']}]
 result=verified_posts([low,low,high],observed,10,5)
 assert len(result)==2
 assert [x['recommendation'] for x in result]==['high','low']

def test_date_read_from_observed_open_page_is_candidate_with_uncertainty():
 date=(datetime.now().astimezone()-timedelta(days=2)).date().isoformat()
 observed=[{'url':URL,'title':'Buying advice','snippet':'Total lines: 400','retrieval_method':'openPage'}]
 result=verified_posts([row(date,date)],observed,10,3)
 assert len(result)==1
 assert result[0]['date_verification']=='model_page_read'
 assert '待核对' in result[0]['date_note_zh']
 assert result[0]['verification_status']=='web_excerpt'

def test_search_only_result_cannot_claim_page_date_was_read():
 date=(datetime.now().astimezone()-timedelta(days=2)).date().isoformat()
 assert not verified_posts([row(date,date)],[{'url':URL,'title':'Buying advice','snippet':'No date','retrieval_method':'search'}],10,3)

def test_tool_date_marked_as_direct_evidence():
 result=verified_posts([row('2 days ago')],trace('2 days ago'),10,3)
 assert result[0]['date_verification']=='tool_text'

def test_official_adapter_preserves_open_page_and_late_sources(tmp_path):
 from waypoint.providers.codex import CodexProvider
 class Protocol(CodexProvider):
  async def start(self):pass
  async def call(self,method,params=None,ready=True):
   if method=='account/read':return {'account':{'type':'chatgpt'}}
   if method=='account/rateLimits/read':return {'rateLimits':{'primary':{'usedPercent':1}}}
   if method=='thread/start':return {'thread':{'id':'t'}}
   if method=='turn/start':
    for q in self.notifications:
     for i in range(4):
      q.put_nowait({'method':'item/completed','params':{'threadId':'t','item':{'type':'webSearch','action':{'type':'search'},'results':[{'url':f'https://example.com/{i}/{j}','title':'search','snippet':'text'} for j in range(30)]}}})
     q.put_nowait({'method':'item/completed','params':{'threadId':'t','item':{'type':'webSearch','action':{'type':'openPage'},'results':[{'url':URL,'title':'Buying advice','snippet':'Total lines: 400','private_field':'must not retain'}]}}})
     q.put_nowait({'method':'item/completed','params':{'threadId':'t','item':{'type':'agentMessage','text':'{}'}}})
     q.put_nowait({'method':'turn/completed','params':{'threadId':'t','turn':{'id':'turn','status':'completed'}}})
    return {'turn':{'id':'turn'}}
 async def run():
  return [x async for x in Protocol(tmp_path).generate({'job_id':'j','model':'test','prompt':'Search','schema':{},'stage':'post_research','web_research':True})]
 import asyncio
 events=asyncio.run(run())
 sources=events[-1]['web_sources'];opened=[x for x in sources if x['url']==URL]
 assert opened and opened[0]['retrieval_method']=='openPage'
 assert 'private_field' not in opened[0]

@pytest.mark.parametrize('format', ['%A %B %d %Y','%A %B %d, %Y','%a %b %d %Y'])
def test_reddit_page_date_includes_weekday(format):
 date=datetime.now().astimezone()-timedelta(days=2);evidence=date.strftime(format)
 result=verified_posts([row(evidence,date.date().isoformat())],trace(evidence),10,2)
 assert len(result)==1

@pytest.mark.parametrize('evidence', ['7d ago','9h ago','15m ago'])
def test_compact_reddit_relative_time(evidence):
 result=verified_posts([row(evidence)],trace(evidence),10,3)
 assert len(result)==1 and result[0]['date_precision']=='relative'

def test_other_action_with_page_line_metadata_can_keep_pending_date():
 date=(datetime.now().astimezone()-timedelta(days=2)).date().isoformat()
 observed=[{'url':URL,'title':'Buying advice','snippet':'Total lines: 285','retrieval_method':'other'}]
 result=verified_posts([row(date,date)],observed,10,3)
 assert len(result)==1 and result[0]['date_verification']=='model_page_read'
 assert '待核对' in result[0]['date_note_zh']

def test_other_action_search_excerpt_not_misclassified_as_page_read():
 date=(datetime.now().astimezone()-timedelta(days=2)).date().isoformat()
 observed=[{'url':URL,'title':'Buying advice','snippet':'Interesting result','retrieval_method':'other'}]
 assert not verified_posts([row(date,date)],observed,10,3)

@pytest.mark.parametrize('format', ['[%A %B %d %Y]','[%Y-%m-%d]','(%b %d, %Y)'])
def test_source_date_wrapped_in_reddit_page_punctuation(format):
 date=datetime.now().astimezone()-timedelta(days=2);evidence=date.strftime(format)
 result=verified_posts([row(evidence,date.date().isoformat())],trace(evidence),10,2)
 assert len(result)==1

def test_search_endpoint_saves_pending_page_date_and_reports_rejection(tmp_path):
 import json
 from fastapi.testclient import TestClient
 from waypoint.server import create_app
 class Reader:
  supports_web_research=True
  requests=[]
  async def generate(self,request):
   self.requests.append(request)
   day=(datetime.now().astimezone()-timedelta(days=2)).date().isoformat()
   yield {'kind':'completed','text':json.dumps({'items':[row(day,day),row(day,day)|{'url':'https://www.reddit.com/r/cars/comments/def456/question/'}],'message_zh':'原帖日期待核对。'}),
          'web_sources':[{'url':URL,'title':'Buying advice','snippet':'Total lines: 285','retrieval_method':'other'}]}
 p=Reader();app=create_app(tmp_path,p,accounts_enabled=False)
 async def select(role):return p,{'model':'test'}
 app.state.engine.select_provider=select
 c=TestClient(app,base_url='http://127.0.0.1');c.headers['X-Waypoint-Token']=c.get('/api/session').json()['token']
 pid=c.post('/api/projects',json={'name':'Brand'}).json()['id']
 response=c.post('/api/comment-sources/search',json={'project_id':pid,'count':2,'days':10})
 assert response.status_code==200,response.text
 result=response.json();assert len(result['items'])==1
 assert result['items'][0]['date_verification']=='model_page_read'
 assert result['filter_summary']=={'链接未被检索工具返回':1}
 assert result['items'][0]['caution_zh']==''
 assert len(p.requests)==1
 assert p.requests[0]['web_research'] is True
 assert not app.state.repo.list('task')
