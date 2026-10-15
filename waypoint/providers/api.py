import asyncio
import json
import math
from datetime import date,datetime,timezone
import httpx
from waypoint.api_profiles import resolve_key, headers, validate_url,check_public_host
from waypoint.providers.api_protocols import payload, decode


class ApiProvider:
    kind = 'api'
    def __init__(self, budget, settings, profile=None, vault=None, *, transport=None):
        self.budget = budget; self.settings = settings; self.profile = profile; self.vault = vault
        self.transport = transport; self.running = {}

    def _profile(self, request):
        if self.profile is not None: return self.profile
        s = self.settings
        return {'id': 'legacy-openai', 'name': '旧版 OpenAI API', 'protocol': 'responses', 'base_url': 'https://api.openai.com/v1',
                'key_env': 'WAYPOINT_API_KEY', 'default_model': s['api_model'],
                'prices': {s['api_model']: {'input': s['api_input_rate'], 'output': s['api_output_rate'], 'date': s['price_date']}}}

    def configuration(self, request):
        s = self.settings
        if not s['api_enabled']: raise ValueError('API 未启用，未发生付费调用；请在设置中明确启用')
        if request.get('attachments'): raise ValueError('付费图片费用尚未验证，请用订阅图片能力或补充文字')
        p = self._profile(request); validate_url(p['base_url'])
        if p['protocol'] not in ('responses', 'chat', 'anthropic'): raise ValueError('接口协议不正确')
        model = request.get('model') or p.get('default_model')
        if not model: raise ValueError('请先选择并核对 API 模型')
        if self.profile and model not in {m['id'] for m in p.get('models', [])}:
            raise ValueError('此模型不在已读取的账户列表中，请重新读取并选择模型')
        if self.profile:
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(p['models_checked_at'])).total_seconds()
                if not 0<=age<=86400:raise ValueError()
            except (ValueError,TypeError,KeyError):raise ValueError('账户模型目录已过期，请重新读取模型（不生成内容）') from None
        quote = p.get('prices', {}).get(model) or {}
        try:
            rates = [quote['input'], quote['output']]
            if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in rates): raise ValueError()
            age = (date.today() - date.fromisoformat(quote['date'])).days
            if not 0 <= age <= 31: raise ValueError()
        except (ValueError, TypeError, KeyError): raise ValueError('请为此模型核对当期 USD 文本价格及日期；未知或过期价格不能启动付费调用') from None
        limit = s['max_output_tokens']
        if type(limit) is not int or not 100 <= limit <= 16000: raise ValueError('输出上限不正确')
        # USD/million tokens equals microUSD/token. Reserve UTF-8 bytes plus overhead.
        n = len(request['prompt'].encode()) + len(json.dumps(request['schema'], ensure_ascii=False).encode()) * 2 + 8192
        return math.ceil(n * rates[0] + limit * rates[1]), rates, p, model

    def preflight(self,request):
        cap,rates,p,model=self.configuration(request)
        key=resolve_key(p,self.vault);headers(p,key)
        return cap,rates,p,key,model

    async def generate(self, request):
        cap, rates, profile, key, model = self.preflight(request)
        suffix, body = payload(profile, request | {'model': model}, self.settings['max_output_tokens'])
        network=await check_public_host(profile['base_url']) if self.transport is None else {}
        reservation = self.budget.reserve(request.get('invocation_id', request['job_id']), cap)
        reservation.update(api_profile_id=profile['id'], api_profile_name=profile['name'], model=model,
                           billing_basis='confirmed_text_rates', input_rate=rates[0], output_rate=rates[1], price_date=profile['prices'][model]['date'])
        self.budget.repo.put('budget', reservation)
        self.running[request['job_id']] = asyncio.current_task(); settled = False
        try:
            try:
                async with httpx.AsyncClient(timeout=240, follow_redirects=False, transport=self.transport,**(network or {})) as client:
                    res = await client.post(profile['base_url'] + suffix, headers=headers(profile, key), json=body)
                if res.status_code >= 300: raise ValueError(f"{profile['name']} API 请求失败（HTTP {res.status_code}）；未自动重试，费用保留待核实")
                if len(res.content) > 2_000_000: raise ValueError('API 返回过大，费用保留待核实')
                data = res.json()
                text, usage, complete = decode(profile['protocol'], data)
            except httpx.HTTPError: raise ValueError('API 网络请求失败；未自动重试，费用保留待核实') from None
            except (TypeError, KeyError, AttributeError, json.JSONDecodeError): raise ValueError('API 返回格式不兼容，费用保留待核实') from None
            actual = math.ceil(usage['input_tokens'] * rates[0] + usage['output_tokens'] * rates[1]) if all(usage[k] is not None for k in ('input_tokens', 'output_tokens')) else None
            self.budget.settle(reservation['id'], actual); settled = True
            if actual is None: raise ValueError('API 未返回可核实的文本用量，已暂停后续付费调用，请核对账单')
            if not complete: raise ValueError('API 返回未完成结果；已按返回用量记录，未自动重试，请检查输出上限与协议')
            yield {'kind': 'completed', 'text': text, 'usage': usage | {'api_profile_id': profile['id'], 'model': model}}
        finally:
            if not settled: self.budget.settle(reservation['id'], None)
            self.running.pop(request['job_id'], None)

    async def interrupt(self, job_id):
        if job_id in self.running: self.running[job_id].cancel()
