from dataclasses import dataclass
from typing import TypedDict

from app.core.config import get_settings
from app.models import RiskLevel


class RiskReason(TypedDict):
    signal: str
    contribution: int
    explanation: str


@dataclass(frozen=True)
class RiskResult:
    risk_score: int
    level: RiskLevel
    reasons: list[RiskReason]


def risk_level(score: int) -> RiskLevel:
    settings = get_settings()
    if score <= settings.risk_normal_max:
        return RiskLevel.normal
    if score <= settings.risk_suspicious_max:
        return RiskLevel.suspicious
    if score <= settings.risk_high_max:
        return RiskLevel.high
    return RiskLevel.critical


def calculate_risk(
    *,
    device_id: str,
    anomaly_score: float,
    features: dict[str, float],
    recent_high_count: int = 0,
) -> RiskResult:
    reasons: list[RiskReason] = []

    def add(signal: str, contribution: int, explanation: str) -> None:
        if contribution > 0:
            reasons.append(
                {
                    "signal": signal,
                    "contribution": int(contribution),
                    "explanation": explanation,
                }
            )

    ml_contribution = round(max(0.0, min(1.0, anomaly_score)) * 35)
    add("ml_anomaly", ml_contribution, f"Isolation Forest anomaly score is {anomaly_score:.2f}")

    traffic_ratio = max(0.0, features.get("traffic_change_ratio", 0.0))
    add(
        "traffic_spike",
        min(20, round(traffic_ratio * 20)),
        f"Traffic increased by {traffic_ratio * 100:.0f}% from baseline",
    )

    failed = int(features.get("failed_login_count", 0))
    add("failed_auth", min(15, failed * 5), f"{failed} failed authentication events in window")

    unknown = int(features.get("unknown_destination_count", 0))
    add(
        "unknown_destination",
        min(20, unknown * 20),
        "Device contacted an unapproved simulated destination",
    )

    unauthorized = int(features.get("unauthorized_topic_count", 0))
    add("unauthorized_topic", min(15, unauthorized * 15), "Unauthorized MQTT topic access observed")

    add(
        "repeated_recent_anomalies",
        min(15, max(0, recent_high_count) * 5),
        f"{recent_high_count} recent high-risk assessments for {device_id}",
    )

    total = min(100, sum(int(reason["contribution"]) for reason in reasons))
    if total < sum(int(reason["contribution"]) for reason in reasons):
        overflow = sum(int(reason["contribution"]) for reason in reasons) - 100
        for reason in reversed(reasons):
            contribution = int(reason["contribution"])
            reduction = min(contribution, overflow)
            reason["contribution"] = contribution - reduction
            overflow -= reduction
            if overflow == 0:
                break
        reasons = [reason for reason in reasons if int(reason["contribution"]) > 0]
    return RiskResult(risk_score=total, level=risk_level(total), reasons=reasons)
