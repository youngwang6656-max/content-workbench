"""Upload-triggered reading through the user's existing model configuration.

The original file and local index exist before this worker starts. Model output
is adopted only through the same page-coverage checks as manual batch reading.
"""
import asyncio

from waypoint.contracts import now
from waypoint.material_batch import read_next


class AutoMaterialProcessor:
    def __init__(self, engine):
        self.engine = engine
        self.repo = engine.repo
        self.tasks = {}
        self.limit = asyncio.Semaphore(1)
        self.blocked_reason = None

    def _state(self, material_id, status, *, covered=None, total=None, message=''):
        with self.repo.db.lock, self.repo.db.conn:
            material = self.repo.get(material_id, 'material')
            state = material.get('auto_processing', {})
            state.update(status=status, message=str(message)[:600], updated_at=now())
            if covered is not None:
                state['covered'] = covered
            if total is not None:
                state['total_units'] = total
            material['auto_processing'] = state
            self.repo._put('material', material)

    def enqueue(self, material_id):
        material = self.repo.get(material_id, 'material')
        if material.get('archived'):
            raise ValueError('已归档资料不能自动处理')
        existing = self.tasks.get(material_id)
        if existing and not existing.done():
            return
        self._state(material_id, 'queued', covered=0,
                    total=len(material.get('units') or []), message='已保存原文件，等待模型读取')
        task = asyncio.create_task(self._run(material_id, material['project_id']))
        self.tasks[material_id] = task
        task.add_done_callback(lambda _: self._finished(material_id))

    def _finished(self, material_id):
        self.tasks.pop(material_id, None)
        if not self.tasks:
            # A later explicit upload is a new attempt after the user may have
            # repaired login, quota, price or budget settings.
            self.blocked_reason = None

    def recover(self):
        """An interrupted process must not silently repeat a chargeable call."""
        for material in self.repo.list('material'):
            if material.get('auto_processing', {}).get('status') in ('queued', 'running', 'working'):
                self._state(material['id'], 'paused', message='服务曾中断；结果和费用可能未知，请先核对分析历史，再手动继续')

    async def _run(self, material_id, project_id):
        async with self.limit:
            try:
                if self.blocked_reason:
                    self._state(material_id, 'paused', message=self.blocked_reason)
                    return
                self._state(material_id, 'running', message='正在逐页读取并整理可用依据')
                max_steps = max(1, len(self.repo.get(material_id, 'material').get('units') or [])) * 2 + 1
                for _ in range(max_steps):
                    result = await read_next(self.engine, material_id, {'project_id': project_id})
                    status = result['status']
                    if status == 'complete':
                        self._state(material_id, 'running', covered=result['covered'],
                                    total=result['total_units'], message='逐页读取完成，检查是否需要公开来源考证')
                        from waypoint.material_public_check import check_public_sources
                        await check_public_sources(self.engine, material_id)
                    self._state(material_id, status, covered=result['covered'],
                                total=result['total_units'], message=result.get('message', ''))
                    if status != 'working':
                        return
                raise ValueError('逐页处理未能收敛，已暂停；请查看分析历史')
            except asyncio.CancelledError:
                self._state(material_id, 'paused', message='服务已停止；在途调用的结果和费用可能未知，请先核对分析历史。原文件仍保留')
                raise
            except Exception as exc:
                # No automatic retry or paid fallback. The local index stays usable.
                message=str(exc) or '模型读取已暂停，请检查连接'
                if any(word in message for word in ('额度', '连接', '登录', 'API 未启用', 'API 配置', 'API 密钥',
                                                     '服务商', '预算', '价格', '未知费用', '订阅', '进程断开')):
                    self.blocked_reason=message
                self._state(material_id, 'paused', message=message)

    async def wait(self):
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)

    async def close(self):
        for task in list(self.tasks.values()):
            if not task.done():
                task.cancel()
        await self.wait()
