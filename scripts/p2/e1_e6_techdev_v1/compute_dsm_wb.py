from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union


AOI = [690791.74, 5335864.05, 691154.65, 5336353.85]
WORLD_SHIFT = [690953.0, 5336071.0, 604.0]
ALS_Z_SHIFT = 45.7


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def write_pipeline(path: Path, stages: list[dict]) -> None:
    path.write_text(json.dumps({"pipeline": stages}, indent=2) + "\n", encoding="utf-8")
    run(["pdal", "pipeline", str(path)])


def load_xyz(tif: Path, xyz: Path) -> np.ndarray:
    run(["gdal_translate", "-q", "-of", "XYZ", str(tif), str(xyz)])
    return np.loadtxt(xyz, dtype=np.float64)


def align_grid(source: Path, target: Path) -> None:
    """Warp a PDAL raster onto the exact shared 0.5 m grid."""
    if target.is_file():
        return
    run(
        [
            "gdalwarp",
            "-q",
            "-overwrite",
            "-te",
            *(str(value) for value in AOI),
            "-tr",
            "0.5",
            "0.5",
            "-tap",
            "-r",
            "near",
            "-srcnodata",
            "-9999",
            "-dstnodata",
            "-9999",
            str(source),
            str(target),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--prep-root", type=Path, required=True)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    prep = args.prep_root.resolve()
    prep.mkdir(parents=True, exist_ok=True)
    footprint_path = artifact_root / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/"
        "freeze/shared_footprints_199.geojson"
    )
    mvs_path = artifact_root / (
        "phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/"
        "P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply"
    )
    synthetic_als = prep / "existing_als_synthetic_local_voxel030.ply"
    for path in [footprint_path, mvs_path, synthetic_als]:
        if not path.is_file():
            raise FileNotFoundError(path)
    bounds = f"([{AOI[0]},{AOI[2]}],[{AOI[1]},{AOI[3]}])"
    mvs_tif = prep / "dsm_mvs_05m.tif"
    als_tif = prep / "dsm_existing_als_synthetic_05m.tif"
    if not mvs_tif.is_file():
        write_pipeline(
            prep / "dsm_mvs_pipeline.json",
            [
                {"type": "readers.ply", "filename": str(mvs_path)},
                {"type": "filters.transformation", "matrix": f"1 0 0 {WORLD_SHIFT[0]} 0 1 0 {WORLD_SHIFT[1]} 0 0 1 {WORLD_SHIFT[2]} 0 0 0 1"},
                {"type": "filters.crop", "bounds": bounds},
                {"type": "writers.gdal", "filename": str(mvs_tif), "resolution": 0.5, "output_type": "max", "data_type": "float32", "nodata": -9999},
            ],
        )
    if not als_tif.is_file():
        stages: list[dict] = [
                {"type": "readers.ply", "filename": str(synthetic_als)},
                {"type": "filters.transformation", "matrix": f"1 0 0 {WORLD_SHIFT[0]} 0 1 0 {WORLD_SHIFT[1]} 0 0 1 {WORLD_SHIFT[2]} 0 0 0 1"},
                {"type": "filters.crop", "bounds": bounds},
                {"type": "writers.gdal", "filename": str(als_tif), "resolution": 0.5, "output_type": "max", "data_type": "float32", "nodata": -9999},
        ]
        write_pipeline(prep / "dsm_als_pipeline.json", stages)
    mvs_aligned = prep / "dsm_mvs_05m_aligned.tif"
    als_aligned = prep / "dsm_existing_als_synthetic_05m_aligned.tif"
    align_grid(mvs_tif, mvs_aligned)
    align_grid(als_tif, als_aligned)
    mvs_xyz = load_xyz(mvs_aligned, prep / "dsm_mvs_05m.xyz")
    als_xyz = load_xyz(als_aligned, prep / "dsm_existing_als_synthetic_05m.xyz")
    if mvs_xyz.shape != als_xyz.shape or not np.allclose(mvs_xyz[:, :2], als_xyz[:, :2]):
        raise RuntimeError("DSM grids do not match")
    delta = mvs_xyz[:, 2] - als_xyz[:, 2]
    finite = np.isfinite(delta) & (mvs_xyz[:, 2] > -9000) & (als_xyz[:, 2] > -9000)
    footprint_data = json.loads(footprint_path.read_text(encoding="utf-8"))
    rows = []
    geometries = []
    for feature in footprint_data["features"]:
        geom = shape(feature["geometry"])
        stable_id = str(feature["properties"]["stable_id"])
        rows.append((stable_id, geom))
        geometries.append(geom)
    footprint_union = unary_union(geometries)
    outside = finite & ~contains_xy(footprint_union, mvs_xyz[:, 0], mvs_xyz[:, 1])
    ground_delta = delta[outside]
    if ground_delta.size < 100:
        raise RuntimeError("insufficient unchanged-ground DSM samples")
    median = float(np.median(ground_delta))
    mad = float(np.median(np.abs(ground_delta - median)))
    sigma0 = 1.4826 * mad
    if not math.isfinite(sigma0) or sigma0 <= 0:
        raise RuntimeError(f"invalid sigma0: {sigma0}")
    tau = 3.0 * sigma0
    beta = 0.5 * sigma0
    buildings = {}
    for stable_id, geom in rows:
        inside = finite & contains_xy(geom, mvs_xyz[:, 0], mvs_xyz[:, 1])
        score = float(np.median(np.abs(delta[inside]))) if inside.any() else None
        weight = (
            1.0 / (1.0 + math.exp(max(-60.0, min(60.0, (score - tau) / beta))))
            if score is not None
            else 1.0
        )
        buildings[stable_id] = {
            "sample_count": int(inside.sum()),
            "s_b_m": score,
            "w_b": weight,
            "support_status": "MEASURED" if score is not None else "NO_OVERLAP_FALLBACK_W1",
        }
    output = {
        "schema": "jointbuildgs.p2.e1_e6.w_b.v1",
        "method": "DSM_0.5M_MEDIAN_ABS_DELTA_LOGISTIC",
        "crs": "EPSG:25832",
        "sigma0_m": sigma0,
        "ground_median_delta_m": median,
        "ground_sample_count": int(outside.sum()),
        "tau_m": tau,
        "beta_m": beta,
        "outside_footprint_weight": 1.0,
        "no_overlap_building_weight": 1.0,
        "buildings": buildings,
        "scientific_verdict": None,
    }
    (prep / "w_b.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
