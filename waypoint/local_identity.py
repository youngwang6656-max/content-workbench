"""Name-only local access: names are display labels, not separate user accounts."""
import hashlib,secrets,sqlite3,threading,time
from fastapi import Body,Request,Response
from waypoint.accounts import COOKIE,SESSION_SECONDS


class LocalIdentity:
    def __init__(self,root):
        self.lock=threading.RLock()
        self.conn=sqlite3.connect(root/'local_identity.sqlite',check_same_thread=False,timeout=20)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('''
          CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);
        ''')
    @staticmethod
    def name(value):
        if not isinstance(value,str) or not 1<=len(value.strip())<=80:raise ValueError('请输入 1–80 个字符的名称')
        return value.strip()
    def configured(self):
        with self.lock:return bool(self.conn.execute('SELECT 1 FROM profile').fetchone())
    def _user(self):
        row=self.conn.execute('SELECT name FROM profile WHERE id=1').fetchone()
        return {'username':'local-owner','display_name':row[0],'role':'owner'} if row else None
    def enter(self,name):
        name=self.name(name);secret=secrets.token_urlsafe(32)
        with self.lock,self.conn:
            self.conn.execute('INSERT INTO profile VALUES(1,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',(name,))
            self.conn.execute('DELETE FROM sessions WHERE expires<=?',(time.time(),))
            self.conn.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(secret.encode()).hexdigest(),secrets.token_urlsafe(32),time.time()+SESSION_SECONDS))
        return secret
    def session(self,value):
        if not isinstance(value,str) or not value or len(value)>200:return None
        with self.lock:
            row=self.conn.execute('SELECT csrf,expires FROM sessions WHERE id=?',(hashlib.sha256(value.encode()).hexdigest(),)).fetchone()
            if not row or row[1]<=time.time():return None
            return {'user':self._user(),'csrf':row[0]}
    def logout(self,value):
        with self.lock,self.conn:self.conn.execute('DELETE FROM sessions WHERE id=?',(hashlib.sha256(value.encode()).hexdigest(),))
    def profile(self,name):
        name=self.name(name)
        with self.lock,self.conn:
            self.conn.execute('UPDATE profile SET name=? WHERE id=1',(name,))
            return self._user()


def install(app):
    identity=app.state.accounts
    @app.post('/api/auth/name')
    def enter(request:Request,response:Response,data:dict=Body(...)):
        secret=identity.enter(data.get('name'))
        if request.cookies.get(COOKIE):identity.logout(request.cookies[COOKIE])
        response.set_cookie(COOKIE,secret,httponly=True,samesite='strict',max_age=SESSION_SECONDS,path='/')
        return {'ok':True}
    @app.patch('/api/auth/profile')
    def profile(data:dict=Body(...)):return identity.profile(data.get('display_name'))
    @app.post('/api/auth/logout')
    def logout(request:Request,response:Response):
        identity.logout(request.cookies.get(COOKIE,''));response.delete_cookie(COOKIE,path='/');return {'ok':True}
