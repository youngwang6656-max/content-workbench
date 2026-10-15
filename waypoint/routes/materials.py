from fastapi import Body,UploadFile,File,Form
from fastapi.responses import FileResponse
from waypoint.materials import Materials

def install(app):
    r=app.state.repo;m=Materials(r)
    from waypoint.material_reading import analyze,adopt,supplement,describe,active,hydrate
    @app.get('/api/materials/{id}/reading')
    def reading_info(id:str):
        material=hydrate(r,active(r,id))
        return {'material':material,**describe(material)}
    @app.post('/api/materials/{id}/analyze')
    async def analyze_material(id:str,data:dict=Body(...)):
        return await analyze(app.state.engine,id,data)
    @app.post('/api/materials/{id}/adopt-analysis')
    def adopt_analysis(id:str,data:dict=Body(...)):return adopt(r,id,data.get('analysis_id'))
    @app.post('/api/materials/{id}/supplement')
    def supplement_text(id:str,data:dict=Body(...)):return supplement(r,id,data.get('text'),data.get('complete',False))
    @app.post('/api/materials/{id}/batch-read')
    async def batch_read(id:str,data:dict=Body(...)):
        from waypoint.material_batch import read_next
        return await read_next(app.state.engine,id,data)
    @app.post('/api/materials/archive-batch')
    def archive_batch(data:dict=Body(...)):
        if 'project_id' not in data:raise ValueError('请明确资料所属范围')
        return m.archive_batch(data.get('ids'),data['project_id'])
    @app.get('/api/materials')
    def materials(project_id:str|None=None,include_global:bool=False):
        if project_id is not None:r.get(project_id,'project')
        rows=r.list('material',project_id=project_id)
        if include_global and project_id is not None:rows+=r.list('material',project_id=None)
        return [x for x in rows if not x.get('reading_translation')]
    @app.post('/api/materials')
    async def add(data:dict=Body(...)):
        saved=m.add_text(data.get('project_id'),data.get('name','资料'),data.get('text',''),data.get('kind','fact'),data.get('url',''),data.get('published_at',''),data.get('trust','unverified'))
        app.state.material_auto.enqueue(saved['id'])
        return r.get(saved['id'],'material')
    @app.post('/api/materials/upload')
    async def upload(project_id:str|None=Form(None),file:UploadFile=File(...)):
        data=await file.read(20_000_001)
        saved=m.import_bytes(project_id,file.filename or 'file',data)
        app.state.material_auto.enqueue(saved['id'])
        return r.get(saved['id'],'material')
    @app.post('/api/materials/{id}/archive')
    def archive(id:str):return m.archive(id)
    @app.get('/api/materials/{id}/file')
    def original(id:str):
        d=r.get(id,'material')
        if not d.get('path'):raise ValueError('此资料没有附件')
        path=(r.db.root/'attachments'/d['path']).resolve()
        if path.parent!=(r.db.root/'attachments').resolve():raise ValueError('文件路径无效')
        return FileResponse(path,filename=d['name'])
    @app.get('/api/rules')
    def rules(project_id:str|None=None):return r.rules(project_id)
    @app.post('/api/rules')
    def rule(data:dict=Body(...)):return r.add_rule(data.get('project_id'),data.get('text',''),append=data.get('append') is True)
    from waypoint.search import find_posts
    @app.post('/api/search/posts')
    async def search(data:dict=Body(...)):
        r.get(data.get('project_id',''),'project')
        return await find_posts(data.get('communities',''),data.get('keywords',''),data.get('days',10))
