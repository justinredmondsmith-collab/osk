#!/usr/bin/env python3
"""Serve a minimal mocked Osk hub for manual member-shell smoke testing."""

from __future__ import annotations

import argparse
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import uvicorn
from fastapi.responses import JSONResponse

from osk.connection_manager import ConnectionManager
from osk.models import Member, MemberRole, MemberStatus, Operation
from osk.server import create_app


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_app(*, operation_name: str):
    operation = Operation(name=operation_name)
    members: dict[str, Member] = {}
    conn_manager = ConnectionManager()
    latest_member_id: str | None = None

    async def add_member(
        operation_id,
        name: str,
        role: MemberRole = MemberRole.OBSERVER,
    ) -> Member:
        nonlocal latest_member_id
        member = Member(name=name, role=role)
        members[member.id] = member
        latest_member_id = str(member.id)
        return member

    async def resume_member(operation_id, member_id, reconnect_token):
        member = members.get(member_id)
        if member is None:
            raise KeyError(member_id)
        if not secrets.compare_digest(member.reconnect_token, reconnect_token):
            raise PermissionError("Reconnect token mismatch")
        member.status = MemberStatus.CONNECTED
        member.connected_at = datetime.now(timezone.utc)
        member.last_seen_at = member.connected_at
        return member

    async def mark_disconnected(member_id):
        member = members.get(member_id)
        if member is None:
            return
        member.status = MemberStatus.DISCONNECTED

    async def touch_member_heartbeat(member_id):
        member = members.get(member_id)
        if member is None:
            return
        member.last_seen_at = datetime.now(timezone.utc)

    async def update_member_gps(member_id, lat, lon):
        member = members.get(member_id)
        if member is None:
            return
        member.latitude = lat
        member.longitude = lon
        member.last_gps_at = datetime.now(timezone.utc)
        member.last_seen_at = member.last_gps_at

    async def promote_member(member_id):
        member = members.get(member_id)
        if member is None:
            raise KeyError(member_id)
        member.role = MemberRole.SENSOR
        conn_manager.update_role(member.id, MemberRole.SENSOR)
        await conn_manager.send_to(
            member.id,
            {"type": "role_change", "role": MemberRole.SENSOR.value},
        )

    async def demote_member(member_id):
        member = members.get(member_id)
        if member is None:
            raise KeyError(member_id)
        member.role = MemberRole.OBSERVER
        conn_manager.update_role(member.id, MemberRole.OBSERVER)
        await conn_manager.send_to(
            member.id,
            {"type": "role_change", "role": MemberRole.OBSERVER.value},
        )

    async def kick_member(member_id):
        member = members.get(member_id)
        if member is None:
            raise KeyError(member_id)
        member.status = MemberStatus.KICKED
        await conn_manager.disconnect(member.id)

    async def update_member_buffer_status(member_id, payload):
        member = members.get(member_id)
        if member is None:
            return
        member.buffer_status = member.buffer_status.model_copy(
            update={
                "pending_count": max(0, int(payload.get("pending_count") or 0)),
                "manual_pending_count": max(0, int(payload.get("manual_pending_count") or 0)),
                "sensor_pending_count": max(0, int(payload.get("sensor_pending_count") or 0)),
                "report_pending_count": max(0, int(payload.get("report_pending_count") or 0)),
                "audio_pending_count": max(0, int(payload.get("audio_pending_count") or 0)),
                "frame_pending_count": max(0, int(payload.get("frame_pending_count") or 0)),
                "in_flight": bool(payload.get("in_flight")),
                "network": (
                    "offline"
                    if str(payload.get("network") or "").strip().lower() == "offline"
                    else "online"
                ),
                "last_error": str(payload.get("last_error") or "").strip() or None,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    op_manager = MagicMock()
    op_manager.operation = operation
    op_manager.members = members
    op_manager.validate_token = MagicMock(
        side_effect=lambda token: str(token).strip() == operation.token
    )
    op_manager.validate_coordinator_token = MagicMock(
        side_effect=lambda token: token == operation.coordinator_token
    )
    op_manager.add_member = AsyncMock(side_effect=add_member)
    op_manager.resume_member = AsyncMock(side_effect=resume_member)
    op_manager.promote_member = AsyncMock(side_effect=promote_member)
    op_manager.demote_member = AsyncMock(side_effect=demote_member)
    op_manager.kick_member = AsyncMock(side_effect=kick_member)
    op_manager.mark_disconnected = AsyncMock(side_effect=mark_disconnected)
    op_manager.touch_member_heartbeat = AsyncMock(side_effect=touch_member_heartbeat)
    op_manager.update_member_gps = AsyncMock(side_effect=update_member_gps)
    op_manager.update_member_buffer_status = AsyncMock(side_effect=update_member_buffer_status)
    op_manager.rotate_token = AsyncMock(return_value="new-token")
    op_manager.get_member_list = MagicMock(
        side_effect=lambda: [member.model_dump(mode="json") for member in members.values()]
    )
    op_manager.get_sensor_count = MagicMock(
        side_effect=lambda: sum(
            1 for member in members.values() if member.role == MemberRole.SENSOR
        )
    )

    db = MagicMock()
    db.insert_event = AsyncMock()
    db.insert_manual_report_once = AsyncMock(
        side_effect=lambda **kwargs: {
            "duplicate": False,
            "event_id": kwargs["event_id"],
            "text": kwargs["text"],
            "timestamp": kwargs["timestamp"],
        }
    )
    db.insert_audit_event = AsyncMock()
    db.get_members = AsyncMock(return_value=[])
    db.get_latest_sitrep = AsyncMock(return_value=None)
    db.get_review_feed = AsyncMock(return_value=[])

    intelligence_service = MagicMock()
    intelligence_service.snapshot.return_value = {
        "running": True,
        "transcriber": {"backend": "fake"},
        "vision": {"backend": "fake"},
    }
    intelligence_service.config = SimpleNamespace(
        max_audio_payload_bytes=32768,
        max_frame_payload_bytes=131072,
    )
    intelligence_service.submit_audio = AsyncMock(return_value=True)
    intelligence_service.submit_frame = AsyncMock(return_value=True)
    intelligence_service.submit_location = AsyncMock(return_value=True)

    app = create_app(
        op_manager=op_manager,
        conn_manager=conn_manager,
        db=db,
        intelligence_service=intelligence_service,
    )

    @app.get("/__smoke/status")
    async def smoke_status():
        return {
            "operation_id": str(operation.id),
            "operation_name": operation.name,
            "connected_count": conn_manager.connected_count,
            "latest_member_id": latest_member_id,
            "members": [member.model_dump(mode="json") for member in members.values()],
        }

    @app.post("/__smoke/wipe")
    async def smoke_wipe():
        target_count = conn_manager.connected_count
        await conn_manager.broadcast({"type": "wipe"})
        return {
            "status": "sent",
            "broadcast_target_count": target_count,
            "type": "wipe",
            "timestamp": _utcnow_iso(),
        }

    @app.post("/__smoke/op-ended")
    async def smoke_op_ended():
        target_count = conn_manager.connected_count
        await conn_manager.broadcast({"type": "op_ended"})
        return {
            "status": "sent",
            "broadcast_target_count": target_count,
            "type": "op_ended",
            "timestamp": _utcnow_iso(),
        }

    @app.post("/__smoke/promote-latest")
    async def smoke_promote_latest():
        if latest_member_id is None:
            return JSONResponse({"error": "No member has joined yet."}, status_code=404)
        member = next(
            (candidate for candidate in members.values() if str(candidate.id) == latest_member_id),
            None,
        )
        if member is None:
            return JSONResponse({"error": "Latest member is unavailable."}, status_code=404)
        await promote_member(member.id)
        return {
            "status": "sent",
            "member_id": str(member.id),
            "role": member.role.value,
            "timestamp": _utcnow_iso(),
        }

    return app, operation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve a mocked Osk member shell for manual browser/device smoke tests.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Use 0.0.0.0 for LAN.")
    parser.add_argument("--port", default=8123, type=int, help="Bind port.")
    parser.add_argument(
        "--advertise-host",
        default="127.0.0.1",
        help="Hostname/IP printed in the join URL for external devices.",
    )
    parser.add_argument(
        "--operation-name",
        default="Osk Member Shell Smoke",
        help="Operation name shown in the join/member shell.",
    )
    parser.add_argument(
        "--metadata-path",
        default="",
        help="Optional JSON file path for writing join URL and operation metadata.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app, operation = build_app(operation_name=args.operation_name)
    join_url = f"http://{args.advertise_host}:{args.port}/join?token={operation.token}"
    metadata_path = Path(args.metadata_path).expanduser() if args.metadata_path else None

    if metadata_path is not None:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(
                {
                    "operation_name": operation.name,
                    "join_url": join_url,
                    "host": args.host,
                    "advertise_host": args.advertise_host,
                    "port": args.port,
                    "controls": {
                        "status_url": f"http://{args.advertise_host}:{args.port}/__smoke/status",
                        "wipe_url": f"http://{args.advertise_host}:{args.port}/__smoke/wipe",
                        "op_ended_url": f"http://{args.advertise_host}:{args.port}/__smoke/op-ended",
                        "promote_latest_url": (
                            f"http://{args.advertise_host}:{args.port}/__smoke/promote-latest"
                        ),
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    print()
    print("Osk member-shell smoke server")
    print(f"Operation: {operation.name}")
    print(f"Join URL:   {join_url}")
    print()
    print("Suggested manual checks:")
    print("1. Open the join URL in a real browser or phone on the same network.")
    print("2. Enter a display name and continue into /member.")
    print(
        "3. Toggle the browser offline, queue a field note, and confirm it appears in the outbox."
    )
    print("4. If camera/mic permissions are available, queue a photo or short clip offline.")
    print("5. Restore connectivity and confirm queued items replay and disappear.")
    print("6. Reload /member and confirm the secure member session resumes.")
    print("7. POST to /__smoke/wipe and confirm the browser clears into the local wiped shell.")
    print("8. If the browser supports it, test the install prompt and standalone launch.")
    print()
    print("Press Ctrl+C to stop.")
    print()

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
