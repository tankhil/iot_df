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
    consecutive_low_count: int = 0
    minimum_quarantine_elapsed: bool = True
    has_completed_quarantine_action: bool = True
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
        elapsed = (_as_utc(now) - _as_utc(context.last_action_at)).total_seconds()
        if elapsed < settings.action_cooldown_seconds:
            return PolicyResult(["monitor"], "Action cooldown active; monitoring only")

    if context.currently_quarantined:
        if context.risk_score < settings.restore_risk_threshold:
            if not context.has_completed_quarantine_action:
                return PolicyResult(["retain_quarantine"], "Recovery blocked until simulated quarantine action completes")
            if not context.minimum_quarantine_elapsed:
                return PolicyResult(
                    ["retain_quarantine", "schedule_health_check"],
                    "Recovery blocked until minimum quarantine duration elapses",
                )
            if context.consecutive_low_count >= settings.recovery_healthy_required:
                return PolicyResult(
                    ["restore_access"],
                    "Trusted recovery observations are below restore threshold for required consecutive windows",
                )
            return PolicyResult(
                ["retain_quarantine", "schedule_health_check"],
                "Trusted recovery observation is below restore threshold; waiting for consecutive confirmation",
            )
        if context.quarantine_expires_at and _as_utc(now) >= _as_utc(context.quarantine_expires_at):
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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
