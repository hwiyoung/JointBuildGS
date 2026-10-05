"""Snapshot and compare frozen G / main-v2 LC refinement traces without GT.

Only exact iteration intersections in 8001..30000 are paired. Camera identities
are retained; a same-iteration pair is not assumed to be a same-camera pair.
Every invocation creates a new immutable output directory, including input byte
snapshots so an in-progress report remains reproducible after training advances.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path


REPORT_REVISION = "v2.1_checkpoint_cost_scope"
REPORT_CHANGE_RECORD = {
    "revision": REPORT_REVISION,
    "date": "2026-09-10",
    "preceding_report_code_sha256": "96e6d0a0ac84837325d1b9b7a0017a757685b9885167fdfe0bba96c2ef3ca3de",
    "preceding_report_preserved": "main_v2/trace_monitor/attempt_20260910T141447Z",
    "reason": "Early process-cumulative RSS differences may reflect unequal Anchor/checkpoint capture histories.",
    "changes": ["Record declared, active and receipt-observed complete checkpoint capture iterations and training start.",
                "Flag mismatched capture schedules in JSON, CSV and resource plot captions.",
                "Retain cumulative peaks without subtraction; do not infer pure refinement memory savings.",
                "Explain that all nine chart panels are ordered-iteration process diagnostics."],
    "runtime_source_config_modified": False,
    "scientific_verdict": None,
}


LIMITATIONS = [
    "Trace losses are sampled training-camera objectives, not geometric accuracy, correction, damage, currentness or held-out appearance metrics.",
    "Exact iteration alignment does not imply the same sampled camera; camera identities and same-camera-only deltas are retained separately.",
    "Baseline controller phase was not recorded in jbgs_trace; lambda_V alone does not identify phase. Missing phase remains null.",
    "The comparison includes local weighting and the native controller response. No controller replay or mean-multiplier-matched global comparator was run.",
    "One run per condition cannot establish small-difference reproducibility, isolated spatial-allocation effects or population generalization.",
    "Prior/DA3 disagreement and attenuation multipliers do not identify the correct source. Spatial correction and damage require the separate evaluation artifacts.",
    "Trace means are unweighted means over observed camera/iteration samples, not pixel-pooled, building-balanced, camera-complete or time-integrated estimates.",
    "CUDA/RSS peaks are process-cumulative observations; GPU monitor memory includes other processes. Driver wall time includes preparation and serialization.",
    "G and LC can have different complete checkpoint capture schedules. Earlier Anchor/8100 serialization may raise cumulative RSS or wall time without indicating a local-loss memory benefit.",
    "Subtracting a cumulative peak cannot recover a pure refinement peak. No such subtraction is performed. Subtracting the iteration8000 elapsed prefix is a wall-time approximation and still leaves same-iteration8000 checkpoint serialization in the remainder.",
    "Baseline invocation/receipt hashes are checked against the reuse binding; trace bytes are separately snapshotted and hashed at report time.",
]
METRICS = ("rgb_loss", "raw_prior_loss", "raw_visual_loss", "lambda_prior", "lambda_visual",
           "gaussians", "protected", "elapsed_seconds", "peak_cuda_allocated_bytes",
           "peak_cuda_reserved_bytes", "peak_rss_bytes")
LOCAL_FIELDS = ("weighted_prior_loss", "weighted_visual_loss", "weighted_depth_total",
                "prior_valid", "visual_valid", "both_valid", "prior_only", "visual_only",
                "neither_valid", "a_mean_both", "a_zero_both", "a_one_both",
                "prior_multiplier_mean_valid", "visual_multiplier_mean_valid",
                "prior_effective_global_coefficient", "visual_effective_global_coefficient",
                "prior_denominator", "visual_denominator")


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write("\n")


def json_document(data):
    return json.loads(data.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON constant: " + value)))


def parse_trace(data):
    """Accept an incomplete final write only; reject corruption or duplicates."""
    rows, ignored = [], 0
    lines = data.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row = json_document(line)
        except (ValueError, UnicodeDecodeError):
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                ignored = len(line)
                break
            raise
        iteration = row.get("iteration")
        if not isinstance(iteration, int) or isinstance(iteration, bool) or iteration < 0:
            raise ValueError("Invalid trace iteration")
        if rows and iteration <= rows[-1]["iteration"]:
            raise ValueError("Trace iterations must be strictly increasing and unique")
        if not isinstance(row.get("camera"), str) or not row["camera"]:
            raise ValueError("Trace camera identity is required")
        rows.append(row)
    return rows, ignored


def finite(value, name, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Nonfinite or absent numerical trace field: " + name)
    return value


def native_row(row):
    out = {key: row[key] for key in ("iteration", "camera")}
    aliases = {"raw_prior_loss": "lod_loss", "raw_visual_loss": "da_loss",
               "lambda_prior": "lod_weight", "lambda_visual": "da_weight"}
    for key in METRICS:
        out[key] = finite(row.get(aliases.get(key, key)), key)
    out["controller_phase"] = None
    return out


def validate_local(row, cfg_hash, binding_hash, tau0, tau1, lambda_prior):
    if row.get("schema") != "JBGS_LOCAL_COMPLEMENTARY_TRACE_v2":
        raise ValueError("LC trace does not use the frozen v2 schema")
    if row.get("config_sha256") != cfg_hash or row.get("input_binding_sha256") != binding_hash:
        raise ValueError("LC trace configuration or input binding differs")
    if (row.get("tau0"), row.get("tau1"), row.get("lambda_prior")) != (tau0, tau1, lambda_prior):
        raise ValueError("LC realized thresholds or prior coefficient differ")
    for key in LOCAL_FIELDS:
        finite(row.get(key), key, optional=key.endswith("_mean_both") or "multiplier_mean" in key or "effective_global" in key)
    for source in ("prior", "visual"):
        raw = finite(row.get("raw_" + source + "_loss"), "raw loss")
        weighted = row["weighted_" + source + "_loss"]
        if weighted < 0 or weighted > raw + max(1e-5, abs(raw) * 1e-5):
            raise ValueError("LC loss is outside finite attenuation bounds")
    if row["prior_valid"] != row["both_valid"] + row["prior_only"] or row["visual_valid"] != row["both_valid"] + row["visual_only"]:
        raise ValueError("LC valid-source partition counts disagree")
    expected_total = row["lambda_prior"] * row["weighted_prior_loss"] + row["lambda_visual"] * row["weighted_visual_loss"]
    if not math.isclose(row["weighted_depth_total"], expected_total, rel_tol=1e-6, abs_tol=1e-7):
        raise ValueError("LC weighted objective total disagrees with realized coefficients")


def pair_trajectories(baseline_rows, lc_native_rows, lc_local_rows, *, cfg_hash,
                      binding_hash, tau0, tau1, lambda_prior, start=8001, end=30000):
    baseline = {r["iteration"]: native_row(r) for r in baseline_rows if start <= r["iteration"] <= end}
    lc = {r["iteration"]: native_row(r) for r in lc_native_rows if start <= r["iteration"] <= end}
    local = {}
    for row in lc_local_rows:
        if start <= row["iteration"] <= end:
            validate_local(row, cfg_hash, binding_hash, tau0, tau1, lambda_prior)
            local[row["iteration"]] = row
    for iteration in set(lc) & set(local):
        if lc[iteration]["camera"] != local[iteration]["camera"]:
            raise ValueError("LC native/local trace camera differs at the same iteration")
        for key in ("raw_prior_loss", "raw_visual_loss", "lambda_prior", "lambda_visual", "rgb_loss"):
            if lc[iteration][key] != local[iteration][key]:
                raise ValueError("LC native/local objective values disagree: " + key)
        phase = local[iteration].get("controller_state")
        lc[iteration]["controller_phase"] = phase.get("phase") if isinstance(phase, dict) else None
    paired = []
    for iteration in sorted(set(baseline) & set(lc) & set(local)):
        g, new, weights = baseline[iteration], lc[iteration], local[iteration]
        row = dict(iteration=iteration, camera_G=g["camera"], camera_LC=new["camera"],
                   same_camera=g["camera"] == new["camera"], controller_phase_G=None,
                   controller_phase_LC=new["controller_phase"],
                   config_sha256=cfg_hash, input_binding_sha256=binding_hash)
        for key in METRICS:
            row[key + "_G"], row[key + "_LC"] = g[key], new[key]
            row[key + "_delta_LC_minus_G"] = new[key] - g[key]
        for key in LOCAL_FIELDS:
            row[key + "_LC"] = weights[key]
        row["lambda_visual_equal"] = g["lambda_visual"] == new["lambda_visual"]
        row["lc_objective_gaussians_before_backward"] = weights.get("gaussians")
        row["lc_objective_protected_before_backward"] = weights.get("protected")
        paired.append(row)
    coverage = dict(baseline_refinement_rows=len(baseline), lc_native_refinement_rows=len(lc),
                    lc_local_refinement_rows=len(local), paired_rows=len(paired),
                    common_iteration_min=paired[0]["iteration"] if paired else None,
                    common_iteration_max=paired[-1]["iteration"] if paired else None,
                    same_camera_rows=sum(r["same_camera"] for r in paired),
                    differing_camera_rows=sum(not r["same_camera"] for r in paired),
                    differing_lambda_visual_rows=sum(not r["lambda_visual_equal"] for r in paired),
                    local_without_native_iterations=sorted(set(local) - set(lc)),
                    native_without_local_iterations=sorted(set(lc) - set(local)),
                    baseline_controller_phase="not_recorded")
    return paired, coverage


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def summarize_pair(pairs):
    result = {"sample_count": len(pairs)}
    for key in METRICS:
        for side in ("G", "LC"):
            result[key + "_sample_mean_" + side] = mean(r[key + "_" + side] for r in pairs)
        result[key + "_paired_delta_sample_mean"] = mean(r[key + "_delta_LC_minus_G"] for r in pairs)
    for key in ("rgb_loss", "raw_prior_loss", "raw_visual_loss"):
        result[key + "_same_camera_delta_sample_mean"] = mean(r[key + "_delta_LC_minus_G"] for r in pairs if r["same_camera"])
    for key in LOCAL_FIELDS:
        result[key + "_sample_mean_LC"] = mean(r[key + "_LC"] for r in pairs)
    for side in ("G", "LC"):
        result["observed_common_iteration_span_seconds_" + side] = (
            pairs[-1]["elapsed_seconds_" + side] - pairs[0]["elapsed_seconds_" + side] if len(pairs) > 1 else None)
    return result


def snapshot_file(root, relative, output, label, records, required=False):
    root, relative = Path(root), Path(relative)
    path = root / relative
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return None
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Input path escapes its read-only run root: " + str(path))
    data = path.read_bytes()
    target = Path(output) / "source_snapshots" / label / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    records.append(dict(path=str(path), snapshot_path=str(target.relative_to(output)),
                        bytes=len(data), sha256=digest_bytes(data)))
    return data


def capture_iterations(command):
    if not command or "--jbgs_capture_iterations" not in command:
        return None
    index = command.index("--jbgs_capture_iterations") + 1
    values = []
    while index < len(command) and not str(command[index]).startswith("-"):
        value = int(command[index])
        if value < 0 or value in values:
            raise ValueError("Invalid or duplicate complete checkpoint capture iteration")
        values.append(value)
        index += 1
    if not values:
        raise ValueError("Explicit capture flag has no iteration values")
    return sorted(values)


def source_cost(receipt, native_rows, invocation=None, observed_captures=None):
    metadata = dict(invocation or {})
    metadata.update(receipt or {})
    start = metadata.get("training_start_iteration")
    prefix = (None if start is None else
              next((r["elapsed_seconds"] for r in native_rows if r["iteration"] == 8000), None) if start == 0 else 0.)
    wall = receipt.get("wall_seconds") if receipt else None
    captures = capture_iterations(metadata.get("command"))
    active = [i for i in captures if i > start] if captures is not None and start is not None else None
    return dict(training_start_iteration=start, driver_wall_seconds=wall,
                anchor_prefix_trace_seconds=prefix,
                driver_wall_minus_anchor_prefix_seconds_approx=wall - prefix if wall is not None and prefix is not None else None,
                child_peak_rss_bytes=receipt.get("child_peak_rss_bytes") if receipt else None,
                complete_capture_iterations_declared=captures,
                complete_capture_iterations_active_after_start=active,
                complete_capture_iterations_observed=observed_captures,
                complete_capture_observation="completed small receipts; no checkpoint payload loaded or rehashed",
                anchor_prefix_includes_initial_training=start == 0 if start is not None else None,
                anchor_prefix_subtraction_excludes_iteration8000_capture_cost=start == 0 if start is not None else None,
                peak_scope="process cumulative; includes initialization, any Anchor training and capture/serialization history",
                driver_wall_scope="includes initialization/resume and all executed capture/serialization events; checkpoint schedules can differ",
                pure_refinement_peak_identified=False, cumulative_peak_subtraction_performed=False,
                pure_refinement_wall_identified=False, checkpoint_capture_cost_isolated=False)


def compare_cost_scopes(g, lc, pairs):
    g_schedule = g["complete_capture_iterations_active_after_start"]
    lc_schedule = lc["complete_capture_iterations_active_after_start"]
    known = g_schedule is not None and lc_schedule is not None
    first = pairs[0]["iteration"] if pairs else None
    last = pairs[-1]["iteration"] if pairs else None
    def span_captures(schedule):
        # jbgs_trace is written before that iteration's complete checkpoint.
        # Thus capture at the first endpoint can fall inside elapsed last-first;
        # capture at the final endpoint is excluded from that span.
        return [i for i in schedule if first <= i < last] if schedule is not None and pairs else None
    return dict(capture_schedule_match=(g_schedule == lc_schedule) if known else None,
                training_start_match=(g["training_start_iteration"] == lc["training_start_iteration"])
                    if g["training_start_iteration"] is not None and lc["training_start_iteration"] is not None else None,
                complete_captures_potentially_inside_observed_span_G=span_captures(g_schedule),
                complete_captures_potentially_inside_observed_span_LC=span_captures(lc_schedule),
                trace_capture_order="native trace is sampled before same-iteration checkpoint capture",
                wall_comparison_has_unequal_checkpoint_schedule=(g_schedule != lc_schedule) if known else None,
                local_loss_memory_gain_established=False,
                pure_refinement_peak_comparison_available=False,
                interpretation="Resource curves and elapsed spans include process/capture history; compare operational costs without attributing differences to local-loss memory efficiency.")


def write_csv(path, rows):
    fields = sorted(set().union(*(r.keys() for r in rows))) if rows else ["region", "condition", "iteration"]
    with Path(path).open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


CHART_CONTRACT = dict(
    analytical_question="How do sampled controller inputs, realized coefficients, primitives and costs differ on exact G/LC iteration intersections?",
    family="Trend", variant="paired small-multiple line charts; single observations use markers",
    renderer="Matplotlib Agg standalone PNG", palette_policy="hard two-root cap",
    palette={"G": "#2864A5", "LC": "#C66B24"}, non_color_distinction="G dashed, LC solid; explicit legend",
    domain="same exact iteration intersection in 8001..30000; no interpolation or camera matching assumed",
    family_rationale="All nine panels measure a process quantity along ordered optimization iterations. Lines organize observed temporal samples and markers retain observation identity; these are not category rankings, composition charts or an arbitrary executive chart-family selection.",
    minimum_line_samples=8, sparse_fallback="labeled markers; no connecting line below eight observations",
    footprint="14 by 12 inch, 160 DPI, 3 by 3 panels", scientific_verdict=None)


def plot_pair(path, region, condition, pairs, coverage, status, g_cost=None, lc_cost=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 3, figsize=(14, 12), constrained_layout=True)
    panels = [("raw_prior_loss", "Raw prior depth L1 (m)", 1),
              ("raw_visual_loss", "Raw DA3 depth L1 (m)", 1), ("rgb_loss", "Native RGB objective", 1),
              ("lambda_visual", "Realized global visual coefficient", 1),
              ("gaussians", "Gaussians after step (millions)", 1e6),
              ("protected", "Protected Gaussians after step (millions)", 1e6),
              ("peak_cuda_allocated_bytes", "Cumulative peak CUDA allocated (GiB)", 2**30),
              ("peak_rss_bytes", "Cumulative peak process RSS (GiB)", 2**30)]
    x = [r["iteration"] for r in pairs]
    for ax, (metric, title, scale) in zip(axes.flat, panels):
        for side, style in (("G", "--"), ("LC", "-")):
            ax.plot(x, [r[metric + "_" + side] / scale for r in pairs],
                    color=CHART_CONTRACT["palette"][side], label=side,
                    linestyle=style if len(pairs) >= 8 else "None",
                    marker="s" if side == "G" else "o", markersize=6 if side == "G" else 3,
                    markerfacecolor="white" if side == "G" else CHART_CONTRACT["palette"][side],
                    markevery=max(1, len(pairs) // 12), linewidth=1.2)
        ax.set_title(title, fontsize=11)
    ax = axes.flat[-1]
    for field, name, style, color in (("prior_multiplier_mean_valid_LC", "Prior", "--", "#2864A5"),
                                     ("visual_multiplier_mean_valid_LC", "Visual", "-", "#C66B24")):
        ax.plot(x, [r[field] if r[field] is not None else float("nan") for r in pairs], label=name,
                linestyle=style if len(pairs) >= 8 else "None", marker="s" if name == "Prior" else "o",
                markersize=6 if name == "Prior" else 3, markerfacecolor="white" if name == "Prior" else color,
                markevery=max(1, len(pairs) // 12), color=color, linewidth=1.2)
    ax.set_title("LC mean multiplier over valid source pixels", fontsize=11)
    ax.set_ylim(-.02, 1.02)
    ax.legend(frameon=False, fontsize=9)
    for ax in axes.flat:
        ax.grid(axis="y", color="#DDDDDD", linewidth=.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("Iteration")
        ax.tick_params(labelsize=9)
    axes.flat[0].legend(frameon=False, fontsize=10)
    resource_caption = "Resource peaks are process-cumulative; checkpoint costs are not isolated."
    if g_cost is not None and lc_cost is not None:
        def schedule(cost):
            value = cost["complete_capture_iterations_active_after_start"]
            return "unknown" if value is None else ",".join(str(i) for i in value)
        resource_caption = f"Active checkpoint schedules: G [{schedule(g_cost)}]; LC [{schedule(lc_cost)}]. Resource peaks include capture history."
    fig.suptitle(f"{region} / {condition}: G and LC refinement trace ({status})\n"
                 f"{len(pairs)} exact iteration pairs; {coverage['same_camera_rows']} same-camera samples. "
                 "Loss samples are training objectives, not surface correction/damage.\n" + resource_caption, fontsize=12)
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def build_report(parent_runs, new_runs, config_path, binding_path, output, *, plots=True):
    parent_runs, new_runs, output = map(Path, (parent_runs, new_runs, output))
    if output.exists():
        raise FileExistsError(output)
    if any(output.resolve().is_relative_to(root.resolve()) for root in (parent_runs, new_runs)):
        raise ValueError("Report output must be separate from both run trees")
    cfg_data, binding_data = Path(config_path).read_bytes(), Path(binding_path).read_bytes()
    cfg, binding = json_document(cfg_data), json_document(binding_data)
    cfg_hash, binding_hash = digest_bytes(cfg_data), digest_bytes(binding_data)
    if cfg.get("schema") != "jbgs.local_complementary_refinement.v2" or binding["config"]["sha256"] != cfg_hash:
        raise ValueError("Trace report requires the frozen main-v2 config/binding")
    if (binding["tau0_m"], binding["tau1_m"]) != (cfg["local_weight"]["tau0_m"], cfg["local_weight"]["tau1_m"]):
        raise ValueError("Threshold binding mismatch")
    output.mkdir(parents=True)
    (output / "experiment_v2.json").write_bytes(cfg_data)
    (output / "input_binding.json").write_bytes(binding_data)
    (output / "summarize_traces_v2.py").write_bytes(Path(__file__).read_bytes())
    records, reports, all_pairs, summaries = [], [], [], []
    write_json(output / "chart_contract.json", CHART_CONTRACT)
    write_json(output / "report_change_record.json", REPORT_CHANGE_RECORD)
    for region in cfg["regions"]:
        for condition in cfg["conditions"]:
            condition_id, parent_id = condition["id"], condition["parent_condition"]
            relative_G, relative_LC = Path(region) / parent_id, Path(region) / condition_id
            def read_snapshot(side, relative, required=False):
                return snapshot_file(parent_runs if side == "G" else new_runs,
                                     (relative_G if side == "G" else relative_LC) / relative,
                                     output, side, records, required)
            g_inv_bytes = read_snapshot("G", "train_invocation.json", True)
            g_receipt_bytes = read_snapshot("G", "train_receipt.json", True)
            g_inv, g_receipt = json_document(g_inv_bytes), json_document(g_receipt_bytes)
            frozen = binding["regions"][region]["baselines"][parent_id]
            if digest_bytes(g_inv_bytes) != frozen["train_invocation"]["sha256"]:
                raise ValueError("Baseline invocation differs from reuse binding")
            if "train_receipt" in frozen and digest_bytes(g_receipt_bytes) != frozen["train_receipt"]["sha256"]:
                raise ValueError("Baseline receipt differs from reuse binding")
            if (g_inv["region"], g_inv["condition"], g_receipt.get("status")) != (region, parent_id, "PASS"):
                raise ValueError("Baseline identity or completed status differs")
            new_inv_bytes = read_snapshot("LC", "train_invocation.json")
            new_receipt_bytes = read_snapshot("LC", "train_receipt.json")
            new_inv = json_document(new_inv_bytes) if new_inv_bytes else None
            new_receipt = json_document(new_receipt_bytes) if new_receipt_bytes else None
            if new_inv and (new_inv.get("config_sha256"), new_inv.get("input_binding", {}).get("sha256"),
                            new_inv.get("region"), new_inv.get("condition")) != (cfg_hash, binding_hash, region, condition_id):
                raise ValueError("LC invocation identity/config/binding differs")
            if new_receipt and (new_receipt.get("config_sha256"), new_receipt.get("input_binding", {}).get("sha256"),
                                new_receipt.get("region"), new_receipt.get("condition")) != (cfg_hash, binding_hash, region, condition_id):
                raise ValueError("LC receipt identity/config/binding differs")
            if new_receipt and new_inv is None:
                raise ValueError("LC receipt exists without bound invocation")
            trace_sets, ignored = {}, {}
            for side, name, required in (("G", "jbgs_trace", True), ("LC", "jbgs_trace", False), ("LC", "local_trace", False)):
                data = read_snapshot(side, "model/" + name + ".jsonl", required)
                trace_sets[side + "_" + name], ignored[side + "_" + name] = parse_trace(data) if data else ([], 0)
            pairs, coverage = pair_trajectories(trace_sets["G_jbgs_trace"], trace_sets["LC_jbgs_trace"],
                trace_sets["LC_local_trace"], cfg_hash=cfg_hash, binding_hash=binding_hash,
                tau0=binding["tau0_m"], tau1=binding["tau1_m"], lambda_prior=condition["lambda_p"])
            if (trace_sets["LC_jbgs_trace"] or trace_sets["LC_local_trace"]) and new_inv is None:
                raise ValueError("LC trace exists without bound invocation")
            status = new_receipt.get("status") if new_receipt else "PARTIAL" if new_inv else "NOT_STARTED"
            if status == "PASS" and coverage["common_iteration_max"] != 30000:
                raise ValueError("Completed LC receipt lacks final matched trace")
            observed_captures = {}
            for side, invocation in (("G", g_inv), ("LC", new_inv)):
                schedule = capture_iterations(invocation.get("command")) if invocation else None
                observed_captures[side] = None if schedule is None else []
                for iteration in schedule or []:
                    data = read_snapshot(side, f"model/jbgs_complete/iteration_{iteration}/receipt.json")
                    if data is not None:
                        capture_receipt = json_document(data)
                        if capture_receipt.get("iteration") != iteration:
                            raise ValueError("Complete checkpoint receipt iteration differs")
                        observed_captures[side].append(iteration)
            g_cost = source_cost(g_receipt, trace_sets["G_jbgs_trace"], g_inv, observed_captures["G"])
            lc_cost = source_cost(new_receipt, trace_sets["LC_jbgs_trace"], new_inv, observed_captures["LC"])
            cost_comparison = compare_cost_scopes(g_cost, lc_cost, pairs)
            summary = dict(region=region, condition=condition_id, parent_condition=parent_id,
                           status=status, **coverage, **summarize_pair(pairs))
            summary.update(capture_schedule_match=cost_comparison["capture_schedule_match"],
                           training_start_match=cost_comparison["training_start_match"],
                           wall_comparison_has_unequal_checkpoint_schedule=cost_comparison["wall_comparison_has_unequal_checkpoint_schedule"],
                           local_loss_memory_gain_established=False)
            for side, cost in (("G", g_cost), ("LC", lc_cost)):
                summary["training_start_iteration_" + side] = cost["training_start_iteration"]
                for key in ("complete_capture_iterations_declared", "complete_capture_iterations_active_after_start", "complete_capture_iterations_observed"):
                    summary[key + "_" + side] = json.dumps(cost[key])
            report = dict(summary=summary, incomplete_tail_bytes_ignored=ignored,
                          baseline_cost=g_cost, lc_cost=lc_cost, cost_comparison=cost_comparison,
                          baseline_config_sha256=g_inv.get("config_sha256"),
                          config_sha256=cfg_hash, input_binding_sha256=binding_hash, scientific_verdict=None)
            for row in pairs:
                row.update(region=region, condition=condition_id, parent_condition=parent_id,
                           baseline_config_sha256=g_inv.get("config_sha256"))
            all_pairs.extend(pairs)
            summaries.append({k: v for k, v in summary.items() if not isinstance(v, (list, dict))})
            reports.append(report)
            if plots and pairs:
                plot_pair(output / (region + "_" + condition_id + "_trace.png"), region, condition_id, pairs, coverage, status, g_cost, lc_cost)
    write_csv(output / "paired_iterations.csv", all_pairs)
    write_csv(output / "condition_summary.csv", summaries)
    result = dict(schema="JBGS_LOCAL_COMPLEMENTARY_TRACE_REPORT_v2", created_unix=time.time(),
                  report_revision=REPORT_REVISION, report_change_record=REPORT_CHANGE_RECORD,
                  scientific_verdict=None, reference_accessed=False,
                  config_sha256=cfg_hash, input_binding_sha256=binding_hash,
                  status_counts={s: sum(r["status"] == s for r in summaries) for s in sorted({r["status"] for r in summaries})},
                  iteration_window=[8001, 30000], paired_iterations=len(all_pairs), conditions=reports,
                  sources=records, limitations=LIMITATIONS,
                  runtime={"python": sys.version,
                           "matplotlib": __import__("matplotlib").__version__ if plots else None,
                           "configured_image_id": cfg.get("runtime", {}).get("image_id")},
                  code_sha256=digest_bytes(Path(__file__).read_bytes()))
    write_json(output / "trace_summary.json", result)
    return result


def main():
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Run project trace analysis in Docker")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-runs", required=True, type=Path)
    parser.add_argument("--new-runs", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    existed_before = args.output.exists()
    try:
        result = build_report(args.parent_runs, args.new_runs, args.config, args.binding, args.output, plots=not args.no_plots)
    except Exception as error:
        if args.output.is_dir() and not existed_before:
            write_json(args.output / "trace_summary_failure.json", dict(status="FAIL", exception_type=type(error).__name__,
                       exception=str(error), scientific_verdict=None, reference_accessed=False))
        raise
    print(json.dumps({"status_counts": result["status_counts"], "paired_iterations": result["paired_iterations"],
                      "output": str(args.output), "scientific_verdict": None}, allow_nan=False))


if __name__ == "__main__":
    main()
