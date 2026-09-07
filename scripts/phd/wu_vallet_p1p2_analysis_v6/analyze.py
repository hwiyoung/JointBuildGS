"""Frozen P1/P2 update-quality diagnosis; UAS distances are evaluation only."""
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
    # The plot is a summary of frozen full-native statistics, not a new scoring domain.
    fig, axes = plt.subplots(2, 3, figsize=(15, 7), layout="constrained")
    names = ["ALS", "Image", "Union", "Wu"]
    colors = ["#ad7829", "#287eb8", "#82908e", "#24815b"]
    for i, row in enumerate(rows):
        scores = [v["coverage"]["fscore"][2] * 100 for v in row["methods"].values()]
        axes[i, 0].bar(names, scores, color=colors)
        axes[i, 0].set(ylim=(0, 105), ylabel="Distance F1 @ 0.5 m (%)", title=f"{row['id']} - full native points / same UAS")
        for x, value in enumerate(scores):
            axes[i, 0].text(x, value + 1, f"{value:.2f}", ha="center", fontsize=10)
        old, new = row["sources"]["old"], row["sources"]["new"]
        axes[i, 1].barh(["Before", "After"], [old["far_total"], old["retained_far"]], color=["#ad7829", "#24815b"])
        axes[i, 1].set(xlabel="Count of ALS points > 2 m from UAS", title=f"{row['id']} - remaining prior discrepancy")
        for y, value in enumerate([old["far_total"], old["retained_far"]]):
            axes[i, 1].text(value, y, f"  {value:,}", va="center", fontsize=10)
        axes[i, 1].set_xlim(0, old["far_total"] * 1.27)
        groups = old["groups"]
        labels = ["consistent", "raw_single", "filtered", "unassessed"]
        counts = [groups.get(label, {}).get("retained_far", 0) for label in labels]
        axes[i, 2].barh(labels, counts, color="#b66d52")
        for y, value in enumerate(counts):
            axes[i, 2].text(value, y, f"  {value:,}", va="center", fontsize=10)
        axes[i, 2].set_xlim(0, max(counts + [1]) * 1.3)
        axes[i, 2].set(xlabel="Retained ALS points > 2 m from UAS", title=f"{row['id']} - decision status of residuals")
        for ax in axes[i]:
            ax.grid(axis="y" if ax is axes[i, 0] else "x", alpha=.15)
    fig.suptitle("P1/P2 update-quality diagnosis | corrected area = 1 m² | UAS is evaluation only\nDistance groups are diagnostic, not annotated true/false changes", fontsize=12)
    fig.savefig(output / "p1p2_update_quality.png", dpi=180)
    fig.savefig(output / "p1p2_update_quality.pdf")
    plt.close(fig)
    assert all(sha(path) == expected for path, expected in bound.items())
    result = dict(status="P1_P2_FROZEN_UPDATE_QUALITY_ANALYSIS_COMPLETE", task_id=cfg["task_id"], scientific_verdict=None,
        new_update_runs=0, prior_completed_update_runs=["PHD-WU-VALLET-P1-UPDATE-v5", "PHD-WU-VALLET-P2-UPDATE-v5"],
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
