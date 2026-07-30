#!/usr/bin/env python3
"""Convert the TUM2TWIN OPF bundle to COLMAP text format and validate poses.

Run this script from phases/p0-audit/. The host-side entrypoint immediately re-runs
itself inside the P0 tools container so the actual processing is Docker-based.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from p0_paths import P0_EVIDENCE


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    subprocess.run(compose + ["build", "tools"], cwd=repo, env=env, check=True)

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo.parent,
        text=True,
    ).strip()

    subprocess.run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            "-e",
            "P0_INSIDE_CONTAINER=1",
            "-e",
            f"P0_GIT_COMMIT={git_commit}",
            "tools",
            "python",
            "/workspace/scripts/02_opf2colmap.py",
            *sys.argv[1:],
        ],
        cwd=repo,
        env=env,
        check=True,
    )


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ensure_opf_extracted(raw_zip: Path, work_dir: Path) -> Path:
    opf_root = work_dir / "opf"
    project = opf_root / "project.opf"
    sparse = opf_root / "sparse" / "pcl.gltf"
    if project.exists() and sparse.exists():
        return opf_root

    if opf_root.exists():
        shutil.rmtree(opf_root)

    work_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            "unzip",
            "-q",
            "-o",
            str(raw_zip),
            "-d",
            str(work_dir),
            "-x",
            "opf/features.bin",
            "opf/matches.bin",
            "opf/originalMatches.bin",
            "opf/images/*",
        ]
    )

    if not project.exists():
        raise FileNotFoundError(f"Missing OPF project after extraction: {project}")
    return opf_root


def convert_opf_to_colmap(opf_project: Path, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run(["opf2colmap", str(opf_project), "--out-dir", str(out_dir)])

    required = ["cameras.txt", "images.txt", "points3D.txt"]
    missing = [name for name in required if not (out_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"opf2colmap did not produce: {', '.join(missing)}")


def qvec_to_rotmat(qvec: np.ndarray) -> np.ndarray:
    q0, q1, q2, q3 = qvec
    return np.array(
        [
            [
                1 - 2 * q2 * q2 - 2 * q3 * q3,
                2 * q1 * q2 - 2 * q0 * q3,
                2 * q3 * q1 + 2 * q0 * q2,
            ],
            [
                2 * q1 * q2 + 2 * q0 * q3,
                1 - 2 * q1 * q1 - 2 * q3 * q3,
                2 * q2 * q3 - 2 * q0 * q1,
            ],
            [
                2 * q3 * q1 - 2 * q0 * q2,
                2 * q2 * q3 + 2 * q0 * q1,
                1 - 2 * q1 * q1 - 2 * q2 * q2,
            ],
        ],
        dtype=float,
    )


def count_colmap_cameras(cameras_txt: Path) -> int:
    count = 0
    with cameras_txt.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


def count_colmap_points(points_txt: Path) -> int:
    count = 0
    with points_txt.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


def parse_colmap_image_poses(images_txt: Path) -> tuple[list[str], np.ndarray]:
    names: list[str] = []
    centers: list[np.ndarray] = []

    data_lines: list[str] = []
    with images_txt.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                data_lines.append(stripped)

    if len(data_lines) % 2 != 0:
        raise ValueError(f"Unexpected COLMAP images.txt line count: {len(data_lines)}")

    for idx in range(0, len(data_lines), 2):
        parts = data_lines[idx].split()
        if len(parts) < 10:
            raise ValueError(f"Malformed COLMAP image line: {data_lines[idx]}")
        qvec = np.array([float(v) for v in parts[1:5]], dtype=float)
        tvec = np.array([float(v) for v in parts[5:8]], dtype=float)
        rot = qvec_to_rotmat(qvec)
        center = -rot.T @ tvec
        centers.append(center)
        names.append(" ".join(parts[9:]))

    return names, np.vstack(centers)


def read_scene_reference(opf_root: Path) -> dict:
    with (opf_root / "scene_reference_frame.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def projected_epsg_code(scene_ref: dict) -> str:
    definition = scene_ref.get("crs", {}).get("definition", "")
    matches = re.findall(r'ID\["EPSG",\s*(\d+)\]', definition)
    return matches[-1] if matches else "not found"


def looks_like_utm32(points: np.ndarray) -> bool:
    x_med = float(np.median(points[:, 0]))
    y_med = float(np.median(points[:, 1]))
    return 100000.0 <= x_med <= 900000.0 and 5_000_000.0 <= y_med <= 6_200_000.0


def canonical_to_base(points: np.ndarray, scene_ref: dict) -> np.ndarray:
    if looks_like_utm32(points):
        return points.copy()

    transform = scene_ref.get("base_to_canonical", {})
    scale = np.array(transform.get("scale", [1.0, 1.0, 1.0]), dtype=float)
    shift = np.array(transform.get("shift", [0.0, 0.0, 0.0]), dtype=float)
    converted = points / scale - shift
    if transform.get("swap_xy", False):
        converted[:, [0, 1]] = converted[:, [1, 0]]
    return converted


def parse_poslist(text: str) -> np.ndarray:
    values = [float(v) for v in text.split()]
    if len(values) % 3 == 0:
        arr = np.array(values, dtype=float).reshape((-1, 3))
        return arr[:, :2]
    if len(values) % 2 == 0:
        return np.array(values, dtype=float).reshape((-1, 2))
    raise ValueError("gml:posList has neither 2D nor 3D coordinate stride")


def parse_lod2_footprints(paths: list[Path]) -> tuple[list[np.ndarray], tuple[float, float, float, float]]:
    footprints: list[np.ndarray] = []
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf

    for path in paths:
        for _, elem in ET.iterparse(path, events=("end",)):
            if local_name(elem.tag) == "GroundSurface":
                poslist = None
                for child in elem.iter():
                    if local_name(child.tag) == "posList" and child.text:
                        poslist = child.text
                        break
                if poslist:
                    xy = parse_poslist(poslist)
                    footprints.append(xy)
                    min_x = min(min_x, float(np.min(xy[:, 0])))
                    min_y = min(min_y, float(np.min(xy[:, 1])))
                    max_x = max(max_x, float(np.max(xy[:, 0])))
                    max_y = max(max_y, float(np.max(xy[:, 1])))
                elem.clear()

    if not footprints:
        raise ValueError("No bldg:GroundSurface footprints found in LoD2 files")
    return footprints, (min_x, min_y, max_x, max_y)


def assert_epsg25832_range(
    positions: np.ndarray,
    lod2_bounds: tuple[float, float, float, float],
    margin_m: float = 500.0,
) -> None:
    x = positions[:, 0]
    y = positions[:, 1]
    z = positions[:, 2]

    if not np.all((100000.0 <= x) & (x <= 900000.0)):
        raise AssertionError("Camera easting values are outside UTM zone 32 numeric range")
    if not np.all((5_000_000.0 <= y) & (y <= 6_200_000.0)):
        raise AssertionError("Camera northing values are outside Germany UTM northing range")
    if not np.all((350.0 <= z) & (z <= 900.0)):
        raise AssertionError("Camera heights are outside the expected TUM campus range")

    min_x, min_y, max_x, max_y = lod2_bounds
    inside_lod2_envelope = (
        (min_x - margin_m <= x)
        & (x <= max_x + margin_m)
        & (min_y - margin_m <= y)
        & (y <= max_y + margin_m)
    )
    if not np.all(inside_lod2_envelope):
        outside = int(np.count_nonzero(~inside_lod2_envelope))
        raise AssertionError(
            f"{outside} camera positions fall outside LoD2 envelope plus {margin_m:.0f} m"
        )


def filter_footprints_for_view(
    footprints: list[np.ndarray],
    view_bounds: tuple[float, float, float, float],
) -> list[np.ndarray]:
    min_x, min_y, max_x, max_y = view_bounds
    selected = []
    for xy in footprints:
        if (
            float(np.max(xy[:, 0])) >= min_x
            and float(np.min(xy[:, 0])) <= max_x
            and float(np.max(xy[:, 1])) >= min_y
            and float(np.min(xy[:, 1])) <= max_y
        ):
            selected.append(xy)
    return selected


def write_overlay(
    footprints: list[np.ndarray],
    positions: np.ndarray,
    out_png: Path,
) -> tuple[int, tuple[float, float, float, float]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_png.parent.mkdir(parents=True, exist_ok=True)

    cam_min_x = float(np.min(positions[:, 0]))
    cam_min_y = float(np.min(positions[:, 1]))
    cam_max_x = float(np.max(positions[:, 0]))
    cam_max_y = float(np.max(positions[:, 1]))
    margin = 180.0
    view_bounds = (
        cam_min_x - margin,
        cam_min_y - margin,
        cam_max_x + margin,
        cam_max_y + margin,
    )
    selected = filter_footprints_for_view(footprints, view_bounds)

    fig, ax = plt.subplots(figsize=(10, 10))
    for xy in selected:
        ax.plot(xy[:, 0], xy[:, 1], color="#707070", linewidth=0.35, alpha=0.65)

    order = np.arange(len(positions))
    ax.plot(positions[:, 0], positions[:, 1], color="#2f6fbd", linewidth=0.5, alpha=0.35)
    sc = ax.scatter(
        positions[:, 0],
        positions[:, 1],
        c=order,
        s=5,
        cmap="viridis",
        linewidths=0,
        label="OPF camera centers",
    )
    fig.colorbar(sc, ax=ax, fraction=0.035, pad=0.02, label="image order")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(view_bounds[0], view_bounds[2])
    ax.set_ylim(view_bounds[1], view_bounds[3])
    ax.set_xlabel("Easting (EPSG:25832 numeric UTM32, metres)")
    ax.set_ylabel("Northing (EPSG:25832 numeric UTM32, metres)")
    ax.set_title("T2 OPF camera positions over LoD2 ground footprints")
    ax.legend(loc="upper right")
    ax.grid(True, linewidth=0.25, alpha=0.35)
    fig.tight_layout()
    fig.savefig(out_png, dpi=220)
    plt.close(fig)
    return len(selected), view_bounds


def write_summary(
    summary_path: Path,
    overlay_path: Path,
    colmap_dir: Path,
    run_dir: Path,
    camera_model_count: int,
    image_count: int,
    point_count: int,
    positions: np.ndarray,
    projected_epsg: str,
    lod2_bounds: tuple[float, float, float, float],
    total_footprints: int,
    plotted_footprints: int,
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    min_xyz = np.min(positions, axis=0)
    max_xyz = np.max(positions, axis=0)
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    rel_overlay = overlay_path.as_posix().replace("/workspace/", "")
    rel_colmap = colmap_dir.as_posix().replace("/workspace/", "")
    rel_run = run_dir.as_posix().replace("/workspace/", "")

    summary_path.write_text(
        "\n".join(
            [
                "# T2 OPF to COLMAP Summary",
                "",
                f"- Generated at: {generated}",
                f"- COLMAP output: `{rel_colmap}`",
                f"- Overlay PNG: `{rel_overlay}`",
                f"- Run directory: `{rel_run}`",
                f"- COLMAP camera model count: {camera_model_count}",
                f"- COLMAP image / pose count: {image_count}",
                f"- COLMAP sparse point count: {point_count}",
                f"- OPF projected CRS EPSG code in WKT: {projected_epsg}",
                "- EPSG:25832 numeric range assertion: PASS",
                (
                    "- Pose bounds after OPF scene-reference inverse shift: "
                    f"x=[{min_xyz[0]:.3f}, {max_xyz[0]:.3f}], "
                    f"y=[{min_xyz[1]:.3f}, {max_xyz[1]:.3f}], "
                    f"z=[{min_xyz[2]:.3f}, {max_xyz[2]:.3f}]"
                ),
                (
                    "- LoD2 footprint bounds: "
                    f"x=[{lod2_bounds[0]:.3f}, {lod2_bounds[2]:.3f}], "
                    f"y=[{lod2_bounds[1]:.3f}, {lod2_bounds[3]:.3f}]"
                ),
                f"- LoD2 ground footprints parsed: {total_footprints}",
                f"- LoD2 ground footprints plotted in overlay extent: {plotted_footprints}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_versions(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"generated_at={datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"git_commit={os.environ.get('P0_GIT_COMMIT', 'unknown')}",
    ]
    for cmd in (
        ["python", "--version"],
        ["opf2colmap", "--help"],
    ):
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        first_line = (proc.stdout or proc.stderr).splitlines()[0]
        lines.append(f"{' '.join(cmd)} => {first_line}")

    proc = subprocess.run(
        [
            "python",
            "-c",
            (
                "import importlib.metadata as metadata; "
                "import matplotlib, numpy; "
                "print('pyopf=' + metadata.version('pyopf')); "
                "print('matplotlib=' + matplotlib.__version__); "
                "print('numpy=' + numpy.__version__)"
            ),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    lines.extend(proc.stdout.strip().splitlines())
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path("/workspace")
    data = root / "data"
    docs = P0_EVIDENCE
    raw_zip = data / "raw/uav/opf.zip"
    work_opf = data / "work/opf"
    colmap_dir = data / "work/colmap/sparse/0"
    lod2_paths = sorted((data / "raw/lod2").glob("*.gml"))
    overlay_png = docs.figs("W1") / "t2_opf_pose_overlay.png"
    summary_md = docs / "opf2colmap_summary.md"
    run_id = datetime.now(timezone.utc).astimezone().strftime("t2_opf2colmap_%Y%m%d_%H%M%S")
    run_dir = root / "runs" / run_id

    if not raw_zip.exists():
        raise FileNotFoundError(raw_zip)
    if not lod2_paths:
        raise FileNotFoundError(data / "raw/lod2")

    write_versions(run_dir)
    opf_root = ensure_opf_extracted(raw_zip, work_opf)
    convert_opf_to_colmap(opf_root / "project.opf", colmap_dir)

    camera_model_count = count_colmap_cameras(colmap_dir / "cameras.txt")
    names, centers_local = parse_colmap_image_poses(colmap_dir / "images.txt")
    point_count = count_colmap_points(colmap_dir / "points3D.txt")
    scene_ref = read_scene_reference(opf_root)
    centers_utm32 = canonical_to_base(centers_local, scene_ref)
    footprints, lod2_bounds = parse_lod2_footprints(lod2_paths)
    assert_epsg25832_range(centers_utm32, lod2_bounds)
    plotted_count, _ = write_overlay(footprints, centers_utm32, overlay_png)

    write_summary(
        summary_path=summary_md,
        overlay_path=overlay_png,
        colmap_dir=colmap_dir,
        run_dir=run_dir,
        camera_model_count=camera_model_count,
        image_count=len(names),
        point_count=point_count,
        positions=centers_utm32,
        projected_epsg=projected_epsg_code(scene_ref),
        lod2_bounds=lod2_bounds,
        total_footprints=len(footprints),
        plotted_footprints=plotted_count,
    )

    print(f"COLMAP camera model count: {camera_model_count}")
    print(f"COLMAP image / pose count: {len(names)}")
    print(f"COLMAP sparse point count: {point_count}")
    print("EPSG:25832 numeric range assertion: PASS")
    print(f"Overlay PNG: {overlay_png.as_posix().replace('/workspace/', '')}")
    print(f"Summary: {summary_md.as_posix().replace('/workspace/', '')}")
    print(f"Run versions: {run_dir.as_posix().replace('/workspace/', '')}/versions.txt")


if __name__ == "__main__":
    if os.environ.get("P0_INSIDE_CONTAINER") != "1":
        host_entrypoint()
    else:
        main()
