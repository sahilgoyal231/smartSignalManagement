import pytest
import networkx as nx
import importlib
route_engine_module = importlib.import_module("cloud.services.route_engine.routing")
RouteEngine = route_engine_module.RouteEngine

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def mock_route_engine():
    """Returns a RouteEngine with a tiny mock graph instead of downloading city graphs."""
    
    # We patch the graph loader to prevent network calls during testing
    class MockRouteEngine(RouteEngine):
        def _load_city_graph(self, city: str):
            # Create a mock 3-node graph representing a straight road
            G = nx.MultiDiGraph()
            G.graph["crs"] = "epsg:4326"
            
            # Add nodes with lat/lon coordinates (x=lon, y=lat)
            G.add_node(1, y=19.0000, x=72.8000)
            G.add_node(2, y=19.0001, x=72.8000)
            G.add_node(3, y=19.0002, x=72.8000)
            
            # Add edges with travel_time weights
            G.add_edge(1, 2, travel_time=10.0)
            G.add_edge(2, 3, travel_time=10.0)
            
            self.graphs[city] = G

    engine = MockRouteEngine(cities=["Mock City"])
    
    # Inject mock EdgeNodes for testing intersection detection
    # Node 1 is at coordinates of Graph Node 2
    engine.update_edge_nodes([
        {"node_id": "NODE-1", "city": "Mock City", "location_lat": 19.0001, "location_lon": 72.8000}
    ])
    
    return engine

# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

def test_heuristic_calculation(mock_route_engine):
    """Verifies that the heuristic accurately calculates geographic distance."""
    graph = mock_route_engine.graphs["Mock City"]
    
    # Distance between Node 1 and 2 (approx 11.1 meters due to lat diff)
    dist = mock_route_engine._heuristic(1, 2, graph)
    assert 10.0 < dist < 12.0

def test_predict_route_finds_path(mock_route_engine):
    """Verifies A* pathfinding correctly traces nodes."""
    route_coords = mock_route_engine.predict_route(
        city="Mock City",
        start_lat=19.0000, start_lon=72.8000,  # Near Node 1
        dest_lat=19.0002, dest_lon=72.8000     # Near Node 3
    )
    
    assert route_coords is not None
    assert len(route_coords) == 3  # Should pass through nodes 1, 2, 3
    assert route_coords[0] == (19.0000, 72.8000) # Start
    assert route_coords[2] == (19.0002, 72.8000) # End

def test_predict_route_unknown_city(mock_route_engine):
    """Verifies graceful routing failure when city is not tracked."""
    route = mock_route_engine.predict_route(
        city="Unknown City", 
        start_lat=1, start_lon=1, 
        dest_lat=2, dest_lon=2
    )
    assert route is None

def test_intersection_detection(mock_route_engine):
    """Verifies the engine accurately detects upcoming edge nodes along a path."""
    
    # Mock route path passing exactly through Node 1 (19.0001) and Node 3 (19.0002)
    route_coords = [
        (19.0000, 72.8000), 
        (19.0001, 72.8000), # Intersection here
        (19.0002, 72.8000)
    ]
    
    upcoming = mock_route_engine.detect_upcoming_intersections(
        route_coords=route_coords,
        current_speed_kmh=36.0, # 10 m/s
        lookahead_distance_m=1000.0
    )
    
    assert len(upcoming) == 1
    assert upcoming[0]["node_id"] == "NODE-1"
    assert upcoming[0]["city"] == "Mock City"
    
    # Distance from start to intersection is roughly 11 meters
    assert 10.0 < upcoming[0]["distance_m"] < 12.0
    
    # At 10 m/s, ETA should be around 1.1s
    assert 1.0 < upcoming[0]["eta_s"] < 1.3

def test_intersection_outside_lookahead(mock_route_engine):
    """Verifies that nodes further than the lookahead distance are not returned."""
    route_coords = [
        (19.0000, 72.8000), 
        (19.0001, 72.8000), # Intersection here
    ]
    
    upcoming = mock_route_engine.detect_upcoming_intersections(
        route_coords=route_coords,
        current_speed_kmh=36.0,
        lookahead_distance_m=5.0 # Set lookahead shorter than the 11m distance
    )
    
    assert len(upcoming) == 0
