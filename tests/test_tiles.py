from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from osk.tiles import TileCacher, bbox_to_tiles, parse_bbox, parse_zoom_range


def test_parse_bbox() -> None:
    assert parse_bbox("39.7,-104.9,39.8,-104.8") == (39.7, -104.9, 39.8, -104.8)


def test_parse_bbox_rejects_invalid_order() -> None:
    with pytest.raises(ValueError, match="south latitude"):
        parse_bbox("39.8,-104.9,39.7,-104.8")


def test_parse_zoom_range_supports_ranges_and_lists() -> None:
    assert parse_zoom_range("13-15,17") == [13, 14, 15, 17]


def test_bbox_to_tiles_returns_tile_coordinates() -> None:
    tiles = bbox_to_tiles(39.7, -104.9, 39.8, -104.8, zoom=15)
    assert tiles
    assert all(len(tile) == 3 for tile in tiles)
    assert all(tile[0] == 15 for tile in tiles)


def test_tile_cacher_status_counts_tiles(tmp_path: Path) -> None:
    cache_root = tmp_path / "tiles"
    (cache_root / "14" / "3411").mkdir(parents=True)
    (cache_root / "14" / "3411" / "6200.png").write_bytes(b"abc")
    (cache_root / "15" / "6822").mkdir(parents=True)
    (cache_root / "15" / "6822" / "12400.png").write_bytes(b"abcdef")

    status = TileCacher(cache_root).status()

    assert status["present"] is True
    assert status["tile_count"] == 2
    assert status["total_bytes"] == 9
    assert status["zoom_levels"] == [14, 15]


@pytest.mark.asyncio
async def test_cache_area_skips_cached_tiles(tmp_path: Path) -> None:
    cache_root = tmp_path / "tiles"
    cacher = TileCacher(cache_root)
    cached_path = cacher.tile_path(14, 3411, 6200)
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(b"cached")

    calls: list[str] = []

    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **_: object) -> None:
            return None

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            calls.append(url)
            return FakeResponse(b"downloaded")

    with patch("osk.tiles.bbox_to_tiles", return_value=[(14, 3411, 6200), (14, 3411, 6201)]):
        with patch("osk.tiles.httpx.AsyncClient", FakeClient):
            stats = await cacher.cache_area((39.7, -104.9, 39.8, -104.8), [14])

    assert stats["requested_tiles"] == 2
    assert stats["downloaded_tiles"] == 1
    assert stats["skipped_tiles"] == 1
    assert stats["total_bytes"] == len(b"downloaded")
    assert cacher.tile_path(14, 3411, 6201).read_bytes() == b"downloaded"
    assert calls == ["https://tile.openstreetmap.org/14/3411/6201.png"]
