import io,json,zipfile
import pytest
from waypoint.repository import Repository
from waypoint.contracts import TaskSpec,Opinion
from waypoint.transfer import ProjectTransfer


def handoff():
    return {'format':'waypoint-handoff','version':1,'project_key':'demo','part':1,'total_parts':1,
      'project':{'name':'演示项目','description':'面向摄影爱好者','summary':'客户希望简洁自然','rules':['品牌名小写']},
      'coverage':{'sources':['当前对话'],'missing':['早期附件未读取'],'uncertain':['客户是否最终通过']},
      'materials':[{'key':'m1','name':'产品资料','text':'尚待补传原件','missing_attachment':True,'filename':'原件.pdf'}],
      'tasks':[{'key':'t1','name':'原帖','raw_input':'保留转折','versions':[
        {'key':'v1','stage':'english','title':'Original title','body':"I didn't expect this.\n\nBut it worked.",'current':True,'approval_notes':['客户似乎认可，未见原文']},
        {'key':'v2','stage':'backtranslation','body':'我没想到。\n\n但确实有效。','source_version':'v1','current':True}],
        'opinions':[{'stage':'english','source':'client','raw_text':'只改第二句','base_version':'v1','status':'pending'}]},
       {'key':'t2','kind':'comment','comment_kind':'own','parent_version':'v1','raw_input':'稳固吗？'}],
      'history':[{'role':'user','text':'原始用户意见 <script>bad()</script>','record_type':'original','source':'当前对话'}]}


def preview(s,payload):return s.preview([('project.json',json.dumps(payload,ensure_ascii=False).encode())])

def test_handoff_is_lossless_preview_then_isolated_import(tmp_path):
    r=Repository(tmp_path);old=r.create_project('已有');r.save_settings({'api_enabled':False})
    s=ProjectTransfer(r);p=preview(s,handoff())
    assert len(r.list('project'))==1
    assert p['counts']['task']==2 and p['counts']['revision']==2
    assert p['missing'] and p['rules']==['品牌名小写']
    result=s.commit(p['token'],accept_rules=True)
    tasks=r.list('task',project_id=result['project_id']);t=next(t for t in tasks if t['kind']=='post')
    en=r.revision(t['active']['english']);zh=r.revision(t['active']['backtranslation'])
    assert en['body']==handoff()['tasks'][0]['versions'][0]['body']
    assert zh['source_revision_id']==en['id']
    assert not r.approvals(en['id']) and en['approval_notes']
    assert r.list('opinion',task_id=t['id'])[0]['status']=='pending'
    assert next(t for t in tasks if t['kind']=='comment')['parent_revision_id']==en['id']
    assert not r.list('task',project_id=old)
    assert r.settings()['api_enabled'] is False
    with pytest.raises(ValueError):s.commit(p['token'],accept_rules=True)
    with pytest.raises(ValueError,match='已经导入'):preview(s,handoff())


def test_handoff_parts_and_invalid_reference_write_nothing(tmp_path):
    s=ProjectTransfer(Repository(tmp_path));d=handoff();d['total_parts']=2
    with pytest.raises(ValueError,match='分卷'):preview(s,d)
    d['total_parts']=1;d['tasks'][1]['parent_version']='missing'
    with pytest.raises(ValueError,match='引用'):preview(s,d)
    assert s.repo.list('project')==[]
    d=handoff();d['tasks'].append(d['tasks'][0])
    with pytest.raises(ValueError,match='重复'):preview(s,d)


def test_native_round_trip_preserves_files_history_rules_and_refs(tmp_path):
    a=Repository(tmp_path/'a');s=ProjectTransfer(a);pid=s.commit(preview(s,handoff())['token'],accept_rules=True)['project_id']
    from waypoint.materials import Materials
    m=Materials(a).import_bytes(pid,'参考.txt','原文内容'.encode())
    t=a.list('task',project_id=pid)[0];a.update_task(t['id'],{'source_ids':[m['id']]})
    from waypoint.context import build_context
    snap=build_context(a,t['id'],'english')
    rev=a.save_revision(t['id'],'english','New exact text.',a.task(t['id'])['input_epoch'],snapshot_id=snap['id'])
    a.record_approval(rev['id'],'client','客户明确同意此版')
    a.add_rule(None,'通用写作偏好');other=a.create_project('不应导出');a.create_task(TaskSpec(project_id=other,raw_input='另一个项目'))
    data=s.export(pid)
    b=Repository(tmp_path/'b');b.save_settings({'api_enabled':False});dest=ProjectTransfer(b)
    p=dest.preview([('archive.zip',data)]);np=dest.commit(p['token'],accept_rules=True)['project_id']
    nt=b.list('task',project_id=np)[0];nr=b.revision(nt['active']['english'])
    assert nr['body']=='New exact text.' and b.approvals(nr['id'])[0]['evidence']=='客户明确同意此版'
    assert b.get(nr['snapshot_id'],'snapshot')['task_id']==nt['id']
    nm=next(m for m in b.list('material',project_id=np) if m['name']=='参考.txt')
    assert (b.db.root/'attachments'/nm['path']).read_bytes()=='原文内容'.encode()
    assert len(b.list('project'))==1 and b.settings()['api_enabled'] is False
    assert any('通用写作偏好' in x['text'] for x in b.rules(np))
    assert not [x for x in b.list('rule') if x['project_id'] is None]
    assert dest.history(np)['records'][0]['text']==handoff()['history'][0]['text']


def test_malicious_archive_and_confirm_gate(tmp_path):
    s=ProjectTransfer(Repository(tmp_path));p=preview(s,handoff())
    with pytest.raises(ValueError,match='规则'):s.commit(p['token'],accept_rules=False)
    assert s.repo.list('project')==[]
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w') as z:z.writestr('../escape','bad')
    with pytest.raises(ValueError):s.preview([('bad.zip',f.getvalue())])
    assert not (tmp_path.parent/'escape').exists()


def test_multiple_parts_preserve_order_and_reject_duplicate_keys(tmp_path):
    d=handoff();second=json.loads(json.dumps(d));d['total_parts']=second['total_parts']=2;second['part']=2
    second['tasks']=d['tasks'][1:];d['tasks']=d['tasks'][:1];second['materials']=[];second['history']=[]
    s=ProjectTransfer(Repository(tmp_path));files=[('second.json',json.dumps(second).encode()),('first.json',json.dumps(d).encode())]
    p=s.preview(files);pid=s.commit(p['token'],accept_rules=True)['project_id']
    assert len(s.repo.list('task',project_id=pid))==2
    assert s.history(pid)['total']==1


def test_commit_failure_rolls_back_database_and_files(tmp_path,monkeypatch):
    r=Repository(tmp_path);s=ProjectTransfer(r);p=preview(s,handoff());original=r._put
    def fail(kind,data):
        if kind=='transfer':raise OSError('disk failure')
        original(kind,data)
    monkeypatch.setattr(r,'_put',fail)
    with pytest.raises(OSError):s.commit(p['token'],accept_rules=True)
    assert not r.list('project') and not list((r.db.root/'attachments').iterdir())


def test_native_corruption_cannot_change_existing_project(tmp_path):
    r=Repository(tmp_path);s=ProjectTransfer(r);pid=r.create_project('原项目');data=s.export(pid)
    f=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as z,zipfile.ZipFile(f,'w') as out:
        for n in z.namelist():out.writestr(n,b'{}' if n=='project.json' else z.read(n))
    with pytest.raises(ValueError,match='校验'):s.preview([('bad.zip',f.getvalue())])
    assert len(r.list('project'))==1


def test_transfer_api_preview_commit_history_and_attachment(tmp_path):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    with TestClient(create_app(tmp_path,accounts_enabled=False),base_url='http://127.0.0.1:8765') as c:
        h={'X-Waypoint-Token':c.get('/api/session').json()['token']}
        assert 'waypoint-handoff' in c.get('/api/transfer/prompt').text
        p=c.post('/api/transfer/preview',data={'text':json.dumps(handoff())},headers=h)
        assert p.status_code==200 and c.get('/api/projects').json()==[]
        result=c.post('/api/transfer/commit',json={'token':p.json()['token'],'accept_rules':True},headers=h)
        assert result.status_code==200
        pid=result.json()['project_id'];rows=c.get(f'/api/projects/{pid}/history',params={'q':'用户意见'}).json()
        assert rows['total']==1
        m=next(m for m in c.get('/api/materials',params={'project_id':pid}).json() if m.get('missing_attachment'))
        result=c.post('/api/materials/'+m['id']+'/complete-file',files={'file':('原件.txt','补传文件'.encode())},headers=h)
        assert result.status_code==200 and result.json()['missing_attachment'] is False
        assert c.get('/api/materials/'+m['id']+'/file').content=='补传文件'.encode()
        assert c.get(f'/api/projects/{pid}/export').content.startswith(b'PK')
        assert c.get('/api/settings').json()['api_enabled'] is False


def test_project_summary_enters_context_but_unconfirmed_preference_is_not_rule(tmp_path):
    from waypoint.context import build_context
    d=handoff();d['project']['preference_candidates']=['可能更喜欢短句，待确认']
    r=Repository(tmp_path);s=ProjectTransfer(r);pid=s.commit(preview(s,d)['token'],accept_rules=True)['project_id']
    t=r.list('task',project_id=pid)[0];context=build_context(r,t['id'],'english')
    assert context['project']['description']=='面向摄影爱好者'
    assert any(m['text']=='客户希望简洁自然' for m in context['materials'])
    assert not any('可能更喜欢' in x['text'] for x in context['rules'])


def test_native_forbidden_records_rejected_and_archived_jobs_accessible(tmp_path):
    from waypoint.transfer import validate
    with pytest.raises(ValueError,match='类型'):validate([{'kind':'settings','data':{'id':'settings'}}],{})
    r=Repository(tmp_path);s=ProjectTransfer(r);pid=r.create_project('测试')
    tid=r.create_task(TaskSpec(project_id=pid,raw_input='中文'))
    r.put('job',{'id':'job-test','task_id':tid,'status':'running','partial':'部分输出','message':'运行中','usage':[],
                 'thread_id':'private-session','turn_id':'private-turn'})
    content=s.export(pid)
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        records=json.loads(z.read('project.json'))['records']
        j=next(x['data'] for x in records if x['kind']=='archived_job')
        assert j['partial']=='部分输出' and 'thread_id' not in j
    other=ProjectTransfer(Repository(tmp_path/'other'));p=other.preview([('copy.zip',content)]);np=other.commit(p['token'],accept_rules=True)['project_id']
    assert other.repo.list('task',project_id=np)[0]['status']=='paused'
    assert not other.repo.list('job')
    assert other.repo.list('archived_job')[0]['partial']=='部分输出'
