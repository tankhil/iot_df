from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings

ALLOW_LISTED_ACTIONS = {
    "monitor",
    "increase_monitoring",
    "create_alert",
    "rate_limit_simulated",
    "temporary_quarantine",
    "schedule_health_check",
    "restore_access",
    "retain_quarantine",
}


@dataclass(frozen=True)
class PolicyContext:
    device_id: str
    risk_score: int
    consecutive_high_count: int
    currently_quarantined: bool
    last_action_at: datetime | None = None
    quarantine_expires_at: datetime | None = None


@dataclass(frozen=True)
class PolicyResult:
    actions: list[str]
    rationale: str


def choose_policy(context: PolicyContext, *, now: datetime | None = None) -> PolicyResult:
    settings = get_settings()
    now = now or datetime.now(UTC)
    if context.last_action_at:
        elapsed = (now - context.last_action_at).total_seconds()
        if elapsed < settings.action_cooldown_seconds:
            return PolicyResult(["monitor"], "Action cooldown active; monitoring only")

    if context.currently_quarantined:
        if context.risk_score < settings.restore_risk_threshold:
            return PolicyResult(["restore_access"], "Risk is below restore threshold")
        if context.quarantine_expires_at and now >= context.quarantine_expires_at:
            return PolicyResult(["retain_quarantine", "schedule_health_check"], "Risk remains elevated after quarantine interval")
        return PolicyResult(["retain_quarantine"], "Device remains quarantined pending re-evaluation")

    if context.risk_score <= settings.risk_normal_max:
        return PolicyResult(["monitor"], "Risk is normal")
    if context.risk_score <= settings.risk_suspicious_max:
        return PolicyResult(["create_alert", "increase_monitoring"], "Risk is suspicious")
    if context.risk_score <= settings.risk_high_max:
        return PolicyResult(["create_alert", "rate_limit_simulated"], "Risk is high")
    if context.consecutive_high_count >= settings.consecutive_high_required:
        return PolicyResult(
            ["create_alert", "temporary_quarantine", "schedule_health_check"],
            "Critical risk with required consecutive high-risk assessments",
        )
    return PolicyResult(["create_alert", "increase_monitoring"], "Critical risk observed; waiting for consecutive confirmation")


def quarantine_expiry(now: datetime | None = None) -> tuple[datetime, datetime]:
    settings = get_settings()
    now = now or datetime.now(UTC)
    return (
        now + timedelta(seconds=settings.quarantine_duration_seconds),
        now + timedelta(seconds=settings.quarantine_max_seconds),
    )
