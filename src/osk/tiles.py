"""Offline map tile caching for the coordinator dashboard."""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

import httpx

DEFAULT_TILE_URL_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_USER_AGENT = "osk/0.1 (+https://github.com/justinredmondsmith-collab/osk)"
_MAX_LATITUDE = 85.05112878


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    """Parse a bbox string in south,west,north,east order."""
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("expected bbox in south,west,north,east format")

    south, west, north, east = (float(part) for part in parts)
    if not -90.0 <= south <= 90.0 or not -90.0 <= north <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if not -180.0 <= west <= 180.0 or not -180.0 <= east <= 180.0:
        raise ValueError("longitude must be between -180 and 180")
    if south >= north:
        raise ValueError("south latitude must be less than north latitude")
    if west >= east:
        raise ValueError("west longitude must be less than east longitude")
    return south, west, north, east


def parse_zoom_range(raw: str) -> list[int]:
    """Parse a single zoom, comma list, or inclusive zoom range."""
    zooms: set[int] = set()
    for chunk in (part.strip() for part in raw.split(",")):
        if not chunk:
            continue
        if "-" in chunk:
            start_raw, end_raw = chunk.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if start > end:
                raise ValueError("zoom range start must be less than or equal to end")
            values = range(start, end + 1)
        else:
            values = (int(chunk),)
        for zoom in values:
            if not 0 <= zoom <= 22:
                raise ValueError("zoom must be between 0 and 22")
            zooms.add(zoom)

    if not zooms:
        raise ValueError("at least one zoom level is required")
    return sorted(zooms)


def _clamp_latitude(value: float) -> float:
    return max(-_MAX_LATITUDE, min(_MAX_LATITUDE, value))


def _lon_to_tile_x(lon: float, zoom: int) -> int:
    tiles_per_axis = 1 << zoom
    x = int((lon + 180.0) / 360.0 * tiles_per_axis)
    return max(0, min(tiles_per_axis - 1, x))


def _lat_to_tile_y(lat: float, zoom: int) -> int:
    latitude = _clamp_latitude(lat)
    lat_rad = math.radians(latitude)
    tiles_per_axis = 1 << zoom
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * tiles_per_axis)
    return max(0, min(tiles_per_axis - 1, y))


def bbox_to_tiles(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    zoom: int,
) -> list[tuple[int, int, int]]:
    """Return all slippy-map tiles intersecting a bbox for one zoom level."""
    x_start = _lon_to_tile_x(west, zoom)
    x_end = _lon_to_tile_x(east, zoom)
    y_start = _lat_to_tile_y(north, zoom)
    y_end = _lat_to_tile_y(south, zoom)

    return [
        (zoom, x, y)
        for x in range(min(x_start, x_end), max(x_start, x_end) + 1)
        for y in range(min(y_start, y_end), max(y_start, y_end) + 1)
    ]


class TileCacher:
    """Manage a local directory of cached XYZ PNG tiles."""

    def __init__(
        self,
        cache_root: Path,
        *,
        tile_url_template: str = DEFAULT_TILE_URL_TEMPLATE,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.cache_root = Path(cache_root)
        self.tile_url_template = tile_url_template
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def tile_path(self, z: int, x: int, y: int) -> Path:
        return self.cache_root / str(z) / str(x) / f"{y}.png"

    def is_cached(self, z: int, x: int, y: int) -> bool:
        return self.tile_path(z, x, y).exists()

    def status(self) -> dict[str, object]:
        tile_count = 0
        total_bytes = 0
        zoom_levels: set[int] = set()

        if self.cache_root.exists():
            for path in self.cache_root.rglob("*.png"):
                tile_count += 1
                total_bytes += path.stat().st_size
                try:
                    zoom_levels.add(int(path.relative_to(self.cache_root).parts[0]))
                except (ValueError, IndexError):
                    continue

        return {
            "cache_root": str(self.cache_root),
            "present": self.cache_root.exists(),
            "tile_count": tile_count,
            "total_bytes": total_bytes,
            "zoom_levels": sorted(zoom_levels),
        }

    async def download_tile(self, client: httpx.AsyncClient, z: int, x: int, y: int) -> int:
        path = self.tile_path(z, x, y)
        if path.exists():
            return 0

        response = await client.get(self.tile_url_template.format(z=z, x=x, y=y))
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return len(response.content)

    async def cache_area(
        self,
        bbox: tuple[float, float, float, float],
        zoom_levels: Iterable[int],
    ) -> dict[str, object]:
        south, west, north, east = bbox
        ordered_zooms = sorted(set(zoom_levels))
        all_tiles = sorted(
            {
                tile
                for zoom in ordered_zooms
                for tile in bbox_to_tiles(south, west, north, east, zoom=zoom)
            }
        )

        self.cache_root.mkdir(parents=True, exist_ok=True)
        stats = {
            "cache_root": str(self.cache_root),
            "requested_tiles": len(all_tiles),
            "downloaded_tiles": 0,
            "skipped_tiles": 0,
            "total_bytes": 0,
            "zoom_levels": ordered_zooms,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            for z, x, y in all_tiles:
                if self.is_cached(z, x, y):
                    stats["skipped_tiles"] += 1
                    continue
                size = await self.download_tile(client, z, x, y)
                stats["downloaded_tiles"] += 1
                stats["total_bytes"] += size

        return stats
