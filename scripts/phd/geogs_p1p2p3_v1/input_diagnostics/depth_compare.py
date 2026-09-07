"""Frozen-input, reference-free prior/DA3 camera-Z depth discrepancy diagnostic."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, data):
    with Path(path).open("x") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def describe(values):
    if not values.size:
        return {key: None for key in ["min", "q25", "median", "q75", "p95", "max", "mean", "rms"]}
    quantiles = np.quantile(values, [0, .25, .5, .75, .95, 1])
    return dict(zip(["min", "q25", "median", "q75", "p95", "max"], map(float, quantiles)),
                mean=float(np.mean(values, dtype=np.float64)),
                rms=float(np.sqrt(np.mean(np.square(values, dtype=np.float64)))))


def domain_stats(prior, depth, box):
    x0, y0, x1, y1 = box
    p, d = prior[y0:y1, x0:x1], depth[y0:y1, x0:x1]
    pv, dv = np.isfinite(p) & (p > 0), np.isfinite(d) & (d > 0)
    common = pv & dv
    a, b = p[common].astype(np.float64), d[common].astype(np.float64)
    diff = b - a
    stats = {"pixels": p.size, "prior_valid": int(pv.sum()), "da3_valid": int(dv.sum()),
             "common_valid": int(common.sum()), "prior_only": int((pv & ~dv).sum()),
             "da3_only": int((dv & ~pv).sum()), "neither": int((~pv & ~dv).sum()),
             "prior_above_depth_display150": int((a > 150).sum()),
             "da3_above_depth_display150": int((b > 150).sum()),
             "diff_below_display_minus50": int((diff < -50).sum()),
             "diff_above_display_plus50": int((diff > 50).sum())}
    for prefix, values in (("prior_m", a), ("da3_m", b), ("da3_minus_prior_m", diff),
                           ("absdiff_m", np.abs(diff)), ("da3_over_prior", b / a)):
        stats.update({prefix + "_" + k: v for k, v in describe(values).items()})
    return stats


def figure(region, label, row, view, prior, depth, rgb_path, target):
    rgb = np.asarray(Image.open(rgb_path).convert("RGB"))
    if sha(rgb_path) != view["sha256"] or rgb.shape[:2] != prior.shape:
        raise ValueError("Selected training RGB changed")
    pv, dv = np.isfinite(prior) & (prior > 0), np.isfinite(depth) & (depth > 0)
    common = pv & dv
    bbox = row["bbox"]
    if bbox is None:
        bbox = [0, 0, view["width"], view["height"]]
    x0, y0, x1, y1 = bbox
    difference = np.where(common, depth - prior, np.nan)
    ratio = np.full_like(depth, np.nan)
    np.divide(depth, prior, out=ratio, where=common)
    fig, axes = plt.subplots(2, 3, figsize=(18, 9), constrained_layout=True)
    axes[0, 0].imshow(rgb); axes[0, 0].set_title("Actual training photograph + fixed prism bbox")
    cm_depth = plt.get_cmap("viridis").copy(); cm_depth.set_bad("#bfc5ca")
    for ax, array, title in [(axes[0, 1], np.where(pv, prior, np.nan), "ALS prior camera-Z"),
                             (axes[0, 2], np.where(dv, depth, np.nan), "DA3 camera-Z")]:
        im = ax.imshow(array, vmin=0, vmax=150, cmap=cm_depth)
        ax.set_title(title + " (0..150 m; clipped)"); fig.colorbar(im, ax=ax, shrink=.7, label="m")
    for ax in axes[0]:
        ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=False, edgecolor="red", linewidth=1))
    axes[1, 0].imshow(rgb[y0:y1, x0:x1]); axes[1, 0].set_title("Same fixed projected-prism crop")
    cm_diff = plt.get_cmap("coolwarm").copy(); cm_diff.set_bad("#bfc5ca")
    im = axes[1, 1].imshow(difference[y0:y1, x0:x1], vmin=-50, vmax=50, cmap=cm_diff)
    axes[1, 1].set_title("DA3 - prior; common finite positive pixels")
    fig.colorbar(im, ax=axes[1, 1], shrink=.7, label="m; fixed -50..50")
    im = axes[1, 2].imshow(ratio[y0:y1, x0:x1], vmin=0, vmax=5, cmap=cm_depth)
    axes[1, 2].set_title("DA3 / prior; fixed 0..5 (display only)")
    fig.colorbar(im, ax=axes[1, 2], shrink=.7, label="ratio")
    for ax in axes.ravel(): ax.set_axis_off()
    fig.suptitle(f"{region} | {label} | {view['name']} | batch {row['batch_id']}\n"
                 f"ROI common n={row['common_valid']:,}; median DA3/prior={row['da3_over_prior_median']:.3f}; "
                 f"median absolute difference={row['absdiff_m_median']:.3f} m\n"
                 "INPUT DISCREPANCY ONLY; neither source is assumed current ground truth", fontsize=12)
    fig.savefig(target, dpi=130)
    plt.close(fig)


def main():
    start = time.monotonic()
    root, out = Path("/inputs"), Path("/out")
    config = json.loads(Path("/config.json").read_text())
    module = importlib.util.spec_from_file_location("roi_contract", "/roi_contract.py")
    roi = importlib.util.module_from_spec(module); module.loader.exec_module(roi)
    policy = {"task_id": config["task_id"], "scientific_verdict": None,
              "purpose": "sealed-input discrepancy diagnostic; no UAS, no rerun, no setting change",
              "domains": ["full_frame_common_finite_positive", "fixed_prism_projected_bbox_common_finite_positive"],
              "roi_contract": "Reuse frozen evaluator projected_prism_bbox; near=1e-4; bounding rectangle, not silhouette",
              "roi_contract_sha256": sha("/roi_contract.py"), "config_sha256": sha("/config.json"),
              "script_sha256": sha(__file__), "depth_display_range_m": [0, 150],
              "signed_difference_display_range_m": [-50, 50], "ratio_display_range": [0, 5],
              "all_numeric_stats_unclipped": True,
              "figure_selection": "Per region fixed lex-first train image plus upper-middle and maximum ranked by per-image ROI median absolute DA3-prior difference; tie by filename ascending; no parameter tuning",
              "summary": "Region/batch summaries are unweighted distributions of image-level statistics; not pooled pixel quantiles",
              "input_difference_not_accuracy": True, "reference_accessed": False, "evaluation_rgb_accessed": False}
    write(out / "policy.json", policy)
    Path(out / "config_snapshot.json").write_bytes(Path("/config.json").read_bytes())
    all_rows, batch_rows, file_ledger, selections, summaries = [], [], [], [], {}
    for region, settings in config["regions"].items():
        folder = root / region
        split_path = folder / "scene/split_manifest_da3_v2.json"
        split = json.loads(split_path.read_text())
        prior_receipt = json.loads((folder / "prior/receipt.json").read_text())
        da3_receipt = json.loads((folder / "da3/receipt.json").read_text())
        inference = json.loads((folder / "da3/inference_receipt.json").read_text())
        if sha(split_path) != da3_receipt["split_sha256"]:
            raise ValueError("Sealed DA3 split mismatch")
        prior_rows = {r["name"]: r for r in prior_receipt["rows"]}
        da3_rows = {r["name"]: r for r in da3_receipt["images"]}
        train = sorted(split["train"], key=lambda v: v["name"])
        if set(prior_rows) != set(da3_rows) or set(da3_rows) != {v["name"] for v in train}:
            raise ValueError("Exact train depth membership mismatch")
        by_name = {v["name"]: v for v in train}
        by_batch = {}
        for batch in inference["batches"]:
            batch_id = batch["batch_id"]
            batchpath = Path("/batches") / region / f"batch_{batch_id:03d}.npz"
            digest = sha(batchpath)
            if digest != batch["files"][f"batches/batch_{batch_id:03d}.npz"]:
                raise ValueError("Retained native batch archive identity mismatch")
            with np.load(batchpath, allow_pickle=False) as data:
                names = data["image_names"].tolist()
                original_ext, aligned_ext = data["input_extrinsics"], data["extrinsics"]
                original_k, output_k = data["input_intrinsics"], data["intrinsics"]
            if names != batch["names"]:
                raise ValueError("Native batch name order mismatch")
            expected_k = original_k.copy()
            expected_k[:, 0, :] *= 840 / 1400
            expected_k[:, 1, :] *= 602 / 1013
            input_diff = max(float(np.max(np.abs(original_ext[i, :3, :3] - np.array(by_name[n]["R"])))) for i, n in enumerate(names))
            t_diff = max(float(np.max(np.abs(original_ext[i, :3, 3] - np.array(by_name[n]["t"])))) for i, n in enumerate(names))
            rank = inference["batch_rank_preflight"][str(batch_id)]
            singular = rank["singular_values"]
            row = {"region": region, "batch_id": batch_id, "names": names, "count": len(names),
                   "batch_npz_sha256": digest, "camera_center_rank": rank["rank"],
                   "camera_center_singular_values_m": singular,
                   "camera_center_s2_over_s1": singular[1] / singular[0],
                   "input_R_max_abs_difference": input_diff, "input_t_max_abs_difference": t_diff,
                   "returned_ext_max_abs_difference": float(np.max(np.abs(aligned_ext - original_ext[:, :3, :]))),
                   "processed_K_max_abs_difference_from_scaled_input": float(np.max(np.abs(output_k - expected_k))),
                   "processed_K": output_k.tolist(), "input_K": original_k.tolist(),
                   "umeyama_scale_retained": False, "pre_overwrite_predicted_poses_retained": False,
                   "native_ransac_enabled": False, "inference_receipt_sha256": sha(folder / "da3/inference_receipt.json")}
            by_batch[batch_id] = row
            batch_rows.append(row)
        region_rows = []
        for index, view in enumerate(train):
            stem = Path(view["name"]).stem
            prior_path, da3_path = folder / "prior/raw_depth" / (stem + ".npy"), folder / "da3/raw_depth" / (stem + ".npy")
            psha, dsha = sha(prior_path), sha(da3_path)
            if psha != prior_rows[view["name"]]["sha256"] or dsha != da3_rows[view["name"]]["files"][f"raw_depth/{stem}.npy"]["sha256"]:
                raise ValueError("Sealed map hash mismatch")
            p, d = np.load(prior_path), np.load(da3_path)
            if p.shape != d.shape or p.shape != (view["height"], view["width"]):
                raise ValueError("Sealed depth dimensions mismatch")
            bbox = roi.projected_prism_bbox(settings["domain"], view["R"], view["t"], view["K"], view["width"], view["height"])
            base = {"region": region, "image_id": view["image_id"], "name": view["name"],
                    "batch_id": da3_rows[view["name"]]["batch_id"], "bbox": bbox,
                    "height": view["height"], "width": view["width"]}
            for domain, box in [("full_frame", [0, 0, view["width"], view["height"]]), ("fixed_prism_projected_bbox", bbox)]:
                row = dict(base, domain=domain)
                row.update(domain_stats(p, d, box if box is not None else [0, 0, 0, 0]))
                all_rows.append(row)
                if domain == "fixed_prism_projected_bbox": region_rows.append(row)
            file_ledger.append(dict(region=region, name=view["name"], prior_sha256=psha, da3_sha256=dsha,
                                    prior_finite_positive_count=int((np.isfinite(p) & (p > 0)).sum()),
                                    da3_nonfinite_count=int((~np.isfinite(d)).sum()), da3_nonpositive_count=int((np.isfinite(d) & (d <= 0)).sum())))
            if index in [0, 1, 2] or index % 20 == 19:
                last = region_rows[-1]
                print(json.dumps({"region": region, "processed": index + 1, "name": view["name"], "ROI_common": last["common_valid"], "ROI_ratio": last["da3_over_prior_median"], "ROI_absdiff_m": last["absdiff_m_median"]}), flush=True)
        eligible = sorted([r for r in region_rows if r["common_valid"] > 0], key=lambda r: (r["absdiff_m_median"], r["name"]))
        selected = [("lex_first", region_rows[0])]
        if eligible:
            selected += [("median_ROI_discrepancy", eligible[len(eligible)//2]), ("maximum_ROI_discrepancy", eligible[-1])]
        for label, row in selected:
            view = by_name[row["name"]]
            stem = Path(view["name"]).stem
            p = np.load(folder / "prior/raw_depth" / (stem + ".npy"))
            d = np.load(folder / "da3/raw_depth" / (stem + ".npy"))
            # Read only selected training photographs from isolated train batch mounts.
            rgb_path = Path("/train_rgb") / region / f"batch_{row['batch_id']:03d}" / "images" / view["name"]
            target = out / f"{region}_{label}.png"
            figure(region, label, row, view, p, d, rgb_path, target)
            selections.append({"region": region, "selection": label, "image_name": view["name"],
                               "batch_id": row["batch_id"], "ROI_statistics": row,
                               "figure": target.name, "figure_sha256": sha(target), "rgb_sha256": sha(rgb_path)})
        metrics = ["prior_m_median", "da3_m_median", "da3_over_prior_median", "absdiff_m_median", "da3_minus_prior_m_median"]
        summary = {"train_views": len(train), "ROI_with_common_pixels": len(eligible),
                   "ROI_pixel_counts_sum": sum(r["pixels"] for r in region_rows),
                   "ROI_common_pixels_sum": sum(r["common_valid"] for r in region_rows),
                   "image_level_distributions": {key: describe(np.array([r[key] for r in eligible])) for key in metrics}}
        for bid, row in by_batch.items():
            rows = [r for r in eligible if r["batch_id"] == bid]
            row["ROI_image_level_distributions"] = {key: describe(np.array([r[key] for r in rows])) for key in metrics}
        summaries[region] = summary
        write(out / f"{region}_summary.json", summary)
        print(json.dumps({"region_complete": region, "summary": summary}), flush=True)
    write(out / "per_image_statistics.json", all_rows)
    with (out / "per_image_statistics.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0])); writer.writeheader(); writer.writerows(all_rows)
    write(out / "batch_context_trace.json", batch_rows)
    write(out / "selected_views.json", selections)
    write(out / "input_hash_ledger.json", file_ledger)
    receipt = {"status": "PASS_REFERENCE_FREE_SEALED_INPUT_DIAGNOSTIC", "scientific_verdict": None,
               "regions": summaries, "reference_accessed": False, "evaluation_rgb_accessed": False,
               "maps_recomputed": False, "training_settings_changed": False, "inputs_mounted_read_only": True,
               "wall_seconds": time.monotonic() - start,
               "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
               "outputs": {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.suffix in [".json", ".csv", ".png"]}}
    write(out / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "wall_seconds": receipt["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
