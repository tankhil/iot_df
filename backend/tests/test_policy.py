from datetime import UTC, datetime, timedelta

from app.policy.engine import PolicyContext, choose_policy


def test_policy_threshold_not_reached_does_not_quarantine() -> None:
    result = choose_policy(PolicyContext("camera-01", 79, 3, False))
    assert "temporary_quarantine" not in result.actions
    assert result.actions == ["create_alert", "rate_limit_simulated"]


def test_policy_requires_three_consecutive_high_for_quarantine() -> None:
    one = choose_policy(PolicyContext("camera-01", 92, 1, False))
    three = choose_policy(PolicyContext("camera-01", 92, 3, False))
    assert "temporary_quarantine" not in one.actions
    assert "temporary_quarantine" in three.actions
    assert "consecutive high-risk assessments" in three.rationale


def test_policy_one_abnormal_sample_does_not_quarantine() -> None:
    result = choose_policy(PolicyContext("camera-01", 100, 1, False))
    assert "temporary_quarantine" not in result.actions
    assert result.actions == ["create_alert", "increase_monitoring"]


def test_policy_cooldown_monitors_only() -> None:
    now = datetime.now(UTC)
    result = choose_policy(
        PolicyContext("camera-01", 92, 3, False, last_action_at=now - timedelta(seconds=1)),
        now=now,
    )
    assert result.actions == ["monitor"]


def test_policy_already_quarantined_is_not_quarantined_again() -> None:
    result = choose_policy(PolicyContext("camera-01", 100, 5, True))
    assert "temporary_quarantine" not in result.actions
    assert result.actions == ["retain_quarantine"]


def test_policy_one_healthy_sample_does_not_restore_early() -> None:
    result = choose_policy(PolicyContext("camera-01", 10, 0, True, consecutive_low_count=1))
    assert "restore_access" not in result.actions
    assert result.actions == ["retain_quarantine", "schedule_health_check"]


def test_policy_restore_when_quarantined_and_sustained_safe() -> None:
    result = choose_policy(PolicyContext("camera-01", 10, 0, True, consecutive_low_count=3))
    assert result.actions == ["restore_access"]


def test_policy_already_active_is_not_restored_again() -> None:
    result = choose_policy(PolicyContext("camera-01", 10, 0, False, consecutive_low_count=3))
    assert "restore_access" not in result.actions
    assert result.actions == ["monitor"]
