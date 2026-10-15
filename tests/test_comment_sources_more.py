import asyncio
from datetime import datetime,timezone,timedelta
from test_comment_sources import setup
from waypoint.comment_sources import verified_posts,validate_source
from waypoint.transfer import ProjectTransfer
from waypoint.repository import Repository
from waypoint.contracts import TaskSpec
import pytest

def test_zero_to_thirty_days_and_missing_results(tmp_path):
    c,r,p,pid=setup(tmp_path)
    p.answer={'items':[],'message_zh':'没有足够证据'}
    for days in (-1,31,1.5,True):
        assert c.post('/api/comment-sources/search',json={'project_id':pid,'days':days}).status_code==400
    for days in (0,30):
        result=c.post('/api/comment-sources/search',json={'project_id':pid,'days':days,'count':5})
        assert result.status_code==200 and result.json()['items']==[] and '0 / 5' in result.json()['message']

def test_comment_transfer_keeps_source_and_original_text(tmp_path):
    c,r,p,pid=setup(tmp_path/'from')
    source=c.post('/api/comment-sources',json={'project_id':pid,'mode':'text','text':'Original post.'}).json()
    tid=c.post('/api/comments',json={'project_id':pid,'source_id':source['id'],'confirmed':True,'source_text':'Original post.\nUser correction.'}).json()['id']
    translated=c.post('/api/reading-translation',json={'project_id':pid,'material_id':source['id']}).json()
    t=r.task(tid);validate_source(r,t)
    archive=ProjectTransfer(r).export(pid);dest=Repository(tmp_path/'to');transfer=ProjectTransfer(dest)
    preview=transfer.preview([('brand.zip',archive)]);newpid=transfer.commit(preview['token'],accept_rules=True)['project_id']
    task=dest.list('task',project_id=newpid)[0];validate_source(dest,task)
    assert task['comment_source_id']!=t['comment_source_id']
    saved=dest.get(task['comment_source_id'],'material')
    assert saved['text']=='Original post.\nUser correction.' and dest.get(saved['original_material_id'],'material')['text']=='Original post.'
    reading=next(x for x in dest.list('material') if x.get('reading_translation'))
    assert reading['reading_origin']['original_material_id']!=source['id']

def test_source_edit_preserves_history_opinions_and_rejects_race(tmp_path):
    c,r,p,pid=setup(tmp_path)
    source=c.post('/api/comment-sources',json={'project_id':pid,'mode':'text','text':'First post.'}).json()
    tid=c.post('/api/comments',json={'project_id':pid,'source_id':source['id'],'confirmed':True}).json()['id']
    t=r.task(tid);rev=r.save_revision(tid,'english','Exact old comment.',0)
    data={'project_id':pid,'source_id':source['id'],'confirmed':True,'source_text':'Rechecked post.','task_id':tid,'expected_epoch':99}
    assert c.post('/api/comments',json=data).status_code==400
    assert r.revision(rev['id'])['body']=='Exact old comment.'
    data['expected_epoch']=0;assert c.post('/api/comments',json=data).status_code==400
    assert r.task(tid)['comment_source_id']==t['comment_source_id']
    assert not r.revision(rev['id'])['stale'] and r.revision(rev['id'])['body']=='Exact old comment.'
    with pytest.raises(ValueError):r.update_task(tid,{'source_ids':[]})
    validate_source(r,r.task(tid))

def test_generic_new_comments_pause_before_any_model_call(tmp_path):
    c,r,p,pid=setup(tmp_path)
    assert c.post('/api/tasks',json={'project_id':pid,'kind':'comment','raw_input':'Write a comment.'}).status_code==400
    tid=r.create_task(TaskSpec(project_id=pid,kind='comment',raw_input='Legacy unbound comment.'))
    r.set_task_state(tid,comment_source_required=True)
    job=asyncio.run(c.app.state.engine.run_and_wait(tid))
    assert job['status']=='paused' and not p.requests
