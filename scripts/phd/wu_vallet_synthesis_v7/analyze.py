"""Frozen P1/P2/P3 update-quality synthesis; UAS distances are evaluation only."""
import csv
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fraction(n, d):
    return float(n / d) if d else None


def main(config, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    cfg = json.loads(config.read_text())
    root = Path(cfg["artifact_root"])
    output.mkdir(parents=True, exist_ok=False)
    rows, bound = [], {}
    for region in cfg["regions"]:
        paths = {key: root / row["path"] for key, row in region["inputs"].items()}
        for key, path in paths.items():
            if sha(path) != region["inputs"][key]["sha256"]:
                raise ValueError(f"Changed frozen input: {region['id']}/{key}")
            bound[str(path)] = sha(path)
        evaluation = json.loads(paths["evaluation"].read_text())
        receipt = json.loads(paths["update"].read_text())
        assert receipt["reference_accessed"] is False and receipt["scientific_verdict"] is None
        assert sha(paths["common"]) == receipt["outputs"]["common.npz"]
        arm = next(row for row in receipt["arms"] if row["name"] == cfg["primary_arm"])
        assert sha(paths["points"]) == arm["outputs"]["updated_points.npz"]
        assert sha(paths["distances"]) == evaluation["outputs"]["source_distances.npz"]
        with np.load(paths["points"]) as points, np.load(paths["common"]) as common, np.load(paths["distances"]) as distances:
            assert np.array_equal(np.r_[common["old_xyz"][points["old_keep_mask"]], common["new_xyz"][points["new_keep_mask"]]], points["updated_points"])
            source_rows = {}
            for side in ("old", "new"):
                keep = points[f"{side}_keep_mask"]
                status = points[f"{side}_vertex_status"]
                distance = distances[f"{side}_reference_distance_m"]
                assert len(keep) == len(status) == len(distance) == len(common[f"{side}_xyz"])
                assert np.isfinite(distance).all()
                near = distance <= cfg["near_threshold_m"]
                far = distance > cfg["far_threshold_m"]
                groups = {}
                for label in np.unique(status):
                    mask = status == label
                    groups[str(label)] = dict(total=int(mask.sum()), retained=int((mask & keep).sum()),
                        retained_far=int((mask & keep & far).sum()), retained_near=int((mask & keep & near).sum()),
                        removed_far=int((mask & ~keep & far).sum()), removed_near=int((mask & ~keep & near).sum()))
                source_rows[side] = dict(total=len(keep), retained=int(keep.sum()), removed=int((~keep).sum()),
                    near_total=int(near.sum()), far_total=int(far.sum()), retained_near=int((keep & near).sum()),
                    retained_far=int((keep & far).sum()), removed_near=int((~keep & near).sum()), removed_far=int((~keep & far).sum()),
                    fraction_far_removed=fraction((~keep & far).sum(), far.sum()),
                    fraction_retained_far=fraction((keep & far).sum(), keep.sum()),
                    fraction_retained_near=fraction((keep & near).sum(), keep.sum()),
                    retained_distance_sum_m=float(distance[keep].sum()), groups=groups)
                expected = evaluation["source_groups"][cfg["primary_evaluation_method"]]["old_kept" if side == "old" else "new_admitted"]
                assert source_rows[side]["retained"] == expected["point_count"]
                assert source_rows[side]["retained_far"] == expected["reference_distance_over_2m"]
            sum_distance = sum(row["retained_distance_sum_m"] for row in source_rows.values())
            for row in source_rows.values():
                row["share_of_output_distance_sum"] = fraction(row["retained_distance_sum_m"], sum_distance)
        methods = {key: evaluation["methods"][key] for key in ("ALS_before", "Image_before", "Naive_union", "Wu_area1")}
        assert all(method["coverage"]["thresholds_m"][2] == cfg["near_threshold_m"] for method in methods.values())
        assert np.isclose(sum_distance, methods["Wu_area1"]["to_reference"]["mean_m"] * methods["Wu_area1"]["point_count"])
        rows.append(dict(id=region["id"], sources=source_rows, methods=methods,
            all_area_methods={key: value for key, value in evaluation["methods"].items() if key.startswith("Wu_")},
            reference_points=evaluation["reference_points"], update_elapsed_seconds=receipt["elapsed_seconds"]))
    # Recompute precision/recall/F1 from frozen integer numerators, every threshold.
    for row in rows:
        for method in list(row["methods"].values()) + list(row["all_area_methods"].values()):
            c = method["coverage"]
            p = np.array(c["precision_numerators"]) / c["prediction_denominator"]
            r = np.array(c["recall_numerators"]) / c["reference_denominator"]
            f = np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p+r)>0)
            assert np.allclose(p, c["precision"], rtol=0, atol=1e-12)
            assert np.allclose(r, c["recall"], rtol=0, atol=1e-12)
            assert np.allclose(f, c["fscore"], rtol=0, atol=1e-12)
    methods = ["ALS_before", "Image_before", "Naive_union", "Wu_area1"]
    labels = ["ALS", "Image", "Union", "Wu (1 m²)"]
    colors = ["#ad7829", "#287eb8", "#82908e", "#24815b"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    for i, row in enumerate(rows):
        scores = [row["methods"][m]["coverage"]["fscore"][2] * 100 for m in methods]
        axes[0, i].bar(labels, scores, color=colors)
        axes[0, i].set(ylim=(0, 106), ylabel="Distance F1 @ 0.5 m (%)", title=row["id"])
        for x, val in enumerate(scores):
            axes[0, i].text(x, val+1, f"{val:.2f}", ha="center", fontsize=10)
        x = np.arange(len(methods))
        for offset, direction, color, label in [(-.18,"to_reference","#956238","Output → UAS"),(.18,"reference_to","#287eb8","UAS → output")]:
            values = [row["methods"][m][direction]["mean_m"] for m in methods]
            axes[1, i].bar(x+offset, values, width=.36, color=color, label=label)
            for at,val in zip(x+offset,values):
                axes[1, i].text(at,val+.025,f"{val:.3f}",ha="center",fontsize=8,rotation=90)
        axes[1, i].set(xticks=x,xticklabels=labels,ylim=(0,2.05),ylabel="Mean nearest-point distance (m)")
        axes[1, i].legend(fontsize=9)
        for ax in axes[:,i]: ax.grid(axis="y",alpha=.15)
    fig.suptitle("P1 / P2 / P3: frozen matched-v5 results, same UAS evaluation protocol\nPaper-based reimplementation; distance F1 is not change-detection F1", fontsize=13)
    fig.savefig(output / "three_region_summary.png", dpi=180)
    fig.savefig(output / "three_region_summary.pdf")
    plt.close(fig)
    fields=["region","method","points","precision_0_5_pct","recall_0_5_pct","f1_0_5_pct","mean_output_to_uas_m","mean_uas_to_output_m","missed_reference_xy_cells"]
    with (output / "metrics.csv").open("x",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for row in rows:
            for name,m in {**row["methods"],**row["all_area_methods"]}.items():
                c=m["coverage"]
                writer.writerow(dict(region=row["id"],method=name,points=m["point_count"],precision_0_5_pct=c["precision"][2]*100,recall_0_5_pct=c["recall"][2]*100,f1_0_5_pct=c["fscore"][2]*100,mean_output_to_uas_m=m["to_reference"]["mean_m"],mean_uas_to_output_m=m["reference_to"]["mean_m"],missed_reference_xy_cells=m["xy_cells"]["missed_reference_cells"]))
    assert all(sha(path) == expected for path, expected in bound.items())
    result = dict(status="THREE_REGION_FROZEN_UPDATE_QUALITY_SYNTHESIS_COMPLETE", task_id=cfg["task_id"], scientific_verdict=None,
        new_update_runs=0, prior_completed_update_runs=[f"PHD-WU-VALLET-{r['id']}-UPDATE-v5" for r in rows],
        candidate_outputs_modified=False, existing_evaluation_modified=False, raw_reference_read=False,
        interpretation="Posthoc diagnosis of fixed matched-v5 outputs. UAS-derived distances are evaluation-only. No semantic or change ground-truth labels; no method/parameter selection by these diagnostics.",
        config_sha256=sha(config), implementation_sha256=sha(__file__), input_hashes=bound,
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
        container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"), regions=rows,
        versions=dict(numpy=np.__version__, matplotlib=matplotlib.__version__),
        outputs={p.name:sha(p) for p in output.iterdir() if p.is_file()})
    (output / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(dict(status=result["status"],regions=[dict(id=row["id"],sources=row["sources"]) for row in rows])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.config, args.output)
