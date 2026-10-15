import difflib

def merge_selection(before,selection,replacement):
    if not selection or before.count(selection)!=1:raise ValueError('修改片段必须在原稿中唯一匹配，请扩大选择范围')
    return before.replace(selection,replacement,1)

def review_scope(snapshot):
    opinions=snapshot['opinions'];clients=[o for o in opinions if o['source']=='client']
    selections=[o for o in opinions if o['scope']=='selection']
    if clients and any(o['source']!='client' for o in opinions):raise ValueError('客户意见与其他待处理意见同时存在，请先明确本轮修改依据')
    if clients and (len(clients)!=1 or not selections):raise ValueError('请标出客户允许修改的原文片段；全文重写可选择全部正文')
    if not selections:return None
    if len(selections)!=1 or len(opinions)!=1:raise ValueError('局部修改请逐轮处理，避免不同范围的意见混用')
    op=selections[0];base=snapshot['base']
    if not base or op['base_revision_id']!=base['id']:raise ValueError('请为局部意见指定确切原稿')
    field=op.get('field','body');before=base[field]
    merge_selection(before,op['selection'],op['selection'])
    return {'selection':op['selection'],'field':field,'base':base}

def compare_revisions(before,after):
    return {k:list(difflib.unified_diff(before.get(k,'').splitlines(),after.get(k,'').splitlines(),fromfile='原稿',tofile='新稿',lineterm='')) for k in ['title','body']}
