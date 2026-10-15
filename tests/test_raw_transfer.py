import io,json,zipfile
import pytest
from waypoint.repository import Repository
from waypoint.transfer import ProjectTransfer


def conversation(cid='one',title='topdon',long=False):
    def node(n,parent,text,role='assistant',content_type='text'):
        return {'id':n,'parent':parent,'children':[], 'message':{'id':'m-'+n,
            'author':{'role':role},'create_time':1700000000,
            'content':{'content_type':content_type,'parts':[text]}}}
    return {'id':cid,'title':title,'current_node':'a','mapping':{
        'root':{'id':'root','parent':None,'message':None},
        'u':node('u','root','用户原始要求','user'),
        'a':node('a','u','X'*210001 if long else '第一条英文稿'),
        'b':node('b','u','另一个分支的原始稿'),
        'image':node('image','b',{'asset_pointer':'file-service://image'},'user','multimodal_text')}}


def encoded(data):return json.dumps(data,ensure_ascii=False).encode()


def inspect(service,data):return service.inspect_raw('conversations.json',encoded(data))


def test_raw_selection_preserves_all_branches_and_long_text(tmp_path):
    r=Repository(tmp_path);r.create_project('已有');r.save_settings({'api_enabled':False})
    s=ProjectTransfer(r)
    assert callable(getattr(s,'inspect_raw',None)), '缺少原始导出检查入口'
    export=[conversation(long=True),conversation('two','其他品牌')]
    info=inspect(s,export)
    assert len(info['conversations'])==2 and len(r.list('project'))==1
    chosen=info['conversations'][0]
    assert chosen['message_count']==4 and chosen['branch_count']==2 and chosen['nontext_count']==1
    p=s.preview_raw(info['token'],[chosen['key']],'topdon 完整原文')
    assert p['history_count']==4 and p['audit']['message_count']==4 and p['audit']['text_message_count']==3
    assert p['missing'] and p['rules']==[] and not r.list('material')
    pid=s.commit(p['token'])['project_id']
    history=s.history(pid)['records']
    assert ''.join(h['text'] for h in history if h['source'].endswith('/a'))=='X'*210001
    assert any(h['text']=='另一个分支的原始稿' for h in history)
    assert all(h['record_type']=='original' and h['created_at']=='2023-11-14T22:13:20+00:00' for h in history)
    assert all('其他品牌' not in m['name'] for m in r.list('material',project_id=pid))
    receipt=r.list('transfer',project_id=pid)[0]
    with zipfile.ZipFile(r.db.root/'attachments'/receipt['archive_path']) as z:
        saved=json.loads(z.read(z.namelist()[0]))
    assert saved==[export[0]] and r.settings()['api_enabled'] is False and not r.list('task')
    with pytest.raises(ValueError,match='已经导入'):s.preview_raw(info['token'],[chosen['key']],'第二次')
    dest=ProjectTransfer(Repository(tmp_path/'destination'))
    preview=dest.preview([('project.zip',s.export(pid))]);new=dest.commit(preview['token'])['project_id']
    assert dest.history(new)['records']==history
    assert dest.history(new)['receipts'][0]['audit']==receipt['audit']


def test_raw_no_selection_invalid_selection_and_expired_cache_write_nothing(tmp_path):
    s=ProjectTransfer(Repository(tmp_path));assert callable(getattr(s,'inspect_raw',None))
    info=inspect(s,[conversation()])
    for keys in [[],['missing'],[info['conversations'][0]['key']]*2]:
        with pytest.raises(ValueError):s.preview_raw(info['token'],keys,'demo')
    s.raw_previews[info['token']]['time']=0
    with pytest.raises(ValueError,match='失效'):s.preview_raw(info['token'],[info['conversations'][0]['key']],'demo')
    assert not s.repo.list('project') and not list((s.repo.db.root/'attachments').iterdir())


@pytest.mark.parametrize('mutation',['cycle','duplicate','parent','schema'])
def test_raw_malformed_exports_are_not_silently_partial(tmp_path,mutation):
    s=ProjectTransfer(Repository(tmp_path));assert callable(getattr(s,'inspect_raw',None))
    d=conversation()
    if mutation=='cycle':d['mapping']['u']['parent']='a'
    if mutation=='parent':d['mapping']['u']['parent']='absent'
    data=[d,d] if mutation=='duplicate' else ([{'title':'summary','text':'不是原始对话'}] if mutation=='schema' else [d])
    with pytest.raises(ValueError):inspect(s,data)
    assert not s.repo.list('project')


def test_raw_zip_and_unknown_dates(tmp_path):
    s=ProjectTransfer(Repository(tmp_path));assert callable(getattr(s,'inspect_raw',None))
    d=conversation();d['mapping']['a']['message']['create_time']=None
    for name in ['conversations.json','../conversations.json']:
        f=io.BytesIO()
        with zipfile.ZipFile(f,'w') as z:z.writestr(name,encoded([d]));z.writestr('private-account.txt','不应保存')
        if name.startswith('..'):
            with pytest.raises(ValueError):s.inspect_raw('export.zip',f.getvalue())
        else:
            info=s.inspect_raw('export.zip',f.getvalue());p=s.preview_raw(info['token'],[info['conversations'][0]['key']],'demo')
            pid=s.commit(p['token'])['project_id']
            assert next(h for h in s.history(pid)['records'] if h['source'].endswith('/a'))['created_at']==''
            assert any('日期' in text for text in p['coverage']['uncertain'])


def test_raw_api_does_not_generate_and_uses_existing_confirmation(tmp_path):
    from tests.test_server import client
    with client(tmp_path) as c:
        headers={'X-Waypoint-Token':c.get('/api/session').json()['token']}
        result=c.post('/api/transfer/raw/inspect',files=[('file',('conversations-1.json',encoded([conversation()]),'application/json')),
            ('file',('conversations-2.json',encoded([conversation('two','其他品牌')]),'application/json'))],headers=headers)
        assert result.status_code==200, result.text
        info=result.json()
        assert len(info['conversations'])==2
        p=c.post('/api/transfer/raw/preview',json={'token':info['token'],'conversation_ids':[info['conversations'][0]['key']],'name':'迁入'},headers=headers)
        assert p.status_code==200 and c.get('/api/projects').json()==[]
        done=c.post('/api/transfer/commit',json={'token':p.json()['token']},headers=headers)
        assert done.status_code==200 and not c.app.state.repo.list('job') and not c.app.state.repo.list('task')


def test_raw_extreme_date_is_unknown_not_server_error(tmp_path):
    s=ProjectTransfer(Repository(tmp_path));d=conversation();d['mapping']['a']['message']['create_time']=10**1000
    info=inspect(s,[d]);p=s.preview_raw(info['token'],[info['conversations'][0]['key']],'demo')
    pid=s.commit(p['token'])['project_id']
    assert next(h for h in s.history(pid)['records'] if h['source'].endswith('/a'))['created_at']==''


def test_raw_restore_capacity_checked_before_commit(tmp_path,monkeypatch):
    import waypoint.transfer as transfer
    monkeypatch.setattr(transfer,'MAX_EXPANDED',20000)
    s=ProjectTransfer(Repository(tmp_path));d=conversation();d['mapping']['a']['message']['content']['parts']=['X'*15000]
    info=inspect(s,[d])
    with pytest.raises(ValueError,match='分批'):s.preview_raw(info['token'],[info['conversations'][0]['key']],'demo')
    assert not s.repo.list('project')


def test_raw_audit_creation_is_not_a_second_cache_lookup(tmp_path,monkeypatch):
    s=ProjectTransfer(Repository(tmp_path));info=inspect(s,[conversation()]);stage=s._stage_preview
    def evict(*args,**kwargs):
        result=stage(*args,**kwargs)
        stage(*args,**kwargs);stage(*args,**kwargs)
        return result
    monkeypatch.setattr(s,'_stage_preview',evict)
    p=s.preview_raw(info['token'],[info['conversations'][0]['key']],'demo')
    assert p['audit']['conversation_count']==1


def test_raw_numbered_json_zip_and_multiple_files(tmp_path):
    s=ProjectTransfer(Repository(tmp_path));f=io.BytesIO()
    files=[('conversations-1.json',encoded([conversation()])),('conversations-2.json',encoded([conversation('two','同品牌另一对话')]))]
    with zipfile.ZipFile(f,'w') as z:
        for name,data in files:z.writestr(name,data)
    info=s.inspect_raw('export.zip',f.getvalue())
    assert len(info['conversations'])==2
    assert callable(getattr(s,'inspect_raw_files',None))
    split=s.inspect_raw_files(files)
    assert len(split['conversations'])==2
    p=s.preview_raw(split['token'],[row['key'] for row in split['conversations']],'同品牌')
    assert p['audit']['conversation_count']==2 and p['audit']['message_count']==8
    with pytest.raises(ValueError,match='重复'):s.inspect_raw_files([files[0],files[0]])


def test_raw_capacity_includes_global_evidence(tmp_path,monkeypatch):
    import waypoint.transfer as transfer
    from waypoint.materials import Materials
    monkeypatch.setattr(transfer,'MAX_EXPANDED',20000)
    r=Repository(tmp_path);Materials(r).add_text(None,'global evidence','G'*25000,'fact')
    s=ProjectTransfer(r);info=inspect(s,[conversation()])
    with pytest.raises(ValueError,match='分批'):s.preview_raw(info['token'],[info['conversations'][0]['key']],'demo')
    assert not r.list('project')


def test_raw_multiple_zips_share_expanded_json_limit(tmp_path,monkeypatch):
    import waypoint.chatgpt_export as raw
    monkeypatch.setattr(raw,'MAX_RAW',5000);monkeypatch.setattr(raw,'MAX_EXPANDED',10000)
    files=[]
    for i in (1,2):
        d=conversation(str(i));d['mapping']['a']['message']['content']['parts']=['X'*3000]
        f=io.BytesIO()
        with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('conversations.json',encoded([d]))
        files.append((f'export-{i}.zip',f.getvalue()))
    assert sum(len(data) for _,data in files)<5000
    s=ProjectTransfer(Repository(tmp_path))
    with pytest.raises(ValueError,match='合计'):s.inspect_raw_files(files)
    assert not s.raw_previews and not s.repo.list('project')
