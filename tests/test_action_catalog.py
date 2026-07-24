from netmedic.action_catalog import (
    DISRUPTIVE_ACTIONS,
    POLKIT_ACTION_IDS,
    PRIVILEGED_ACTIONS,
    SAFE_ACTIONS,
    is_disruptive,
    is_privileged,
    is_safe,
    polkit_action_for,
)


def test_every_privileged_action_has_polkit_mapping():
    for action in PRIVILEGED_ACTIONS:
        assert polkit_action_for(action) in POLKIT_ACTION_IDS.values()
        assert polkit_action_for(action) is not None


def test_safe_and_privileged_disjoint():
    assert PRIVILEGED_ACTIONS.isdisjoint(SAFE_ACTIONS)


def test_firewall_status_is_safe():
    assert is_safe("firewall_status")
    assert not is_privileged("firewall_status")


def test_vpn_list_clients_is_privileged():
    assert is_privileged("vpn_list_clients")
    assert not is_safe("vpn_list_clients")
    assert polkit_action_for("vpn_list_clients") == "com.kayab.netmedic.vpn-list"


def test_disruptive_subset_of_privileged():
    assert DISRUPTIVE_ACTIONS.issubset(PRIVILEGED_ACTIONS)
    assert is_disruptive("reset_tcp_ip_stack")
    assert not is_disruptive("flush_dns")