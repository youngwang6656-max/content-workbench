"""One owner per local installation, separate from content and ChatGPT authentication."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from fastapi import Body, Request, Response, HTTPException

COOKIE = 'content_workbench_session'
SESSION_SECONDS = 7 * 24 * 3600
ITERATIONS = 600_000


class Accounts:
    def __init__(self, root):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(root / 'accounts.sqlite', check_same_thread=False, timeout=20)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS owner(id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                display_name TEXT NOT NULL, salt BLOB NOT NULL, password_hash BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(at REAL NOT NULL);
        ''')
        self.dummy_salt = secrets.token_bytes(16)

    @staticmethod
    def _hash(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)

    @staticmethod
    def _password(password):
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ValueError('密码须为 12–128 个字符')
        return password

    def configured(self):
        with self.lock: return bool(self.conn.execute('SELECT 1 FROM owner').fetchone())

    def _user(self):
        row = self.conn.execute('SELECT username,display_name FROM owner').fetchone()
        return {'username': row[0], 'display_name': row[1], 'role':'owner'} if row else None

    def session(self, value):
        if not value or len(value) > 200: return None
        with self.lock:
            row = self.conn.execute('SELECT csrf,expires FROM sessions WHERE id=?', (hashlib.sha256(value.encode()).hexdigest(),)).fetchone()
            if not row or row[1] <= time.time(): return None
            return {'user': self._user(), 'csrf': row[0]}

    def _new_session(self):
        secret = secrets.token_urlsafe(32); csrf = secrets.token_urlsafe(32)
        self.conn.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
        self.conn.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(secret.encode()).hexdigest(), csrf, time.time() + SESSION_SECONDS))
        return secret

    def register(self, username, display_name, password):
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}', username):
            raise ValueError('用户名须为 3–32 个英文字母、数字、点、下划线或短横线')
        if not isinstance(display_name, str) or len(display_name.strip()) > 80:
            raise ValueError('昵称最多八十字')
        salt = secrets.token_bytes(16); digest = self._hash(self._password(password), salt)
        with self.lock, self.conn:
            if self.configured(): raise ValueError('此安装已有个人账号，请登录；其他人请使用自己的安装和数据目录')
            self.conn.execute('INSERT INTO owner VALUES(1,?,?,?,?)', (username.casefold(), display_name.strip() or username, salt, digest))
            return self._new_session()

    def login(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 128 or len(password) > 128:
            raise ValueError('用户名或密码不正确')
        with self.lock, self.conn:
            self.conn.execute('DELETE FROM attempts WHERE at<?', (time.time() - 900,))
            if self.conn.execute('SELECT count(*) FROM attempts').fetchone()[0] >= 5:
                raise HTTPException(429, '登录失败次数过多，请十五分钟后重试')
            row = self.conn.execute('SELECT username,salt,password_hash FROM owner').fetchone()
            digest = self._hash(password, row[1] if row else self.dummy_salt)
            valid = row and hmac.compare_digest(row[2], digest) and row[0] == username.casefold()
            if valid:
                self.conn.execute('DELETE FROM attempts')
                return self._new_session()
            self.conn.execute('INSERT INTO attempts VALUES(?)', (time.time(),))
        # Raise after committing the failed attempt, so retries cannot reset the limit.
        raise ValueError('用户名或密码不正确')

    def logout(self, secret):
        with self.lock, self.conn:
            self.conn.execute('DELETE FROM sessions WHERE id=?', (hashlib.sha256(secret.encode()).hexdigest(),))

    def profile(self, display_name):
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name.strip()) > 80:
            raise ValueError('请填写一至八十字的昵称')
        with self.lock, self.conn:
            self.conn.execute('UPDATE owner SET display_name=?', (display_name.strip(),))
            return self._user()

    def change_password(self, current, password):
        self._password(password)
        if not isinstance(current, str) or len(current) > 128: raise ValueError('当前密码不正确')
        with self.lock, self.conn:
            row = self.conn.execute('SELECT salt,password_hash FROM owner').fetchone()
            if not hmac.compare_digest(row[1], self._hash(current, row[0])):
                raise ValueError('当前密码不正确')
            salt = secrets.token_bytes(16)
            self.conn.execute('UPDATE owner SET salt=?,password_hash=?', (salt, self._hash(password, salt)))
            self.conn.execute('DELETE FROM sessions')
            return self._new_session()


def install(app):
    accounts = app.state.accounts
    def set_cookie(response, secret):
        response.set_cookie(COOKIE, secret, httponly=True, samesite='strict', max_age=SESSION_SECONDS, path='/')
        return {'ok': True}

    @app.post('/api/auth/register')
    def register(response: Response, data: dict = Body(...)):
        return set_cookie(response, accounts.register(data.get('username'), data.get('display_name', ''), data.get('password')))

    @app.post('/api/auth/login')
    def login(request: Request, response: Response, data: dict = Body(...)):
        secret = accounts.login(data.get('username'), data.get('password'))
        if request.cookies.get(COOKIE): accounts.logout(request.cookies[COOKIE])
        return set_cookie(response, secret)

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response):
        accounts.logout(request.cookies.get(COOKIE, '')); response.delete_cookie(COOKIE, path='/'); return {'ok': True}

    @app.patch('/api/auth/profile')
    def profile(data: dict = Body(...)): return accounts.profile(data.get('display_name'))

    @app.post('/api/auth/password')
    def password(response: Response, data: dict = Body(...)):
        return set_cookie(response, accounts.change_password(data.get('current_password'), data.get('password')))
