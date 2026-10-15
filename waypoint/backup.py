import hashlib,json,sqlite3,tempfile,zipfile,shutil
from pathlib import Path
from waypoint.contracts import uid,now

class Backup:
    def __init__(self,repo):self.repo=repo
    def create_backup(self,destination:Path):
        destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
        out=destination/('waypoint_'+uid()+'.zip')
        with self.repo.db.lock,tempfile.TemporaryDirectory() as scratch:
            db=Path(scratch)/'waypoint.sqlite';con=sqlite3.connect(db)
            self.repo.db.conn.backup(con);con.close()
            files={'waypoint.sqlite':db}
            files.update({'attachments/'+p.name:p for p in (self.repo.db.root/'attachments').iterdir() if p.is_file() and not p.is_symlink()})
            manifest={'format':1,'created_at':now(),'files':{name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in files.items()}}
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json',json.dumps(manifest))
                for name,p in files.items():z.write(p,name)
        return out
    def restore_backup(self,archive:Path):
        with self.repo.db.lock:
            if any(j['status'] in ['running','queued'] for j in self.repo.list('job')):raise ValueError('请先停止所有正在运行或排队的任务')
            if any(j['status'] in ('running','queued') for j in self.repo.list('comment_search_job')):raise ValueError('请先停止后台原帖搜索，再恢复备份')
            if any(m.get('auto_processing',{}).get('status') in ('running','queued','working') for m in self.repo.list('material')):raise ValueError('请先停止资料读取，再恢复备份')
            with tempfile.TemporaryDirectory(dir=self.repo.db.root) as tmp:
                root=Path(tmp)
                try:
                    with zipfile.ZipFile(archive) as z:
                        names=z.namelist()
                        if len(names)!=len(set(names)) or sum(i.file_size for i in z.infolist())>200_000_000:raise ValueError()
                        if any(n not in ['manifest.json','waypoint.sqlite'] and (not n.startswith('attachments/') or len(Path(n).parts)!=2 or '..' in Path(n).parts or '\\' in n) for n in names):raise ValueError()
                        manifest=json.loads(z.read('manifest.json'))
                        if manifest['format']!=1 or set(manifest['files'])!=set(names)-{'manifest.json'}:raise ValueError()
                        for n,digest in manifest['files'].items():
                            data=z.read(n)
                            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError()
                            dest=root/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                    source=sqlite3.connect(root/'waypoint.sqlite')
                    if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or source.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0]!='1':raise ValueError()
                    for row in source.execute('SELECT id,kind,data FROM records'):
                        record=json.loads(row[2])
                        if not isinstance(record,dict) or record.get('id')!=row[0]:raise ValueError()
                        if row[1]=='material' and record.get('path') and (Path(record['path']).name!=record['path'] or '\\' in record['path']):raise ValueError()
                except Exception as exc:
                    if 'source' in locals():source.close()
                    raise ValueError('备份无效、损坏或版本不兼容；当前资料未修改') from exc
                # Cash expenditure cannot be rolled back with creative content.
                for current_entry in self.repo.list('budget'):
                    found=source.execute("SELECT data FROM records WHERE id=? AND kind='budget'",(current_entry['id'],)).fetchone()
                    old_entry=json.loads(found[0]) if found else {}
                    merged=current_entry.copy()
                    amounts=[x.get('actual') for x in [old_entry,current_entry] if x.get('actual') is not None]
                    merged['actual']=max(amounts) if amounts else None
                    merged['reserved']=max(old_entry.get('reserved',0),current_entry.get('reserved',0))
                    if 'unknown' in [old_entry.get('state'),current_entry['state']]:merged['state']='unknown'
                    elif amounts:merged['state']='settled'
                    source.execute("INSERT INTO records VALUES(?,'budget',?) ON CONFLICT(id) DO UPDATE SET kind='budget',data=excluded.data",(merged['id'],json.dumps(merged,ensure_ascii=False)))
                restored_settings=source.execute("SELECT data FROM records WHERE id='settings' AND kind='settings'").fetchone()
                if restored_settings:
                    settings=json.loads(restored_settings[0]);settings.update(api_enabled=False,provider='codex',usage_mode='codex',switch_policy='manual')
                    subscription=next((c for c in settings.get('usage_configs',[]) if c.get('provider')=='codex'),None)
                    if subscription:settings.update(active_usage_config_id=subscription['id'],auto_default_config_id=subscription['id'])
                    source.execute("UPDATE records SET data=? WHERE id='settings'",(json.dumps(settings),))
                source.commit()
                self.create_backup(self.repo.db.root/'rollback')
                old=self.repo.db.root/('attachments_before_'+uid());current=self.repo.db.root/'attachments'
                (root/'attachments').mkdir(exist_ok=True)
                try:
                    current.rename(old);(root/'attachments').rename(current)
                    source.backup(self.repo.db.conn)
                except Exception:
                    if current.exists():shutil.rmtree(current)
                    if old.exists():old.rename(current)
                    raise
                finally:source.close()
                shutil.rmtree(old)
