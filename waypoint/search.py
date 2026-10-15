"""Public read-only Reddit lookup; never fabricates a result when access fails."""
import re
from datetime import datetime,timezone,timedelta
import httpx

def parse_posts(data,since):
    rows=[]
    for item in data.get('data',{}).get('children',[]):
        d=item.get('data',{});path=d.get('permalink','');ts=d.get('created_utc')
        if not re.fullmatch(r'/r/[A-Za-z0-9_]+/comments/[A-Za-z0-9]+/[^?#]*/?',path):continue
        if not isinstance(ts,(int,float)) or ts<since or ts>datetime.now(timezone.utc).timestamp()+300:continue
        text=d.get('selftext','')
        if text in ('[removed]','[deleted]'):continue
        rows.append({'url':'https://www.reddit.com'+path,'original_text':d.get('title','')+'\n\n'+text,
            'published_at':datetime.fromtimestamp(ts,timezone.utc).isoformat(),'verification_status':'retrieved',
            'reason_zh':'按你指定的关键词、社群与时间检索；请结合原帖判断是否适合评论。','community':d.get('subreddit','')})
    return rows

async def find_posts(communities,keywords,days=10):
    if not keywords.strip():raise ValueError('请填写关键词')
    if not isinstance(days,int) or not 1<=days<=365:raise ValueError('时间范围为一至三百六十五天')
    subs=[x.strip().removeprefix('r/') for x in communities.split(',') if x.strip()]
    if any(not re.fullmatch('[A-Za-z0-9_]{1,30}',s) for s in subs):raise ValueError('社群名称只填写 r/ 后面的部分，多个用英文逗号分隔')
    q=keywords[:300]
    if subs:q+=' ('+' OR '.join('subreddit:'+s for s in subs)+')'
    try:
        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response=await client.get('https://www.reddit.com/search.json',params={'q':q,'sort':'new','limit':50,'raw_json':1},headers={'User-Agent':'waypoint-personal-workbench/0.1 (read-only content research)'})
        if response.status_code!=200:raise ValueError()
        return parse_posts(response.json(),(datetime.now(timezone.utc)-timedelta(days=days)).timestamp())
    except (ValueError,httpx.HTTPError):raise ValueError('站点暂不允许读取或网络不可用。未生成替代结果，请粘贴原帖文字或截图。')
