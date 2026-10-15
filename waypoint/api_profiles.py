"""Provider configuration contains public metadata only; credentials stay in KeyVault."""
import ipaddress
import json
import math
import os
import re
import socket
import asyncio
from datetime import date
from urllib.parse import urlsplit, urlunsplit
from urllib.request import getproxies,proxy_bypass
import httpx
from waypoint.contracts import uid, now
from waypoint.secrets import KeyVault

PRESETS = {
    'openai': {'name': 'OpenAI', 'base_url': 'https://api.openai.com/v1', 'protocol': 'responses', 'json_mode': 'schema', 'key_env': 'WAYPOINT_API_KEY'},
    'deepseek': {'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com/v1', 'protocol': 'chat', 'json_mode': 'object', 'key_env': 'WAYPOINT_DEEPSEEK_API_KEY'},
    'gemini': {'name': 'Gemini', 'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai', 'protocol': 'chat', 'json_mode': 'schema', 'key_env': 'WAYPOINT_GEMINI_API_KEY'},
    'anthropic': {'name': 'Claude', 'base_url': 'https://api.anthropic.com/v1', 'protocol': 'anthropic', 'json_mode': 'schema', 'key_env': 'WAYPOINT_ANTHROPIC_API_KEY'},
    'custom': {'name': '自定义服务商', 'base_url': '', 'protocol': 'chat', 'json_mode': 'schema', 'key_env': 'WAYPOINT_CUSTOM_API_KEY'},
}
ROLES = {'write', 'translate', 'extract', 'complex', 'read'}


def validate_url(value):
    if not isinstance(value, str) or len(value) > 500 or any(c.isspace() for c in value):
        raise ValueError('请填写服务商的 HTTPS 基础接口地址')
    try:
        p = urlsplit(value); host = (p.hostname or '').lower(); port = p.port
        if p.scheme != 'https' or not host or p.username or p.password or p.query or p.fragment:
            raise ValueError()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')): raise ValueError()
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global: raise ValueError('private')
        except ValueError as exc:
            if str(exc) == 'private' or '.' not in host or re.fullmatch(r'[0-9.]+',host) or not re.fullmatch(r'[a-z0-9.-]+', host): raise ValueError()
        if port is not None and not 1 <= port <= 65535: raise ValueError()
        if '\\' in value: raise ValueError()
        return urlunsplit(('https', p.netloc.lower(), p.path.rstrip('/'), '', ''))
    except ValueError: raise ValueError('接口地址须为公开 HTTPS 地址，不含密码、查询参数或本机/内网地址') from None


def binding(profile): return profile['base_url'] + '|' + profile['protocol']


def https_proxy(url):
    """Use the actual HTTPS tunnel, respecting local proxy bypass settings."""
    p=urlsplit(url)
    if proxy_bypass(p.hostname):return None
    proxy=getproxies().get('https') or getproxies().get('all')
    if not proxy:return None
    try:
        parsed=urlsplit(proxy)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.port==0:return None
    except ValueError:return None
    return proxy


async def public_dns(host,proxy):
    # Only a public hostname is sent to the resolver, never an API key or content.
    # Explicitly reuse the same tunnel for verification and the later API request.
    addresses=[]
    try:
        async with httpx.AsyncClient(timeout=15,proxy=proxy,trust_env=False,follow_redirects=False) as client:
            for kind in ('A','AAAA'):
                res=await client.get('https://dns.google/resolve',params={'name':host,'type':kind})
                if res.status_code!=200 or len(res.content)>200000:raise ValueError()
                data=res.json()
                if data.get('Status')!=0 or not any(q.get('name','').rstrip('.').lower()==host.lower() for q in data.get('Question',[])):raise ValueError()
                for answer in data.get('Answer',[]):
                    if answer.get('type') in (1,28):addresses.append(str(ipaddress.ip_address(answer['data'])))
    except (httpx.HTTPError,ValueError,KeyError,TypeError,AttributeError):
        raise ValueError('检测到代理 Fake-IP，但公开 DNS 核对失败；未发送密钥，请检查代理网络后重试') from None
    return addresses


async def check_public_host(url):
    validate_url(url)
    p=urlsplit(url)
    try:
        addresses=await asyncio.to_thread(socket.getaddrinfo,p.hostname,p.port or 443,type=socket.SOCK_STREAM)
    except OSError:raise ValueError('服务商地址无法解析，请核对接口地址和本机网络') from None
    ips=[ipaddress.ip_address(x[4][0]) for x in addresses]
    if ips and all(x.is_global for x in ips):return {}
    # The benchmark range is used by Clash/Mihomo Fake-IP. Ordinary private,
    # loopback, link-local and mixed destinations remain prohibited.
    fake=ipaddress.ip_network('198.18.0.0/15')
    if ips and all(x.version==4 and x in fake for x in ips):
        proxy=https_proxy(url)
        if not proxy:raise ValueError('服务商使用代理 Fake-IP，但没有生效的 HTTPS 代理；请为该域名改用真实 DNS，或配置 HTTPS_PROXY 后重启工作台；未发送密钥')
        public=await public_dns(p.hostname,proxy)
        if not public or any(not ipaddress.ip_address(x).is_global for x in public):
            raise ValueError('服务商公开 DNS 不是公网地址，已阻止发送密钥')
        return {'proxy':proxy,'trust_env':False}
    raise ValueError('服务商地址解析到本机或内网，已阻止发送密钥')


def headers(profile, key):
    if not isinstance(key, str) or not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError('服务端密钥格式不正确，请重新配置')
    if profile['protocol'] == 'anthropic': return {'x-api-key': key, 'anthropic-version': '2023-06-01'}
    return {'Authorization': 'Bearer ' + key}


def resolve_key(profile, vault):
    key = vault.get(profile['id'], binding(profile)) if vault else None
    if not key and profile.get('key_env'): key = os.environ.get(profile['key_env'])
    if not key: raise ValueError('此服务商尚未配置对应接口的密钥；请在设置中保存本机密钥或配置其服务端环境变量')
    return key


def validate_prices(prices):
    if not isinstance(prices, dict) or len(prices) > 100: raise ValueError('模型价格配置不正确')
    for model, quote in prices.items():
        if not isinstance(model, str) or not model or len(model) > 200 or not isinstance(quote, dict) or set(quote) != {'input', 'output', 'date'}:
            raise ValueError('模型价格配置不正确')
        for key in ('input', 'output'):
            n = quote[key]
            if type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1_000_000: raise ValueError('价格须为有效的 USD / 百万 token 数值')
        try: date.fromisoformat(quote['date'])
        except (ValueError, TypeError): raise ValueError('请填写价格核对日期') from None


class ApiProfiles:
    def __init__(self, repo, vault=None): self.repo = repo; self.vault = vault or KeyVault(repo.db.root)
    def public(self, p):
        result = dict(p)
        try:result['has_key'] = self.vault.has(p['id'], binding(p))
        except ValueError:result.update(has_key=False,key_status_error=True)
        result['has_env_key'] = bool(p.get('key_env') and os.environ.get(p['key_env']))
        return result
    def list(self): return [self.public(p) for p in self.repo.list('api_profile')]
    def get(self, id): return self.repo.get(id, 'api_profile')

    def save(self, patch, id=None):
        allowed = {'name', 'vendor', 'protocol', 'base_url', 'json_mode', 'key_env', 'api_key', 'default_model', 'prices', 'token_parameter'}
        if set(patch) - allowed: raise ValueError('未知 API 配置字段')
        with self.repo.db.lock, self.repo.db.conn:
            old = self.get(id) if id else None
            vendor = patch.get('vendor', (old or {}).get('vendor', 'custom'))
            if vendor not in PRESETS: raise ValueError('服务商类型不正确')
            p = dict(old or (PRESETS[vendor] | {'id': uid(), 'vendor': vendor, 'models': [], 'models_checked_at': '', 'default_model': '', 'prices': {}, 'created_at': now(), 'token_parameter': 'max_tokens'}))
            p.update({k: v for k, v in patch.items() if k != 'api_key'})
            if not isinstance(p['name'], str) or not p['name'].strip() or len(p['name']) > 80: raise ValueError('请填写一至八十字的配置名称')
            p['name'] = p['name'].strip(); p['base_url'] = validate_url(p['base_url'])
            if p['protocol'] not in ('responses', 'chat', 'anthropic') or p['json_mode'] not in ('schema', 'object'):
                raise ValueError('接口协议或 JSON 格式不正确')
            if p['vendor']=='deepseek' and urlsplit(p['base_url']).hostname=='api.deepseek.com' and urlsplit(p['base_url']).path in ('','/v1') and p['protocol']!='chat':
                raise ValueError('DeepSeek 官方预设使用兼容 Chat Completions，请选择该协议')
            if p['token_parameter'] not in ('max_tokens', 'max_completion_tokens'): raise ValueError('输出上限参数不正确')
            if not isinstance(p['key_env'], str) or (p['key_env'] and not re.fullmatch(r'WAYPOINT_(?:[A-Z0-9_]+_)?API_KEY', p['key_env'])):
                raise ValueError('环境变量须使用 WAYPOINT_API_KEY 或 WAYPOINT_服务商_API_KEY 格式')
            validate_prices(p['prices'])
            if old and (binding(old) != binding(p) or old.get('key_env') != p['key_env'] or patch.get('api_key')):
                p.update(models=[], models_checked_at='', default_model='', prices={})
            available = {m['id'] for m in p['models']}
            if p['default_model'] and p['default_model'] not in available: raise ValueError('请先读取账户模型列表，再选择默认模型')
            if set(p['prices']) - available: raise ValueError('价格只能关联此配置账户返回的模型')
            if patch.get('api_key'): self.vault.set(p['id'], patch['api_key'], binding(p))
            elif old and old['base_url']==p['base_url'] and urlsplit(p['base_url']).hostname=='api.deepseek.com' and p['vendor']=='deepseek' and old['protocol']=='responses' and p['protocol']=='chat':
                # Repair this known same-endpoint protocol error without asking
                # the owner to reveal or re-enter their saved key.
                key=self.vault.get(p['id'],binding(old))
                if key:
                    self.vault.preserve_encrypted()
                    self.vault.set(p['id'],key,binding(p))
            p['updated_at'] = now(); p.pop('has_key', None); p.pop('has_env_key', None)
            self.repo._put('api_profile', p)
            return self.public(p)

    async def read_models(self, id, transport=None):
        p = self.get(id); validate_url(p['base_url']); key = resolve_key(p, self.vault)
        network=await check_public_host(p['base_url']) if transport is None else {}
        models = {}; params = {'limit': 100} if p['protocol'] == 'anthropic' else {}
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False, transport=transport,**(network or {})) as client:
                for _ in range(20):
                    res = await client.get(p['base_url'] + '/models', headers=headers(p, key), params=params)
                    if res.status_code >= 300: raise ValueError(f'读取模型失败（HTTP {res.status_code}），请检查地址和密钥')
                    if len(res.content) > 2_000_000: raise ValueError('模型列表响应过大')
                    data = res.json(); items = data.get('data')
                    if not isinstance(items, list): raise ValueError('接口未返回兼容的账户模型列表')
                    for item in items:
                        model = item.get('id')
                        if not isinstance(model, str) or not model or len(model) > 200: raise ValueError('模型列表格式不正确')
                        name = item.get('display_name') or item.get('name') or model
                        if not isinstance(name, str) or len(name) > 300: name = model
                        models[model] = {'id': model, 'name': name}
                    if not data.get('has_more'): break
                    cursor = data.get('last_id') or (items[-1].get('id') if items else None)
                    if not cursor or cursor == params.get('after_id'): raise ValueError('模型列表分页不完整，未保存')
                    params.update(after_id=cursor, limit=100)
                else: raise ValueError('模型列表页数过多，未保存不完整结果')
            if not models: raise ValueError('此接口没有返回可用模型，未替换现有列表')
        except httpx.HTTPError: raise ValueError('读取模型的网络请求失败；未生成内容，未改变 API 开关') from None
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError): raise ValueError('接口未返回有效的账户模型列表') from None
        with self.repo.db.lock, self.repo.db.conn:
            current = self.get(id)
            if binding(current) != binding(p) or current.get('updated_at') != p.get('updated_at'):
                raise ValueError('读取期间配置已变化，请重新读取模型')
            current.update(models=list(models.values()), models_checked_at=now())
            current['prices'] = {k: v for k, v in current['prices'].items() if k in models}
            if current['default_model'] not in models: current['default_model'] = ''
            self.repo._put('api_profile', current)
        return self.public(current) | {'message': '已读取账户模型列表；文本生成、结构化输出和图片能力仍需分别验收'}


def validate_routes(repo, routes):
    if not isinstance(routes, dict) or set(routes) - ROLES: raise ValueError('模型分工不正确')
    for role, route in routes.items():
        if not isinstance(route, dict) or set(route) - {'provider', 'profile_id', 'model'} or route.get('provider') not in ('codex', 'api'):
            raise ValueError('环节接入配置不正确')
        if route['provider'] == 'api':
            p = repo.get(route.get('profile_id'), 'api_profile')
            if route.get('model') not in {m['id'] for m in p['models']}: raise ValueError('请从此服务商实际账户模型列表选择环节模型')
