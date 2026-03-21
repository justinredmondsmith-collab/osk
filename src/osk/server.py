"""FastAPI application with REST endpoints and WebSocket handler."""

from __future__ import annotations

import ipaddress
import json
import logging
import uuid

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from osk.connection_manager import ConnectionManager
from osk.models import Event, EventCategory, EventSeverity, MemberRole, Pin
from osk.operation import OperationManager

logger = logging.getLogger(__name__)
ADMIN_TOKEN_HEADER = "X-Osk-Coordinator-Token"
LOCAL_ADMIN_TEST_HOSTS = {"testclient", "localhost"}
MAX_AUDIT_LIMIT = 200


class ReportRequest(BaseModel):
    member_id: str
    text: str


class PinRequest(BaseModel):
    member_id: str


def _extract_coordinator_token(request: Request) -> str | None:
    if token := request.headers.get(ADMIN_TOKEN_HEADER):
        return token.strip()

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def _is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    if host in LOCAL_ADMIN_TEST_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _require_local_admin(request: Request, op_manager: OperationManager) -> JSONResponse | None:
    client_host = request.client.host if request.client else None
    if _is_loopback_host(client_host):
        operation = op_manager.operation
        if operation is None:
            return None

        token = _extract_coordinator_token(request)
        if token is None:
            return JSONResponse(
                {"error": "Missing coordinator token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if op_manager.validate_coordinator_token(token):
            return None

        logger.warning("Rejected admin request with invalid coordinator token from %s", client_host)
        return JSONResponse({"error": "Invalid coordinator token"}, status_code=403)

    logger.warning("Rejected non-local admin request from %s", client_host)
    return JSONResponse({"error": "Local coordinator access only"}, status_code=403)


def create_app(op_manager: OperationManager, conn_manager: ConnectionManager, db) -> FastAPI:
    app = FastAPI(title="Osk Hub", docs_url=None, redoc_url=None)

    @app.get("/join")
    async def join_page(token: str = Query(...)):
        if not op_manager.validate_token(token):
            return JSONResponse({"error": "Invalid token"}, status_code=403)

        operation = op_manager.operation
        name = operation.name if operation else "Osk"
        return HTMLResponse(
            "<html><body>"
            "<h1>Osk</h1>"
            f"<p>Join: {name}</p>"
            f"<script>sessionStorage.setItem('osk_token','{token}');</script>"
            "</body></html>"
        )

    @app.get("/api/operation/status")
    async def operation_status(request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        return {
            "id": str(operation.id),
            "name": operation.name,
            "started_at": operation.started_at.isoformat(),
            "members": len(op_manager.members),
            "sensors": op_manager.get_sensor_count(),
            "connected": conn_manager.connected_count,
        }

    @app.get("/api/members")
    async def list_members(request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        if op_manager.operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        return op_manager.get_member_list()

    @app.get("/api/audit")
    async def list_audit_events(request: Request, limit: int = 50):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        clamped_limit = max(1, min(limit, MAX_AUDIT_LIMIT))
        return await db.get_audit_events(operation.id, clamped_limit)

    @app.post("/api/members/{member_id}/promote")
    async def promote_member(member_id: uuid.UUID, request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        if op_manager.operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        if member_id not in op_manager.members:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        await op_manager.promote_member(member_id)
        conn_manager.update_role(member_id, MemberRole.SENSOR)
        await conn_manager.send_to(
            member_id,
            {"type": "role_change", "role": MemberRole.SENSOR.value},
        )
        await db.insert_audit_event(
            op_manager.operation.id,
            "coordinator",
            "member_promoted",
            actor_member_id=member_id,
            details={"role": MemberRole.SENSOR.value},
        )
        return {"status": "promoted"}

    @app.post("/api/members/{member_id}/demote")
    async def demote_member(member_id: uuid.UUID, request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        if op_manager.operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        if member_id not in op_manager.members:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        await op_manager.demote_member(member_id)
        conn_manager.update_role(member_id, MemberRole.OBSERVER)
        await conn_manager.send_to(
            member_id,
            {"type": "role_change", "role": MemberRole.OBSERVER.value},
        )
        await db.insert_audit_event(
            op_manager.operation.id,
            "coordinator",
            "member_demoted",
            actor_member_id=member_id,
            details={"role": MemberRole.OBSERVER.value},
        )
        return {"status": "demoted"}

    @app.post("/api/members/{member_id}/kick")
    async def kick_member(member_id: uuid.UUID, request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        if op_manager.operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        if member_id not in op_manager.members:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        await op_manager.kick_member(member_id)
        await conn_manager.disconnect(member_id)
        await db.insert_audit_event(
            op_manager.operation.id,
            "coordinator",
            "member_kicked",
            actor_member_id=member_id,
        )
        return {"status": "kicked"}

    @app.post("/api/rotate-token")
    async def rotate_token(request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        token = await op_manager.rotate_token(operation.id)
        await db.insert_audit_event(
            operation.id,
            "coordinator",
            "join_token_rotated",
        )
        return {"token": token}

    @app.post("/api/pin/{event_id}")
    async def pin_event(event_id: uuid.UUID, req: PinRequest, request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        if op_manager.operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        pin = Pin(event_id=event_id, pinned_by=uuid.UUID(req.member_id))
        await db.insert_pin(pin.id, pin.event_id, pin.pinned_by)
        await db.insert_audit_event(
            op_manager.operation.id,
            "coordinator",
            "event_pinned",
            actor_member_id=pin.pinned_by,
            details={"event_id": str(pin.event_id), "pin_id": str(pin.id)},
        )
        return {"status": "pinned", "pin_id": str(pin.id)}

    @app.post("/api/report")
    async def submit_report(req: ReportRequest, request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        event = Event(
            severity=EventSeverity.INFO,
            category=EventCategory.MANUAL_REPORT,
            text=req.text,
            source_member_id=uuid.UUID(req.member_id),
        )
        await db.insert_event(
            event.id,
            operation.id,
            event.severity,
            event.category,
            event.text,
            event.source_member_id,
            None,
            None,
        )
        await db.insert_audit_event(
            operation.id,
            "coordinator",
            "report_submitted",
            actor_member_id=event.source_member_id,
            details={"event_id": str(event.id)},
        )
        return {"status": "reported", "event_id": str(event.id)}

    @app.post("/api/wipe")
    async def trigger_wipe(request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        if op_manager.operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        await conn_manager.broadcast({"type": "wipe"})
        await db.insert_audit_event(
            op_manager.operation.id,
            "coordinator",
            "wipe_triggered",
        )
        return {"status": "wipe_initiated"}

    @app.get("/api/events")
    async def get_events(request: Request, since: str = "1970-01-01T00:00:00Z"):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        return await db.get_events_since(operation.id, since)

    @app.get("/api/sitrep/latest")
    async def get_latest_sitrep(request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        sitrep = await db.get_latest_sitrep(operation.id)
        return sitrep or {"text": "No situation reports yet", "trend": "stable"}

    @app.websocket("/ws")
    async def websocket_handler(ws: WebSocket):
        await ws.accept()
        member_id: uuid.UUID | None = None
        try:
            auth_message = await ws.receive_json()
            if auth_message.get("type") != "auth":
                await ws.close(code=4001, reason="First message must be auth")
                return

            token = auth_message.get("token", "")
            name = auth_message.get("name", "Anonymous")
            if not op_manager.validate_token(token):
                await ws.close(code=4003, reason="Invalid token")
                return

            operation = op_manager.operation
            if operation is None:
                await ws.close(code=4004, reason="No active operation")
                return

            resume_member_id = auth_message.get("resume_member_id")
            resume_token = auth_message.get("resume_token")
            resumed = False
            if resume_member_id and resume_token:
                try:
                    member = await op_manager.resume_member(
                        operation.id,
                        uuid.UUID(str(resume_member_id)),
                        str(resume_token),
                    )
                    resumed = True
                except (KeyError, PermissionError, ValueError):
                    await ws.close(code=4003, reason="Invalid resume credentials")
                    return
            else:
                member = await op_manager.add_member(operation.id, name)

            member_id = member.id
            if member_id in conn_manager.connections:
                await conn_manager.disconnect(member_id)
            conn_manager.register(member_id, ws, member.role)

            await ws.send_json(
                {
                    "type": "auth_ok",
                    "member_id": str(member_id),
                    "role": member.role.value,
                    "resume_token": member.reconnect_token,
                    "resumed": resumed,
                }
            )

            while True:
                message = await ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    if msg_type == "gps":
                        await op_manager.update_member_gps(member_id, data["lat"], data["lon"])
                    elif msg_type == "report":
                        event = Event(
                            severity=EventSeverity.INFO,
                            category=EventCategory.MANUAL_REPORT,
                            text=data["text"],
                            source_member_id=member_id,
                        )
                        await db.insert_event(
                            event.id,
                            operation.id,
                            event.severity,
                            event.category,
                            event.text,
                            event.source_member_id,
                            None,
                            None,
                        )
                        await db.insert_audit_event(
                            operation.id,
                            "member",
                            "report_submitted",
                            actor_member_id=member_id,
                            details={"event_id": str(event.id)},
                        )
                    elif msg_type in {"pong", "audio_meta", "frame_meta", "clip_meta"}:
                        continue
                elif "bytes" in message:
                    continue
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.error("WebSocket error for %s: %s", member_id, exc)
            if ws.client_state.name.lower() != "disconnected":
                await ws.close(code=1011)
        finally:
            if member_id is not None:
                conn_manager.unregister(member_id)
                try:
                    await op_manager.mark_disconnected(member_id)
                except KeyError:
                    pass

    return app
