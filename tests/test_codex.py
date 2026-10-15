import asyncio
import pytest

def test_windows_desktop_cli_without_path(tmp_path,monkeypatch):
    import os
    if os.name!='nt':pytest.skip('Windows desktop installation discovery')
    from waypoint.providers.codex import CodexProvider
    import waypoint.providers.codex as codex_module
    monkeypatch.setattr(codex_module,'LOCAL_CODEX_BIN',tmp_path/'missing-codex.exe',raising=False)
    root=tmp_path/'OpenAI'/'Codex'/'bin'
    binary=root/'installed-build'/'codex.exe'
    binary.parent.mkdir(parents=True);binary.write_bytes(b'fixture')
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    monkeypatch.setenv('PATH','')
    async def run():
        p=CodexProvider(tmp_path)
        launched=[]
        async def spawn(*args,**kwargs):
            launched.append(args[0])
            raise OSError('Stop before launching the fixture')
        monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
        report=await p.capabilities()
        assert launched==[str(binary)]
        assert report['auth_state']=='unavailable'
    asyncio.run(run())

def test_windows_prefers_verified_local_codex_cli(tmp_path,monkeypatch):
    import os
    if os.name!='nt':pytest.skip('Windows local Codex CLI discovery')
    import waypoint.providers.codex as codex_module
    local=tmp_path/'runtime'/'bin'/'codex.exe';local.parent.mkdir(parents=True);local.write_bytes(b'fixture')
    monkeypatch.setattr(codex_module,'LOCAL_CODEX_BIN',local,raising=False)
    monkeypatch.setattr(codex_module.shutil,'which',lambda name: 'C:/old/codex.exe')
    async def run():
        p=codex_module.CodexProvider(tmp_path);launched=[]
        async def spawn(*args,**kwargs):
            launched.append(args[0]);raise OSError('Stop before launching fixture')
        monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
        report=await p.capabilities()
        assert launched==[str(local)]
        assert report['auth_state']=='unavailable'
    asyncio.run(run())

def test_split_events_and_login_expiry(tmp_path):
    from waypoint.providers.codex import JsonLines, safe_error, CodexProvider
    d=JsonLines()
    assert d.feed(b'{"id":1,') == []
    assert d.feed(b'"result":{}}\n') == [{'id':1,'result':{}}]
    assert 'sk-secret' not in safe_error({'message':'401 sk-secret'})
    p=CodexProvider(tmp_path, executable='waypoint_missing_codex')
    report=asyncio.run(p.capabilities())
    assert report['auth_state']=='unavailable'
    assert report['text']=='unverified'

def test_unknown_image_capability(tmp_path):
    from waypoint.providers.codex import CodexProvider
    p=CodexProvider(tmp_path, executable='missing')
    r=asyncio.run(p.capabilities())
    assert r['image']=='unverified'

def test_no_api_auth_accepted(tmp_path):
    from waypoint.providers.codex import require_subscription
    with pytest.raises(ValueError, match='ChatGPT'):
        require_subscription({'account':{'type':'apiKey'}})
    require_subscription({'account':{'type':'chatgpt'}})

def test_real_subprocess_protocol(tmp_path):
    import sys,os,shlex
    from pathlib import Path
    from waypoint.providers.codex import CodexProvider
    from waypoint.workflow import RESULT_SCHEMA
    script=Path(__file__).parent/'fixtures/fake_codex.py'
    executable=tmp_path/('fake-codex.cmd' if os.name=='nt' else 'fake-codex')
    if os.name=='nt':
        executable.write_bytes(('@echo off\r\n"'+sys.executable+'" "'+str(script.resolve())+'"\r\n').encode('utf-8'))
    else:
        executable.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(script.resolve()))+'\n',encoding='utf-8')
        executable.chmod(0o755)
    async def run():
        p=CodexProvider(tmp_path,executable=str(executable))
        try:
            report=await p.capabilities();assert report['auth_state']=='chatgpt' and report['models'][0]['model']=='test'
            calls=[];original=p.call
            async def capture(method,params=None,ready=True):
                calls.append((method,params));return await original(method,params,ready)
            p.call=capture
            events=[x async for x in p.generate({'job_id':'job','model':'test','effort':'high','prompt':'test','schema':RESULT_SCHEMA})]
            assert events[-1]['kind']=='completed' and 'Example.' in events[-1]['text']
            assert next(params for method,params in calls if method=='turn/start')['effort']=='high'
        finally:await p.close()
    asyncio.run(run())
