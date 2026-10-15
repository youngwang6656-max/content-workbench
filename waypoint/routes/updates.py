from pathlib import Path
from fastapi import Body
from fastapi.responses import FileResponse
from waypoint.updates import Updates
def install(app):
    updates=Updates(app.state.repo,Path(__file__).resolve().parents[2]);app.state.updates=updates
    @app.get('/api/updates/status')
    def status():return updates.status()
    @app.post('/api/updates/source')
    def source(data:dict=Body(...)):return updates.save_source(data.get('url'))
    @app.post('/api/updates/check')
    async def check():return await updates.check()
    @app.post('/api/updates/download')
    async def download(data:dict=Body(...)):return await updates.download(data.get('candidate_id'))
    @app.get('/api/updates/packages/{id}')
    def package(id:str):
        path=updates.packages.get(id)
        if not path or not path.is_file():raise ValueError('更新包不存在或服务已重启，请重新检查下载')
        return FileResponse(path,filename=path.name,media_type='application/zip')
