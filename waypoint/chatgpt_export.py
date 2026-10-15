"""Local raw-export preservation. Conversation text is evidence, never instructions."""
import io,json,math,zipfile,re
from datetime import datetime,timezone
from pathlib import PurePosixPath
from waypoint.contracts import uid,now
from waypoint.handoff import unique_json

MAX_RAW=100_000_000
MAX_EXPANDED=200_000_000


def date(value):
    try:
        if type(value) not in (int,float) or not math.isfinite(value):return ''
        return datetime.fromtimestamp(value,timezone.utc).isoformat()
    except (OverflowError,ValueError,OSError):return ''


def read_export(filename,data,*,budget=None):
    if not data or len(data)>MAX_RAW:raise ValueError('原始导出文件上限为一百 MB')
    documents=[data]
    if zipfile.is_zipfile(io.BytesIO(data)):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names=z.namelist()
                if len(names)!=len(set(names)) or len(names)>20000:raise ValueError('导出包存在重复文件或文件数量过多')
                if sum(i.file_size for i in z.infolist())>MAX_EXPANDED:raise ValueError('导出包展开超过二百 MB，请单独选择 conversations.json')
                if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n or ':' in n for n in names):
                    raise ValueError('导出包包含非法路径')
                files=sorted((i for i in z.infolist() if re.fullmatch(r'conversations(?:[-_]?\d+)?\.json',PurePosixPath(i.filename).name) and not i.is_dir()),key=lambda i:i.filename)
                if not files:raise ValueError('请提供含 conversations.json 或编号分卷的原始导出 ZIP，或单独上传 JSON')
                if any(i.flag_bits&1 for i in files) or sum(i.file_size for i in files)>(budget[0] if budget is not None else MAX_RAW):raise ValueError('原始对话文件加密或展开 JSON 合计超过一百 MB')
                documents=[]
                for item in files:
                    with z.open(item) as stream:documents.append(stream.read(MAX_RAW+1))
        except (zipfile.BadZipFile,RuntimeError,NotImplementedError) as exc:raise ValueError('原始导出 ZIP 无法读取') from exc
    if budget is not None:
        budget[0]-=sum(len(document) for document in documents)
        if budget[0]<0:raise ValueError('原始对话展开 JSON 合计超过一百 MB，请分批提供')
    conversations=[]
    for document in documents:
        try:root=unique_json(document.decode('utf-8-sig'))
        except (UnicodeError,json.JSONDecodeError,RecursionError) as exc:raise ValueError('请选择原始 UTF-8 conversations.json，不支持网页摘要或 HTML') from exc
        values=root if isinstance(root,list) else root.get('conversations',[root]) if isinstance(root,dict) else None
        if not isinstance(values,list):raise ValueError('未识别到原始对话列表')
        conversations.extend(values)
    if not isinstance(conversations,list) or not 1<=len(conversations)<=10000:raise ValueError('未识别到原始对话列表')
    rows=[];seen=set();node_count=0
    for index,raw in enumerate(conversations):
        if not isinstance(raw,dict) or not isinstance(raw.get('mapping'),dict) or not raw['mapping']:
            raise ValueError('原始对话缺少 mapping 消息结构；请勿上传交接摘要')
        cid=raw.get('id') or raw.get('conversation_id') or f'{filename}:export-conversation-{index+1}'
        if not isinstance(cid,str) or cid in seen:raise ValueError('原始对话标识缺失或重复')
        seen.add(cid);node_count+=len(raw['mapping'])
        if node_count>100000:raise ValueError('原始对话超过十万个节点，请分批提供')
        rows.append(parse_conversation(raw,f'conversation-{index+1}',cid))
    return rows


def read_export_files(files):
    if not files or len(files)>100 or sum(len(data) for _,data in files)>MAX_RAW:raise ValueError('原始导出合计最多一百 MB、一百个文件')
    rows=[];seen=set();nodes=0;budget=[MAX_RAW]
    for name,data in files:
        for row in read_export(name,data,budget=budget):
            if row['id'] in seen:raise ValueError('原始分卷中对话标识重复，请勿同时上传总文件和重复分卷')
            seen.add(row['id']);nodes+=row['node_count'];row['key']=f'conversation-{len(rows)+1}';rows.append(row)
            if len(rows)>10000 or nodes>100000:raise ValueError('原始导出对话或节点过多，请分批提供')
    return rows


def parse_conversation(raw,key,cid):
    mapping=raw['mapping'];ordered=[];done=set();children={n:0 for n in mapping}
    for n,node in mapping.items():
        if not isinstance(node,dict):raise ValueError('对话节点格式无效')
        parent=node.get('parent')
        if parent is not None:
            if not isinstance(parent,str) or parent not in mapping:raise ValueError('对话存在缺失的父节点，无法确认分支完整性')
            children[parent]+=1
    # Iterative parent ordering handles deep conversations without truncation or recursion limits.
    for n in mapping:
        trail=[];visiting=set();current=n
        while current is not None and current not in done:
            if current in visiting:raise ValueError('对话节点存在循环引用')
            visiting.add(current);trail.append(current);current=mapping[current].get('parent')
        for item in reversed(trail):
            ordered.append(item);done.add(item)
    title=raw.get('title') or '未命名对话'
    if not isinstance(title,str):raise ValueError('对话标题格式无效')
    history=[];message_count=0;text_count=0;nontext=0;unknown_dates=0;warnings=[];mids=set()
    for n in ordered:
        message=mapping[n].get('message')
        if message is None:continue
        if not isinstance(message,dict):raise ValueError('对话消息格式无效')
        mid=message.get('id')
        if mid:
            if not isinstance(mid,str) or mid in mids:raise ValueError('对话消息标识重复')
            mids.add(mid)
        message_count+=1
        author=message.get('author') or {}
        role=author.get('role') if isinstance(author,dict) else None
        role=role if role in ('user','assistant') else 'unknown'
        created=date(message.get('create_time'))
        if not created:unknown_dates+=1
        content=message.get('content') or {};parts=[];unsupported=False
        if isinstance(content,dict):
            values=content.get('parts')
            if values is None and isinstance(content.get('text'),str):values=[content['text']]
            if isinstance(values,list):
                for part in values:
                    if isinstance(part,str):parts.append(part)
                    elif isinstance(part,dict) and part.get('content_type',part.get('type'))=='text' and isinstance(part.get('text'),str):parts.append(part['text'])
                    else:unsupported=True
            else:unsupported=True
            if content.get('content_type') not in ('text','multimodal_text',None):unsupported=True
        else:unsupported=True
        metadata=message.get('metadata') or {}
        if isinstance(metadata,dict) and metadata.get('attachments'):unsupported=True
        if unsupported:nontext+=1
        text='\n'.join(parts)
        if text:
            text_count+=1
            for start in range(0,len(text),200000):
                history.append({'role':role,'text':text[start:start+200000],'record_type':'original',
                                'source':f'{title} · {cid}/{n}','created_at':created})
    if nontext:warnings.append(f'{title}：{nontext} 条消息含图片、附件或其他非文字内容；仅保留引用，需另行提供原件')
    if unknown_dates:warnings.append(f'{title}：{unknown_dates} 条消息没有可用原始日期，未补造日期')
    if raw.get('current_node') and (not isinstance(raw['current_node'],str) or raw['current_node'] not in mapping):warnings.append(f'{title}：当前分支标识未找到，已保留文件中全部节点')
    return {'key':key,'id':cid,'title':title,'message_count':message_count,'text_message_count':text_count,
            'branch_count':sum(count==0 for count in children.values()),'node_count':len(mapping),
            'nontext_count':nontext,'history_count':len(history),'created_at':date(raw.get('create_time')),
            'updated_at':date(raw.get('update_time')),'warnings':warnings,'history':history,'raw':raw}


def raw_records(selected,name):
    pid=uid();coverage={'sources':[f"原始导出：{c['title']} · {c['message_count']} 条消息 · {c['branch_count']} 个分支" for c in selected],
        'missing':['仅包含所选对话；项目自定义指令、记忆及未随原文提供的附件需另外迁入'],
        'uncertain':['历史对话是参考资料，不自动成为产品事实、当前任务或长期规则']}
    for c in selected:
        for warning in c['warnings']:
            coverage['missing' if '非文字' in warning else 'uncertain'].append(warning)
    audit={k:sum(c[k] for c in selected) for k in ('message_count','text_message_count','branch_count','node_count','nontext_count','history_count')}
    audit['conversation_count']=len(selected)
    records=[{'kind':'project','data':{'id':pid,'name':name,'description':'原始 ChatGPT 对话档案','created_at':now(),
                                     'pinned':False,'sort_order':0,'coverage':coverage,'raw_history_audit':audit}}]
    for c in selected:
        history=c['history']
        for start in range(0,len(history),10000):
            records.append({'kind':'history','data':{'id':uid(),'project_id':pid,'records':history[start:start+10000],'created_at':now()}})
        transcript='\n\n'.join(f"[{h['role']} · {h['created_at'] or '日期未提供'} · {h['source']}]\n{h['text']}" for h in history)
        for start in range(0,len(transcript),200000):
            text=transcript[start:start+200000];part=start//200000+1
            records.append({'kind':'material','data':{'id':uid(),'project_id':pid,'name':f"{c['title'][:160]} · 原始对话 {part}",
                'text':text,'kind':'sample','url':'','trust':'unverified','extraction':'text','archived':False,'created_at':now(),
                'raw_conversation':True,'raw_conversation_id':c['id'],'extraction_warnings':c['warnings']}})
    return records,coverage,audit
