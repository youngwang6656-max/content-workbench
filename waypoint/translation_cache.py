"""Reuse exact translations, without weakening version or rule evidence."""
def cached_translation(repo,snapshot):
    current=snapshot.get('base')
    if not current:return None
    if any(o['status']=='pending' and o['stage']=='backtranslation' for o in repo.list('opinion',task_id=snapshot['task_id'])):return None
    rules=[x['text'] for x in snapshot.get('rules',[])]
    tasks={t['id'] for t in repo.list('task',project_id=snapshot['project_id'])}
    revisions=list(reversed(repo.list('revision')))
    revisions.sort(key=lambda x:x['task_id']!=snapshot['task_id'])
    blocked=set()
    for tr in revisions:
        if tr['task_id'] not in tasks or tr['stage']!='backtranslation' or tr['task_id'] in blocked:continue
        try:
            source=repo.revision(tr['source_revision_id'])
        except (ValueError,KeyError,TypeError):continue
        if source.get('candidate') or not source.get('complete'):continue
        # Staleness caused solely by replacing identical English is expected.
        # Require both the exact text and current applicable rules nonetheless.
        if (source['title'],source['body'])!=(current['title'],current['body']):continue
        # The latest applicable version is authoritative. Never fall back to a
        # superseded translation after a manual correction or an invalid result.
        blocked.add(tr['task_id'])
        valid=not tr.get('candidate') and tr.get('complete') and tr['body'].strip() and not any(x.get('severity','error')=='error' for x in tr.get('issues',[]))
        recorded_rules=tr.get('translation_rules')
        if recorded_rules is None:
            try:
                origin=repo.get(tr['snapshot_id'],'snapshot')
                recorded_rules=[x['text'] for x in origin.get('rules',[])] if origin.get('project_id')==snapshot['project_id'] else None
            except (ValueError,KeyError,TypeError):pass
        valid=valid and recorded_rules==rules and not any(o['stage']=='backtranslation' and o['status']=='pending' for o in repo.list('opinion',task_id=tr['task_id']))
        if not valid:
            if tr['task_id']==snapshot['task_id']:return None
            continue
        return tr
