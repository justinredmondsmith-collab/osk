"""FastAPI application with REST endpoints and WebSocket handler."""

from __future__ import annotations

import base64
import datetime as dt
import ipaddress
import json
import logging
import uuid

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from osk.connection_manager import ConnectionManager
from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IngestPriority,
    IngestSource,
    LocationSample,
)
from osk.intelligence_service import IngestSubmissionResult
from osk.local_operator import validate_operator_session
from osk.models import Event, EventCategory, EventSeverity, MemberRole, Pin
from osk.operation import OperationManager

logger = logging.getLogger(__name__)
ADMIN_TOKEN_HEADER = "X-Osk-Coordinator-Token"
OPERATOR_SESSION_HEADER = "X-Osk-Operator-Session"
LOCAL_ADMIN_TEST_HOSTS = {"testclient", "localhost"}
MAX_AUDIT_LIMIT = 200
MAX_OBSERVATION_LIMIT = 200
MAX_FINDING_LIMIT = 100


class ReportRequest(BaseModel):
    member_id: str
    text: str


class PinRequest(BaseModel):
    member_id: str


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _extract_admin_token(request: Request) -> str | None:
    if token := request.headers.get(ADMIN_TOKEN_HEADER):
        return token.strip()

    if token := request.headers.get(OPERATOR_SESSION_HEADER):
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

        token = _extract_admin_token(request)
        if token is None:
            return JSONResponse(
                {"error": "Missing operator credentials"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if validate_operator_session(token, str(operation.id)):
            return None
        if op_manager.validate_coordinator_token(token):
            return None

        logger.warning("Rejected admin request with invalid local credentials from %s", client_host)
        return JSONResponse({"error": "Invalid operator credentials"}, status_code=403)

    logger.warning("Rejected non-local admin request from %s", client_host)
    return JSONResponse({"error": "Local coordinator access only"}, status_code=403)


def _member_priority(role: MemberRole) -> IngestPriority:
    return {
        MemberRole.COORDINATOR: IngestPriority.URGENT,
        MemberRole.SENSOR: IngestPriority.SENSOR,
        MemberRole.OBSERVER: IngestPriority.OBSERVER,
    }[role]


def _coerce_timestamp(value) -> dt.datetime:
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            pass
    return _utcnow()


def _coerce_uuid(value) -> uuid.UUID | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _coerce_ingest_key(data: dict, *, preferred_id_key: str) -> str | None:
    for key in ("ingest_key", preferred_id_key):
        raw = str(data.get(key) or "").strip()
        if raw:
            return raw[:128]
    return None


def _decode_inline_payload(data: dict) -> bytes:
    payload_b64 = str(data.get("payload_b64") or "").strip()
    if not payload_b64:
        return b""
    return base64.b64decode(payload_b64, validate=True)


def _build_audio_chunk(member, data: dict, payload: bytes) -> AudioChunk:
    received_at = _coerce_timestamp(data.get("captured_at") or data.get("received_at"))
    chunk_id = _coerce_uuid(data.get("chunk_id")) or uuid.uuid4()
    return AudioChunk(
        chunk_id=chunk_id,
        ingest_key=_coerce_ingest_key(data, preferred_id_key="chunk_id"),
        source=IngestSource(
            member_id=member.id,
            member_role=member.role,
            priority=_member_priority(member.role),
            received_at=received_at,
        ),
        codec=str(data.get("codec") or "audio/webm"),
        sample_rate_hz=int(data.get("sample_rate_hz") or 16000),
        duration_ms=int(data.get("duration_ms") or 0),
        sequence_no=int(data.get("sequence_no") or 0),
        payload=payload,
    )


def _build_frame_sample(member, data: dict, payload: bytes) -> FrameSample:
    captured_at = _coerce_timestamp(data.get("captured_at"))
    frame_id = _coerce_uuid(data.get("frame_id")) or uuid.uuid4()
    return FrameSample(
        frame_id=frame_id,
        ingest_key=_coerce_ingest_key(data, preferred_id_key="frame_id"),
        source=IngestSource(
            member_id=member.id,
            member_role=member.role,
            priority=_member_priority(member.role),
            received_at=captured_at,
        ),
        content_type=str(data.get("content_type") or "image/jpeg"),
        width=int(data.get("width") or 0),
        height=int(data.get("height") or 0),
        change_score=float(data.get("change_score") or 0.0),
        sequence_no=int(data.get("sequence_no") or 0),
        captured_at=captured_at,
        payload=payload,
    )


def _payload_too_large(payload: bytes, *, limit_bytes: int) -> bool:
    return len(payload) > max(int(limit_bytes), 1)


def _build_location_sample(member, data: dict) -> LocationSample:
    captured_at = _coerce_timestamp(data.get("captured_at"))
    return LocationSample(
        source=IngestSource(
            member_id=member.id,
            member_role=member.role,
            priority=_member_priority(member.role),
            received_at=captured_at,
        ),
        latitude=float(data["lat"]),
        longitude=float(data["lon"]),
        accuracy_m=float(data.get("accuracy_m") or 0.0),
        heading_degrees=(
            float(data["heading_degrees"]) if data.get("heading_degrees") is not None else None
        ),
        speed_mps=float(data["speed_mps"]) if data.get("speed_mps") is not None else None,
        captured_at=captured_at,
    )


def _normalize_submission_result(result) -> IngestSubmissionResult:
    if isinstance(result, IngestSubmissionResult):
        return result
    return IngestSubmissionResult(accepted=bool(result))


def _submission_ack_payload(
    *,
    ack_type: str,
    item_field: str,
    item_id: uuid.UUID,
    ingest_key: str | None,
    result,
) -> dict[str, object]:
    submission = _normalize_submission_result(result)
    payload: dict[str, object] = {
        "type": ack_type,
        "accepted": submission.accepted,
        item_field: str(item_id),
    }
    if ingest_key:
        payload["ingest_key"] = ingest_key
    if submission.duplicate:
        payload["duplicate"] = True
    if submission.reason:
        payload["reason"] = submission.reason
    return payload


def _oversized_ingest_ack_payload(
    *,
    data: dict,
    ack_type: str,
    item_field: str,
    preferred_id_key: str,
    reason: str,
) -> dict[str, object]:
    item_id = _coerce_uuid(data.get(preferred_id_key)) or uuid.uuid4()
    payload: dict[str, object] = {
        "type": ack_type,
        "accepted": False,
        item_field: str(item_id),
        "reason": reason,
    }
    ingest_key = _coerce_ingest_key(data, preferred_id_key=preferred_id_key)
    if ingest_key:
        payload["ingest_key"] = ingest_key
    return payload


def create_app(
    op_manager: OperationManager,
    conn_manager: ConnectionManager,
    db,
    intelligence_service=None,
) -> FastAPI:
    app = FastAPI(title="Osk Hub", docs_url=None, redoc_url=None)
    app.state.intelligence_service = intelligence_service

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

    @app.get("/api/intelligence/status")
    async def intelligence_status(request: Request):
        if response := _require_local_admin(request, op_manager):
            return response
        if intelligence_service is None:
            return JSONResponse(
                {"error": "Intelligence service is not configured"}, status_code=503
            )
        return intelligence_service.snapshot()

    @app.get("/api/intelligence/observations")
    async def intelligence_observations(request: Request, limit: int = 25):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        clamped_limit = max(1, min(limit, MAX_OBSERVATION_LIMIT))
        return await db.get_recent_intelligence_observations(operation.id, clamped_limit)

    @app.get("/api/intelligence/findings")
    async def intelligence_findings(request: Request, limit: int = 25):
        if response := _require_local_admin(request, op_manager):
            return response
        operation = op_manager.operation
        if operation is None:
            return JSONResponse({"error": "No active operation"}, status_code=503)
        clamped_limit = max(1, min(limit, MAX_FINDING_LIMIT))
        return await db.get_recent_synthesis_findings(operation.id, clamped_limit)

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
        pending_audio_meta: dict | None = None
        pending_frame_meta: dict | None = None
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
                conn_manager.mark_seen(member_id)
                await op_manager.touch_member_heartbeat(member_id)
                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    if msg_type == "gps":
                        await op_manager.update_member_gps(member_id, data["lat"], data["lon"])
                        if intelligence_service is not None:
                            await intelligence_service.submit_location(
                                _build_location_sample(member, data)
                            )
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
                    elif msg_type == "audio_meta":
                        pending_audio_meta = data
                        pending_frame_meta = None
                    elif msg_type == "frame_meta":
                        pending_frame_meta = data
                        pending_audio_meta = None
                    elif msg_type == "audio_chunk":
                        payload = _decode_inline_payload(data)
                        if intelligence_service is not None and _payload_too_large(
                            payload,
                            limit_bytes=intelligence_service.config.max_audio_payload_bytes,
                        ):
                            await ws.send_json(
                                _oversized_ingest_ack_payload(
                                    data=data,
                                    ack_type="audio_ack",
                                    item_field="chunk_id",
                                    preferred_id_key="chunk_id",
                                    reason="audio payload too large",
                                )
                            )
                            continue
                        chunk = _build_audio_chunk(member, data, payload)
                        submission = (
                            await intelligence_service.submit_audio(chunk)
                            if intelligence_service is not None
                            else IngestSubmissionResult(
                                accepted=False,
                                reason="intelligence service unavailable",
                            )
                        )
                        await ws.send_json(
                            _submission_ack_payload(
                                ack_type="audio_ack",
                                item_field="chunk_id",
                                item_id=chunk.chunk_id,
                                ingest_key=chunk.ingest_key,
                                result=submission,
                            )
                        )
                    elif msg_type == "frame_sample":
                        payload = _decode_inline_payload(data)
                        if intelligence_service is not None and _payload_too_large(
                            payload,
                            limit_bytes=intelligence_service.config.max_frame_payload_bytes,
                        ):
                            await ws.send_json(
                                _oversized_ingest_ack_payload(
                                    data=data,
                                    ack_type="frame_ack",
                                    item_field="frame_id",
                                    preferred_id_key="frame_id",
                                    reason="frame payload too large",
                                )
                            )
                            continue
                        frame = _build_frame_sample(member, data, payload)
                        submission = (
                            await intelligence_service.submit_frame(frame)
                            if intelligence_service is not None
                            else IngestSubmissionResult(
                                accepted=False,
                                reason="intelligence service unavailable",
                            )
                        )
                        await ws.send_json(
                            _submission_ack_payload(
                                ack_type="frame_ack",
                                item_field="frame_id",
                                item_id=frame.frame_id,
                                ingest_key=frame.ingest_key,
                                result=submission,
                            )
                        )
                    elif msg_type in {"pong", "clip_meta"}:
                        continue
                elif "bytes" in message:
                    payload = message["bytes"]
                    if pending_audio_meta is not None:
                        if intelligence_service is not None and _payload_too_large(
                            payload,
                            limit_bytes=intelligence_service.config.max_audio_payload_bytes,
                        ):
                            audio_meta = pending_audio_meta
                            pending_audio_meta = None
                            await ws.send_json(
                                _oversized_ingest_ack_payload(
                                    data=audio_meta,
                                    ack_type="audio_ack",
                                    item_field="chunk_id",
                                    preferred_id_key="chunk_id",
                                    reason="audio payload too large",
                                )
                            )
                            continue
                        chunk = _build_audio_chunk(member, pending_audio_meta, payload)
                        submission = (
                            await intelligence_service.submit_audio(chunk)
                            if intelligence_service is not None
                            else IngestSubmissionResult(
                                accepted=False,
                                reason="intelligence service unavailable",
                            )
                        )
                        pending_audio_meta = None
                        await ws.send_json(
                            _submission_ack_payload(
                                ack_type="audio_ack",
                                item_field="chunk_id",
                                item_id=chunk.chunk_id,
                                ingest_key=chunk.ingest_key,
                                result=submission,
                            )
                        )
                        continue
                    if pending_frame_meta is not None:
                        if intelligence_service is not None and _payload_too_large(
                            payload,
                            limit_bytes=intelligence_service.config.max_frame_payload_bytes,
                        ):
                            frame_meta = pending_frame_meta
                            pending_frame_meta = None
                            await ws.send_json(
                                _oversized_ingest_ack_payload(
                                    data=frame_meta,
                                    ack_type="frame_ack",
                                    item_field="frame_id",
                                    preferred_id_key="frame_id",
                                    reason="frame payload too large",
                                )
                            )
                            continue
                        frame = _build_frame_sample(member, pending_frame_meta, payload)
                        submission = (
                            await intelligence_service.submit_frame(frame)
                            if intelligence_service is not None
                            else IngestSubmissionResult(
                                accepted=False,
                                reason="intelligence service unavailable",
                            )
                        )
                        pending_frame_meta = None
                        await ws.send_json(
                            _submission_ack_payload(
                                ack_type="frame_ack",
                                item_field="frame_id",
                                item_id=frame.frame_id,
                                ingest_key=frame.ingest_key,
                                result=submission,
                            )
                        )
                        continue
                    await ws.send_json(
                        {"type": "ingest_error", "reason": "binary payload without metadata"}
                    )
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
