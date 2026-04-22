import pytest
import time
import importlib
resolver_module = importlib.import_module("cloud.services.priority_queue.resolver")
PriorityResolver = resolver_module.PriorityResolver

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def resolver():
    # Use a short timeout for tests if needed, but we'll mock time mostly
    return PriorityResolver(stale_timeout_s=5.0)

def make_req(vehicle_id: str, node_id: str, priority: int, eta: float) -> dict:
    return {
        "vehicle_id": vehicle_id,
        "target_node_id": node_id,
        "city": "Test City",
        "eta_s": eta,
        "distance_m": eta * 15.0, # rough approximation
        "priority_class": priority,
        "source": "TEST"
    }

# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

def test_add_single_request_becomes_winner(resolver):
    req = make_req("V1", "NODE-A", priority=1, eta=30.0)
    changed = resolver.add_request(req)
    
    assert changed is True
    assert resolver.current_winners["NODE-A"] == "V1"

def test_add_same_vehicle_updates_eta_no_winner_change(resolver):
    resolver.add_request(make_req("V1", "NODE-A", priority=1, eta=30.0))
    changed = resolver.add_request(make_req("V1", "NODE-A", priority=1, eta=25.0))
    
    # State was updated, but the winner is still V1
    assert changed is False
    assert resolver.current_winners["NODE-A"] == "V1"
    assert resolver.active_requests["NODE-A"]["V1"].eta_s == 25.0

def test_higher_priority_beats_lower_priority(resolver):
    # Ambulance arrives first, ETA 10s
    resolver.add_request(make_req("AMB-1", "NODE-A", priority=1, eta=10.0))
    
    # Firetruck arrives later, ETA 45s (Farther away, but higher priority)
    changed = resolver.add_request(make_req("FIRE-1", "NODE-A", priority=3, eta=45.0))
    
    assert changed is True
    assert resolver.current_winners["NODE-A"] == "FIRE-1"

def test_equal_priority_lower_eta_wins(resolver):
    # Firetruck 1, ETA 45s
    resolver.add_request(make_req("FIRE-1", "NODE-A", priority=3, eta=45.0))
    
    # Firetruck 2, ETA 20s (Closer)
    changed = resolver.add_request(make_req("FIRE-2", "NODE-A", priority=3, eta=20.0))
    
    assert changed is True
    assert resolver.current_winners["NODE-A"] == "FIRE-2"

def test_removal_reverts_to_next_best(resolver):
    resolver.add_request(make_req("AMB-1", "NODE-A", priority=1, eta=10.0))
    resolver.add_request(make_req("FIRE-1", "NODE-A", priority=3, eta=45.0))
    
    assert resolver.current_winners["NODE-A"] == "FIRE-1"
    
    # Firetruck passes the intersection and is removed
    changed = resolver.remove_request("NODE-A", "FIRE-1")
    
    assert changed is True
    assert resolver.current_winners["NODE-A"] == "AMB-1"

def test_removal_clears_winner_if_empty(resolver):
    resolver.add_request(make_req("AMB-1", "NODE-A", priority=1, eta=10.0))
    changed = resolver.remove_request("NODE-A", "AMB-1")
    
    assert changed is True
    assert resolver.current_winners["NODE-A"] is None
    assert "NODE-A" not in resolver.active_requests

def test_prune_stale_requests(resolver, monkeypatch):
    """Verifies that old requests are pruned and the winner is recalculated."""
    current_time = 100.0
    monkeypatch.setattr(time, "time", lambda: current_time)
    
    # V1 (Ambulance) arrives at t=100
    resolver.add_request(make_req("V1", "NODE-A", priority=1, eta=10.0))
    
    # V2 (Firetruck) arrives at t=101
    current_time = 101.0
    resolver.add_request(make_req("V2", "NODE-A", priority=3, eta=40.0))
    
    assert resolver.current_winners["NODE-A"] == "V2" # Firetruck wins
    
    # Fast forward to t=106
    # Timeout is 5.0 seconds. V1 is 6 seconds old (stale). V2 is 5 seconds old (borderline, let's say safe or stale depending on strict > or >=). 
    # Actually, current_time - timestamp > 5.0.
    # For V1: 106 - 100 = 6 > 5.0 (pruned)
    # For V2: 106 - 101 = 5 (not strictly >, kept)
    current_time = 106.0
    changed_nodes = resolver.prune_stale_requests()
    
    # Neither winning identity should change here (V1 was pruned, but V2 was the winner)
    assert len(changed_nodes) == 0
    assert "V1" not in resolver.active_requests["NODE-A"]
    assert resolver.current_winners["NODE-A"] == "V2"
    
    # Fast forward to t=107
    # V2 is now 6 seconds old
    current_time = 107.0
    changed_nodes = resolver.prune_stale_requests()
    
    assert "NODE-A" in changed_nodes
    assert resolver.current_winners["NODE-A"] is None
    assert "NODE-A" not in resolver.active_requests
