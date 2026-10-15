import pytest
from test_repository import make

def test_only_available_models_and_no_silent_upgrade(tmp_path):
    from waypoint.routing import choose_model
    r,p,t=make(tmp_path)
    with pytest.raises(ValueError):choose_model('write',{'models':[]},r.settings())
    s=r.settings();s['model_roles']={'write':'available','translate':'missing'}
    report={'models':[{'id':'available','model':'available'}]}
    assert choose_model('write',report,s)['model']=='available'
    with pytest.raises(ValueError):choose_model('translate',report,s)


def test_subscription_models_explicitly_use_high_reasoning(tmp_path):
    from waypoint.routing import choose_model
    r,p,t=make(tmp_path)
    settings=r.settings();settings['model_roles']={'write':'gpt-6.1-sol','translate':'gpt-6-luna'}
    report={'models':[{'model':'gpt-6.1-sol','supportedReasoningEfforts':[{'reasoningEffort':'low'},{'reasoningEffort':'high'}]},
                      {'model':'gpt-6-luna','supportedReasoningEfforts':[{'reasoningEffort':'high'}]}]}
    for role in ('write','translate'):
        choice=choose_model(role,report,settings)
        assert choice['model']==settings['model_roles'][role] and choice['effort']=='high'


def test_unsupported_high_effort_pauses_without_silent_downgrade(tmp_path):
    from waypoint.routing import choose_model
    r,p,t=make(tmp_path);settings=r.settings();settings['model_roles']={'write':'limited'}
    report={'models':[{'model':'limited','supportedReasoningEfforts':[{'reasoningEffort':'low'}]}]}
    with pytest.raises(ValueError,match='高'):choose_model('write',report,settings)


def test_hidden_subscription_model_is_unavailable(tmp_path):
    from waypoint.routing import choose_model
    r,p,t=make(tmp_path);settings=r.settings();settings['model_roles']={'write':'retired'}
    report={'models':[{'model':'retired','hidden':True,'supportedReasoningEfforts':[{'reasoningEffort':'high'}]}]}
    with pytest.raises(ValueError,match='不可用'):choose_model('write',report,settings)
