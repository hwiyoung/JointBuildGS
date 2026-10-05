"""Point-projection input diagnostic, not a surface or reference evaluation."""
import csv
import importlib.util
import json
from pathlib import Path
import resource
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


base = load_module("depth_diagnostic", "/base_script.py")
roi = load_module("roi_contract", "/roi_contract.py")
describe, write, sha = base.describe, base.write, base.sha


def project(points, view):
    xyz = points @ np.asarray(view["R"]).T + np.asarray(view["t"])
    xyz = xyz[xyz[:, 2] >= 1e-4]
    homogeneous = xyz @ np.asarray(view["K"]).T
    pixels = np.floor(homogeneous[:, :2] / homogeneous[:, 2:] + .5).astype(np.int64)
    valid = (pixels[:, 0] >= 0) & (pixels[:, 0] < view["width"]) & (pixels[:, 1] >= 0) & (pixels[:, 1] < view["height"])
    indices = pixels[valid, 1] * view["width"] + pixels[valid, 0]
    depth = np.full(view["height"] * view["width"], np.inf, dtype=np.float64)
    np.minimum.at(depth, indices, xyz[valid, 2])
    return depth.reshape(view["height"], view["width"]), int(valid.sum())


def stats(mvs, prior, da3, box):
    x0, y0, x1, y1 = box
    m, p, d = [x[y0:y1, x0:x1] for x in (mvs, prior, da3)]
    mv, pv, dv = [np.isfinite(x) & (x > 0) for x in (m, p, d)]
    common = mv & pv & dv
    row = {"pixels": m.size, "mvs_supported_pixels": int(mv.sum()),
           "mvs_prior_supported_pixels": int((mv & pv).sum()), "mvs_da3_supported_pixels": int((mv & dv).sum()),
           "all_three_common_pixels": int(common.sum())}
    m, p, d = m[common], p[common].astype(np.float64), d[common].astype(np.float64)
    for key, values in [("mvs_m", m), ("prior_m", p), ("da3_m", d),
                        ("prior_minus_mvs_m", p-m), ("da3_minus_mvs_m", d-m),
                        ("abs_prior_mvs_m", np.abs(p-m)), ("abs_da3_mvs_m", np.abs(d-m)),
                        ("prior_over_mvs", p/m), ("da3_over_mvs", d/m), ("da3_over_prior", d/p)]:
        row.update({key + "_" + k: v for k, v in describe(values).items()})
    row["prior_minus_mvs_clipped_minus50"] = int((p-m < -50).sum())
    row["prior_minus_mvs_clipped_plus50"] = int((p-m > 50).sum())
    row["da3_minus_mvs_clipped_minus50"] = int((d-m < -50).sum())
    row["da3_minus_mvs_clipped_plus50"] = int((d-m > 50).sum())
    for key, array in [("mvs", m), ("prior", p), ("da3", d)]: row[key + "_clipped_depth150"] = int((array > 150).sum())
    return row


def make_figure(mvs, prior, da3, box, row, output, label):
    x0, y0, x1, y1 = box
    m, p, d = [x[y0:y1, x0:x1] for x in (mvs, prior, da3)]
    common = np.isfinite(m) & (m > 0) & np.isfinite(p) & (p > 0) & np.isfinite(d) & (d > 0)
    cm = plt.get_cmap("viridis").copy(); cm.set_bad("#bfc5ca")
    cd = plt.get_cmap("coolwarm").copy(); cd.set_bad("#bfc5ca")
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    for ax, array, title in zip(axes[0], [m, p, d], ["Projected MVS core points", "ALS prior", "DA3"]):
        value = np.where(np.isfinite(array) & (array > 0), array, np.nan)
        im = ax.imshow(value, vmin=0, vmax=150, cmap=cm)
        ax.set_title(title + "; camera-Z (0..150 m)"); fig.colorbar(im, ax=ax, shrink=.65)
    for ax, array, title in [(axes[1, 0], p-m, "prior - MVS"), (axes[1, 1], d-m, "DA3 - MVS")]:
        im = ax.imshow(np.where(common, array, np.nan), vmin=-50, vmax=50, cmap=cd)
        ax.set_title(title + "; three-way supported pixels")
        fig.colorbar(im, ax=ax, shrink=.65, label="m; fixed -50..50")
    axes[1, 2].imshow(common, vmin=0, vmax=1, cmap="gray"); axes[1, 2].set_title("Three-way support; no point-depth filling")
    for ax in axes.ravel(): ax.set_axis_off()
    fig.suptitle(f"{row['region']} | {label} | {row['name']}\n"
                 f"n={row['all_three_common_pixels']:,}; median |prior-MVS|={row['abs_prior_mvs_m_median']:.3f} m; "
                 f"median |DA3-MVS|={row['abs_da3_mvs_m_median']:.3f} m\n"
                 "POINT-PROJECTION INPUT DIAGNOSTIC; production all-view MVS is not independent ground truth", fontsize=11)
    fig.savefig(output, dpi=130); plt.close(fig)


def main():
    start = time.monotonic(); out = Path("/out")
    config = json.loads(Path("/config.json").read_text())
    selected = json.loads(Path("/selected_views.json").read_text())
    policy = {"scientific_verdict": None, "status": "POINT_PROJECTION_INPUT_DIAGNOSTIC_ONLY",
              "projection": "Frozen scene-local MVS core points @ R.T+t; camera-Z; nearest integer pixel floor(u+0.5); frontmost minimum Z; no fill/surface interpolation",
              "scope": "Production all-view MVS geometry; historical shared camera lineage; not independent evaluation or current ground truth",
              "three_way_stats": "MVS/prior/DA3 all finite positive at same pixel; full frame and fixed projected-prism bbox",
              "prior_ray_offset_limit": "Prior Open3D rays use pixel+0.5; diagnostic point projection nearest integer centers; original native half-pixel convention discrepancy is retained, not fitted",
              "figures": "Same lex-first/median/worst selections already frozen by prior-vs-DA3 input diagnostic; no new result selection",
              "depth_color_m": [0, 150], "difference_color_m": [-50, 50], "numeric_statistics_unclipped": True,
              "config_sha256": sha("/config.json"), "script_sha256": sha(__file__), "base_script_sha256": sha("/base_script.py"),
              "reference_accessed": False, "evaluation_rgb_accessed": False, "no_input_or_training_changes": True}
    write(out / "policy.json", policy)
    rows, native_ledger, summaries = [], {}, {}
    for region, settings in config["regions"].items():
        native_path = Path("/native") / (region + ".npz")
        with np.load(native_path, allow_pickle=False) as data: points = np.asarray(data["mvs_xyz"], dtype=np.float64)
        if not np.isfinite(points).all(): raise ValueError("Nonfinite native MVS geometry")
        bounds = np.array([settings["domain"][axis] for axis in "xyz"])
        if not np.all((points >= bounds[:, 0]) & (points < bounds[:, 1])): raise ValueError("Frozen MVS geometry escaped exact core prism")
        native_ledger[region] = {"native_npz_sha256": sha(native_path), "mvs_core_points": len(points), "array_read": "mvs_xyz"}
        split = json.loads((Path("/inputs") / region / "scene/split_manifest_da3_v2.json").read_text())
        region_rows = []
        for i, view in enumerate(sorted(split["train"], key=lambda v: v["name"])):
            stem = Path(view["name"]).stem; root = Path("/inputs") / region
            p, d = np.load(root / "prior/raw_depth" / (stem + ".npy")), np.load(root / "da3/raw_depth" / (stem + ".npy"))
            m, projected_count = project(points, view)
            box = roi.projected_prism_bbox(settings["domain"], view["R"], view["t"], view["K"], view["width"], view["height"])
            for domain, bbox in [("full_frame", [0, 0, view["width"], view["height"]]), ("fixed_prism_projected_bbox", box)]:
                row = {"region": region, "image_id": view["image_id"], "name": view["name"], "domain": domain,
                       "bbox": bbox, "mvs_points_projected_in_frame": projected_count}
                row.update(stats(m, p, d, bbox if bbox else [0, 0, 0, 0])); rows.append(row)
                if domain == "fixed_prism_projected_bbox": region_rows.append(row)
            for item in selected:
                if item["region"] == region and item["image_name"] == view["name"]:
                    make_figure(m, p, d, box, region_rows[-1], out / f"{region}_{item['selection']}_mvs.png", item["selection"])
            if i == 0 or i % 25 == 24:
                row = region_rows[-1]
                print(json.dumps({"region": region, "processed": i+1, "name": view["name"], "support": row["all_three_common_pixels"],
                                  "prior_mvs_median_abs": row["abs_prior_mvs_m_median"], "da3_mvs_median_abs": row["abs_da3_mvs_m_median"]}), flush=True)
        eligible = [r for r in region_rows if r["all_three_common_pixels"]]
        keys = ["abs_prior_mvs_m_median", "abs_da3_mvs_m_median", "prior_over_mvs_median", "da3_over_mvs_median"]
        summaries[region] = {"train_count": len(region_rows), "common_supported_views": len(eligible),
                             "three_way_pixel_count_sum": sum(r["all_three_common_pixels"] for r in region_rows),
                             "image_level_distributions": {k: describe(np.array([r[k] for r in eligible])) for k in keys}}
        write(out / f"{region}_summary.json", summaries[region])
    write(out / "per_image_statistics.json", rows)
    with (out / "per_image_statistics.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    write(out / "native_input_ledger.json", native_ledger)
    write(out / "receipt.json", {"scientific_verdict": None, "status": "PASS_REFERENCE_FREE_MVS_POINT_PROJECTION_DIAGNOSTIC",
                                  "reference_accessed": False, "regions": summaries, "wall_seconds": time.monotonic()-start,
                                  "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                                  "outputs": {p.name: sha(p) for p in out.iterdir() if p.suffix in [".png", ".json", ".csv"]}})


if __name__ == "__main__": main()
