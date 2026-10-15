ROLE_EFFORTS={'write':'high','read':'high','complex':'high','extract':'medium','translate':'low'}
EFFORTS=('none','minimal','low','medium','high','xhigh')
def validate_efforts(value):
    if not isinstance(value,dict) or set(value)-set(ROLE_EFFORTS) or any(x not in EFFORTS for x in value.values()):
        raise ValueError('环节推理强度配置不正确')
def choose_model(job_kind,report,settings):
    model=settings['model_roles'].get(job_kind)
    if not model:raise ValueError('请在设置中从账户可用模型里配置本环节模型')
    available={m.get('model',m.get('id')):m for m in report['models'] if not m.get('hidden')}
    if model not in available:raise ValueError('此环节配置的模型目前不可用，请重新选择')
    supported=available[model].get('supportedReasoningEfforts') or []
    values={e.get('reasoningEffort') if isinstance(e,dict) else e for e in supported}
    configured=settings.get('role_efforts',{});effort=configured.get(job_kind,ROLE_EFFORTS.get(job_kind,'high'))
    if supported and effort not in values:
        if job_kind not in configured and job_kind in ('translate','extract'):
            effort=next((x for x in EFFORTS if x in values),None)
        else:raise ValueError('此模型不支持所选推理强度（'+('高' if effort=='high' else effort)+'），请调整该环节强度或模型')
    if effort is None:raise ValueError('账户模型没有可用推理强度，请重新同步模型目录')
    return {'model':model,'effort':effort,'provider':'codex'}
