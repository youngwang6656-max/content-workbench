from concurrent.futures import ThreadPoolExecutor
import pytest
from test_repository import make

def test_atomic_reservations_unknown_and_cap(tmp_path):
    from waypoint.budget import Budget
    r,p,t=make(tmp_path);b=Budget(r);b.add_external(17_000_000,'其他运行费用')
    def attempt(i):
        try:return b.reserve(str(i),800_000)
        except ValueError:return None
    with ThreadPoolExecutor(2) as ex: got=list(ex.map(attempt,[1,2]))
    assert sum(x is not None for x in got)==1
    with pytest.raises(ValueError):b.reserve('unknown',None)
    x=next(x for x in got if x);b.settle(x['id'],None)
    with pytest.raises(ValueError):b.reserve('next',1)
    assert r.settings()['api_enabled'] is False
