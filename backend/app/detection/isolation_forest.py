from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.features.extraction import FEATURE_NAMES, features_to_vector


@dataclass(frozen=True)
class DetectionResult:
    anomaly_score: float
    is_anomaly: bool
    explanation: dict[str, Any]


def normalize_raw_score(raw_score: float, *, low: float = -0.25, high: float = 0.15) -> float:
    # IsolationForest decision_function is higher for normal points. Invert into risk-like 0..1.
    if high <= low:
        return 0.0
    normalized = (high - raw_score) / (high - low)
    return round(max(0.0, min(1.0, normalized)), 6)


class AnomalyModel:
    def __init__(self, estimator: IsolationForest, metadata: dict[str, Any]) -> None:
        self.estimator = estimator
        self.metadata = metadata

    def predict_one(self, features: dict[str, float]) -> DetectionResult:
        vector = [features_to_vector(features)]
        raw = float(self.estimator.decision_function(vector)[0])
        score = normalize_raw_score(raw)
        is_anomaly = bool(self.estimator.predict(vector)[0] == -1 or score >= 0.7)
        top_features = sorted(features.items(), key=lambda item: abs(float(item[1])), reverse=True)[:3]
        return DetectionResult(
            anomaly_score=score,
            is_anomaly=is_anomaly,
            explanation={"raw_score": raw, "top_feature_values": dict(top_features)},
        )


def train_isolation_forest(
    rows: list[dict[str, float]],
    *,
    random_seed: int,
    contamination: float = 0.08,
) -> AnomalyModel:
    if len(rows) < 5:
        raise ValueError("At least 5 feature rows are required to train a model")
    frame = pd.DataFrame(rows)
    frame = frame.reindex(columns=FEATURE_NAMES, fill_value=0.0).fillna(0.0)
    estimator = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=random_seed,
    )
    estimator.fit(frame)
    return AnomalyModel(estimator, {"feature_names": FEATURE_NAMES, "rows": len(rows)})


def save_model(model: AnomalyModel, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": model.estimator, "metadata": model.metadata}, path)


def load_model(path: str | Path) -> AnomalyModel:
    payload = joblib.load(path)
    return AnomalyModel(payload["estimator"], payload.get("metadata", {}))


def safe_fallback_detection(reason: str = "model_missing") -> DetectionResult:
    return DetectionResult(
        anomaly_score=0.0,
        is_anomaly=False,
        explanation={"fallback": True, "reason": reason},
    )
