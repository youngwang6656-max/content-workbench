import asyncio,json,secrets
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,FileResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from waypoint.repository import Repository
from waypoint.providers.codex import CodexProvider
from waypoint.workflow import Engine
from waypoint.material_auto import AutoMaterialProcessor
from waypoint.accounts import COOKIE
from waypoint.local_identity import LocalIdentity

def create_app(data_dir,provider=None,*,accounts_enabled=True):
    repo=Repository(data_dir);codex=provider or CodexProvider(Path(data_dir));engine=Engine(repo,codex);token=secrets.token_urlsafe(32)
    material_auto=AutoMaterialProcessor(engine)
    @asynccontextmanager
    async def lifespan(app):
        engine.recover();material_auto.recover();app.state.comment_search.recover();yield
        await app.state.comment_search.close()
        await material_auto.close()
        await engine.close()
        if hasattr(codex,'close'):await codex.close()
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.repo=repo;app.state.provider=codex;app.state.engine=engine;app.state.material_auto=material_auto
    accounts=LocalIdentity(Path(data_dir)) if accounts_enabled else None
    app.state.accounts=accounts
    @app.middleware('http')
    async def secure(request,call_next):
        host=request.headers.get('host','');parsed=urlparse('http://'+host)
        origin=request.headers.get('origin')
        if parsed.hostname not in ('127.0.0.1','localhost','::1') or (origin and origin not in ('http://'+host,'https://'+host)) or request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'仅允许本机工作台访问'},status_code=403)
        auth=accounts.session(request.cookies.get(COOKIE)) if accounts else None
        request.state.auth=auth
        public=request.url.path in ('/api/session','/api/auth/name') or (request.method in ('GET','HEAD') and request.url.path in ('/api/branding','/api/branding/logo'))
        if accounts and request.url.path.startswith('/api/') and not public and not auth:
            return JSONResponse({'detail':'请先输入使用名称'},status_code=401)
        expected_token=auth['csrf'] if auth else token
        if request.method not in ('GET','HEAD','OPTIONS') and not secrets.compare_digest(request.headers.get('x-waypoint-token',''),expected_token):
            return JSONResponse({'detail':'会话已更新，请刷新页面后再试'},status_code=403)
        try: size=int(request.headers.get('content-length','0'))
        except ValueError:return JSONResponse({'detail':'请求长度不正确'},status_code=400)
        max_size=201_000_000 if request.url.path=='/api/backup/restore' else (101_000_000 if request.url.path in ('/api/transfer/preview','/api/transfer/raw/inspect') else 21_000_000)
        if size>max_size:return JSONResponse({'detail':'文件过大，单个文件上限二十 MB'},status_code=413)
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'",'Cache-Control':'no-store'})
        return response
    @app.exception_handler(ValueError)
    async def value_error(request,e):return JSONResponse({'detail':str(e)},status_code=400)
    @app.get('/api/session')
    def session(request:Request):
        auth=request.state.auth
        return {'token':auth['csrf'] if auth else token,'version':'1.0.1','edition':'generic',
                'auth':{'enabled':accounts_enabled,'mode':'name','configured':accounts.configured() if accounts else False,
                        'user':auth['user'] if auth else None}}
    @app.get('/')
    def index():return FileResponse(Path(__file__).parent/'web/index.html')
    @app.get('/api/events')
    async def events(request:Request):
        async def stream():
            previous=''
            while not await request.is_disconnected():
                if accounts and not accounts.session(request.cookies.get(COOKIE)):break
                stamp=json.dumps([(t['id'],t['updated_at'],t['status']) for t in repo.list('task')])
                if stamp!=previous:yield 'data: '+stamp+'\n\n';previous=stamp
                else:yield ': heartbeat\n\n'
                await asyncio.sleep(2)
        return StreamingResponse(stream(),media_type='text/event-stream')
    from waypoint.routes.tasks import install as tasks
    from waypoint.routes.materials import install as materials
    from waypoint.routes.settings import install as settings
    from waypoint.routes.transfer import install as transfer
    from waypoint.routes.communities import install as communities
    from waypoint.routes.api_profiles import install as api_profiles
    from waypoint.routes.updates import install as updates
    from waypoint.comment_sources import install as comment_sources
    from waypoint.manual import install as manual
    from waypoint.branding import install as branding
    branding(app)
    manual(app)
    comment_sources(app)
    tasks(app);materials(app);settings(app);transfer(app);communities(app);api_profiles(app);updates(app)
    if accounts:install_accounts(app)
    app.mount('/static',StaticFiles(directory=Path(__file__).parent/'web'),name='static')
    return app

from waypoint.local_identity import install as install_accounts
