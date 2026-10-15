"""One bounded, resumable step of explicitly requested reading and adoption."""
import asyncio
from waypoint.material_reading import active,hydrate,describe,units_for,analyze,adopt,covered_by_analysis


def next_range(units,remaining):
    start=remaining[0];end=start-1;characters=images=0
    for number in remaining:
        if number!=end+1 or number-start>=8:break
        unit=units[number-1];text_size=len(unit['text'])
        # PPTX pictures on one slide are combined into one bounded slide preview.
        image_size=1 if unit.get('visual') else 0
        if characters+text_size>45000 or images+image_size>8:break
        characters+=text_size;images+=image_size;end=number
    if end<start:raise ValueError('此页/段超过单次读取限制，请拆分资料或补充文字；未调用模型')
    return start,end


async def read_next(engine,id,data):
    if 'project_id' not in data:raise ValueError('请明确资料所属范围')
    if not hasattr(engine,'material_batch_locks'):engine.material_batch_locks={}
    lock=engine.material_batch_locks.setdefault(id,asyncio.Lock())
    if lock.locked():raise ValueError('此资料正在批量读取，请等待当前操作结束')
    async with lock:
        repo=engine.repo;m=active(repo,id)
        if m['project_id']!=data['project_id']:raise ValueError('资料不在本次选择范围内')
        m=hydrate(repo,m);info=describe(m)
        def pending(current_material,current):
            history=[a for a in current_material.get('analysis_history',[]) if a.get('source_fingerprint')==current['fingerprint']]
            attempted={n for a in history if 'reading_issues_zh' in a for n in range(a['start'],a['end']+1)}
            return [n for n in current['remaining'] if n not in attempted]
        def progress(message='',analysis=None,reused=False):
            material=hydrate(repo,active(repo,id));current=describe(material)
            remaining=current['remaining'];next_pages=pending(material,current)
            reusable=any(covered_by_analysis(a) and a.get('source_fingerprint')==current['fingerprint']
                         and any(n in remaining for n in range(a['start'],a['end']+1))
                         for a in material.get('analysis_history',[]))
            if not remaining:status='complete'
            elif next_pages or reusable:status='working'
            else:
                status='needs_attention'
                pages=', '.join(map(str,remaining[:16]))+('…' if len(remaining)>16 else '')
                message=f'已尝试全文件，仍有 {len(remaining)} 页/段未通过读取核对（{pages}）。原文件与分析历史已保留，请按范围精读或补充清晰资料。'
            return {'status':status,
                    'covered':len(current['covered']),'total_units':len(current['units']),
                    'message':message,'analysis_id':analysis['id'] if analysis else None,'reused':reused}
        if not info['remaining']:return progress()
        # A saved complete analysis can be adopted without another model call.
        result=next((a for a in reversed(m.get('analysis_history',[]))
                     if covered_by_analysis(a) and a['source_fingerprint']==info['fingerprint']
                     and any(n in info['remaining'] for n in range(a['start'],a['end']+1))),None)
        reused=result is not None
        if not result:
            remaining=pending(m,info)
            if not remaining:return progress()
            start,end=next_range(units_for(m),remaining)
            result=await analyze(engine,id,{'start':start,'end':end,'include_images':True,'source_fingerprint':info['fingerprint']})
        if not result['complete']:
            return progress('；'.join(result.get('reading_issues_zh',[])) or '本段读取不完整，继续处理其余页/段',result,reused)
        # Brand merges may move this record while its model call is in flight.
        # Scope validation and adoption share the repository lock so that a late
        # result stays history rather than becoming evidence in a new brand.
        with repo.db.lock,repo.db.conn:
            if active(repo,id)['project_id']!=data['project_id']:
                raise ValueError('资料所属范围已变化，请在新品牌核对；原文与分析历史已保留，未自动采纳')
            adopt(repo,id,result['id'])
        return progress(analysis=result,reused=reused)
