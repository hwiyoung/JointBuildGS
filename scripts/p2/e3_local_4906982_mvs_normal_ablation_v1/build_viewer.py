#!/usr/bin/env python3
"""Publish an add-only interactive full-LoD2 MVS-normal comparison slot."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import shape
import yaml


REPO = Path("/workspace/JointBuildGS")
ARTIFACTS = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"
TASK_ROOT = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1" / TASK_ID
CONFIG = REPO / "configs/p2/e3_local_4906982_mvs_normal_ablation_v1/viewer.yaml"
REFERENCE_GML = ARTIFACTS / "phase-payloads/p0-audit/data/raw/lod2/690_5336.gml"
STEPS = (7000, 12000, 15000, 20000)
ARMS = {
    "FUSED_VIS_CONF": "Control: supported fused MVS depth + MVC/NC",
    "FUSED_VIS_CONF_MVS_NORMAL": "Intervention: same base + supported MVS normal",
}


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None: raise RuntimeError(path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


helper = module("e4_viewer_helpers_for_mvs_normal", REPO / "scripts/p2/e4_local_4906982_55v_als_normal_ablation_v1/build_viewer.py")


def find(rows: list[dict], arm: str, step: int) -> dict:
    return next(row for row in rows if row["arm"] == arm and int(row["completed_updates"]) == step)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text()); viewer_root = Path(cfg["viewer_root"]); output = viewer_root / cfg["slot_dir"]
    precondition = json.loads((TASK_ROOT / "control/viewer_root_precondition.json").read_text())
    for name, expected in precondition["fixed_file_sha256"].items():
        if helper.sha256(viewer_root / name) != expected: raise RuntimeError(f"viewer root drift: {name}")
    if output.exists() and any(output.iterdir()):
        manifest = json.loads((output / "manifest.json").read_text())
        if manifest.get("task_id") != TASK_ID: raise RuntimeError(f"slot collision: {output}")
    (output / "data").mkdir(parents=True, exist_ok=True)
    footprint = shape(json.loads((TASK_ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())["features"][0]["geometry"])
    center = np.asarray([footprint.centroid.x, footprint.centroid.y, 584.0])
    references, reference_roofs = helper.reference_surfaces(center)
    reference_ground_z = float(np.median(np.concatenate([np.asarray(face["vertices"])[:, 1] + center[2] for face in references if face["type"] == "ReferenceGround"])))
    reference_roof_z = float(np.median(np.concatenate([np.asarray(face["vertices"])[:, 1] + center[2] for face in references if face["type"] == "ReferenceRoof"])))
    comparison = json.loads((TASK_ROOT / "metrics.json").read_text())["aggregates"]
    mvs_rows = json.loads((TASK_ROOT / "mvs_surface_audit.json").read_text())["rows"]
    lod2_rows = json.loads((TASK_ROOT / "lod2_fused_evaluation.json").read_text())["rows"]
    panels = []
    for arm, label in ARMS.items():
        for step in STEPS:
            work = TASK_ROOT / f"arms/{arm}/R1/evaluation/step_{step:06d}/fusion"
            cloud = laspy.read(work / "classified_surface.laz")
            xyz = np.column_stack((cloud.x, cloud.y, cloud.z)).astype(np.float64)
            mapped = np.column_stack((xyz[:, 0] - center[0], xyz[:, 2] - center[2], -(xyz[:, 1] - center[1])))
            classes = np.asarray(cloud.classification)
            normals = np.column_stack((cloud["NormalX"], cloud["NormalY"], cloud["NormalZ"])).astype(np.float64)
            rooflike = (classes == 6) & (np.abs(normals[:, 2]) >= .7)
            city = next((work / "roofer/output").glob("*.city.jsonl")); surfaces, attributes = helper.city_surfaces(city, center)
            exterior = [np.asarray(face["vertices"]) for face in surfaces if face["type"] == "WallSurface" and face.get("on_footprint_edge") is True]
            wall_heights = [float(np.ptp(vertices[:, 1])) for vertices in exterior]
            mvs = find(mvs_rows, arm, step); lod2 = find(lod2_rows, arm, step); aggregate = comparison[str(step)][arm]
            body = {
                "schema": "jointbuildgs.viewer.mvs_normal_case.v1", "arm": arm, "label": label, "completed_updates": step,
                "center_epsg25832": center.tolist(),
                "points": {"class6": np.round(helper.sample(mapped[classes == 6], 22000), 3).tolist(), "class2": np.round(helper.sample(mapped[classes == 2], 7000), 3).tolist(),
                           "normal_axes": helper.sampled_normal_axes(mapped, normals, xyz, rooflike, reference_roofs)},
                "counts": {"all": int(len(xyz)), "class6": int((classes == 6).sum()), "rooflike_class6": int(rooflike.sum()), "class2": int((classes == 2).sum()),
                           "predicted_roof_faces": sum(face["type"] == "RoofSurface" for face in surfaces), "predicted_wall_faces": sum(face["type"] == "WallSurface" for face in surfaces), "predicted_ground_faces": sum(face["type"] == "GroundSurface" for face in surfaces)},
                "reference": {"surfaces": references, "path": str(REFERENCE_GML), "evaluation_only": True, "z_shift_to_prediction_space_m": 45.7},
                "roofer": {"surfaces": surfaces, "attributes": attributes},
                "metrics": {
                    "roofer_coverage": lod2["grid_coverage_fraction"], "roofer_fscore_0p5": None, "roofer_internal_rmse": None,
                    "roofer_reference_normal_median": lod2["normal_angle_deg_median"], "roofer_surface_count": sum(face["type"] == "RoofSurface" for face in surfaces),
                    "classified_grid_coverage": mvs["ordinary_grid_coverage_of_mvs"], "classified_center_coverage": lod2["coherent_center_grid_coverage_fraction"],
                    "classified_normal_median": mvs["ordinary_normal_angle_deg_median"], "classified_normal_p95": mvs["ordinary_normal_angle_deg_p95"],
                    "reference_ground_z": reference_ground_z, "reference_building_height": reference_roof_z - reference_ground_z,
                    "roofer_ground_z": attributes.get("rf_h_ground"), "roofer_ground_z_error": None if attributes.get("rf_h_ground") is None else float(attributes["rf_h_ground"] - reference_ground_z),
                    "roofer_exterior_wall_height_median": None if not wall_heights else float(np.median(wall_heights)), "roofer_exterior_wall_height_max": None if not wall_heights else float(np.max(wall_heights)),
                    "lod2_abs_dz_median": lod2["abs_dz_m_median"], "lod2_normal_median": lod2["normal_angle_deg_median"],
                    "mvs_p2plane_median": mvs["ordinary_point_to_plane_m_median"], "gaussian_z_gt_650": int(aggregate["z_gt_650"]["mean"]),
                },
                "sources": {"classified_laz": str(work / "classified_surface.laz"), "cityjsonseq": str(city)}, "scientific_verdict": None,
            }
            (output / "data" / f"{arm}_{step:06d}.json").write_text(json.dumps(body, separators=(",", ":")) + "\n")
            if step == 20000: panels.append((arm, label, xyz[classes == 6], surfaces, body["metrics"]))
    manifest = {"schema": "jointbuildgs.viewer.mvs_normal_ablation.v1", "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982",
                "arms": [{"id": arm, "label": label} for arm, label in ARMS.items()], "steps": list(STEPS), "default": {"arm": "FUSED_VIS_CONF_MVS_NORMAL", "step": 20000}, "scientific_verdict": None}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    page = helper.page_html().replace("55-view E4 ALS normal ablation Roofer", "55-view MVS normal ablation Roofer").replace("DEBY_LOD2_4906982 · Roofer LoD2", "DEBY_LOD2_4906982 · MVS normal ablation")
    page = page.replace("Roofer LoD2", "MVS normal + Roofer LoD2")
    app = helper.app_js().replace("E4_ALS_PRIOR_ONLY", "FUSED_VIS_CONF_MVS_NORMAL")
    app = app.replace("Roofer output roof coverage", "Fused roof grid coverage vs reference").replace("Roofer output/reference normal", "Fused/reference normal").replace("Input class6/reference normal", "MVS-reference ordinary normal").replace("Input center roof coverage", "Fused coherent center coverage")
    (output / "index.html").write_text(page); (output / "app.js").write_text(app)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    for axis, (_arm, label, points, surfaces, metrics) in zip(axes, panels):
        subset = helper.sample(points, 25000); axis.scatter(subset[:, 0], subset[:, 1], c=subset[:, 2], s=.3, cmap="viridis", alpha=.28, rasterized=True)
        for face in surfaces:
            if face["type"] != "RoofSurface": continue
            vertices = np.asarray(face["vertices"]); axis.plot(vertices[:, 0] + center[0], -vertices[:, 2] + center[1], color="#ff8c24", linewidth=1.3)
        axis.set_aspect("equal"); axis.set_title(f"{label}\nMVS p2plane={metrics['mvs_p2plane_median']:.4f}m · normal={metrics['classified_normal_median']:.2f}°")
        axis.set_xlabel("EPSG:25832 X"); axis.set_ylabel("Y")
    image = TASK_ROOT / "representative_images/roofer_2arm_20k_top.png"; image.parent.mkdir(parents=True, exist_ok=True); fig.savefig(image, dpi=170); plt.close(fig)
    fixed_after = {name: helper.sha256(viewer_root / name) for name in precondition["fixed_file_sha256"]}
    if fixed_after != precondition["fixed_file_sha256"]: raise RuntimeError("viewer root changed")
    receipt = {"schema": "jointbuildgs.viewer.add_only_slot_receipt.v1", "slot_id": cfg["slot_dir"], "slot_path": str(output), "relative_url": f"{cfg['slot_dir']}/index.html",
               "root_fixed_sha256_before_after_equal": True, "source_artifacts_modified": False, "files": {str(path.relative_to(output)): helper.sha256(path) for path in sorted(output.rglob("*")) if path.is_file()}, "scientific_verdict": None}
    (TASK_ROOT / "viewer_slot.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    contract_path = TASK_ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text()); contract.update({"status": "COMPLETE_MEASURED_VIEWER_PUBLISHED", "viewer_slot": cfg["slot_dir"], "scientific_verdict": None}); contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"slot": str(output), "cases": len(ARMS) * len(STEPS), "root_preserved": True}, indent=2))


if __name__ == "__main__": main()
