"""Compare saved fixed-8000 reference proximity arrays; never reconstruct or score."""
import argparse
import csv
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
import sys
import time

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--helper", required=True, type=Path)
    args = parser.parse_args()
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    spec = importlib.util.spec_from_file_location("saved_support", args.helper)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    config = json.loads(args.config.read_text())
    if (config["regions"] != list(helper.REGIONS) or config["kinds"] != list(helper.KINDS)
            or tuple(config["thresholds_m"]) != helper.THRESHOLDS
            or config["optimizer_updates"] != 8000 or config["scientific_verdict"] is not None
            or config["primary_sampling"] != helper.PRIMARY):
        raise ValueError("Unexpected prefix comparison scope")
    task, out = args.task.resolve(strict=True), args.out.resolve(strict=True)
    if (out / "receipt.json").exists() or (out / "support_transitions.csv").exists():
        raise FileExistsError("Do not overwrite a previous comparison")
    receipt = dict(schema="GEOGS_PREFIX8000_SUPPORT_TRANSITIONS_v1", status="RUNNING",
        scientific_verdict=None, started_unix=time.time(), command=sys.argv,
        script_sha256=helper.sha(__file__), helper_sha256=helper.sha(args.helper),
        config_sha256=helper.sha(args.config), python_version=platform.python_version(),
        numpy_version=np.__version__, runtime_image=config["runtime_image"],
        optimizer_updates=8000, analysis_role="SUPPLEMENTARY_PREFIX_DIAGNOSTIC",
        main_experiment_replaced=False, geometry_recomputed=False, scores_recomputed=False,
        pure_anchor_only_ablation=False, image_only=False,
        historical_sfm_evaluation_image_influence_removed=False,
        full_30000_completion_inferred=False,
        alignment_or_resampling_performed=False, input_geometry_modified=False,
        threshold_operator="strictly_less_than", thresholds_m=helper.THRESHOLDS,
        interpretation=config["interpretation"], inputs=[], comparisons=[], outputs=[])
    bound = {}

    def bind(path):
        path = path.resolve(strict=True)
        relative = str(path.relative_to(task))
        record = dict(path=relative, bytes=path.stat().st_size, sha256=helper.sha(path))
        if relative in bound and bound[relative] != record:
            raise ValueError("Input changed during comparison")
        bound[relative] = record
        return record

    try:
        policy_path = task / "contracts/sfm_prefix8000_diagnostic_v1.json"
        if bind(policy_path)["sha256"] != config["prefix_policy_sha256"]:
            raise ValueError("Frozen prefix policy changed")
        policy = json.loads(policy_path.read_text())
        execution_path = task / "contracts/execution_v1.json"
        bind(execution_path)
        execution = json.loads(execution_path.read_text())
        all_rows = []
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for region in config["regions"]:
            summary_path = task / config["prefix_root"] / "summary" / region / "R8000/receipt.json"
            summary = json.loads(summary_path.read_text())
            if (summary["status"] != "PREFIX8000_COMPARISON_READY" or summary["region"] != region
                    or summary["optimizer_updates"] != 8000
                    or summary["experiment_source_relative"] != policy["selected_attempts"][region]
                    or summary["scientific_verdict"] is not None):
                raise ValueError("Exact completed regional prefix summary is required")
            bind(summary_path)
            figure, axes = plt.subplots(1, 2, figsize=(12, 6), constrained_layout=True)
            for axis, kind in zip(axes, config["kinds"]):
                old_id = config["baseline_condition"] + "." + kind
                new_id = config["new_condition"] + "." + kind
                old_path = task / config["baseline_root"] / region / old_id / (helper.PRIMARY + ".npz")
                new_path = task / config["prefix_root"] / "geometry" / region / new_id / (helper.PRIMARY + ".npz")
                old_metric = helper.inspect_metrics(old_path.with_suffix(".json"), region, old_id, execution)
                new_metric = helper.inspect_metrics(new_path.with_suffix(".json"), region, new_id, execution)
                for key in ("reference_sha256", "bounds_half_open", "reference_voxel_origin", "crs", "iteration"):
                    if old_metric[key] != new_metric[key]:
                        raise ValueError("Reference/domain/update mismatch: " + key)
                if (new_metric["iteration"] != 8000
                        or new_metric["new_condition_seal_sha256"] != summary["new_condition_seal_sha256"]):
                    raise ValueError("Array metrics select another checkpoint/seal")
                source_records = [bind(path) for path in (old_path, old_path.with_suffix(".json"), new_path, new_path.with_suffix(".json"))]
                old, new = helper.load_arrays(old_path), helper.load_arrays(new_path)
                codes, rows = helper.compare_arrays(old, new)
                helper.check_recall(rows, old_metric, "baseline_recall")
                helper.check_recall(rows, new_metric, "new_recall")
                filename = region + ".anchor8000_to_sfm8000." + kind + ".npz"
                with (out / filename).open("xb") as stream:
                    np.savez_compressed(stream, reference_original_indices=old["reference_original_indices"],
                        reference_points=old["reference_points"],
                        baseline_reference_to_triangle_distance=old["reference_to_triangle_distance"],
                        new_reference_to_triangle_distance=new["reference_to_triangle_distance"],
                        thresholds_m=np.asarray(helper.THRESHOLDS), status_codes=codes,
                        status_code_names=np.asarray(helper.STATES), evaluation_only=np.asarray(True))
                identity = dict(region=region, kind=kind, baseline_candidate=old_id, new_candidate=new_id,
                    baseline_optimizer_updates=8000, new_optimizer_updates=8000,
                    execution_attempt_id=policy["selected_attempts"][region], transition_array=filename)
                all_rows.extend(dict(identity, **row) for row in rows)
                receipt["comparisons"].append(dict(identity, inputs=source_records,
                    original_indices_and_reference_xyz_byte_equal=True,
                    original_reference_count=len(old["reference_points"]),
                    original_reference_array_sha256={k: hashlib.sha256(old[k].tobytes(order="C")).hexdigest()
                        for k in ("reference_original_indices", "reference_points")},
                    saved_recall_crosscheck_passed=True))
                receipt["outputs"].append(dict(path=filename, bytes=(out / filename).stat().st_size, sha256=helper.sha(out / filename)))
                selected = codes[helper.THRESHOLDS.index(config["figure_threshold_m"])]
                xyz = old["reference_points"]
                for code, color in ((3, "#bdbdbd"), (0, "#4477aa"), (1, "#228833"), (2, "#cc3311")):
                    mask = selected == code
                    axis.scatter(xyz[mask, 0], xyz[mask, 1], s=1, c=color,
                        label=helper.STATES[code] + ": " + str(int(mask.sum())), rasterized=True, linewidths=0)
                bounds = old_metric["bounds_half_open"]
                axis.set(xlim=tuple(bounds[0]), ylim=tuple(bounds[1]),
                    xlabel="Scene X (m)", ylabel="Scene Y (m)", title=kind + " triangle surface")
                axis.set_aspect("equal", adjustable="box")
                axis.legend(loc="upper left", fontsize=7, markerscale=4)
                del old, new, codes
            figure.suptitle(region + " | Anchor8000 to SfM8000 | distance < 0.5 m\n"
                "Observed reference proximity only; vertically overlapping points may overlap in XY")
            png = out / (region + ".transitions_0.5m.png")
            figure.savefig(png, dpi=160)
            plt.close(figure)
            receipt["outputs"].append(dict(path=png.name, bytes=png.stat().st_size, sha256=helper.sha(png)))
        if len(all_rows) != 36 or len(receipt["comparisons"]) != 6:
            raise RuntimeError("Incomplete 3-region/raw-post/six-threshold comparison")
        csv_path = out / "support_transitions.csv"
        with csv_path.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
            writer.writeheader()
            writer.writerows(all_rows)
        receipt["outputs"].append(dict(path=csv_path.name, bytes=csv_path.stat().st_size, sha256=helper.sha(csv_path)))
        for relative, record in list(bound.items()):
            if bind(task / relative) != record:
                raise ValueError("Source changed during comparison")
        receipt.update(status="PASS_REFERENCE_PROXIMITY_TRANSITIONS", threshold_rows=36,
            comparison_count=6, input_sources_unchanged=True)
    except Exception as error:
        receipt.update(status="FAIL_REFERENCE_PROXIMITY_TRANSITIONS", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt.update(completed_unix=time.time(), inputs=list(bound.values()))
        helper.write_json(out / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "comparison_count", "threshold_rows", "scientific_verdict")}))


if __name__ == "__main__":
    main()
