"""Execute small, unchanged GeoGS source fragments on synthetic evidence.

This is a control-flow diagnostic, not a GeoGS reproduction or benchmark.
Published code is AST-extracted rather than reimplemented. A source hash binds
the extraction to the reviewed revision. CPU tensors are used throughout.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config_path = Path(args.config)
    cfg = json.loads(config_path.read_text())
    source = Path(cfg["source_root"])
    output = Path(cfg["output_root"])
    output.mkdir(parents=True, exist_ok=False)
    path = source / "train.py"
    if sha(path) != cfg["train_sha256"]:
        raise RuntimeError("Reviewed source hash mismatch")
    tree = ast.parse(path.read_text())
    scope = {"torch": torch, "np": np, "GaussianModel": object}
    excerpts = []
    for name in ("compute_depth_loss", "find_building_mask_from_pcd", "attenuate_building_xyz_lr"):
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), scope)
        excerpts.append({"file": "train.py", "name": name, "start": node.lineno, "end": node.end_lineno})

    # Execute the original complete stage-weighting If, including both anchor
    # and visual-depth terms. No editing or manual translation of the logic.
    stage = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == "not stage2_active")
    stage_code = compile(ast.Module(body=[stage], type_ignores=[]), str(path), "exec")
    excerpts.append({"file": "train.py", "name": "stage_weighting", "start": stage.lineno, "end": stage.end_lineno})
    options = {}
    for node in ast.walk(ast.parse((source / "arguments/__init__.py").read_text())):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Attribute) and target.attr.startswith(("depth_", "rgb_")):
                try:
                    options[target.attr] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    train_defaults = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument" and node.args:
            if isinstance(node.args[0], ast.Constant):
                for kw in node.keywords:
                    if kw.arg == "default":
                        try:
                            train_defaults[node.args[0].value.lstrip("-")] = ast.literal_eval(kw.value)
                        except (ValueError, TypeError):
                            pass

    records, trace_summary = [], []
    log = io.StringIO()
    cases = [("improving_rgb_low_lod_error", 0.1, True, False),
             ("improving_rgb_high_lod_error", 10.0, True, False),
             ("small_stable_rgb_high_lod_error", 10.0, False, False),
             ("rising_da_error", 10.0, True, True)]
    with contextlib.redirect_stdout(log):
        for case, lod_error, improving, rising in cases:
            ns = dict(scope, opt=SimpleNamespace(**options), stage2_active=True,
                      dynamic_da=True, da_depth=torch.ones(1), lod_depth=torch.ones(1),
                      lambda_lod_init=train_defaults["lambda_lod_init"],
                      lambda_lod_anchor=train_defaults["lambda_lod_anchor"],
                      lambda_da_depth=train_defaults["lambda_da_depth"],
                      PHASE_INITIAL=0, PHASE_CONVERGED=1, PHASE_DECAYING=2, PHASE_LOCKED=3,
                      da_phase=0, da_weight=options["depth_initial_weight"],
                      da_depth_history=[], da_monitor_depth=[], da_monitor_rgb=[],
                      da_last_check=None, da_consecutive=0, da_locked_weight=None)
            for step in range(1, cfg["synthetic_trace_steps"] + 1):
                rgb = 0.2 * math.exp(-cfg["synthetic_rgb_decay_per_step"] * step) if improving else 0.001
                depth_error = math.exp(0.001 * max(step - 1400, 0)) if rising else 1.0
                ns.update(iteration=8000 + step, rgb_loss=torch.tensor(rgb),
                          da_depth_loss=torch.tensor(depth_error), lod_depth_loss=torch.tensor(lod_error),
                          dist_loss=torch.tensor(0.0), normal_loss=torch.tensor(0.0))
                exec(stage_code, ns)
                records.append({"case": case, "stage2_step": step, "rgb_loss": rgb,
                                "da_loss": depth_error, "lod_loss": lod_error,
                                "da_weight": ns["current_da_weight"], "lod_weight": ns["current_lod_weight"],
                                "phase": ns["da_phase"]})
            trace_summary.append({"case": case, "final_da_weight": ns["current_da_weight"],
                                  "final_lod_weight": ns["current_lod_weight"], "final_phase": ns["da_phase"]})

    # The actual proximity classifier sees source geometry, not semantic truth.
    xyz = torch.tensor([[0., 0., 10.], [0., 0., 12.], [0., 0., 10.1]])
    mask = scope["find_building_mask_from_pcd"](SimpleNamespace(get_xyz=xyz),
               torch.tensor([[0., 0., 10.]]), train_defaults["lod2_match_thresh"], chunk_size=2)

    adam_records, adam_summary = [], []
    scale = train_defaults["lod2_building_xyz_lr_scale"]
    with contextlib.redirect_stdout(log):
        for warmup in (0, cfg["synthetic_adam_warmup"]):
            parameter = torch.nn.Parameter(torch.zeros((2, 3), dtype=torch.float64))
            optimizer = torch.optim.Adam([parameter], lr=cfg["synthetic_adam_lr"], eps=1e-15)
            hook_gradients = None
            for step in range(cfg["synthetic_adam_steps"]):
                if step == warmup:
                    scope["attenuate_building_xyz_lr"](SimpleNamespace(_xyz=parameter), torch.tensor([True, False]), scale)
                optimizer.zero_grad(set_to_none=True)
                # Equal linear gradients isolate the protection hook and Adam.
                parameter.sum().backward()
                old = parameter.detach().clone()
                if step == warmup:
                    hook_gradients = parameter.grad[:, 0].tolist()
                optimizer.step()
                delta = (parameter.detach() - old).abs()[:, 0].tolist()
                adam_records.append({"warmup": warmup, "step": step + 1,
                                     "protected_step": delta[0], "unprotected_step": delta[1],
                                     "step_ratio": delta[0] / delta[1]})
            own = [r for r in adam_records if r["warmup"] == warmup]
            adam_summary.append({"warmup": warmup, "hook_gradient_pair": hook_gradients,
                                 "first_hook_step_ratio": own[warmup]["step_ratio"],
                                 "last_step_ratio": own[-1]["step_ratio"]})

    for filename, rows in (("weight_trace.csv", records), ("adam_trace.csv", adam_records)):
        with (output / filename).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    (output / "official_fragment_stdout.txt").write_text(log.getvalue())
    report = {"task_id": cfg["task_id"], "scientific_verdict": None,
              "scope": cfg["scope"], "scene_training_runs": 0, "rendered_scene_outputs": 0,
              "source_commit": cfg["source_commit"], "train_sha256": sha(path),
              "config_sha256": sha(config_path), "script_sha256": sha(Path(__file__)),
              "versions": {"torch": torch.__version__, "numpy": np.__version__},
              "source_excerpts": excerpts, "native_defaults": {"options": options, "train": train_defaults},
              "weight_cases": trace_summary,
              "proximity_case": {"synthetic_xyz": xyz.tolist(), "prior_xyz": [[0, 0, 10]],
                                 "mask": mask.tolist(), "uses_current_reference": False},
              "adam_cases": adam_summary,
              "interpretation_limits": ["Synthetic traces do not establish real-scene failure or scientific novelty.",
                  "Gradient attenuation is not generally equivalent to an Adam learning-rate multiplier.",
                  "Warm Adam state makes scaling effects transient and history-dependent.",
                  "Opacity and appearance remain optimizable in full GeoGS; this probe does not establish visible survival of stale geometry."]}
    (output / "receipt.json").write_text(json.dumps(report, indent=2))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.5))
    for case, *_ in cases:
        data = [r for r in records if r["case"] == case]
        ax[0].plot([r["stage2_step"] for r in data], [r["da_weight"] for r in data], label=case.replace("_", " "))
    ax[0].axhline(train_defaults["lambda_lod_anchor"], color="black", linestyle="--", label="LoD anchor (all cases)")
    ax[0].set(xlabel="Synthetic Stage-2 iteration", ylabel="Loss coefficient", title="Official weight controller")
    ax[0].legend(fontsize=6)
    for warmup in (0, cfg["synthetic_adam_warmup"]):
        data = [r for r in adam_records if r["warmup"] == warmup and r["step"] > warmup]
        ax[1].plot([r["step"] - warmup for r in data], [r["step_ratio"] for r in data], label=f"Adam warmup={warmup}")
    ax[1].axhline(scale, color="black", linestyle="--", label=f"Gradient multiplier={scale}")
    ax[1].set(xlabel="Steps after hook", ylabel="Protected / unprotected step", title="Gradient scaling and Adam displacement")
    ax[1].legend(fontsize=7)
    fig.suptitle("GeoGS source diagnostic — synthetic inputs, no scene reconstruction", fontsize=11)
    fig.tight_layout()
    fig.savefig(output / "control_diagnostic.png", dpi=160)
    fig.savefig(output / "control_diagnostic.svg")
    print(json.dumps({k: report[k] for k in ("weight_cases", "proximity_case", "adam_cases")}, indent=2))


if __name__ == "__main__":
    main()
