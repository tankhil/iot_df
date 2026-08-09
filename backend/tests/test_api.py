import pytest
from anyio import run
from fastapi import HTTPException

from app.api.routes import health, ready, root, start_attack
from app.core import security
from app.core.config import get_settings
from app.core.security import require_admin
from app.main import create_app
from app.schemas.api import AttackRequest, SafeAttackScenario


def test_root_endpoint() -> None:
    response = root()
    assert response.name == "AI Adaptive IoT Defense Platform"
    assert response.documentation == "/docs"
    assert response.health == "/health"
    assert response.readiness == "/ready"


def test_health_endpoint_has_exact_schema() -> None:
    response = health()
    assert response.model_dump() == {"status": "ok", "service": "api"}


def test_ready_reports_database_ok_with_working_session() -> None:
    class FakeDb:
        def execute(self, _statement: object) -> None:
            return None

    response = ready(FakeDb())  # type: ignore[arg-type]
    assert response.model_dump() == {"status": "ready", "database": "ok"}


def test_ready_hides_dependency_errors() -> None:
    class BrokenDb:
        def execute(self, _statement: object) -> None:
            raise RuntimeError("secret database detail")

    with pytest.raises(HTTPException) as exc:
        ready(BrokenDb())  # type: ignore[arg-type]
    assert exc.value.status_code == 503
    assert exc.value.detail == "Required dependency is unavailable"


def test_openapi_has_meaningful_tags_and_explicit_health_schema() -> None:
    document = create_app().openapi()
    tag_names = {tag["name"] for tag in document["tags"]}
    assert {"System", "Devices", "Simulations", "Administration"}.issubset(tag_names)
    assert document["paths"]["/health"]["get"]["tags"] == ["System"]
    schema_ref = document["paths"]["/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref == "#/components/schemas/HealthResponse"
    health_schema = document["components"]["schemas"]["HealthResponse"]
    assert "additionalProperties" not in health_schema
    assert set(health_schema["properties"]) == {"status", "service"}
    for methods in document["paths"].values():
        for operation in methods.values():
            assert operation["tags"] != ["default"]


def test_protected_endpoints_declare_api_key_security() -> None:
    document = create_app().openapi()
    assert "APIKeyHeader" in document["components"]["securitySchemes"]
    protected_paths = [
        "/api/simulations/attacks/{scenario}/start",
        "/api/simulations/attacks/{scenario}/stop",
        "/api/admin/devices/{device_id}/quarantine",
        "/api/admin/devices/{device_id}/restore",
        "/api/admin/devices/{device_id}/recovery-probe",
    ]
    for path in protected_paths:
        assert document["paths"][path]["post"]["security"] == [{"APIKeyHeader": []}]


def test_missing_admin_key_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        run(require_admin, None)
    assert exc.value.status_code == 401


def test_incorrect_admin_key_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        run(require_admin, "wrong-key")
    assert exc.value.status_code == 403


def test_correct_admin_key_is_accepted() -> None:
    run(require_admin, get_settings().admin_api_key)


@pytest.mark.parametrize("placeholder", sorted(security.PLACEHOLDER_ADMIN_KEYS))
def test_placeholder_admin_key_is_rejected_outside_local_modes(monkeypatch: pytest.MonkeyPatch, placeholder: str) -> None:
    class ProductionSettings:
        environment = "production"
        admin_api_key = placeholder

    monkeypatch.setattr(security, "get_settings", lambda: ProductionSettings())
    with pytest.raises(HTTPException) as exc:
        run(security.require_admin, placeholder)
    assert exc.value.status_code == 500
    assert exc.value.detail == "Admin API key is not configured"


def test_correct_key_can_start_allowed_safe_simulation() -> None:
    response = start_attack(
        SafeAttackScenario.mqtt_flood,
        AttackRequest(device_id="camera-01", intensity=5, seed=42),
    )
    assert response["status"] == "started"
    assert response["scenario"] == "mqtt_flood"
    assert response["simulated"] is True


def test_invalid_scenario_is_rejected_by_schema() -> None:
    with pytest.raises(ValueError):
        SafeAttackScenario("external_scan")
