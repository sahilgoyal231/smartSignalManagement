"""
Shared configuration module for all cloud services.
Reads from environment variables (.env file or OS environment).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # Project
    project_name: str = "SmartSignalSystem"
    environment: str = "development"
    log_level: str = "INFO"

    # PostgreSQL
    postgres_url: str = "sqlite+aiosqlite:///dev.db"

    # InfluxDB
    influx_url: str = "http://localhost:8086"
    influx_token: str
    influx_org: str = "SmartSignal"
    influx_bucket: str = "telemetry"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # MQTT
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 8883
    mqtt_broker_user: str
    mqtt_broker_password: str
    mqtt_client_id_prefix: str = "cloud-service"

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "RS256"
    jwt_expire_minutes: int = 60


    # AWS
    aws_region: str = "ap-south-1"
    aws_s3_bucket: str = "smart-signal-assets"



    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns cached settings instance (loaded once at startup)."""
    return Settings()
