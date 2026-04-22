"""
Edge Node Main Entrypoint
=========================
Initializes all Node components (LoRa, Sensor Fusion, Decision Engine, 
MQTT Client, Signal Controller) and runs the main evaluation loop.
"""
import sys
import time
from loguru import logger

from ren.src.config import get_config
from ren.src.lora_rx import LoRaReceiver
from ren.src.sensor_fusion import SensorFusionEngine
from ren.src.signal_controller import get_signal_controller
from ren.src.mqtt_client import EdgeMQTTClient
from ren.src.decision_engine import DecisionEngine

def main():
    logger.info("🚦 Starting Edge Node (REN) Software...")
    config = get_config()

    # 1. Initialize Signal Controller (Mock, Relay, or Serial)
    signal_controller = get_signal_controller(config)

    # 2. Initialize MQTT Client for Cloud Connectivity
    mqtt_client = EdgeMQTTClient(config)
    mqtt_client.connect()

    # Register a command handler (e.g., to reboot or force clear preemption)
    def handle_reboot(data):
        logger.warning(f"Received reboot command from cloud: {data}")
        # In a real system, you might os.system('sudo reboot')
        sys.exit(0)
    
    mqtt_client.register_command_handler("reboot", handle_reboot)

    # 3. Initialize Sensor Fusion Engine
    fusion_engine = SensorFusionEngine(config)

    # 4. Initialize LoRa Receiver (runs its own thread)
    lora_rx = LoRaReceiver(config)
    lora_rx.register_callback(fusion_engine.process_lora_beacon)
    lora_rx.start()

    # 5. Initialize Decision Engine
    decision_engine = DecisionEngine(
        config=config, 
        signal_controller=signal_controller,
        mqtt_client=mqtt_client
    )

    try:
        logger.info("✅ Edge Node is running. Press Ctrl+C to stop.")
        last_telemetry_time = time.time()
        
        while True:
            # 1. Update Fusion Tracks
            fusion_engine.update_tracks()
            active_tracks = fusion_engine.get_active_tracks()
            
            # 2. Evaluate Preemption Logic
            decision = decision_engine.evaluate(active_tracks)
            
            # 3. Publish Telemetry Periodically (every 5 seconds)
            now = time.time()
            if now - last_telemetry_time >= 5.0:
                telemetry_data = {
                    "status": "ONLINE",
                    "active_tracks_count": len(active_tracks),
                    "signal_state": decision.target_phase if decision.should_preempt else "NORMAL",
                    "preemption_active": decision.should_preempt
                }
                mqtt_client.publish_telemetry(telemetry_data)
                last_telemetry_time = now

            # Sleep for 100ms before next evaluation cycle
            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("🛑 Shutting down Edge Node...")
    finally:
        lora_rx.stop()
        mqtt_client.disconnect()
        signal_controller.clear_preemption()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()
