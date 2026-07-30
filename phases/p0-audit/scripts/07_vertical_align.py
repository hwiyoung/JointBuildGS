#!/usr/bin/env python3
"""Align DIM vertical reference against ALS ground points.

Run from phases/p0-audit/. The host entrypoint re-runs this script inside the P0 tools
container so PROJ/laspy/matplotlib execution stays in the audit toolchain.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np


TASK_ID = "T7"
GROUND_CLASS = 2
CELL_SIZE_M = 2.0
SECTION_BAND_WIDTH_M = 8.0
SECTION_MAX_POINTS = 120_000
STD_THRESHOLD_M = 0.5
GCG2016_URL = "https://cdn.proj.org/de_bkg_gcg2016.tif"
BKG_PRODUCT_URL = "https://gdz.bkg.bund.de/index.php/default/quasigeoid-der-bundesrepublik-deutschland-quasigeoid.html"
PROJ_CDN_URL = "https://cdn.proj.org/"


@dataclass
class CellGrid:
    keys: np.ndarray
    x_idx: np.ndarray
    y_idx: np.ndarray
    med_z: np.ndarray
    count: np.ndarray


@dataclass
class ResidualStats:
    name: str
    mean: float
    std: float
    median: float
    p05: float
    p95: float
    count: int


@dataclass
class VerticalResult:
    raw: ResidualStats
    geoid: ResidualStats | None
    constant: ResidualStats
    chosen_method: str
    chosen_std_pass: bool
    constant_offset_m: float
    geoid_available: bool
    geoid_error: str
    geoid_sha256: str | None
    geoid_size_bytes: int | None
    chosen_inlier: ResidualStats
    chosen_inlier_share: float


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env)

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo.parent,
        text=True,
    ).strip()
    run_id = env.get("RUN_ID") or datetime.now().strftime("t7_vertical_%Y%m%d_%H%M%S")

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
                f"P0_GIT_COMMIT={git_commit}",
                "-e",
                f"RUN_ID={run_id}",
                "tools",
                "python",
                "/workspace/scripts/07_vertical_align.py",
                *sys.argv[1:],
            ],
            cwd=repo,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise


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
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return (proc.stdout or proc.stderr).strip()


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "phases/p0-audit/docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Vertical Alignment\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_gcg2016_grid(path: Path) -> tuple[bool, str, str | None, int | None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not path.exists() or path.stat().st_size == 0:
            tmp = path.with_suffix(".tmp")
            if tmp.exists():
                tmp.unlink()
            urlretrieve(GCG2016_URL, tmp)
            tmp.replace(path)
        return True, "", sha256_file(path), int(path.stat().st_size)
    except Exception as exc:
        return False, repr(exc), None, None


def load_scene_aoi(path: Path) -> tuple[tuple[float, float, float, float], float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    props = data["features"][0]["properties"]
    bbox = (
        float(props["min_x"]),
        float(props["min_y"]),
        float(props["max_x"]),
        float(props["max_y"]),
    )
    return bbox, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def read_ground_points(paths: list[Path], bbox: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import laspy

    min_x, min_y, max_x, max_y = bbox
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    for path in paths:
        with laspy.open(path) as fh:
            for points in fh.chunk_iterator(1_000_000):
                cls = np.asarray(points.classification, dtype=np.uint8)
                x = np.asarray(points.x)
                y = np.asarray(points.y)
                mask = (
                    (cls == GROUND_CLASS)
                    & (x >= min_x)
                    & (x <= max_x)
                    & (y >= min_y)
                    & (y <= max_y)
                )
                if not np.any(mask):
                    continue
                xs.append(x[mask].astype(np.float64, copy=False))
                ys.append(y[mask].astype(np.float64, copy=False))
                zs.append(np.asarray(points.z)[mask].astype(np.float64, copy=False))

    if not xs:
        raise RuntimeError(f"No ground(class 2) points found in {', '.join(str(p) for p in paths)}")
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)


def build_cell_grid(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    origin: tuple[float, float],
    cell_size: float,
    min_points_per_cell: int,
) -> CellGrid:
    x_idx = np.floor((x - origin[0]) / cell_size).astype(np.int64)
    y_idx = np.floor((y - origin[1]) / cell_size).astype(np.int64)
    key = (x_idx << 32) | (y_idx & 0xFFFFFFFF)
    order = np.argsort(key, kind="mergesort")
    key_sorted = key[order]
    z_sorted = z[order]

    unique_keys, start, counts = np.unique(key_sorted, return_index=True, return_counts=True)
    keep = counts >= min_points_per_cell
    unique_keys = unique_keys[keep]
    start = start[keep]
    counts = counts[keep]

    medians = np.array(
        [float(np.median(z_sorted[s : s + c])) for s, c in zip(start, counts)],
        dtype=np.float64,
    )
    x_idx_unique = (unique_keys >> 32).astype(np.int64)
    y_idx_unique = (unique_keys & 0xFFFFFFFF).astype(np.int64)
    return CellGrid(unique_keys, x_idx_unique, y_idx_unique, medians, counts.astype(np.int64))


def join_cell_grids(als: CellGrid, dim: CellGrid) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    als_pos = {int(key): idx for idx, key in enumerate(als.keys)}
    dim_indices: list[int] = []
    als_indices: list[int] = []
    for dim_idx, key in enumerate(dim.keys):
        als_idx = als_pos.get(int(key))
        if als_idx is not None:
            dim_indices.append(dim_idx)
            als_indices.append(als_idx)
    if not dim_indices:
        raise RuntimeError("No common ground grid cells between ALS and DIM")
    d_idx = np.array(dim_indices, dtype=np.int64)
    a_idx = np.array(als_indices, dtype=np.int64)
    return (
        dim.keys[d_idx],
        dim.x_idx[d_idx],
        dim.y_idx[d_idx],
        als.med_z[a_idx],
        dim.med_z[d_idx],
    )


def residual_stats(name: str, residuals: np.ndarray) -> ResidualStats:
    return ResidualStats(
        name=name,
        mean=float(np.mean(residuals)),
        std=float(np.std(residuals)),
        median=float(np.median(residuals)),
        p05=float(np.percentile(residuals, 5.0)),
        p95=float(np.percentile(residuals, 95.0)),
        count=int(residuals.size),
    )


def central_inlier_stats(name: str, residuals: np.ndarray) -> tuple[ResidualStats, float]:
    low, high = np.percentile(residuals, [5.0, 95.0])
    mask = (residuals >= low) & (residuals <= high)
    return residual_stats(name, residuals[mask]), float(np.count_nonzero(mask) / residuals.size)


def make_geoid_transformer(geoid_path: Path):
    from pyproj import Transformer, datadir, network

    datadir.append_data_dir(str(geoid_path.parent))
    network.set_network_enabled(False)
    transformer = Transformer.from_crs("EPSG:25832+4937", "EPSG:25832+7837", always_xy=True)
    transformer.transform(690973.0, 5336109.0, 500.0)
    return transformer


def geoid_correct_z(transformer, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    _, _, z_corr = transformer.transform(x, y, z)
    return np.asarray(z_corr, dtype=np.float64)


def choose_method(geoid_stats: ResidualStats | None, constant_stats: ResidualStats) -> tuple[str, bool]:
    if geoid_stats:
        return "GCG2016", geoid_stats.std <= STD_THRESHOLD_M
    return "ground_constant", constant_stats.std <= STD_THRESHOLD_M


def sample_array_indices(size: int, limit: int, seed: int) -> np.ndarray:
    if size <= limit:
        return np.arange(size, dtype=np.int64)
    rng = np.random.default_rng(seed)
    return rng.choice(size, size=limit, replace=False)


def write_corrected_laz(
    input_laz: Path,
    output_laz: Path,
    method: str,
    constant_offset_m: float,
    transformer,
) -> None:
    import laspy

    output_laz.parent.mkdir(parents=True, exist_ok=True)
    tmp_laz = output_laz.with_suffix(".tmp.laz")
    if tmp_laz.exists():
        tmp_laz.unlink()

    with laspy.open(input_laz) as src:
        header = src.header.copy()
        with laspy.open(tmp_laz, mode="w", header=header) as dst:
            for points in src.chunk_iterator(1_000_000):
                if method == "GCG2016":
                    x = np.asarray(points.x)
                    y = np.asarray(points.y)
                    z = np.asarray(points.z)
                    points.z = geoid_correct_z(transformer, x, y, z)
                else:
                    points.z = np.asarray(points.z) - constant_offset_m
                dst.write_points(points)

    tmp_laz.replace(output_laz)


def write_offset_map(
    x: np.ndarray,
    y: np.ndarray,
    raw_residuals: np.ndarray,
    chosen_residuals: np.ndarray,
    chosen_name: str,
    out_png: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    raw_vmin, raw_vmax = np.percentile(raw_residuals, [2.0, 98.0])
    raw_sc = axes[0].scatter(
        x,
        y,
        c=raw_residuals,
        s=10,
        cmap="viridis",
        vmin=float(raw_vmin),
        vmax=float(raw_vmax),
        linewidths=0,
    )
    axes[0].set_title("Raw DIM - ALS ground median Z")
    fig.colorbar(raw_sc, ax=axes[0], shrink=0.82, label="raw Z difference (m)")

    abs_limit = float(np.nanpercentile(np.abs(chosen_residuals), 98.0))
    abs_limit = max(abs_limit, 0.25)
    residual_sc = axes[1].scatter(
        x,
        y,
        c=chosen_residuals,
        s=10,
        cmap="coolwarm",
        vmin=-abs_limit,
        vmax=abs_limit,
        linewidths=0,
    )
    axes[1].set_title(f"Residual after {chosen_name} correction")
    fig.colorbar(residual_sc, ax=axes[1], shrink=0.82, label="corrected residual (m)")

    for ax in axes:
        ax.set_xlabel("Easting (EPSG:25832 m)")
        ax.set_ylabel("Northing (EPSG:25832 m)")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, linewidth=0.25, alpha=0.3)
    fig.savefig(out_png, dpi=220)
    plt.close(fig)


def read_section_points(
    paths: list[Path],
    bbox: tuple[float, float, float, float],
    center_y: float,
    half_band: float,
    max_points: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    import laspy

    min_x, min_y, max_x, max_y = bbox
    xs: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    for path in paths:
        with laspy.open(path) as fh:
            for points in fh.chunk_iterator(1_000_000):
                x = np.asarray(points.x)
                y = np.asarray(points.y)
                mask = (
                    (x >= min_x)
                    & (x <= max_x)
                    & (y >= min_y)
                    & (y <= max_y)
                    & (np.abs(y - center_y) <= half_band)
                )
                if not np.any(mask):
                    continue
                xs.append(x[mask].astype(np.float64, copy=False))
                zs.append(np.asarray(points.z)[mask].astype(np.float64, copy=False))
    if not xs:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    x_all = np.concatenate(xs)
    z_all = np.concatenate(zs)
    idx = sample_array_indices(x_all.size, max_points, seed)
    return x_all[idx], z_all[idx]


def write_section_png(
    als_paths: list[Path],
    dim_original: Path,
    dim_corrected: Path,
    bbox: tuple[float, float, float, float],
    out_png: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    center_y = (bbox[1] + bbox[3]) / 2.0
    half_band = SECTION_BAND_WIDTH_M / 2.0
    als_x, als_z = read_section_points(als_paths, bbox, center_y, half_band, SECTION_MAX_POINTS, 29)
    dim_x, dim_z = read_section_points([dim_original], bbox, center_y, half_band, SECTION_MAX_POINTS, 31)
    cor_x, cor_z = read_section_points([dim_corrected], bbox, center_y, half_band, SECTION_MAX_POINTS, 37)

    if not als_x.size or not dim_x.size or not cor_x.size:
        raise RuntimeError("Section comparison has an empty ALS/DIM/corrected sample")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 7), constrained_layout=True)
    ax.scatter(dim_x, dim_z, s=0.7, c="#d62728", alpha=0.20, label=f"DIM original ({dim_x.size:,})")
    ax.scatter(cor_x, cor_z, s=0.7, c="#2ca02c", alpha=0.25, label=f"DIM corrected ({cor_x.size:,})")
    ax.scatter(als_x, als_z, s=1.0, c="#1f77b4", alpha=0.35, label=f"ALS ({als_x.size:,})")
    ax.set_xlabel("Easting (EPSG:25832 m)")
    ax.set_ylabel("Z (m)")
    ax.set_title(f"ALS vs DIM vertical section after correction, y={center_y:.2f} +/- {half_band:.1f} m")
    ax.legend(markerscale=7)
    ax.grid(True, linewidth=0.3, alpha=0.4)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def format_stats(stats: ResidualStats | None) -> str:
    if stats is None:
        return "n/a"
    return (
        f"mean={stats.mean:.3f} m, std={stats.std:.3f} m, "
        f"median={stats.median:.3f} m, p05={stats.p05:.3f} m, p95={stats.p95:.3f} m, n={stats.count:,}"
    )


def write_metrics_json(
    path: Path,
    run_id: str,
    result: VerticalResult,
    output_laz: Path,
    offset_map: Path,
    section_png: Path,
) -> None:
    def pack(stats: ResidualStats | None) -> dict[str, float | int | str] | None:
        if stats is None:
            return None
        return {
            "name": stats.name,
            "mean_m": stats.mean,
            "std_m": stats.std,
            "median_m": stats.median,
            "p05_m": stats.p05,
            "p95_m": stats.p95,
            "cell_count": stats.count,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "cell_size_m": CELL_SIZE_M,
                "std_threshold_m": STD_THRESHOLD_M,
                "raw_offset": pack(result.raw),
                "gcg2016_candidate": pack(result.geoid),
                "ground_constant_candidate": pack(result.constant),
                "chosen_method": result.chosen_method,
                "chosen_std_pass": result.chosen_std_pass,
                "chosen_central90": pack(result.chosen_inlier),
                "chosen_central90_share": result.chosen_inlier_share,
                "constant_offset_m": result.constant_offset_m,
                "geoid_available": result.geoid_available,
                "geoid_error": result.geoid_error,
                "geoid_source_url": GCG2016_URL,
                "geoid_sha256": result.geoid_sha256,
                "geoid_size_bytes": result.geoid_size_bytes,
                "output_laz": output_laz.as_posix().replace("/workspace/", ""),
                "offset_map": offset_map.as_posix().replace("/workspace/", ""),
                "section_png": section_png.as_posix().replace("/workspace/", ""),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def vertical_report_section(
    run_id: str,
    run_dir: Path,
    result: VerticalResult,
    output_laz: Path,
    offset_map: Path,
    section_png: Path,
    metrics_json: Path,
) -> str:
    rel = lambda path: path.as_posix().replace("/workspace/", "")
    chosen = result.geoid if result.chosen_method == "GCG2016" else result.constant
    pass_text = "PASS" if result.chosen_std_pass else "FAIL"
    inlier_pass_text = "PASS" if result.chosen_inlier.std <= STD_THRESHOLD_M else "FAIL"
    geoid_line = (
        f"- GCG2016 grid: `{rel(Path('/workspace/data/raw/geoid/de_bkg_gcg2016.tif'))}` "
        f"({result.geoid_size_bytes:,} bytes, SHA256 `{result.geoid_sha256}`)"
        if result.geoid_available
        else f"- GCG2016 grid: not applied (`{result.geoid_error}`)"
    )
    method_note = (
        "- Final correction: GCG2016 was selected as the default official geoid correction. The remaining all-cell standard deviation is dominated by ground-grid outliers rather than a single vertical offset."
        if result.chosen_method == "GCG2016"
        else "- Final correction: ground-point constant correction was selected because the GCG2016 model could not be applied in this run."
    )
    return "\n".join(
        [
            "## 수직 기준면 정합",
            "",
            f"- Run ID: {run_id}",
            f"- Run directory: {rel(run_dir)}",
            "- Ground-grid comparison: ALS class 2 vs DIM class 2, same 2 m cells inside `scene_aoi.gpkg`.",
            f"- Raw DIM-ALS ground offset: {format_stats(result.raw)}",
            f"- GCG2016 candidate residual: {format_stats(result.geoid)}",
            f"- Ground-constant candidate residual: {format_stats(result.constant)}",
            f"- Applied method: `{result.chosen_method}`",
            f"- Ground-constant fallback offset: {result.constant_offset_m:.3f} m would be subtracted from DIM Z if `ground_constant` is used.",
            f"- Corrected residual standard deviation check, all cells: {chosen.std:.3f} m <= {STD_THRESHOLD_M:.3f} m -> {pass_text}",
            (
                f"- Corrected residual standard deviation check, central 90% cells: "
                f"{result.chosen_inlier.std:.3f} m <= {STD_THRESHOLD_M:.3f} m -> {inlier_pass_text} "
                f"(share {result.chosen_inlier_share * 100.0:.1f}%)."
            ),
            geoid_line,
            f"- Corrected DIM LAZ: `{rel(output_laz)}`",
            f"- Residual metrics JSON: `{rel(metrics_json)}`",
            f"- Offset map PNG: `{rel(offset_map)}`",
            f"- Regenerated section comparison PNG: `{rel(section_png)}`",
            f"- GCG2016 product reference: {BKG_PRODUCT_URL}",
            f"- PROJ grid source: {GCG2016_URL}",
            "",
            method_note,
            "",
        ]
    )


def update_w1_diagnosis(path: Path, section: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "## 수직 기준면 정합"
    w2_marker = "## W2 진입 가능 여부 관찰 요약"
    if marker in text:
        start = text.index(marker)
        next_w2 = text.find(w2_marker, start)
        if next_w2 == -1:
            text = text[:start].rstrip() + "\n\n" + section
        else:
            text = text[:start].rstrip() + "\n\n" + section + text[next_w2 - 1 :]
    elif w2_marker in text:
        start = text.index(w2_marker)
        text = text[:start].rstrip() + "\n\n" + section + text[start:]
    else:
        text = text.rstrip() + "\n\n" + section
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_offset_csv(
    path: Path,
    x: np.ndarray,
    y: np.ndarray,
    raw: np.ndarray,
    geoid: np.ndarray | None,
    constant: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        header = "x,y,raw_dim_minus_als_m,constant_residual_m"
        if geoid is not None:
            header += ",gcg2016_residual_m"
        fh.write(header + "\n")
        for idx in range(raw.size):
            row = f"{x[idx]:.3f},{y[idx]:.3f},{raw[idx]:.4f},{constant[idx]:.4f}"
            if geoid is not None:
                row += f",{geoid[idx]:.4f}"
            fh.write(row + "\n")


def write_versions(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# T7 Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {os.environ['RUN_ID']}",
        f"- Repository commit: {os.environ.get('P0_GIT_COMMIT', 'unknown')}",
        "",
        "```console",
    ]
    for cmd in (
        ["python", "--version"],
        ["projinfo", "EPSG:7837"],
        ["lasinfo", "--version"],
        [
            "python",
            "-c",
            "import laspy, matplotlib, numpy, pyproj; print('laspy ' + laspy.__version__); print('matplotlib ' + matplotlib.__version__); print('numpy ' + numpy.__version__); print('pyproj ' + pyproj.__version__)",
        ],
    ):
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_config(run_dir: Path, values: dict[str, str | int | float]) -> None:
    lines = ["task: T7_vertical_alignment"]
    for key, value in values.items():
        lines.append(f"{key}: {value}")
    (run_dir / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path("/workspace")
    data = root / "data"
    docs = root / "docs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    work_dir = data / "work/vertical"
    figs_dir = docs / "figs"

    scene_aoi = data / "work/footprints/scene_aoi.geojson"
    dim_laz = data / "work/classify/dim_v1_classified.laz"
    corrected_laz = data / "work/classify/dim_v1_classified_z.laz"
    als_paths = sorted((data / "raw/als").glob("*.laz"))
    geoid_path = data / "raw/geoid/de_bkg_gcg2016.tif"
    metrics_json = work_dir / "vertical_alignment_metrics.json"
    offset_csv = work_dir / "ground_grid_offsets.csv"
    offset_map = figs_dir / "w1_ground_z_offset_map.png"
    section_png = figs_dir / "w1_vertical_section_corrected.png"
    diagnosis_md = docs / "W1_diagnosis.md"

    for path in (scene_aoi, dim_laz, diagnosis_md):
        if not path.exists():
            raise FileNotFoundError(path)
    if not als_paths:
        raise FileNotFoundError(data / "raw/als")

    work_dir.mkdir(parents=True, exist_ok=True)
    figs_dir.mkdir(parents=True, exist_ok=True)
    write_versions(run_dir)

    geoid_available, geoid_error, geoid_sha, geoid_size = ensure_gcg2016_grid(geoid_path)
    transformer = None
    if geoid_available:
        try:
            transformer = make_geoid_transformer(geoid_path)
        except Exception as exc:
            geoid_available = False
            geoid_error = repr(exc)

    aoi_bbox, _ = load_scene_aoi(scene_aoi)
    origin = (aoi_bbox[0], aoi_bbox[1])

    als_x, als_y, als_z = read_ground_points(als_paths, aoi_bbox)
    dim_x, dim_y, dim_z = read_ground_points([dim_laz], aoi_bbox)
    als_grid = build_cell_grid(als_x, als_y, als_z, origin, CELL_SIZE_M, min_points_per_cell=2)
    dim_grid = build_cell_grid(dim_x, dim_y, dim_z, origin, CELL_SIZE_M, min_points_per_cell=6)
    _, x_idx, y_idx, als_med_z, dim_med_z = join_cell_grids(als_grid, dim_grid)

    cell_x = origin[0] + (x_idx.astype(np.float64) + 0.5) * CELL_SIZE_M
    cell_y = origin[1] + (y_idx.astype(np.float64) + 0.5) * CELL_SIZE_M
    raw_residual = dim_med_z - als_med_z
    raw_stats = residual_stats("raw_dim_minus_als", raw_residual)
    constant_offset = raw_stats.mean
    constant_residual = raw_residual - constant_offset
    constant_stats = residual_stats("ground_constant", constant_residual)

    geoid_residual = None
    geoid_stats = None
    if geoid_available and transformer is not None:
        try:
            geoid_dim_z = geoid_correct_z(transformer, cell_x, cell_y, dim_med_z)
            geoid_residual = geoid_dim_z - als_med_z
            geoid_stats = residual_stats("GCG2016", geoid_residual)
        except Exception as exc:
            geoid_available = False
            geoid_error = repr(exc)

    chosen_method, chosen_pass = choose_method(geoid_stats, constant_stats)
    chosen_residual = geoid_residual if chosen_method == "GCG2016" and geoid_residual is not None else constant_residual
    chosen_inlier_stats, chosen_inlier_share = central_inlier_stats(f"{chosen_method}_central90", chosen_residual)
    write_corrected_laz(dim_laz, corrected_laz, chosen_method, constant_offset, transformer)
    write_offset_map(cell_x, cell_y, raw_residual, chosen_residual, chosen_method, offset_map)
    write_section_png(als_paths, dim_laz, corrected_laz, aoi_bbox, section_png)
    write_offset_csv(offset_csv, cell_x, cell_y, raw_residual, geoid_residual, constant_residual)

    result = VerticalResult(
        raw=raw_stats,
        geoid=geoid_stats,
        constant=constant_stats,
        chosen_method=chosen_method,
        chosen_std_pass=chosen_pass,
        constant_offset_m=constant_offset,
        geoid_available=geoid_available,
        geoid_error=geoid_error,
        geoid_sha256=geoid_sha,
        geoid_size_bytes=geoid_size,
        chosen_inlier=chosen_inlier_stats,
        chosen_inlier_share=chosen_inlier_share,
    )
    write_metrics_json(metrics_json, run_id, result, corrected_laz, offset_map, section_png)
    update_w1_diagnosis(
        diagnosis_md,
        vertical_report_section(run_id, run_dir, result, corrected_laz, offset_map, section_png, metrics_json),
    )
    write_config(
        run_dir,
        {
            "run_id": run_id,
            "cell_size_m": CELL_SIZE_M,
            "std_threshold_m": STD_THRESHOLD_M,
            "ground_cells": raw_stats.count,
            "raw_offset_mean_m": f"{raw_stats.mean:.6f}",
            "raw_offset_std_m": f"{raw_stats.std:.6f}",
            "gcg2016_residual_std_m": "n/a" if geoid_stats is None else f"{geoid_stats.std:.6f}",
            "ground_constant_offset_m": f"{constant_offset:.6f}",
            "ground_constant_residual_std_m": f"{constant_stats.std:.6f}",
            "chosen_method": chosen_method,
            "chosen_std_pass": str(chosen_pass),
            "chosen_central90_residual_std_m": f"{chosen_inlier_stats.std:.6f}",
            "chosen_central90_share": f"{chosen_inlier_share:.6f}",
            "corrected_laz": "data/work/classify/dim_v1_classified_z.laz",
        },
    )

    print(f"ground_grid_cells={raw_stats.count}")
    print(f"raw_offset_mean_m={raw_stats.mean:.6f}")
    print(f"raw_offset_std_m={raw_stats.std:.6f}")
    print(f"gcg2016_residual={format_stats(geoid_stats)}")
    print(f"constant_offset_m={constant_offset:.6f}")
    print(f"constant_residual_std_m={constant_stats.std:.6f}")
    print(f"chosen_method={chosen_method}")
    print(f"chosen_residual_all_cell_std_pass={chosen_pass}")
    print(f"chosen_residual_central90_std_m={chosen_inlier_stats.std:.6f}")
    print(f"corrected_laz={corrected_laz}")
    print(f"offset_map={offset_map}")
    print(f"section_png={section_png}")


if __name__ == "__main__":
    if os.environ.get("P0_INSIDE_CONTAINER") != "1":
        host_entrypoint()
    else:
        main()
