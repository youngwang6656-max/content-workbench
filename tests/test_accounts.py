"""Password-store rollback remains possible, but active access is name-only."""
import pytest
from fastapi import HTTPException
from waypoint.accounts import Accounts,SESSION_SECONDS


def client(root):
    from fastapi.testclient import TestClient
    from waypoint.server import create_app
    app=create_app(root);return app,TestClient(app,base_url='http://localhost')


def register(c):
    token=c.get('/api/session').json()['token']
    result=c.post('/api/auth/name',headers={'X-Waypoint-Token':token},json={'name':'老细'})
    assert result.status_code==200
    return c.get('/api/session').json()['token']


def test_retained_owner_password_is_hashed_and_can_be_restored(tmp_path):
    account=Accounts(tmp_path);account.register('owner','老细','local-test-password-123')
    assert b'local-test-password-123' not in (tmp_path/'accounts.sqlite').read_bytes()
    secret=account.login('OWNER','local-test-password-123')
    assert account.session(secret)['user']['username']=='owner'


def test_retained_password_change_revokes_old_sessions(tmp_path):
    account=Accounts(tmp_path);secret=account.register('owner','老细','local-test-password-123')
    new=account.change_password('local-test-password-123','new-local-password-123')
    assert account.session(secret) is None and account.session(new)['user']['role']=='owner'


def test_retained_password_attempt_limit_is_not_removed(tmp_path):
    account=Accounts(tmp_path);account.register('owner','老细','local-test-password-123')
    for _ in range(5):
        with pytest.raises(ValueError):account.login('owner','wrong')
    with pytest.raises(HTTPException) as exc:account.login('owner','local-test-password-123')
    assert exc.value.status_code==429


def test_retained_password_session_expires(tmp_path,monkeypatch):
    import time
    account=Accounts(tmp_path);secret=account.register('owner','老细','local-test-password-123')
    later=time.time()+SESSION_SECONDS+1
    monkeypatch.setattr('waypoint.accounts.time.time',lambda:later)
    assert account.session(secret) is None
