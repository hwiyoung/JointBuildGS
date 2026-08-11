#!/usr/bin/env python3
"""Render the completed 20k fused-view-support 3D comparison read-only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from shapely import contains_xy


REPO = Path("/workspace/JointBuildGS")
ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1")
OUTPUT = ROOT / "representative_images/geometry_3d"
MVS_NPY = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1/P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/fused_seed/mvs_xyz_f32.npy")
SOURCE = REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/render_3d_comparison.py"
ARMS = ("MVS_SURFACE_METRIC", "FUSED_VIS_CONF")
LABELS = {
    "MVS_SURFACE_METRIC": "All fused mesh ray hits",
    "FUSED_VIS_CONF": "View-supported fused target",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_renderer():
    spec = importlib.util.spec_from_file_location("mvs_surface_3d_renderer", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.OUTPUT = OUTPUT
    module.ARMS = ARMS
    module.LABELS = LABELS
    module.REPO = REPO
    return module


def main() -> None:
    renderer = load_renderer()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    footprint = renderer.footprint_geometry()
    mvs = np.load(MVS_NPY).astype(np.float64) + renderer.SHIFT
    mvs = mvs[contains_xy(footprint, mvs[:, 0], mvs[:, 1])]
    fused = {arm: renderer.fused_points(arm) for arm in ARMS}
    gaussian = {arm: renderer.checkpoint_geometry(arm) for arm in ARMS}
    renderer.surface_figure(footprint, mvs, fused)
    renderer.tail_figure(footprint, gaussian)
    renderer.interactive_payload(footprint, mvs, fused, gaussian)

    outputs = (
        "ordinary_surface_3d.png",
        "high_z_tail_3d.png",
        "geometry_3d_samples.json",
    )
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_vis_conf_v1.geometry_3d_receipt.v1",
        "status": "COMPLETE",
        "comparison": list(ARMS),
        "completed_updates": 20000,
        "inputs": {
            "checkpoints": 2,
            "fused_surfaces": 2,
            "filtered_mvs_reference": str(MVS_NPY),
            "shared_xy_footprint": str(ROOT / "control/shared_standard_footprint_4906982.geojson"),
        },
        "output_sha256": {name: sha256(OUTPUT / name) for name in outputs},
        "lod2_z_or_roof_geometry_used": False,
        "scientific_verdict": None,
    }
    (OUTPUT / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    source_hashes = provenance.setdefault("source_config_sha256", {})
    for relative in (
        "scripts/p2/e3_local_4906982_fused_vis_conf_v1/render_3d_comparison.py",
        "scripts/p2/e3_local_4906982_fused_vis_conf_v1/build_inline_3d.py",
    ):
        source_hashes[relative] = sha256(REPO / relative)
    output_hashes = provenance.setdefault("output_index_sha256", {})
    for name in (*outputs, "receipt.json"):
        output_hashes[f"representative_images/geometry_3d/{name}"] = sha256(OUTPUT / name)
    provenance["scientific_verdict"] = None
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
