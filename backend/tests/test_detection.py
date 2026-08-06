from app.detection.isolation_forest import normalize_raw_score, safe_fallback_detection


def test_normalize_raw_score_bounds() -> None:
    assert normalize_raw_score(1.0) == 0.0
    assert normalize_raw_score(-1.0) == 1.0
    assert 0.0 <= normalize_raw_score(-0.1) <= 1.0


def test_safe_fallback_never_anomaly() -> None:
    result = safe_fallback_detection()
    assert result.anomaly_score == 0.0
    assert result.is_anomaly is False
    assert result.explanation["fallback"] is True
