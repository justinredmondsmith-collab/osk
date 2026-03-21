from __future__ import annotations

from pathlib import Path

from osk.qr import build_join_url, generate_qr_ascii, generate_qr_png


def test_build_join_url() -> None:
    url = build_join_url("192.168.1.1", 8443, "abc123token")
    assert url == "https://192.168.1.1:8443/join?token=abc123token"


def test_generate_qr_ascii() -> None:
    text = generate_qr_ascii("https://example.com")
    assert len(text) > 0
    assert "\n" in text


def test_generate_qr_png(tmp_path: Path) -> None:
    out = tmp_path / "qr.png"
    generate_qr_png("https://example.com", out)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.read_bytes()[:4] == b"\x89PNG"
