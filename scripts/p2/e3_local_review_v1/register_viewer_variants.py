#!/usr/bin/env python3
"""Register completed 7k/30k local Roofer runs as 8876 display variants."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


SCHEMA = "jointbuildgs.p2.e3_local_4906982.viewer_variants.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--extra-specs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = args.task_root.resolve()
    selection = load(args.selection)
    if selection.get("selected", {}).get("step") != 7000:
        raise RuntimeError("best-validation checkpoint is not the locked 7k selection")
    specs = [
        {
            "id": "BESTVAL_7K", "label": "7k best-val PSNR",
            "run_name": "E3_LOCAL_4906982_BESTVAL_7K", "step": 7000,
            "default": True, "validation_selected": True,
            "checkpoint_sha256": selection["selected"]["checkpoint_sha256"],
        },
        {
            "id": "FINAL_30K", "label": "30k final",
            "run_name": "E3_LOCAL_4906982_FINAL_30K", "step": 30000,
            "default": False, "validation_selected": False,
            "checkpoint_sha256": sha256(
                task / "runs/E3_LOCAL_4906982_2DGS_V6_DIST0_RESETOFF_30K/seed0/ckpt/final.pt"
            ),
        },
    ]
    if args.extra_specs:
        extras = load(args.extra_specs)
        if not isinstance(extras, list):
            raise RuntimeError("extra-specs must contain a JSON list")
        specs.extend(extras)
    variants = []
    for spec in specs:
        variant_id = str(spec["id"])
        label = str(spec["label"])
        run_name = str(spec["run_name"])
        step = int(spec["step"])
        is_default = bool(spec.get("default", False))
        run = task / "runs" / run_name
        extraction = load(run / "pointcloud/extraction_receipt.json")
        classified = load(run / "roofer/classified_scene_receipt.json")
        roofer = load(run / "roofer/receipt.json")
        if extraction["checkpoint"]["sha256"] != str(spec["checkpoint_sha256"]):
            raise RuntimeError(f"{variant_id} checkpoint identity drifted")
        variants.append({
            "id": variant_id,
            "label": label,
            "run_name": run_name,
            "step": step,
            "default": is_default,
            "validation_selected": bool(spec.get("validation_selected", False)),
            "checkpoint": extraction["checkpoint"],
            "depth_fusion": {
                "pointcloud": extraction["pointcloud"],
                "mesh": extraction["mesh"],
                "alpha_threshold": extraction["alpha_threshold"],
                "training_view_count": extraction["training_view_count"],
            },
            "classified_scene": {
                "path": str(run / "roofer/classified_scene.laz"),
                "sha256": roofer["classified_scene"]["sha256"],
                "point_count": classified["point_count"],
                "class_counts": classified["class_counts"],
            },
            "roofer": roofer,
        })
    payload = {
        "schema": SCHEMA,
        "building_id": "DEBY_LOD2_4906982",
        "base_condition": "E3",
        "selection_receipt": str(args.selection.resolve()),
        "selection_receipt_sha256": sha256(args.selection),
        "variants": variants,
        "display_rule": "PRESERVE_CANONICAL_E3_AND_EXPOSE_REGISTERED_LOCAL_VARIANTS",
        "downstream_metrics_used_for_checkpoint_selection": False,
        "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": "registered", "variants": len(variants)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
