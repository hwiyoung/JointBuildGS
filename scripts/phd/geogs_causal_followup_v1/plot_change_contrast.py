"""Compare two existing input/output geometry bands without reconstruction."""
from __future__ import annotations
import argparse
import json
import platform
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from plot_valleys import digest, select, summary, write_csv


def main():
    parser = argparse.ArgumentParser()
    for name in ["source", "output", "config"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--git-commit", required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    assert config["scientific_verdict"] is None
    figures, analysis = args.output / "figures", args.output / "analysis"
    figures.mkdir(exist_ok=True, parents=True); analysis.mkdir(exist_ok=True, parents=True)
    outputs = [figures / "change_contrast.png", analysis / "change_receipt.json",
               analysis / "change_samples.csv", analysis / "change_bins.csv"]
    if any(path.exists() for path in outputs):
        raise FileExistsError("Refusing existing output overwrite")
    hashes, all_bands, sample_rows, bin_rows, source_meta = {}, {}, [], [], {}
    for region in config["regions"]:
        rid = region["id"]
        arrays, reference, reference_ids = {}, None, None
        for candidate in config["candidates"]:
            cid = candidate["id"]
            base = args.source / "evaluation" / "geometry" / rid / cid / config["cached_evaluation"]
            data_path, meta_path = Path(str(base) + ".npz"), Path(str(base) + ".json")
            for path in [data_path, meta_path]: hashes[str(path.relative_to(args.source))] = digest(path)
            meta = json.loads(meta_path.read_text())
            if cid != "prior_mesh": assert meta["mesh_res"] == 512
            source_meta[rid + "/" + cid] = {key: meta.get(key) for key in ["mesh_res", "iteration", "source_sha256", "crs", "surface_samples"]}
            with np.load(data_path, allow_pickle=False) as data:
                arrays[cid] = data["prediction_surface_samples"].copy()
                if reference is None:
                    reference = data["reference_points"].copy()
                    reference_ids = data["reference_original_indices"].copy()
                else:
                    assert np.array_equal(reference, data["reference_points"])
                    assert np.array_equal(reference_ids, data["reference_original_indices"])
        arrays["observed_UAS"] = reference
        bands = {}
        for name, points in arrays.items():
            ids = select(points, region["bounds_half_open_m"])
            bands[name] = points[ids]
            for index in ids:
                sample_rows.append({"region": rid, "source": name, "array_row_index": int(index),
                    "reference_original_index": int(reference_ids[index]) if name == "observed_UAS" else None,
                    "x_m": float(points[index, 0]), "y_m": float(points[index, 1]), "z_m": float(points[index, 2])})
            for lo in np.arange(*region["bounds_half_open_m"][1], config["y_bin_width_m"]):
                hi = lo + config["y_bin_width_m"]
                subset = bands[name][(bands[name][:, 1] >= lo) & (bands[name][:, 1] < hi)]
                bin_rows.append({"region": rid, "source": name, "y_lo_m": float(lo), "y_hi_m": float(hi), **summary(subset)})
        all_bands[rid] = bands
    write_csv(analysis / "change_samples.csv", sample_rows)
    write_csv(analysis / "change_bins.csv", bin_rows)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6))
    for ax, region in zip(axes, config["regions"]):
        bands, bounds = all_bands[region["id"]], region["bounds_half_open_m"]
        ref = bands["observed_UAS"]
        for candidate in config["candidates"]:
            points = bands[candidate["id"]]
            ax.scatter(points[:, 1], points[:, 2], s=8, c=candidate["color"], alpha=.7, linewidths=0)
        ax.scatter(ref[:, 1], ref[:, 2], s=10, c="#171717", alpha=.75, linewidths=0, zorder=5)
        ax.set_title(region["title"] + f"\nX in [{bounds[0][0]}, {bounds[0][1]}) m", loc="left", fontsize=11, fontweight="bold")
        ax.set_xlim(*bounds[1]); ax.set_ylim(*bounds[2]); ax.grid(alpha=.16)
        ax.set_xlabel("Local Y (m)"); ax.set_ylabel("Local Z (m)")
    handles = [Line2D([], [], linestyle="", marker="o", color="#171717", label="Observed current UAS")]
    handles += [Line2D([], [], linestyle="", marker="o", color=c["color"], label=c["label"]) for c in config["candidates"]]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .995), ncol=2, frameon=False, fontsize=9)
    fig.text(.01, .02, "All stored samples in each displayed 0.5 m X band; no interpolation. Different Y/Z axis ranges are explicit.\n"
             "Post hoc local diagnostics, not matched errors, population rates, exact mesh sections or a demolition label. UAS is evaluation-only.", fontsize=9)
    fig.tight_layout(rect=(0, .10, 1, .85))
    fig.savefig(figures / "change_contrast.png", dpi=170)
    plt.close(fig)
    for relative, before in hashes.items(): assert digest(args.source / relative) == before
    receipt = {"task_id": config["task_id"], "scientific_verdict": None,
        "status": "PASS_CACHED_CHANGE_CONTRAST", "config": config,
        "input_sha256": hashes, "script_sha256": digest(__file__),
        "helper_script_sha256": digest(Path(__file__).with_name("plot_valleys.py")),
        "config_sha256": digest(args.config), "git_commit": args.git_commit,
        "docker_image_id": args.image_id,
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "source_metadata": source_meta,
        "same_reference_points_and_original_ids_within_each_region": True,
        "source_preserved_sha256_before_after": True,
        "band_statistics": {r: {c: summary(p) for c, p in bands.items()} for r, bands in all_bands.items()},
        "new_training_runs": 0, "new_scene_renders": 0, "new_mesh_extractions": 0,
        "new_registration": 0, "new_distance_queries": 0,
        "output_sha256": {str(path.relative_to(args.output)): digest(path) for path in outputs if path.exists()}}
    with (analysis / "change_receipt.json").open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps({"status": receipt["status"], "band_statistics": receipt["band_statistics"]}))


if __name__ == "__main__":
    main()
