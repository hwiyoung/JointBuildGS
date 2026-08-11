#!/usr/bin/env python3
"""Build a compact inline visual from the measured Roofer comparison panel."""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image


ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_roofer_vis_v1/"
    "P2-E3-LOCAL-4906982-ROOFER-VIS-v1"
)
TEMPLATE = Path("/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_vis_conf_v1/roofer_inline.tpl")
OUTPUT = Path("/visualization/4906982-roofer-20k-comparison.html")


def main() -> None:
    image = Image.open(ROOT / "representative_images/roofer_20k_comparison.png").convert("RGB")
    if image.width > 1600:
        image = image.resize((1600, round(image.height * 1600 / image.width)), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=84, optimize=True, progressive=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    body = TEMPLATE.read_text().replace("__ROOFER_IMAGE__", encoded)
    if "__ROOFER_IMAGE__" in body:
        raise RuntimeError("inline template placeholder replacement failed")
    OUTPUT.write_text(body)
    if OUTPUT.stat().st_size >= 2 * 1024 * 1024:
        raise RuntimeError(f"inline visualization exceeds 2MB: {OUTPUT.stat().st_size}")
    print(f"{OUTPUT} {OUTPUT.stat().st_size}")


if __name__ == "__main__":
    main()
