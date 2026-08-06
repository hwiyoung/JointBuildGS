from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


WORLD_SHIFT = [690953.0, 5336071.0, 604.0]
AOI = [690791.74, 5335864.05, 691154.65, 5336353.85]
# Exact 1400 px training images imply a 0.1333 m effective ground sampling
# interval over the frozen scene support; the full-resolution source GSD is not
# used by this downscaled training chain.
EFFECTIVE_TRAINING_GSD_M = 0.40 / 3.0
VOXEL_M = EFFECTIVE_TRAINING_GSD_M * 3.0


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def ply_vertex_count(path: Path) -> int:
    with path.open("rb") as stream:
        for line in stream:
            if line.startswith(b"element vertex "):
                return int(line.split()[2])
            if line.strip() == b"end_header":
                break
    raise RuntimeError(f"PLY vertex count missing: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--prep-root", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    prep = args.prep_root.resolve()
    prep.mkdir(parents=True, exist_ok=True)
    source = artifacts / (
        "phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/"
        "P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply"
    )
    output = prep / "seed_dense.ply"
    receipt_path = prep / "seed_dense.receipt.json"
    if output.is_file() and receipt_path.is_file():
        return 0
    local = [
        AOI[0] - WORLD_SHIFT[0],
        AOI[1] - WORLD_SHIFT[1],
        AOI[2] - WORLD_SHIFT[0],
        AOI[3] - WORLD_SHIFT[1],
    ]
    pipeline = {
        "pipeline": [
            {"type": "readers.ply", "filename": str(source)},
            {
                "type": "filters.crop",
                "bounds": f"([{local[0]},{local[2]}],[{local[1]},{local[3]}])",
            },
            {"type": "filters.outlier", "method": "statistical", "mean_k": 16, "multiplier": 2.0},
            {"type": "filters.expression", "expression": "Classification != 7"},
            {"type": "filters.voxelcenternearestneighbor", "cell": VOXEL_M},
            {
                "type": "writers.ply",
                "filename": str(output),
                "dims": "X,Y,Z,Red,Green,Blue",
                "storage_mode": "little endian",
            },
        ]
    }
    pipeline_path = prep / "seed_dense_pipeline.json"
    pipeline_path.write_text(json.dumps(pipeline, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["pdal", "pipeline", str(pipeline_path)], check=True)
    count = ply_vertex_count(output)
    if not 1_000_000 <= count <= 3_000_000:
        raise RuntimeError(f"dense seed target count violated: {count}")
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.seed_dense.v1",
        "source": {"path": str(source), "sha256": sha256(source), "point_count": 43_926_567},
        "operations": ["AOI_CROP", "STATISTICAL_OUTLIER_MEAN16_MULTIPLIER2", "VOXEL_CENTER_NEAREST"],
        "effective_training_gsd_m": EFFECTIVE_TRAINING_GSD_M,
        "voxel_rule": "GSD_X_3",
        "voxel_size_m": VOXEL_M,
        "output": {"path": str(output), "sha256": sha256(output), "point_count": count},
        "scientific_verdict": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
