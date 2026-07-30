#!/usr/bin/env python3
"""Finalize COLMAP MVS provenance after the GPU container exits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def ply_vertices(path: Path) -> int | None:
    with path.open("rb") as f:
        for _ in range(100):
            line = f.readline().decode("ascii", errors="replace").strip()
            if line.startswith("element vertex "):
                return int(line.split()[-1])
            if line == "end_header":
                break
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/fair_pilot/vaihingen_area3.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    run_dir = ROOT / "fair-pilot" / "runs" / cfg["run_id"]
    status_file = run_dir / "mvs_step_status.tsv"
    fused_geometric = run_dir / "mvs" / "fused_source_epsg32632.ply"
    fused_photometric = run_dir / "mvs" / "fused_photometric_source_epsg32632.ply"
    steps = []
    if status_file.exists():
        for line in status_file.read_text(encoding="utf-8").splitlines():
            name, rc, elapsed, reason = line.split("\t")
            steps.append({"name": name, "returncode": int(rc), "elapsed_seconds": int(elapsed), "reason": reason})
    geometric_vertices = ply_vertices(fused_geometric) if fused_geometric.is_file() else None
    photometric_vertices = ply_vertices(fused_photometric) if fused_photometric.is_file() else None
    fused = fused_geometric if geometric_vertices and geometric_vertices > 0 else fused_photometric
    selected_vertices = geometric_vertices if fused == fused_geometric else photometric_vertices
    complete = bool(steps) and all(step["returncode"] == 0 for step in steps) and fused.is_file() and bool(selected_vertices and selected_vertices > 0)
    payload = {
        "task_id": cfg["task_id"], "run_id": cfg["run_id"], "stage": "colmap_mvs",
        "status": "complete" if complete else "partial", "gpu_mapping": "host GPU 1 -> container GPU 0",
        "training_runs": 0, "poses": "fixed DGPF daporp.dat; no SfM pose optimization",
        "source_crs": cfg["pilot"]["source_crs"], "output_crs": cfg["pilot"]["output_crs"],
        "depth_range_m": [cfg["pilot"]["mvs_depth_min_m"], cfg["pilot"]["mvs_depth_max_m"]],
        "reprojection_threshold_px": cfg["pilot"]["reprojection_error_px"], "steps": steps,
        "official_dim_fallback_available": True,
        "colmap_version_line": (run_dir / "colmap_version.txt").read_text(encoding="utf-8").strip() if (run_dir / "colmap_version.txt").exists() else "unknown",
        "colmap_image_id": os.environ.get("FAIR_COLMAP_IMAGE_ID", "not_provided"),
        "fusion_attempts": {
            "geometric_vertices": geometric_vertices,
            "photometric_vertices": photometric_vertices,
            "selected": "geometric" if fused == fused_geometric else "photometric_after_geometric_zero",
        },
    }
    if fused.is_file():
        payload["fused"] = {"path": str(fused.relative_to(ROOT)), "size_bytes": fused.stat().st_size, "sha256": sha256(fused), "vertices": ply_vertices(fused)}
    path = run_dir / "mvs_manifest.json"
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    with (run_dir / "run.log").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\tstage=colmap_mvs status={payload['status']} vertices={payload.get('fused', {}).get('vertices')}\n")
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\tstage=colmap_mvs final_status_authority=mvs_manifest.json prior_status_lines_superseded=true\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
