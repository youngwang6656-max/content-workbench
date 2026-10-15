"""Installation-local branding. Only the authenticated local owner may change it."""
import hashlib,io,os,tempfile,threading,warnings
from pathlib import Path
from PIL import Image,ImageOps,UnidentifiedImageError
from fastapi import UploadFile,File,HTTPException
from fastapi.responses import Response

MAX_LOGO_BYTES=5_000_000


class Branding:
    def __init__(self,root):
        self.directory=Path(root)/'branding';self.path=self.directory/'logo.png';self.lock=threading.RLock()
    def read(self):
        with self.lock:
            return self.path.read_bytes() if self.path.is_file() else None
    def config(self):
        data=self.read()
        return {'name':'内容工作台','custom_logo':data is not None,
                'logo_url':'/api/branding/logo?v='+hashlib.sha256(data).hexdigest()[:20] if data else '/static/workbench-mark.svg'}
    def save(self,data):
        if not data or len(data)>MAX_LOGO_BYTES:raise ValueError('标识图片上限为 5 MB')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as original:
                    if original.format not in ('PNG','JPEG','WEBP') or getattr(original,'is_animated',False):raise ValueError('请选择静态 PNG、JPEG 或 WebP 图片')
                    if original.width*original.height>16_000_000 or max(original.size)>8000:raise ValueError('图片尺寸过大，请使用不超过 1600 万像素的标识')
                    original.load();image=ImageOps.exif_transpose(original).convert('RGBA')
                    image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
                    output=io.BytesIO();image.save(output,'PNG')
        except (UnidentifiedImageError,OSError,SyntaxError,Image.DecompressionBombWarning,Image.DecompressionBombError) as exc:
            raise ValueError('图片无法读取，请使用有效的静态 PNG、JPEG 或 WebP') from exc
        with self.lock:
            self.directory.mkdir(parents=True,exist_ok=True);temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=self.directory,suffix='.png',delete=False) as stream:
                    temporary=Path(stream.name);stream.write(output.getvalue())
                os.replace(temporary,self.path)
            finally:
                if temporary:temporary.unlink(missing_ok=True)
            return self.config()
    def remove(self):
        with self.lock:self.path.unlink(missing_ok=True);return self.config()


def install(app):
    branding=Branding(app.state.repo.db.root)
    @app.get('/api/branding')
    def config():return branding.config()
    @app.get('/api/branding/logo')
    def logo():
        data=branding.read()
        if data is None:raise HTTPException(404,'尚未上传自定义图片')
        return Response(data,media_type='image/png')
    @app.post('/api/branding/logo')
    async def upload(file:UploadFile=File(...)):
        from starlette.concurrency import run_in_threadpool
        data=await file.read(MAX_LOGO_BYTES+1)
        return await run_in_threadpool(branding.save,data)
    @app.delete('/api/branding/logo')
    def remove():return branding.remove()
