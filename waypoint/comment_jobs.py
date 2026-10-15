"""Persistent source selection searches and independent comment batches."""
import asyncio
import hashlib
import json
from waypoint.contracts import uid, now, TaskSpec

ACTIVE = ('queued', 'running')


def shared_failure(message):
    if isinstance(message,OSError):return True
    return any(word in str(message) for word in ('额度', '连接', '登录', 'API 未启用', 'API 配置',
        'API 密钥', '服务商', '预算', '价格', '未知费用', '订阅', '进程断开', '网络', '超时', 'timeout', 'HTTP 401', 'HTTP 429'))


def request_key(data):
    value=data.get('request_id')
    if not isinstance(value,str) or not 1<=len(value)<=100:raise ValueError('请提供有效请求标识')
    return value


class CommentSearchJobs:
    def __init__(self, engine, search):
        self.engine=engine; self.repo=engine.repo; self.search=search; self.tasks={}

    def get(self,id):return self.repo.get(id,'comment_search_job')

    def latest(self,pid):
        self.repo.active_project(pid)
        rows=self.repo.list('comment_search_job',project_id=pid)
        return rows[-1] if rows else None

    def start(self,data):
        pid=data.get('project_id'); self.repo.active_project(pid); key=request_key(data)
        count=data.get('count',3); days=data.get('days',10); goal=data.get('keywords','')
        if type(count) is not int or not 1<=count<=5:raise ValueError('搜索数量为 1–5 篇')
        if type(days) is not int or not 0<=days<=30:raise ValueError('时间范围为 0–30 天；0 表示今天')
        if not isinstance(goal,str) or len(goal)>4000:raise ValueError('搜索意图过长或格式不正确')
        with self.repo.db.lock,self.repo.db.conn:
            rows=self.repo.list('comment_search_job',project_id=pid)
            match=next((x for x in rows if x['request_id']==key),None)
            if match:return match
            active=next((x for x in reversed(rows) if x['status'] in ACTIVE),None)
            if active:return active
            record={'id':uid(),'project_id':pid,'request_id':key,'count':count,'days':days,'keywords':goal,
                    'status':'queued','message':'等待模型搜索','created_at':now(),'updated_at':now(),
                    'result':None,'selected_source_ids':[],'raw_input':'','name':'','input_stage':'idea','target_stage':'english','batch_request_id':uid()}
            self.repo._put('comment_search_job',record)
        self.tasks[record['id']]=asyncio.create_task(self._run(record['id']))
        return record

    def _state(self,id,status,message,**fields):
        with self.repo.db.lock,self.repo.db.conn:
            record=self.get(id); record.update(status=status,message=message,updated_at=now(),**fields)
            self.repo._put('comment_search_job',record)
        return record

    async def _run(self,id):
        try:
            async with self.engine.lock:
                record=self.get(id); self.repo.active_project(record['project_id'])
                self._state(id,'running','正在全站搜索并核对原帖')
                result=await self.search(record,job_id=id,lock_held=True)
                # Save only once. Closing a browser has no connection to this task.
                self._state(id,'completed',result['message'],result=result,
                            selected_source_ids=[x['id'] for x in result['items']])
        except asyncio.CancelledError:
            self._state(id,'interrupted','搜索已停止，已有记录保留；继续搜索需主动重新开始')
        except (ValueError,OSError) as exc:self._state(id,'paused',str(exc))
        except Exception:self._state(id,'failed','搜索异常，条件与已有结果保留；请检查连接后重新搜索')
        finally:self.engine.current_providers.pop(id,None)

    def update(self,id,data):
        allowed={'selected_source_ids','raw_input','name','input_stage','target_stage','batch_request_id'}
        if set(data)-allowed:raise ValueError('搜索条件已固定，修改条件请重新搜索')
        with self.repo.db.lock,self.repo.db.conn:
            record=self.get(id); self.repo.active_project(record['project_id'])
            ids=data.get('selected_source_ids',record['selected_source_ids'])
            valid={x['id'] for x in (record.get('result') or {}).get('items',[])}
            if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids) or not set(ids)<=valid:
                raise ValueError('请选择本次搜索返回的原帖')
            TaskSpec(project_id=record['project_id'],kind='comment',**{k:data.get(k,record[k]) for k in ('name','raw_input','input_stage','target_stage')})
            if 'batch_request_id' in data:request_key({'request_id':data['batch_request_id']})
            record.update(data,updated_at=now());self.repo._put('comment_search_job',record)
        return record

    async def stop(self,id):
        record=self.get(id)
        if record['status'] not in ACTIVE:return record
        provider=self.engine.current_providers.get(id)
        future=self.tasks.get(id)
        try:
            if provider:await provider.interrupt(id)
        except (ValueError,OSError):pass
        finally:
            if future:future.cancel();await asyncio.gather(future,return_exceptions=True)
        return self._state(id,'interrupted','搜索已停止，已有记录保留；继续搜索需主动重新开始')

    def recover(self):
        for record in self.repo.list('comment_search_job'):
            if record['status'] in ACTIVE:self._state(record['id'],'interrupted','程序曾中断，未自动重复搜索；请主动重新搜索')

    async def wait(self):
        if self.tasks:await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)

    async def close(self):
        for id in list(self.tasks):
            if not self.tasks[id].done():await self.stop(id)
        await self.wait()


def bound_source(repo,task):
    return task.get('comment_source_id') if task.get('kind')=='comment' else None


def ensure_source_edit(repo,task,source_id,text):
    current=bound_source(repo,task)
    if not current:return
    original=repo.get(current,'material')
    if source_id not in (current,original.get('original_material_id')) or text!=original['text']:
        raise ValueError('评论原帖已固定，不能更换或改写；请围绕新原帖新建任务')


def protect_material(repo,id):
    if any(bound_source(repo,t)==id for t in repo.list('task')):
        raise ValueError('这是评论任务固定的原帖快照，不能改写；请新建任务')


async def create_batch(engine,data):
    from waypoint.comment_sources import source_material
    repo=engine.repo;pid=data.get('project_id');repo.active_project(pid);key=request_key(data)
    ids=data.get('source_ids',[]); revision_ids=data.get('revision_ids',[])
    if not isinstance(ids,list) or not isinstance(revision_ids,list) or bool(ids)==bool(revision_ids):
        raise ValueError('请选择原帖来源或自有帖文版本')
    selected=ids or revision_ids
    if not 1<=len(selected)<=20 or any(not isinstance(x,str) for x in selected) or len(set(selected))!=len(selected):
        raise ValueError('每批支持一至二十篇不同原帖')
    spec_fields={k:data.get(k,default) for k,default in (('name',''),('raw_input',''),('input_stage','idea'),('target_stage','english'))}
    TaskSpec(project_id=pid,kind='comment',**spec_fields)
    fingerprint=hashlib.sha256(json.dumps({'source_ids':ids,'revision_ids':revision_ids,**spec_fields},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with repo.db.lock:
        prior=next((x for x in repo.list('comment_batch',project_id=pid) if x['request_id']==key),None)
        if prior:
            if prior['fingerprint']!=fingerprint:raise ValueError('同一请求标识不能用于不同内容，请重新提交')
            return {'created':False,'results':[{'task_id':tid,'job_id':repo.task(tid).get('job_id'),'status':repo.task(tid)['status']} for tid in prior['task_ids']]}
        originals=[]
        for id in selected:
            if revision_ids:
                rev=repo.revision(id);parent=repo.task(rev['task_id'])
                if (parent['project_id']!=pid or parent['kind']!='post' or parent.get('abandoned') or parent.get('retired')
                    or rev['stage']!='english' or rev['stale'] or rev['candidate'] or not rev['complete'] or parent['active'].get('english')!=id):
                    raise ValueError('请选择本品牌当前有效的英文帖文版本')
                original={'id':uid(),'project_id':pid,'name':rev['title'] or parent['name'] or '自有帖文',
                    'text':'\n\n'.join(filter(None,[rev['title'],rev['body']])),'kind':'thread','url':'','published_at':'',
                    'trust':'user_confirmed','extraction':'text','archived':False,'created_at':now(),
                    'comment_source':True,'source_mode':'project','parent_revision_id':id}
            else:original=source_material(repo,pid,id)
            parent_id=original.get('parent_revision_id')
            if parent_id:
                rev=repo.revision(parent_id);parent=repo.task(rev['task_id'])
                if parent['project_id']!=pid or parent['kind']!='post' or parent.get('abandoned') or parent.get('retired') or rev['stale'] or rev['candidate'] or not rev['complete'] or parent['active'].get(rev['stage'])!=parent_id:
                    raise ValueError('关联原帖版本已变化，请围绕新版本新建任务')
            if not original['text'].strip():raise ValueError('原帖正文不能为空')
            originals.append(original)
        task_ids=[]
        # _create_task does not commit an inner transaction: snapshots and tasks
        # are all committed, or none, before any model job is scheduled.
        with repo.db.conn:
            for original in originals:
                if revision_ids:repo._put('material',original)
                frozen=dict(original,id=uid(),trust='simulation_selected',selected_at=now(),original_material_id=original['id'])
                repo._put('material',frozen)
                spec=TaskSpec(project_id=pid,kind='comment',comment_kind='own' if original.get('parent_revision_id') else 'natural',
                    **(spec_fields|{'name':(spec_fields['name']+' · '+original['name'] if spec_fields['name'] else '铺评 · '+original['name'])[:200]}),
                    source_ids=[frozen['id']],parent_revision_id=original.get('parent_revision_id'))
                tid=repo._create_task(spec);task=repo.task(tid)
                task.update(comment_source_id=frozen['id'],comment_source_required=True)
                repo._put('task',task);task_ids.append(tid)
            for tid in task_ids:
                task=repo.task(tid);task['comment_batch_id']=task_ids[0];repo._put('task',task)
            receipt={'id':uid(),'project_id':pid,'request_id':key,'fingerprint':fingerprint,'task_ids':task_ids,'created_at':now()}
            repo._put('comment_batch',receipt)
    return {'created':True,'results':engine.start_batch(task_ids)}


def install(app,search):
    from fastapi import Body
    jobs=CommentSearchJobs(app.state.engine,search);app.state.comment_search=jobs
    @app.post('/api/comment-search-jobs')
    async def start(data:dict=Body(...)):return jobs.start(data)
    @app.get('/api/comment-search-jobs')
    def latest(project_id:str):return jobs.latest(project_id)
    @app.get('/api/comment-search-jobs/{id}')
    def get(id:str):return jobs.get(id)
    @app.patch('/api/comment-search-jobs/{id}')
    def update(id:str,data:dict=Body(...)):return jobs.update(id,data)
    @app.post('/api/comment-search-jobs/{id}/stop')
    async def stop(id:str):return await jobs.stop(id)
    @app.post('/api/comments/batch')
    async def batch(data:dict=Body(...)):return await create_batch(app.state.engine,data)
