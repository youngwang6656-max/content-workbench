"""Community plans are evidence; generated alternatives remain ordinary versioned tasks."""
import re
from waypoint.contracts import TaskSpec, now, uid

def community_name(value):
    name=str(value).strip().removeprefix('r/').removeprefix('/r/').rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,30}',name):raise ValueError('社群格式应为 r/社群名')
    return 'r/'+name

def checked_plan(items):
    if not isinstance(items,list) or not 1<=len(items)<=5:raise ValueError('请先确认 1–5 个发布社群')
    seen=set();out=[]
    for item in items:
        name=community_name(item.get('name',''));key=name.lower()
        if key in seen:raise ValueError('同一社群不能重复选择')
        seen.add(key)
        if type(item.get('variants')) is not int or not 1<=item['variants']<=3:raise ValueError('每个社群需要 1–3 个候选版本')
        # Selection confirmation is separate from evidence verification.
        # Missing rules do not block simulation once communities are chosen.
        out.append(dict(item,name=name))
    return out

def invalidate_children(repo,group_id):
    for child in repo.list('task',post_group_id=group_id):
        child['input_epoch']+=1;child['message']='主帖输入或社群方案已变化，请从主帖继续';child['updated_at']=now()
        repo._put('task',child)
        for rid in child['active'].values():repo._stale(rid)

def save_plan(repo,task_id,items,expected_epoch):
    if not isinstance(items,list) or len(items)>10 or any(not isinstance(x,dict) for x in items):raise ValueError('社群方案格式不正确')
    allowed={'name','variants','rules_zh','culture_zh','confirmed','reason_zh'}
    cleaned=[]
    for item in items:
        if set(item)-allowed:raise ValueError('社群证据不能通过编辑方案伪造')
        if any(len(str(v))>12000 for v in item.values()):raise ValueError('社群说明过长')
        cleaned.append(dict(item))
    confirmed=bool(cleaned) and all(x.get('confirmed') is True for x in cleaned)
    if confirmed:checked_plan(cleaned)
    with repo.db.lock,repo.db.conn:
        t=repo.task(task_id)
        if t['kind']!='post' or t.get('post_group_id'):raise ValueError('仅主帖可配置发布社群')
        if t['input_epoch']!=expected_epoch:raise ValueError('任务已变化，请刷新后保存方案')
        if t.get('community_plan',[])==cleaned and t.get('community_selection_pending',False)==(not confirmed):return t
        t.setdefault('community_plan_history',[]).append({'plan':t.get('community_plan',[]),'saved_at':now()})
        t.update(community_plan=cleaned,community_selection_pending=not confirmed,input_epoch=t['input_epoch']+1,updated_at=now())
        repo._put('task',t);invalidate_children(repo,task_id)
    return t

def prepare_variants(repo,task_id):
    with repo.db.lock,repo.db.conn:
        t=repo.task(task_id)
        if t.get('community_selection_pending'):raise ValueError('请先勾选社群并确认每个社群的帖文数量')
        plan=checked_plan(t.get('community_plan'))
        for opinion in repo.list('opinion',task_id=task_id):
            if opinion['status']=='pending' and (opinion.get('base_revision_id') or opinion['source']=='client'):
                raise ValueError('主帖有针对旧稿的意见，请先在原稿处理，再确认社群方案')
        existing=repo.list('task',post_group_id=task_id);active=[]
        for profile in plan:
            for number in range(1,profile['variants']+1):
                child=next((x for x in existing if x['community']['name'].lower()==profile['name'].lower() and x['variant_number']==number),None)
                if child is None:
                    spec={k:v for k,v in t.items() if k in TaskSpec.model_fields}
                    spec['name']=f"{t['name'] or '帖文'} · {profile['name']} · 候选 {number}"
                    child=repo.task(repo.create_task(TaskSpec(**spec)))
                    child.update(post_group_id=task_id,variant_number=number,group_epoch=-1)
                    repo._put('task',child)
                if child.get('group_epoch')!=t['input_epoch']:
                    patch={k:t[k] for k in ('raw_input','input_stage','target_stage','pause_at','source_ids','parent_revision_id')}
                    repo.update_task(child['id'],patch);child=repo.task(child['id'])
                    child.update(community=profile,group_epoch=t['input_epoch'],retired=False)
                    # Shared opinions are copied as evidence, never as approval. A revision-specific
                    # legacy/customer request must be handled against its original draft.
                    for opinion in repo.list('opinion',task_id=task_id):
                        if opinion['status']!='pending':continue
                        if opinion.get('base_revision_id') or opinion['source']=='client':
                            raise ValueError('主帖有针对旧稿的意见，请先在原稿处理，再确认社群方案')
                        if not any(o.get('origin_opinion_id')==opinion['id'] for o in repo.list('opinion',task_id=child['id'])):
                            repo._put('opinion',dict(opinion,id=uid(),task_id=child['id'],origin_opinion_id=opinion['id']))
                    repo._put('task',child)
                if not child.get('abandoned'):
                    active.append(child)
        ids={x['id'] for x in active}
        for child in existing:
            if child['id'] not in ids and not child.get('abandoned'):
                child['retired']=True;repo._put('task',child)
        return active

def validate_leaf(repo,task):
    group=repo.task(task['post_group_id'])
    if group.get('community_selection_pending'):raise ValueError('请回主帖勾选社群并确认帖文数量后继续')
    if group['kind']!='post' or group.get('post_group_id') or group['project_id']!=task['project_id']:raise ValueError('候选稿主帖关系不正确')
    plan=checked_plan(group.get('community_plan'))
    profile=next((x for x in plan if x['name'].lower()==task['community']['name'].lower()),None)
    if task.get('retired') or task.get('abandoned') or task.get('group_epoch')!=group['input_epoch'] or not profile or not 1<=task['variant_number']<=profile['variants']:
        raise ValueError('社群方案或主帖已更新，请回主帖同步候选稿后继续')
    return profile
