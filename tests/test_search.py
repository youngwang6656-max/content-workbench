import pytest

def test_verified_search_results_only():
    from waypoint.search import parse_posts
    data={'data':{'children':[{'data':{'title':'Need mount','selftext':'question','permalink':'/r/cars/comments/abc/post/','created_utc':1790000000,'subreddit':'cars'}},{'data':{'title':'Missing date','permalink':'https://evil.com'}},{'data':{'title':'Removed','selftext':'[removed]','created_utc':1790000000,'permalink':'/r/cars/comments/def/post/','subreddit':'cars'}}]}}
    rows=parse_posts(data,0)
    assert len(rows)==1 and rows[0]['url'].startswith('https://www.reddit.com/r/cars/')
    assert rows[0]['published_at'] and rows[0]['verification_status']=='retrieved'
