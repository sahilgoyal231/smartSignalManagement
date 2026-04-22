"""
InfluxDB Client — Time-Series Data Layer
==========================================
Wraps the official influxdb-client-python with:
  - Async write API for sensor telemetry (vehicle, node, signal state)
  - Query API for analytics and dashboard data
  - Health check
  - Connection shared via singleton pattern

Measurements:
  1. vehicle_telemetry   — GPS, speed, siren state per vehicle (1 Hz)
  2. node_telemetry      — CPU, RAM, temp, uptime per edge node (30 s)
  3. signal_state        — Phase state per node per phase (5 s)
  4. preemption_metrics  — Duration, ETA accuracy per event (on event)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from functools import lru_cache

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS, SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from loguru import logger

from cloud.shared.config import get_settings

settings = get_settings()


# ─────────────────────────────────────────────────────────────
# Singleton client
# ─────────────────────────────────────────────────────────────

class InfluxManager:
    """
    Long-lived InfluxDB client singleton.
    Use get_influx() to access the shared instance.
    """

    def __init__(self) -> None:
        self._client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
            enable_gzip=True,           # compress writes
        )
        self._write_api = self._client.write_api(write_options=ASYNCHRONOUS)
        self._query_api = self._client.query_api()
        self._bucket = settings.influx_bucket
        self._org = settings.influx_org
        logger.info(f"InfluxDB client initialised → {settings.influx_url}")

    # ─────────────────────────────────────────────
    # Health
    # ─────────────────────────────────────────────

    def is_healthy(self) -> bool:
        """Ping the InfluxDB instance."""
        try:
            return self._client.ping()
        except Exception as exc:
            logger.error(f"InfluxDB health check failed: {exc}")
            return False

    # ─────────────────────────────────────────────
    # Write: vehicle telemetry
    # ─────────────────────────────────────────────

    def write_vehicle_telemetry(
        self,
        vehicle_id: str,
        vehicle_type: str,
        city: str,
        lat: float,
        lon: float,
        speed_kmh: float,
        heading_deg: float,
        battery_pct: int,
        siren_active: bool,
        gps_accuracy_m: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write a single vehicle GPS/status sample.
        Called by the cloud MQTT listener every time a beacon arrives.
        """
        ts = timestamp or datetime.now(timezone.utc)
        point = (
            Point("vehicle_telemetry")
            .tag("vehicle_id",   vehicle_id)
            .tag("vehicle_type", vehicle_type)
            .tag("city",         city)
            .field("lat",            lat)
            .field("lon",            lon)
            .field("speed_kmh",      speed_kmh)
            .field("heading_deg",    heading_deg)
            .field("battery_pct",    battery_pct)
            .field("siren_active",   int(siren_active))   # bool → 0/1 for math
            .field("gps_accuracy_m", gps_accuracy_m)
            .time(ts, WritePrecision.MILLISECONDS)
        )
        self._write_api.write(bucket=self._bucket, org=self._org, record=point)

    # ─────────────────────────────────────────────
    # Write: edge node heartbeat telemetry
    # ─────────────────────────────────────────────

    def write_node_telemetry(
        self,
        node_id: str,
        city: str,
        cpu_pct: float,
        mem_pct: float,
        temp_c: float,
        cam_ok: bool,
        lora_ok: bool,
        lte_signal_dbm: int,
        controller_ok: bool,
        uptime_s: int,
        preemptions_today: int,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write edge node health heartbeat.
        Called every 30 seconds from each node via MQTT.
        """
        ts = timestamp or datetime.now(timezone.utc)
        point = (
            Point("node_telemetry")
            .tag("node_id", node_id)
            .tag("city",    city)
            .field("cpu_pct",           cpu_pct)
            .field("mem_pct",           mem_pct)
            .field("temp_c",            temp_c)
            .field("cam_ok",            int(cam_ok))
            .field("lora_ok",           int(lora_ok))
            .field("lte_signal_dbm",    lte_signal_dbm)
            .field("controller_ok",     int(controller_ok))
            .field("uptime_s",          uptime_s)
            .field("preemptions_today", preemptions_today)
            .time(ts, WritePrecision.MILLISECONDS)
        )
        self._write_api.write(bucket=self._bucket, org=self._org, record=point)

    # ─────────────────────────────────────────────
    # Write: signal phase state
    # ─────────────────────────────────────────────

    def write_signal_state(
        self,
        node_id: str,
        city: str,
        phase: int,
        direction: str,
        phase_state: str,          # GREEN / RED / AMBER / ALL_RED / FLASHING_AMBER
        time_in_state_s: int,
        is_preempted: bool,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write current traffic signal phase status.
        Called every 5 seconds per phase from each edge node.
        """
        ts = timestamp or datetime.now(timezone.utc)
        point = (
            Point("signal_state")
            .tag("node_id",   node_id)
            .tag("city",      city)
            .tag("phase",     str(phase))
            .tag("direction", direction)
            .field("phase_state",    phase_state)
            .field("time_in_state_s", time_in_state_s)
            .field("is_preempted",   int(is_preempted))
            .time(ts, WritePrecision.MILLISECONDS)
        )
        self._write_api.write(bucket=self._bucket, org=self._org, record=point)

    # ─────────────────────────────────────────────
    # Write: preemption event metrics
    # ─────────────────────────────────────────────

    def write_preemption_metric(
        self,
        event_id: str,
        vehicle_id: str,
        node_id: str,
        city: str,
        eta_at_trigger_s: float,
        actual_arrival_s: float,
        green_hold_duration_s: float,
        sensor_confidence: float,
        outcome: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write KPI data for a completed preemption event.
        Used by Grafana dashboards to compute response time savings.
        """
        ts = timestamp or datetime.now(timezone.utc)
        eta_accuracy_pct = (
            100.0 - abs(actual_arrival_s - eta_at_trigger_s) / max(eta_at_trigger_s, 1) * 100
        )
        point = (
            Point("preemption_metrics")
            .tag("vehicle_id", vehicle_id)
            .tag("node_id",    node_id)
            .tag("city",       city)
            .tag("outcome",    outcome)
            .field("event_id",             event_id)
            .field("eta_at_trigger_s",     eta_at_trigger_s)
            .field("actual_arrival_s",     actual_arrival_s)
            .field("green_hold_duration_s", green_hold_duration_s)
            .field("sensor_confidence",    sensor_confidence)
            .field("eta_accuracy_pct",     round(eta_accuracy_pct, 2))
            .time(ts, WritePrecision.MILLISECONDS)
        )
        self._write_api.write(bucket=self._bucket, org=self._org, record=point)

    # ─────────────────────────────────────────────
    # Query helpers (Flux)
    # ─────────────────────────────────────────────

    def query_vehicle_last_position(self, vehicle_id: str) -> dict:
        """Returns latest GPS position for a vehicle."""
        flux = f"""
        from(bucket: "{self._bucket}")
          |> range(start: -1h)
          |> filter(fn: (r) => r._measurement == "vehicle_telemetry")
          |> filter(fn: (r) => r.vehicle_id == "{vehicle_id}")
          |> filter(fn: (r) => r._field == "lat" or r._field == "lon"
                                or r._field == "speed_kmh" or r._field == "heading_deg")
          |> last()
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
        tables = self._query_api.query(flux, org=self._org)
        for table in tables:
            for record in table.records:
                return {
                    "lat":         record.values.get("lat"),
                    "lon":         record.values.get("lon"),
                    "speed_kmh":   record.values.get("speed_kmh"),
                    "heading_deg": record.values.get("heading_deg"),
                    "time":        record.get_time(),
                }
        return {}

    def query_node_health_summary(self, node_id: str) -> dict:
        """Returns latest health snapshot for an edge node."""
        flux = f"""
        from(bucket: "{self._bucket}")
          |> range(start: -10m)
          |> filter(fn: (r) => r._measurement == "node_telemetry")
          |> filter(fn: (r) => r.node_id == "{node_id}")
          |> last()
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
        tables = self._query_api.query(flux, org=self._org)
        for table in tables:
            for record in table.records:
                return dict(record.values)
        return {}

    def query_preemption_count(self, city: str, hours: int = 24) -> int:
        """Returns total preemption events in the last N hours for a city."""
        flux = f"""
        from(bucket: "{self._bucket}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r._measurement == "preemption_metrics")
          |> filter(fn: (r) => r.city == "{city}")
          |> filter(fn: (r) => r._field == "eta_at_trigger_s")
          |> count()
        """
        tables = self._query_api.query(flux, org=self._org)
        for table in tables:
            for record in table.records:
                return record.get_value() or 0
        return 0

    def close(self) -> None:
        """Flush all buffered writes and close client."""
        self._write_api.close()
        self._client.close()
        logger.info("InfluxDB client closed.")


# ─────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────

_influx_instance: Optional[InfluxManager] = None


def get_influx() -> InfluxManager:
    """
    Returns the shared InfluxManager singleton.
    Call once at app startup; reuse across requests.
    """
    global _influx_instance
    if _influx_instance is None:
        _influx_instance = InfluxManager()
    return _influx_instance


def close_influx() -> None:
    """Call on app shutdown to flush and close the client."""
    global _influx_instance
    if _influx_instance:
        _influx_instance.close()
        _influx_instance = None
