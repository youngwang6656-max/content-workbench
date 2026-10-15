from fastapi.testclient import TestClient

def client(tmp_path):
    from waypoint.server import create_app
    return TestClient(create_app(tmp_path,accounts_enabled=False),base_url='http://127.0.0.1:8765')

def test_security_and_task_api(tmp_path):
    with client(tmp_path) as c:
        assert c.get('/',headers={'host':'evil.example'}).status_code==403
        assert c.post('/api/projects',json={'name':'甲'}).status_code==403
        session=c.get('/api/session').json();headers={'X-Waypoint-Token':session['token'],'Origin':'http://127.0.0.1:8765'}
        assert c.post('/api/projects',json={'name':'甲'},headers=headers|{'Origin':'https://evil.example'}).status_code==403
        p=c.post('/api/projects',json={'name':'甲'},headers=headers).json()['id']
        t=c.post('/api/tasks',json={'project_id':p,'raw_input':'中文想法'},headers=headers).json()['id']
        assert c.get('/api/tasks/'+t).json()['task']['raw_input']=='中文想法'
        assert c.post('/api/tasks/'+t+'/run',json={},headers=headers).status_code==200
        assert c.get('/api/settings').json()['api_enabled'] is False
        assert c.get('/').status_code==200
        assert c.get('/static/../../waypoint.sqlite').status_code==404

def test_batch_invalid_is_atomic(tmp_path):
    with client(tmp_path) as c:
        h={'X-Waypoint-Token':c.get('/api/session').json()['token']}
        p=c.post('/api/projects',json={'name':'甲'},headers=h).json()['id']
        res=c.post('/api/tasks/batch',json={'items':[{'project_id':p,'raw_input':'好'},{'project_id':'missing'}]},headers=h)
        assert res.status_code==400
        assert c.get('/api/tasks').json()==[]

def test_batch_with_merged_brand_writes_nothing(tmp_path):
    with client(tmp_path) as c:
        r=c.app.state.repo;p=r.create_project('当前品牌');source=r.create_project('合并来源')
        preview=r.preview_project_merge(source,p);r.merge_projects(source,p,preview['fingerprint'])
        headers={'X-Waypoint-Token':c.get('/api/session').json()['token']}
        response=c.post('/api/tasks/batch',headers=headers,json={'items':[
            {'project_id':p,'raw_input':'第一项合法'}, {'project_id':source,'raw_input':'来自旧页面'}]})
        assert response.status_code==400
        assert r.list('task')==[]
