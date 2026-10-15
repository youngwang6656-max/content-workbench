"""Explicit update checks/downloads. Never executes downloaded code."""
import asyncio,hashlib,json,os,re,sys,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,urljoin
import httpx
from waypoint import __version__
from waypoint.api_profiles import validate_url,check_public_host
from waypoint.distribution import local_changes,version_tuple,validate_package,MAX_PACKAGE
from waypoint.backup import Backup
from waypoint.contracts import uid
from contextlib import nullcontext

def validate_update_url(value):
    try:
        if not isinstance(value,str) or len(value)>2500 or any(c.isspace() or ord(c)<32 for c in value):raise ValueError()
        p=urlsplit(value)
        if p.fragment or '\\' in value:raise ValueError()
        clean=validate_url(urlunsplit((p.scheme,p.netloc,p.path,'','')))
        return clean+('?' + p.query if p.query else '')
    except ValueError:raise ValueError('更新地址须为公开 HTTPS 地址，不含账号密码或本机/内网地址') from None

async def fetch(url,limit,*,transport=None,target=None):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=15),follow_redirects=False,transport=transport,
                                     headers={'User-Agent':'waypoint-updates','Accept':'application/json, application/zip'}) as client:
            for _ in range(6):
                url=validate_update_url(url)
                if transport is None:await check_public_host(url)
                client.cookies.clear()
                async with client.stream('GET',url) as response:
                    if response.status_code in (301,302,303,307,308):
                        location=response.headers.get('location')
                        if not location:raise ValueError('更新服务器未返回有效下载位置')
                        url=urljoin(url,location);continue
                    if response.status_code!=200:raise ValueError(f'更新服务器返回 HTTP {response.status_code}，未改动程序')
                    chunks=[];size=0
                    with (open(target,'wb') if target else nullcontext()) as output:
                        async for chunk in response.aiter_bytes():
                            size+=len(chunk)
                            if size>limit:raise ValueError('更新响应超过允许大小，已停止下载')
                            if target:output.write(chunk)
                            else:chunks.append(chunk)
                    return size if target else b''.join(chunks)
            raise ValueError('更新地址重定向次数过多')
    except httpx.HTTPError:raise ValueError('更新网络请求失败，请核对更新源和本机网络；原程序未改动') from None

def validate_manifest(data):
    try:
        if not isinstance(data,dict) or data.get('format')!='waypoint-update' or data.get('schema')!=1:raise ValueError()
        version_tuple(data['version']);url=validate_update_url(data['download_url'])
        if not isinstance(data['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',data['sha256']):raise ValueError()
        if type(data['size']) is not int or not 0<data['size']<=MAX_PACKAGE:raise ValueError()
        minimum=data.get('min_python','3.12')
        if not isinstance(minimum,str) or not re.fullmatch(r'3\.\d{1,2}',minimum):raise ValueError()
        notes=data.get('notes_zh','')
        if not isinstance(notes,str) or len(notes)>6000:raise ValueError()
        return {k:data[k] for k in ('version','sha256','size')}|{'download_url':url,'notes_zh':notes,'min_python':minimum}
    except (ValueError,TypeError,KeyError):raise ValueError('更新清单不正确或下载地址尚未配置，未改动程序') from None

class Updates:
    def __init__(self,repo,app_root,current_version=None):
        self.repo=repo;self.app_root=Path(app_root);self.version=current_version or __version__
        self.candidate=None;self.packages={};self.lock=asyncio.Lock()
    def status(self):
        return {'current_version':self.version,'manifest_url':self.repo.settings()['update_manifest_url'],
                'local_changes':local_changes(self.app_root),'automatic_install':False}
    def save_source(self,url):
        if url:url=validate_update_url(url)
        elif not isinstance(url,str):raise ValueError('更新源地址不正确')
        self.repo.save_settings({'update_manifest_url':url});self.candidate=None
        return {'manifest_url':url,'message':'更新源已保存；未检查、下载或安装更新'}
    async def check(self,transport=None):
        source=self.repo.settings()['update_manifest_url']
        if not source:raise ValueError('尚未配置更新源，请先填写开发者发布的 HTTPS 清单地址')
        self.candidate=None;raw=await fetch(source,250_000,transport=transport)
        try:manifest=validate_manifest(json.loads(raw))
        except (json.JSONDecodeError,UnicodeError):raise ValueError('更新源没有返回有效 JSON 清单') from None
        if source!=self.repo.settings()['update_manifest_url']:raise ValueError('更新源已改变，请重新检查')
        available=version_tuple(manifest['version'])>version_tuple(self.version)
        result={'available':available,'current_version':self.version,'version':manifest['version'],
                'notes_zh':manifest['notes_zh'],'size':manifest['size'],'min_python':manifest['min_python']}
        if available:
            if tuple(map(int,manifest['min_python'].split('.')))>sys.version_info[:2]:raise ValueError('新版要求更新的 Python，请先更新运行环境')
            self.candidate=manifest|{'id':uid(),'source':source,'expires':time.monotonic()+600};result['candidate_id']=self.candidate['id']
        return result
    async def download(self,candidate_id,transport=None):
        async with self.lock:
            candidate=dict(self.candidate or {})
            if candidate.get('id')!=candidate_id or not candidate or candidate['source']!=self.repo.settings()['update_manifest_url'] or candidate['expires']<time.monotonic():raise ValueError('更新检查已失效，请重新检查后下载')
            directory=self.repo.db.root/'updates';directory.mkdir(exist_ok=True)
            if directory.is_symlink():raise ValueError('更新目录不可为文件链接')
            with tempfile.TemporaryDirectory(dir=directory) as scratch:
                path=Path(scratch)/'package.zip';size=await fetch(candidate['download_url'],candidate['size'],transport=transport,target=path)
                if size!=candidate['size'] or hashlib.sha256(path.read_bytes()).hexdigest()!=candidate['sha256']:raise ValueError('更新包大小或 SHA-256 不一致，未保存、未替换程序')
                await asyncio.to_thread(validate_package,path,candidate['version'])
                if candidate['source']!=self.repo.settings()['update_manifest_url']:raise ValueError('下载期间更新源已改变，未保存程序包')
                backup=await asyncio.to_thread(Backup(self.repo).create_backup,self.repo.db.root/'backups')
                final=directory/('waypoint_workbench_v'+candidate['version'].replace('.','_')+'_'+candidate['sha256'][:12]+'.zip');os.replace(path,final)
            id=uid();self.packages[id]=final
            return {'package_id':id,'version':candidate['version'],'filename':final.name,'backup':str(backup),
                    'message':'已校验下载并备份业务资料。请解压到新文件夹，保留旧目录及自改代码；未自动安装。'}
