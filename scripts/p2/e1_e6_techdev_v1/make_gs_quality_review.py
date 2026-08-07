from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


SCHEMA = "jointbuildgs.p2.e1_e6.gs_quality_review.v1"
RUNS = {
    "E3 image-only": "E3_GS_IMAGE",
    "E4 ALS unweighted": "E4_GS_ALS_UNWEIGHTED",
    "E5 ALS w_b": "E5_GS_ALS_WB",
    "E6 LoD planes": "E6_GS_LOD2_PLANES_DIAGNOSTIC",
}


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def panel(image: Image.Image, title: str, size: tuple[int, int]) -> Image.Image:
    fitted = ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size[0], size[1] + 34), "#161616")
    canvas.paste(fitted, (0, 34))
    ImageDraw.Draw(canvas).text((10, 9), title, fill="white")
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    artifact_root = args.artifact_root.resolve()
    task_root = args.task_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    image_root = artifact_root / "phase-payloads/p0-audit/data/work/mvs/colmap_dense/images"
    e3_renders = task_root / "runs/E3_GS_IMAGE/renders"
    view_receipts = [
        json.loads((e3_renders / f"it030000_v{slot}_depth.json").read_text(encoding="utf-8"))
        for slot in range(4)
    ]
    cell = (360, 260)
    rows: list[Image.Image] = []
    views = []
    for slot, receipt in enumerate(view_receipts):
        view_name = receipt["view_name"]
        images = [("Input image", Image.open(image_root / view_name))]
        for label, run_name in RUNS.items():
            images.append((label, Image.open(task_root / "runs" / run_name / "renders" / f"it030000_v{slot}_rgb.png")))
        panels = [panel(image, label, cell) for label, image in images]
        row = Image.new("RGB", (sum(item.width for item in panels), panels[0].height), "black")
        x = 0
        for item in panels:
            row.paste(item, (x, 0))
            x += item.width
        row_path = output_root / f"heldout_v{slot}_rgb_30k.png"
        row.save(row_path)
        rows.append(row)
        views.append({"slot": slot, "view_name": view_name, "montage": row_path.name})

    sheet = Image.new("RGB", (rows[0].width, sum(row.height for row in rows)), "black")
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    sheet.save(output_root / "heldout_rgb_30k_contact_sheet.png")

    metrics = {}
    for label, run_name in RUNS.items():
        payload = json.loads((task_root / "runs" / run_name / "metrics.json").read_text(encoding="utf-8"))
        metrics[label] = {
            "depth_held_out": payload["depth_held_out"],
            "mesh": payload["mesh"],
            "operation": payload["operation"],
        }
    atomic_json(output_root / "receipt.json", {
        "schema": SCHEMA,
        "iteration": 30000,
        "views": views,
        "metrics": metrics,
        "interpretation_constraint": "Technical diagnostic only; human reviewer retains scientific verdict.",
        "scientific_verdict": None,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
