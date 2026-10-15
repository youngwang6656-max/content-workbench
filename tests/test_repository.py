import pytest

def make(tmp_path):
    from waypoint.repository import Repository
    from waypoint.contracts import TaskSpec
    r=Repository(tmp_path); p=r.create_project('甲'); t=r.create_task(TaskSpec(project_id=p,raw_input='我的想法'))
    return r,p,t

def test_version_race_and_approval(tmp_path):
    from waypoint.contracts import Opinion
    r,p,t=make(tmp_path)
    a=r.save_revision(t,'english','First',expected_epoch=0)
    r.record_approval(a['id'],'client','客户确认')
    r.add_opinion(Opinion(task_id=t,stage='english',raw_text='新的意见'))
    b=r.save_revision(t,'english','Late',expected_epoch=0)
    assert b['candidate'] and r.task(t)['active']['english']==a['id']
    c=r.save_revision(t,'english','Current',expected_epoch=1)
    assert not c['candidate'] and not r.approvals(c['id'])
    with pytest.raises(ValueError):r.record_approval(c['id'],'client','')

def test_dependencies_and_isolation(tmp_path):
    from waypoint.contracts import TaskSpec
    r,p,t=make(tmp_path)
    a=r.save_revision(t,'english','First',expected_epoch=0)
    tr=r.save_revision(t,'backtranslation','第一版',expected_epoch=0,source_revision_id=a['id'])
    c=r.create_task(TaskSpec(project_id=p,kind='comment',comment_kind='own',parent_revision_id=a['id']))
    cr=r.save_revision(c,'english','Reply',expected_epoch=0)
    r.save_revision(t,'english','Second',expected_epoch=0)
    assert r.revision(tr['id'])['stale'] and r.revision(cr['id'])['stale']
    p2=r.create_project('乙')
    with pytest.raises(ValueError):r.create_task(TaskSpec(project_id=p2,parent_revision_id=a['id']))

def test_manual_edit_preserves_raw_and_history(tmp_path):
    r,p,t=make(tmp_path)
    r.update_task(t,{'raw_input':'新想法'})
    assert r.task(t)['raw_history']==['我的想法']
    assert r.task(t)['input_epoch']==1
