from datetime import UTC, datetime, timedelta

import pytest

from app.features.extraction import EventLike, extract_features, features_to_vector


def test_extract_features_handles_empty_window() -> None:
    start = datetime(2026, 8, 6, tzinfo=UTC)
    features = extract_features([], start, start + timedelta(minutes=1))
    assert features["messages_per_minute"] == 0.0
    assert features["time_since_last_message"] == 60.0
    assert len(features_to_vector(features)) == 10


def test_extract_features_counts_security_signals() -> None:
    start = datetime(2026, 8, 6, tzinfo=UTC)
    event = EventLike(
        timestamp=start + timedelta(seconds=5),
        message_size=100,
        destination="unknown",
        auth_success=False,
        topic="iot/admin/shadow",
    )
    features = extract_features([event], start, start + timedelta(minutes=1), baseline_messages_per_minute=0.5)
    assert features["messages_per_minute"] == 1.0
    assert features["failed_login_count"] == 1.0
    assert features["unknown_destination_count"] == 1.0
    assert features["unauthorized_topic_count"] == 0.0
    assert features["traffic_change_ratio"] == 1.0


def test_extract_features_rejects_bad_window() -> None:
    start = datetime(2026, 8, 6, tzinfo=UTC)
    with pytest.raises(ValueError):
        extract_features([], start, start)
