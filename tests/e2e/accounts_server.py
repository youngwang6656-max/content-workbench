"""Browser QA uses disposable local data and an existing test login, never the owner's data."""
import tempfile
import sys
from pathlib import Path
import uvicorn
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from waypoint.server import create_app
from test_workflow import FakeProvider
app=create_app(tempfile.mkdtemp(prefix='waypoint_accounts_qa_'),provider=FakeProvider())
app.state.accounts.register('qa_owner','界面验收账号','disposable-qa-password-2026')
a=app.state.repo.create_project('TOPDON');b=app.state.repo.create_project('DJI')
app.state.repo.create_project('70mai')
from waypoint.contracts import TaskSpec
app.state.repo.create_task(TaskSpec(project_id=a,raw_input='保留的测试想法',name='界面验收测试稿',kind='cb',target_stage='cb'))
uvicorn.run(app,host='127.0.0.1',port=8878,log_level='warning')
