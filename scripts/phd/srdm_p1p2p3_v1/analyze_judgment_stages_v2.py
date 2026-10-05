"""Read frozen SRDM stages; audit the previously recorded P1/P2/P3 surfaces.

No matching, training, parameter changes, or new source decisions are performed.
Run in the recorded Docker image with inputs mounted read-only.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def summary(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    return {"n": int(len(values)), "median": float(np.median(values)) if len(values) else None,
            "p10": float(np.percentile(values, 10)) if len(values) else None,
            "p90": float(np.percentile(values, 90)) if len(values) else None}


def counts(mask, decision):
    seed = decision["als_projection_state"] == 3
    keep, reject = decision["keep"] & mask, decision["rejected"] & mask
    return {"total": int(mask.sum()), "seed": int((mask & seed).sum()),
            "keep": int(keep.sum()), "reject": int(reject.sum()),
            "seed_untestable": int((mask & seed & decision["unassessed"]).sum()),
            "not_seed": int((mask & ~seed).sum()),
            "testable_fraction": float((keep | reject).sum() / mask.sum()) if mask.any() else None,
            "reject_fraction_of_testable": float(reject.sum() / (keep | reject).sum()) if (keep | reject).any() else None}


def region(root, task, out, rid, config):
    paths = {}
    def remember(name, path):
        paths[name] = {"path": str(path), "sha256": digest(path)}
        return path
    pair = load(remember("pair", task / "run" / rid / "pair.npz"))
    decision = load(remember("decision", task / "run" / rid / "decision.npz"))
    old_eval = load(remember("als_reference", task / "evaluation" / rid / "als_decision_reference.npz"))
    native = load(remember("native_sources", root / config["native_relative"] / rid / "native.npz"))
    suffix = "" if rid == "P1" else "-" + rid
    pairing = root / "phase-payloads/phd/patch_pairing_xy_v1" / ("PHD-PATCH-PAIRING-XY" + suffix + "-v1")
    patch = root / "phase-payloads/phd/surface_patch_rg_v1" / ("PHD-SURFACE-PATCH-RG" + suffix + "-v1")
    cells = np.load(remember("cells", pairing / "pair_cells.npy"), allow_pickle=False)
    patch_rows = np.load(remember("patch_rows", patch / "point_rows_als.npy"), allow_pickle=False)
    patch_labels = np.load(remember("patch_labels", patch / "points_als.npy"), allow_pickle=False)
    assert np.array_equal(native["als_tile_rows"], patch_rows)
    lookup = {(int(f), int(r)): i for i, (f, r) in enumerate(zip(decision["source_file_index"], decision["source_row"]))}
    assert len(lookup) == len(decision["source_row"])
    ids = np.array([lookup[(int(f), int(r))] for f, r in zip(native["als_original_file_index"], native["als_original_row"])])
    assert len(np.unique(ids)) == len(ids)
    assert np.allclose(native["als_xyz"], decision["als_xyz"][ids], rtol=0, atol=1e-4)
    assert old_eval["in_roi"][ids].all() and len(ids) == int(old_eval["in_roi"].sum())
    top = cells["layer"] == 0
    expected = config["regions"][rid]
    if rid in ("P1", "P2"):
        target_cells = top & (cells["state"] == 2) & (cells["rough"] == 0)
    else:
        target_cells = top & (cells["mvs_z"] > -30) & (cells["als_patch"] > 0)
    assert int(target_cells.sum()) == expected["legacy_target_cells"]
    target_lookup = {(int(c["ix"]), int(c["iy"]), int(c["als_patch"])) for c in cells[target_cells]}
    ij = np.floor((native["als_xyz"][:, :2].astype(float) - pair["bbox_min"][:2]) / config["cell_m"]).astype(int)
    local_target = np.array([(int(i), int(j), int(p)) in target_lookup for (i, j), p in zip(ij, patch_labels["patch_id"])])
    target = np.zeros(len(decision["als_xyz"]), bool)
    target[ids[local_target]] = True
    states = np.zeros(len(target), np.uint8)
    states[decision["keep"]] = 1
    states[decision["rejected"]] = 2
    states[decision["unassessed"] & (decision["als_projection_state"] == 3)] = 3
    roi = old_eval["in_roi"]
    assert all(int(counts(m, decision)["total"]) == sum(counts(m, decision)[k] for k in ("keep", "reject", "seed_untestable", "not_seed")) for m in (roi, target))

    # Decode the already saved weak disparity. This is geometry read-out only.
    rectified = cv2.reprojectImageTo3D(decision["weak_disparity"].astype(np.float32), pair["Q"]).astype(np.float64)
    camera = rectified @ pair["R1"]
    world = (camera - pair["world_to_left_t"]) @ pair["world_to_left_R"]
    finite = np.isfinite(world).all(axis=2) & (camera[:, :, 2] > 0)
    valid = decision["weak_valid"] & pair["left_valid_mask"] & finite
    inside = np.all((world >= pair["bbox_min"]) & (world < pair["bbox_max"]), axis=2)
    weak = world[valid & inside]
    reference_path = root / expected["reference_relative"]
    ref = load(remember("reference", reference_path))["uas_xyz"].astype(np.float64)
    ref = ref[np.all((ref >= pair["bbox_min"]) & (ref < pair["bbox_max"]), axis=1)]
    tree = cKDTree(ref)
    weak_distance = tree.query(weak, workers=2)[0]
    prior_indices = pair["sparse_source_index"]
    present = prior_indices >= 0
    weak_at_source = np.full((len(target), 3), np.nan)
    weak_at_source[prior_indices[present]] = world[present]
    testable = (decision["keep"] | decision["rejected"])
    assert np.isfinite(weak_at_source[testable]).all()
    weak_source_distance = np.full(len(target), np.nan)
    weak_source_distance[testable] = tree.query(weak_at_source[testable], workers=2)[0]

    result = {"region": rid, "expected_source": expected["source"], "scientific_verdict": None,
              "inputs": paths, "checks": {"original_source_ids_unique": True, "native_patch_rows_equal": True,
              "source_coordinates_match": True, "legacy_target_cell_count_matches": True, "partition_counts_match": True},
              "legacy_target_cells": int(target_cells.sum()), "roi_counts": counts(roi, decision),
              "target_counts": counts(target, decision),
              "weak_stage": {"roi_projection_pixels": int(pair["roi_mask"].sum()),
                             "lr_valid_fraction_in_roi_projection": float(decision["weak_valid"][pair["roi_mask"]].mean()),
                             "decoded_points_in_roi": len(weak), "distance_to_reference_m": summary(weak_distance)},
              "source_discrepancy": {}}
    for scope, selection in (("roi", roi), ("target_surface", target)):
        result["source_discrepancy"][scope] = {}
        for label, group in (("keep", decision["keep"]), ("reject", decision["rejected"]), ("unassessed", decision["unassessed"])):
            pick = selection & group
            assessed = pick & testable
            original = old_eval["distance_to_reference"][pick]
            delta = weak_source_distance[assessed] - old_eval["distance_to_reference"][assessed]
            result["source_discrepancy"][scope][label] = {
                "als_to_reference_m": summary(original), "weak_same_seed_ray_to_reference_m": summary(weak_source_distance[assessed]),
                "weak_minus_als_reference_distance_m": summary(delta),
                "weak_closer_fraction": float((delta < 0).mean()) if len(delta) else None,
                "absolute_disparity_difference_px": summary(np.abs(decision["disparity_difference"][assessed]))}

    # Save exact membership and paired diagnostic values, not a new decision.
    np.savez_compressed(out / (rid + "_membership.npz"), source_file_index=decision["source_file_index"],
        source_row=decision["source_row"], in_roi=roi, legacy_target_surface=target, decision_state=states,
        weak_same_seed_xyz=weak_at_source, weak_reference_distance=weak_source_distance,
        als_reference_distance=old_eval["distance_to_reference"])
    axis_fixed, value = expected["section"]
    horizontal = 1 - axis_fixed
    band = config["section_half_width_m"]
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.5), sharex=True, sharey=True)
    def scatter(ax, points, color, label, size=2, alpha=.7):
        chosen = points[np.abs(points[:, axis_fixed] - value) <= band]
        chosen = chosen[::max(1, int(np.ceil(len(chosen) / 40000)))]
        ax.scatter(chosen[:, horizontal], chosen[:, 2], s=size, c=color, label=label, alpha=alpha, linewidths=0)
    for ax in axes:
        scatter(ax, ref, "#333333", "Current UAS (evaluation only)", 1, .35)
        ax.set(xlim=(pair["bbox_min"][horizontal], pair["bbox_max"][horizontal]), ylim=(pair["bbox_min"][2], pair["bbox_max"][2]),
               xlabel=("Y" if horizontal else "X") + " (scene-local m)")
        ax.grid(alpha=.15)
    scatter(axes[0], native["als_xyz"], "#db8700", "ALS input", 4)
    scatter(axes[0], native["mvs_xyz"], "#1670cc", "Existing MVS (context)", 2)
    scatter(axes[0], weak, "#b434c6", "Saved SRDM weak stereo", 2)
    axes[0].set_title("1. Geometry used for judgment")
    for state, color, label in ((0, "#a6a6a6", "Not a seed"), (3, "#d5a018", "Seed: untestable"), (2, "#d73027", "ALS rejected"), (1, "#159457", "ALS kept")):
        scatter(axes[1], decision["als_xyz"][roi & (states == state)], color, label, 4)
    axes[1].set_title("2. Saved ALS judgment (before reconstruction)")
    for arm, color, label in (("SRDM_FILTER_OFF", "#db8700", "All seed ALS"), ("SRDM_NATIVE", "#1670cc", "Kept seed ALS only")):
        arm_path = task / "run" / rid / arm / "result.npz"
        cloud = load(remember(arm, arm_path))
        scatter(axes[2], cloud["xyz"][cloud["in_roi"]], color, label, 2)
    axes[2].set_title("3. Previously computed downstream reconstruction")
    axes[0].set_ylabel("Z (scene-local m)")
    for ax in axes:
        ax.legend(fontsize=7, loc="best")
    fig.suptitle(f"{rid}: expected {expected['source']} use | fixed {'X' if axis_fixed == 0 else 'Y'}={value:g} m, half-width {band:g} m", fontsize=12)
    fig.tight_layout()
    fig.savefig(out / (rid + "_stages.png"), dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    colors = {0: "#a6a6a6", 1: "#159457", 2: "#d73027", 3: "#d5a018"}
    labels = {0: "Not a seed", 1: "ALS kept", 2: "ALS rejected", 3: "Seed: untestable"}
    axes[0].imshow(pair["left_rgb"])
    axes[0].set_title("Actual SRDM input + target ALS judgments")
    for state in (0, 3, 2, 1):
        use = target & (states == state)
        uv = decision["pixel_xy"][use]
        xy = decision["als_xyz"][use]
        axes[0].scatter(uv[:, 0], uv[:, 1], c=colors[state], s=3, linewidths=0)
        axes[1].scatter(xy[:, 0], xy[:, 1], c=colors[state], s=3, linewidths=0, label=f"{labels[state]}: {use.sum():,}")
    axes[0].set(xlim=(0, pair["left_rgb"].shape[1]), ylim=(pair["left_rgb"].shape[0], 0))
    axes[0].axis("off")
    axes[1].set(xlabel="Local X (m)", ylabel="Local Y (m)", title="Previously defined target surface only", aspect="equal")
    axes[1].legend(fontsize=8)
    fig.suptitle(f"{rid}: {target.sum():,} original ALS points in {target_cells.sum():,} legacy target cells\nProjection is a location overlay, not proof of visibility", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / (rid + "_target_decisions.png"), dpi=160)
    plt.close(fig)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.monotonic()
    config = json.loads(Path(args.config).read_text())
    root, out = Path(args.artifact_root), Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    task = root / config["task_relative"]
    result = {"task_id": config["task_id"], "scientific_verdict": None,
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "matching_runs": 0, "training_runs": 0, "new_source_decisions": False,
              "config_sha256": digest(args.config), "script_sha256": digest(__file__),
              "evaluation_limit": config["evaluation_limit"], "regions": {}}
    for rid in config["regions"]:
        data = region(root, task, out, rid, config)
        result["regions"][rid] = data
        print(json.dumps({"region": rid, "target_counts": data["target_counts"], "weak_stage": data["weak_stage"],
                          "target_diagnostics": data["source_discrepancy"]["target_surface"]}), flush=True)
    result["elapsed_seconds"] = time.monotonic() - started
    result["output_hashes"] = {p.name: digest(p) for p in sorted(out.iterdir())}
    with (out / "stage_audit.json").open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
