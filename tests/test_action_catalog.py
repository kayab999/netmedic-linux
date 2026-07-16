from netmedic.action_catalog import (
    POLKIT_ACTION_IDS,
    PRIVILEGED_ACTIONS,
    SAFE_ACTIONS,
    is_privileged,
    is_safe,
    polkit_action_for,
)


def test_every_privileged_action_has_polkit_mapping():
    for action in PRIVILEGED_ACTIONS:
        assert polkit_action_for(action) in POLKIT_ACTION_IDS.values()


def test_safe_and_privileged_disjoint():
    assert PRIVILEGED_ACTIONS.isdisjoint(SAFE_ACTIONS)


def test_firewall_status_is_safe():
    assert is_safe("firewall_status")
    assert not is_privileged("firewall_status")