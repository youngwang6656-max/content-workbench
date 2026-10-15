"""Editable source releases; personal installation data is never collected."""
import hashlib,json,re,stat,zipfile,os
from pathlib import Path,PurePosixPath
from waypoint.contracts import now
from waypoint.provenance import metadata
BASELINE='release-files.json'
TOP={'README.md','AGENTS.md','CODEX_HANDOFF.md','pyproject.toml','requirements.lock','package.json',
     'playwright.config.js','启动waypoint.cmd','发布新版.cmd','DEVELOPER_PROVENANCE.json','给AI的启动说明.md','先看这里.html','启动内容工作台.cmd','GITHUB发布说明.md'}
REQUIRED={'waypoint/__init__.py','waypoint/server.py','waypoint/launcher.py','waypoint/web/index.html',
          'scripts/start_windows.cmd','启动waypoint.cmd','pyproject.toml','requirements.lock','DEVELOPER_PROVENANCE.json'}
MAX_PACKAGE=50_000_000
MAX_EXPANDED=200_000_000

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:0|[1-9]\d{0,5})\.(?:0|[1-9]\d{0,5})\.(?:0|[1-9]\d{0,5})',value):raise ValueError('版本号须为三个非负整数，例如 0.6.0')
    return tuple(map(int,value.split('.')))

def source_version(root):
    text=(Path(root)/'waypoint/__init__.py').read_text(encoding='utf-8')
    found=re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]",text)
    if not found:raise ValueError('源码缺少版本号')
    version_tuple(found[1]);return found[1]

def safe_relative(name):
    if not isinstance(name,str) or not name or len(name)>240 or name.startswith('/') or '\\' in name:raise ValueError('发布包包含不安全路径')
    for part in name.split('/'):
        if part in ('','.', '..') or part.rstrip(' .')!=part or any(ord(c)<32 or c in ':<>"|?*' for c in part):raise ValueError('发布包包含不安全路径')
        if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',part.split('.')[0],re.I):raise ValueError('发布包包含 Windows 保留路径')
    return name

def allowed_source(name):
    safe_relative(name);p=PurePosixPath(name)
    if any(part.startswith('.') or part in ('__pycache__','node_modules','private','attachments','backups','runtime_logs') for part in p.parts):return False
    if len(p.parts)==1:return name in TOP
    if p.parts[0]=='waypoint':return p.suffix in ('.py','.sql','.md','.html','.css','.js') or name in ('waypoint/web/workbench-mark.svg',)
    if p.parts[0]=='scripts':return p.suffix in ('.py','.cmd','.command','.ps1')
    if p.parts[0]=='tests':return p.suffix in ('.py','.js','.cjs','.json','.txt')
    if p.parts[0]=='docs':return p.suffix=='.md'
    return False

def source_files(root):
    root=Path(root).resolve();files={};candidates=[root/n for n in TOP if (root/n).exists()]
    for folder in ('waypoint','scripts','tests','docs'):
        base=root/folder
        if base.is_dir() and not base.is_symlink():candidates.extend(base.rglob('*'))
    for p in candidates:
        if not p.is_file():continue
        name=p.relative_to(root).as_posix()
        if not allowed_source(name):continue
        if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('源码含指向外部的文件链接，请先核对')
        if p.stat().st_size>20_000_000:raise ValueError('单个源码文件过大')
        files[name]=p.read_bytes()
    if len(files)>5000 or sum(map(len,files.values()))>MAX_EXPANDED:raise ValueError('源码发布包过大')
    return files

def json_bytes(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')

def build_release(root,output_dir,download_url='',notes_zh=''):
    root=Path(root);version=source_version(root);files=source_files(root)
    if download_url:
        from waypoint.updates import validate_update_url
        download_url=validate_update_url(download_url)
    if not isinstance(notes_zh,str) or len(notes_zh)>6000:raise ValueError('更新说明过长')
    for name,content in files.items():
        if name.endswith('.cmd'):
            try:files[name]=content.decode('ascii').replace('\r\n','\n').replace('\r','\n').replace('\n','\r\n').encode('ascii')
            except UnicodeError:raise ValueError('Windows CMD 必须为 ASCII 源码') from None
    files['DEVELOPER_PROVENANCE.json']=json_bytes(metadata())
    if not REQUIRED.issubset(files):raise ValueError('缺少启动所需程序文件')
    baseline={'format':'waypoint-release-files','schema':1,'version':version,
              'files':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(files.items())}}
    destination=Path(output_dir);destination.mkdir(parents=True,exist_ok=True)
    package=destination/('content_workbench_v'+version.replace('.','_')+'.zip');temporary=package.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
            for name,content in sorted(files.items()):z.writestr('content_workbench/'+name,content)
            z.writestr('content_workbench/'+BASELINE,json_bytes(baseline))
        if temporary.stat().st_size>MAX_PACKAGE:raise ValueError('发布包超过五十 MB')
        validate_package(temporary,version);os.replace(temporary,package)
    finally:temporary.unlink(missing_ok=True)
    manifest={'format':'waypoint-update','schema':1,'version':version,'download_url':download_url,
              'sha256':hashlib.sha256(package.read_bytes()).hexdigest(),'size':package.stat().st_size,
              'min_python':'3.12','notes_zh':notes_zh,'published_at':now()}
    manifest_path=destination/('update-manifest.json' if download_url else 'update-manifest.template.json');manifest_path.write_bytes(json_bytes(manifest))
    return {'version':version,'package':str(package),'manifest':str(manifest_path),'configured':bool(download_url),'files':len(files)}

def read_baseline(data):
    try:
        b=json.loads(data)
        if b['format']!='waypoint-release-files' or b['schema']!=1 or not isinstance(b['files'],dict) or not 1<=len(b['files'])<=5000:raise ValueError()
        version_tuple(b['version']);seen=set()
        for name,digest in b['files'].items():
            if not allowed_source(name) or name.casefold() in seen or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError()
            seen.add(name.casefold())
        if not REQUIRED.issubset(b['files']):raise ValueError()
        return b
    except (ValueError,TypeError,KeyError,AttributeError):raise ValueError('程序文件基线无效') from None

def validate_package(path,expected_version):
    try:
        with zipfile.ZipFile(path) as z:
            entries=z.infolist();seen=set();files={}
            if not 1<=len(entries)<=5001 or sum(i.file_size for i in entries)>MAX_EXPANDED:raise ValueError()
            for item in entries:
                if not item.filename.startswith('content_workbench/') or item.is_dir() or item.file_size>20_000_000 or item.flag_bits&1 or stat.S_ISLNK(item.external_attr>>16):raise ValueError()
                name=safe_relative(item.filename[len('content_workbench/'):])
                if name.casefold() in seen or (name!=BASELINE and not allowed_source(name)):raise ValueError()
                seen.add(name.casefold());files[name]=item
            baseline=read_baseline(z.read(files[BASELINE]))
            if baseline['version']!=expected_version or set(files)-{BASELINE}!=set(baseline['files']):raise ValueError()
            for name,digest in baseline['files'].items():
                if hashlib.sha256(z.read(files[name])).hexdigest()!=digest:raise ValueError()
            version=re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]",z.read(files['waypoint/__init__.py']).decode('utf-8'))
            if not version or version[1]!=expected_version:raise ValueError()
            return {'version':baseline['version'],'files':len(baseline['files'])}
    except (ValueError,TypeError,KeyError,zipfile.BadZipFile,RuntimeError,NotImplementedError,OSError):raise ValueError('更新包结构或文件校验失败，未替换程序') from None

def local_changes(root):
    root=Path(root);baseline=root/BASELINE
    if not baseline.is_file():return {'state':'missing','changed':[],'deleted':[],'added':[],'count':0}
    try:
        if baseline.is_symlink() or baseline.stat().st_size>2_000_000:raise ValueError()
        b=read_baseline(baseline.read_bytes());current=source_files(root)
        changed=sorted(n for n,d in b['files'].items() if n in current and hashlib.sha256(current[n]).hexdigest()!=d)
        deleted=sorted(set(b['files'])-set(current));added=sorted(set(current)-set(b['files']))
        return {'state':'modified' if changed or deleted or added else 'clean','changed':changed,'deleted':deleted,'added':added,
                'count':len(changed)+len(deleted)+len(added),'baseline_version':b['version']}
    except (ValueError,OSError):return {'state':'invalid','changed':[],'deleted':[],'added':[],'count':0}
