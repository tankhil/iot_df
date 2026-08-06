from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Adaptive IoT Defense Platform"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://iot:iot@postgres:5432/iot_defense"
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_topic: str = "iot/+/telemetry"
    admin_api_key: str = Field(default="change-me-local-demo-only", min_length=12)
    cors_origins: list[str] = ["http://localhost:5173"]
    model_dir: str = "/app/models"
    model_min_samples_per_type: int = 20
    random_seed: int = 42
    risk_normal_max: int = 29
    risk_suspicious_max: int = 59
    risk_high_max: int = 79
    consecutive_high_required: int = 3
    quarantine_duration_seconds: int = 120
    quarantine_max_seconds: int = 900
    action_cooldown_seconds: int = 30
    restore_risk_threshold: int = 30
    max_payload_bytes: int = 16_384
    sensitive_rate_limit_per_minute: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        return ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
