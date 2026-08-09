from functools import lru_cache

from pydantic import Field, field_validator, model_validator
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
    recovery_healthy_required: int = 3
    minimum_quarantine_seconds: int = 30
    quarantine_duration_seconds: int = 120
    quarantine_max_seconds: int = 900
    action_cooldown_seconds: int = 30
    restore_risk_threshold: int = 30
    max_payload_bytes: int = 16_384
    sensitive_rate_limit_per_minute: int = 30
    e2e_consecutive_high_required: int | None = Field(default=None, ge=1)
    e2e_recovery_healthy_required: int | None = Field(default=None, ge=1)
    e2e_minimum_quarantine_seconds: int | None = Field(default=None, ge=0)
    e2e_quarantine_duration_seconds: int | None = Field(default=None, ge=1)
    e2e_quarantine_max_seconds: int | None = Field(default=None, ge=1)
    e2e_action_cooldown_seconds: int | None = Field(default=None, ge=0)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        return ["http://localhost:5173"]

    @model_validator(mode="after")
    def apply_e2e_overrides(self) -> "Settings":
        overrides = {
            "consecutive_high_required": self.e2e_consecutive_high_required,
            "recovery_healthy_required": self.e2e_recovery_healthy_required,
            "minimum_quarantine_seconds": self.e2e_minimum_quarantine_seconds,
            "quarantine_duration_seconds": self.e2e_quarantine_duration_seconds,
            "quarantine_max_seconds": self.e2e_quarantine_max_seconds,
            "action_cooldown_seconds": self.e2e_action_cooldown_seconds,
        }
        enabled = {name: value for name, value in overrides.items() if value is not None}
        if enabled and self.environment != "e2e":
            names = ", ".join(sorted(f"e2e_{name}" for name in enabled))
            raise ValueError(f"E2E policy overrides require ENVIRONMENT=e2e: {names}")
        if self.environment == "e2e":
            for name, value in enabled.items():
                setattr(self, name, value)
        if self.quarantine_max_seconds < self.quarantine_duration_seconds:
            raise ValueError("quarantine_max_seconds must be >= quarantine_duration_seconds")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
