import pytest
from waypoint.materials import Materials
from waypoint.context import build_context
from waypoint.contracts import TaskSpec
from waypoint.repository import Repository
from waypoint.transfer import ProjectTransfer
from test_repository import make

def test_brand_and_global_context_with_no_cross_brand_leak(tmp_path):
    r,p,t=make(tmp_path);m=Materials(r);other=r.create_project('其他品牌')
    common=m.add_text(None,'通用策略','全品牌中文说明',kind='strategy')
    own=m.add_text(p,'本品牌','品牌事实');m.add_text(other,'隔离','其他品牌秘密')
    file=m.import_bytes(None,'参考.txt','全局附件正文'.encode())
    r.update_task(t,{'source_ids':[file['id']]})
    assert {x['id'] for x in build_context(r,t,'english')['materials']}=={common['id'],own['id'],file['id']}
    r.create_task(TaskSpec(project_id=other,source_ids=[file['id']]))
    with pytest.raises(ValueError):r.create_task(TaskSpec(project_id=other,source_ids=[own['id']]))

def test_global_archive_invalidates_all_brands_and_inflight_epoch(tmp_path):
    r,p,t=make(tmp_path);m=Materials(r);g=m.add_text(None,'通用事实','共同依据')
    other=r.create_project('乙');u=r.create_task(TaskSpec(project_id=other,raw_input='想法'))
    a=r.save_revision(t,'english','A',r.task(t)['input_epoch']);b=r.save_revision(u,'english','B',0)
    epochs={x:r.task(x)['input_epoch'] for x in (t,u)};m.archive(g['id'])
    assert r.revision(a['id'])['stale'] and r.revision(b['id'])['stale']
    assert all(r.task(x)['input_epoch']>epochs[x] for x in (t,u))

def test_export_snapshots_shared_materials_without_overwriting_global_library(tmp_path):
    r,p,t=make(tmp_path/'a');m=Materials(r)
    shared=m.add_text(None,'通用策略','共同依据',kind='strategy');file=m.import_bytes(None,'通用.txt','附件内容'.encode())
    unrelated=m.import_bytes(None,'无关.txt','未引用'.encode());r.update_task(t,{'source_ids':[file['id']]})
    build_context(r,t,'english')
    data=ProjectTransfer(r).export(p);dest=Repository(tmp_path/'b');service=ProjectTransfer(dest)
    preview=service.preview([('brand.zip',data)]);pid=service.commit(preview['token'],accept_rules=True)['project_id']
    rows=dest.list('material',project_id=pid)
    assert {x['name'] for x in rows}=={'通用策略','通用.txt'}
    assert all(x['imported_global_snapshot'] for x in rows)
    assert dest.list('material',project_id=None)==[] and len(r.list('material',project_id=None))==3

def test_global_library_http_without_any_brand(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    with TestClient(create_app(tmp_path,accounts_enabled=False),base_url='http://127.0.0.1') as client:
        client.headers['X-Waypoint-Token']=client.get('/api/session').json()['token']
        assert client.post('/api/materials',json={'project_id':None,'name':'全局','text':'共享文字'}).status_code==200
        assert len(client.get('/api/materials').json())==1
        response=client.post('/api/materials/upload',files={'file':('共享.txt','共享附件'.encode(),'text/plain')})
        assert response.status_code==200 and response.json()['project_id'] is None
        assert client.post('/api/rules',json={'project_id':None,'text':'全局规则'}).status_code==200
        assert client.get('/api/rules').json()[-1]['text']=='全局规则'
