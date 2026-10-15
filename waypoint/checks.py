import re,json

def validate_result(result,snapshot):
    issues=[];stage=snapshot['target_stage'];source=snapshot.get('raw_input','')+'\n'+json.dumps(snapshot.get('materials',[]),ensure_ascii=False)
    if snapshot.get('base'):source+='\n'+snapshot['base'].get('body','')+'\n'+snapshot['base'].get('title','')
    def add(code,field,message,severity='error'):
        issues.append({'code':code,'field':field,'severity':severity,'message_zh':message})
    for field in ['title','body']:
        text=result.get(field,'')
        if field=='body' and not text.strip():add('empty',field,'正文为空')
        if not text.strip():continue
        zh=len(re.findall(r'[\u4e00-\u9fff]',text))
        if stage!='english' and zh==0:add('language',field,'此环节应使用中文，准确名称与必要原文除外')
        if stage=='english' and zh>max(2,len(text)*.15):add('language',field,'交付成稿应使用自然英文')
        if stage=='english':
            if '老细' in text:add('copy',field,'复制正文不应包含对用户的称呼')
            if re.search('[—–]',text):add('punctuation',field,'正文含禁用破折号')
            for m in re.finditer(r'\S*-\S*',text):
                token=m.group()
                if token not in source and not token.startswith(('http://','https://')):add('punctuation',field,'请检查连字符；准确名称与网址不应改写')
            for num in set(re.findall(r'\b\d+(?:\.\d+)?\b',text)):
                if num not in source:add('fact',field,f'数字 {num} 未在本轮材料中找到依据，请核实','warning')
    note=result.get('note_zh','')
    if note and not re.search(r'[\u4e00-\u9fff]',note):add('language','note_zh','修改说明应使用中文')
    for q in result.get('questions',[]):
        if not re.search(r'[\u4e00-\u9fff]',q):add('language','questions','待确认问题应使用中文')
    return issues
