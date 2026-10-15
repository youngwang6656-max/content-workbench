"""Quota fixtures verify the safety gate, not real Plus generation."""
import asyncio
import pytest
from waypoint.providers.codex import CodexProvider


@pytest.mark.parametrize('quota', [
    {'ordinaryUsageAllowed': False, 'rateLimits': {'primary': {'usedPercent': 100}, 'credits': {'hasCredits': True, 'balance': '10'}}},
    {'rateLimits': {'primary': {'usedPercent': 100}}},
    {'rateLimits': {'primary': {'usedPercent': 5}, 'secondary': {'usedPercent': 100}}},
    {'rateLimits': {'primary': {'usedPercent': 1}}, 'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 100}}}},
    {'rateLimits': {'primary': {'usedPercent': 1}, 'spendControlReached': True}},
    None,
    {},
    ValueError('quota endpoint unavailable'),
])
def test_generation_stops_before_thread_when_subscription_not_available(tmp_path, quota):
    class QuotaProvider(CodexProvider):
        async def start(self): pass
        async def call(self, method, params=None, ready=True):
            if method == 'account/read':
                return {'account': {'type': 'chatgpt', 'planType': 'plus'}}
            if method == 'account/rateLimits/read':
                if isinstance(quota, Exception): raise quota
                return quota
            raise AssertionError('Generation reached ' + method + ' without subscription quota')
    async def run():
        p = QuotaProvider(tmp_path)
        with pytest.raises(ValueError):
            async for _ in p.generate({'job_id': 'test', 'model': 'test', 'prompt': 'test', 'schema': {}}):
                pass
    asyncio.run(run())
