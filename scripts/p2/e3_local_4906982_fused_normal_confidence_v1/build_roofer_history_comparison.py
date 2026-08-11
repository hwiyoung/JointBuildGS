#!/usr/bin/env python3
"""Render filled Roofer roof and full-solid comparisons across comparable 55-view arms."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import laspy
import numpy as np
from matplotlib.patches import Polygon as PolygonPatch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely import contains_xy, distance, points
from shapely.geometry import shape


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1/P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"
FIXED = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
COMMON = AR / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
ALS_ABL = AR / "phase-payloads/p2/e4_local_4906982_55v_als_normal_ablation_v1/P2-E4-LOCAL-4906982-55V-ALS-NORMAL-ABLATION-v1"
ALS_FULL = AR / "phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
OUT = ROOT / "representative_images/roofer_history_comparison_v1"
BUILDING = "DEBY_LOD2_4906982"

ARMS = [
    ("FUSED_VIS_CONF", "MVS depth only", ROOT, "FUSED_VIS_CONF"),
    ("FUSED_VIS_CONF_FUSED_NORMAL", "Fused N · previous mask", FIXED, "FUSED_VIS_CONF_FUSED_NORMAL"),
    ("FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT", "Fused N · depth mask", COMMON, "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT"),
    ("FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE", "Fused N · confidence mask", ROOT, "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE"),
    ("ALS_DEPTH_ONLY", "ALS depth only", ALS_ABL, "ALS_DEPTH_ONLY"),
    ("E4_ALS_PRIOR_ONLY", "ALS depth + normal", ALS_FULL, "E4_ALS_PRIOR_ONLY"),
]


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def city_path(root: Path, arm: str) -> Path:
    return next((root / f"arms/{arm}/R1/evaluation/step_020000/fusion/roofer/output").glob("*.city.jsonl"))


def polygons(surface, flatten):
    return flatten(surface.polygon)


def sample_xy(xy: np.ndarray, maximum: int) -> np.ndarray:
    if len(xy) <= maximum:
        return xy
    return xy[np.linspace(0, len(xy) - 1, maximum, dtype=np.int64)]


def add_plan_surface(ax, surface, flatten, face_index: int, predicted: bool) -> None:
    for poly in polygons(surface, flatten):
        coords = np.asarray(poly.exterior.coords, dtype=np.float64)
        if predicted:
            patch = PolygonPatch(coords, closed=True, facecolor="#f28e2b", edgecolor="#b54f00", alpha=0.42, linewidth=1.4)
            ax.add_patch(patch)
            c = poly.representative_point()
            ax.text(c.x, c.y, f"P{face_index}", fontsize=7, ha="center", va="center", color="#6b2b00")
        else:
            patch = PolygonPatch(coords, closed=True, facecolor="#4e9ec2", edgecolor="#007c9e", alpha=0.23, linewidth=1.4, linestyle="--")
            ax.add_patch(patch)
            c = poly.representative_point()
            ax.text(c.x, c.y, f"R{face_index}", fontsize=7, ha="center", va="center", color="#005c78")


def main() -> None:
    evaluator = module("roofer_history_evaluator", REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py")
    solid_lib = module("roofer_history_solid", REPO / "scripts/p2/e4_local_4906982_55v_als_normal_ablation_v1/build_viewer.py")
    footprint = shape(json.loads((ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())["features"][0]["geometry"])
    center = np.asarray([footprint.centroid.x, footprint.centroid.y, 584.0])
    reference = evaluator.parse_reference_roofs(AR / "phase-payloads/p0-audit/data/raw/lod2/690_5336.gml", BUILDING)
    reference_solid, _ = solid_lib.reference_surfaces(center)
    ref_ground = float(np.median(np.concatenate([np.asarray(face["vertices"], dtype=np.float64)[:, 1] + center[2] for face in reference_solid if face["type"] == "ReferenceGround"])))
    ref_roof = float(np.median(np.concatenate([np.asarray(face["vertices"], dtype=np.float64)[:, 1] + center[2] for face in reference_solid if face["type"] == "ReferenceRoof"])))
    current_metrics = json.loads((ROOT / "roofer_surface_evaluation.json").read_text())["rows"]
    als_metrics = {row["arm"]: row for row in json.loads((ALS_ABL / "three_arm_metrics.json").read_text())["rows"]}
    records = []
    loaded = {}
    for visible, label, root, source_arm in ARMS:
        path = city_path(root, source_arm)
        classified_path = root / f"arms/{source_arm}/R1/evaluation/step_020000/fusion/classified_surface.laz"
        roofs, vertices = evaluator.load_cityjsonseq(path, BUILDING, -45.7)
        solid, attrs = solid_lib.city_surfaces(path, center)
        cloud = laspy.read(classified_path)
        cloud_x = np.asarray(cloud.x)
        cloud_y = np.asarray(cloud.y)
        cloud_z = np.asarray(cloud.z)
        cloud_class = np.asarray(cloud.classification)
        cloud_inside = contains_xy(footprint, cloud_x, cloud_y)
        cloud_distance = distance(points(cloud_x, cloud_y), footprint)
        class2 = cloud_class == 2
        class6 = cloud_class == 6
        true_ground_band = (cloud_z >= 555.0) & (cloud_z <= 561.0)
        roof_band = (cloud_z >= 580.0) & (cloud_z <= 585.0)
        walls = [np.asarray(face["vertices"], dtype=np.float64) for face in solid if face["type"] == "WallSurface" and face.get("on_footprint_edge") is True]
        wall_heights = [float(np.ptp(face[:, 1])) for face in walls]
        roof_vertices_z = np.concatenate([
            np.asarray(face["vertices"], dtype=np.float64)[:, 1] + center[2]
            for face in solid if face["type"] == "RoofSurface"
        ])
        if visible in als_metrics:
            metric = als_metrics[visible]
            coverage = metric["roofer_roof_xy_coverage"]
            fscore = metric["roofer_fscore_0p5m"]
            normal = metric["roofer_reference_normal_median_deg"]
            internal = metric["roofer_internal_rmse_m"]
        else:
            metric = next(row for row in current_metrics if row["arm"] == visible and row["completed_updates"] == 20000)
            coverage = metric["roofer_roof_xy_coverage_fraction"]
            fscore = metric["roofer_surface_fscore_0p5m"]
            normal = metric["roofer_surface_normal_angle_deg_median"]
            checkpoint_rows = []
            with (root / "checkpoint_metrics.csv").open() as stream:
                import csv
                checkpoint_rows = list(csv.DictReader(stream))
            checkpoint = next(row for row in checkpoint_rows if row["arm"] == source_arm and int(row["completed_updates"]) == 20000)
            internal = float(checkpoint["roofer_rmse_lod22"])
        ground = float(attrs.get("rf_h_ground"))
        record = {
            "arm": visible,
            "label": label,
            "source_cityjsonseq": str(path),
            "source_classified_laz": str(classified_path),
            "roof_surface_count": len(roofs),
            "roof_xy_coverage": float(coverage),
            "surface_fscore_0p5m": float(fscore),
            "surface_normal_median_deg": float(normal),
            "internal_rmse": float(internal),
            "ground_z_m": ground,
            "roof_vertex_z_median_m": float(np.median(roof_vertices_z)),
            "roof_vertex_z_min_m": float(np.min(roof_vertices_z)),
            "roof_vertex_z_max_m": float(np.max(roof_vertices_z)),
            "ground_to_roof_vertex_median_m": float(np.median(roof_vertices_z) - ground),
            "reference_ground_z_m": ref_ground,
            "ground_z_error_m": ground - ref_ground,
            "exterior_wall_height_median_m": None if not wall_heights else float(np.median(wall_heights)),
            "exterior_wall_height_max_m": None if not wall_heights else float(np.max(wall_heights)),
            "reference_building_height_m": ref_roof - ref_ground,
            "footprint_inside_point_count": int(np.count_nonzero(cloud_inside)),
            "class2_inside_count": int(np.count_nonzero(class2 & cloud_inside)),
            "class2_inside_fraction": float(np.count_nonzero(class2 & cloud_inside) / max(np.count_nonzero(cloud_inside), 1)),
            "class2_inside_true_ground_band_count": int(np.count_nonzero(class2 & cloud_inside & true_ground_band)),
            "class2_inside_roof_band_count": int(np.count_nonzero(class2 & cloud_inside & roof_band)),
            "class2_outside_true_ground_band_count": int(np.count_nonzero(class2 & ~cloud_inside & true_ground_band)),
            "class2_outside_true_ground_band_within_3m_count": int(np.count_nonzero(class2 & ~cloud_inside & true_ground_band & (cloud_distance <= 3.0))),
            "roof_faces": [
                {
                    "area_m2": float(surface.polygon.area),
                    "area_fraction_of_footprint": float(surface.polygon.area / footprint.area),
                    "tilt_deg": float(np.degrees(np.arccos(np.clip(surface.normal()[2], -1.0, 1.0)))),
                    "z_at_centroid_m": float(surface.z_at(surface.polygon.centroid.x, surface.polygon.centroid.y)),
                }
                for surface in roofs
            ],
            "scientific_verdict": None,
        }
        records.append(record)
        loaded[visible] = {
            "roofs": roofs,
            "solid": solid,
            "record": record,
            "classification_xy": {
                "class2_inside_roof": sample_xy(np.column_stack((cloud_x[class2 & cloud_inside & roof_band], cloud_y[class2 & cloud_inside & roof_band])), 8000),
                "class2_outside_ground": sample_xy(np.column_stack((cloud_x[class2 & ~cloud_inside & true_ground_band], cloud_y[class2 & ~cloud_inside & true_ground_band])), 8000),
                "class6_inside": sample_xy(np.column_stack((cloud_x[class6 & cloud_inside], cloud_y[class6 & cloud_inside])), 2500),
            },
        }

    min_x, min_y, max_x, max_y = footprint.bounds
    pad = 2.0
    fig, axes = plt.subplots(2, 4, figsize=(18, 10), constrained_layout=True)
    plan_panels = [("REFERENCE", "Evaluation reference", reference, None), *[(arm, label, loaded[arm]["roofs"], loaded[arm]["record"]) for arm, label, _, _ in ARMS]]
    for ax, (arm, label, surfaces, record) in zip(axes.flat, plan_panels):
        for index, surface in enumerate(reference, 1):
            add_plan_surface(ax, surface, evaluator.flatten_polygons, index, predicted=False)
        if arm != "REFERENCE":
            for index, surface in enumerate(surfaces, 1):
                add_plan_surface(ax, surface, evaluator.flatten_polygons, index, predicted=True)
            ax.set_title(f"{label}\ncoverage {100*record['roof_xy_coverage']:.2f}% · F@0.5 {record['surface_fscore_0p5m']:.3f}\nfaces {record['roof_surface_count']} · normal {record['surface_normal_median_deg']:.2f}°", fontsize=10)
        else:
            ax.set_title(f"{label}\nfaces {len(reference)} · blue dashed/fill = reference", fontsize=10)
        ax.set_xlim(min_x - pad, max_x + pad)
        ax.set_ylim(min_y - pad, max_y + pad)
        ax.set_aspect("equal")
        ax.grid(True, linewidth=0.3, alpha=0.35)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("EPSG:25832 X", fontsize=8)
        ax.set_ylabel("EPSG:25832 Y", fontsize=8)
    axes.flat[-1].axis("off")
    fig.suptitle("DEBY_LOD2_4906982 · Roofer RoofSurface · filled plan comparison at 20k\nblue dashed/fill: evaluation reference · orange fill: prediction · P/R labels: individual faces", fontsize=14)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "roofer_roof_filled_7panel_20k.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(16, 8), sharex=True, sharey=True, constrained_layout=True)
    min_local_x = min_x - center[0]
    max_local_x = max_x - center[0]
    for ax, (arm, label, _, _) in zip(axes.flat, ARMS):
        item = loaded[arm]
        for face in item["solid"]:
            if face["type"] != "RoofSurface":
                continue
            vertices = np.asarray(face["vertices"], dtype=np.float64)
            ax.plot(vertices[:, 0], vertices[:, 1] + center[2], color="#d55e00", linewidth=1.3, alpha=0.85)
            ax.scatter(vertices[:, 0], vertices[:, 1] + center[2], color="#d55e00", s=5, alpha=0.8)
        ax.axhline(ref_ground, color="#4d4d4d", linestyle="--", linewidth=1.2, label="reference ground")
        ax.axhline(ref_roof, color="#009ec1", linestyle="--", linewidth=1.2, label="reference roof median")
        ax.axhline(item["record"]["ground_z_m"], color="#b2182b", linewidth=1.8, label="predicted ground")
        ax.fill_between([min_local_x, max_local_x], ref_ground, ref_roof, color="#009ec1", alpha=0.06)
        ax.set_title(f"{label}\nground error {item['record']['ground_z_error_m']:+.2f}m · wall med {item['record']['exterior_wall_height_median_m']:.2f}m", fontsize=10)
        ax.grid(True, linewidth=0.3, alpha=0.35)
        ax.tick_params(labelsize=8)
        ax.set_xlabel("local X (m)", fontsize=8)
        ax.set_ylabel("Z (m)", fontsize=8)
    axes.flat[0].legend(fontsize=7, loc="lower right")
    axes.flat[0].set_xlim(min_local_x - pad, max_local_x + pad)
    axes.flat[0].set_ylim(ref_ground - 2.0, ref_roof + 6.0)
    fig.suptitle("Full-solid side diagnostic · orange roof vertices · red predicted ground\nreference building height 24.68m", fontsize=14)
    fig.savefig(OUT / "roofer_full_solid_side_6arm_20k.png", dpi=180)
    plt.close(fig)

    semantic_style = {
        "RoofSurface": ("#f28e2b", 0.78),
        "WallSurface": ("#59a14f", 0.46),
        "GroundSurface": ("#e15759", 0.72),
    }
    fig = plt.figure(figsize=(18, 10), constrained_layout=True)
    grid = fig.add_gridspec(2, 4)
    oblique_panels = [("REFERENCE", "Evaluation reference", reference_solid, None), *[(arm, label, loaded[arm]["solid"], loaded[arm]["record"]) for arm, label, _, _ in ARMS]]
    all_local_y = []
    for face in reference_solid:
        vertices = np.asarray(face["vertices"], dtype=np.float64)
        all_local_y.extend(vertices[:, 2].tolist())
    y_min, y_max = min(all_local_y), max(all_local_y)
    for index, (arm, label, surfaces, record) in enumerate(oblique_panels):
        ax = fig.add_subplot(grid[index // 4, index % 4], projection="3d")
        if arm != "REFERENCE":
            for face in reference_solid:
                vertices = np.asarray(face["vertices"], dtype=np.float64)
                xyz = np.column_stack((vertices[:, 0], vertices[:, 2], vertices[:, 1] + center[2]))
                closed = np.vstack((xyz, xyz[0]))
                ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color="#009ec1", linestyle="--", linewidth=0.7, alpha=0.42)
        for face in surfaces:
            face_type = ({
                "ReferenceRoof": "RoofSurface",
                "ReferenceWall": "WallSurface",
                "ReferenceGround": "GroundSurface",
            }.get(face["type"], face["type"]) if arm == "REFERENCE" else face["type"])
            if face_type not in semantic_style:
                continue
            vertices = np.asarray(face["vertices"], dtype=np.float64)
            xyz = np.column_stack((vertices[:, 0], vertices[:, 2], vertices[:, 1] + center[2]))
            color, alpha = semantic_style[face_type]
            if arm == "REFERENCE":
                color = "#009ec1" if face_type == "RoofSurface" else ("#8a8a8a" if face_type == "WallSurface" else "#4e79a7")
                alpha = 0.62 if face_type == "RoofSurface" else 0.32
            collection = Poly3DCollection([xyz], facecolor=color, edgecolor=color, linewidth=0.65, alpha=alpha)
            ax.add_collection3d(collection)
        if arm == "REFERENCE":
            ax.set_title(f"{label}\nroof {ref_roof:.2f}m · ground {ref_ground:.2f}m · height {ref_roof-ref_ground:.2f}m", fontsize=9)
        else:
            ax.set_title(
                f"{label}\nroof med {record['roof_vertex_z_median_m']:.2f}m · ground {record['ground_z_m']:.2f}m\nsolid height {record['ground_to_roof_vertex_median_m']:.2f}m · ref {record['reference_building_height_m']:.2f}m",
                fontsize=9,
            )
        ax.set_xlim(min_local_x - pad, max_local_x + pad)
        ax.set_ylim(y_min - pad, y_max + pad)
        ax.set_zlim(ref_ground - 2.0, ref_roof + 7.0)
        ax.set_box_aspect((1.0, 1.0, 0.72))
        ax.view_init(elev=25, azim=-55)
        ax.set_xlabel("X", fontsize=7, labelpad=-1)
        ax.set_ylabel("Y", fontsize=7, labelpad=-1)
        ax.set_zlabel("Z", fontsize=7, labelpad=-1)
        ax.tick_params(labelsize=6, pad=0)
    empty = fig.add_subplot(grid[1, 3]); empty.axis("off")
    fig.suptitle("Roofer CityJSON full-solid oblique comparison at 20k\ncyan dashed wireframe: evaluation reference · orange roof · green wall · red ground", fontsize=14)
    fig.savefig(OUT / "roofer_full_solid_oblique_7panel_20k.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(16, 9), sharex=True, sharey=True, constrained_layout=True)
    footprint_xy = np.asarray(footprint.exterior.coords, dtype=np.float64)
    all_bounds = []
    for arm, _, _, _ in ARMS:
        groups = loaded[arm]["classification_xy"]
        for values in groups.values():
            if len(values):
                all_bounds.append(values)
    stacked = np.vstack(all_bounds)
    x_lo, y_lo = np.quantile(stacked, 0.01, axis=0)
    x_hi, y_hi = np.quantile(stacked, 0.99, axis=0)
    for ax, (arm, label, _, _) in zip(axes.flat, ARMS):
        groups = loaded[arm]["classification_xy"]
        if len(groups["class2_outside_ground"]):
            ax.scatter(groups["class2_outside_ground"][:, 0], groups["class2_outside_ground"][:, 1], s=1.2, c="#4e79a7", alpha=0.25, rasterized=True, label="class2 true-ground Z outside")
        if len(groups["class2_inside_roof"]):
            ax.scatter(groups["class2_inside_roof"][:, 0], groups["class2_inside_roof"][:, 1], s=1.2, c="#e15759", alpha=0.24, rasterized=True, label="class2 roof-Z inside")
        if len(groups["class6_inside"]):
            ax.scatter(groups["class6_inside"][:, 0], groups["class6_inside"][:, 1], s=1.2, c="#59a14f", alpha=0.28, rasterized=True, label="class6 inside")
        ax.plot(footprint_xy[:, 0], footprint_xy[:, 1], color="#111111", linewidth=1.5, label="shared footprint")
        rec = loaded[arm]["record"]
        ax.set_title(
            f"{label}\ninside class2 {100*rec['class2_inside_fraction']:.1f}% · roof-Z {rec['class2_inside_roof_band_count']:,}\ntrue-ground class2: inside {rec['class2_inside_true_ground_band_count']:,} · outside≤3m {rec['class2_outside_true_ground_band_within_3m_count']:,}",
            fontsize=9,
        )
        ax.set_aspect("equal")
        ax.grid(True, linewidth=0.3, alpha=0.25)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("EPSG:25832 X", fontsize=8)
        ax.set_ylabel("EPSG:25832 Y", fontsize=8)
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_lo, y_hi)
    axes.flat[0].legend(fontsize=7, loc="upper right", markerscale=4)
    fig.suptitle("Roofer input classification around the shared footprint at 20k\nred: roof-height points classified as ground inside · blue: true-height ground outside", fontsize=14)
    fig.savefig(OUT / "roofer_ground_class_footprint_diagnosis_6arm_20k.png", dpi=180)
    plt.close(fig)

    payload = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.roofer_history_comparison.v1",
        "building_id": BUILDING,
        "completed_updates": 20000,
        "comparison_scope": "directly comparable 55-view, shared-footprint arms",
        "reference_roof_surface_count": len(reference),
        "reference_ground_z_m": ref_ground,
        "reference_roof_z_median_m": ref_roof,
        "rows": records,
        "evaluation_only": True,
        "scientific_verdict": None,
    }
    comparison_path = OUT / "roofer_history_comparison.json"
    comparison_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.roofer_history_comparison_receipt.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "docker": {"image": "jointbuildgs:mvc-eval-v1", "image_id": "sha256:5968cc43e93e915abc0d82ede44d718990d526eef054d6b47aa96120f00d39d1"},
        "command": ["python", "scripts/p2/e3_local_4906982_fused_normal_confidence_v1/build_roofer_history_comparison.py"],
        "source_sha256": {
            "script": sha256(REPO / "scripts/p2/e3_local_4906982_fused_normal_confidence_v1/build_roofer_history_comparison.py"),
            "reference_gml": sha256(AR / "phase-payloads/p0-audit/data/raw/lod2/690_5336.gml"),
            "shared_footprint": sha256(ROOT / "control/shared_standard_footprint_4906982.geojson"),
            **{record["arm"]: sha256(Path(record["source_cityjsonseq"])) for record in records},
        },
        "output_sha256": {
            "roofer_roof_filled_7panel_20k.png": sha256(OUT / "roofer_roof_filled_7panel_20k.png"),
            "roofer_full_solid_side_6arm_20k.png": sha256(OUT / "roofer_full_solid_side_6arm_20k.png"),
            "roofer_full_solid_oblique_7panel_20k.png": sha256(OUT / "roofer_full_solid_oblique_7panel_20k.png"),
            "roofer_ground_class_footprint_diagnosis_6arm_20k.png": sha256(OUT / "roofer_ground_class_footprint_diagnosis_6arm_20k.png"),
            "roofer_history_comparison.json": sha256(comparison_path),
        },
        "return_code": 0,
        "evaluation_only": True,
        "scientific_verdict": None,
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "COMPLETE", "output": str(OUT), "arms": len(records), "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
