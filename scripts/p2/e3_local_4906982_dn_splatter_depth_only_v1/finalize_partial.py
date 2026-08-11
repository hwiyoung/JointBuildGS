#!/usr/bin/env python3
"""Finalize the bounded DN-Splatter depth-only run after its OOM stop.

This script is idempotent and evaluation/reporting-only.  It does not train,
render, fuse, run Roofer, or alter any comparator artifact.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

from PIL import Image, ImageDraw


STEPS = (7000, 12000)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value)
    os.replace(temporary, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def by_step(rows: list[dict], key: str = "completed_updates") -> dict[int, dict]:
    return {int(row[key]): row for row in rows}


def number(value: object) -> float | int | None:
    if value in (None, ""):
        return None
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def delta(new: object, old: object) -> float | None:
    a, b = number(new), number(old)
    return None if a is None or b is None else float(a - b)


def compose_panels(task_root: Path, control_root: Path) -> int:
    count = 0
    for step in STEPS:
        control_dir = control_root / f"representative_images/GSPLAT_2DGS_REF/step_{step:06d}"
        dn_dir = task_root / f"representative_images/DN_DEPTH/step_{step:06d}"
        output_dir = task_root / f"representative_images/control_vs_dn/step_{step:06d}"
        output_dir.mkdir(parents=True, exist_ok=True)
        for dn_path in sorted(dn_dir.glob("*.png")):
            control_path = control_dir / dn_path.name
            if not control_path.is_file():
                raise RuntimeError(f"missing matching control panel: {control_path}")
            with Image.open(control_path) as left_image, Image.open(dn_path) as right_image:
                left, right = left_image.convert("RGB"), right_image.convert("RGB")
                if left.size != right.size:
                    raise RuntimeError(f"panel size mismatch: {control_path} vs {dn_path}")
                header = 42
                canvas = Image.new("RGB", (left.width + right.width, left.height + header), "white")
                canvas.paste(left, (0, header))
                canvas.paste(right, (left.width, header))
                draw = ImageDraw.Draw(canvas)
                draw.text((12, 12), f"depth-free 2DGS control | step {step}", fill="black")
                draw.text((left.width + 12, 12), f"DN EdgeAwareLogL1 depth-only | step {step}", fill="black")
                output = output_dir / dn_path.name
                temporary = output.with_suffix(".tmp.png")
                canvas.save(temporary)
                os.replace(temporary, output)
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--expected-audit-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--git-head", required=True)
    parser.add_argument("--git-branch", required=True)
    parser.add_argument("--git-dirty", choices=("true", "false"), required=True)
    parser.add_argument("--docker-image-id", required=True)
    parser.add_argument("--gpu-model", required=True)
    args = parser.parse_args()

    root = args.task_root
    evaluation = by_step([
        read_json(root / f"arms/DN_DEPTH/R1/evaluation/step_{step:06d}/evaluation.json")
        for step in STEPS
    ])
    mvs = by_step(read_json(root / "mvs_surface_audit.json")["rows"])
    lod = by_step(read_json(root / "lod2_evaluation.json")["rows"])
    control = by_step([
        row for row in read_csv(args.control_root / "checkpoint_metrics.csv")
        if row["arm"] == "GSPLAT_2DGS_REF" and int(row["completed_updates"]) in STEPS
    ])

    fields = [
        "arm", "replica", "completed_updates", "checkpoint_sha256", "gaussian_count",
        "z_min", "z_median", "z_p95", "z_p99", "z_max", "seed_max_z",
        "above_seed_max", "z_gt_650", "z_gt_650_footprint_inside",
        "z_gt_650_footprint_outside", "z_gt_650_opacity_lt_0p1",
        "z_gt_650_opacity_0p1_0p5", "z_gt_650_opacity_0p5_0p9",
        "z_gt_650_opacity_ge_0p9", "scale_min_q50", "scale_max_q50",
        "elongation_q50", "eval_psnr", "eval_ssim", "eval_lpips", "fusion_ge2",
        "fusion_ge3", "fusion_ge3_ratio", "roof_density", "wall_density",
        "mvs_point_to_point_median", "mvs_point_to_plane_median",
        "mvs_normal_angle_median", "mvs_grid_coverage", "lod2_abs_dz_median",
        "lod2_abs_dz_rmse", "lod2_normal_angle_median", "lod2_grid_coverage",
        "lod2_coherent_grid_coverage", "roofer_success", "roofer_internal_rmse",
        "roofer_roof_xy_coverage", "roofer_surface_fscore_0p5m",
        "roofer_surface_normal_angle_median", "scientific_verdict",
    ]
    rows: list[dict[str, object]] = []
    for step in STEPS:
        item, surface, reference = evaluation[step], mvs[step], lod[step]
        geometry, fusion = item["geometry"], item["fusion"]
        opacity = geometry["opacity_bins"]
        terminal = read_json(root / f"arms/DN_DEPTH/R1/evaluation/step_{step:06d}/fusion/roofer/roofer_terminal.json")
        row = {
            "arm": "DN_DEPTH", "replica": "R1", "completed_updates": step,
            "checkpoint_sha256": item["checkpoint_sha256"],
            "gaussian_count": geometry["gaussian_count"],
            "z_min": geometry["z_epsg25832"]["min"],
            "z_median": geometry["z_epsg25832"]["median"],
            "z_p95": geometry["z_epsg25832"]["p95"],
            "z_p99": geometry["z_epsg25832"]["p99"],
            "z_max": geometry["z_epsg25832"]["max"],
            "seed_max_z": geometry["seed_max_z_epsg25832"],
            "above_seed_max": geometry["count_above_seed_max_z"],
            "z_gt_650": geometry["count_z_gt_650m"],
            "z_gt_650_footprint_inside": surface["gaussian_z_gt_650_footprint_inside_count"],
            "z_gt_650_footprint_outside": surface["gaussian_z_gt_650_footprint_outside_count"],
            "z_gt_650_opacity_lt_0p1": opacity["lt_0p1"]["z_gt_650m"],
            "z_gt_650_opacity_0p1_0p5": opacity["0p1_0p5"]["z_gt_650m"],
            "z_gt_650_opacity_0p5_0p9": opacity["0p5_0p9"]["z_gt_650m"],
            "z_gt_650_opacity_ge_0p9": opacity["ge_0p9"]["z_gt_650m"],
            "scale_min_q50": geometry["scale_min_q50_q95_q99_max"][0],
            "scale_max_q50": geometry["scale_max_q50_q95_q99_max"][0],
            "elongation_q50": geometry["elongation_q01_q05_q50_q95"][2],
            "eval_psnr": item["render_metrics"]["eval"]["psnr"],
            "eval_ssim": item["render_metrics"]["eval"]["ssim"],
            "eval_lpips": item["render_metrics"]["eval"]["lpips"],
            "fusion_ge2": fusion["point_count_ge2"], "fusion_ge3": fusion["point_count_ge3"],
            "fusion_ge3_ratio": fusion["ratio_ge3_of_ge2"],
            "roof_density": fusion["roof_density_per_footprint_m2"],
            "wall_density": fusion["wall_density_per_footprint_m2"],
            "mvs_point_to_point_median": surface["ordinary_point_to_point_m_median"],
            "mvs_point_to_plane_median": surface["ordinary_point_to_plane_m_median"],
            "mvs_normal_angle_median": surface["ordinary_normal_angle_deg_median"],
            "mvs_grid_coverage": surface["ordinary_grid_coverage_of_mvs"],
            "lod2_abs_dz_median": reference["classified_abs_dz_m_median"],
            "lod2_abs_dz_rmse": reference["classified_abs_dz_m_rmse"],
            "lod2_normal_angle_median": reference["classified_normal_angle_deg_median"],
            "lod2_grid_coverage": reference["classified_grid_coverage_fraction"],
            "lod2_coherent_grid_coverage": reference["classified_coherent_grid_coverage_fraction"],
            "roofer_success": bool(terminal.get("rf_success")),
            "roofer_internal_rmse": reference["roofer_internal_rmse"],
            "roofer_roof_xy_coverage": reference["roofer_roof_xy_coverage_fraction"],
            "roofer_surface_fscore_0p5m": reference["roofer_surface_fscore_0p5m"],
            "roofer_surface_normal_angle_median": reference["roofer_surface_normal_angle_deg_median"],
            "scientific_verdict": None,
        }
        rows.append(row)

    with (root / "checkpoint_metrics.csv.tmp").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(root / "checkpoint_metrics.csv.tmp", root / "checkpoint_metrics.csv")

    comparisons: dict[str, dict[str, object]] = {}
    for row in rows:
        step, base = int(row["completed_updates"]), control[int(row["completed_updates"])]
        comparisons[str(step)] = {
            "dn": {key: row[key] for key in fields if key not in {"scientific_verdict"}},
            "control": {
                key: (
                    None if key == "scientific_verdict"
                    else base.get(key) if key in {"arm", "replica", "roofer_success"}
                    else number(base.get(key))
                )
                for key in base
            },
            "delta_dn_minus_control": {
                key: delta(row.get(key), base.get(key)) for key in (
                    "gaussian_count", "z_max", "z_gt_650", "eval_psnr", "eval_ssim",
                    "eval_lpips", "fusion_ge2", "fusion_ge3_ratio", "roof_density",
                    "wall_density", "mvs_point_to_point_median", "mvs_point_to_plane_median",
                    "mvs_normal_angle_median", "mvs_grid_coverage", "lod2_abs_dz_median",
                    "lod2_abs_dz_rmse", "lod2_normal_angle_median", "lod2_grid_coverage",
                    "lod2_coherent_grid_coverage", "roofer_internal_rmse",
                    "roofer_roof_xy_coverage", "roofer_surface_fscore_0p5m",
                    "roofer_surface_normal_angle_median",
                )
            },
        }

    expected_json = args.expected_audit_root / "expected_median_audit.json"
    expected_csv = args.expected_audit_root / "expected_median_audit.csv"
    for source in (expected_json, expected_csv):
        destination = root / source.name
        if destination.exists() and sha256(destination) != sha256(source):
            raise RuntimeError(f"existing expected-depth audit drift: {destination}")
        if not destination.exists():
            shutil.copyfile(source, destination)

    panel_count = compose_panels(root, args.control_root)
    metrics = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.metrics.v1",
        "status": "STOPPED_OOM_PARTIAL_EVALUATED",
        "task_id": "P2-E3-LOCAL-4906982-DN-SPLATTER-DEPTH-ONLY-v1",
        "training_experiments_started": 1,
        "training_experiments_reached_20000": 0,
        "valid_evaluated_steps": list(STEPS),
        "unmeasured_steps": {"15000": "not produced after OOM", "20000": "not produced after OOM"},
        "stop_gate": {
            "reason": "CUDA OOM during unchanged gsplat densification",
            "first_attempt": {"approx_completed_updates": 11900, "requested_gib": 1.58, "reserved_unallocated_gib": 6.66},
            "exact_resume_attempt": {"resume_checkpoint": 10000, "approx_completed_updates": 13600, "gaussian_count_approx": 10300000, "requested_gib": 1.76, "free_gib": 1.40, "reserved_unallocated_mib": 431.51},
        },
        "causal_scope": "DN EdgeAwareLogL1 expected-depth term only versus the existing depth-free 2DGS control",
        "comparisons": comparisons,
        "representative_comparison_panel_count": panel_count,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(root / "metrics.json", metrics)

    def f(value: object, digits: int = 3) -> str:
        return "NA" if value in (None, "") else f"{float(value):.{digits}f}"

    lines = [
        "# DN-Splatter depth-only partial comparison",
        "",
        "## Expected-depth gate (read-only prerequisite)",
        "",
        "The reused gate remained `STOP_AMBIGUOUS_EXPECTED_DEPTH_GATE`: the all-pixel expected/median gap p95 was 10.522 m, footprint p95 was 15.899 m, and footprint expected-only rate was 1.767%. It did not establish a clean expected-depth representation, but it also did not meet the preregistered aggregate degeneracy stop rule. This DN reference transfer was therefore treated as a separate, explicitly approved reference-family diagnostic, not as continuation of the blocked MVS-transfer arms.",
        "",
        "## Execution and stop",
        "",
        "One new training experiment (`DN_DEPTH/R1`) started. It produced valid full-state checkpoints at 7k and 12k. No 15k or 20k result exists. The first run OOMed near 11.9k; an exact 10k full-state resume with expandable CUDA segments passed that allocation but OOMed again near 13.6k at about 10.3M Gaussians. No densification cap, loss weight, mask, or other scientific variable was changed.",
        "",
        "## High-Z (DN depth-only versus depth-free 2DGS control)",
        "",
        "| step | arm | Gaussians | Z p99 m | Z max m | Z>650 | inside/outside | opacity >=0.9 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for step in STEPS:
        base, dn = control[step], next(row for row in rows if row["completed_updates"] == step)
        lines.append(f"| {step} | control | {int(float(base['gaussian_count'])):,} | {f(base['z_p99'])} | {f(base['z_max'])} | {int(float(base['z_gt_650']))} | {int(float(base['z_gt_650_footprint_inside']))}/{int(float(base['z_gt_650_footprint_outside']))} | {int(float(base['z_gt_650_opacity_ge_0p9']))} |")
        lines.append(f"| {step} | DN depth | {int(dn['gaussian_count']):,} | {f(dn['z_p99'])} | {f(dn['z_max'])} | {dn['z_gt_650']} | {dn['z_gt_650_footprint_inside']}/{dn['z_gt_650_footprint_outside']} | {dn['z_gt_650_opacity_ge_0p9']} |")
    lines += [
        "",
        "Observed: DN depth reduced the count above 650 m, but increased the extreme maximum to about 750 m and grew substantially more Gaussians. High-Z count reduction and tail elimination are therefore not the same outcome.",
        "",
        "## Ordinary surface and downstream read-out",
        "",
        "| step | arm | MVS p2p med m | MVS p2plane med m | MVS normal med deg | LoD2 abs dz med m | LoD2 normal med deg | held-out PSNR | fusion >=2 | Roofer RMSE | Roofer F0.5m |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for step in STEPS:
        base, dn = control[step], next(row for row in rows if row["completed_updates"] == step)
        lines.append(f"| {step} | control | {f(base['mvs_point_to_point_median'])} | {f(base['mvs_point_to_plane_median'])} | {f(base['mvs_normal_angle_median'])} | {f(base['lod2_abs_dz_median'])} | {f(base['lod2_normal_angle_median'])} | {f(base['eval_psnr'])} | {int(float(base['fusion_ge2'])):,} | {f(base['roofer_internal_rmse'])} | {f(base['roofer_surface_fscore_0p5m'])} |")
        lines.append(f"| {step} | DN depth | {f(dn['mvs_point_to_point_median'])} | {f(dn['mvs_point_to_plane_median'])} | {f(dn['mvs_normal_angle_median'])} | {f(dn['lod2_abs_dz_median'])} | {f(dn['lod2_normal_angle_median'])} | {f(dn['eval_psnr'])} | {dn['fusion_ge2']:,} | {f(dn['roofer_internal_rmse'])} | {f(dn['roofer_surface_fscore_0p5m'])} |")
    lines += [
        "",
        "Observed: fusion point/support counts increased, while held-out RGB quality and Roofer surface accuracy decreased at both measured steps. MVS point residuals improved relative to control, but normal error worsened by 12k and LoD2/Roofer coherence did not follow the added support.",
        "",
        "## Qualitative panels",
        "",
        "Sixteen aligned control-versus-DN panels are under `representative_images/control_vs_dn/`. In the inspected near-nadir 7k panel the DN render is visibly softer and its depth is separated into broad foreground/background blocks. In the inspected oblique 12k panel the main silhouette remains recognizable, while depth and world-normal regions are more coarsely segmented/noisy. The panel depth column is the frozen evaluator's **median-depth read-out**; the training supervision itself used expected depth.",
        "",
        "## Failures and next recommendation",
        "",
        "The measured run is incomplete and cannot supply a 20k endpoint. The reference-style loss alone did not yield a stable aerial raw-COLMAP-depth transfer under the frozen 2DGS densification. If another reference-family arm is approved, test the AGS-Mesh-style confidence/filtering mechanism as one isolated depth-selection arm on the same 2DGS base; do not add normal loss, new densification, or multiple losses simultaneously.",
        "",
        "`scientific_verdict: null`",
        "",
    ]
    atomic_text(root / "comparison.md", "\n".join(lines))

    issues = """# Issues

- Initial host-side reference read used the container-only `/artifacts` path and failed without modifying data; the host backend path was then resolved read-only.
- Docker Compose could not allocate a subnet because all configured address pools were exhausted; isolated `docker run --network none` was used instead.
- The evaluation image did not include pytest; the new loss test was converted to standard-library unittest and passed in Docker.
- Pinned DN-Splatter main applies `depth_loss += lambda * depth_loss`, inconsistent with README weight semantics. This bounded transfer uses the documented/paper-intended `lambda * loss` semantics and records the adaptation.
- Training first OOMed near 11.9k during gsplat splitting (1.58 GiB request; 6.66 GiB reserved but unallocated). Exact full-state resume from 10k with expandable CUDA segments passed this fragmentation-sensitive point.
- The resumed run OOMed again near 13.6k during gsplat splitting at about 10.3M Gaussians (1.76 GiB request; 1.40 GiB free; only 431.51 MiB reserved but unallocated). This is treated as a capacity stop. No density cap or scientific setting was changed.
- The frozen checkpoint analyzer emitted valid 7k/12k products, then its hard-coded 20k summary print failed. The partial wrapper was corrected to retain only the two valid steps; 15k/20k remain explicitly unmeasured.
- Stage-3 preparation initially retained the frozen four-step loop and failed on the absent 15k checkpoint; the thin wrapper was corrected to the pre-existing 7k/12k checkpoints and rerun idempotently.
- Final JSON QA caught two nested comparator `scientific_verdict` values inherited as empty CSV strings; the finalizer now normalizes them to JSON null and the full artifact audit was rerun.
"""
    atomic_text(root / "issues.md", issues)

    arm_log_index = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.arm_log_index.v1",
        "arm": "DN_DEPTH",
        "replica": "R1",
        "logs": [
            {"task_relative_path": str(path.relative_to(root)), "sha256": sha256(path)}
            for path in sorted((root / "logs").glob("*.log"))
        ],
        "scientific_verdict": None,
    }
    atomic_json(root / "arms/DN_DEPTH/R1/logs/index.json", arm_log_index)

    contract = read_json(root / "experiment_contract.json")
    contract.update({
        "status": "STOPPED_OOM_PARTIAL_EVALUATED",
        "new_training_arms_started": ["DN_DEPTH"],
        "training_experiments_started": 1,
        "training_experiments_reached_20000": 0,
        "valid_evaluated_steps": list(STEPS),
        "stop_gate": "repeated CUDA OOM during unchanged gsplat splitting/densification",
        "scientific_verdict": None,
    })
    atomic_json(root / "experiment_contract.json", contract)

    provenance = read_json(root / "provenance.json")
    tracked_sources = [
        args.repo_root / "src/stage2/loss/depth_reference.py",
        args.repo_root / "src/stage2/train.py",
        args.repo_root / "configs/p2/e3_local_4906982_dn_splatter_depth_only_v1/common.yaml",
        args.repo_root / "configs/p2/e3_local_4906982_dn_splatter_depth_only_v1/dn_depth.yaml",
        args.repo_root / "configs/p2/e3_local_4906982_dn_splatter_depth_only_v1/reference_sources.yaml",
        args.repo_root / "scripts/p2/e3_local_4906982_dn_splatter_depth_only_v1/prepare.py",
        args.repo_root / "scripts/p2/e3_local_4906982_dn_splatter_depth_only_v1/record.py",
        args.repo_root / "scripts/p2/e3_local_4906982_dn_splatter_depth_only_v1/evaluate_partial.py",
        args.repo_root / "scripts/p2/e3_local_4906982_dn_splatter_depth_only_v1/finalize_partial.py",
    ]
    provenance.update({
        "git": {"commit": args.git_head, "branch": args.git_branch, "dirty": args.git_dirty == "true"},
        "docker": {"image": "jointbuildgs:mvc-eval-v1", "image_id": args.docker_image_id, "network": "none"},
        "gpu_model": args.gpu_model,
        "source_and_config_sha256": {str(path.relative_to(args.repo_root)): sha256(path) for path in tracked_sources},
        "random_seed": 0,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "return_code": 1,
        "return_code_meaning": "training stopped by repeated CUDA OOM; 7k and 12k evaluation completed",
        "scientific_verdict": None,
    })
    atomic_json(root / "provenance.json", provenance)

    notes = """# DN-Splatter depth-only

One new arm ports only DN-Splatter-style expected-depth EdgeAwareLogL1 onto the existing gsplat 2D surface control. Normal, scale, confidence filtering, MVC, distortion, and external priors are excluded. The arm stopped after repeated unchanged-densification OOM; 7k and 12k are the only evaluated checkpoints. `scientific_verdict` remains null.
"""
    atomic_text(root / "NOTES.md", notes)
    print(json.dumps({"status": metrics["status"], "rows": len(rows), "comparison_panels": panel_count}, indent=2))


if __name__ == "__main__":
    main()
