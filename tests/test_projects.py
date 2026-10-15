import pytest
from waypoint.contracts import TaskSpec,Opinion
from waypoint.materials import Materials
from test_repository import make

def test_rename_pin_and_reorder_persist(tmp_path):
    r,p,t=make(tmp_path);q=r.create_project('乙');u=r.create_project('丙')
    r.update_project(p,{'name':'TOPDON'});assert r.task(t)['project_id']==p
    r.update_project(u,{'pinned':True});assert r.projects()[0]['id']==u
    r.reorder_projects([u,q,p]);assert [x['id'] for x in r.projects()]==[u,q,p]
    from waypoint.repository import Repository
    assert [x['id'] for x in Repository(tmp_path).projects()]==[u,q,p]
    assert r.get(p,'project')['name_history'][0]['name']=='甲'
    with pytest.raises(ValueError):r.reorder_projects([p,p])

def test_merge_keeps_ids_files_opinions_rules_and_can_undo(tmp_path):
    r,p,t=make(tmp_path);q=r.create_project('目标');m=Materials(r).import_bytes(p,'证据.txt','原件'.encode())
    r.update_task(t,{'source_ids':[m['id']]});rev=r.save_revision(t,'english','Original.',r.task(t)['input_epoch'])
    r.record_approval(rev['id'],'user','原稿核对记录')
    op=Opinion(task_id=t,stage='english',source='client',base_revision_id=rev['id'],scope='selection',selection='Original.',raw_text='仅调整这一句')
    r.add_opinion(op);approval=r.approvals(rev['id'])[0]
    r.add_rule(p,'源规则');r.add_rule(q,'目标规则')
    preview=r.preview_project_merge(p,q);receipt=r.merge_projects(p,q,preview['fingerprint'])
    assert r.task(t)['project_id']==q and r.revision(rev['id'])['body']=='Original.'
    assert r.get(m['id'],'material')['project_id']==q
    assert r.get(op.id,'opinion')['base_revision_id']==rev['id']
    assert r.get(approval['id'],'approval')['evidence']=='原稿核对记录'
    assert r.revision(rev['id'])['stale']
    assert (r.db.root/'attachments'/m['path']).read_bytes()=='原件'.encode()
    assert p not in {x['id'] for x in r.projects()} and r.get(p,'project')['merged_into']==q
    assert '源规则' in r.rules(q)[-1]['text'] and '目标规则' in r.rules(q)[-1]['text']
    r.undo_project_merge(receipt['id']);assert r.task(t)['project_id']==p
    assert r.get(m['id'],'material')['project_id']==p and not r.get(p,'project').get('merged_into')
    assert r.get(op.id,'opinion')['selection']=='Original.'

def test_merge_preview_race_and_active_jobs_write_nothing(tmp_path):
    r,p,t=make(tmp_path);q=r.create_project('乙');preview=r.preview_project_merge(p,q)
    r.update_project(q,{'name':'乙新名称'})
    with pytest.raises(ValueError,match='变化'):r.merge_projects(p,q,preview['fingerprint'])
    assert r.task(t)['project_id']==p
    r.put('job',{'id':'running','task_id':t,'status':'running'})
    with pytest.raises(ValueError,match='运行'):r.preview_project_merge(p,q)

def test_undo_rejects_new_edits_and_native_export_after_merge(tmp_path):
    from waypoint.transfer import ProjectTransfer
    from waypoint.repository import Repository
    r,p,t=make(tmp_path/'a');q=r.create_project('乙');preview=r.preview_project_merge(p,q)
    receipt=r.merge_projects(p,q,preview['fingerprint']);data=ProjectTransfer(r).export(q)
    dest=ProjectTransfer(Repository(tmp_path/'b'));pre=dest.preview([('brand.zip',data)])
    pid=dest.commit(pre['token'],accept_rules=True)['project_id'];assert len(dest.repo.list('task',project_id=pid))==1
    r.update_task(t,{'raw_input':'合并后的新意见'})
    with pytest.raises(ValueError,match='修改'):r.undo_project_merge(receipt['id'])
    assert r.task(t)['raw_input']=='合并后的新意见'
