import io
from PIL import Image
from fastapi.testclient import TestClient
from waypoint.server import create_app


def picture(color='red',size=(120,60)):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,'PNG');return out.getvalue()


def register(c):
    headers={'X-Waypoint-Token':c.get('/api/session').json()['token']}
    assert c.post('/api/auth/register',headers=headers,json={'username':'owner','password':'local-test-password-123'}).status_code==200
    return {'X-Waypoint-Token':c.get('/api/session').json()['token']}


def test_only_owner_can_change_public_login_logo(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        public=c.get('/api/branding');assert public.status_code==200
        assert public.json()['custom_logo'] is False
        assert c.post('/api/branding/logo',files={'file':('logo.png',picture())}).status_code==401
        headers=register(c)
        assert c.get('/api/session').json()['auth']['user']['role']=='owner'
        assert c.cookies.get('content_workbench_session') and 'waypoint_session' not in c.cookies
        assert c.post('/api/branding/logo',files={'file':('logo.png',picture())}).status_code==403
        upload=c.post('/api/branding/logo',files={'file':('logo.png',picture())},headers=headers)
        assert upload.status_code==200 and upload.json()['custom_logo']
        url=upload.json()['logo_url'];saved=c.get(url)
        assert saved.status_code==200 and saved.headers['content-type']=='image/png'
        with Image.open(io.BytesIO(saved.content)) as image:assert image.size==(120,60)
        assert not c.app.state.repo.list('job') and not c.app.state.repo.list('task')
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        assert c.get('/api/branding').json()['logo_url']==url
        assert c.get(url).content==saved.content


def test_invalid_upload_keeps_previous_logo_and_remove_restores_neutral(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        headers=register(c)
        original=c.post('/api/branding/logo',files={'file':('a.png',picture())},headers=headers).json()
        for name,data in [('bad.svg',b'<svg onload="alert(1)"/>'),('bad.png',b'not-image'),('large.png',b'x'*5_000_001)]:
            response=c.post('/api/branding/logo',files={'file':(name,data)},headers=headers)
            assert response.status_code==400
            assert c.get('/api/branding').json()==original
        other=c.post('/api/branding/logo',files={'file':('b.png',picture('blue'))},headers=headers).json()
        assert other['logo_url']!=original['logo_url']
        removed=c.delete('/api/branding/logo',headers=headers)
        assert removed.status_code==200 and removed.json()['custom_logo'] is False
        assert c.get('/api/branding/logo').status_code==404
        assert c.get('/static/waypoint-white.png').status_code==404


def test_large_dimensions_are_reduced_and_do_not_become_business_materials(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        headers=register(c)
        result=c.post('/api/branding/logo',files={'file':('wide.png',picture(size=(2400,1200)))},headers=headers)
        assert result.status_code==200
        with Image.open(io.BytesIO(c.get(result.json()['logo_url']).content)) as image:assert image.size==(1600,800)
        assert not c.app.state.repo.list('material')


def test_generic_default_data_directory_is_separate_from_original(tmp_path,monkeypatch):
    from waypoint.launcher import data_directory
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));monkeypatch.delenv('CONTENT_WORKBENCH_DATA_DIR',raising=False)
    monkeypatch.setenv('WAYPOINT_DATA_DIR',str(tmp_path/'original'))
    assert data_directory()==tmp_path/'content-workbench'


def test_generic_backup_reads_only_its_own_data_directory(tmp_path,monkeypatch):
    import json,sqlite3,sys
    from waypoint.repository import Repository
    from scripts import backup_live_data
    generic=tmp_path/'generic';r=Repository(generic);r.create_project('generic-only');r.db.conn.close()
    monkeypatch.setenv('CONTENT_WORKBENCH_DATA_DIR',str(generic));monkeypatch.setenv('WAYPOINT_DATA_DIR',str(tmp_path/'original'))
    monkeypatch.setattr(sys,'argv',['backup_live_data','--output',str(tmp_path/'backups')])
    backup_live_data.main()
    folders=list((tmp_path/'backups').iterdir());assert len(folders)==1
    with sqlite3.connect(folders[0]/'waypoint.sqlite') as db:
        row=db.execute("SELECT data FROM records WHERE kind='project'").fetchone()
        assert json.loads(row[0])['name']=='generic-only'
    assert not (tmp_path/'original').exists()
