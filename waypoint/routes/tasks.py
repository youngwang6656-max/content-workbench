from fastapi import Body
from waypoint.contracts import TaskSpec,Opinion,uid,now
from waypoint.reviews import compare_revisions
from waypoint.progress import task_view

def install(app):
    r=app.state.repo;e=app.state.engine
    @app.get('/api/projects')
    def projects(sort:str='manual'):return r.projects(sort=sort)
    @app.patch('/api/projects/{id}')
    def rename_project(id:str,data:dict=Body(...)):return r.update_project(id,data)
    @app.post('/api/projects/reorder')
    def reorder_projects(data:dict=Body(...)):return r.reorder_projects(data.get('ids'))
    @app.get('/api/projects/{id}/management')
    def project_management(id:str):return r.project_management(id)
    @app.post('/api/projects/{id}/merge-preview')
    def merge_preview(id:str,data:dict=Body(...)):return r.preview_project_merge(id,data.get('target_id'))
    @app.post('/api/projects/{id}/merge')
    def merge(id:str,data:dict=Body(...)):return r.merge_projects(id,data.get('target_id'),data.get('fingerprint'))
    @app.post('/api/project-merges/{id}/undo')
    def undo_merge(id:str):return r.undo_project_merge(id)
    @app.post('/api/projects')
    def project(data:dict=Body(...)):
        return {'id':r.create_project(data.get('name',''),data.get('description',''))}
    @app.get('/api/tasks')
    def tasks(project_id:str|None=None):return [task_view(r,t) for t in r.list('task',**({'project_id':project_id} if project_id else {}))]
    @app.post('/api/tasks')
    def create(spec:TaskSpec):
        if spec.kind=='comment':raise ValueError('请先选择一篇原帖，再通过评论入口新建任务')
        id=r.create_task(spec)
        if spec.kind=='comment':r.set_task_state(id,comment_source_required=True)
        return {'id':id}
    @app.post('/api/tasks/batch')
    def batch(data:dict=Body(...)):
        items=data.get('items',[])
        if not 1<=len(items)<=20:raise ValueError('每批支持一至二十条任务')
        specs=[TaskSpec(**x) for x in items]
        if any(s.kind=='comment' for s in specs):raise ValueError('批量评论请先选择原帖，再通过批量铺评入口新建任务')
        # Validate all foreign references before the first mutation.
        for s in specs:
            r.active_project(s.project_id)
            for sid in s.source_ids:
                if r.get(sid,'material')['project_id'] not in (None,s.project_id):raise ValueError('资料不属于此项目')
            if s.parent_revision_id:
                pr=r.revision(s.parent_revision_id);pt=r.task(pr['task_id'])
                if pt['project_id']!=s.project_id or (s.kind=='comment' and s.comment_kind=='own' and pt['kind']!='post'):raise ValueError('父稿关联不正确')
        ids=[r.create_task(x) for x in specs]
        for id,spec in zip(ids,specs):
            if spec.kind=='comment':r.set_task_state(id,comment_source_required=True)
        return {'ids':ids}
    @app.post('/api/tasks/run-batch')
    async def run_batch(data:dict=Body(...)):
        ids=data.get('ids',[])
        if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):raise ValueError('任务列表不正确')
        return {'results':e.start_batch(ids)}
    @app.get('/api/tasks/{id}')
    def task(id:str):
        from waypoint.word_counts import counted
        t=r.task(id);revisions=[counted(x) for x in r.list('revision',task_id=id)]
        return {'task':task_view(r,t),'revisions':revisions,'opinions':r.list('opinion',task_id=id),
                'approvals':[a for a in r.list('approval') if a['revision_id'] in {v['id'] for v in revisions}],
                'jobs':r.list('archived_job',task_id=id)+r.list('job',task_id=id)}
    @app.patch('/api/tasks/{id}')
    def edit_task(id:str,data:dict=Body(...)):return r.update_task(id,data)
    @app.post('/api/tasks/{id}/opinions')
    def opinion(id:str,data:dict=Body(...)):
        data['task_id']=id;op=Opinion(**data);epoch=r.add_opinion(op);return {'id':op.id,'input_epoch':epoch}
    @app.post('/api/tasks/{id}/run')
    async def run(id:str,data:dict=Body(default={})):
        return {'job_id':e.start_task(id,resume=bool(data.get('resume',False)))}
    @app.post('/api/tasks/{id}/to-english')
    async def to_english(id:str,data:dict=Body(...)):
        result=r.continue_to_english(id,data.get('revision_id'))
        if result['changed']:return {'job_id':e.start_task(id,resume=True),'continued':True}
        return {'continued':False,'message':'此查看节点已继续到英文流程；不会重复调用模型'}
    @app.post('/api/jobs/{id}/stop')
    async def stop(id:str):await e.stop_job(id);return {'ok':True}
    @app.post('/api/tasks/{id}/revisions')
    def manual(id:str,data:dict=Body(...)):
        t=r.task(id)
        if data.get('expected_epoch')!=t['input_epoch']:raise ValueError('任务已发生变化，请刷新后保存，避免覆盖新意见')
        body=data.get('body','');title=data.get('title','')
        if len(body)>100000 or len(title)>1000:raise ValueError('稿件过长')
        return r.save_manual_revision(id,data.get('stage','english'),body,data.get('expected_epoch'),title=title)
    @app.post('/api/revisions/{id}/approve')
    def approve(id:str,data:dict=Body(...)):
        r.record_approval(id,data.get('reviewer','user'),data.get('evidence',''));return {'ok':True}
    @app.post('/api/revisions/{id}/pass')
    def pass_simulation(id:str):return r.pass_simulation(id)
    @app.post('/api/tasks/{id}/abandon')
    def abandon_variant(id:str):return r.abandon_variant(id)
    @app.post('/api/tasks/{id}/restore')
    def restore_variant(id:str):return r.restore_variant(id)
    @app.get('/api/revisions/{id}/diff')
    def diff(id:str):
        rev=r.revision(id);before=r.revision(rev['parent_id']) if rev['parent_id'] else {}
        return compare_revisions(before,rev)
    @app.post('/api/tasks/{id}/publication')
    def publish_record(id:str,data:dict=Body(...)):
        if data.get('url') and not data['url'].startswith(('https://','http://')):raise ValueError('请填写完整发布链接')
        r.set_task_state(id,publication={k:str(data.get(k,''))[:5000] for k in ['url','date','result']});return {'ok':True}
    @app.post('/api/opinions/{id}/resolve')
    def resolve(id:str,data:dict=Body(...)):
        op=r.get(id,'opinion')
        if data.get('status') not in ['processed','partial','conflict','no_change']:raise ValueError('处理状态不正确')
        op['status']=data['status'];r.put('opinion',op);return op
