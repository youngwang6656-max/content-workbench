"""Read-only workflow summaries; a finished model call is not final approval."""


def _valid(revision):
    return bool(revision and revision.get('complete') and not revision.get('stale') and not revision.get('candidate'))


def task_view(repo, task):
    result = dict(task, final_stage='english' if task['kind'] in ('post', 'comment') else 'cb',
                  checkpoint_stage=task.get('checkpoint_stage', task['target_stage']))
    if task.get('abandoned') or task.get('retired'):
        return dict(result, workflow_phase='abandoned')
    live = any(j['status'] in ('running', 'queued') for j in repo.list('job', task_id=task['id']))
    if live:
        return dict(result, workflow_phase='working')
    if task['kind'] == 'post' and not task.get('post_group_id'):
        children = [t for t in repo.list('task', post_group_id=task['id'])
                    if not t.get('abandoned') and not t.get('retired') and t.get('group_epoch') == task['input_epoch']]
        if children:
            phases = [task_view(repo, child)['workflow_phase'] for child in children]
            result['final_counts'] = {'total':len(phases), 'passed':phases.count('finished'),
                                     'english_ready':phases.count('final_ready') + phases.count('finished')}
            phase = phases[0] if len(set(phases)) == 1 else ('working' if 'working' in phases else 'mixed')
            return dict(result, workflow_phase=phase)
    active = task['active'].get(task['target_stage'])
    revision = repo.revision(active) if active else None
    if not _valid(revision):
        return dict(result, workflow_phase='blocked' if task['status'] in ('paused','failed','interrupted') else 'not_started')
    if any(i.get('severity','error')=='error' for i in revision.get('issues',[])):
        return dict(result, workflow_phase='blocked')
    if any(o['status']=='pending' for o in repo.list('opinion',task_id=task['id'])):
        return dict(result, workflow_phase='blocked')
    if task['kind'] in ('post','comment') and task['target_stage'] != 'english':
        return dict(result, workflow_phase='checkpoint_ready')
    if task['target_stage'] == 'english':
        translation = task['active'].get('backtranslation')
        tr = repo.revision(translation) if translation else None
        if not _valid(tr) or tr.get('source_revision_id') != active:
            return dict(result, workflow_phase='blocked')
    passed = any(a.get('simulation_pass') for a in repo.approvals(active))
    return dict(result, workflow_phase='finished' if passed else ('final_ready' if task['kind'] in ('post','comment') else 'standalone_ready'))
