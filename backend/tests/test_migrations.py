from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_code_does_not_call_create_all() -> None:
    searched = [ROOT / "backend" / "app", ROOT / "scripts"]
    offenders: list[str] = []
    for base in searched:
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "create_all" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_initial_migration_reuses_postgresql_enums_without_recreating() -> None:
    migration = ROOT / "backend" / "alembic" / "versions" / "0001_initial.py"
    text = migration.read_text(encoding="utf-8")
    assert "from sqlalchemy.dialects import postgresql" in text
    assert 'name="devicestatus",' in text
    assert 'name="risklevel",' in text
    assert text.count("postgresql.ENUM(") == 4
    assert text.count("create_type=False") >= 4
    assert "device_status.create(bind, checkfirst=True)" in text
    assert "risk_level.create(bind, checkfirst=True)" in text
    assert "stamp head" not in text


def test_initial_migration_downgrade_drops_tables_before_enums() -> None:
    migration = ROOT / "backend" / "alembic" / "versions" / "0001_initial.py"
    text = migration.read_text(encoding="utf-8")
    drop_table_index = text.index("op.drop_table(table)")
    drop_risk_enum_index = text.index('postgresql.ENUM(name="risklevel", create_type=False).drop')
    drop_device_enum_index = text.index('postgresql.ENUM(name="devicestatus", create_type=False).drop')
    assert drop_table_index < drop_risk_enum_index < drop_device_enum_index


def test_compose_runs_api_only_after_successful_migration() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "  migrate:" in compose
    assert "command: alembic upgrade head" in compose
    assert "condition: service_completed_successfully" in compose


def test_demo_seed_script_is_idempotent_and_does_not_migrate_schema() -> None:
    seed_script = (ROOT / "scripts" / "seed_demo_data.py").read_text(encoding="utf-8")
    assert "DEMO_SEED_VERSION" in seed_script
    assert "demo.seed.completed" in seed_script
    assert "created" in seed_script
    assert "skipped" in seed_script
    assert "alembic" not in seed_script
    assert "create_all" not in seed_script
