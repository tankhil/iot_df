from app.risk.engine import calculate_risk


def test_risk_contributions_sum_to_score() -> None:
    result = calculate_risk(
        device_id="camera-01",
        anomaly_score=1.0,
        features={
            "traffic_change_ratio": 5.4,
            "failed_login_count": 2,
            "unknown_destination_count": 1,
            "unauthorized_topic_count": 1,
        },
        recent_high_count=3,
    )
    assert result.risk_score == sum(int(reason["contribution"]) for reason in result.reasons)
    assert result.risk_score == 100
    assert result.level.value == "critical"


def test_low_risk_is_normal() -> None:
    result = calculate_risk(device_id="temp-01", anomaly_score=0.0, features={}, recent_high_count=0)
    assert result.risk_score == 0
    assert result.level.value == "normal"
