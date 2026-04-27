try:
    import osmnx as ox
    import networkx as nx
    from geopy.distance import geodesic
    GEO_AVAILABLE = True
except ImportError:
    GEO_AVAILABLE = False
    ox = None
    nx = None
    geodesic = None

from typing import List, Tuple, Dict, Any, Optional
from loguru import logger
import math

class RouteEngine:
    """
    Core routing engine using OSMnx and NetworkX.
    Preloads city street networks to predict emergency vehicle paths via A*.
    """
    def __init__(self, cities: List[str]):
        """
        Args:
            cities: List of city names to preload (e.g., ["Mumbai, India", "Delhi, India"])
        """
        self.graphs: Dict[str, Any] = {}
        self.edge_nodes: List[Dict[str, Any]] = [] # Will be populated from the database
        
        if not GEO_AVAILABLE:
            logger.warning(
                "osmnx/networkx/geopy not installed — Route Engine running in STUB mode. "
                "Route prediction is disabled. Install geo dependencies for full functionality."
            )
            return
        
        # Configure osmnx to use a local cache to avoid rate limits on subsequent runs
        ox.settings.use_cache = True
        ox.settings.log_console = False
        
        for city in cities:
            self._load_city_graph(city)

    def _load_city_graph(self, city: str):
        """Downloads or loads the drivable street network for a city."""
        logger.info(f"Loading OSM street network for: {city} (This may take a minute...)")
        try:
            # We specifically want the 'drive' network as emergency vehicles use roads
            G = ox.graph_from_place(city, network_type="drive", simplify=True)
            
            # Impute missing edge speeds and calculate travel times
            G = ox.add_edge_speeds(G)
            G = ox.add_edge_travel_times(G)
            
            self.graphs[city] = G
            logger.info(f"Successfully loaded graph for {city}: {len(G.nodes)} nodes, {len(G.edges)} edges.")
        except Exception as e:
            logger.error(f"Failed to load OSM graph for {city}. Error: {e}")

    def update_edge_nodes(self, nodes: List[Dict[str, Any]]):
        """Update the internal list of EdgeNode locations from the DB."""
        self.edge_nodes = nodes
        logger.debug(f"RouteEngine updated with {len(self.edge_nodes)} EdgeNodes.")

    def _heuristic(self, node1: int, node2: int, graph: "nx.MultiDiGraph") -> float:
        """
        Heuristic function for A* (straight-line distance).
        Args:
            node1: OSM node ID 1
            node2: OSM node ID 2
            graph: The OSMnx graph
        Returns:
            Distance in meters
        """
        n1 = graph.nodes[node1]
        n2 = graph.nodes[node2]
        return ox.distance.great_circle(n1['y'], n1['x'], n2['y'], n2['x'])

    def predict_route(self, city: str, start_lat: float, start_lon: float, dest_lat: float, dest_lon: float) -> Optional[List[Tuple[float, float]]]:
        """
        Predicts the optimal path between two coordinates using A* on travel time.
        
        Returns:
            List of (lat, lon) road coordinates representing the path, or None if no path found.
        """
        if city not in self.graphs or not GEO_AVAILABLE:
            logger.error(f"Cannot route in {city}: Graph not loaded.")
            return None
            
        G = self.graphs[city]

        try:
            # 1. Find the nearest OSM nodes to the raw GPS coordinates
            # OSMnx 2.0+ requires `return_dist=False` by default if not specified, 
            # and returns scalar array if 1 point passed. We ensure standard scalar usage:
            start_node = ox.distance.nearest_nodes(G, X=start_lon, Y=start_lat)
            dest_node = ox.distance.nearest_nodes(G, X=dest_lon, Y=dest_lat)

            if start_node == dest_node:
                logger.debug("Vehicle is already at or very close to the destination.")
                return [(start_lat, start_lon)]

            # 2. Run A* Algorithm (weighted by travel_time)
            # Use a lambda to pass the graph to our heuristic
            route_node_ids = nx.astar_path(
                G, 
                source=start_node, 
                target=dest_node, 
                heuristic=lambda u, v: self._heuristic(u, v, G) / 15.0, # Divide distance by roughly 15m/s (54kmh) for time heuristic
                weight='travel_time'
            )

            # 3. Convert node IDs back to (Lat, Lon) coordinates
            route_coords = [
                (G.nodes[n]['y'], G.nodes[n]['x']) for n in route_node_ids
            ]
            
            return route_coords

        except nx.NetworkXNoPath:
            logger.warning(f"No drivable path found from ({start_lat}, {start_lon}) to ({dest_lat}, {dest_lon}) in {city}.")
            return None
        except Exception as e:
            logger.error(f"Error during route prediction: {e}")
            return None

    def detect_upcoming_intersections(
        self, 
        route_coords: List[Tuple[float, float]], 
        current_speed_kmh: float,
        lookahead_distance_m: float = 1500.0  # Only look 1.5km ahead
    ) -> List[Dict[str, Any]]:
        """
        Walks along the predicted route and identifies which `EdgeNodes` (smart intersections)
        the vehicle will pass through, calculating an ETA for each.
        
        Args:
            route_coords: List of (lat, lon) on the path
            current_speed_kmh: Vehicle's current speed
            lookahead_distance_m: Max distance to look ahead to prevent triggering signals too early.
            
        Returns:
            List of dicts: {"node_id": str, "distance_m": float, "eta_s": float}
        """
        if not route_coords or not self.edge_nodes or not GEO_AVAILABLE:
            return []

        speed_ms = current_speed_kmh / 3.6
        if speed_ms < 5.0:  # If moving very slowly or stopped, assume a baseline 18 km/h (5 m/s) city speed for ETA bounds
            speed_ms = 5.0

        upcoming_nodes = []
        accumulated_distance_m = 0.0
        
        # Start at the vehicle's position (index 0)
        for i in range(len(route_coords) - 1):
            p1 = route_coords[i]
            p2 = route_coords[i+1]
            
            # Distance of this specific road segment
            segment_dist = geodesic(p1, p2).meters
            accumulated_distance_m += segment_dist
            
            if accumulated_distance_m > lookahead_distance_m:
                break # Stop searching, we've looked far enough ahead

            # Check if any EdgeNode lies near this street segment
            for node in self.edge_nodes:
                node_coords = (node["location_lat"], node["location_lon"])
                
                # Fast check: If the distance from segment end to intersection is within 50m
                dist_to_node = geodesic(p2, node_coords).meters
                
                if dist_to_node <= 50.0:
                    # Target acquired on this segment
                    
                    # Prevent duplicate node additions if multiple tiny segments are near the intersection
                    if not any(n["node_id"] == node["node_id"] for n in upcoming_nodes):
                        # Calculate ETA based on the distance traversed *along the road path*
                        total_dist_to_node = accumulated_distance_m
                        eta_s = total_dist_to_node / speed_ms
                        
                        upcoming_nodes.append({
                            "node_id": node["node_id"],
                            "city": node["city"],
                            "distance_m": round(total_dist_to_node, 2),
                            "eta_s": round(eta_s, 1)
                        })

        return upcoming_nodes
