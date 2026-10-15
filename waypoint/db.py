import sqlite3, threading
from pathlib import Path
class Database:
    def __init__(self,data_dir):
        self.root=Path(data_dir); self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'attachments').mkdir(exist_ok=True)
        self.lock=threading.RLock(); self.path=self.root/'waypoint.sqlite'
        self.conn=sqlite3.connect(self.path,check_same_thread=False,timeout=20)
        self.conn.execute('PRAGMA journal_mode=WAL'); self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.executescript('''CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS records_kind ON records(kind);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO metadata VALUES('schema','1');''')
