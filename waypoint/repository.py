import json
from waypoint.db import Database
from waypoint.contracts import uid,now,DEFAULT_RULES,TaskSpec,Opinion,STAGES
from waypoint.projects import ProjectManagement

class Repository(ProjectManagement):
    def __init__(self,root): self.db=Database(root)
    def _get(self,id,kind=None):
        row=self.db.conn.execute('SELECT kind,data FROM records WHERE id=?',(id,)).fetchone()
        if not row or (kind and row[0]!=kind): raise ValueError('记录不存在或类型不符')
        return json.loads(row[1])
    def _put(self,kind,d):
        self.db.conn.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
            (d['id'],kind,json.dumps(d,ensure_ascii=False)))
    def get(self,id,kind=None):
        with self.db.lock: return self._get(id,kind)
    def list(self,kind,**filters):
        with self.db.lock:
            items=[json.loads(r[0]) for r in self.db.conn.execute('SELECT data FROM records WHERE kind=? ORDER BY rowid',(kind,))]
            return [d for d in items if all(d.get(k)==v for k,v in filters.items())]
    def put(self,kind,d):
        with self.db.lock,self.db.conn: self._put(kind,d)
        return d
    def create_project(self,name,description=''):
        if not isinstance(name,str) or not name.strip() or len(name.strip())>200: raise ValueError('品牌名称须为一至二百字')
        d={'id':uid(),'name':name.strip(),'description':description,'created_at':now(),'pinned':False,
           'sort_order':max((p.get('sort_order',i) for i,p in enumerate(self.projects())),default=-1)+1}
        self.put('project',d); return d['id']
    def create_task(self,spec:TaskSpec):
        with self.db.lock,self.db.conn:
            return self._create_task(spec)
    def _create_task(self,spec:TaskSpec):
        """Called inside the caller's lock and transaction, without committing it."""
        self.active_project(spec.project_id)
        if spec.parent_revision_id:
            parent=self._get(spec.parent_revision_id,'revision'); pt=self._get(parent['task_id'],'task')
            if pt['project_id']!=spec.project_id: raise ValueError('不能跨项目关联稿件')
            if spec.kind=='comment' and spec.comment_kind=='own' and pt['kind']!='post': raise ValueError('铺评需要关联帖文')
        for sid in spec.source_ids:
            if self._get(sid,'material')['project_id'] not in (None,spec.project_id): raise ValueError('资料不属于此项目')
        d=spec.model_dump()|{'id':uid(),'input_epoch':0,'active':{},'status':'queued','raw_history':[],
            'created_at':now(),'updated_at':now(),'message':'','publication':{},'job_id':None}
        if spec.kind in ('post','comment'):d['checkpoint_stage']=spec.target_stage
        self._put('task',d); return d['id']
    def task(self,id): return self.get(id,'task')
    def revision(self,id): return self.get(id,'revision')
    def update_task(self,id,patch):
        allowed={'raw_input','name','input_stage','target_stage','pause_at','source_ids','parent_revision_id'}
        if set(patch)-allowed: raise ValueError('不允许更新此字段')
        with self.db.lock,self.db.conn:
            t=self._get(id,'task'); data={k:t[k] for k in TaskSpec.model_fields}; data.update(patch)
            if t['kind']=='comment' and t.get('comment_source_id'):
                if data['parent_revision_id']!=t.get('parent_revision_id') or t['comment_source_id'] not in data['source_ids']:
                    raise ValueError('评论原帖已固定，不能更换；请新建任务')
                for sid in data['source_ids']:
                    if sid!=t['comment_source_id'] and self._get(sid,'material').get('comment_source'):
                        raise ValueError('一篇原帖一个评论任务；请为其他原帖新建任务')
            spec=TaskSpec(**data)
            for sid in spec.source_ids:
                if self._get(sid,'material')['project_id'] not in (None,t['project_id']): raise ValueError('资料不属于此项目')
            if spec.parent_revision_id:
                r=self._get(spec.parent_revision_id,'revision')
                if self._get(r['task_id'],'task')['project_id']!=t['project_id']: raise ValueError('不能跨项目关联')
                ancestor=self._get(r['task_id'],'task');visited={id}
                while True:
                    if ancestor['id'] in visited:raise ValueError('父稿关联不能构成循环')
                    visited.add(ancestor['id'])
                    if not ancestor.get('parent_revision_id'):break
                    ancestor=self._get(self._get(ancestor['parent_revision_id'],'revision')['task_id'],'task')
            if all(t.get(k)==v for k,v in patch.items()): return t
            if 'raw_input' in patch and t['raw_input']!=patch['raw_input']: t['raw_history'].append(t['raw_input'])
            t.update(spec.model_dump()); t['input_epoch']+=1; t['updated_at']=now()
            if t['kind'] in ('post','comment'):
                t['checkpoint_stage']=spec.target_stage;t.pop('checkpoint_revision_id',None)
            for rid in t['active'].values(): self._stale(rid)
            self._put('task',t)
            if t['kind']=='post' and not t.get('post_group_id'):
                from waypoint.communities import invalidate_children
                invalidate_children(self,id)
            return t
    def set_task_state(self,id,**fields):
        with self.db.lock,self.db.conn:
            t=self._get(id,'task'); t.update(fields); t['updated_at']=now(); self._put('task',t)
    def add_opinion(self,op:Opinion):
        with self.db.lock,self.db.conn:
            t=self._get(op.task_id,'task')
            if op.base_revision_id and self._get(op.base_revision_id,'revision')['task_id']!=t['id']: raise ValueError('意见原稿不属于此任务')
            if op.scope=='selection' and not (op.selection or op.paragraph_ids): raise ValueError('请指定修改范围')
            d=op.model_dump()|{'status':'pending','created_at':now()}; self._put('opinion',d)
            if t['kind'] in ('post','comment') and op.stage not in ('english','backtranslation') and op.base_revision_id==t['active'].get(op.stage):
                t['target_stage']=op.stage;t['checkpoint_stage']=op.stage;t.pop('checkpoint_revision_id',None)
            t['input_epoch']+=1
            if t['status']!='running':t['status']='paused'
            t['message']='有新的意见待处理'
            for rid in t['active'].values():
                if rid==t.get('checkpoint_revision_id') and op.stage in ('english','backtranslation'):continue
                self._stale(rid)
            self._put('task',t)
            if t['kind']=='post' and not t.get('post_group_id'):
                from waypoint.communities import invalidate_children
                invalidate_children(self,t['id'])
            return t['input_epoch']
    def _stale(self,rid):
        r=self._get(rid,'revision'); r['stale']=True; self._put('revision',r)
        self._dependents(rid,set())
    def mark_dependents_stale(self,rid):
        with self.db.lock,self.db.conn: return self._dependents(rid,set())
    def _dependents(self,rid,seen,bumped=None):
        if rid in seen:return []
        seen.add(rid);changed=[];bumped=bumped if bumped is not None else set()
        # Invalidate the child task even if it has no output yet. This protects in-flight work.
        related_tasks={t['id'] for t in self.list('task') if t.get('parent_revision_id')==rid}
        for tid in related_tasks:
            if tid not in bumped:
                t=self._get(tid,'task');t['input_epoch']+=1;t['message']='关联父稿已变化，请重新核对'
                t['updated_at']=now();self._put('task',t);bumped.add(tid)
        for r in self.list('revision'):
            if r.get('source_revision_id')==rid or r.get('checkpoint_revision_id')==rid or r['task_id'] in related_tasks:
                r['stale']=True;self._put('revision',r);changed.append(r['id'])
                changed+=self._dependents(r['id'],seen,bumped)
        return changed
    def save_manual_revision(self,task_id,stage,body,expected_epoch,title=''):
        if stage not in STAGES:raise ValueError('阶段不正确')
        with self.db.lock,self.db.conn:
            t=self._get(task_id,'task')
            if expected_epoch!=t['input_epoch']:raise ValueError('任务已发生变化，请刷新后保存')
            t['input_epoch']+=1;t['status']='paused';t['message']='手动稿件已保存，继续任务可补齐失效的下游内容'
            if t['kind'] in ('post','comment') and stage not in ('english','backtranslation'):
                t['target_stage']=stage;t['checkpoint_stage']=stage;t.pop('checkpoint_revision_id',None)
            t['updated_at']=now();self._put('task',t)
            return self.save_revision(task_id,stage,body,t['input_epoch'],title=title,
                source_revision_id=t['active'].get('english') if stage=='backtranslation' else None,
                **({'translation_rules':[x['text'] for x in self.rules(t['project_id'])]} if stage=='backtranslation' else {}),
                note_zh='老细，此版本由你手动保存。')
    def save_revision(self,task_id,stage,body,expected_epoch,**extra):
        if stage not in STAGES:raise ValueError('阶段不正确')
        with self.db.lock,self.db.conn:
            t=self._get(task_id,'task'); old=t['active'].get(stage); source=extra.get('source_revision_id');checkpoint=extra.get('checkpoint_revision_id')
            if checkpoint and (stage!='english' or self._get(checkpoint,'revision')['task_id']!=task_id or self._get(checkpoint,'revision')['stage'] in ('english','backtranslation')):raise ValueError('查看节点原稿不属于此任务')
            if source and self._get(source,'revision')['task_id']!=task_id: raise ValueError('释义原稿不属于此任务')
            invalid_parent=False
            if t.get('parent_revision_id'):
                pr=self._get(t['parent_revision_id'],'revision');pt=self._get(pr['task_id'],'task')
                invalid_parent=pr['stale'] or pt['active'].get(pr['stage'])!=pr['id']
            if source:
                sr=self._get(source,'revision')
                invalid_parent=invalid_parent or sr['stale'] or t['active'].get(sr['stage'])!=source
            if checkpoint:
                cr=self._get(checkpoint,'revision')
                invalid_parent=invalid_parent or cr['stale'] or t['active'].get(cr['stage'])!=checkpoint
            d={'id':uid(),'task_id':task_id,'stage':stage,'body':body,'title':'','note_zh':'','issues':[],
                'parent_id':old,'source_revision_id':None,'snapshot_id':None,'created_at':now(),'complete':True,
                'input_epoch':expected_epoch,'candidate':expected_epoch!=t['input_epoch'] or invalid_parent,'stale':False,**extra}
            self._put('revision',d)
            if not d['candidate'] and d['complete']:
                if old: self._dependents(old,set())
                # Changes to upstream stages invalidate downstream outputs.
                order=['theme','idea','chinese','english','backtranslation']
                if stage in order:
                    for st,rid in t['active'].items():
                        if st in order and order.index(st)>order.index(stage): self._stale(rid)
                t['active'][stage]=d['id']; t['updated_at']=now(); self._put('task',t)
            return d
    def approvals(self,rid):return self.list('approval',revision_id=rid)
    def record_approval(self,rid,reviewer,evidence):
        if reviewer not in ['user','supervisor','client'] or not evidence.strip():raise ValueError('请明确审核来源与通过依据')
        with self.db.lock,self.db.conn:
            r=self._get(rid,'revision')
            if r['candidate'] or r['stale'] or not r['complete']:raise ValueError('请先核对当前有效版本')
            self._put('approval',{'id':uid(),'revision_id':rid,'reviewer':reviewer,'evidence':evidence,'created_at':now()})
    def pass_simulation(self,rid):
        with self.db.lock,self.db.conn:
            revision=self._get(rid,'revision');task=self._get(revision['task_id'],'task')
            if task['active'].get(revision['stage'])!=rid or revision['candidate'] or revision['stale']:
                raise ValueError('请先打开当前有效稿件')
            if task.get('abandoned') or task.get('retired'):
                raise ValueError('已移除的稿件不能通过')
            if any(j['status'] in ('queued','running') for j in self.list('job',task_id=task['id'])):
                raise ValueError('稿件正在生成，请等待结束后通过')
            if task['kind'] in ('post','comment') and revision['stage']!='english':
                raise ValueError('帖文与评论请先直达英文成品；中途节点通过不等于最终通过')
            if not revision['complete'] or any(i.get('severity','error')=='error' for i in revision.get('issues',[])):
                raise ValueError('请先处理当前稿件的问题')
            if revision['stage']!=task['target_stage']:
                raise ValueError('只能通过本任务的目标稿')
            if task['target_stage']=='english':
                translation=task['active'].get('backtranslation')
                tr=self._get(translation,'revision') if translation else {}
                if not tr or tr.get('source_revision_id')!=rid or tr['stale'] or tr['candidate'] or not tr['complete']:
                    raise ValueError('请先完成此英文稿对应的中文回译')
            if not any(a['reviewer']=='user' and a.get('simulation_pass') for a in self.approvals(rid)):
                self._put('approval',{'id':uid(),'revision_id':rid,'reviewer':'user',
                                      'evidence':'模拟稿通过','simulation_pass':True,'created_at':now()})
            return {'revision_id':rid,'passed':True}

    def continue_to_english(self,task_id,revision_id):
        """Approve one exact checkpoint and advance without overwriting its draft."""
        with self.db.lock,self.db.conn:
            task=self._get(task_id,'task');revision=self._get(revision_id,'revision')
            if task['kind'] not in ('post','comment') or revision['task_id']!=task_id:
                raise ValueError('仅帖文或评论可从自己的查看节点直达英文成品')
            if task.get('abandoned') or task.get('retired'):raise ValueError('已移除的稿件不能继续')
            if task['kind']=='post' and not task.get('post_group_id'):
                raise ValueError('请在社群候选稿上继续，原主帖稿件作为历史保留')
            if task['target_stage']=='english' and task.get('checkpoint_revision_id')==revision_id:
                return {'changed':False,'task':task}
            if task['target_stage']=='english' or revision['stage']!=task['target_stage']:
                raise ValueError('请打开当前查看节点的稿件')
            if any(j['status'] in ('queued','running') for j in self.list('job',task_id=task_id)):
                raise ValueError('当前稿件正在生成，请等待结束后继续')
            if task['active'].get(revision['stage'])!=revision_id or revision['stale'] or revision['candidate'] or not revision['complete']:
                raise ValueError('查看节点版本已变化，请查看最新稿件')
            if any(o['status']=='pending' for o in self.list('opinion',task_id=task_id)) or any(i.get('severity','error')=='error' for i in revision.get('issues',[])):
                raise ValueError('请先处理查看节点的新意见或错误')
            self._put('approval',{'id':uid(),'revision_id':revision_id,'reviewer':'user',
                'evidence':'查看节点通过，继续生成英文成品','checkpoint_pass':True,'created_at':now()})
            task.setdefault('checkpoint_history',[]).append({'revision_id':revision_id,'stage':revision['stage'],'continued_at':now()})
            task.update(checkpoint_stage=revision['stage'],checkpoint_revision_id=revision_id,
                        target_stage='english',input_epoch=task['input_epoch']+1,status='paused',
                        message='查看节点已通过，准备生成英文成品及对应回译',updated_at=now())
            for stage in ('english','backtranslation'):
                if task['active'].get(stage):self._stale(task['active'][stage])
            self._put('task',task)
            return {'changed':True,'task':task}

    def abandon_variant(self,task_id):
        with self.db.lock,self.db.conn:
            task=self._get(task_id,'task');group_id=task.get('post_group_id')
            if not group_id or task.get('abandoned') or task.get('retired'):
                raise ValueError('只能移除当前多稿方案中的候选稿')
            if task['status'] in ('queued','running'):
                raise ValueError('这篇稿件正在生成，请等待本轮结束后移除')
            siblings=[t for t in self.list('task',post_group_id=group_id)
                      if not t.get('abandoned') and not t.get('retired')]
            if len(siblings)<2:raise ValueError('不能移除最后一篇稿件')
            task['abandoned']=True;task['abandoned_at']=now();task['updated_at']=now()
            self._put('task',task)
            group=self._get(group_id,'task')
            choices=group.get('chosen_variants',{})
            for key,choice in list(choices.items()):
                if choice.get('task_id')==task_id:choices.pop(key)
            group['chosen_variants']=choices;self._put('task',group)
            return task
    def restore_variant(self,task_id):
        with self.db.lock,self.db.conn:
            task=self._get(task_id,'task')
            if not task.get('post_group_id') or not task.get('abandoned'):
                raise ValueError('此稿件未处于移除状态')
            group=self._get(task['post_group_id'],'task')
            from waypoint.communities import checked_plan
            plan=checked_plan(group.get('community_plan'))
            profile=next((x for x in plan if x['name'].lower()==task['community']['name'].lower()),None)
            if not profile or task.get('group_epoch')!=group['input_epoch'] or task['variant_number']>profile['variants']:
                raise ValueError('社群方案已变化，请先调整方案再恢复稿件')
            task['abandoned']=False;task.pop('abandoned_at',None);task['updated_at']=now()
            self._put('task',task)
            return task
    def settings(self):
        defaults={'id':'settings','api_enabled':False,'provider':'codex','model_roles':{},'api_model':'','api_input_rate':None,
            'api_output_rate':None,'price_date':'','stop_microusd':18_000_000,'max_output_tokens':4000,
            'api_default_profile_id':'','role_routes':{},'update_manifest_url':'',
            'usage_mode':'','switch_policy':'manual','api_default_model':'','api_role_models':{},
            'usage_configs':[],'active_usage_config_id':'','auto_default_config_id':'','fallback_usage_config_id':'',
            'auto_used_threshold':100,'role_efforts':{}}
        try:return defaults|self.get('settings','settings')
        except ValueError:return defaults
    def save_settings(self,patch):
        s=self.settings(); allowed=set(s)-{'id'}
        if set(patch)-allowed:raise ValueError('未知设置')
        s.update(patch)
        from waypoint.routing import validate_efforts
        validate_efforts(s['role_efforts'])
        if 'update_manifest_url' in patch:
            from waypoint.updates import validate_update_url
            if s['update_manifest_url']:s['update_manifest_url']=validate_update_url(s['update_manifest_url'])
            elif not isinstance(s['update_manifest_url'],str):raise ValueError('更新源地址不正确')
        from waypoint.api_profiles import validate_routes
        if 'role_routes' in patch:validate_routes(self,s['role_routes'])
        if 'api_role_models' in patch:
            validate_routes(self,s['api_role_models'])
            if any(x['provider']!='api' for x in s['api_role_models'].values()):raise ValueError('API 模型分工不正确')
        if s['usage_mode'] not in ('','codex','api'):raise ValueError('使用模式不正确')
        if s['switch_policy'] not in ('manual','auto'):raise ValueError('切换设置不正确')
        if type(s['auto_used_threshold']) not in (int,float) or not 1<=s['auto_used_threshold']<=100:raise ValueError('自动切换阈值须为已用百分比 1–100')
        from waypoint.usage import validate_configs
        validate_configs(self,s,validate_models='usage_configs' in patch)
        if 'api_default_profile_id' in patch and s['api_default_profile_id']:self.get(s['api_default_profile_id'],'api_profile')
        if ('api_default_model' in patch or 'api_default_profile_id' in patch) and s['api_default_model']:
            p=self.get(s['api_default_profile_id'],'api_profile')
            if s['api_default_model'] not in {m['id'] for m in p['models']}:raise ValueError('请从此服务商实际账户列表选择 API 模型')
        if s['provider'] not in ['codex','api']:raise ValueError('接入方式不正确')
        if type(s['api_enabled']) is not bool:raise ValueError('API 开关不正确')
        if not isinstance(s['stop_microusd'],int) or not 0<=s['stop_microusd']<=18_000_000:raise ValueError('停止线最多十八美元')
        if not isinstance(s['max_output_tokens'],int) or not 100<=s['max_output_tokens']<=16000:raise ValueError('输出上限不正确')
        return self.put('settings',s)
    def rules(self,project_id):
        rows=[x for x in self.list('rule') if x['project_id'] in (None,project_id)]
        latest={}
        for x in rows: latest[x['project_id']]=x
        return [{'id':'builtin-v1','project_id':None,'text':DEFAULT_RULES},*latest.values()]
    def add_rule(self,project_id,text,append=False):
        if not text.strip():raise ValueError('规则不能为空')
        with self.db.lock,self.db.conn:
            if project_id:self.active_project(project_id)
            if append:
                previous=self.list('rule',project_id=project_id)
                if previous:text=previous[-1]['text']+'\n'+text
            d={'id':uid(),'project_id':project_id,'text':text,'created_at':now()}
            self._put('rule',d)
            for t in self.list('task'):
                if project_id is None or t['project_id']==project_id:
                    self.set_task_state(t['id'],input_epoch=t['input_epoch']+1,message='规则已更新，请重新核对')
                    for rid in t['active'].values():self._stale(rid)
            return d
