from collections import defaultdict
from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.detection.isolation_forest import save_model, train_isolation_forest
from app.models import FeatureWindow, ModelVersion
from sqlalchemy import select
from sqlalchemy.orm import Session


def train_scope(rows: list[FeatureWindow], device_type: str, model_dir: Path) -> ModelVersion:
    settings = get_settings()
    model = train_isolation_forest([row.features for row in rows], random_seed=settings.random_seed)
    path = model_dir / f"isolation_forest_{device_type}.joblib"
    save_model(model, path)
    return ModelVersion(
        name="IsolationForest",
        device_type=device_type,
        artifact_path=str(path),
        training_rows=len(rows),
        metrics={"preliminary": True, "note": "Trained on simulated normal-behavior windows"},
        active=True,
    )


def upsert_model_version(db: Session, model_version: ModelVersion) -> str:
    existing = db.scalar(
        select(ModelVersion).where(
            ModelVersion.name == model_version.name,
            ModelVersion.device_type == model_version.device_type,
            ModelVersion.artifact_path == model_version.artifact_path,
            ModelVersion.active.is_(True),
        )
    )
    if existing:
        existing.training_rows = model_version.training_rows
        existing.metrics = model_version.metrics
        return "updated"
    db.add(model_version)
    return "created"


def main() -> None:
    settings = get_settings()
    model_dir = Path(settings.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        created = 0
        updated = 0
        rows = list(db.scalars(select(FeatureWindow)))
        if len(rows) < 5:
            raise SystemExit("Need at least 5 feature windows. Run simulators or make demo first.")
        if upsert_model_version(db, train_scope(rows, "global", model_dir)) == "created":
            created += 1
        else:
            updated += 1
        by_type: dict[str, list[FeatureWindow]] = defaultdict(list)
        for row in rows:
            by_type[row.device_type].append(row)
        for device_type, type_rows in by_type.items():
            if len(type_rows) >= settings.model_min_samples_per_type:
                if upsert_model_version(db, train_scope(type_rows, device_type, model_dir)) == "created":
                    created += 1
                else:
                    updated += 1
        db.commit()
    print(
        {
            "trained_from_feature_windows": len(rows),
            "model_dir": str(model_dir),
            "created": created,
            "updated": updated,
            "synthetic": True,
        }
    )


if __name__ == "__main__":
    main()
