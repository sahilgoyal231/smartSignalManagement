"""
Edge Node — Main Daemon Loop
"""
import asyncio
from typing import Dict
from loguru import logger

import importlib

# Using importlib to handle hyphenated root directory "edge-node"
_cfg = importlib.import_module("edge-node.src.config")
NODE_ID, CITY, NODE_LAT, NODE_LON = _cfg.NODE_ID, _cfg.CITY, _cfg.NODE_LAT, _cfg.NODE_LON
LORA_PORT, PREEMPT_THRESHOLD_S, MAX_GREEN_HOLD_S = _cfg.LORA_PORT, _cfg.PREEMPT_THRESHOLD_S, _cfg.MAX_GREEN_HOLD_S
MQTT_BROKER_HOST, MQTT_BROKER_PORT = _cfg.MQTT_BROKER_HOST, _cfg.MQTT_BROKER_PORT
MQTT_USER, MQTT_PASS = _cfg.MQTT_USER, _cfg.MQTT_PASS

SensorFusionEngine = importlib.import_module("edge-node.src.fusion.engine").SensorFusionEngine
KinematicPredictor = importlib.import_module("edge-node.src.eta.predictor").KinematicPredictor
LoraReceiver = importlib.import_module("edge-node.src.sensors.lora_rx").LoraReceiver

_stubs = importlib.import_module("edge-node.src.sensors.stubs")
YoloCameraStub, AudioFftStub = _stubs.YoloCameraStub, _stubs.AudioFftStub

_signal = importlib.import_module("edge-node.src.signal.controller")
SignalController, ControllerState = _signal.SignalController, _signal.ControllerState

EdgeMqttClient = importlib.import_module("edge-node.src.mqtt.client").EdgeMqttClient

async def heartbeat_loop(mqtt_client: EdgeMqttClient, signal_ctrl: SignalController):
    """Periodically publish node health status to the cloud."""
    while True:
        try:
            if mqtt_client.connected:
                status = {
                    "node_id": NODE_ID,
                    "city": CITY,
                    "firmware_version": "v1.5.0-edge",
                    "status": "ONLINE",
                    "lat": NODE_LAT,
                    "lon": NODE_LON,
                    "active_preemption": signal_ctrl.active_preemption_id,
                    "hw_state": signal_ctrl.current_state.value
                }
                mqtt_client.publish_heartbeat(status)
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}")
        await asyncio.sleep(10.0)

async def preemption_evaluator(
    fusion_engine: SensorFusionEngine,
    eta_predictor: KinematicPredictor,
    signal_ctrl: SignalController,
    mqtt_client: EdgeMqttClient
):
    """
    Main decision loop.
    1. Reads fused tracking state of all known vehicles.
    2. Calculates ETA to this intersection.
    3. If ETA < Threshold AND Confidence > Threshold:
       a. Publishes PREEMPT request to cloud (so Priority Queue can arbitrate).
       b. Cloud runs arbitration and sends back an ACK/NACK via MQTT (alert).
       c. Here, we'll act autonomously if cloud disconnected, or wait for cloud.
       For simplicity + edge autonomy, if Confidence is high enough, we preempt locally.
    """
    # Track when we started holding
    current_hold_start = 0.0
    
    while True:
        try:
            # Check for cloud arbitration messages
            try:
                alert = mqtt_client.alert_queue.get_nowait()
                if alert.get("event_type") == "PREEMPT_ACK":
                    logger.success(f"[{NODE_ID}] Cloud approved preemption for {alert.get('vehicle_id')}")
                    await signal_ctrl.preempt(alert.get("vehicle_id"), 1, 1)
                    current_hold_start = asyncio.get_event_loop().time()
            except asyncio.QueueEmpty:
                pass

            active_vehicles = list(fusion_engine.observations.keys())
            
            best_candidate = None
            best_eta = float('inf')
            best_conf = 0.0
            
            # Evaluate all vehicles tracked nearby
            for vid in active_vehicles:
                state = fusion_engine.get_fused_state(vid)
                if not state or 'location_lat' not in state or state['location_lat'] is None:
                    continue
                    
                confidence = state['confidence']
                if confidence < 0.6: # Need minimum trust
                    continue
                    
                eta_s = eta_predictor.predict_eta(
                    state['location_lat'], 
                    state['location_lon'], 
                    state['speed_kmh']
                )
                
                # Are they close enough to justify preemption?
                if eta_s <= PREEMPT_THRESHOLD_S:
                    if eta_s < best_eta:
                        best_eta = eta_s
                        best_candidate = vid
                        best_conf = confidence
                        
            # Determine Action
            now = asyncio.get_event_loop().time()
            
            if best_candidate:
                # Tell the cloud we want to preempt
                mqtt_client.publish_preempt(best_candidate, best_eta, approach_phase=1, confidence=best_conf)
                
                # Autonomous fallback: if cloud is disconnected or we just want immediate action
                # We trigger local hardware HOLD_GREEN
                if await signal_ctrl.preempt(best_candidate, priority=1, approach_phase=1):
                    if current_hold_start == 0.0:
                        current_hold_start = now
                
            else:
                # Nobody nearby needs it. Release signal if we were holding.
                if signal_ctrl.current_state == ControllerState.HOLD_GREEN:
                    await signal_ctrl.release()
                    current_hold_start = 0.0
                    
            # Safety timeout (failsafe against getting stuck green)
            if signal_ctrl.current_state == ControllerState.HOLD_GREEN and current_hold_start > 0:
                if (now - current_hold_start) > MAX_GREEN_HOLD_S:
                    logger.error(f"[{NODE_ID}] MAX GREEN TIMEOUT EXCEEDED! Forcing release.")
                    await signal_ctrl.release()
                    current_hold_start = 0.0

        except Exception as e:
            logger.error(f"Preemption loop error: {e}")
            
        await asyncio.sleep(1.0) # Check every second


async def main():
    logger.info(f"Starting Edge Node daemon: {NODE_ID} ({CITY})")
    
    # 1. Init Core Services
    fusion_engine = SensorFusionEngine(stale_timeout_s=15.0)
    eta_predictor = KinematicPredictor(NODE_LAT, NODE_LON)
    signal_ctrl   = SignalController(NODE_ID)
    mqtt_client   = EdgeMqttClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_USER, MQTT_PASS, NODE_ID, CITY)
    
    # 2. Init Sensors
    lora   = LoraReceiver(LORA_PORT)
    camera = YoloCameraStub(NODE_ID)
    audio  = AudioFftStub(NODE_ID)
    
    # 3. Connect to Cloud
    await mqtt_client.connect()
    
    # 4. Start Event Loops concurrently
    tasks = [
        asyncio.create_task(lora.run(fusion_engine)),
        asyncio.create_task(camera.run(fusion_engine)),
        asyncio.create_task(audio.run(fusion_engine)),
        asyncio.create_task(heartbeat_loop(mqtt_client, signal_ctrl)),
        asyncio.create_task(preemption_evaluator(fusion_engine, eta_predictor, signal_ctrl, mqtt_client))
    ]
    
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Daemon shutting down...")
    finally:
        await mqtt_client.disconnect()
        await signal_ctrl.release()

if __name__ == "__main__":
    import sys
    # Add project root to path for relative imports if run directly
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEdge Node Stopped.")
