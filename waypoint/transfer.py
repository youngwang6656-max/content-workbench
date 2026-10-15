"""Validated, transactional single-project transfer. Never imports account or billing state."""
import copy,hashlib,io,json,time,zipfile,threading
from collections import Counter
from pathlib import Path
from waypoint.contracts import uid,now,TaskSpec,Opinion,STAGES
from waypoint.handoff import handoff_records,unique_json

MAX_UPLOAD=100_000_000
MAX_EXPANDED=200_000_000
KINDS={'project','task','revision','opinion','approval','material','rule','snapshot','history','transfer','archived_job'}
ID_FIELDS={'id','project_id','task_id','revision_id','base_revision_id','parent_id','parent_revision_id','source_revision_id','snapshot_id','post_group_id','comment_batch_id','origin_opinion_id','comment_source_id','original_material_id','material_id','checkpoint_revision_id','quick_comment_source_revision_id'}


def validate(records,files):
    if not isinstance(records,list) or not 1<=len(records)<=100000:raise ValueError('项目记录数量不正确')
    index={};groups={k:[] for k in KINDS}
    for item in records:
        if not isinstance(item,dict) or set(item)!= {'kind','data'} or item['kind'] not in KINDS:raise ValueError('项目包包含不支持的记录类型')
        d=item['data'];kind=item['kind']
        if not isinstance(d,dict) or not isinstance(d.get('id'),str) or not d['id'] or d['id'] in index:raise ValueError('记录 ID 缺失或重复')
        index[d['id']]=(kind,d);groups[kind].append(d)
    if len(groups['project'])!=1:raise ValueError('每个迁移包只能包含一个项目')
    project=groups['project'][0];pid=project['id']
    if not isinstance(project.get('name'),str) or not project['name'].strip():raise ValueError('项目名称不能为空')
    def ref(value,kind,optional=False):
        if optional and value is None:return None
        if not isinstance(value,str) or value not in index or index[value][0]!=kind:raise ValueError('项目包存在无效或跨项目引用')
        return index[value][1]
    try:
        for kind,rows in groups.items():
            for d in rows:
                if kind in {'material','rule','history','transfer','snapshot'} and d['project_id']!=pid:raise ValueError('项目包混入其他项目')
                if kind in {'opinion','revision','archived_job','snapshot'}:ref(d['task_id'],'task')
                if kind=='task':
                    spec=TaskSpec(**{k:d[k] for k in TaskSpec.model_fields})
                    if spec.project_id!=pid:raise ValueError('任务不属于此项目')
                    if d.get('post_group_id'):
                        group=ref(d['post_group_id'],'task')
                        if group['id']==d['id'] or group.get('post_group_id') or group['kind']!='post' or spec.kind!='post':raise ValueError('社群候选关联无效')
                        from waypoint.communities import community_name
                        community_name(d['community']['name'])
                        if type(d['variant_number']) is not int or not 1<=d['variant_number']<=3:raise ValueError('候选序号无效')
                    if d['status'] not in {'queued','running','paused','completed','interrupted','failed'}:raise ValueError('任务状态无效')
                    if not isinstance(d['active'],dict) or not isinstance(d['raw_history'],list) or not isinstance(d['input_epoch'],int):raise ValueError('任务结构无效')
                    for stage,rid in d['active'].items():
                        rev=ref(rid,'revision')
                        if stage not in STAGES or rev['task_id']!=d['id'] or rev['stage']!=stage:raise ValueError('当前版本引用无效')
                    for sid in spec.source_ids:ref(sid,'material')
                    if d.get('checkpoint_revision_id'):
                        checkpoint=ref(d['checkpoint_revision_id'],'revision')
                        if checkpoint['task_id']!=d['id'] or checkpoint['stage'] in ('english','backtranslation'):raise ValueError('查看节点引用无效')
                    if d.get('comment_source_id'):
                        source=ref(d['comment_source_id'],'material')
                        if source['project_id']!=pid or source['id'] not in spec.source_ids or not source.get('comment_source'):raise ValueError('评论原帖引用无效')
                    for sid in d.get('comment_source_history',[]):ref(sid,'material')
                    for choice in d.get('chosen_variants',{}).values():
                        child=ref(choice['task_id'],'task');revision=ref(choice['revision_id'],'revision')
                        if child.get('post_group_id')!=d['id'] or revision['task_id']!=child['id']:raise ValueError('选用候选引用无效')
                    parent=ref(spec.parent_revision_id,'revision',True)
                    if parent and spec.kind=='comment' and spec.comment_kind=='own' and ref(parent['task_id'],'task')['kind']!='post':raise ValueError('铺评必须引用帖文')
                elif kind=='revision':
                    if d['stage'] not in STAGES or not isinstance(d['body'],str) or not isinstance(d['title'],str):raise ValueError('稿件格式无效')
                    for field in ('candidate','stale','complete'):
                        if type(d[field]) is not bool:raise ValueError('稿件状态无效')
                    for field in ('parent_id','source_revision_id','checkpoint_revision_id'):
                        other=ref(d.get(field),'revision',True)
                        if other and other['task_id']!=d['task_id']:raise ValueError('稿件引用跨任务')
                        if other and field=='source_revision_id' and (d['stage']!='backtranslation' or other['stage']!='english'):raise ValueError('回译引用无效')
                        if other and field=='checkpoint_revision_id' and (d['stage']!='english' or other['stage'] in ('english','backtranslation')):raise ValueError('查看节点引用无效')
                    snap=ref(d.get('snapshot_id'),'snapshot',True)
                    if snap and snap['task_id']!=d['task_id']:raise ValueError('快照引用跨任务')
                elif kind=='opinion':
                    Opinion(**{k:d[k] for k in Opinion.model_fields})
                    base=ref(d.get('base_revision_id'),'revision',True)
                    if base and base['task_id']!=d['task_id']:raise ValueError('意见引用跨任务')
                    if d['status'] not in {'pending','processed','partial','conflict','no_change'}:raise ValueError('意见状态无效')
                elif kind=='approval':
                    ref(d['revision_id'],'revision')
                    if d['reviewer'] not in {'user','supervisor','client'} or not isinstance(d['evidence'],str) or not d['evidence'].strip():raise ValueError('审核依据缺失')
                elif kind=='material':
                    if not isinstance(d['text'],str) or not isinstance(d['name'],str) or d['kind'] not in {'fact','strategy','sample','thread','attachment'}:raise ValueError('资料格式无效')
                    if type(d['archived']) is not bool or d['trust'] not in {'unverified','user_confirmed','simulation_selected'}:raise ValueError('资料状态无效')
                    if d.get('path') and d['path'] not in files:raise ValueError('附件缺失或引用无效')
                elif kind=='rule' and not isinstance(d['text'],str):raise ValueError('规则格式无效')
                elif kind=='history':
                    if not isinstance(d['records'],list):raise ValueError('历史档案格式无效')
                    from waypoint.handoff import HistoryInfo
                    for row in d['records']:HistoryInfo.model_validate(row)
                elif kind=='transfer':
                    if d.get('archive_path') and d['archive_path'] not in files:raise ValueError('原始迁移档案缺失')
                    validate_coverage(d.get('coverage',{}))
        for t in groups['task']:
            seen={t['id']};p=t.get('parent_revision_id')
            while p:
                parent=ref(ref(p,'revision')['task_id'],'task')
                if parent['id'] in seen:raise ValueError('父稿引用构成循环')
                seen.add(parent['id']);p=parent.get('parent_revision_id')
        for r in groups['revision']:
            seen={r['id']};p=r.get('parent_id')
            while p:
                if p in seen:raise ValueError('稿件版本引用构成循环')
                seen.add(p);p=ref(p,'revision').get('parent_id')
    except (KeyError,TypeError) as exc:raise ValueError('项目记录缺少必要字段或格式不正确') from exc
    return project,groups


def validate_coverage(coverage):
    if not isinstance(coverage,dict):raise ValueError('来源范围格式无效')
    for key in ('sources','missing','uncertain'):
        values=coverage.get(key,[])
        if not isinstance(values,list) or any(not isinstance(x,str) for x in values):raise ValueError('来源范围字段必须是文字列表')


def remap(value,ids,paths,key=''):
    if isinstance(value,dict):
        if key=='active':return {k:ids.get(v,v) for k,v in value.items()}
        return {k:remap(v,ids,paths,k) for k,v in value.items()}
    if isinstance(value,list):
        if key in {'source_ids','citations','comment_source_history'}:return [ids.get(x,x) for x in value]
        return [remap(x,ids,paths,key) for x in value]
    if isinstance(value,str):
        if key in ID_FIELDS:return ids.get(value,value)
        if key in {'path','archive_path'}:return paths.get(value,value)
    return value


class ProjectTransfer:
    def __init__(self,repo):
        self.repo=repo;self.previews={};self.raw_previews={};self.raw_lock=threading.RLock();self.preview_lock=threading.RLock()
    def inspect_raw(self,filename,data):
        return self.inspect_raw_files([(filename,data)])
    def inspect_raw_files(self,files):
        from waypoint.chatgpt_export import read_export_files
        rows=read_export_files(files);token=uid()
        with self.raw_lock:
            self.raw_previews={k:v for k,v in self.raw_previews.items() if time.monotonic()-v['time']<1800}
            if len(self.raw_previews)>=2:self.raw_previews.pop(next(iter(self.raw_previews)))
            self.raw_previews[token]={'rows':rows,'time':time.monotonic()}
        return {'token':token,'conversations':[{k:v for k,v in row.items() if k not in ('history','raw')} for row in rows],
                'notice':'请选择同一品牌的对话。只保存所选原文和分支，不自动生成摘要或调用模型。'}
    def preview_raw(self,token,conversation_ids,name=''):
        from waypoint.chatgpt_export import raw_records
        if not isinstance(token,str):raise ValueError('原始导出检查标识无效')
        if not isinstance(conversation_ids,list) or not conversation_ids or any(not isinstance(k,str) for k in conversation_ids) or len(set(conversation_ids))!=len(conversation_ids):
            raise ValueError('请勾选需要迁入的对话，不可重复选择')
        if not isinstance(name,str) or len(name)>200:raise ValueError('项目名称最长二百字')
        with self.raw_lock:
            item=self.raw_previews.get(token)
            if not item or time.monotonic()-item['time']>1800:raise ValueError('原始导出检查已失效，请重新上传')
            keys=set(conversation_ids);selected=[c for c in item['rows'] if c['key'] in keys]
            if len(selected)!=len(keys):raise ValueError('所选对话不属于本次导出检查')
            records,coverage,audit=raw_records(selected,name.strip() or selected[0]['title'][:200])
            data=json.dumps([c['raw'] for c in sorted(selected,key=lambda c:c['id'])],ensure_ascii=False,sort_keys=True,allow_nan=False).encode()
        # Check portability before writing any business record; do not accept an archive
        # that immediately exceeds the existing native export/restore limits.
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('part-1.json',data)
        portable=list(records);archive_name=uid()+'.zip';portable_files={'attachments/'+archive_name:archive.getvalue()}
        portable.append({'kind':'transfer','data':{'id':uid(),'project_id':records[0]['data']['id'],'source':'chatgpt_raw',
            'source_hash':hashlib.sha256(data).hexdigest(),'coverage':coverage,'created_at':now(),'audit':audit,'archive_path':archive_name}})
        globals_=[r['text'] for r in self.repo.rules(None) if r['id']!='builtin-v1']
        if globals_:portable.append({'kind':'rule','data':{'id':uid(),'project_id':records[0]['data']['id'],'text':'\n\n'.join(globals_),
                                                         'created_at':now(),'imported_global_snapshot':True}})
        for material in self.repo.list('material',project_id=None):
            if material.get('archived') or material['kind'] not in ('fact','strategy'):continue
            portable.append({'kind':'material','data':dict(material,project_id=records[0]['data']['id'],imported_global_snapshot=True)})
            filename=material.get('path')
            if filename:
                if Path(filename).name!=filename or '\\' in filename:raise ValueError('全局资料附件路径异常，无法完整导出')
                path=self.repo.db.root/'attachments'/filename
                if not path.is_file() or path.is_symlink():raise ValueError('全局资料附件缺失，无法完整导出')
                if path.stat().st_size+sum(map(len,portable_files.values()))>MAX_EXPANDED:raise ValueError('原文及全局附件超出恢复上限，请分批迁移或归档过量全局资料')
                portable_files['attachments/'+filename]=path.read_bytes()
        package=json.dumps({'records':portable,'coverage':coverage},ensure_ascii=False).encode()
        if len(package)+sum(map(len,portable_files.values()))+4096>MAX_EXPANDED:raise ValueError('所选原文及全局资料超过项目可恢复上限，请分批勾选对话或归档过量全局资料')
        bundle=io.BytesIO()
        with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('project.json',package)
            for filename,contents in portable_files.items():z.writestr(filename,contents)
        if len(bundle.getvalue())+4096>MAX_UPLOAD:raise ValueError('所选原文及全局资料超过项目导出上限，请分批勾选对话或归档过量全局资料')
        p=self._stage_preview(records,{},coverage,[],[('selected-conversations.json',data)],'chatgpt_raw',audit=audit)
        p.update(audit=audit,history_count=audit['history_count'],notice='完整保留所选文件中的原文与各分支；未调用模型。缺失附件和未导出内容不算已迁入。')
        return p
    def preview(self,files):
        if not files or len(files)>100 or sum(len(data) for _,data in files)>MAX_UPLOAD:raise ValueError('迁移文件合计上限为一百 MB，最多一百卷')
        attachments={};rules=[]
        if len(files)==1 and zipfile.is_zipfile(io.BytesIO(files[0][1])):
            try:
                with zipfile.ZipFile(io.BytesIO(files[0][1])) as z:
                    names=z.namelist()
                    if len(names)!=len(set(names)) or len(names)>10000 or sum(i.file_size for i in z.infolist())>MAX_EXPANDED:raise ValueError('项目包展开过大或存在重复文件')
                    if any(n not in {'project.json','manifest.json'} and (not n.startswith('attachments/') or len(Path(n).parts)!=2 or '..' in Path(n).parts or '\\' in n or ':' in n) for n in names):raise ValueError('项目包包含非法路径')
                    manifest=unique_json(z.read('manifest.json').decode('utf-8'))
                    if manifest['format']!='waypoint-project' or manifest['version']!=1 or set(manifest['files'])!=set(names)-{'manifest.json'}:raise ValueError('项目包版本或清单无效')
                    for n,h in manifest['files'].items():
                        data=z.read(n)
                        if hashlib.sha256(data).hexdigest()!=h:raise ValueError('项目包校验失败，文件可能损坏')
                        if n.startswith('attachments/'):attachments[n.split('/')[1]]=data
                    package=unique_json(z.read('project.json').decode('utf-8'))
                    records=package['records'];coverage=package.get('coverage',{});source='waypoint'
            except (KeyError,UnicodeError,zipfile.BadZipFile,RuntimeError,json.JSONDecodeError) as exc:raise ValueError('不是有效的 waypoint 单项目导出包；全库备份请从设置中恢复') from exc
        else:
            records,coverage,rules=handoff_records(files);source='chatgpt'
        return self._stage_preview(records,attachments,coverage,rules,files,source)
    def _stage_preview(self,records,attachments,coverage,rules,files,source,audit=None):
        project,groups=validate(records,attachments)
        if not rules:rules=[r['text'] for r in groups['rule']]
        # Handoff staging generates internal IDs, so use the actual normalized source documents for dedupe.
        source_hash=hashlib.sha256(b'\0'.join(sorted(data for _,data in files))).hexdigest()
        if any(x.get('source_hash')==source_hash for x in self.repo.list('transfer')):raise ValueError('这个迁移包已经导入，请打开现有项目')
        validate_coverage(coverage)
        missing=coverage.get('missing',[])
        if not isinstance(missing,list) or any(not isinstance(x,str) for x in missing):raise ValueError('缺失清单格式无效')
        missing=list(missing)+[m.get('original_filename') or m['name'] for m in groups['material'] if m.get('missing_attachment')]
        token=uid()
        with self.preview_lock:
            self.previews={k:v for k,v in self.previews.items() if time.monotonic()-v['time']<1800}
            if len(self.previews)>=2:self.previews.pop(next(iter(self.previews)))
            self.previews[token]={'records':records,'attachments':attachments,'source':source,'source_hash':source_hash,
                'coverage':coverage,'files':files if source in ('chatgpt','chatgpt_raw') else [],'time':time.monotonic(),'rules':rules,
                'audit':audit}
        return {'token':token,'name':project['name'],'source':source,'counts':dict(Counter(x['kind'] for x in records)),
            'attachment_count':len(attachments),'missing':list(dict.fromkeys(missing)),'coverage':coverage,'rules':rules,
            'tasks':[{'name':t['name'] or t['raw_input'][:60],'kind':t['kind']} for t in groups['task']],
            'notice':'GPT 交接受可见范围限制；历史审核说明不自动记为审核通过。' if source=='chatgpt' else '保留原始项目档案；所有运行停止，账户与费用设置不变。'}
    def commit(self,token,name='',accept_rules=False):
        with self.preview_lock:return self._commit(token,name,accept_rules)
    def _commit(self,token,name='',accept_rules=False):
        item=self.previews.get(token)
        if not item or time.monotonic()-item['time']>1800:raise ValueError('预览已失效，请重新上传校验')
        if item['rules'] and accept_rules is not True:raise ValueError('请先确认迁入项目规则')
        if not isinstance(name,str) or len(name)>200:raise ValueError('项目名称最长二百字')
        records=copy.deepcopy(item['records']);ids={x['data']['id']:uid() for x in records}
        paths={n:uid()+Path(n).suffix for n in item['attachments']};written=[]
        with self.repo.db.lock:
            if any(x.get('source_hash')==item['source_hash'] for x in self.repo.list('transfer')):raise ValueError('这个迁移包已经导入')
            try:
                with self.repo.db.conn:
                    for filename,data in item['attachments'].items():
                        dest=self.repo.db.root/'attachments'/paths[filename];written.append(dest);dest.write_bytes(data)
                    pid=None
                    for row in records:
                        d=remap(row['data'],ids,paths);kind=row['kind']
                        if kind=='archived_job':d['archived']=True
                        if kind=='project':
                            pid=d['id'];d['name']=name.strip() or d['name'];d['imported_at']=now()
                            d.pop('merged_into',None);d['pinned']=False
                            d['sort_order']=max((p.get('sort_order',i) for i,p in enumerate(self.repo.projects())),default=-1)+1
                        elif kind=='task':
                            d['job_id']=None
                            if d.get('attention'):d['attention']['page']='materials'
                            if d['status'] in {'running','queued'}:d['status']='paused';d['message']='迁入的任务已暂停，请检查后继续'
                        self.repo._put(kind,d)
                    receipt={'id':uid(),'project_id':pid,'source':item['source'],'source_hash':item['source_hash'],
                        'coverage':item['coverage'],'created_at':now()}
                    if item.get('audit'):receipt['audit']=item['audit']
                    if item['files']:
                        archive=uid()+'.zip';dest=self.repo.db.root/'attachments'/archive;written.append(dest)
                        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
                            for i,(_,data) in enumerate(item['files']):z.writestr(f'part-{i+1}.json',data)
                        receipt['archive_path']=archive
                    self.repo._put('transfer',receipt)
            except Exception:
                for p in written:p.unlink(missing_ok=True)
                raise
        del self.previews[token]
        return {'project_id':pid,'counts':dict(Counter(x['kind'] for x in records))}
    def export(self,project_id):
        with self.repo.db.lock:
            project=self.repo.active_project(project_id);records=[{'kind':'project','data':project}]
            tasks=self.repo.list('task',project_id=project_id);tids={t['id'] for t in tasks}
            revs=[r for r in self.repo.list('revision') if r['task_id'] in tids];rids={r['id'] for r in revs}
            rows={'task':tasks,'revision':revs,'approval':[a for a in self.repo.list('approval') if a['revision_id'] in rids]}
            for k in ['opinion','snapshot','archived_job']:rows[k]=[x for x in self.repo.list(k) if x['task_id'] in tids]
            for k in ['material','rule','history','transfer']:rows[k]=self.repo.list(k,project_id=project_id)
            referenced={sid for t in tasks for sid in t['source_ids']}
            referenced.update(m['id'] for s in rows['snapshot'] for m in s.get('materials',[]))
            # Shared evidence travels as a brand-local snapshot, never replaces the
            # recipient's global library, and keeps task/file references resolvable.
            for material in self.repo.list('material',project_id=None):
                if material['id'] in referenced or (not material['archived'] and material['kind'] in ('fact','strategy')):
                    rows['material'].append(dict(material,project_id=project_id,imported_global_snapshot=True))
            for job in self.repo.list('job'):
                if job['task_id'] in tids:rows['archived_job'].append({k:v for k,v in job.items() if k not in {'thread_id','turn_id'}})
            globals_=[r for r in self.repo.rules(project_id) if r['project_id'] is None and r['id']!='builtin-v1']
            if globals_:
                rules=[r['text'] for r in self.repo.rules(project_id) if r['id']!='builtin-v1']
                rows['rule'].append({'id':uid(),'project_id':project_id,'text':'\n\n'.join(rules),'created_at':now(),'imported_global_snapshot':True})
            for kind,items in rows.items():records.extend({'kind':kind,'data':d} for d in items)
            names={m['path'] for m in rows['material'] if m.get('path')}|{x['archive_path'] for x in rows['transfer'] if x.get('archive_path')}
            files={}
            for name in names:
                if Path(name).name!=name or '\\' in name:raise ValueError('附件路径异常')
                path=self.repo.db.root/'attachments'/name
                if not path.is_file() or path.is_symlink():raise ValueError('附件缺失，无法完整导出：'+name)
                files['attachments/'+name]=path.read_bytes()
            files['project.json']=json.dumps({'records':records,'coverage':project.get('coverage',{})},ensure_ascii=False).encode()
            if sum(map(len,files.values()))>MAX_EXPANDED:raise ValueError('项目过大，超出当前二百 MB 导出上限')
            manifest={'format':'waypoint-project','version':1,'created_at':now(),'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json',json.dumps(manifest))
                for n,b in files.items():z.writestr(n,b)
            result=out.getvalue()
            if len(result)>MAX_UPLOAD:raise ValueError('导出包超过一百 MB，无法通过当前导入入口，请拆分项目资料')
            return result
    def history(self,project_id,query='',offset=0):
        self.repo.get(project_id,'project')
        records=[row for h in self.repo.list('history',project_id=project_id) for row in h['records']]
        if query:records=[r for r in records if query.casefold() in r['text'].casefold()]
        return {'records':records[offset:offset+100],'total':len(records),'offset':offset,
            'receipts':self.repo.list('transfer',project_id=project_id)}
