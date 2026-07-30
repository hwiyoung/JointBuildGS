#!/usr/bin/env python3
"""T12 integrated Figure 1.1 failure story.

Run from phases/p0-audit/. Host mode re-runs this script inside the P0 tools
container so LAZ/GIS/image processing stays in the recorded audit toolchain.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from p0_paths import P0_EVIDENCE, P0_EVIDENCE_ROOT, P0_G1_PACKAGE


TASK_ID = "T12"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"
FAILURE_ID = "DEBY_LOD2_4907182"
SURVIVOR_ID = "DEBY_LOD2_4908023"
FOOTPRINT_GPKG = "data/work/footprints/lod2_ground_plan.gpkg"
FOOTPRINT_LAYER = "lod2_ground_plan"
IMAGE_DIR = "data/work/images/Images"
PACKAGE_FIGURE_1_1 = "fig_02_figure_1_1a_dim_unrecovered_4907182.png"
PACKAGE_FIGURE_1_1_PATH = f"figs/{PACKAGE_FIGURE_1_1}"


@dataclass
class StoryCase:
    label: str
    building_id: str
    cohort: str
    crop_metric: Any
    patch: Any
    dim_surface: Any
    als_surface: Any
    dim_points: tuple[np.ndarray, np.ndarray, np.ndarray]
    als_points: tuple[np.ndarray, np.ndarray, np.ndarray]


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t12_figure_failure_story_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    write_host_config(run_dir, run_id, git_commit)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    try:
        run(
            compose
            + [
                "run",
                "-T",
                "--rm",
                "-e",
                "P0_INSIDE_CONTAINER=1",
                "-e",
                f"RUN_ID={run_id}",
                "-e",
                f"P0_GIT_COMMIT={git_commit}",
                "tools",
                "python",
                "/workspace/scripts/12_figure_failure_story.py",
                "--mode",
                "compute",
            ],
            cwd=repo,
            env=env,
            log_path=logs_dir / "compute.log",
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("figure=docs/figs/w3_t12_figure_1_1_failure_story.png")


def compute_entrypoint() -> None:
    root = Path("/workspace")
    docs = P0_EVIDENCE
    data = root / "data"
    figs = docs.figs("W3")
    package = P0_G1_PACKAGE
    package_figs = package / "figs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    scratch_dir = run_dir / "scratch"
    run_dir.mkdir(parents=True, exist_ok=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    t7 = load_helper_module("t7_failure_diagnosis", root / "scripts/07_failure_diagnosis.py")
    t9 = load_helper_module("t9_failure_surface_cause", root / "scripts/09_failure_surface_cause.py")
    t11 = load_helper_module("t11_survivor_texture_refine", root / "scripts/11_survivor_texture_refine.py")

    t9.assert_gpkg_epsg25832(root / FOOTPRINT_GPKG, FOOTPRINT_LAYER)
    footprint_geojson = scratch_dir / "lod2_ground_plan.geojson"
    t9.convert_gpkg_to_geojson(root / FOOTPRINT_GPKG, footprint_geojson, FOOTPRINT_LAYER)
    footprints = t7.load_footprints(footprint_geojson, {FAILURE_ID, SURVIVOR_ID})
    t7.assert_epsg25832_footprints(footprints)

    dim_path = data / "work/w2/dim_v1_classified_z_minus0p174.laz"
    if not dim_path.exists():
        dim_path = data / "work/classify/dim_v1_classified_z.laz"
    bbox = t7.combined_bbox([footprints[FAILURE_ID], footprints[SURVIVOR_ID]], buffer_m=12.0)
    dim_cloud = t7.read_cloud("DIM", [dim_path], bbox)
    als_cloud = t7.read_cloud("ALS", sorted((data / "raw/als").glob("*.laz")), bbox)
    t7.assert_epsg25832_cloud("DIM", dim_cloud)
    t7.assert_epsg25832_cloud("ALS", als_cloud)

    surface_by_id = {
        bid: {"DIM": t7.surface_metrics(dim_cloud, footprints[bid]), "ALS": t7.surface_metrics(als_cloud, footprints[bid])}
        for bid in (FAILURE_ID, SURVIVOR_ID)
    }

    camera_model = t7.parse_camera_model(data / "work/colmap/sparse/0/cameras.txt")
    scene_ref = read_json(data / "work/opf/opf/scene_reference_frame.json")
    cameras = t7.parse_colmap_cameras(data / "work/colmap/sparse/0/images.txt", scene_ref)
    t7.assert_epsg25832_camera_range(cameras)
    image_dir = root / IMAGE_DIR
    t11.assert_image_inputs(image_dir, cameras)

    low_gradient_threshold = t11.read_t9_low_gradient_threshold(docs / "W3_failure_surface_cause_thresholds.csv")
    candidates = t9.build_view_candidates(
        [FAILURE_ID],
        [SURVIVOR_ID],
        footprints,
        {bid: surface_by_id[bid]["DIM"] for bid in (FAILURE_ID, SURVIVOR_ID)},
        cameras,
        camera_model,
        scene_ref,
    )
    selected = t11.select_near_nadir_candidates(candidates)
    crop_metrics = t11.measure_sharp_crop_metrics(image_dir, selected, low_gradient_threshold)
    failure_metric = select_texture_metric(crop_metrics, FAILURE_ID, prefer="low")
    survivor_metric = select_texture_metric(crop_metrics, SURVIVOR_ID, prefer="high")

    cases = [
        build_case(t7, t11, image_dir, low_gradient_threshold, "Textureless DIM failure", FAILURE_ID, "failure_8", failure_metric, surface_by_id, dim_cloud, als_cloud, footprints),
        build_case(t7, t11, image_dir, low_gradient_threshold, "Textured survivor", SURVIVOR_ID, "control_success_71", survivor_metric, surface_by_id, dim_cloud, als_cloud, footprints),
    ]

    figure_path = figs / "w3_t12_figure_1_1_failure_story.png"
    metadata_path = docs / "W3_figure_failure_story_metadata.json"
    render_failure_story_figure(figure_path, image_dir, cases, footprints)
    write_metadata(metadata_path, run_id, low_gradient_threshold, cases, figure_path)
    add_to_g1_package(package, package_figs, figure_path, metadata_path)
    copy_outputs(
        run_dir,
        [
            figure_path,
            metadata_path,
            package_figs / PACKAGE_FIGURE_1_1,
            package / "t12_figure_failure_story_metadata.json",
            package / "captions.md",
            package / "manifest.json",
        ],
    )

    failure = cases[0]
    print(f"failure_id={FAILURE_ID}")
    print(f"survivor_id={SURVIVOR_ID}")
    print(f"failure_low_texture_pixel_ratio={failure.patch.low_texture_pixel_ratio:.4f}")
    print(f"failure_dim_density={failure.dim_surface.density_pts_m2:.3f}")
    print(f"failure_als_density={failure.als_surface.density_pts_m2:.3f}")
    print(f"figure={figure_path.relative_to(root)}")


def select_texture_metric(metrics: list[Any], building_id: str, prefer: str) -> Any:
    items = [item for item in metrics if item.building_id == building_id]
    if not items:
        raise RuntimeError(f"No near-nadir crop metrics for {building_id}")
    if prefer == "low":
        return max(items, key=lambda item: (item.low_texture_pixel_ratio, -item.gradient_p10, item.mask_pixel_count))
    return max(items, key=lambda item: (item.gradient_p10, item.gradient_median, -item.low_texture_pixel_ratio, item.mask_pixel_count))


def build_case(
    t7: Any,
    t11: Any,
    image_dir: Path,
    low_gradient_threshold: float,
    label: str,
    building_id: str,
    cohort: str,
    metric: Any,
    surface_by_id: dict[str, dict[str, Any]],
    dim_cloud: Any,
    als_cloud: Any,
    footprints: dict[str, Any],
) -> StoryCase:
    prefer = "low" if building_id == FAILURE_ID else "high"
    patch = t11.extract_roof_patch(cohort, image_dir / metric.image_name, metric, low_gradient_threshold, prefer=prefer)
    footprint = footprints[building_id]
    return StoryCase(
        label=label,
        building_id=building_id,
        cohort=cohort,
        crop_metric=metric,
        patch=patch,
        dim_surface=surface_by_id[building_id]["DIM"],
        als_surface=surface_by_id[building_id]["ALS"],
        dim_points=t7.clip_building_points(dim_cloud, footprint),
        als_points=t7.clip_building_points(als_cloud, footprint),
    )


def render_failure_story_figure(
    out_path: Path,
    image_dir: Path,
    cases: list[StoryCase],
    footprints: dict[str, Any],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 4, figsize=(16.2, 8.2), constrained_layout=True)
    col_titles = [
        "1. near-nadir image + footprint",
        "2. roof interior texture",
        "3. DIM class-6 clip",
        "4. ALS class-6 clip",
    ]
    for col_idx, title in enumerate(col_titles):
        axes[0, col_idx].set_title(title, fontsize=11, pad=10)

    for row_idx, case in enumerate(cases):
        footprint = footprints[case.building_id]
        render_overview_panel(axes[row_idx, 0], image_dir / case.crop_metric.image_name, case.crop_metric, case)
        render_patch_panel(axes[row_idx, 1], case)
        render_point_panel(axes[row_idx, 2], footprint, case.dim_points, case.dim_surface, "DIM", "#d62728")
        render_point_panel(axes[row_idx, 3], footprint, case.als_points, case.als_surface, "ALS", "#1f77b4")

    fig.suptitle("Figure 1.1: why image-derived DIM fails while LiDAR remains reconstructable", fontsize=15)
    fig.savefig(out_path, dpi=240)
    plt.close(fig)


def render_overview_panel(ax: Any, image_path: Path, metric: Any, case: StoryCase) -> None:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        min_u, min_v, max_u, max_v = expanded_bbox(metric.bbox, width, height, scale=2.8, min_size=420)
        crop = np.asarray(rgb.crop((min_u, min_v, max_u, max_v)))
    polygon = metric.polygon_in_crop + np.array([metric.bbox[0] - min_u, metric.bbox[1] - min_v], dtype=np.float64)
    closed = np.vstack([polygon, polygon[0]])
    ax.imshow(crop)
    ax.plot(closed[:, 0], closed[:, 1], color="#ffea00", linewidth=2.0)
    ax.fill(closed[:, 0], closed[:, 1], color="#ffea00", alpha=0.12)
    ax.text(
        0.02,
        0.95,
        f"{case.label}: {case.building_id.replace('DEBY_LOD2_', '')}",
        transform=ax.transAxes,
        fontsize=10.5,
        fontweight="bold",
        va="top",
        color="white",
        bbox={"facecolor": "black", "alpha": 0.58, "pad": 3, "edgecolor": "none"},
    )
    ax.text(
        0.02,
        0.05,
        f"{metric.image_name}\ninc={metric.incidence_deg:.1f} deg",
        transform=ax.transAxes,
        fontsize=8,
        color="white",
        bbox={"facecolor": "black", "alpha": 0.55, "pad": 3, "edgecolor": "none"},
    )
    ax.set_axis_off()


def render_patch_panel(ax: Any, case: StoryCase) -> None:
    ax.imshow(case.patch.rgb)
    ax.text(
        0.02,
        0.05,
        (
            f"p10 grad={case.patch.gradient_p10:.4f}\n"
            f"low-grad pixels={case.patch.low_texture_pixel_ratio:.2f}\n"
            f"patch={case.patch.patch_size_px}px"
        ),
        transform=ax.transAxes,
        fontsize=8.5,
        color="white",
        bbox={"facecolor": "black", "alpha": 0.55, "pad": 3, "edgecolor": "none"},
    )
    ax.set_axis_off()


def render_point_panel(
    ax: Any,
    footprint: Any,
    points: tuple[np.ndarray, np.ndarray, np.ndarray],
    surface: Any,
    label: str,
    color: str,
) -> None:
    x, y, z = points
    if x.size:
        if x.size > 12000:
            rng = np.random.default_rng(20260615 + x.size)
            idx = rng.choice(x.size, size=12000, replace=False)
            x = x[idx]
            y = y[idx]
            z = z[idx]
        size = 10.0 if x.size < 400 else 2.2
        ax.scatter(x, y, s=size, c=z, cmap="viridis", alpha=0.78, linewidths=0)
    ring = footprint.ring
    ax.plot(ring[:, 0], ring[:, 1], color="#111111", linewidth=1.1)
    min_x, min_y, max_x, max_y = footprint.bbox
    pad = max(max_x - min_x, max_y - min_y) * 0.18 + 1.0
    ax.set_xlim(min_x - pad, max_x + pad)
    ax.set_ylim(min_y - pad, max_y + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    ax.text(
        0.02,
        0.04,
        (
            f"{label}: n={surface.point_count:,}\n"
            f"density={surface.density_pts_m2:.1f} pts/m2\n"
            f"holes={surface.hole_ratio:.2f}"
        ),
        transform=ax.transAxes,
        fontsize=8.5,
        bbox={"facecolor": "white", "alpha": 0.82, "pad": 3, "edgecolor": "#cccccc"},
    )


def expanded_bbox(
    bbox: tuple[int, int, int, int],
    width: int,
    height: int,
    scale: float,
    min_size: int,
) -> tuple[int, int, int, int]:
    min_u, min_v, max_u, max_v = bbox
    cx = (min_u + max_u) / 2.0
    cy = (min_v + max_v) / 2.0
    side = max((max_u - min_u) * scale, (max_v - min_v) * scale, float(min_size))
    x0 = max(0, int(math.floor(cx - side / 2.0)))
    y0 = max(0, int(math.floor(cy - side / 2.0)))
    x1 = min(width, int(math.ceil(cx + side / 2.0)))
    y1 = min(height, int(math.ceil(cy + side / 2.0)))
    return x0, y0, x1, y1


def write_metadata(
    path: Path,
    run_id: str,
    low_gradient_threshold: float,
    cases: list[StoryCase],
    figure_path: Path,
) -> None:
    payload = {
        "run_id": run_id,
        "task_id": TASK_ID,
        "canonical_run": CANONICAL_RUN,
        "figure": figure_path.as_posix().replace("/workspace/", ""),
        "crs": "EPSG:25832 numeric UTM32 for footprints, DIM/ALS LAZ, and camera centers after T2 OPF scene-reference transform",
        "local_gradient_low_threshold": low_gradient_threshold,
        "cases": [case_metadata(case) for case in cases],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def case_metadata(case: StoryCase) -> dict[str, Any]:
    return {
        "label": case.label,
        "building_id": case.building_id,
        "cohort": case.cohort,
        "image_name": case.crop_metric.image_name,
        "incidence_deg": round(float(case.crop_metric.incidence_deg), 3),
        "texture_gradient_p10": round(float(case.patch.gradient_p10), 5),
        "low_texture_pixel_ratio": round(float(case.patch.low_texture_pixel_ratio), 4),
        "dim_point_count": int(case.dim_surface.point_count),
        "dim_density_pts_m2": round(float(case.dim_surface.density_pts_m2), 3),
        "dim_hole_ratio": round(float(case.dim_surface.hole_ratio), 3),
        "als_point_count": int(case.als_surface.point_count),
        "als_density_pts_m2": round(float(case.als_surface.density_pts_m2), 3),
        "als_hole_ratio": round(float(case.als_surface.hole_ratio), 3),
    }


def add_to_g1_package(package: Path, package_figs: Path, figure_path: Path, metadata_path: Path) -> None:
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)
    figure_dst = package_figs / PACKAGE_FIGURE_1_1
    metadata_dst = package / "t12_figure_failure_story_metadata.json"
    shutil.copy2(figure_path, figure_dst)
    shutil.copy2(metadata_path, metadata_dst)
    update_package_captions(package / "captions.md")

    manifest_path = package / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = {"package": "G1_package", "canonical_run": CANONICAL_RUN, "files": [], "figure_count": 0}
    files = set(manifest.get("files", []))
    files.add(PACKAGE_FIGURE_1_1_PATH)
    files.add("t12_figure_failure_story_metadata.json")
    files.add("captions.md")
    manifest["files"] = sorted(files)
    manifest["figure_count"] = sum(1 for item in manifest["files"] if item.startswith("figs/") and item.endswith(".png"))
    manifest["t12_failure_story"] = {
        "figure_1_1": PACKAGE_FIGURE_1_1_PATH,
        "metadata": "t12_figure_failure_story_metadata.json",
        "failure_id": FAILURE_ID,
        "survivor_id": SURVIVOR_ID,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_package_captions(path: Path) -> None:
    if not path.exists():
        return
    figure2 = (
        "| Figure 2 | figs/fig_02_figure_1_1a_dim_unrecovered_4907182.png | "
        "Figure 1.1 story: threshold-confirmed textureless failure DEBY_LOD2_4907182 and textured survivor DEBY_LOD2_4908023, showing near-nadir image footprint, roof texture, DIM clip, and ALS clip. |"
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("| Figure 2 |"):
            updated.append(figure2)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(figure2)
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def load_helper_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "phases/p0-audit/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Figure Failure Story\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(
        "\n".join(
            [
                f"task_id: {TASK_ID}",
                f"run_id: {run_id}",
                f"git_commit: {git_commit}",
                "canonical_run: " + CANONICAL_RUN,
                f"failure_id: {FAILURE_ID}",
                f"survivor_id: {SURVIVOR_ID}",
                "t11_inputs: docs/W3_survivor_texture_refine.md and docs/W3_survivor_texture_refine_thresholds.csv",
                "dim_pointcloud: data/work/w2/dim_v1_classified_z_minus0p174.laz",
                "als_pointclouds: data/raw/als/*.laz",
                "images: " + IMAGE_DIR,
                "footprints: " + FOOTPRINT_GPKG,
                "crs: EPSG:25832 numeric UTM32 coordinates",
                "classification_rule: figure synthesis only; no P0 judgement",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# T12 Figure Failure Story Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    version_cmds = [
        ["git", "status", "--short", "--branch"],
        compose + ["run", "-T", "--rm", "tools", "python", "--version"],
        compose
        + [
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import PIL, laspy, matplotlib, numpy; print('Pillow=' + PIL.__version__); print('laspy=' + laspy.__version__); print('matplotlib=' + matplotlib.__version__); print('numpy=' + numpy.__version__)",
        ],
        compose + ["run", "-T", "--rm", "tools", "ogrinfo", "--version"],
    ]
    for cmd in version_cmds:
        proc = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True, check=False)
        lines.append("$ " + " ".join(cmd))
        out = (proc.stdout or proc.stderr).strip()
        if out:
            lines.append(out)
        if proc.returncode != 0:
            lines.append(f"[exit {proc.returncode}]")
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "outputs"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            continue
        if path.is_relative_to(P0_EVIDENCE_ROOT):
            dst = snapshot / "evidence" / path.relative_to(P0_EVIDENCE_ROOT)
        elif path.is_relative_to(Path("/workspace/data")):
            dst = snapshot / "data" / path.relative_to(Path("/workspace/data"))
        else:
            dst = snapshot / path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def main() -> None:
    if os.environ.get("P0_INSIDE_CONTAINER") == "1":
        compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()
