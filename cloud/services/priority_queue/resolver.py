import time
from typing import Dict, Any, Optional
from loguru import logger
from pydantic import BaseModel

class PreemptionRequest(BaseModel):
    vehicle_id: str
    target_node_id: str
    city: str
    eta_s: float
    distance_m: float
    priority_class: int
    source: str
    timestamp: float = 0.0

class PriorityResolver:
    """
    In-memory state engine to manage concurrent preemption requests 
    for intersections and determine the 'winner'.
    """
    def __init__(self, stale_timeout_s: float = 30.0):
        # Dictionary mapping node_id -> dict mapping vehicle_id -> PreemptionRequest
        self.active_requests: Dict[str, Dict[str, PreemptionRequest]] = {}
        # Dictionary mapping node_id -> the current winning vehicle_id
        self.current_winners: Dict[str, Optional[str]] = {}
        
        self.stale_timeout_s = stale_timeout_s

    def add_request(self, request_data: Dict[str, Any]) -> bool:
        """
        Admit a new preemption request into the tracked state.
        Returns True if this request changes the current winner for the node.
        """
        req = PreemptionRequest(**request_data)
        req.timestamp = time.time()
        
        node_id = req.target_node_id
        
        if node_id not in self.active_requests:
            self.active_requests[node_id] = {}
            
        self.active_requests[node_id][req.vehicle_id] = req
        
        # Recalculate and return whether the winner changed
        return self._recalculate_winner(node_id)

    def remove_request(self, node_id: str, vehicle_id: str) -> bool:
        """
        Remove a request (e.g. if the vehicle passed the intersection or aborted).
        Returns True if this removal changed the current winner.
        """
        if node_id in self.active_requests and vehicle_id in self.active_requests[node_id]:
            del self.active_requests[node_id][vehicle_id]
            logger.debug(f"Removed request for '{vehicle_id}' from '{node_id}'")
            
            # Clean up empty node registries
            if not self.active_requests[node_id]:
                del self.active_requests[node_id]
                
            return self._recalculate_winner(node_id)
        return False

    def prune_stale_requests(self) -> list[str]:
        """
        Removes requests that haven't received updates within the timeout window.
        Returns a list of node_ids that had a change in winner due to pruning.
        """
        now = time.time()
        changed_nodes = set()
        
        nodes_to_check = list(self.active_requests.keys())
        
        for node_id in nodes_to_check:
            vehicles = list(self.active_requests[node_id].keys())
            for vid in vehicles:
                req = self.active_requests[node_id][vid]
                if now - req.timestamp > self.stale_timeout_s:
                    logger.info(f"Pruning stale request for '{vid}' at '{node_id}'")
                    del self.active_requests[node_id][vid]
                    
            if not self.active_requests[node_id]:
                del self.active_requests[node_id]
                
            # Recalculate in case the winner was pruned or state is empty
            if self._recalculate_winner(node_id):
                changed_nodes.add(node_id)
                
        return list(changed_nodes)

    def _recalculate_winner(self, node_id: str) -> bool:
        """
        Determines the current winning request for a node.
        Priority Class wins first (Higher is better: 3 > 1).
        If tied, lowest ETA wins.
        Returns True if the winner identity changed.
        """
        old_winner = self.current_winners.get(node_id)
        
        if node_id not in self.active_requests or not self.active_requests[node_id]:
            self.current_winners[node_id] = None
            new_winner = None
        else:
            requests = list(self.active_requests[node_id].values())
            
            # Sort by Priority Class (Descending: 3=Fire, 2=Police, 1=Amb), then ETA (Ascending)
            # Python's list sort is stable, but we can do it via a composite key
            requests.sort(key=lambda r: (-r.priority_class, r.eta_s))
            
            new_winner = requests[0].vehicle_id
            self.current_winners[node_id] = new_winner

        changed = old_winner != new_winner
        if changed:
            logger.info(f"Intersection '{node_id}' winner changed from {old_winner} to {new_winner}")
            
        return changed

    def get_winner_payload(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Returns the full request data of the current winner to broadcast."""
        winner_id = self.current_winners.get(node_id)
        if winner_id and node_id in self.active_requests:
            return self.active_requests[node_id][winner_id].model_dump()
        return None
