from pathlib import Path
import io,hashlib,zipfile
from waypoint.contracts import uid,now
class Materials:
    def __init__(self,repo):self.repo=repo
    def add_text(self,project_id,name,text,kind='fact',url='',published_at='',trust='unverified',**extra):
        if not isinstance(text,str) or len(text)>210000 or not isinstance(name,str) or not isinstance(url,str):raise ValueError('资料文字格式错误或过长')
        if not text.strip() and url:extra.setdefault('extraction','needs_link')
        if project_id is not None:self.repo.active_project(project_id)
        if kind not in ['fact','strategy','sample','thread','attachment']:raise ValueError('资料类型错误')
        if trust not in ['unverified','user_confirmed']:raise ValueError('来源状态错误')
        d={'id':uid(),'project_id':project_id,'name':name[:200],'text':text,'kind':kind,'url':url,
           'published_at':published_at,'trust':trust,'extraction':'text','archived':False,'created_at':now(),**extra}
        with self.repo.db.lock,self.repo.db.conn:
            self.repo._put('material',d)
            if project_id is None and kind in ('fact','strategy'):self._invalidate(None,'全局资料已更新，请核对依据')
        return d
    def import_bytes(self,project_id,name,data):
        if project_id is not None:self.repo.active_project(project_id)
        suffix=Path(name).suffix.lower()
        from waypoint.document_text import SUPPORTED,extract
        if suffix not in SUPPORTED:raise ValueError('支持文本、PDF、Word、PPT、Excel、CSV 与常用图片')
        if len(data)>20_000_000:raise ValueError('单个文件上限为二十 MB')
        try:units,warnings,extraction=extract(data,suffix)
        except ValueError:raise
        except Exception:raise ValueError('资料无法解析，请检查文件是否损坏/加密，或另存为 PDF 后导入') from None
        text='\n\n'.join('['+u['label']+']\n'+u['text'] for u in units)
        filename=uid()+suffix;path=self.repo.db.root/'attachments'/filename;path.write_bytes(data)
        return self.add_text(project_id,Path(name).name,text,kind='attachment',path=filename,extraction=extraction,sha256=hashlib.sha256(data).hexdigest(),units=units,extraction_warnings=warnings)
    def archive(self,id):
        with self.repo.db.lock,self.repo.db.conn:
            d=self.repo.get(id,'material');d['archived']=True;d['updated_at']=now();self.repo._put('material',d)
            self._invalidate(d['project_id'],'资料已归档，请核对依据')
        return d
    def archive_batch(self,ids,project_id):
        if not isinstance(ids,list) or not 1<=len(ids)<=200 or any(not isinstance(id,str) for id in ids):raise ValueError('请一次选择一至二百份资料')
        with self.repo.db.lock,self.repo.db.conn:
            if project_id is not None:self.repo.active_project(project_id)
            rows=[self.repo.get(id,'material') for id in dict.fromkeys(ids)]
            if any(d['project_id']!=project_id or d.get('reading_translation') for d in rows):raise ValueError('资料不在本次选择范围内')
            changed=[d for d in rows if not d.get('archived')]
            for d in changed:
                d['archived']=True;d['updated_at']=now();self.repo._put('material',d)
            if changed:self._invalidate(project_id,'资料已批量归档，请核对依据')
        return {'archived_ids':[d['id'] for d in changed],'count':len(changed)}
    def _invalidate(self,project_id,message):
        for t in self.repo.list('task',**({'project_id':project_id} if project_id is not None else {})):
            self.repo.set_task_state(t['id'],input_epoch=t['input_epoch']+1,message=message)
            for rid in t['active'].values():
                with self.repo.db.lock,self.repo.db.conn:self.repo._stale(rid)
