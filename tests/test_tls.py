from __future__ import annotations

from pathlib import Path

from osk.tls import generate_self_signed_cert


def test_generate_cert(tmp_path: Path) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    generate_self_signed_cert(cert_path, key_path)
    assert cert_path.exists()
    assert key_path.exists()
    assert cert_path.stat().st_size > 0
    assert key_path.stat().st_size > 0


def test_cert_contains_pem_markers(tmp_path: Path) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    generate_self_signed_cert(cert_path, key_path)
    assert "BEGIN CERTIFICATE" in cert_path.read_text()
    assert "BEGIN" in key_path.read_text()


def test_no_overwrite_existing(tmp_path: Path) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    generate_self_signed_cert(cert_path, key_path)
    mtime = cert_path.stat().st_mtime
    generate_self_signed_cert(cert_path, key_path)
    assert cert_path.stat().st_mtime == mtime
