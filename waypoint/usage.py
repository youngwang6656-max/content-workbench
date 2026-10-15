"""Shared mode decisions and cached status. Status reads never contact a model."""
from waypoint.api_profiles import ApiProfiles
from waypoint.budget import Budget
from waypoint.providers.api import ApiProvider
from waypoint.providers.codex import require_subscription_quota,SubscriptionQuotaError
from waypoint.routing import choose_model
import re


def validate_configs(repo,settings,*,validate_models=False):
    configs=settings['usage_configs']
    if not isinstance(configs,list) or len(configs)>30:raise ValueError('最多保存三十份模型配置')
    ids=set()
    for c in configs:
        if not isinstance(c,dict) or set(c)-{'id','name','provider','model_roles','profile_id','model','api_role_models','role_efforts'}:raise ValueError('模型配置格式不正确')
        from waypoint.routing import validate_efforts
        validate_efforts(c.get('role_efforts',{}))
        if not isinstance(c.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',c['id']) or c['id'] in ids:raise ValueError('配置标识不正确或重复')
        ids.add(c['id'])
        if not isinstance(c.get('name'),str) or not 1<=len(c['name'].strip())<=80:raise ValueError('请填写配置名称，最多八十字')
        if c.get('provider') not in ('codex','api'):raise ValueError('请选择订阅或 API 模式')
        from waypoint.api_profiles import ROLES,validate_routes
        models=c.get('model_roles',{})
        if not isinstance(models,dict) or set(models)-ROLES or any(not isinstance(v,str) or len(v)>200 for v in models.values()):raise ValueError('订阅模型分工不正确')
        routes=c.get('api_role_models',{})
        if not isinstance(routes,dict) or set(routes)-ROLES:raise ValueError('API 模型分工不正确')
        if c['provider']=='api':
            p=repo.get(c.get('profile_id'),'api_profile')
            model=c.get('model','')
            if not isinstance(model,str):raise ValueError('API 模型不正确')
            if validate_models and model and model not in {m['id'] for m in p['models']}:raise ValueError('请从服务商实际账户列表选择 API 模型')
            if validate_models:validate_routes(repo,routes)
            if any(route.get('provider')!='api' or route.get('profile_id')!=p['id'] for route in routes.values()):raise ValueError('环节须使用本配置指定的 API 服务商')
    for key in ('active_usage_config_id','auto_default_config_id','fallback_usage_config_id'):
        if settings[key] and settings[key] not in ids:raise ValueError('当前或备用配置已不存在，请先重新选择')
    if configs and not settings['active_usage_config_id']:raise ValueError('请选择当前模型配置')
    if configs and settings['switch_policy']=='auto':
        primary=settings['auto_default_config_id'] or settings['active_usage_config_id']
        default=next(c for c in configs if c['id']==primary)
        fallback=next((c for c in configs if c['id']==settings['fallback_usage_config_id']),None)
        if default['provider']!='codex' or not fallback or fallback['provider']!='api':raise ValueError('自动模式请选择订阅默认配置及 API 备用配置')


def config_settings(settings,id):
    config=next((c for c in settings['usage_configs'] if c['id']==id),None)
    if not config:return settings
    return settings|{'usage_mode':config['provider'],'provider':config['provider'],
                     'role_efforts':config.get('role_efforts',{}),
                     'model_roles':config.get('model_roles',{}),'api_role_models':config.get('api_role_models',{}),
                     'api_default_profile_id':config.get('profile_id',''),'api_default_model':config.get('model',''),
                     '_config_id':config['id'],'_config_name':config['name']}


def threshold_window(settings,report):
    quota=report.get('quota') or {};limits=(quota.get('rateLimitsByLimitId') or {}).get('codex') or quota.get('rateLimits') or {}
    for key in ('primary','secondary'):
        window=limits.get(key) or {}
        if window.get('windowDurationMins')==300 and type(window.get('usedPercent')) in (int,float):return window
    return {}


def switch_reason(settings,report):
    window=threshold_window(settings,report)
    if window and window['usedPercent']>=settings['auto_used_threshold']:
        return f"订阅 5 小时额度剩余 {max(0,100-window['usedPercent']):g}%，达到 {100-settings['auto_used_threshold']:g}% 切换阈值"
    return '订阅额度不足'


def resolve_settings(settings,report,role='write'):
    primary=settings['auto_default_config_id'] if settings['switch_policy']=='auto' else settings['active_usage_config_id']
    selected=config_settings(settings,primary or settings['active_usage_config_id'])
    kind,switched=mode_decision(selected,report,role)
    if switched:selected=config_settings(settings,settings['fallback_usage_config_id'])
    return selected,kind,switched


def mode_decision(settings,report,role='write'):
    explicit=bool(settings['usage_mode'])
    if settings['switch_policy']=='auto':
        if report.get('auth_state')!='chatgpt':raise ValueError(report.get('message') or '请先通过官方 ChatGPT 登录；自动切换仅处理已核实的订阅额度不足')
        try:require_subscription_quota(report.get('quota'),unavailable_message=report.get('message'))
        except SubscriptionQuotaError as exc:
            if not exc.exhausted:raise
            return 'api',True
        window=threshold_window(settings,report)
        if window and window['usedPercent']>=settings['auto_used_threshold']:return 'api',True
        return 'codex',False
    return (settings['usage_mode'] if explicit else settings['role_routes'].get(role,{}).get('provider',settings['provider'])),False


def api_choice(settings,profiles,role='write'):
    if settings['usage_mode'] or settings['switch_policy']=='auto':
        route=settings['api_role_models'].get(role,{})
        if route.get('profile_id')!=settings['api_default_profile_id']:route={}
    else:route=settings['role_routes'].get(role,{})
    id=route.get('profile_id') or settings['api_default_profile_id']
    p=profiles.get(id) if id else None
    model=route.get('model') or settings['api_default_model'] or (p['default_model'] if p else settings['api_model'])
    return p,model


def usage_status(repo):
    s=repo.settings();profiles=ApiProfiles(repo)
    try:report=repo.get('connection','connection')
    except ValueError:report={}
    status={'switch_policy':s['switch_policy'],'usage_mode':s['usage_mode'] or s['provider'],
            'subscription_auth_state':report.get('auth_state','unverified'),
            'effective_provider':None,'provider_name':'','model':'','model_name':'','ready':False,
            'switched':False,'message':'','checked_at':report.get('checked_at'),
            'legacy_routes':not s['usage_mode'] and bool(s['role_routes']),
            'notice':'每次调用前再检查；API 文本可用不代表截图或联网搜索可用。'}
    try:
        s,kind,switched=resolve_settings(s,report)
        status.update(effective_provider=kind,switched=switched,usage_mode=s['usage_mode'] or s['provider'])
        status.update(config_id=s.get('_config_id',''),config_name=s.get('_config_name',''))
        if kind=='api':
            p,model=api_choice(s,profiles)
            status.update(provider_name=p['name'] if p else 'OpenAI API',model=model,
                          model_name=next((m['name'] for m in p['models'] if m['id']==model),model) if p else model)
            if not model:raise ValueError('尚未选择 API 模型，请在使用模式中选择')
            provider=ApiProvider(Budget(repo),s,p,profiles.vault)
            cap,*_=provider.configuration({'model':model,'prompt':'','schema':{},'attachments':[]})
            public=profiles.public(p) if p else {}
            if p and not (public.get('has_key') or public.get('has_env_key')):raise ValueError('尚未配置本机 API 密钥')
            if not p:
                import os
                if not os.environ.get('WAYPOINT_API_KEY'):raise ValueError('尚未配置旧版 API 密钥')
            b=Budget(repo).summary()
            if b['unknown']:raise ValueError('存在待核实费用，已暂停 API')
            if b['used_microusd']+b['reserved_microusd']+cap>b['stop_microusd']:raise ValueError('预算余量不足，请检查停止线与本次输出上限')
            status.update(ready=True,message=switch_reason(s,report)+'，已选择 '+s.get('_config_name','API')+'；按用量计费' if switched else 'API 文本已配置；按用量计费')
        else:
            status['provider_name']='ChatGPT '+str(report.get('plan') or '订阅')
            status['model']=s['model_roles'].get('write','');status['model_name']=status['model']
            if report.get('auth_state')!='chatgpt':raise ValueError(report.get('message') or '官方订阅尚未验证，请检查连接')
            require_subscription_quota(report.get('quota'),unavailable_message=report.get('message'))
            choose_model('write',report,s)
            status.update(ready=True,message='使用官方订阅额度 · 按环节配置推理强度；不使用 credits')
    except ValueError as exc:status['message']=(switch_reason(s,report)+'；' if status['switched'] else '')+str(exc)
    jobs=[j for j in repo.list('job') if j['status']=='running' and j.get('model')]
    if jobs:
        j=jobs[-1];status['active_call']={'model':j['model'],'provider':j.get('provider_kind'),
                                         'provider_name':j.get('provider_name'),'config_name':j.get('config_name'),'stage':j.get('stage')}
    return status
