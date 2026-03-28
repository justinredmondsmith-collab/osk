#!/usr/bin/env python3
"""
Simulate a browser sensor connecting to a running Osk hub.

This connects via HTTP/WebSocket like a real browser and streams
synthetic audio and frame data for stability testing.

Usage:
    python scripts/simulate_sensor.py --hub-url https://10.0.0.60:8444 --name "Test-Sensor-01"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import ssl
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class SensorSession:
    """Sensor connection state."""
    member_id: str | None = None
    reconnect_token: str | None = None
    connected: bool = False
    audio_chunks_sent: int = 0
    frames_sent: int = 0
    errors: list[str] = field(default_factory=list)


async def join_as_sensor(hub_url: str, name: str) -> SensorSession:
    """Join the hub as a sensor member."""
    session = SensorSession()
    
    # Get operation info
    async with aiohttp.ClientSession() as http_session:
        # First, try to get the join page to extract token or config
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        join_url = f"{hub_url}/join"
        logger.info(f"Connecting to {join_url}")
        
        # For simplicity, we'll use a direct API approach
        # In production, this would parse the HTML form
        
        # Get operation details
        status_url = f"{hub_url}/api/status"
        try:
            async with http_session.get(status_url, ssl=ssl_context) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"Hub status: {data.get('status', 'unknown')}")
                else:
                    logger.warning(f"Status check failed: {resp.status}")
        except Exception as exc:
            logger.error(f"Could not connect to hub: {exc}")
            session.errors.append(str(exc))
            return session
        
        # Try to join via the member endpoint
        join_api_url = f"{hub_url}/api/members"
        join_data = {
            "name": name,
            "role": "sensor",
            "latitude": 40.7128 + random.uniform(-0.01, 0.01),
            "longitude": -74.0060 + random.uniform(-0.01, 0.01),
        }
        
        try:
            async with http_session.post(
                join_api_url,
                json=join_data,
                ssl=ssl_context,
            ) as resp:
                if resp.status in (200, 201):
                    result = await resp.json()
                    session.member_id = result.get("id")
                    session.reconnect_token = result.get("reconnect_token")
                    session.connected = True
                    logger.info(f"✓ Joined as sensor: {name}")
                    logger.info(f"  Member ID: {session.member_id}")
                else:
                    error_text = await resp.text()
                    logger.error(f"Join failed: {resp.status} - {error_text}")
                    session.errors.append(f"HTTP {resp.status}: {error_text}")
        except Exception as exc:
            logger.error(f"Join error: {exc}")
            session.errors.append(str(exc))
    
    return session


async def stream_audio(
    hub_url: str,
    session: SensorSession,
    duration_seconds: int,
) -> None:
    """Stream synthetic audio chunks."""
    if not session.connected or not session.member_id:
        return
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    start_time = time.time()
    chunk_duration = 4  # 4 second chunks
    
    async with aiohttp.ClientSession() as http_session:
        while time.time() - start_time < duration_seconds:
            try:
                # Generate synthetic audio data (128KB for 4s at 16kHz mono)
                audio_data = bytes([random.randint(0, 255) for _ in range(128000)])
                
                # Upload audio chunk
                upload_url = f"{hub_url}/api/members/{session.member_id}/audio"
                
                # Create multipart form data
                data = aiohttp.FormData()
                data.add_field("chunk", audio_data, filename="chunk.webm")
                
                async with http_session.post(
                    upload_url,
                    data=data,
                    ssl=ssl_context,
                ) as resp:
                    if resp.status in (200, 202):
                        session.audio_chunks_sent += 1
                        if session.audio_chunks_sent % 10 == 0:
                            logger.info(f"Audio chunks sent: {session.audio_chunks_sent}")
                    else:
                        error = await resp.text()
                        logger.warning(f"Audio upload failed: {resp.status}")
                        session.errors.append(f"Audio HTTP {resp.status}")
                
                await asyncio.sleep(chunk_duration)
                
            except Exception as exc:
                logger.error(f"Audio streaming error: {exc}")
                session.errors.append(str(exc))
                await asyncio.sleep(5)


async def stream_frames(
    hub_url: str,
    session: SensorSession,
    duration_seconds: int,
) -> None:
    """Stream synthetic frame data."""
    if not session.connected or not session.member_id:
        return
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    start_time = time.time()
    frame_interval = 0.5  # 2 FPS
    
    async with aiohttp.ClientSession() as http_session:
        while time.time() - start_time < duration_seconds:
            try:
                # Generate synthetic JPEG data (10KB placeholder)
                # In reality, this would be actual JPEG data
                frame_data = bytes([0xFF, 0xD8] + [random.randint(0, 255) for _ in range(10000)] + [0xFF, 0xD9])
                
                # Upload frame
                upload_url = f"{hub_url}/api/members/{session.member_id}/frames"
                
                data = aiohttp.FormData()
                data.add_field("frame", frame_data, filename="frame.jpg")
                
                async with http_session.post(
                    upload_url,
                    data=data,
                    ssl=ssl_context,
                ) as resp:
                    if resp.status in (200, 202):
                        session.frames_sent += 1
                        if session.frames_sent % 20 == 0:
                            logger.info(f"Frames sent: {session.frames_sent}")
                    else:
                        error = await resp.text()
                        logger.warning(f"Frame upload failed: {resp.status}")
                
                await asyncio.sleep(frame_interval)
                
            except Exception as exc:
                logger.error(f"Frame streaming error: {exc}")
                await asyncio.sleep(1)


async def send_heartbeats(
    hub_url: str,
    session: SensorSession,
    duration_seconds: int,
) -> None:
    """Send periodic heartbeats."""
    if not session.connected or not session.member_id:
        return
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as http_session:
        while time.time() - start_time < duration_seconds:
            try:
                heartbeat_url = f"{hub_url}/api/members/{session.member_id}/heartbeat"
                
                async with http_session.post(heartbeat_url, ssl=ssl_context) as resp:
                    if resp.status != 200:
                        logger.warning(f"Heartbeat failed: {resp.status}")
                
                await asyncio.sleep(15)  # Heartbeat every 15 seconds
                
            except Exception as exc:
                logger.debug(f"Heartbeat error: {exc}")
                await asyncio.sleep(5)


async def run_sensor(
    hub_url: str,
    name: str,
    duration_seconds: int,
) -> SensorSession:
    """Run a complete sensor session."""
    logger.info(f"Starting sensor: {name}")
    logger.info(f"Hub URL: {hub_url}")
    logger.info(f"Duration: {duration_seconds}s")
    
    # Join
    session = await join_as_sensor(hub_url, name)
    if not session.connected:
        logger.error("Failed to connect")
        return session
    
    # Start streaming tasks
    logger.info("Starting data streams...")
    await asyncio.gather(
        stream_audio(hub_url, session, duration_seconds),
        stream_frames(hub_url, session, duration_seconds),
        send_heartbeats(hub_url, session, duration_seconds),
    )
    
    logger.info(f"Sensor session complete:")
    logger.info(f"  Audio chunks: {session.audio_chunks_sent}")
    logger.info(f"  Frames: {session.frames_sent}")
    logger.info(f"  Errors: {len(session.errors)}")
    
    return session


async def main():
    parser = argparse.ArgumentParser(description="Simulate Osk sensor")
    parser.add_argument("--hub-url", default="https://10.0.0.60:8444", help="Hub URL")
    parser.add_argument("--name", default="Simulated-Sensor-01", help="Sensor name")
    parser.add_argument("--duration", type=int, default=3600, help="Duration in seconds")
    args = parser.parse_args()
    
    session = await run_sensor(args.hub_url, args.name, args.duration)
    
    return 0 if session.connected and len(session.errors) < 10 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
