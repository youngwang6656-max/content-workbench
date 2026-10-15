"""Local handbooks. Viewing or downloading them never calls a model."""
from pathlib import Path
from fastapi.responses import FileResponse
ROOT=Path(__file__).parent/'manuals'
def install(app):
    @app.get('/api/manual')
    def user_manual():return {'version':'1.0.1','markdown':(ROOT/'用户使用手册.md').read_text(encoding='utf-8')}
    @app.get('/api/manual/download')
    def download():return FileResponse(ROOT/'用户使用手册.md',filename='waypoint-user-manual.md',media_type='text/markdown; charset=utf-8')
    @app.get('/api/manual/agent')
    def agent():return FileResponse(ROOT/'智能体使用手册.md',filename='waypoint-agent-manual.md',media_type='text/plain; charset=utf-8')
