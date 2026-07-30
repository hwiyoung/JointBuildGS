#!/usr/bin/env python3
"""P1W-READOUT: classify one fused expanded-pilot scene for canonical Roofer.

The input is the geometry-only scene NPZ emitted by
``e5_c001_readout_extract_ablation.py --no-sem``.  This adapter deliberately
reuses the historical P0 classification recipe used before this pilot:

1. PDAL SMRF assigns ground class 2;
2. the approved LoD2 ``GroundSurface`` XY roofprints overlay non-ground points
   as building class 6;
3. the output LAS is EPSG:25832 and is consumed by one canonical Roofer call.

No reference height, RoofSurface geometry, or semantic label is opened here.
The 30-feature roofprint file must first be materialized by
``pilot_1wave_scoring.py prepare-roofprints``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import laspy
import numpy as np
from pyproj import CRS as PyprojCRS

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pilot_1wave_readout_lineage import (
    validate_roofprint_file,
    validate_scene_npz_binding,
)


SCHEMA = "jointbuildgs.pilot_1wave.scene_classification.v1"
CRS = "EPSG:25832"
EXPECTED_FOOTPRINTS = 30
GROUND = 2
BUILDING = 6
UNCLASSIFIED = 1
SMRF = {
    "cell": 1.0,
    "slope": 0.15,
    "scalar": 1.25,
    "threshold": 0.5,
    "window": 18.0,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def validate_roofprints(
    path: Path, *, expected_building_ids: list[str] | tuple[str, ...] | None = None
) -> dict[str, Any]:
    return validate_roofprint_file(
        path,
        expected_building_ids=expected_building_ids,
        expected_count=EXPECTED_FOOTPRINTS,
    )


def load_scene_points(path: Path) -> tuple[np.ndarray, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=False) as payload:
        if "P_utm_clean" in payload:
            key = "P_utm_clean"
        elif "P_utm" in payload:
            key = "P_utm"
        else:
            raise RuntimeError("scene NPZ has neither P_utm_clean nor P_utm")
        points = np.asarray(payload[key], dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise RuntimeError(f"scene point shape must be Nx3, got {points.shape}")
    if len(points) == 0:
        raise RuntimeError("scene point cloud is empty")
    if not np.isfinite(points).all():
        raise RuntimeError("scene point cloud contains non-finite coordinates")
    return points, key


def load_scene_binding(path: Path) -> dict[str, Any]:
    """Re-open lineage and duplicated crop scalars from one scene NPZ."""

    return validate_scene_npz_binding(path, allow_unverified_legacy=True)


def load_scene_lineage(path: Path) -> dict[str, Any]:
    """Backward-compatible lineage-only view of :func:`load_scene_binding`."""

    return load_scene_binding(path)["readout_lineage"]


def write_raw_las(path: Path, points: np.ndarray) -> None:
    if path.exists():
        raise RuntimeError(f"raw LAS already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    header = laspy.LasHeader(point_format=6, version="1.4")
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = np.floor(points.min(axis=0))
    header.add_crs(PyprojCRS.from_epsg(25832))
    las = laspy.LasData(header)
    las.x = points[:, 0]
    las.y = points[:, 1]
    las.z = points[:, 2]
    las.classification = np.full(len(points), UNCLASSIFIED, dtype=np.uint8)
    las.write(path)


def pdal_pipeline(raw_las: Path, roofprints: Path, output_las: Path) -> dict[str, Any]:
    return {
        "pipeline": [
            {"type": "readers.las", "filename": str(raw_las.resolve())},
            {
                "type": "filters.smrf",
                **SMRF,
                "ground_class": GROUND,
                "other_class": UNCLASSIFIED,
            },
            {
                "type": "filters.overlay",
                "dimension": "Classification",
                "datasource": str(roofprints.resolve()),
                "column": "class",
                "where": f"Classification != {GROUND}",
            },
            {
                "type": "writers.las",
                "filename": str(output_las.resolve()),
                "a_srs": CRS,
                "minor_version": 4,
                "dataformat_id": 6,
            },
        ]
    }


def class_counts(path: Path) -> tuple[dict[str, int], int, int | None]:
    counts: dict[str, int] = {}
    with laspy.open(path) as reader:
        point_count = int(reader.header.point_count)
        crs = reader.header.parse_crs()
        epsg = crs.to_epsg() if crs is not None else None
        for chunk in reader.chunk_iterator(1_000_000):
            values, numbers = np.unique(
                np.asarray(chunk.classification), return_counts=True
            )
            for value, number in zip(values, numbers):
                key = str(int(value))
                counts[key] = counts.get(key, 0) + int(number)
    return counts, point_count, epsg


def pdal_version() -> str:
    return subprocess.check_output(
        ["pdal", "--version"], text=True, stderr=subprocess.STDOUT
    ).strip()


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_las = args.output.resolve()
    receipt = args.receipt.resolve()
    pipeline_path = args.pipeline.resolve()
    raw_las = args.raw_las.resolve()
    for path in (output_las, receipt, pipeline_path, raw_las):
        if path.exists():
            raise RuntimeError(f"refusing to overwrite readout artifact: {path}")

    scene_npz = args.scene_npz.resolve()
    points, source_key = load_scene_points(scene_npz)
    scene_binding = load_scene_binding(scene_npz)
    readout_lineage = scene_binding["readout_lineage"]
    crop_contract = scene_binding["crop_contract"]
    expected_ids = (
        crop_contract["ordered_building_ids"] if crop_contract is not None else None
    )
    roofprint_record = validate_roofprints(
        args.roofprints.resolve(), expected_building_ids=expected_ids
    )
    write_raw_las(raw_las, points)
    pipeline = pdal_pipeline(raw_las, args.roofprints.resolve(), output_las)
    atomic_json(pipeline_path, pipeline)
    process = subprocess.run(
        ["pdal", "pipeline", str(pipeline_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path = receipt.with_suffix(".log")
    log_path.write_text(
        f"+ pdal pipeline {pipeline_path}\n{process.stdout or ''}", encoding="utf-8"
    )
    if process.returncode != 0 or not output_las.is_file():
        raise RuntimeError(
            f"PDAL classification failed exit={process.returncode}; see {log_path}"
        )
    counts, output_count, epsg = class_counts(output_las)
    if output_count != len(points):
        raise RuntimeError(f"point count changed: {output_count} != {len(points)}")
    if epsg != 25832:
        raise RuntimeError(f"classified LAS EPSG drift: {epsg}")
    missing = [value for value in (GROUND, BUILDING) if counts.get(str(value), 0) == 0]
    if missing:
        raise RuntimeError(
            f"classified LAS lacks Roofer-required classes {missing}; counts={counts}"
        )
    bounds = {
        axis: [float(np.min(points[:, index])), float(np.max(points[:, index]))]
        for index, axis in enumerate(("x", "y", "z"))
    }
    if not all(math.isfinite(value) for pair in bounds.values() for value in pair):
        raise AssertionError("non-finite bounds escaped input validation")
    result = {
        "schema": SCHEMA,
        "created_utc": now(),
        "state": "complete",
        "crs": CRS,
        "historical_recipe_source": (
            "phases/p0-audit/scripts/04_classify.py and "
            "scripts/input_and_alignment/tum_transfer/_mob_prep_las.py"
        ),
        "source_scene_npz": {
            "path": str(scene_npz),
            "sha256": sha256_file(scene_npz),
            "array": source_key,
            "point_count": len(points),
            "bounds": bounds,
        },
        "readout_lineage": readout_lineage,
        "crop_contract": crop_contract,
        "roofprints": {
            **roofprint_record,
            "role": "approved historical LoD2 GroundSurface XY support only",
            "gt_height_or_roofsurface_opened": False,
        },
        "classification": {
            "method": "PDAL SMRF then footprint overlay on non-ground",
            "smrf": SMRF,
            "ground_class": GROUND,
            "building_class": BUILDING,
            "unclassified_class": UNCLASSIFIED,
            "pdal_version": pdal_version(),
            "pipeline_path": str(pipeline_path),
            "pipeline_sha256": sha256_file(pipeline_path),
        },
        "raw_las": {"path": str(raw_las), "sha256": sha256_file(raw_las)},
        "classified_las": {
            "path": str(output_las),
            "sha256": sha256_file(output_las),
            "point_count": output_count,
            "class_counts": counts,
            "epsg": epsg,
        },
        "learning_runs_started_by_this_adapter": 0,
        "reference_role": "none; classification precedes scoring",
    }
    atomic_json(receipt, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-npz", type=Path, required=True)
    parser.add_argument("--roofprints", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-las", type=Path, required=True)
    parser.add_argument("--pipeline", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    result = run(parse_args())
    print(json.dumps(result["classified_las"], ensure_ascii=False))


if __name__ == "__main__":
    main()
