from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    detail: str


class RootResponse(BaseModel):
    name: str = "AI Adaptive IoT Defense Platform"
    version: str = "0.1.0"
    status: str = "running"
    documentation: str = "/docs"
    health: str = "/health"
    readiness: str = "/ready"


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str = Field(examples=["api"])


class ReadinessResponse(BaseModel):
    status: str = Field(examples=["ready"])
    database: str = Field(examples=["ok"])


class SafeAttackScenario(StrEnum):
    mqtt_flood = "mqtt_flood"
    auth_failures = "auth_failures"
    unauthorized_topic = "unauthorized_topic"
    unknown_destination = "unknown_destination"


class TelemetryIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    device_type: str = Field(min_length=1, max_length=80)
    timestamp: datetime
    topic: str = Field(min_length=1, max_length=255)
    message_size: int = Field(ge=0, le=16384)
    destination: str = Field(min_length=1, max_length=120)
    auth_success: bool = True
    value: float | None = None


class Page(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class AttackRequest(BaseModel):
    device_id: str = "camera-01"
    intensity: int = Field(default=10, ge=1, le=100)
    seed: int = 42


class ManualOverride(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AttackSimulationResponse(BaseModel):
    status: str
    scenario: SafeAttackScenario | None = None
    simulated: bool = True
    options: dict[str, Any] | None = None
    reason: str | None = None
    allowed: list[str] | None = None


class ManualOverrideResponse(BaseModel):
    actions: list[dict[str, Any]]
    reason: str


class DeviceSummary(BaseModel):
    id: str
    device_type: str
    status: str
    allowed_destinations: list[str]
    created_at: str
    updated_at: str


class DeviceDetailResponse(BaseModel):
    device: dict[str, Any]
    current_risk: dict[str, Any] | None = None
    quarantine: dict[str, Any] | None = None


class CurrentRiskResponse(BaseModel):
    device_id: str
    device_type: str
    status: str
    risk: dict[str, Any] | None = None


class TelemetryCreateResponse(BaseModel):
    telemetry: dict[str, Any]
    risk: dict[str, Any]


class GenericDictResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
