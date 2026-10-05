"""Write bounded synthetic ray-update fixtures; run inside the project Docker.

python scripts/phd/wu_vallet_p3_v1/run_ray_fixture.py --config \
  configs/phd/wu_vallet_p3_v1/ray_fixture_v1.json

Output ownership is exclusive: an existing output directory is never overwritten.
This driver does not read real P3, ALS, images, UAS references, or GS artifacts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.phd.wu_vallet_p3_v1.ray_update import (  # noqa: E402
    LABELS, RayUpdateConfig, SensorMesh, classify_and_update,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_mesh(surfaces: list[dict], config: dict) -> SensorMesh:
    vertices, faces, origins = [], [], []
    size = float(config["square_size_m"])
    for i, surface in enumerate(surfaces):
        x, y, z = (float(surface[key]) for key in ("x", "y", "z"))
        points = np.array([[x, y, z], [x + size, y, z], [x + size, y + size, z], [x, y + size, z]])
        centers = points.copy()
        centers[:, 2] = float(config["optical_origin_height_m"])
        vertices.append(points)
        origins.append(centers)
        faces.append(np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64) + i * 4)
    return SensorMesh(np.concatenate(vertices) if vertices else np.empty((0, 3)),
                      np.concatenate(faces) if faces else np.empty((0, 3), dtype=np.int64),
                      np.concatenate(origins) if origins else np.empty((0, 3)))


def write_ply(path: Path, points: np.ndarray, sources: np.ndarray, native_rows: np.ndarray) -> None:
    with path.open("w", encoding="ascii") as out:
        out.write("ply\nformat ascii 1.0\ncomment synthetic_local_cartesian_metres_not_P3\n")
        out.write(f"element vertex {len(points)}\nproperty double x\nproperty double y\nproperty double z\n")
        out.write("property uchar source_id\nproperty int native_row\nend_header\n")
        for point, source, row in zip(points, sources, native_rows):
            out.write(f"{point[0]:.12g} {point[1]:.12g} {point[2]:.12g} {int(source == 'new')} {int(row)}\n")


def plot_scenes(scenes: list[tuple], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    colors = {"consistent": "#28825b", "changed": "#c64444", "single": "#6a737d"}
    source_colors = {"old": "#2377bb", "new": "#d9801f"}
    fig, axes = plt.subplots(len(scenes), 3, figsize=(13, 2.4 * len(scenes)), squeeze=False)
    for row, (scene_id, old, new, result) in enumerate(scenes):
        bounds = np.concatenate((old.vertices, new.vertices))
        xlim = (bounds[:, 0].min() - 0.4, bounds[:, 0].max() + 0.4)
        zlim = (bounds[:, 2].min() - 0.35, bounds[:, 2].max() + 0.35)
        for column, (side, mesh) in enumerate((("old", old), ("new", new))):
            ax = axes[row, column]
            for face, label in zip(mesh.triangles, result[f"{side}_face_labels"]):
                p = mesh.vertices[face]
                closed = np.concatenate((p, p[:1]))
                ax.plot(closed[:, 0], closed[:, 2], color=colors[str(label)], lw=3, alpha=0.65)
            ax.scatter(mesh.vertices[:, 0], mesh.vertices[:, 2], c=[colors[str(x)] for x in result[f"{side}_vertex_labels"]], s=24, zorder=3)
            ax.set_title(f"{scene_id}: {side} labels", fontsize=10)
        ax = axes[row, 2]
        for source, color in source_colors.items():
            points = result["updated_points"][result["updated_source"] == source]
            ax.scatter(points[:, 0], points[:, 2], color=color, s=30, label=source)
        ax.set_title(f"updated point cloud ({len(result['updated_points'])} points)", fontsize=10)
        for ax in axes[row]:
            ax.set(xlim=xlim, ylim=zlim, xlabel="synthetic X (m)", ylabel="Z (m)")
            ax.grid(alpha=0.18)
    handles = [Line2D([0], [0], color=colors[label], lw=3, label=label) for label in LABELS]
    handles += [Line2D([0], [0], color=color, marker="o", linestyle="", label=f"output: {source}") for source, color in source_colors.items()]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False)
    fig.suptitle("Wu–Vallet 2026 paper-based sampled-ray component — synthetic fixtures, no GS", fontsize=13)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    fig.savefig(output, dpi=150)
    plt.close(fig)


def run(config_path: Path, output_override: Path | None = None) -> dict:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run this project driver inside Docker")
    config = json.loads(config_path.read_text())
    if config.get("scientific_verdict") is not None:
        raise ValueError("scientific_verdict must remain null")
    scene_ids = [scene["id"] for scene in config["scenes"]]
    if len(set(scene_ids)) != len(scene_ids) or any(Path(x).name != x for x in scene_ids):
        raise ValueError("scene IDs must be unique simple directory names")
    output = output_override or Path(config["output_root"])
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    receipt = {
        "task_id": config["task_id"], "status": "RUNNING", "scientific_verdict": None,
        "scope": config["scope"], "coordinate_frame": config["coordinate_frame"],
        "crs": config["crs"], "units": config["units"], "real_P3_executed": False,
        "native_Wu_Vallet_reproduction": False, "GS_executed": False,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path.resolve()), "config_sha256": sha256(config_path),
        "git_commit": os.environ.get("JBGS_SOURCE_GIT_HEAD") or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "docker_image_id": os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
        "source_snapshot_manifest": os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in (
            Path(__file__), ROOT / "src/phd/wu_vallet_p3_v1/ray_update.py")},
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "scenes": [],
    }
    try:
        (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        all_scenes = []
        algorithm = RayUpdateConfig(**config["algorithm"])
        for scene in config["scenes"]:
            scene_root = output / scene["id"]
            scene_root.mkdir()
            old, new = make_mesh(scene["old_surfaces"], config), make_mesh(scene["new_surfaces"], config)
            result = classify_and_update(old, new, algorithm)
            arrays = {key: value for key, value in result.items() if isinstance(value, np.ndarray)}
            for side, mesh in (("old", old), ("new", new)):
                arrays.update({f"{side}_{name}": getattr(mesh, name) for name in ("vertices", "triangles", "optical_origins", "native_rows")})
            np.savez_compressed(scene_root / "geometry_and_labels.npz", **arrays)
            write_ply(scene_root / "updated_points.ply", result["updated_points"], result["updated_source"], result["updated_native_rows"])
            checks = {key: {"expected": value, "actual": result["diagnostics"][key],
                            "pass": result["diagnostics"][key] == value}
                      for key, value in scene["expected"].items()}
            metadata = {"scene_id": scene["id"], "status": "PASS" if all(x["pass"] for x in checks.values()) else "FAIL",
                        "expected_accounting_checks": checks, "diagnostics": result["diagnostics"],
                        "reproduction_scope": result["reproduction_scope"], "conflict_pair_columns": result["conflict_pair_columns"]}
            (scene_root / "result.json").write_text(json.dumps(metadata, indent=2) + "\n")
            receipt["scenes"].append(metadata)
            all_scenes.append((scene["id"], old, new, result))
        plot_scenes(all_scenes, output / "source_and_section_fixtures.png")
        receipt["status"] = "PASS" if all(scene["status"] == "PASS" for scene in receipt["scenes"]) else "FAIL"
        receipt["outputs"] = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size,
                               "sha256": sha256(path)} for path in sorted(output.rglob("*")) if path.is_file()]
        receipt["elapsed_seconds"] = time.monotonic() - started
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps({"status": receipt["status"], "output": str(output), "scenes": len(all_scenes),
                          "scientific_verdict": None}, indent=2), flush=True)
        return receipt
    except Exception as error:
        receipt.update({"status": "FAIL", "error": str(error), "traceback": traceback.format_exc(),
                        "elapsed_seconds": time.monotonic() - started})
        (output / "failure_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.config, args.output)
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
