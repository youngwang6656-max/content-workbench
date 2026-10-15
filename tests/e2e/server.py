import tempfile,uvicorn,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from waypoint.server import create_app
from test_workflow import FakeProvider
uvicorn.run(create_app(tempfile.mkdtemp(prefix='waypoint_e2e_'),provider=FakeProvider(),accounts_enabled=False),host='127.0.0.1',port=8877)
