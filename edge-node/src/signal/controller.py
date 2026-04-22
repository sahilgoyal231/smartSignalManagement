"""
Edge Node — Signal Controller Interface
"""
import asyncio
from enum import Enum
from loguru import logger

class ControllerState(Enum):
    NORMAL_OPERATION = "NORMAL_OPERATION"
    HOLD_GREEN = "HOLD_GREEN"
    FLASHING_RED = "FLASHING_RED"

class SignalController:
    """
    Interfaces with the physical traffic light controller.
    In a real deployment, this would speak NTCIP over Ethernet or actuate
    RS-485 GPIO relays. Here, we simulate the hardware interaction.
    """
    
    def __init__(self, node_id: str, protocol: str = "NTCIP"):
        self.node_id = node_id
        self.protocol = protocol
        self.current_state = ControllerState.NORMAL_OPERATION
        self.active_preemption_id = None
        self._lock = asyncio.Lock()

    async def preempt(self, vehicle_id: str, priority: int, approach_phase: int):
        """Command the intersection to hold green for the approaching vehicle."""
        async with self._lock:
            if self.current_state == ControllerState.HOLD_GREEN and self.active_preemption_id == vehicle_id:
                # Already holding for this vehicle
                return True
                
            logger.warning(
                f"[{self.node_id}] 🚦 HARDWARE PREEMPTION TRIGGERED. "
                f"Holding Phase {approach_phase} GREEN for {vehicle_id} (Priority {priority})"
            )
            self.current_state = ControllerState.HOLD_GREEN
            self.active_preemption_id = vehicle_id
            
            # Simulating physical controller acknowledgment delay
            await asyncio.sleep(0.1) 
            return True

    async def release(self):
        """Release the intersection back to normal timing plans."""
        async with self._lock:
            if self.current_state == ControllerState.NORMAL_OPERATION:
                return True
                
            logger.info(f"[{self.node_id}] 🚦 HARDWARE RELEASED. Resuming normal operations.")
            self.current_state = ControllerState.NORMAL_OPERATION
            self.active_preemption_id = None
            
            # Simulating physical controller acknowledgment delay
            await asyncio.sleep(0.1)
            return True
            
    def get_status(self) -> dict:
        return {
            "state": self.current_state.value,
            "active_vehicle": self.active_preemption_id,
            "protocol": self.protocol,
            "hw_ok": True
        }
