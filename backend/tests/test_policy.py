from datetime import UTC, datetime, timedelta

from app.policy.engine import PolicyContext, choose_policy


def test_policy_requires_three_consecutive_high_for_quarantine() -> None:
    one = choose_policy(PolicyContext("camera-01", 92, 1, False))
    three = choose_policy(PolicyContext("camera-01", 92, 3, False))
    assert "temporary_quarantine" not in one.actions
    assert "temporary_quarantine" in three.actions


def test_policy_cooldown_monitors_only() -> None:
    now = datetime.now(UTC)
    result = choose_policy(
        PolicyContext("camera-01", 92, 3, False, last_action_at=now - timedelta(seconds=1)),
        now=now,
    )
    assert result.actions == ["monitor"]


def test_policy_restore_when_quarantined_and_safe() -> None:
    result = choose_policy(PolicyContext("camera-01", 10, 0, True))
    assert result.actions == ["restore_access"]
