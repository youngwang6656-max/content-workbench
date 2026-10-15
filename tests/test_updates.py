import asyncio,functools,hashlib,json,zipfile,io
from pathlib import Path
import pytest,httpx
from waypoint.repository import Repository

def run_async(fn):
    @functools.wraps(fn)
    def wrapped(*a,**k):return asyncio.run(fn(*a,**k))
    return wrapped

def source(tmp_path):
    root=tmp_path/'app';root.mkdir()
    files={'waypoint/__init__.py':"__version__ = '0.6.1'\n",'waypoint/server.py':'# editable server\n',
        'waypoint/launcher.py':'# launcher\n','waypoint/web/index.html':'<html><head></head><body>Hello</body></html>',
        'scripts/start_windows.cmd':'@echo off\nexit /b 0\n','启动waypoint.cmd':'@echo off\nexit /b 0\n',
        'requirements.lock':'# dependencies\n','pyproject.toml':'[project]\nversion="0.6.1"\n','README.md':'本地工作台'}
    for name,text in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode('utf-8'))
    return root

def release(root,out):
    from waypoint.distribution import build_release
    result=build_release(root,out,download_url='https://updates.example.com/waypoint.zip',notes_zh='测试更新')
    package=Path(result['package']);manifest=json.loads(Path(result['manifest']).read_text(encoding='utf-8'))
    return result,package,manifest

def test_distribution_excludes_personal_data_and_preserves_custom_source(tmp_path):
    from waypoint.distribution import local_changes
    root=source(tmp_path)
    for name in ['accounts.sqlite','waypoint.sqlite','.env','private/api_keys.json','attachments/photo.png','runtime_logs/secret.txt','waypoint/.env','waypoint/auth.json']:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('private-personal-data')
    (root/'waypoint'/'local_custom.py').write_text('# local custom code')
    (root/'waypoint/web/workbench-mark.svg').write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    result,package,manifest=release(root,tmp_path/'out')
    with zipfile.ZipFile(package) as z:
        assert b'private-personal-data' not in b''.join(z.read(i) for i in z.infolist())
        assert z.read('content_workbench/waypoint/local_custom.py')==b'# local custom code'
        assert z.read('content_workbench/waypoint/web/workbench-mark.svg')==b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        cmd=z.read('content_workbench/scripts/start_windows.cmd');assert b'\r\n' in cmd and b'\n' not in cmd.replace(b'\r\n',b'')
        provenance=json.loads(z.read('content_workbench/DEVELOPER_PROVENANCE.json'))
        assert provenance['developer']=='youngwang6656@gmail.com' and len(provenance['fingerprint'])==64
    assert manifest['sha256']==hashlib.sha256(package.read_bytes()).hexdigest() and manifest['size']==package.stat().st_size
    # Baseline does not overwrite source just to normalize package line endings.
    assert (root/'scripts/start_windows.cmd').read_bytes()==b'@echo off\nexit /b 0\n'
    assert local_changes(root)['state']=='missing'

def test_baseline_detects_local_changes_without_overwriting(tmp_path):
    from waypoint.distribution import local_changes
    root=source(tmp_path);result,package,manifest=release(root,tmp_path/'out')
    with zipfile.ZipFile(package) as z:z.extractall(tmp_path/'installed')
    installed=tmp_path/'installed'/'content_workbench'
    assert local_changes(installed)['state']=='clean'
    (installed/'waypoint/server.py').write_text('# user modification')
    (installed/'waypoint/launcher.py').unlink();(installed/'waypoint/new.py').write_text('# new module')
    diff=local_changes(installed);assert diff['state']=='modified'
    assert diff['changed']==['waypoint/server.py'] and diff['deleted']==['waypoint/launcher.py'] and diff['added']==['waypoint/new.py']

@run_async
async def test_manual_check_download_backup_and_no_code_overwrite(tmp_path):
    from waypoint.updates import Updates
    root=source(tmp_path);result,package,manifest=release(root,tmp_path/'out');r=Repository(tmp_path/'data')
    r.create_project('原有品牌');s=Updates(r,root,current_version='0.6.0');assert s.status()['manifest_url']==''
    with pytest.raises(ValueError,match='更新源'):await s.check()
    s.save_source('https://updates.example.com/latest.json');calls=[]
    def handle(request):
        calls.append(request);assert request.method=='GET'
        assert 'authorization' not in request.headers and 'cookie' not in request.headers and 'x-api-key' not in request.headers
        return httpx.Response(200,json=manifest) if request.url.path.endswith('latest.json') else httpx.Response(200,content=package.read_bytes())
    candidate=await s.check(transport=httpx.MockTransport(handle));assert candidate['available'] is True
    before=(root/'waypoint/server.py').read_bytes()
    downloaded=await s.download(candidate['candidate_id'],transport=httpx.MockTransport(handle))
    assert len(calls)==2 and Path(s.packages[downloaded['package_id']]).read_bytes()==package.read_bytes()
    assert Path(downloaded['backup']).is_file() and (root/'waypoint/server.py').read_bytes()==before
    assert len(r.list('project'))==1 and r.settings()['api_enabled'] is False
    assert r.list('budget')==[]

@run_async
async def test_source_change_invalidates_candidate_and_bad_hash_never_saved(tmp_path):
    from waypoint.updates import Updates
    root=source(tmp_path);result,package,manifest=release(root,tmp_path/'out');r=Repository(tmp_path/'data');s=Updates(r,root,current_version='0.6.0')
    s.save_source('https://updates.example.com/latest.json')
    def handle(request):return httpx.Response(200,json=manifest) if request.url.path.endswith('json') else httpx.Response(200,content=b'broken')
    transport=httpx.MockTransport(handle);candidate=await s.check(transport=transport)
    with pytest.raises(ValueError):await s.download(candidate['candidate_id'],transport=transport)
    assert not s.packages and not list((r.db.root/'updates').glob('*.zip'))
    s.save_source('https://other.example.com/latest.json')
    with pytest.raises(ValueError):await s.download(candidate['candidate_id'],transport=transport)

@run_async
async def test_https_redirect_guard_and_manifest_validation(tmp_path):
    from waypoint.updates import Updates
    root=source(tmp_path);result,package,manifest=release(root,tmp_path/'out');s=Updates(Repository(tmp_path/'data'),root,current_version='0.6.0')
    for url in ['http://updates.example.com/latest.json','https://localhost/latest.json','https://user:password@example.com/x','https://127.0.0.1/x']:
        with pytest.raises(ValueError):s.save_source(url)
    s.save_source('https://updates.example.com/latest.json');calls=[]
    def redirect(req):calls.append(req);return httpx.Response(302,headers={'Location':'http://127.0.0.1/private'})
    with pytest.raises(ValueError):await s.check(transport=httpx.MockTransport(redirect))
    assert len(calls)==1
    for bad in [manifest|{'version':'../../evil'},manifest|{'sha256':'wrong'},manifest|{'size':True},manifest|{'download_url':'https://localhost/package.zip'}]:
        with pytest.raises(ValueError):await s.check(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=bad)))
    latest=await s.check(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=manifest|{'version':'0.6.0'})))
    assert latest['available'] is False and 'candidate_id' not in latest

@pytest.mark.parametrize('name',['waypoint_workbench/../../escape.py','waypoint_workbench/C:/evil.py','waypoint_workbench/waypoint/CON.py','waypoint_workbench/waypoint/code.py:stream'])
def test_unsafe_archives_rejected(tmp_path,name):
    from waypoint.distribution import validate_package
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr(name,'malicious')
    with pytest.raises(ValueError):validate_package(path,'0.6.1')

def test_hidden_marker_only_in_metadata(tmp_path):
    from waypoint.provenance import DEVELOPER_EMAIL,FINGERPRINT
    assert DEVELOPER_EMAIL=='youngwang6656@gmail.com' and len(FINGERPRINT)==64
    root=Path(__file__).resolve().parents[1];html=(root/'waypoint/web/index.html').read_text(encoding='utf-8')
    assert DEVELOPER_EMAIL in html.split('</head>')[0] and DEVELOPER_EMAIL not in html.split('<body>')[1]

def test_update_routes_protected_by_account(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    from test_workflow import FakeProvider
    with TestClient(create_app(tmp_path,FakeProvider()),base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/updates/status').status_code==401
        token=c.get('/api/session').json()['token']
        assert c.post('/api/auth/register',headers={'X-Waypoint-Token':token},json={
            'username':'qa_owner','display_name':'模拟验收','password':'disposable-password-2026'}).status_code==200
        status=c.get('/api/updates/status');assert status.status_code==200 and status.json()['manifest_url']==''
        assert c.post('/api/updates/source',json={'url':''}).status_code==403
        assert c.get('/api/settings').json()['api_enabled'] is False

@run_async
async def test_stream_limits_expiry_and_package_version_are_enforced(tmp_path):
    from waypoint.updates import Updates,fetch
    from waypoint.distribution import validate_package
    root=source(tmp_path);result,package,manifest=release(root,tmp_path/'out')
    with pytest.raises(ValueError):await fetch('https://updates.example.com/huge',1,transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b'12')))
    s=Updates(Repository(tmp_path/'data'),root,current_version='0.6.0');s.save_source('https://updates.example.com/latest.json')
    candidate=await s.check(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=manifest)))
    s.candidate['expires']=0
    with pytest.raises(ValueError):await s.download(candidate['candidate_id'],transport=httpx.MockTransport(lambda req:pytest.fail('expired candidate must not connect')))
    with pytest.raises(ValueError):validate_package(package,'9.0.0')

def test_windows_bootstrap_syntax_and_archive_guard(tmp_path):
    import subprocess
    root=Path(__file__).resolve().parents[1];ps=root/'scripts/bootstrap_windows.ps1'
    bad=tmp_path/'unsafe.nupkg';bad.write_bytes(b'not-an-official-runtime')
    script='''param($Script,$Bad)
    $tokens=$null;$errors=$null
    [Management.Automation.Language.Parser]::ParseFile($Script,[ref]$tokens,[ref]$errors) | Out-Null
    if($errors.Count){throw 'PowerShell syntax invalid'}
    . $Script -FunctionsOnly
    try{Assert-PythonArchive $Bad;throw 'Guard accepted unsafe file'}catch{if($_.Exception.Message -notlike '*SHA-512*'){throw}}
    Write-Output 'syntax and bad-archive guard passed'
    '''
    test=tmp_path/'check.ps1';test.write_bytes(script.encode('utf-8-sig'))
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(test),str(ps),str(bad)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    for name in ('启动waypoint.cmd','发布新版.cmd','scripts/start_windows.cmd'):
        content=(root/name).read_bytes();content.decode('ascii')
        assert b'\n' not in content.replace(b'\r\n',b'') and not any(c<32 and c not in (10,13,9) for c in content)
