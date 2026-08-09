import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from scripts import evaluate_model, seed_demo_data, train_model
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.features.extraction import FEATURE_NAMES
from app.models import AuditLog, Device, FeatureWindow, ModelVersion, TelemetryEvent


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
    Base.metadata.drop_all(engine)


def feature_rows(count: int = 6, *, device_type: str = "smart_camera") -> list[FeatureWindow]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(count):
        rows.append(
            FeatureWindow(
                id=f"{device_type}-{index}",
                device_id=f"{device_type}-01",
                device_type=device_type,
                window_start=start + timedelta(minutes=index),
                window_end=start + timedelta(minutes=index + 1),
                features={name: float(index + offset + 1) for offset, name in enumerate(FEATURE_NAMES)},
            )
        )
    return rows


def add_feature_rows(db: Session, rows: list[FeatureWindow]) -> None:
    db.add_all(rows)
    db.commit()


def model_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(ModelVersion)) or 0)


def artifact_hashes(model_dir: Path) -> dict[str, str]:
    return {
        path.name: train_model._sha256_file(path)
        for path in sorted(model_dir.glob("*.joblib"))
    }


def test_demo_seed_run_twice_creates_no_duplicate_seed_records(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    db_session: Session,
) -> None:
    class DemoSettings:
        random_seed = 42

    def ingest_for_seed_test(db: Session, payload: object) -> TelemetryEvent:
        if db.get(Device, payload.device_id) is None:
            db.add(
                Device(
                    id=payload.device_id,
                    device_type=payload.device_type,
                    allowed_destinations=["health-check", "mqtt-broker"],
                )
            )
        event = TelemetryEvent(
            device_id=payload.device_id,
            device_type=payload.device_type,
            timestamp=payload.timestamp,
            topic=payload.topic,
            message_size=payload.message_size,
            destination=payload.destination,
            auth_success=payload.auth_success,
            value=payload.value,
            raw_payload=payload.model_dump(mode="json"),
            processed=True,
        )
        db.add(event)
        db.commit()
        return event

    monkeypatch.setattr(seed_demo_data, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(seed_demo_data, "get_settings", lambda: DemoSettings())
    monkeypatch.setattr(seed_demo_data, "ingest_telemetry", ingest_for_seed_test)
    monkeypatch.setattr(seed_demo_data, "run_detection_cycle", lambda *_args, **_kwargs: None)

    seed_demo_data.main()
    first = ast.literal_eval(capsys.readouterr().out.strip())
    telemetry_after_first = int(db_session.scalar(select(func.count()).select_from(TelemetryEvent)) or 0)

    seed_demo_data.main()
    second = ast.literal_eval(capsys.readouterr().out.strip())
    telemetry_after_second = int(db_session.scalar(select(func.count()).select_from(TelemetryEvent)) or 0)
    completed_markers = int(
        db_session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == seed_demo_data.SEED_COMPLETED_EVENT)
        )
        or 0
    )

    assert first["status"] == "seeded"
    assert first["created"] > 0
    assert second["status"] == "already_seeded"
    assert second["created"] == 0
    assert telemetry_after_second == telemetry_after_first
    assert completed_markers == 1


def test_training_run_twice_reuses_identical_model_rows_and_artifacts(
    db_session: Session,
    tmp_path: Path,
) -> None:
    add_feature_rows(db_session, feature_rows())

    first = train_model.train_all(db_session, tmp_path, random_seed=42, min_samples_per_type=5)
    first_rows = model_count(db_session)
    first_hashes = artifact_hashes(tmp_path)
    second = train_model.train_all(db_session, tmp_path, random_seed=42, min_samples_per_type=5)

    assert first["created"] == 2
    assert second["created"] == 0
    assert second["reused"] == 2
    assert model_count(db_session) == first_rows == 2
    assert artifact_hashes(tmp_path) == first_hashes


def test_changed_seed_creates_new_model_versions(db_session: Session, tmp_path: Path) -> None:
    add_feature_rows(db_session, feature_rows())

    train_model.train_all(db_session, tmp_path, random_seed=42, min_samples_per_type=5)
    second = train_model.train_all(db_session, tmp_path, random_seed=7, min_samples_per_type=5)

    assert second["created"] == 2
    assert model_count(db_session) == 4
    assert len(artifact_hashes(tmp_path)) == 4


def test_changed_training_data_creates_new_model_version(db_session: Session, tmp_path: Path) -> None:
    rows = feature_rows()
    add_feature_rows(db_session, rows)
    train_model.train_scope(db_session, rows, "global", tmp_path, random_seed=42)

    changed = feature_rows()
    changed[0].features["messages_per_minute"] += 1.0
    result = train_model.train_scope(db_session, changed, "global", tmp_path, random_seed=42)

    assert result == "created"
    assert model_count(db_session) == 2


def test_missing_artifact_recovers_same_metadata_row(db_session: Session, tmp_path: Path) -> None:
    rows = feature_rows()
    add_feature_rows(db_session, rows)
    train_model.train_scope(db_session, rows, "global", tmp_path, random_seed=42)
    row = db_session.scalar(select(ModelVersion))
    assert row is not None
    Path(row.artifact_path).unlink()

    result = train_model.train_scope(db_session, rows, "global", tmp_path, random_seed=42)

    assert result == "rebuilt"
    assert model_count(db_session) == 1
    assert Path(row.artifact_path).is_file()


def test_corrupt_artifact_recovers_same_metadata_row(db_session: Session, tmp_path: Path) -> None:
    rows = feature_rows()
    add_feature_rows(db_session, rows)
    train_model.train_scope(db_session, rows, "global", tmp_path, random_seed=42)
    row = db_session.scalar(select(ModelVersion))
    assert row is not None
    Path(row.artifact_path).write_bytes(b"not-a-joblib-model")

    result = train_model.train_scope(db_session, rows, "global", tmp_path, random_seed=42)

    assert result == "rebuilt"
    assert model_count(db_session) == 1
    assert train_model._valid_artifact(Path(row.artifact_path), row.artifact_sha256)


def test_model_identity_fingerprint_is_unique(db_session: Session, tmp_path: Path) -> None:
    rows = feature_rows()
    identity = train_model.build_model_identity(rows, "global", tmp_path, random_seed=42)
    first = train_model._new_model_version(identity, "a" * 64, len(rows))
    duplicate = train_model._new_model_version(identity, "b" * 64, len(rows))

    db_session.add(first)
    db_session.commit()
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_uniqueness_race_reuses_competing_metadata_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    rows = feature_rows()
    with session_factory() as db:
        add_feature_rows(db, rows)

    with session_factory() as trainer:
        real_commit = trainer.commit

        def raced_commit() -> None:
            pending = next(row for row in trainer.new if isinstance(row, ModelVersion))
            with session_factory() as competitor:
                competitor.add(
                    ModelVersion(
                        name=pending.name,
                        device_type=pending.device_type,
                        artifact_path=pending.artifact_path,
                        identity_fingerprint=pending.identity_fingerprint,
                        feature_schema_version=pending.feature_schema_version,
                        training_dataset_hash=pending.training_dataset_hash,
                        hyperparameters=pending.hyperparameters,
                        training_code_version=pending.training_code_version,
                        artifact_sha256=pending.artifact_sha256,
                        training_rows=pending.training_rows,
                        metrics=pending.metrics,
                        active=pending.active,
                    )
                )
                competitor.commit()
            raise IntegrityError("insert model_versions", {}, RuntimeError("duplicate fingerprint"))

        monkeypatch.setattr(trainer, "commit", raced_commit)
        result = train_model.train_scope(trainer, rows, "global", tmp_path, random_seed=42)
        monkeypatch.setattr(trainer, "commit", real_commit)

    with session_factory() as verifier:
        assert result == "reused"
        assert model_count(verifier) == 1
    assert len(artifact_hashes(tmp_path)) == 1


def test_atomic_write_removes_temporary_file_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows = feature_rows()
    identity = train_model.build_model_identity(rows, "global", tmp_path, random_seed=42)

    def broken_save_model(_model: object, path: str | Path) -> None:
        Path(path).write_bytes(b"partial")
        raise RuntimeError("save failed")

    monkeypatch.setattr(train_model, "save_model", broken_save_model)

    with pytest.raises(RuntimeError):
        train_model._atomic_save_model(rows, identity)

    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob("*.joblib")) == []


def test_evaluation_is_read_only_for_model_identity(db_session: Session, tmp_path: Path) -> None:
    add_feature_rows(db_session, feature_rows())
    train_model.train_all(db_session, tmp_path, random_seed=42, min_samples_per_type=5)
    rows_before = model_count(db_session)
    hashes_before = artifact_hashes(tmp_path)

    evaluate_model.main()

    assert model_count(db_session) == rows_before
    assert artifact_hashes(tmp_path) == hashes_before
