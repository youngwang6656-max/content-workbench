import asyncio,json,pytest
from waypoint.contracts import Opinion
from test_workflow import setup

def test_client_selection_outside_exactly_preserved(tmp_path):
    from waypoint.reviews import merge_selection
    before='One.\n\nTwo.\n\nThree.'
    assert merge_selection(before,'Two.','Updated.')=='One.\n\nUpdated.\n\nThree.'
    with pytest.raises(ValueError):merge_selection('Same. Same.','Same.','New.')

def test_client_feedback_no_supervisor_and_four_rounds(tmp_path):
    r,p,t,f,e=setup(tmp_path)
    a=r.save_revision(t,'english','First.\n\nSecond.',expected_epoch=0)
    r.add_opinion(Opinion(task_id=t,stage='english',source='client',base_revision_id=a['id'],scope='selection',selection='Second.',raw_text='改成更生活化'))
    asyncio.run(e.run_and_wait(t))
    current=r.revision(r.task(t)['active']['english'])
    assert current['body'].startswith('First.\n\n')
    assert r.task(t)['status']=='completed' and r.approvals(current['id'])==[]
    for i in range(4):r.add_opinion(Opinion(task_id=t,stage='english',source='client',raw_text=f'第{i}轮'))
    assert len(r.list('opinion',task_id=t))==5

def test_client_unspecified_scope_pauses_before_model(tmp_path):
    r,p,t,f,e=setup(tmp_path);a=r.save_revision(t,'english','First.',expected_epoch=0)
    r.add_opinion(Opinion(task_id=t,stage='english',source='client',base_revision_id=a['id'],raw_text='调整一句'))
    asyncio.run(e.run_and_wait(t));assert len(f.requests)==0 and r.task(t)['status']=='paused'
