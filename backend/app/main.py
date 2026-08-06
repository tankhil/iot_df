from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Defensive, hardware-free IoT cybersecurity lab API. All devices, telemetry, "
            "attack simulations, quarantine actions, and recovery actions are simulated "
            "inside the project environment."
        ),
        openapi_tags=[
            {"name": "System", "description": "Liveness, readiness, and API discovery."},
            {"name": "Devices", "description": "Simulated IoT device inventory and details."},
            {"name": "Telemetry", "description": "Validated simulated MQTT telemetry events."},
            {"name": "Security Events", "description": "Synthetic security event records."},
            {"name": "Detection", "description": "ML anomaly detection history."},
            {"name": "Risk Assessment", "description": "Explainable deterministic risk scores."},
            {"name": "Alerts", "description": "Suspicious or higher simulated alerts."},
            {"name": "Policy Decisions", "description": "Deterministic allow-listed decisions."},
            {"name": "Response Actions", "description": "Safe simulated response execution."},
            {"name": "Quarantine", "description": "Simulated quarantine and recovery state."},
            {"name": "Audit", "description": "Append-only security decision audit trail."},
            {"name": "ML Models", "description": "Model metadata without exposing artifacts."},
            {"name": "Simulations", "description": "Admin-only safe attack simulation controls."},
            {"name": "Administration", "description": "Admin-only manual quarantine overrides."},
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-API-Key"],
    )
    app.include_router(router)

    @app.middleware("http")
    async def enforce_payload_size(request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_payload_bytes:
            return JSONResponse({"detail": "Payload too large"}, status_code=413)
        return await call_next(request)

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"type": "connected", "simulated": True})
        while True:
            await websocket.receive_text()
            await websocket.send_json({"type": "heartbeat", "simulated": True})

    return app


app = create_app()
