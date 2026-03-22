from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "member_shell_smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("member_shell_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_wipe_control_broadcasts_to_connected_member() -> None:
    smoke = _load_smoke_module()
    app, operation = smoke.build_app(operation_name="Smoke Test")

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "auth", "token": operation.token, "name": "Jay"})
            auth = websocket.receive_json()

            assert auth["type"] == "auth_ok"

            response = client.post("/__smoke/wipe")

            assert response.status_code == 200
            assert response.json()["broadcast_target_count"] == 1

            message = websocket.receive_json()

    assert message["type"] == "wipe"


def test_smoke_promote_latest_updates_connected_member_role() -> None:
    smoke = _load_smoke_module()
    app, operation = smoke.build_app(operation_name="Smoke Test")

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "auth", "token": operation.token, "name": "Jay"})
            auth = websocket.receive_json()

            assert auth["type"] == "auth_ok"

            response = client.post("/__smoke/promote-latest")

            assert response.status_code == 200
            assert response.json()["role"] == "sensor"

            message = websocket.receive_json()
            assert message == {"type": "role_change", "role": "sensor"}

            status_payload = client.get("/__smoke/status").json()

    assert status_payload["connected_count"] == 1
    assert status_payload["members"][0]["role"] == "sensor"


def test_smoke_member_report_ack_works() -> None:
    smoke = _load_smoke_module()
    app, operation = smoke.build_app(operation_name="Smoke Test")

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "auth", "token": operation.token, "name": "Jay"})
            auth = websocket.receive_json()

            assert auth["type"] == "auth_ok"

            websocket.send_json(
                {
                    "type": "report",
                    "report_id": "report-1",
                    "text": "Need medics at the west gate",
                }
            )
            ack = websocket.receive_json()

    assert ack["type"] == "report_ack"
    assert ack["accepted"] is True
    assert ack["report_id"] == "report-1"
