"""QR code generation for Osk operation join URLs."""

from __future__ import annotations

import io
from pathlib import Path

import qrcode
from qrcode.image.pure import PyPNGImage


def build_join_url(host: str, port: int, token: str) -> str:
    return f"https://{host}:{port}/join?token={token}"


def generate_qr_ascii(data: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf)
    return buf.getvalue()


def generate_qr_png(data: str, output_path: Path) -> None:
    qr = qrcode.QRCode(border=2)
    qr.add_data(data)
    qr.make(fit=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = qr.make_image(image_factory=PyPNGImage)
    img.save(str(output_path))
