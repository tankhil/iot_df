import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.detection.isolation_forest import (
    load_model,
    save_model,
    train_isolation_forest,
)
from app.features.extraction import FEATURE_NAMES
from app.models import FeatureWindow, ModelVersion
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MODEL_NAME = "IsolationForest"
MODEL_TYPE = "IsolationForest"
FEATURE_SCHEMA_VERSION = "features-v1"
TRAINING_CODE_VERSION = "isolation-forest-training-v2"
MODEL_FORMAT_VERSION = "joblib-anomaly-model-v1"
HYPERPARAMETERS: dict[str, int | float] = {"contamination": 0.08, "n_estimators": 100}


@dataclass(frozen=True)
class ModelIdentity:
    scope: str
    fingerprint: str
    dataset_hash: str
    artifact_path: Path
    feature_schema: list[str]
    hyperparameters: dict[str, int | float]
    random_seed: int


def _json_hash(payload: dict[str, Any] | list[Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _sanitize_scope(scope: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", scope).strip("._-").lower()
    return sanitized or "global"


def _safe_artifact_path(model_dir: Path, scope: str, fingerprint: str) -> Path:
    model_dir = model_dir.resolve()
    filename = f"isolation_forest_{_sanitize_scope(scope)}_{fingerprint[:16]}.joblib"
    path = (model_dir / filename).resolve()
    if path.parent != model_dir:
        raise ValueError("Refusing to write model artifact outside MODEL_DIR")
    return path


def _ordered_rows(rows: list[FeatureWindow]) -> list[FeatureWindow]:
    return sorted(
        rows,
        key=lambda row: (
            row.device_type,
            row.device_id,
            row.window_start,
            row.window_end,
            row.id,
        ),
    )


def _dataset_hash(rows: list[FeatureWindow]) -> str:
    payload = []
    for row in _ordered_rows(rows):
        payload.append(
            {
                "device_id": row.device_id,
                "device_type": row.device_type,
                "window_start": _iso(row.window_start),
                "window_end": _iso(row.window_end),
                "features": {name: float(row.features.get(name, 0.0) or 0.0) for name in FEATURE_NAMES},
            }
        )
    return _json_hash(payload)


def build_model_identity(rows: list[FeatureWindow], scope: str, model_dir: Path, random_seed: int) -> ModelIdentity:
    dataset_hash = _dataset_hash(rows)
    feature_schema = list(FEATURE_NAMES)
    hyperparameters = dict(sorted(HYPERPARAMETERS.items()))
    payload = {
        "model_type": MODEL_TYPE,
        "scope": scope,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema": feature_schema,
        "training_dataset_hash": dataset_hash,
        "hyperparameters": hyperparameters,
        "random_seed": random_seed,
        "training_code_version": TRAINING_CODE_VERSION,
        "model_format_version": MODEL_FORMAT_VERSION,
    }
    fingerprint = _json_hash(payload)
    return ModelIdentity(
        scope=scope,
        fingerprint=fingerprint,
        dataset_hash=dataset_hash,
        artifact_path=_safe_artifact_path(model_dir, scope, fingerprint),
        feature_schema=feature_schema,
        hyperparameters=hyperparameters,
        random_seed=random_seed,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_artifact(path: Path, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    if expected_sha256 and _sha256_file(path) != expected_sha256:
        return False
    try:
        load_model(path)
    except Exception:  # noqa: BLE001
        return False
    return True


def _atomic_save_model(rows: list[FeatureWindow], identity: ModelIdentity) -> str:
    identity.artifact_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{identity.artifact_path.stem}.",
            suffix=".tmp",
            dir=identity.artifact_path.parent,
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name
        model = train_isolation_forest(
            [row.features for row in _ordered_rows(rows)],
            random_seed=identity.random_seed,
            contamination=float(identity.hyperparameters["contamination"]),
        )
        model.metadata.update(
            {
                "model_type": MODEL_TYPE,
                "identity_fingerprint": identity.fingerprint,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "training_dataset_hash": identity.dataset_hash,
                "training_code_version": TRAINING_CODE_VERSION,
                "model_format_version": MODEL_FORMAT_VERSION,
                "hyperparameters": identity.hyperparameters,
                "random_seed": identity.random_seed,
            }
        )
        save_model(model, temp_name)
        os.replace(temp_name, identity.artifact_path)
        temp_name = ""
        return _sha256_file(identity.artifact_path)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def _apply_metadata(row: ModelVersion, identity: ModelIdentity, artifact_sha256: str, training_rows: int) -> None:
    row.name = MODEL_NAME
    row.device_type = identity.scope
    row.artifact_path = str(identity.artifact_path)
    row.identity_fingerprint = identity.fingerprint
    row.feature_schema_version = FEATURE_SCHEMA_VERSION
    row.training_dataset_hash = identity.dataset_hash
    row.hyperparameters = {
        "model_type": MODEL_TYPE,
        "model_format_version": MODEL_FORMAT_VERSION,
        "feature_schema": identity.feature_schema,
        **identity.hyperparameters,
        "random_seed": identity.random_seed,
    }
    row.training_code_version = TRAINING_CODE_VERSION
    row.artifact_sha256 = artifact_sha256
    row.training_rows = training_rows
    row.metrics = {"preliminary": True, "note": "Trained on simulated normal-behavior windows"}
    row.active = True
    row.updated_at = datetime.now(UTC)


def _new_model_version(identity: ModelIdentity, artifact_sha256: str, training_rows: int) -> ModelVersion:
    row = ModelVersion(
        name=MODEL_NAME,
        device_type=identity.scope,
        artifact_path=str(identity.artifact_path),
        identity_fingerprint=identity.fingerprint,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        training_dataset_hash=identity.dataset_hash,
        hyperparameters={},
        training_code_version=TRAINING_CODE_VERSION,
        artifact_sha256=artifact_sha256,
        training_rows=training_rows,
        metrics={},
        active=True,
    )
    _apply_metadata(row, identity, artifact_sha256, training_rows)
    return row


def train_scope(
    db: Session,
    rows: list[FeatureWindow],
    scope: str,
    model_dir: Path,
    random_seed: int,
) -> str:
    identity = build_model_identity(rows, scope, model_dir, random_seed)
    existing = db.scalar(
        select(ModelVersion).where(ModelVersion.identity_fingerprint == identity.fingerprint)
    )
    if existing:
        if _valid_artifact(identity.artifact_path, existing.artifact_sha256):
            return "reused"
        artifact_sha256 = _atomic_save_model(rows, identity)
        _apply_metadata(existing, identity, artifact_sha256, len(rows))
        db.commit()
        return "rebuilt"

    artifact_sha256 = _atomic_save_model(rows, identity)
    row = _new_model_version(identity, artifact_sha256, len(rows))
    db.add(row)
    try:
        db.commit()
        return "created"
    except IntegrityError:
        db.rollback()
        raced = db.scalar(
            select(ModelVersion).where(ModelVersion.identity_fingerprint == identity.fingerprint)
        )
        if raced and _valid_artifact(identity.artifact_path, raced.artifact_sha256):
            return "reused"
        if raced:
            artifact_sha256 = _atomic_save_model(rows, identity)
            _apply_metadata(raced, identity, artifact_sha256, len(rows))
            db.commit()
            return "rebuilt"
        raise
    except Exception:
        db.rollback()
        raise


def train_all(db: Session, model_dir: Path, random_seed: int, min_samples_per_type: int) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    rows = _ordered_rows(list(db.scalars(select(FeatureWindow))))
    if len(rows) < 5:
        raise SystemExit("Need at least 5 feature windows. Run simulators or make demo first.")

    scopes: list[tuple[str, list[FeatureWindow]]] = [("global", rows)]
    by_type: dict[str, list[FeatureWindow]] = defaultdict(list)
    for row in rows:
        by_type[row.device_type].append(row)
    for device_type in sorted(by_type):
        type_rows = _ordered_rows(by_type[device_type])
        if len(type_rows) >= min_samples_per_type:
            scopes.append((device_type, type_rows))
        else:
            counters["skipped"] += 1

    failures: list[dict[str, str]] = []
    for scope, scope_rows in scopes:
        try:
            result = train_scope(db, scope_rows, scope, model_dir, random_seed)
            counters[result] += 1
            if result == "rebuilt":
                counters["updated"] += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            counters["failed"] += 1
            failures.append({"scope": scope, "error": exc.__class__.__name__})

    return {
        "trained_from_feature_windows": len(rows),
        "model_dir": str(model_dir),
        "created": counters["created"],
        "reused": counters["reused"],
        "rebuilt": counters["rebuilt"],
        "updated": counters["updated"],
        "skipped": counters["skipped"],
        "failed": counters["failed"],
        "synthetic": True,
        "failures": failures,
    }


def main() -> None:
    settings = get_settings()
    model_dir = Path(settings.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        result = train_all(
            db,
            model_dir,
            random_seed=settings.random_seed,
            min_samples_per_type=settings.model_min_samples_per_type,
        )
    print(result)
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
