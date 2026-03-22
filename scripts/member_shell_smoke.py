#!/usr/bin/env python3
"""Serve a minimal mocked Osk hub for manual member-shell smoke testing."""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import uvicorn

from osk.models import Member, MemberRole, Operation
from osk.server import create_app


def build_app(*, operation_name: str):
    operation = Operation(name=operation_name)
    members: dict[str, Member] = {}

    async def add_member(
        name: str,
        role: MemberRole = MemberRole.OBSERVER,
    ) -> Member:
        member = Member(name=name, role=role)
        members[member.id] = member
        return member

    async def resume_member(operation_id, member_id, reconnect_token):
        return members.get(member_id)

    op_manager = MagicMock()
    op_manager.operation = operation
    op_manager.members = members
    op_manager.validate_token = MagicMock(
        side_effect=lambda token: str(token).strip() == operation.token
    )
    op_manager.validate_coordinator_token = MagicMock(
        side_effect=lambda token: token == operation.coordinator_token
    )
    op_manager.add_member = AsyncMock(
        side_effect=lambda name, role=MemberRole.OBSERVER: add_member(name, role)
    )
    op_manager.resume_member = AsyncMock(side_effect=resume_member)
    op_manager.promote_member = AsyncMock()
    op_manager.demote_member = AsyncMock()
    op_manager.kick_member = AsyncMock()
    op_manager.mark_disconnected = AsyncMock()
    op_manager.touch_member_heartbeat = AsyncMock()
    op_manager.update_member_gps = AsyncMock()
    op_manager.rotate_token = AsyncMock(return_value="new-token")
    op_manager.get_member_list = MagicMock(return_value=[])
    op_manager.get_sensor_count = MagicMock(return_value=0)

    conn_manager = MagicMock()
    conn_manager.broadcast = AsyncMock()
    conn_manager.broadcast_alert = AsyncMock()
    conn_manager.disconnect = AsyncMock()
    conn_manager.send_to = AsyncMock()
    conn_manager.register = MagicMock()
    conn_manager.unregister = MagicMock()
    conn_manager.update_role = MagicMock()
    conn_manager.mark_seen = MagicMock()
    conn_manager.connected_count = 0

    db = MagicMock()
    db.insert_event = AsyncMock()
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app, operation = build_app(operation_name=args.operation_name)
    join_url = f"http://{args.advertise_host}:{args.port}/join?token={operation.token}"

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
    print("6. If the browser supports it, test the install prompt and standalone launch.")
    print()
    print("Press Ctrl+C to stop.")
    print()

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
