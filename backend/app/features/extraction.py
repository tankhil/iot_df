from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from statistics import mean, pstdev
from typing import Any

FEATURE_NAMES = [
    "messages_per_minute",
    "average_message_size",
    "message_size_std",
    "failed_login_count",
    "unique_destination_count",
    "unknown_destination_count",
    "unauthorized_topic_count",
    "connection_frequency",
    "traffic_change_ratio",
    "time_since_last_message",
]


@dataclass(frozen=True)
class EventLike:
    timestamp: datetime
    message_size: int
    destination: str
    auth_success: bool
    topic: str


def _safe_float(value: float) -> float:
    if not isfinite(value):
        return 0.0
    return round(float(value), 6)


def extract_features(
    events: list[EventLike],
    window_start: datetime,
    window_end: datetime,
    *,
    allowed_destinations: set[str] | None = None,
    allowed_topic_prefixes: tuple[str, ...] = ("iot/",),
    baseline_messages_per_minute: float | None = None,
) -> dict[str, float]:
    window_start = _as_utc(window_start)
    window_end = _as_utc(window_end)
    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")

    allowed_destinations = allowed_destinations or {"mqtt-broker"}
    ordered = sorted(
        [event for event in events if window_start <= _as_utc(event.timestamp) <= window_end],
        key=lambda event: _as_utc(event.timestamp),
    )
    duration_seconds = max((window_end - window_start).total_seconds(), 1.0)
    duration_minutes = duration_seconds / 60.0
    count = len(ordered)
    sizes = [max(0, int(event.message_size)) for event in ordered]
    destinations = {event.destination for event in ordered if event.destination}
    failed = sum(1 for event in ordered if not event.auth_success)
    unknown_destinations = sum(1 for event in ordered if event.destination not in allowed_destinations)
    unauthorized_topics = sum(
        1 for event in ordered if not any(event.topic.startswith(prefix) for prefix in allowed_topic_prefixes)
    )
    messages_per_minute = count / duration_minutes
    baseline = baseline_messages_per_minute if baseline_messages_per_minute and baseline_messages_per_minute > 0 else messages_per_minute
    traffic_change_ratio = 0.0 if baseline <= 0 else max(0.0, (messages_per_minute - baseline) / baseline)
    last_message = _as_utc(ordered[-1].timestamp) if ordered else window_start
    time_since_last = max(0.0, (window_end - last_message).total_seconds())

    features = {
        "messages_per_minute": messages_per_minute,
        "average_message_size": mean(sizes) if sizes else 0.0,
        "message_size_std": pstdev(sizes) if len(sizes) > 1 else 0.0,
        "failed_login_count": float(failed),
        "unique_destination_count": float(len(destinations)),
        "unknown_destination_count": float(unknown_destinations),
        "unauthorized_topic_count": float(unauthorized_topics),
        "connection_frequency": count / duration_seconds,
        "traffic_change_ratio": traffic_change_ratio,
        "time_since_last_message": time_since_last,
    }
    return {name: _safe_float(features.get(name, 0.0)) for name in FEATURE_NAMES}


def features_to_vector(features: dict[str, Any]) -> list[float]:
    return [_safe_float(float(features.get(name, 0.0) or 0.0)) for name in FEATURE_NAMES]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
