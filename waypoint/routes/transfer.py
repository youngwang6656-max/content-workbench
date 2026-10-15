from pathlib import Path
from fastapi import Body,UploadFile,File,Form
from fastapi.responses import Response,FileResponse,PlainTextResponse
from waypoint.transfer import ProjectTransfer,MAX_UPLOAD
from waypoint.materials import Materials
from waypoint.contracts import now
from starlette.concurrency import run_in_threadpool


def install(app):
    r=app.state.repo;service=ProjectTransfer(r);app.state.transfer=service
    @app.get('/api/transfer/prompt')
    def prompt():return PlainTextResponse((Path(__file__).parents[1]/'transfer_prompt.md').read_text(encoding='utf-8'))
    @app.post('/api/transfer/preview')
    async def preview(files:list[UploadFile]=File(default=[]),text:str=Form(default='')):
        values=[];total=0
        if text.strip():values.append(('粘贴内容.json',text.encode()));total=len(values[0][1])
        if total>MAX_UPLOAD:raise ValueError('迁移内容超过一百 MB')
        for f in files:
            data=await f.read(MAX_UPLOAD-total+1);total+=len(data)
            if total>MAX_UPLOAD:raise ValueError('迁移文件合计超过一百 MB')
            values.append((f.filename or '项目.json',data))
        return service.preview(values)
    @app.post('/api/transfer/commit')
    def commit(data:dict=Body(...)):
        return service.commit(data.get('token',''),data.get('name',''),data.get('accept_rules') is True)
    @app.post('/api/transfer/raw/inspect')
    async def inspect_raw(file:list[UploadFile]=File(...)):
        values=[];total=0
        if len(file)>100:raise ValueError('原始导出最多一百个文件')
        for f in file:
            data=await f.read(MAX_UPLOAD-total+1);total+=len(data)
            if total>MAX_UPLOAD:raise ValueError('原始导出合计最多一百 MB')
            values.append((f.filename or 'conversations.json',data))
        return await run_in_threadpool(service.inspect_raw_files,values)
    @app.post('/api/transfer/raw/preview')
    def preview_raw(data:dict=Body(...)):
        return service.preview_raw(data.get('token',''),data.get('conversation_ids'),data.get('name',''))
    @app.get('/api/projects/{id}/export')
    def export(id:str):return Response(service.export(id),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="waypoint_project.zip"'})
    @app.get('/api/projects/{id}/history')
    def history(id:str,q:str='',offset:int=0):
        if offset<0:raise ValueError('页码无效')
        return service.history(id,q,offset)
    @app.get('/api/transfer/{id}/source')
    def source(id:str):
        receipt=r.get(id,'transfer');name=receipt.get('archive_path','')
        if not name or Path(name).name!=name or '\\' in name:raise ValueError('此记录无原始 GPT 迁移文件')
        return FileResponse(r.db.root/'attachments'/name,filename='waypoint_original_handoff.zip')
    @app.post('/api/materials/{id}/complete-file')
    async def complete_file(id:str,file:UploadFile=File(...)):
        from waypoint.comment_jobs import protect_material
        protect_material(r,id)
        data=await file.read(20_000_001)
        with r.db.lock:
            m=r.get(id,'material')
            if not m.get('missing_attachment') or m.get('path'):raise ValueError('此资料无需补传，请使用资料页添加新文件')
            added=Materials(r).import_bytes(m['project_id'],file.filename or 'file',data)
            with r.db.conn:
                m.update(path=added['path'],extraction=added['extraction'],sha256=added['sha256'],missing_attachment=False,
                         units=added.get('units',[]),extraction_warnings=added.get('extraction_warnings',[]))
                m.setdefault('original_text_history',[]).append({'text':m['text'],'created_at':now()})
                if added['text']:m['text']='\n\n'.join(x for x in [m['text'],added['text']] if x)
                r._put('material',m);r.db.conn.execute('DELETE FROM records WHERE id=?',(added['id'],))
                for t in r.list('task',project_id=m['project_id']):
                    t['input_epoch']+=1;t['message']='迁移附件已补齐，请核对更新后的资料';r._put('task',t)
                    for rid in t['active'].values():r._stale(rid)
            app.state.material_auto.enqueue(m['id'])
            return r.get(m['id'],'material')
