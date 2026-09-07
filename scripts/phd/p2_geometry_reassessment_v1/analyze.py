"""Audit frozen P2 distance arrays without changing geometry or recomputing distances."""
import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean(values):
    return float(np.mean(values)) if len(values) else None


def load(root, candidate, setting, receipts):
    source = root / candidate / (setting + ".npz")
    meta_path = source.with_suffix(".json")
    with np.load(source, allow_pickle=False) as arrays:
        data = {key: arrays[key] for key in (
            "prediction_surface_samples", "reference_points", "reference_original_indices",
            "prediction_to_reference_distance", "reference_to_triangle_distance")}
    meta = json.loads(meta_path.read_text())
    receipts.append({"path": str(source), "sha256": sha(source),
                     "metrics_path": str(meta_path), "metrics_sha256": sha(meta_path)})
    assert meta["scientific_verdict"] is None
    assert len(data["prediction_surface_samples"]) == meta["surface_samples"]
    assert len(data["reference_points"]) == meta["reference_points_after_voxel"]
    for key, values in data.items():
        assert np.isfinite(values).all(), (source, key)
    return data, meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    thresholds = cfg["thresholds_m"]
    heights = np.asarray(cfg["height_bin_edges_m"])
    tol = cfg["paired_distance_tolerance_m"]
    receipts, globals_, bins, pairs, height_pairs, areas, cells = [], [], [], [], [], [], []
    errors = []
    plots = {}
    for resolution, candidates in cfg["pairs"].items():
        for setting in cfg["settings"]:
            print("READ", resolution, setting, flush=True)
            loaded = [load(args.source, c, setting, receipts) for c in candidates]
            first, second = [item[0] for item in loaded]
            assert np.array_equal(first["reference_original_indices"], second["reference_original_indices"])
            assert np.array_equal(first["reference_points"], second["reference_points"])
            for candidate, (data, meta) in zip(candidates, loaded):
                forward = data["prediction_to_reference_distance"]
                reverse = data["reference_to_triangle_distance"]
                area = meta["surface_area_m2"]
                weight = area / len(forward)
                assert len(forward) > 0 and len(reverse) > 0
                for threshold in thresholds:
                    precision, recall = float(np.mean(forward < threshold)), float(np.mean(reverse < threshold))
                    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
                    original = next(r for r in meta["thresholds"] if r["threshold_m"] == threshold)
                    for metric, value in (("precision", precision), ("recall", recall), ("f1", f1)):
                        if abs(original[metric] - value) > 1e-12:
                            errors.append([candidate, setting, threshold, metric, original[metric], value])
                    globals_.append(dict(resolution=resolution, candidate=candidate, setting=setting,
                        threshold_m=threshold, precision=precision, recall=recall, f1=f1,
                        area_m2=area, near_observed_area_estimate_m2=float(np.sum(forward < threshold)*weight),
                        far_observed_area_estimate_m2=float(np.sum(forward >= threshold)*weight),
                        mean_prediction_to_reference_m=float(forward.mean()),
                        mean_reference_to_surface_m=float(reverse.mean())))
                for lower, upper in zip(heights[:-1], heights[1:]):
                    pm = (data["prediction_surface_samples"][:, 2] >= lower) & (data["prediction_surface_samples"][:, 2] < upper)
                    rm = (data["reference_points"][:, 2] >= lower) & (data["reference_points"][:, 2] < upper)
                    for threshold in thresholds:
                        bins.append(dict(resolution=resolution, candidate=candidate, setting=setting,
                            z_lower_m=int(lower), z_upper_m=int(upper), threshold_m=threshold,
                            prediction_samples=int(pm.sum()), prediction_area_estimate_m2=float(pm.sum()*weight),
                            reference_points=int(rm.sum()), reference_share=float(rm.mean()),
                            conditional_precision=mean(forward[pm] < threshold),
                            conditional_recall=mean(reverse[rm] < threshold),
                            mean_prediction_distance_m=mean(forward[pm]), mean_reference_distance_m=mean(reverse[rm]),
                            far_observed_area_estimate_m2=float(np.sum(pm & (forward >= threshold))*weight)))
                if setting == cfg["primary_setting"]:
                    edges = cfg["distance_bin_edges_m"] + [float("inf")]
                    for lo, hi in zip(edges[:-1], edges[1:]):
                        mask = (forward >= lo) & (forward < hi)
                        areas.append(dict(resolution=resolution, candidate=candidate, distance_lower_m=lo,
                            distance_upper_m=None if np.isinf(hi) else hi, sample_count=int(mask.sum()),
                            area_estimate_m2=float(mask.sum()*weight), fraction=float(mask.mean())))
            ref = first["reference_points"]
            d0, d1 = first["reference_to_triangle_distance"], second["reference_to_triangle_distance"]
            delta = d1 - d0
            for threshold in thresholds:
                gain = (d0 >= threshold) & (d1 < threshold)
                loss = (d0 < threshold) & (d1 >= threshold)
                pairs.append(dict(resolution=resolution, setting=setting, threshold_m=threshold,
                    n_reference=len(ref), gained_reference=int(gain.sum()), lost_reference=int(loss.sum()),
                    matched_both=int(np.sum((d0 < threshold) & (d1 < threshold))),
                    unmatched_both=int(np.sum((d0 >= threshold) & (d1 >= threshold))),
                    recall_change=float(gain.mean()-loss.mean()),
                    distance_improved=int(np.sum(delta < -tol)), distance_worsened=int(np.sum(delta > tol)),
                    distance_unchanged=int(np.sum(np.abs(delta) <= tol)), mean_distance_change_m=float(delta.mean())))
                for lower, upper in zip(heights[:-1], heights[1:]):
                    rm = (ref[:, 2] >= lower) & (ref[:, 2] < upper)
                    height_pairs.append(dict(resolution=resolution, setting=setting, threshold_m=threshold,
                        z_lower_m=int(lower), z_upper_m=int(upper), reference_points=int(rm.sum()),
                        gained_reference=int(np.sum(gain & rm)), lost_reference=int(np.sum(loss & rm)),
                        contribution_to_global_recall_change=float((np.sum(gain & rm)-np.sum(loss & rm))/len(ref)),
                        mean_distance_change_m=mean(delta[rm])))
                assert gain.sum()+loss.sum()+np.sum((d0<threshold)&(d1<threshold))+np.sum((d0>=threshold)&(d1>=threshold)) == len(ref)
            if setting != cfg["primary_setting"]:
                continue
            xy = np.floor((ref[:, :2]-np.asarray(cfg["xy_origin_m"]))/cfg["xy_cell_size_m"]).astype(int)
            unique, inverse = np.unique(xy, axis=0, return_inverse=True)
            count = np.bincount(inverse)
            cell_delta = np.bincount(inverse, weights=delta)/count
            for index, cell in enumerate(unique):
                selected = inverse == index
                cells.append(dict(resolution=resolution, cell_x=int(cell[0]), cell_y=int(cell[1]),
                    x_m=float(cell[0]*cfg["xy_cell_size_m"]), y_m=float(cell[1]*cfg["xy_cell_size_m"]),
                    reference_points=int(count[index]), mean_distance_change_m=float(cell_delta[index]),
                    mean_reference_height_m=float(ref[selected,2].mean()),
                    recall_native_05=float(np.mean(d0[selected]<0.5)), recall_reduced_05=float(np.mean(d1[selected]<0.5))))
            plots[resolution] = (unique, cell_delta)
    assert not errors, errors
    for name, rows in (("global_recomputed.csv",globals_), ("height_strata.csv",bins),
                       ("paired_reference.csv",pairs), ("paired_reference_height.csv",height_pairs),
                       ("prediction_distance_area.csv",areas), ("xy_cells.csv",cells)):
        write_csv(args.output/name,rows)

    fig, axes = plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
    for ax,(res,(coords,change)) in zip(axes,plots.items()):
        pos=(coords+.5)*cfg["xy_cell_size_m"]+np.asarray(cfg["xy_origin_m"])
        sc=ax.scatter(pos[:,0],pos[:,1],c=change,s=8,marker="s",cmap="RdBu_r",vmin=-1,vmax=1)
        ax.set(xlim=cfg["bounds_xyz_half_open"][0],ylim=cfg["bounds_xyz_half_open"][1],aspect="equal",
               xlabel="Local X (m)",ylabel="Local Y (m)",title=f"{res}: same observed UAS points")
    fig.colorbar(sc,ax=axes,label="Reduced prior minus native mean distance (m); blue improves, red worsens")
    fig.suptitle("P2: reference-to-surface change across the full prism\n0.5 m XY cells; mixed heights per cell; colors clipped at +/-1 m")
    fig.savefig(args.output/"xy_distance_change.png",dpi=170)
    plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(13,6),constrained_layout=True,sharey=True)
    for ax,res in zip(axes,cfg["pairs"]):
        rows=[r for r in height_pairs if r["resolution"]==res and r["setting"]==cfg["primary_setting"] and r["threshold_m"]==0.5]
        y=np.arange(len(rows))
        ax.barh(y,[r["gained_reference"] for r in rows],color="#287db4",label="Newly within 0.5 m")
        ax.barh(y,[-r["lost_reference"] for r in rows],color="#d66549",label="No longer within 0.5 m")
        ax.axvline(0,color="black",lw=.7)
        ax.set(yticks=y,yticklabels=[f"[{r['z_lower_m']}, {r['z_upper_m']})" for r in rows],
               xlabel="Same-reference point count (loss shown left)",title=f"{res}: recall gains and losses")
        ax.legend(loc="lower right",fontsize=8)
    axes[0].set_ylabel("Local Z band (m); geometric bins, not semantic classes")
    fig.suptitle("P2: where the global recall change comes from\nAll height bands included; fixed threshold from the original evaluation")
    fig.savefig(args.output/"recall_height_contributions.png",dpi=170)
    plt.close(fig)

    write_json(args.output/"receipt.json",dict(task_id=cfg["task_id"],scientific_verdict=None,
        status="PASS_DESCRIPTIVE_REANALYSIS",config_sha256=sha(args.config),script_sha256=sha(Path(__file__)),
        git_commit=args.git_commit,image_id=args.image_id,python=platform.python_version(),numpy=np.__version__,matplotlib=matplotlib.__version__,
        input_files=receipts,global_rows_reconciled=len(globals_),max_global_metric_difference_tolerance=1e-12,
        same_reference_coordinate_and_original_identity_checks="PASS",paired_partition_checks="PASS",
        methodology=cfg["interpretation"],models_retrained=0,scene_renders=0,meshes_extracted=0,new_distance_queries=0,
        inputs_unchanged=all(sha(Path(r["path"]))==r["sha256"] and sha(Path(r["metrics_path"]))==r["metrics_sha256"] for r in receipts)))
    print("PASS",len(globals_),"global rows reconciled; exact common reference identities verified",flush=True)


if __name__ == "__main__":
    main()
