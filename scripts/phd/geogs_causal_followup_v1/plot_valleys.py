"""Plot only frozen evaluation samples; no rendering, extraction or distances."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def select(points, bounds):
    keep = np.ones(len(points), dtype=bool)
    for axis, (lo, hi) in enumerate(bounds):
        keep &= (points[:, axis] >= lo) & (points[:, axis] < hi)
    return np.flatnonzero(keep)


def summary(points):
    if not len(points):
        return {"count": 0, **{k: None for k in ["z_min_m", "z_q10_m", "z_median_m", "z_q90_m", "z_max_m"]}}
    vals = np.quantile(points[:, 2], [0, .1, .5, .9, 1])
    return {"count": len(points), **dict(zip(["z_min_m", "z_q10_m", "z_median_m", "z_q90_m", "z_max_m"], map(float, vals)))}


def write_csv(path, rows):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--git-commit", required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    assert config["scientific_verdict"] is None
    figures, analysis = args.output / "figures", args.output / "analysis"
    figures.mkdir(exist_ok=True, parents=True)
    analysis.mkdir(exist_ok=True, parents=True)
    targets = [figures / f"valley_{name}.png" for name in ["panels", "zooms"]]
    targets += [analysis / f"valley_{name}" for name in ["receipt.json", "bins.csv", "windows.csv", "samples.csv"]]
    if any(p.exists() for p in targets):
        raise FileExistsError("Refusing to overwrite existing diagnostic outputs")
    hashes, arrays, metadata = {}, {}, {}
    reference = reference_ids = None
    root = args.source / "evaluation" / "geometry" / config["region"]
    for candidate in config["candidates"]:
        candidate_id = candidate["id"]
        base = root / candidate_id / config["cached_evaluation"]
        data_path, meta_path = base.with_suffix(".npz"), base.with_suffix(".json")
        # The base includes decimal points; append suffix rather than replace it.
        data_path, meta_path = Path(str(base) + ".npz"), Path(str(base) + ".json")
        for path in [data_path, meta_path]:
            hashes[str(path.relative_to(args.source))] = digest(path)
        metadata[candidate_id] = json.loads(meta_path.read_text())
        if candidate_id != "prior_mesh":
            assert metadata[candidate_id]["mesh_res"] == 512
        with np.load(data_path, allow_pickle=False) as data:
            arrays[candidate_id] = data["prediction_surface_samples"].copy()
            if reference is None:
                reference = data["reference_points"].copy()
                reference_ids = data["reference_original_indices"].copy()
            else:
                assert np.array_equal(reference, data["reference_points"])
                assert np.array_equal(reference_ids, data["reference_original_indices"])
    arrays["observed_UAS"] = reference
    bounds = [config[f"{axis}_half_open_m"] for axis in "xyz"]
    bands, sample_rows = {}, []
    for name, points in arrays.items():
        ids = select(points, bounds)
        bands[name] = points[ids]
        for index in ids:
            sample_rows.append({"source": name, "array_row_index": int(index),
                "reference_original_index": int(reference_ids[index]) if name == "observed_UAS" else None,
                "x_m": float(points[index, 0]), "y_m": float(points[index, 1]), "z_m": float(points[index, 2])})
    write_csv(analysis / "valley_samples.csv", sample_rows)
    bin_rows, window_rows = [], []
    bin_width = config["y_bin_width_m"]
    for lo in np.arange(*bounds[1], bin_width):
        hi = float(lo + bin_width)
        for name, points in bands.items():
            subset = points[(points[:, 1] >= lo) & (points[:, 1] < hi)]
            bin_rows.append({"source": name, "y_lo_m": float(lo), "y_hi_m": hi, **summary(subset)})
    for index, (lo, hi) in enumerate(config["diagnostic_windows_y_m"]):
        for name, points in bands.items():
            subset = points[(points[:, 1] >= lo) & (points[:, 1] < hi)]
            window_rows.append({"window": chr(65 + index), "source": name, "y_lo_m": lo, "y_hi_m": hi, **summary(subset)})
    write_csv(analysis / "valley_bins.csv", bin_rows)
    write_csv(analysis / "valley_windows.csv", window_rows)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False})
    ref = bands["observed_UAS"]
    fig, axes = plt.subplots(2, 2, figsize=(14.5, 8), sharex=True, sharey=True)
    for ax, candidate in zip(axes.flat, config["candidates"]):
        points = bands[candidate["id"]]
        ax.scatter(ref[:, 1], ref[:, 2], s=5, c="#171717", alpha=.72, linewidths=0, label="Observed current UAS")
        ax.scatter(points[:, 1], points[:, 2], s=4, c=candidate["color"], alpha=.75, linewidths=0, label="Stored surface samples")
        ax.set_title(candidate["label"], loc="left", fontweight="bold", fontsize=11)
        ax.set_xlim(*bounds[1]); ax.set_ylim(*bounds[2]); ax.grid(alpha=.16)
        for index, (lo, hi) in enumerate(config["diagnostic_windows_y_m"]):
            ax.axvspan(lo, hi, color="#687785", alpha=.13)
            ax.text((lo + hi) / 2, -27.25, chr(65 + index), ha="center", fontsize=10)
    axes[0, 0].legend(loc="upper left", fontsize=9, markerscale=1.8)
    for ax in axes[:, 0]: ax.set_ylabel("Local Z (m)")
    for ax in axes[-1, :]: ax.set_xlabel("Local Y (m)")
    fig.suptitle("P2 repeated-roof troughs | same 0.5 m X band | no interpolation", fontsize=15, fontweight="bold")
    fig.text(.01, .016, "X in [133.75, 134.25) m. All cached samples in the displayed window; UAS is evaluation-only.\n"
             "Band projections are not mesh-plane intersections. Multiple surface layers remain visible. Windows A/B are post hoc diagnostics.", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .95))
    fig.savefig(figures / "valley_panels.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True)
    for index, (ax, (lo, hi)) in enumerate(zip(axes, config["zoom_windows_y_m"])):
        ax.scatter(ref[:, 1], ref[:, 2], s=16, c="#141414", alpha=.76, linewidths=0, zorder=5)
        for candidate in config["candidates"]:
            points = bands[candidate["id"]]
            ax.scatter(points[:, 1], points[:, 2], s=10, c=candidate["color"], alpha=.64, linewidths=0)
        wlo, whi = config["diagnostic_windows_y_m"][index]
        ax.axvspan(wlo, whi, color="#687785", alpha=.1)
        ax.set_title(f"Window {chr(65 + index)} | highlighted Y [{wlo}, {whi}) m", loc="left", fontsize=11)
        ax.set_xlim(lo, hi); ax.set_ylim(*bounds[2]); ax.grid(alpha=.16)
        ax.set_xlabel("Local Y (m)")
    axes[0].set_ylabel("Local Z (m)")
    handles = [Line2D([], [], linestyle="", marker="o", color="#171717", label="Observed current UAS")]
    handles += [Line2D([], [], linestyle="", marker="o", color=c["color"], label=c["label"]) for c in config["candidates"]]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .985), ncol=3, frameon=False, fontsize=9)
    fig.text(.01, .02, "Same stored samples as the full panels. No fitted surface or matching. A/B selected after inspecting existing results; not population estimates.", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .85))
    fig.savefig(figures / "valley_zooms.png", dpi=170)
    plt.close(fig)
    for relative, before in hashes.items():
        assert digest(args.source / relative) == before, relative
    receipt = {
        "task_id": config["task_id"], "scientific_verdict": None,
        "status": "PASS_CACHED_SAMPLE_DIAGNOSTIC", "config": config,
        "input_sha256": hashes, "script_sha256": digest(__file__),
        "config_sha256": digest(args.config), "git_commit": args.git_commit,
        "docker_image_id": args.image_id,
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "same_reference_points_and_original_ids": True,
        "source_preserved_sha256_before_after": True,
        "crs": metadata["prior_mesh"]["crs"],
        "candidate_metadata": {k: {f: m.get(f) for f in ["mesh_res", "iteration", "surface_kind", "surface_samples", "surface_sample_spacing_m", "reference_voxel_size_m", "source_sha256"]} for k, m in metadata.items()},
        "band_sample_counts": {k: len(v) for k, v in bands.items()},
        "window_statistics": window_rows,
        "new_training_runs": 0, "new_scene_renders": 0, "new_mesh_extractions": 0,
        "new_registration": 0, "new_distance_queries": 0,
        "warnings": ["Post hoc fixed-window sample diagnostics, not confirmatory performance.",
                     "Z bounds deliberately show roof-height support; out-of-window surfaces remain in source arrays.",
                     "Quantile differences compare distributions in the same XY strip; they are not paired errors or topology proof.",
                     "Anchor contains multiple surface layers, so near-reference samples do not demonstrate unique correct geometry."]
    }
    receipt["output_sha256"] = {str(p.relative_to(args.output)): digest(p) for p in targets if p.exists()}
    with (analysis / "valley_receipt.json").open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "band_sample_counts": receipt["band_sample_counts"], "window_statistics": window_rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
