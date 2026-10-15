from fastapi.testclient import TestClient
from waypoint.server import create_app
from waypoint.accounts import Accounts


def enter(c,name='老细'):
    csrf=c.get('/api/session').json()['token']
    response=c.post('/api/auth/name',headers={'X-Waypoint-Token':csrf},json={'name':name})
    assert response.status_code==200,response.text
    return {'X-Waypoint-Token':c.get('/api/session').json()['token']}


def test_name_is_enough_and_session_survives_restart(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        assert c.get('/api/session').json()['auth'].get('mode')=='name'
        assert c.get('/api/projects').status_code==401
        before=c.get('/api/session').json()['token'];h=enter(c,'  中文名字  ')
        user=c.get('/api/session').json()['auth']['user']
        assert user['display_name']=='中文名字' and user['role']=='owner'
        assert c.post('/api/projects',json={'name':'项目'},headers={'X-Waypoint-Token':before}).status_code==403
        assert c.post('/api/projects',json={'name':'项目'},headers=h).status_code==200
        cookies=dict(c.cookies)
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        c.cookies.update(cookies)
        assert c.get('/api/session').json()['auth']['user']['display_name']=='中文名字'
        assert c.get('/api/projects').json()[0]['name']=='项目'


def test_invalid_names_csrf_and_cross_site_do_not_enter(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        token=c.get('/api/session').json()['token'];h={'X-Waypoint-Token':token}
        for name in ['', '   ', 'x'*81, None, 123]:
            assert c.post('/api/auth/name',headers=h,json={'name':name}).status_code==400
        assert c.post('/api/auth/name',json={'name':'test'}).status_code==403
        assert c.post('/api/auth/name',json={'name':'test'},headers=h|{'Origin':'https://example.com'}).status_code==403
        assert c.get('/api/projects').status_code==401
        assert not c.app.state.repo.list('job')


def test_existing_password_owner_is_preserved_and_password_routes_inactive(tmp_path):
    tmp_path.mkdir(exist_ok=True);old=Accounts(tmp_path);old.register('6656','管理员','existing-local-password')
    before=old.conn.execute('SELECT * FROM owner').fetchone();old.conn.close()
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        h=enter(c,'新名称')
        for path in ['/api/auth/register','/api/auth/login','/api/auth/password']:
            assert c.post(path,headers=h,json={}).status_code==404
        assert c.patch('/api/auth/profile',headers=h,json={'display_name':'改过的名称'}).json()['display_name']=='改过的名称'
        assert c.get('/api/session').json()['auth']['user']['role']=='owner'
    old=Accounts(tmp_path);assert old.conn.execute('SELECT * FROM owner').fetchone()==before;old.conn.close()


def test_switch_name_revokes_current_browser_session_without_erasing_projects(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        h=enter(c);c.app.state.repo.create_project('保留资料')
        assert c.post('/api/auth/logout',headers=h,json={}).status_code==200
        assert c.get('/api/projects').status_code==401
        enter(c,'另一名称')
        assert c.get('/api/projects').json()[0]['name']=='保留资料'
