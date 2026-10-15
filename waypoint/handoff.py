"""The human-readable ChatGPT handoff format; no model calls during import."""
import json,re,tempfile
from typing import Literal
from pydantic import Field,ValidationError
from waypoint.contracts import Strict,TaskSpec,Opinion,STAGES,uid,now
from waypoint.repository import Repository
from waypoint.materials import Materials

class ProjectInfo(Strict):
    name:str=Field(min_length=1,max_length=200)
    description:str=Field(default='',max_length=20000)
    summary:str=Field(default='',max_length=40000)
    rules:list[str]=Field(default_factory=list,max_length=200)
    preference_candidates:list[str]=Field(default_factory=list,max_length=200)
class Coverage(Strict):
    sources:list[str]=Field(default_factory=list,max_length=1000)
    missing:list[str]=Field(default_factory=list,max_length=1000)
    uncertain:list[str]=Field(default_factory=list,max_length=1000)
class MaterialInfo(Strict):
    key:str=Field(min_length=1,max_length=120)
    name:str=Field(min_length=1,max_length=200)
    text:str=Field(default='',max_length=200000)
    kind:Literal['fact','strategy','sample','thread','attachment']='fact'
    url:str=''
    filename:str=''
    missing_attachment:bool=False
class VersionInfo(Strict):
    key:str=Field(min_length=1,max_length=120)
    stage:Literal['theme','idea','chinese','english','backtranslation','cb']
    title:str=Field(default='',max_length=1000)
    body:str=Field(max_length=100000)
    current:bool=False
    source_version:str|None=None
    created_at:str=''
    approval_notes:list[str]=Field(default_factory=list)
class OpinionInfo(Strict):
    stage:Literal['theme','idea','chinese','english','backtranslation','cb']='english'
    source:Literal['user','supervisor','client']='user'
    raw_text:str=Field(min_length=1,max_length=20000)
    base_version:str|None=None
    status:Literal['pending','processed','partial','conflict','no_change']='pending'
    selection:str=''
    field:Literal['body','title']='body'
    created_at:str=''
class TaskInfo(Strict):
    key:str=Field(min_length=1,max_length=120)
    name:str=Field(default='',max_length=200)
    kind:Literal['post','comment','cb']='post'
    comment_kind:Literal['own','natural']='natural'
    raw_input:str=Field(default='',max_length=100000)
    raw_history:list[str]=Field(default_factory=list)
    input_stage:Literal['theme','idea','chinese','english','cb']='idea'
    target_stage:Literal['theme','idea','chinese','english','cb']='english'
    parent_version:str|None=None
    material_keys:list[str]=Field(default_factory=list,max_length=30)
    versions:list[VersionInfo]=Field(default_factory=list,max_length=1000)
    opinions:list[OpinionInfo]=Field(default_factory=list,max_length=1000)
    publication:dict[str,str]=Field(default_factory=dict)
class HistoryInfo(Strict):
    role:Literal['user','assistant','supervisor','client','unknown']='unknown'
    text:str=Field(max_length=200000)
    record_type:Literal['original','summary']='original'
    source:str=''
    created_at:str=''
class Handoff(Strict):
    format:Literal['waypoint-handoff']
    version:Literal[1]
    project_key:str=Field(min_length=1,max_length=200)
    part:int=Field(default=1,ge=1,le=100)
    total_parts:int=Field(default=1,ge=1,le=100)
    project:ProjectInfo
    coverage:Coverage=Field(default_factory=Coverage)
    materials:list[MaterialInfo]=Field(default_factory=list,max_length=2000)
    tasks:list[TaskInfo]=Field(default_factory=list,max_length=2000)
    history:list[HistoryInfo]=Field(default_factory=list,max_length=10000)


def unique_json(text):
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj:raise ValueError('JSON 字段重复：'+key)
            obj[key]=value
        return obj
    return json.loads(text,object_pairs_hook=pairs)


def read_parts(files):
    parts=[]
    for name,data in files:
        try:
            text=data.decode('utf-8-sig').strip()
            blocks=re.findall(r'```(?:json)?\s*\n(.*?)\n```',text,re.S)
            for raw in (blocks or [text]):parts.append(Handoff.model_validate(unique_json(raw)))
        except (UnicodeError,ValidationError,json.JSONDecodeError) as exc:
            if isinstance(exc,ValidationError):
                first=exc.errors()[0];where='.'.join(map(str,first['loc']))
                raise ValueError(f'{name} 的字段 {where} 不符合迁移格式，请使用固定提示词重新导出') from exc
            raise ValueError(f'{name} 不是完整的 UTF-8 JSON；请检查是否截断') from exc
    if not parts:raise ValueError('请上传或粘贴迁移内容')
    first=parts[0]
    if any(p.project_key!=first.project_key or p.total_parts!=first.total_parts or p.project!=first.project for p in parts):
        raise ValueError('分卷的项目标识、项目说明或总卷数不一致')
    if len(parts)!=first.total_parts or {p.part for p in parts}!=set(range(1,first.total_parts+1)):
        raise ValueError('分卷不齐或重复，请一次提供全部分卷')
    parts.sort(key=lambda p:p.part)
    materials=[m for p in parts for m in p.materials];tasks=[t for p in parts for t in p.tasks]
    keys=[m.key for m in materials]+[t.key for t in tasks]+[v.key for t in tasks for v in t.versions]
    if len(keys)!=len(set(keys)):raise ValueError('资料、任务或稿件 key 重复；每个对象应有唯一 key')
    coverage={k:list(dict.fromkeys(x for p in parts for x in getattr(p.coverage,k))) for k in Coverage.model_fields}
    history=[h.model_dump() for p in parts for h in p.history]
    return first.project,materials,tasks,coverage,history


def handoff_records(files):
    project,materials,tasks,coverage,history=read_parts(files)
    with tempfile.TemporaryDirectory(prefix='waypoint_handoff_') as tmp:
        r=Repository(tmp)
        try:
            pid=r.create_project(project.name,project.description)
            p=r.get(pid,'project');p['handoff_summary']=project.summary;p['coverage']=coverage;r.put('project',p)
            if project.rules:r.add_rule(pid,'\n\n'.join(project.rules))
            if project.summary:Materials(r).add_text(pid,'项目交接摘要',project.summary,kind='strategy',import_summary=True)
            if project.preference_candidates:Materials(r).add_text(pid,'待采纳的客户偏好','\n'.join(project.preference_candidates),kind='sample',preference_candidates=True)
            mids={m.key:Materials(r).add_text(pid,m.name,m.text,kind=m.kind,url=m.url,
                 missing_attachment=m.missing_attachment,original_filename=m.filename,extraction='needs_text' if m.missing_attachment else 'text')['id'] for m in materials}
            tids={};vids={};owners={}
            def ref(mapping,key):
                if key is None:return None
                if key not in mapping:raise ValueError('迁移包中存在无法对应的引用：'+str(key))
                return mapping[key]
            for t in tasks:
                tid=r.create_task(TaskSpec(project_id=pid,kind=t.kind,name=t.name,raw_input=t.raw_input,
                    input_stage=t.input_stage,target_stage=t.target_stage,comment_kind=t.comment_kind,
                    source_ids=[ref(mids,k) for k in t.material_keys]));tids[t.key]=tid
                currents={}
                for v in t.versions:
                    rev=r.save_revision(tid,v.stage,v.body,0,title=v.title,approval_notes=v.approval_notes,
                        imported_from='chatgpt',created_at=v.created_at or now(),date_unknown=not bool(v.created_at))
                    vids[v.key]=rev['id'];owners[v.key]=tid
                    if v.current:
                        if v.stage in currents:raise ValueError('同一任务、同一阶段存在多个当前版本')
                        currents[v.stage]=rev['id']
                # Only explicitly identified latest drafts become current; no guessed approvals.
                r.set_task_state(tid,active=currents,status='paused',message='已迁入，请核对历史资料后继续',
                    raw_history=t.raw_history,publication=t.publication,imported_from='chatgpt')
            for t in tasks:
                tid=tids[t.key]
                parent=ref(vids,t.parent_version)
                if parent:r.update_task(tid,{'parent_revision_id':parent})
                for v in t.versions:
                    rev=r.revision(vids[v.key]);source=ref(vids,v.source_version)
                    if source and (owners[v.source_version]!=tid or v.stage!='backtranslation' or r.revision(source)['stage']!='english'):
                        raise ValueError('中文回译引用必须对应本任务的英文版本')
                    rev['source_revision_id']=source;rev['stale']=False
                    if v.stage=='backtranslation' and (not source or source!=r.task(tid)['active'].get('english')):rev['stale']=True
                    r.put('revision',rev)
                for op in t.opinions:
                    base=ref(vids,op.base_version)
                    if base and owners[op.base_version]!=tid:raise ValueError('意见引用了其他任务的稿件')
                    o=Opinion(task_id=tid,stage=op.stage,source=op.source,raw_text=op.raw_text,base_revision_id=base,
                        scope='selection' if op.selection else 'task',selection=op.selection,field=op.field).model_dump()
                    r.put('opinion',o|{'status':op.status,'created_at':op.created_at or now(),'date_unknown':not bool(op.created_at)})
            if history:r.put('history',{'id':uid(),'project_id':pid,'records':history,'created_at':now()})
            records=[{'kind':kind,'data':json.loads(data)} for kind,data in r.db.conn.execute('SELECT kind,data FROM records ORDER BY rowid')]
            return records,coverage,project.rules
        finally:r.db.conn.close()
