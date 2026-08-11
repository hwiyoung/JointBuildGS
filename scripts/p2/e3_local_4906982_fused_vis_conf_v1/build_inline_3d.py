#!/usr/bin/env python3
"""Compress the measured 3D panels and fill the inline-visual template."""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image


ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1")
VIS = Path("/visualization")
TEMPLATE = VIS / "4906982-fused-view-support-3d.tpl"
OUTPUT = VIS / "4906982-fused-view-support-3d.html"


def encoded(name: str, width: int) -> str:
    image = Image.open(ROOT / "representative_images/geometry_3d" / name).convert("RGB")
    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True, progressive=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def main() -> None:
    body = TEMPLATE.read_text()
    body = body.replace("__ORDINARY_IMAGE__", encoded("ordinary_surface_3d.png", 1600))
    body = body.replace("__HIGH_Z_IMAGE__", encoded("high_z_tail_3d.png", 1600))
    if "__ORDINARY_IMAGE__" in body or "__HIGH_Z_IMAGE__" in body:
        raise RuntimeError("inline template placeholder replacement failed")
    OUTPUT.write_text(body)
    if OUTPUT.stat().st_size >= 2 * 1024 * 1024:
        raise RuntimeError(f"inline visualization exceeds 2MB: {OUTPUT.stat().st_size}")
    print(f"{OUTPUT} {OUTPUT.stat().st_size}")


if __name__ == "__main__":
    main()
