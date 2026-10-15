"""Brand navigation and reversible merges; creative records keep their IDs."""
import hashlib
import json
from datetime import datetime,timezone
from waypoint.contracts import uid, now

def instant(value):
    try:
        d=datetime.fromisoformat(value)
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError,TypeError,OverflowError):return float('-inf')


class ProjectManagement:
    def active_project(self, id):
        p = self.get(id, 'project')
        if p.get('merged_into'):
            raise ValueError('此品牌已合并，请打开目标品牌')
        return p

    def projects(self,sort='manual'):
        if sort not in ('manual','added','modified'):raise ValueError('请选择添加时间、最新修改或手动排序')
        rows = [p for p in self.list('project') if not p.get('merged_into')]
        activity={p['id']:max((p.get('created_at',''),p.get('updated_at','')),key=instant) for p in rows}
        tasks={t['id']:t['project_id'] for t in self.list('task')}
        for kind in ('task','revision','opinion','approval','material','rule'):
            for d in self.list(kind):
                pid=d.get('project_id') or tasks.get(d.get('task_id'))
                if kind=='approval' and d.get('revision_id'):
                    try:pid=tasks.get(self.revision(d['revision_id'])['task_id'])
                    except ValueError:continue
                if pid in activity:activity[pid]=max((activity[pid],d.get('updated_at',''),d.get('created_at','')),key=instant)
        rows=[p|{'modified_at':activity[p['id']]} for p in rows]
        if sort=='manual':return sorted(rows,key=lambda p:(not p.get('pinned',False),p.get('sort_order',rows.index(p))))
        field='created_at' if sort=='added' else 'modified_at'
        rows.sort(key=lambda p:(instant(p.get(field,'')),p['id']),reverse=True)
        return sorted(rows,key=lambda p:not p.get('pinned',False))

    def update_project(self, id, patch):
        if set(patch) - {'name', 'pinned'}:
            raise ValueError('不允许更新此品牌字段')
        with self.db.lock, self.db.conn:
            p = self.active_project(id)
            if 'name' in patch:
                name = patch['name']
                if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
                    raise ValueError('品牌名称须为一至二百字')
                name = name.strip()
                if name != p['name']:
                    p.setdefault('name_history', []).append({'name': p['name'], 'changed_at': now()})
                    p['name'] = name
            if 'pinned' in patch:
                if type(patch['pinned']) is not bool:
                    raise ValueError('置顶状态不正确')
                p['pinned'] = patch['pinned']
            p['updated_at']=now()
            self._put('project', p)
            return p

    def reorder_projects(self, ids):
        with self.db.lock, self.db.conn:
            rows = self.projects()
            if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids) or len(ids) != len(rows) or set(ids) != {p['id'] for p in rows}:
                raise ValueError('品牌列表已变化，请刷新后排序')
            for i, id in enumerate(ids):
                p = self._get(id, 'project'); p['sort_order'] = i; self._put('project', p)
        return self.projects()

    def _merge_records(self, source, target):
        records = [(kind, json.loads(data)) for kind, data in self.db.conn.execute('SELECT kind,data FROM records ORDER BY rowid')]
        tasks = {d['id'] for k, d in records if k == 'task' and d['project_id'] in (source, target)}
        revisions = {d['id'] for k, d in records if k == 'revision' and d['task_id'] in tasks}
        return [(k, d) for k, d in records if k != 'project_merge' and
                (d['id'] in (source, target) or d.get('project_id') in (source, target) or
                 d.get('task_id') in tasks or d.get('revision_id') in revisions)]

    @staticmethod
    def _merge_fingerprint(records):
        # Sort by ID: restoring records need not preserve SQLite row positions.
        payload = json.dumps(sorted(records, key=lambda x: x[1]['id']), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def preview_project_merge(self, source, target):
        with self.db.lock:
            if source == target: raise ValueError('请选择另一个目标品牌')
            a = self.active_project(source); b = self.active_project(target)
            records = self._merge_records(source, target)
            if any(k in ('job','comment_search_job') and d['status'] in ('running', 'queued') for k, d in records):
                raise ValueError('请先停止两个品牌中正在运行或排队的任务')
            counts = {k: sum(kind == k and d.get('project_id') == source for kind, d in records)
                      for k in ('task', 'material', 'rule')}
            rules = [self.list('rule', project_id=id) for id in (source, target)]
            return {'source': a, 'target': b, 'counts': counts,
                    'source_rules': rules[0][-1]['text'] if rules[0] else '',
                    'target_rules': rules[1][-1]['text'] if rules[1] else '',
                    'fingerprint': self._merge_fingerprint(records)}

    def merge_projects(self, source, target, fingerprint):
        from waypoint.backup import Backup
        with self.db.lock:
            preview = self.preview_project_merge(source, target)
            if preview['fingerprint'] != fingerprint: raise ValueError('品牌内容已发生变化，请重新预览合并')
            before = self._merge_records(source, target)
            original = json.loads(json.dumps(before))
            backup = Backup(self).create_backup(self.db.root / 'backups')
            with self.db.conn:
                a, b = preview['source'], preview['target']
                for kind, d in before:
                    if d.get('project_id') == source:
                        d.setdefault('origin_project', {'id': source, 'name': a['name']})
                        d['project_id'] = target
                    if kind == 'task':
                        d['input_epoch'] += 1
                        d['message'] = '品牌合并后资料与规则已变化，请核对后继续'
                        d['updated_at'] = now(); d['status'] = 'paused'
                    if kind == 'revision': d['stale'] = True
                    self._put(kind, d)
                a['merged_into'] = target; a['merged_at'] = now(); self._put('project', a)
                b.setdefault('merged_brand_history', []).append(preview['source'] | {'merged_at': now()})
                self._put('project', b)
                added = []
                text = '\n\n'.join(f"【{p['name']}原规则】\n{value}" for p, value in
                                   ((b, preview['target_rules']), (a, preview['source_rules'])) if value)
                if text:
                    rule = {'id': uid(), 'project_id': target, 'text': text, 'created_at': now()}
                    self._put('rule', rule); added.append(rule['id'])
                receipt = {'id': uid(), 'source_id': source, 'target_id': target, 'created_at': now(),
                           'status': 'merged', 'before': original, 'added_ids': added,
                           'backup_name': backup.name}
                receipt['after_fingerprint'] = self._merge_fingerprint(self._merge_records(source, target))
                self._put('project_merge', receipt)
                return {k: v for k, v in receipt.items() if k != 'before'}

    def project_management(self, id):
        self.active_project(id)
        return {'merges': [{k: v for k, v in d.items() if k != 'before'} for d in self.list('project_merge', target_id=id) if d['status'] == 'merged']}

    def undo_project_merge(self, id):
        from waypoint.backup import Backup
        with self.db.lock:
            receipt = self._get(id, 'project_merge')
            if receipt['status'] != 'merged': raise ValueError('此合并已经撤销')
            current = self._merge_records(receipt['source_id'], receipt['target_id'])
            if self._merge_fingerprint(current) != receipt['after_fingerprint']:
                raise ValueError('合并后已有新的修改，为保留新内容不能直接撤销')
            Backup(self).create_backup(self.db.root / 'backups')
            with self.db.conn:
                for kind, data in receipt['before']: self._put(kind, data)
                for added in receipt['added_ids']: self.db.conn.execute('DELETE FROM records WHERE id=?', (added,))
                receipt['status'] = 'undone'; receipt['undone_at'] = now(); self._put('project_merge', receipt)
            return {'ok': True, 'project_id': receipt['source_id']}
