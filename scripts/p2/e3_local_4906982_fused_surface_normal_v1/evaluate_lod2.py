#!/usr/bin/env python3
"""Evaluation-only LoD2 roof metrics for the new two-arm task namespace."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

import laspy
import numpy as np
from shapely.geometry import shape
import yaml


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
REFERENCE = AR / "phase-payloads/p0-audit/data/raw/lod2/690_5336.gml"
CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml"
MODULE = REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py"
ARMS = ("FUSED_VIS_CONF", "FUSED_VIS_CONF_FUSED_NORMAL")
STEPS = (7000, 12000, 15000, 20000)


def load_module():
    spec = importlib.util.spec_from_file_location("readout_metric", MODULE)
    if spec is None or spec.loader is None: raise RuntimeError(MODULE)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


def alias_normals(source: Path, target: Path) -> None:
    cloud = laspy.read(source)
    names = {str(name).lower(): str(name) for name in cloud.point_format.dimension_names}
    if all(name.lower() in names for name in ("NormalX", "NormalY", "NormalZ")): cloud.write(target); return
    for destination, source_name in (("NormalX", "normal_x"), ("NormalY", "normal_y"), ("NormalZ", "normal_z")):
        cloud.add_extra_dim(laspy.ExtraBytesParams(name=destination, type=np.float32))
        cloud[destination] = np.asarray(cloud[names[source_name]], dtype=np.float32)
    cloud.write(target)


def main() -> None:
    metric = load_module(); cfg = yaml.safe_load(CONFIG.read_text())
    footprint_doc = json.loads((ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())
    feature = next(item for item in footprint_doc["features"] if str(item["properties"].get("stable_id")) == "DEBY_LOD2_4906982")
    footprint = shape(feature["geometry"]); refs = metric.parse_reference_roofs(REFERENCE, "DEBY_LOD2_4906982")
    rows = []
    with tempfile.TemporaryDirectory(prefix="jbgs-lod2-eval-") as temporary:
        temporary = Path(temporary)
        for arm in ARMS:
            for step in STEPS:
                source = ROOT / f"arms/{arm}/R1/evaluation/step_{step:06d}/fusion/fused_surface.laz"
                alias = temporary / f"{arm}_{step:06d}.laz"; alias_normals(source, alias)
                values = metric.point_metrics(alias, footprint, refs, cfg, classified=False)
                values.update({"arm": arm, "replica": "R1", "completed_updates": step,
                               "source_fused_surface": str(source), "normal_alias_applied_in_temporary_copy": True,
                               "scientific_verdict": None})
                rows.append(values)
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_surface_normal_v1.lod2_fused_evaluation.v1",
        "reference": {"path": str(REFERENCE), "evaluation_only": True, "prediction_z_shift_to_reference_m": float(cfg["prediction_z_shift_to_reference_m"])},
        "reference_used_in_training_mask_view_or_checkpoint_selection": False,
        "normal_alias_reason": "fused LAZ stores normal_x/y/z while the frozen metric library resolves NormalX/Y/Z",
        "source_artifacts_modified": False, "rows": rows, "scientific_verdict": None,
    }
    (ROOT / "lod2_fused_evaluation.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    keys = sorted(set().union(*(row.keys() for row in rows)))
    with (ROOT / "lod2_fused_evaluation.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"status": "COMPLETE", "rows": len(rows), "evaluation_only": True, "scientific_verdict": None}, indent=2))


if __name__ == "__main__": main()
