"""
InfluxDB Setup & Initialisation Script
========================================
Run once to:
  1. Create the 'telemetry' bucket (if not exists)
  2. Set retention policy (30 days for raw, 1 year for aggregated)
  3. Create downsampling tasks (hourly + daily aggregates)
  4. Verify connection and print bucket info

Usage:
    python infra/scripts/setup_influx.py

Requirements:
    INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG set in .env
"""
import sys
import os
from datetime import timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dotenv import load_dotenv
load_dotenv()

from influxdb_client import InfluxDBClient, BucketRetentionRules
from influxdb_client.client.exceptions import InfluxDBError
from loguru import logger

INFLUX_URL    = os.environ["INFLUX_URL"]
INFLUX_TOKEN  = os.environ["INFLUX_TOKEN"]
INFLUX_ORG    = os.environ["INFLUX_ORG"]
RAW_BUCKET    = os.environ.get("INFLUX_BUCKET", "telemetry")
AGG_BUCKET    = "telemetry_aggregated"

# Retention: 30 days raw telemetry (high resolution)
RAW_RETENTION_SECONDS = int(timedelta(days=30).total_seconds())
# Retention: 1 year aggregated (hourly/daily summaries)
AGG_RETENTION_SECONDS = int(timedelta(days=365).total_seconds())

# ─────────────────────────────────────────────────────────────
# Downsampling tasks (Flux)
# Runs inside InfluxDB to compress old data into hourly averages
# ─────────────────────────────────────────────────────────────

HOURLY_DOWNSAMPLE_TASK = f"""
option task = {{
  name: "hourly_vehicle_downsample",
  every: 1h,
  offset: 5m
}}

from(bucket: "{RAW_BUCKET}")
  |> range(start: -2h, stop: -1h)
  |> filter(fn: (r) => r._measurement == "vehicle_telemetry")
  |> filter(fn: (r) => r._field == "speed_kmh" or r._field == "lat" or r._field == "lon")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> set(key: "_measurement", value: "vehicle_telemetry_hourly")
  |> to(bucket: "{AGG_BUCKET}")
"""

DAILY_NODE_SUMMARY_TASK = f"""
option task = {{
  name: "daily_node_summary",
  every: 24h,
  offset: 15m
}}

from(bucket: "{RAW_BUCKET}")
  |> range(start: -2d, stop: -1d)
  |> filter(fn: (r) => r._measurement == "node_telemetry")
  |> filter(fn: (r) => r._field == "cpu_pct" or r._field == "temp_c"
                        or r._field == "preemptions_today")
  |> aggregateWindow(every: 24h, fn: mean, createEmpty: false)
  |> set(key: "_measurement", value: "node_daily_summary")
  |> to(bucket: "{AGG_BUCKET}")
"""

DAILY_PREEMPTION_SUMMARY_TASK = f"""
option task = {{
  name: "daily_preemption_kpi",
  every: 24h,
  offset: 20m
}}

from(bucket: "{RAW_BUCKET}")
  |> range(start: -2d, stop: -1d)
  |> filter(fn: (r) => r._measurement == "preemption_metrics")
  |> filter(fn: (r) => r._field == "eta_accuracy_pct"
                        or r._field == "green_hold_duration_s"
                        or r._field == "sensor_confidence")
  |> aggregateWindow(every: 24h, fn: mean, createEmpty: false)
  |> set(key: "_measurement", value: "preemption_daily_kpi")
  |> to(bucket: "{AGG_BUCKET}")
"""


def run_setup() -> None:
    logger.info(f"Connecting to InfluxDB at {INFLUX_URL} ...")

    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
        # ── Health check ────────────────────────────────────
        if not client.ping():
            logger.error("InfluxDB is not reachable. Check INFLUX_URL and token.")
            sys.exit(1)
        logger.success("✅ InfluxDB connection OK")

        buckets_api = client.buckets_api()
        tasks_api   = client.tasks_api()
        orgs_api    = client.organizations_api()

        # Get org ID
        org_obj = orgs_api.find_organizations(org=INFLUX_ORG)
        if not org_obj:
            logger.error(f"Org '{INFLUX_ORG}' not found.")
            sys.exit(1)
        org_id = org_obj[0].id
        logger.info(f"Org: {INFLUX_ORG} (id={org_id})")

        # ── Create raw telemetry bucket ──────────────────────
        existing = buckets_api.find_bucket_by_name(RAW_BUCKET)
        if existing:
            logger.info(f"Bucket '{RAW_BUCKET}' already exists — skipping create.")
        else:
            retention = BucketRetentionRules(
                type="expire",
                every_seconds=RAW_RETENTION_SECONDS
            )
            buckets_api.create_bucket(
                bucket_name=RAW_BUCKET,
                retention_rules=retention,
                org_id=org_id,
            )
            logger.success(f"✅ Created bucket '{RAW_BUCKET}' (30-day retention)")

        # ── Create aggregated bucket ─────────────────────────
        existing_agg = buckets_api.find_bucket_by_name(AGG_BUCKET)
        if existing_agg:
            logger.info(f"Bucket '{AGG_BUCKET}' already exists — skipping create.")
        else:
            agg_retention = BucketRetentionRules(
                type="expire",
                every_seconds=AGG_RETENTION_SECONDS
            )
            buckets_api.create_bucket(
                bucket_name=AGG_BUCKET,
                retention_rules=agg_retention,
                org_id=org_id,
            )
            logger.success(f"✅ Created bucket '{AGG_BUCKET}' (1-year retention)")

        # ── Create downsampling tasks ────────────────────────
        tasks = {
            "hourly_vehicle_downsample":  HOURLY_DOWNSAMPLE_TASK,
            "daily_node_summary":          DAILY_NODE_SUMMARY_TASK,
            "daily_preemption_kpi":        DAILY_PREEMPTION_SUMMARY_TASK,
        }
        existing_tasks = {t.name for t in tasks_api.find_tasks(org_id=org_id)}

        for name, flux in tasks.items():
            if name in existing_tasks:
                logger.info(f"Task '{name}' already exists — skipping.")
            else:
                tasks_api.create_task_every(
                    name=name,
                    flux=flux,
                    every="1h" if "hourly" in name else "24h",
                    organization=INFLUX_ORG,
                )
                logger.success(f"✅ Created downsampling task: {name}")

        logger.success("\n🎉 InfluxDB setup complete!")
        logger.info(f"   Raw bucket:  {RAW_BUCKET} (30-day retention)")
        logger.info(f"   Agg bucket:  {AGG_BUCKET} (1-year retention)")
        logger.info(f"   Tasks:       {', '.join(tasks.keys())}")


if __name__ == "__main__":
    run_setup()
