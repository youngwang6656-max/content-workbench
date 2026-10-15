import json
from fastapi import Body
from waypoint.budget import Budget
from waypoint.contracts import uid,now

def install(app):
    r=app.state.repo;p=app.state.provider;b=Budget(r)
    @app.get('/api/settings')
    def settings():return r.settings()
    @app.post('/api/settings')
    def save(data:dict=Body(...)):return r.save_settings(data)
    @app.get('/api/usage-status')
    def usage():
        from waypoint.usage import usage_status
        return usage_status(r)
    @app.post('/api/usage-status/check')
    async def check_usage():
        from waypoint.usage import usage_status
        if r.settings()['switch_policy']=='auto':
            report=await p.capabilities();r.put('connection',report|{'id':'connection'})
        return usage_status(r)
    @app.get('/api/budget')
    def budget():return b.summary()
    @app.post('/api/budget/external')
    def external(data:dict=Body(...)):return b.add_external(data.get('amount'),data.get('note',''))
    @app.post('/api/budget/{id}/settle')
    def settle(id:str,data:dict=Body(...)):
        b.settle(id,data.get('amount'));return {'ok':True}
    @app.post('/api/connection/check')
    async def check():
        report=await p.capabilities();r.put('connection',report|{'id':'connection'});return report
    @app.get('/api/connection')
    def connection():
        try:return r.get('connection','connection')
        except ValueError:return {'auth_state':'unverified','models':[],'message':'尚未在此电脑验证'}
    @app.post('/api/connection/login')
    async def login():return await p.login()
    @app.get('/api/connection/report')
    def report():return {'connection':connection(),'saved_at':now(),'notice':'文本及截图成功任务才证明对应能力；未运行的能力保持未验证'}
    from waypoint.backup import Backup
    from fastapi import UploadFile,File
    from fastapi.responses import FileResponse
    import tempfile
    from pathlib import Path
    backups={}
    @app.post('/api/backup')
    def backup():
        path=Backup(r).create_backup(r.db.root/'backups');id=uid();backups[id]=path;return {'id':id}
    @app.get('/api/backup/{id}')
    def download_backup(id:str):
        if id not in backups:raise ValueError('备份不存在，请重新创建')
        return FileResponse(backups[id],filename='waypoint_backup.zip')
    @app.post('/api/backup/restore')
    async def restore(file:UploadFile=File(...)):
        data=await file.read(200_000_001)
        if len(data)>200_000_000:raise ValueError('备份过大')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'restore.zip';path.write_bytes(data);Backup(r).restore_backup(path)
        app.state.engine.recover();app.state.comment_search.recover();app.state.material_auto.recover();return {'ok':True}
