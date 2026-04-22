"""
Tests for Edge Node MQTT Client
"""
import json
from unittest.mock import MagicMock, patch
import pytest

from ren.src.mqtt_client import EdgeMQTTClient
from ren.src.config import RENConfig


@pytest.fixture
def config():
    cfg = RENConfig()
    cfg.node_id = "TEST_NODE"
    return cfg

@pytest.fixture
def mock_paho():
    with patch("ren.src.mqtt_client.mqtt.Client") as mock_client:
        yield mock_client

def test_mqtt_client_initialization(config, mock_paho):
    client = EdgeMQTTClient(config)
    mock_paho.assert_called_once()
    assert client.connected is False
    assert len(client._command_handlers) == 0

def test_mqtt_connect_disconnect(config, mock_paho):
    client = EdgeMQTTClient(config)
    mock_inner_client = mock_paho.return_value
    
    client.connect()
    mock_inner_client.connect.assert_called_once_with(config.mqtt_host, config.mqtt_port, keepalive=60)
    mock_inner_client.loop_start.assert_called_once()

    client.disconnect()
    mock_inner_client.loop_stop.assert_called_once()
    mock_inner_client.disconnect.assert_called_once()

def test_mqtt_on_connect_callback(config, mock_paho):
    client = EdgeMQTTClient(config)
    mock_inner_client = mock_paho.return_value
    
    # Simulate failed connection
    client._on_connect(mock_inner_client, None, {}, 1, None)
    assert client.connected is False
    
    # Simulate successful connection
    client._on_connect(mock_inner_client, None, {}, 0, None)
    assert client.connected is True
    # Should subscribe to its command topic
    mock_inner_client.subscribe.assert_called_with("city/nodes/TEST_NODE/commands/#")
    
    # And publish initial heartbeat
    mock_inner_client.publish.assert_called_with(
        "city/nodes/TEST_NODE/telemetry", 
        json.dumps({"status": "ONLINE", "uptime_s": 0.0}), 
        qos=1
    )

def test_mqtt_publish_telemetry(config, mock_paho):
    client = EdgeMQTTClient(config)
    mock_inner_client = mock_paho.return_value
    
    # If not connected, shouldn't publish
    client.connected = False
    client.publish_telemetry({"test": 123})
    mock_inner_client.publish.assert_not_called()
    
    # If connected, should publish
    client.connected = True
    client.publish_telemetry({"test": 123})
    mock_inner_client.publish.assert_called_once_with(
        "city/nodes/TEST_NODE/telemetry", '{"test": 123}', qos=1
    )

def test_mqtt_publish_event(config, mock_paho):
    client = EdgeMQTTClient(config)
    mock_inner_client = mock_paho.return_value
    client.connected = True
    
    with patch("ren.src.mqtt_client.time.time", return_value=100.0):
        client.publish_event("PREEMPT_TRIGGER", {"phase": "NORTHBOUND"})
    
    expected_payload = json.dumps({
        "event": "PREEMPT_TRIGGER",
        "timestamp": 100.0,
        "data": {"phase": "NORTHBOUND"}
    })
    
    mock_inner_client.publish.assert_called_once_with(
        "city/nodes/TEST_NODE/events", expected_payload, qos=1
    )

def test_mqtt_on_message_callback(config, mock_paho):
    client = EdgeMQTTClient(config)
    mock_inner_client = mock_paho.return_value
    
    handler = MagicMock()
    client.register_command_handler("reboot", handler)
    
    msg = MagicMock()
    msg.topic = "city/nodes/TEST_NODE/commands/reboot"
    msg.payload = b'{"force": true}'
    
    # Trigger callback
    client._on_message(mock_inner_client, None, msg)
    
    # Handler should be called with parsed JSON
    handler.assert_called_once_with({"force": True})
    
    # Test invalid JSON doesn't crash
    msg.payload = b'{"bad_json":'
    client._on_message(mock_inner_client, None, msg) # Shouldn't raise
