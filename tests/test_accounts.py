from fastapi.testclient import TestClient
from waypoint.server import create_app
from waypoint.backup import Backup
import zipfile


def client(root):
    app=create_app(root);return app,TestClient(app,base_url='http://localhost')


def register(c):
    token=c.get('/api/session').json()['token']
    result=c.post('/api/auth/register',headers={'X-Waypoint-Token':token},json={
        'username':'owner','display_name':'老细','password':'local-test-password-123'})
    assert result.status_code==200
    return c.get('/api/session').json()['token']


def test_first_registration_claims_existing_local_data_and_protects_gets(tmp_path):
    app,c=client(tmp_path);pid=app.state.repo.create_project('现有真实数据的替身')
    for path in ['/api/projects','/api/settings','/api/tasks','/api/events','/api/projects/'+pid+'/export','/api/materials']:
        assert c.get(path).status_code==401
    assert c.get('/api/session').json()['auth']=={'enabled':True,'configured':False,'user':None}
    csrf=register(c)
    assert c.get('/api/projects').json()[0]['id']==pid
    assert 'HttpOnly' in c.post('/api/auth/login',headers={'X-Waypoint-Token':csrf},json={
        'username':'owner','password':'local-test-password-123'}).headers['set-cookie']
    csrf=c.get('/api/session').json()['token']
    assert c.post('/api/auth/register',headers={'X-Waypoint-Token':csrf},json={
        'username':'second','password':'local-test-password-123'}).status_code==400
    assert c.post('/api/projects',json={'name':'unauthorized'}).status_code==403
    assert c.post('/api/projects',headers={'X-Waypoint-Token':csrf},json={'name':'DJI'}).status_code==200
    c.post('/api/auth/logout',headers={'X-Waypoint-Token':csrf})
    assert c.get('/api/projects').status_code==401


def test_password_is_hashed_persisted_sessions_and_password_change_revokes(tmp_path):
    app,c=client(tmp_path);csrf=register(c);app2,c2=client(tmp_path)
    assert c2.get('/api/session').json()['auth']['configured']
    c2.cookies.update(c.cookies)
    assert c2.get('/api/session').json()['auth']['user']['username']=='owner'
    assert c2.get('/api/projects').status_code==200
    c2.cookies.clear()
    assert b'local-test-password-123' not in (tmp_path/'accounts.sqlite').read_bytes()
    public=c2.get('/api/session').json()['token']
    assert c2.post('/api/auth/login',headers={'X-Waypoint-Token':public},json={'username':'OWNER','password':'local-test-password-123'}).status_code==200
    assert c.post('/api/auth/password',headers={'X-Waypoint-Token':csrf},json={'current_password':'wrong','password':'new-local-password-123'}).status_code==400
    assert c.post('/api/auth/password',headers={'X-Waypoint-Token':csrf},json={'current_password':'local-test-password-123','password':'new-local-password-123'}).status_code==200
    assert c2.get('/api/projects').status_code==401
    assert c.get('/api/projects').status_code==200
    archive=Backup(app.state.repo).create_backup(tmp_path/'backups')
    with zipfile.ZipFile(archive) as z:assert 'accounts.sqlite' not in z.namelist()
    app.state.repo.create_project('备份后的品牌')
    Backup(app.state.repo).restore_backup(archive)
    assert c.get('/api/projects').status_code==200
    assert app.state.accounts.configured()


def test_login_rate_limit_and_csrf_rotation(tmp_path):
    app,c=client(tmp_path);before=c.get('/api/session').json()['token'];csrf=register(c)
    assert before!=csrf
    assert c.post('/api/projects',headers={'X-Waypoint-Token':before},json={'name':'wrong session'}).status_code==403
    c.post('/api/auth/logout',headers={'X-Waypoint-Token':csrf});public=c.get('/api/session').json()['token']
    for _ in range(5):
        assert c.post('/api/auth/login',headers={'X-Waypoint-Token':public},json={'username':'owner','password':'wrong'}).status_code==400
    assert c.post('/api/auth/login',headers={'X-Waypoint-Token':public},json={'username':'owner','password':'local-test-password-123'}).status_code==429
    app2,c2=client(tmp_path);public=c2.get('/api/session').json()['token']
    assert c2.post('/api/auth/login',headers={'X-Waypoint-Token':public},json={'username':'owner','password':'local-test-password-123'}).status_code==429


def test_session_expires(tmp_path,monkeypatch):
    from waypoint.accounts import Accounts,SESSION_SECONDS
    import time
    a=Accounts(tmp_path);secret=a.register('owner','老细','local-test-password-123')
    assert a.session(secret)['user']['username']=='owner'
    later=time.time()+SESSION_SECONDS+1
    monkeypatch.setattr('waypoint.accounts.time.time',lambda:later)
    assert a.session(secret) is None
