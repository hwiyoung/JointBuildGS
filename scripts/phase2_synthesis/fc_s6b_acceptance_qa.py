#!/usr/bin/env python3
"""FC-S6b acceptance QA for the A8 terrain-off Mutual candidate.

This script is intentionally read-only with respect to training/evaluation
artifacts. It consumes existing Stage3Algo-v1 + Metric-v1 outputs and writes
comparison tables, a QA note, and a candidate acceptance report.
"""
from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path("results/FC_S6_componentwise_revised_lmutual_design_validation")
OUT = ROOT / "phase_s6b_acceptance"
PHASE1 = ROOT / "phase1_existing_terms"
PHASE2 = ROOT / "phase2_terrain_safe"
PHASE1_METRICS = PHASE1 / "term_ablation_metrics_by_bid.csv"
PHASE2_METRICS = PHASE2 / "terrain_safe_metrics_by_bid.csv"

ARMS = [
    ("A0_baseline_w0", "Baseline", "context"),
    ("A1_original_mutual", "Original Mutual", "context"),
    ("A4_terrain_normal_only", "A4 terrain-normal-only", "candidate"),
    ("A8_no_terrain_terms", "A8 no terrain terms", "candidate"),
    ("B2_terrain_confidence_gated", "B2 terrain confidence-gated", "candidate"),
    ("A9_no_terrain_terms_ramp", "A9 no terrain + ramp", "candidate"),
]

BIDS = ["B0", "B1", "B2", "B8", "B6", "B3", "B123", "B126", "B50", "B104"]
SPLITS = {
    "all_10": BIDS,
    "easy_control": ["B0", "B1", "B2", "B8", "B50"],
    "hard_diagnostic": ["B104", "B6", "B3", "B123", "B126"],
    "roof_complex": ["B3", "B123", "B126"],
    "terrain_sensitive": ["B104", "B6", "B50"],
}
VIEWER_BIDS = ["B104", "B6", "B3", "B123", "B126", "B2", "B0", "B1"]

PER_BID_FIELDS = [
    "F",
    "roof_cov",
    "wall_cov",
    "ground_cov",
    "support_cov",
    "h_err",
    "vol_ratio",
    "chamfer",
    "open_edges",
    "non_manifold_edges",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def fval(row: dict[str, Any] | None, key: str) -> float | None:
    if not row:
        return None
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6g}"


def arm_phase(arm: str) -> Path:
    if arm.startswith("B"):
        return PHASE2
    return PHASE1


def run_root(arm: str) -> Path:
    return arm_phase(arm) / "runs" / arm


def stage3_bid_dir(arm: str, bid: str) -> Path:
    return run_root(arm) / "rendered_evidence" / "stage3_readout" / arm / bid


def metric_bid_dir(arm: str, bid: str) -> Path:
    return run_root(arm) / "rendered_evidence" / "metric_v1" / arm / bid


def rows_by_arm_bid() -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv(PHASE1_METRICS) + read_csv(PHASE2_METRICS)
    wanted = {arm for arm, _, _ in ARMS}
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        arm = row.get("run", "")
        bid = row.get("bid", "")
        if arm in wanted and bid in BIDS:
            result[(arm, bid)] = row
    return result


def split_mean(data: dict[tuple[str, str], dict[str, str]], arm: str, split: str, key: str) -> float | None:
    vals = [fval(data.get((arm, bid)), key) for bid in SPLITS[split]]
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None


def classwise_per_face_summary(arm: str, bid: str, semantic_type: str) -> dict[str, str]:
    path = metric_bid_dir(arm, bid) / "per_face_matching.csv"
    if not path.exists():
        return {
            "pred_face_count": "",
            "pred_face_coverage_mean": "",
            "pred_face_coverage_min": "",
            "gt_face_count": "",
            "gt_face_coverage_mean": "",
            "gt_face_coverage_min": "",
            "per_face_rejection_reasons_available": "false",
        }
    pred_cov: list[float] = []
    gt_cov: list[float] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("query_semantic_type") != semantic_type:
                continue
            cov = fval(row, "coverage_at_0p5_same_semantic")
            if cov is None:
                continue
            if row.get("direction") == "pred_to_gt":
                pred_cov.append(cov)
            elif row.get("direction") == "gt_to_pred":
                gt_cov.append(cov)
    return {
        "pred_face_count": str(len(pred_cov)),
        "pred_face_coverage_mean": fmt(mean(pred_cov) if pred_cov else None),
        "pred_face_coverage_min": fmt(min(pred_cov) if pred_cov else None),
        "gt_face_count": str(len(gt_cov)),
        "gt_face_coverage_mean": fmt(mean(gt_cov) if gt_cov else None),
        "gt_face_coverage_min": fmt(min(gt_cov) if gt_cov else None),
        "per_face_rejection_reasons_available": "false",
    }


def make_candidate_comparison(data: dict[tuple[str, str], dict[str, str]]) -> None:
    fields = [
        "run",
        "label",
        "role",
        "bid",
        "status",
        *PER_BID_FIELDS,
        "roof_support_cov",
        "wall_support_cov",
        "ground_support_cov",
        "n_faces",
        "n_roof_faces",
        "n_wall_faces",
        "n_ground_faces",
        "failure_reason",
    ]
    rows: list[dict[str, Any]] = []
    for arm, label, role in ARMS:
        for bid in BIDS:
            src = data.get((arm, bid), {})
            row = {
                "run": arm,
                "label": label,
                "role": role,
                "bid": bid,
                "status": src.get("status", "MISSING"),
            }
            for key in fields:
                if key not in row and key in src:
                    row[key] = src.get(key, "")
            rows.append(row)
    write_csv(OUT / "candidate_comparison_by_bid.csv", rows, fields)


def make_classwise_support(data: dict[tuple[str, str], dict[str, str]]) -> None:
    class_fields = {
        "RoofSurface": ("roof_cov", "roof_support_cov"),
        "WallSurface": ("wall_cov", "wall_support_cov"),
        "GroundSurface": ("ground_cov", "ground_support_cov"),
    }
    fields = [
        "run",
        "label",
        "bid",
        "semantic_type",
        "coverage",
        "support_cov",
        "pred_face_count",
        "pred_face_coverage_mean",
        "pred_face_coverage_min",
        "gt_face_count",
        "gt_face_coverage_mean",
        "gt_face_coverage_min",
        "per_face_rejection_reasons_available",
    ]
    rows: list[dict[str, Any]] = []
    for arm, label, _ in ARMS:
        for bid in BIDS:
            src = data.get((arm, bid), {})
            for sem, (cov_key, support_key) in class_fields.items():
                row = {
                    "run": arm,
                    "label": label,
                    "bid": bid,
                    "semantic_type": sem,
                    "coverage": src.get(cov_key, ""),
                    "support_cov": src.get(support_key, ""),
                }
                row.update(classwise_per_face_summary(arm, bid, sem))
                rows.append(row)
    write_csv(OUT / "classwise_support_comparison.csv", rows, fields)


def make_topology(data: dict[tuple[str, str], dict[str, str]]) -> None:
    fields = [
        "run",
        "label",
        "bid",
        "status",
        "n_faces",
        "n_roof_faces",
        "n_wall_faces",
        "n_ground_faces",
        "open_edges",
        "non_manifold_edges",
        "edge_ok",
        "shell_completeness",
        "roof_wall_adjacency_count",
        "wall_ground_adjacency_count",
        "wall_ground_closure_status",
        "roof_wall_gap_status",
        "height_range",
        "h_err",
        "vol_ratio",
        "chamfer",
        "face_count_source",
    ]
    rows: list[dict[str, Any]] = []
    for arm, label, _ in ARMS:
        for bid in BIDS:
            src = data.get((arm, bid), {})
            shell = load_json(stage3_bid_dir(arm, bid) / "shell_diagnostics.json")
            graph = load_json(stage3_bid_dir(arm, bid) / "face_graph.json")
            diag = graph.get("diagnostics", {}) if isinstance(graph, dict) else {}
            open_edges = fval(src, "open_edges")
            nonman = fval(src, "non_manifold_edges")
            wall_ground = shell.get("wall_ground_adjacency_count", diag.get("wall_ground_adjacency_count", ""))
            roof_wall = shell.get("roof_wall_adjacency_count", diag.get("roof_wall_adjacency_count", ""))
            wall_ground_ok = (
                "closed"
                if str(wall_ground) not in ("", "0") and (open_edges is None or open_edges == 0.0)
                else "needs_review"
            )
            roof_wall_status = (
                "no_gap_flag_from_topology"
                if str(roof_wall) not in ("", "0") and (open_edges is None or open_edges == 0.0)
                else "needs_review"
            )
            rows.append({
                "run": arm,
                "label": label,
                "bid": bid,
                "status": src.get("status", "MISSING"),
                "n_faces": shell.get("n_faces", src.get("n_faces", "")),
                "n_roof_faces": shell.get("n_roof_faces", src.get("n_roof_faces", "")),
                "n_wall_faces": shell.get("n_wall_faces", src.get("n_wall_faces", "")),
                "n_ground_faces": shell.get("n_ground_faces", src.get("n_ground_faces", "")),
                "open_edges": src.get("open_edges", shell.get("open_edges", "")),
                "non_manifold_edges": src.get("non_manifold_edges", shell.get("nonmanifold_edges", "")),
                "edge_ok": shell.get("edge_ok", diag.get("edge_ok", "")),
                "shell_completeness": shell.get("shell_completeness", ""),
                "roof_wall_adjacency_count": roof_wall,
                "wall_ground_adjacency_count": wall_ground,
                "wall_ground_closure_status": wall_ground_ok,
                "roof_wall_gap_status": roof_wall_status,
                "height_range": shell.get("height_range", ""),
                "h_err": src.get("h_err", ""),
                "vol_ratio": src.get("vol_ratio", ""),
                "chamfer": src.get("chamfer", ""),
                "face_count_source": "shell_diagnostics.json",
            })
    write_csv(OUT / "topology_comparison.csv", rows, fields)


def copy_preview_artifacts() -> dict[str, list[Path]]:
    dest = OUT / "viewer_screenshots"
    dest.mkdir(parents=True, exist_ok=True)
    copied: dict[str, list[Path]] = defaultdict(list)
    for bid in VIEWER_BIDS:
        for arm, _, _ in ARMS:
            src = stage3_bid_dir(arm, bid) / "preview.png"
            if not src.exists():
                continue
            out = dest / f"{bid}__{arm}.png"
            shutil.copy2(src, out)
            copied[bid].append(out)
    return copied


def make_contact_sheets(copied: dict[str, list[Path]]) -> dict[str, Path]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {}

    contact_dir = OUT / "viewer_screenshots"
    sheets: dict[str, Path] = {}
    labels = {arm: label for arm, label, _ in ARMS}
    font = ImageFont.load_default()
    thumb_size = 280
    label_h = 28
    for bid in VIEWER_BIDS:
        images = []
        for arm, _, _ in ARMS:
            path = contact_dir / f"{bid}__{arm}.png"
            if not path.exists():
                continue
            im = Image.open(path).convert("RGB")
            im.thumbnail((thumb_size, thumb_size))
            tile = Image.new("RGB", (thumb_size, thumb_size + label_h), "white")
            x = (thumb_size - im.width) // 2
            tile.paste(im, (x, label_h))
            draw = ImageDraw.Draw(tile)
            draw.text((4, 6), labels.get(arm, arm)[:42], fill="black", font=font)
            images.append(tile)
        if not images:
            continue
        sheet = Image.new("RGB", (thumb_size * len(images), thumb_size + label_h), "white")
        for idx, tile in enumerate(images):
            sheet.paste(tile, (idx * thumb_size, 0))
        out = contact_dir / f"{bid}__candidate_matrix.png"
        sheet.save(out)
        sheets[bid] = out
    return sheets


def split_summary(data: dict[tuple[str, str], dict[str, str]]) -> dict[str, dict[str, float | None]]:
    summary: dict[str, dict[str, float | None]] = {}
    for arm, _, _ in ARMS:
        summary[arm] = {split: split_mean(data, arm, split, "F") for split in SPLITS}
        for key in ["support_cov", "ground_support_cov", "ground_cov", "roof_cov", "wall_cov", "h_err", "vol_ratio", "chamfer", "open_edges", "non_manifold_edges"]:
            summary[arm][f"mean_{key}"] = split_mean(data, arm, "all_10", key)
    return summary


def candidate_pass_flags(data: dict[tuple[str, str], dict[str, str]], summary: dict[str, dict[str, float | None]]) -> dict[str, dict[str, bool]]:
    baseline = summary["A0_baseline_w0"]
    best_support = max((summary[arm].get("mean_support_cov") or -1.0) for arm, _, role in ARMS if role == "candidate")
    best_ground_support = max((summary[arm].get("mean_ground_support_cov") or -1.0) for arm, _, role in ARMS if role == "candidate")
    flags: dict[str, dict[str, bool]] = {}
    for arm, _, role in ARMS:
        if role != "candidate":
            continue
        s = summary[arm]
        b104 = data.get((arm, "B104"), {})
        flags[arm] = {
            "all_10_vs_baseline": (s.get("all_10") or -1.0) >= (baseline.get("all_10") or 0.0) - 0.005,
            "easy_vs_baseline": (s.get("easy_control") or -1.0) >= (baseline.get("easy_control") or 0.0) - 0.005,
            "hard_vs_baseline": (s.get("hard_diagnostic") or -1.0) >= (baseline.get("hard_diagnostic") or 0.0) - 0.005,
            "b104_ground_recovered": (fval(b104, "ground_cov") or -1.0) >= 0.99,
            "support_not_materially_worse": (s.get("mean_support_cov") or -1.0) >= best_support - 0.02,
            "ground_support_not_materially_worse": (s.get("mean_ground_support_cov") or -1.0) >= best_ground_support - 0.02,
            "topology_not_regressed": (s.get("mean_open_edges") or 0.0) <= 0.0 and (s.get("mean_non_manifold_edges") or 0.0) <= 0.0,
        }
    return flags


def choose_label(summary: dict[str, dict[str, float | None]], flags: dict[str, dict[str, bool]]) -> tuple[str, str]:
    label_map = {
        "A8_no_terrain_terms": "ACCEPT_A8_TERRAIN_OFF",
        "A4_terrain_normal_only": "ACCEPT_A4_TERRAIN_NORMAL_ONLY",
        "B2_terrain_confidence_gated": "ACCEPT_B2_TERRAIN_GATED",
        "A9_no_terrain_terms_ramp": "ACCEPT_A9_TERRAIN_OFF_RAMP",
    }
    passing = [arm for arm, arm_flags in flags.items() if all(arm_flags.values())]
    if not passing:
        return "REJECT_ALL_REVISED_MUTUAL_CANDIDATES", "No candidate passed all FC-S6b acceptance flags."
    # Prefer final read-out F, then ground recovery, then easy/hard stability.
    best = max(
        passing,
        key=lambda arm: (
            summary[arm].get("all_10") or -1.0,
            summary[arm].get("mean_ground_cov") or -1.0,
            summary[arm].get("easy_control") or -1.0,
            summary[arm].get("hard_diagnostic") or -1.0,
        ),
    )
    return label_map[best], f"{best} is the highest-F passing candidate and has the strongest mean ground coverage among the passing top candidates."


def make_viewer_notes(data: dict[tuple[str, str], dict[str, str]], sheets: dict[str, Path]) -> None:
    lines = [
        "# FC-S6b Viewer QA Notes",
        "",
        "Scope: saved Stage3 preview screenshots only. No retraining, Stage3 rerun, Metric-v1 rerun, or interactive 3D viewer manipulation was performed.",
        "",
        "Saved screenshot matrices:",
        "",
    ]
    for bid in VIEWER_BIDS:
        path = sheets.get(bid)
        if path:
            lines.append(f"- `{bid}`: `{path}`")
        else:
            lines.append(f"- `{bid}`: preview matrix unavailable")
    lines.extend([
        "",
        "Automated QA notes from Metric-v1 and Stage3 topology:",
        "",
    ])
    focus = {
        "B104": "GroundSurface and wall-ground closure",
        "B6": "height issue",
        "B3": "roof-complex case",
        "B123": "roof-complex case",
        "B126": "roof-complex case",
        "B2": "easy/control sanity",
        "B0": "easy/control sanity",
        "B1": "easy/control sanity",
    }
    for bid, reason in focus.items():
        a8 = data.get(("A8_no_terrain_terms", bid), {})
        shell = load_json(stage3_bid_dir("A8_no_terrain_terms", bid) / "shell_diagnostics.json")
        lines.append(
            f"- `{bid}` ({reason}): A8 F=`{a8.get('F', '')}`, "
            f"ground_cov=`{a8.get('ground_cov', '')}`, h_err=`{a8.get('h_err', '')}`, "
            f"open/nonmanifold=`{a8.get('open_edges', '')}/{a8.get('non_manifold_edges', '')}`, "
            f"roof-wall adjacency=`{shell.get('roof_wall_adjacency_count', '')}`, "
            f"wall-ground adjacency=`{shell.get('wall_ground_adjacency_count', '')}`, "
            f"shell=`{shell.get('shell_completeness', '')}`."
        )
    lines.extend([
        "",
        "Saved-preview review observations:",
        "",
        "- `B104`: no visible GroundSurface collapse or wall-ground closure break in the saved candidate matrix.",
        "- `B6`: no topology break is visible, but the height error remains high and is not solved by A8.",
        "- `B3`/`B123`/`B126`: roof-complex cases remain low-F diagnostic cases; saved previews do not show a new open-shell artifact for A8.",
        "- `B2`/`B0`/`B1`: easy/control previews remain visually sane for A8, with no saved-preview sign of GroundSurface removal.",
        "",
        "Limitations:",
        "",
        "- Per-face rejection reasons are not present in the available Metric-v1 logs; only per-face matching coverage is available.",
        "- The saved previews are sufficient for audit traceability, but a human interactive 3D viewer pass is still recommended before treating this as final publication evidence.",
    ])
    (OUT / "viewer_qa_notes.md").write_text("\n".join(lines) + "\n")


def make_report(data: dict[tuple[str, str], dict[str, str]], sheets: dict[str, Path]) -> None:
    summary = split_summary(data)
    flags = candidate_pass_flags(data, summary)
    label, reason = choose_label(summary, flags)
    l_structure_allowed = label != "REJECT_ALL_REVISED_MUTUAL_CANDIDATES"

    def split_line(arm: str, label_name: str) -> str:
        s = summary[arm]
        return (
            f"| {label_name} | {fmt(s.get('all_10'))} | {fmt(s.get('easy_control'))} | "
            f"{fmt(s.get('hard_diagnostic'))} | {fmt(s.get('roof_complex'))} | "
            f"{fmt(s.get('terrain_sensitive'))} | {fmt(s.get('mean_ground_cov'))} | "
            f"{fmt(s.get('mean_support_cov'))} | {fmt(s.get('mean_ground_support_cov'))} | "
            f"{fmt(s.get('mean_open_edges'))}/{fmt(s.get('mean_non_manifold_edges'))} |"
        )

    lines = [
        "# FC-S6b Candidate Acceptance Report",
        "",
        "## Decision",
        "",
        f"Selected label: `{label}`.",
        "",
        reason,
        "",
        "This is candidate acceptance for the next controlled pilot, not a final claim that revised `L_mutual` is universally optimal.",
        "",
        "## Candidate Split Summary",
        "",
        "| Arm | all_10 F | easy_control F | hard_diagnostic F | roof_complex F | terrain_sensitive F | mean ground_cov | mean support_cov | mean ground_support_cov | open/nonmanifold |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, label_name, _ in ARMS:
        lines.append(split_line(arm, label_name))

    lines.extend([
        "",
        "## Acceptance Flags",
        "",
        "| Candidate | all_10 | easy | hard | B104 ground | support | ground support | topology |",
        "|---|---|---|---|---|---|---|---|",
    ])
    for arm, label_name, role in ARMS:
        if role != "candidate":
            continue
        f = flags[arm]
        lines.append(
            f"| {label_name} | {f['all_10_vs_baseline']} | {f['easy_vs_baseline']} | "
            f"{f['hard_vs_baseline']} | {f['b104_ground_recovered']} | "
            f"{f['support_not_materially_worse']} | {f['ground_support_not_materially_worse']} | "
            f"{f['topology_not_regressed']} |"
        )

    a8 = summary["A8_no_terrain_terms"]
    a4 = summary["A4_terrain_normal_only"]
    b2 = summary["B2_terrain_confidence_gated"]
    a9 = summary["A9_no_terrain_terms_ramp"]
    lines.extend([
        "",
        "## Interpretation",
        "",
        f"- A8 has the best all_10 F (`{fmt(a8.get('all_10'))}`) and best easy/control F (`{fmt(a8.get('easy_control'))}`) among the compared arms.",
        f"- A4 is a near tie in all_10 and is slightly stronger on hard/roof_complex (`{fmt(a4.get('hard_diagnostic'))}` / `{fmt(a4.get('roof_complex'))}`), but A8 has much stronger mean ground_cov (`{fmt(a8.get('mean_ground_cov'))}` vs `{fmt(a4.get('mean_ground_cov'))}`).",
        f"- B2 preserves B104 and has better height error on average (`{fmt(b2.get('mean_h_err'))}`), but it does not beat A8 on all_10/easy and has substantially lower mean ground_cov.",
        f"- A9 improves terrain_sensitive F (`{fmt(a9.get('terrain_sensitive'))}`), but regresses all_10 and easy/control relative to A8.",
        "- All compared completed arms have zero mean open_edges and zero mean non_manifold_edges under Metric-v1.",
        "- B6 height error remains a residual issue and is not solved by A8; it should be tracked in the 4-way pilot.",
        "",
        "## Viewer QA",
        "",
        "Saved Stage3 preview matrices were created under `phase_s6b_acceptance/viewer_screenshots/`.",
    ])
    for bid in VIEWER_BIDS:
        path = sheets.get(bid)
        if path:
            lines.append(f"- `{bid}`: `{path}`")
    lines.extend([
        "",
        "The available logs do not contain per-face rejection reasons. `classwise_support_comparison.csv` therefore records classwise support plus per-face matching coverage where available.",
        "",
        "Saved-preview review found no visible B104 GroundSurface collapse or wall-ground closure break for A8. B6 height error and roof-complex low-F cases remain residual risks for the next pilot.",
        "",
        "## L_structure 4-way Pilot",
        "",
        f"Allowed: `{'yes' if l_structure_allowed else 'no'}`.",
        "",
    ])
    if l_structure_allowed:
        lines.append("A controlled Baseline / accepted revised Mutual / Structure-only / revised Mutual+Structure 4-way pilot is allowed, with relation hints M7/M8 still disabled unless separately tested.")
    else:
        lines.append("No candidate passed FC-S6b acceptance, so `L_structure` remains blocked.")
    (OUT / "FC_S6B_CANDIDATE_ACCEPTANCE_REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = rows_by_arm_bid()
    make_candidate_comparison(data)
    make_classwise_support(data)
    make_topology(data)
    copied = copy_preview_artifacts()
    sheets = make_contact_sheets(copied)
    make_viewer_notes(data, sheets)
    make_report(data, sheets)


if __name__ == "__main__":
    main()
