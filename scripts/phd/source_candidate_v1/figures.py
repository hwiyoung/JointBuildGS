"""Reproducible stage/case figures from sealed source-candidate measurements.

Native points are display-subsampled only. No reference score is computed here.
Image case panels regenerate the saved camera pair and reference-pixel patches;
the regenerated costs must agree with the recorded method before export.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import textwrap

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np

from scripts.phd.source_candidate_v1.common import sha, write
from src.phd.source_candidate_v1.geometry import self_depth_buffer
from src.phd.source_candidate_v1.photometry import (
    ScoringConfig, _prepare_candidate, _patch_pixels, _warp, _sample_gray, _cost,
    _intersect, project,
)


BLUE, ORANGE, GRAY, INK = "#2878B5", "#E18A26", "#B2B5B9", "#252A30"
COLORS = {"mvs": BLUE, "als": ORANGE, "IMAGE": BLUE, "PRIOR": ORANGE, "ABSTAIN": GRAY}
ACTION_CODE = {"ABSTAIN": 0, "IMAGE": 1, "PRIOR": 2}
LABELS = {"mvs": "Current MVS", "als": "Existing ALS"}
DIVERGING = LinearSegmentedColormap.from_list("als_equal_mvs", [ORANGE, "#FAFAFA", BLUE])
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.labelcolor": INK, "text.color": INK, "axes.titleweight": "semibold",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.facecolor": "white", "figure.facecolor": "white"})


def read(path):
    return json.loads(Path(path).read_text())


def finite(value):
    return value is not None and np.isfinite(value)


def fmt(value, digits=3):
    return f"{value:.{digits}f}" if finite(value) else "NA"


def empty(ax, message):
    ax.text(.5, .5, message, ha="center", va="center", transform=ax.transAxes,
            color="#5E6369", wrap=True)
    ax.set_xticks([]); ax.set_yticks([])


def sample(points, maximum=20000):
    if len(points) <= maximum:
        return points
    return points[np.linspace(0, len(points)-1, maximum, dtype=int)]


def save(fig, output, stem, manifest, contract, case=None):
    records = []
    for suffix in ("png", "pdf"):
        path = output / f"{stem}.{suffix}"
        if path.exists():
            raise FileExistsError(path)
        fig.savefig(path, dpi=180, bbox_inches="tight")
        records.append({"path": str(path), "sha256": sha(path), "format": suffix})
    plt.close(fig)
    manifest["figures"].append({"id": stem, "files": records, "chart_contract": contract,
                                "case": case})


def legend_sources(ax, actions=False):
    names = ("IMAGE", "PRIOR", "ABSTAIN") if actions else ("mvs", "als")
    markers = ("o", "^", "s") if actions else ("o", "^")
    ax.legend(handles=[Line2D([], [], color=COLORS[n], marker=m, ls="", markersize=5,
                             label=n if actions else LABELS[n]) for n, m in zip(names, markers)],
              fontsize=8, loc="best", frameon=False)


def grid_values(rows, values):
    shape = (max(r["iy"] for r in rows)+1, max(r["ix"] for r in rows)+1)
    grid = np.full(shape, np.nan)
    for row, value in zip(rows, values, strict=True):
        if finite(value):
            grid[row["iy"], row["ix"]] = value
    return grid


def cellmap(ax, rows, values, title, domain, cmap="Blues", limits=None, colorbar_label=None):
    image = ax.imshow(grid_values(rows, values), origin="lower", interpolation="none", cmap=cmap,
                      extent=[*domain["x"], *domain["y"]],
                      vmin=limits[0] if limits else None, vmax=limits[1] if limits else None)
    ax.set(title=title, xlabel="Scene-local X (m)", ylabel="Scene-local Y (m)")
    ax.set_aspect("equal")
    if colorbar_label:
        ax.figure.colorbar(image, ax=ax, fraction=.045, pad=.025, label=colorbar_label)
    return image


def summary(regions, output, manifest):
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), layout="constrained")
    stages = ["All census cells", "Both planes valid", "Matched observations", "Source accepted"]
    bar_width = .19
    x = np.arange(len(regions))
    tones = ["#E3E5E7", "#A7BACB", "#608FBA", BLUE]
    for j, stage in enumerate(stages):
        values = []
        for data in regions.values():
            obs = data["observations"].values()
            values.append([len(data["rows"]), sum(r["both_valid"] for r in data["rows"]),
                sum(o["shared"]["common_scored_pair_count"] >= 3
                    and o["shared"]["distinct_view_count"] >= 4
                    and o["shared"]["disjoint_pair_count"] >= 2 for o in obs),
                sum(d["accepted"] for d in data["decisions"].values())][j])
        bars = axes[0].bar(x+(j-1.5)*bar_width, values, bar_width, color=tones[j],
                           label=stage, edgecolor=INK, linewidth=.4)
        axes[0].bar_label(bars, fontsize=8, padding=2)
    axes[0].set(xticks=x, xticklabels=list(regions), ylabel="Number of fixed 2 m cells",
                title="Candidate input → observation evaluation → source judgment")
    axes[0].legend(fontsize=8, frameon=False, loc="upper left")
    axes[0].set_ylim(0, max(len(d["rows"]) for d in regions.values())*1.28)
    bottom = np.zeros(len(regions))
    for action in ("IMAGE", "PRIOR", "ABSTAIN"):
        values = np.array([sum(d["action"] == action for d in data["decisions"].values())
                           for data in regions.values()])
        axes[1].bar(x, values, bottom=bottom, color=COLORS[action], width=.6,
                    label=action, edgecolor="white", linewidth=.5)
        for xi, n, base in zip(x, values, bottom):
            if n > 0:
                axes[1].text(xi, base+n/2, str(n), ha="center", va="center", fontsize=9)
        bottom += values
    axes[1].set(xticks=x, xticklabels=list(regions), ylabel="Number of fixed 2 m cells",
                title="Source decisions on the complete census")
    axes[1].legend(frameon=False, fontsize=9)
    fig.suptitle("P1 / P2 / P3 source-candidate development evaluation", fontsize=15)
    fig.supxlabel("Matched: ≥3 common pairs, ≥4 views and ≥2 disjoint camera pairs. No GS run; no temporal-change certification.", fontsize=9)
    save(fig, output, "00_stage_summary", manifest,
         {"question": "How much of the full spatial census reaches each stage?",
          "family": "grouped and stacked stage bars", "grain": "region x fixed 2 m cell",
          "denominator": "all cells, including invalid or missing candidates", "reference_used": False})


def overview(region, data, config, output, manifest):
    rows, observations, decisions = data["rows"], data["observations"], data["decisions"]
    domain = config["regions"][region]["domain"]
    fig, axes = plt.subplots(2, 3, figsize=(16.5, 10.8), layout="constrained")
    for source, marker in (("mvs", "."), ("als", "^")):
        xyz = sample(data["native"][source+"_xyz"])
        axes[0, 0].scatter(xyz[:, 0], xyz[:, 1], s=2 if source == "mvs" else 4,
                           color=COLORS[source], alpha=.45, marker=marker, rasterized=True,
                           label=f"{LABELS[source]}: {len(data['native'][source+'_xyz']):,} native points")
    axes[0, 0].set(title="1. Candidate input: native point support", xlabel="Scene-local X (m)", ylabel="Scene-local Y (m)")
    axes[0, 0].set_aspect("equal"); axes[0, 0].legend(fontsize=8, frameon=False)
    gaps = [r["height_difference_m"] for r in rows]
    limit = max([abs(v) for v in gaps if finite(v)] or [1.])
    cellmap(axes[0, 1], rows, gaps, "1. Native-plane height difference", domain,
            DIVERGING, (-limit, limit), "MVS minus ALS along estimated up (m)")
    counts = [observations[r["cell_id"]]["shared"]["common_scored_pair_count"] for r in rows]
    cellmap(axes[0, 2], rows, counts, "2. Common scored camera pairs", domain,
            limits=(0, config["photometry"]["max_pairs"]), colorbar_label="Camera-pair count")
    good = [(r, observations[r["cell_id"]]) for r in rows
            if all(finite(observations[r["cell_id"]]["candidates"][s]["cost"]) for s in ("mvs", "als"))]
    ax = axes[1, 0]
    if good:
        for action, marker in (("IMAGE", "o"), ("PRIOR", "^"), ("ABSTAIN", "s")):
            subset = [(r, o) for r, o in good if decisions[r["cell_id"]]["action"] == action]
            ax.scatter([o["candidates"]["mvs"]["cost"] for _, o in subset],
                       [o["candidates"]["als"]["cost"] for _, o in subset],
                       color=COLORS[action], marker=marker, s=18, alpha=.75)
        ax.plot([0, 1], [0, 1], "--", color=INK, lw=.8)
        ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="MVS median pair cost", ylabel="ALS median pair cost")
        legend_sources(ax, actions=True)
    else:
        empty(ax, "No common photometric scores")
    ax.set_title(f"2. Matched source costs: {len(good)} cells\nCost = (1 − ZNCC) / 2; lower is better")
    cellmap(axes[1, 1], rows, [ACTION_CODE[decisions[r["cell_id"]]["action"]] for r in rows],
            "3. Conditional source judgment", domain, ListedColormap([GRAY, BLUE, ORANGE]), (-.5, 2.5))
    legend_sources(axes[1, 1], actions=True)
    evaluated = [v for v in data["evaluation"].values()
                 if v.get("action") in {"IMAGE", "PRIOR"}
                 and finite(v.get("mvs_error_m")) and finite(v.get("als_error_m"))]
    ax = axes[1, 2]
    if evaluated:
        maximum = max(max(r["mvs_error_m"], r["als_error_m"]) for r in evaluated)*1.06
        maximum = max(maximum, .1)
        for action, marker in (("IMAGE", "o"), ("PRIOR", "^")):
            subset = [r for r in evaluated if r["action"] == action]
            ax.scatter([r["mvs_error_m"] for r in subset], [r["als_error_m"] for r in subset],
                       color=COLORS[action], marker=marker, s=25, alpha=.85)
        ax.plot([0, maximum], [0, maximum], "--", color=INK, lw=.8)
        ax.set(xlim=(0, maximum), ylim=(0, maximum), xlabel="MVS symmetric mean NN error (m)", ylabel="ALS symmetric mean NN error (m)")
        legend_sources(ax, actions=True)
    else:
        empty(ax, "No accepted cells with paired reference evaluation")
    ax.set_title(f"3. Evaluation on the same accepted cells: n={len(evaluated)}\nReference read only after method freeze")
    fig.suptitle(f"{region}: stage-by-stage source-candidate evidence", fontsize=16)
    fig.supxlabel("Scene-local coordinates, EPSG:25832 lineage. Display sampling does not alter native membership or scores. Missing cells are retained.", fontsize=9)
    save(fig, output, region+"_stage_overview", manifest,
         {"question": "Where does source disagreement become measurable or remain unresolved?",
          "family": "native support scatter, fixed-cell maps, matched cost/error scatter",
          "grain": "fixed 2 m cell", "native_display_cap_per_source": 20000,
          "evaluation_subset": "accepted cells with both reference error fields present",
          "evaluation_is_post_freeze": True})


def select_cases(data):
    chosen = {}
    def add(cell, reason):
        chosen.setdefault(int(cell), []).append(reason)
    for action in ("IMAGE", "PRIOR", "ABSTAIN"):
        candidates = [cid for cid, d in data["decisions"].items() if d["action"] == action]
        if candidates:
            add(min(candidates), "PRE_REFERENCE_FIRST_"+action)
    scored_abstentions = [cid for cid, d in data["decisions"].items() if d["action"] == "ABSTAIN"
                          and data["observations"][cid]["shared"]["common_scored_pair_count"] > 0]
    if scored_abstentions:
        add(min(scored_abstentions), "PRE_REFERENCE_FIRST_SCORED_ABSTAIN")
    with_gap = [r for r in data["rows"] if finite(r["height_difference_m"])]
    if with_gap:
        add(max(with_gap, key=lambda r: (abs(r["height_difference_m"]), -r["cell_id"]))["cell_id"],
            "PRE_REFERENCE_MAX_ABSOLUTE_SOURCE_HEIGHT_GAP")
    evaluated = [r for r in data["evaluation"].values() if r.get("action") in {"IMAGE", "PRIOR"}
                 and finite(r.get("regret_m"))]
    if evaluated:
        add(max(evaluated, key=lambda r: (r["regret_m"], -r["cell_id"]))["cell_id"],
            "POST_REFERENCE_MAX_ACCEPTED_REGRET_DIAGNOSTIC")
    return chosen


def load_view(metadata):
    R, t = np.asarray(metadata["R"], float), np.asarray(metadata["t"], float)
    gray = cv2.imread(metadata["path"], cv2.IMREAD_GRAYSCALE)
    rgb = cv2.imread(metadata["path"], cv2.IMREAD_COLOR)
    if gray is None or rgb is None or gray.shape != (metadata["height"], metadata["width"]):
        raise ValueError("Original image missing or dimensions changed: "+metadata["path"])
    if sha(metadata["path"]) != metadata["sha256"]:
        raise ValueError("Original image identity changed: "+metadata["path"])
    return dict(id=metadata["image_id"], R=R, t=t, K=np.asarray(metadata["K"], float),
                center=-R.T@t, width=metadata["width"], height=metadata["height"],
                gray=gray.astype(np.float32), rgb=cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB),
                path=metadata["path"], name=metadata["name"], sha256=metadata["sha256"])


def warp_evidence(data, row, observation, config):
    sources = observation["candidates"]
    pairs_by_source = {s: {p["pair_id"]: p for p in sources[s]["pairs"]} for s in ("mvs", "als")}
    pairs = [p for p in observation["shared"]["selected_pairs"]
             if all(finite(pairs_by_source[s].get(p["pair_id"], {}).get("cost")) for s in ("mvs", "als"))]
    if not pairs:
        return None
    selected = pairs[0]  # Geometry-defined saved ordering; no reference or score ranking.
    cfg = ScoringConfig(**observation["config"])
    metadata = {str(v["image_id"]): v for v in data["views"]}
    views = [load_view(metadata[str(selected[k])]) for k in ("reference_id", "target_id")]
    prepared = {}
    for source in ("mvs", "als"):
        mask = ((data["membership"][source+"_cell"] == row["cell_id"])
                & data["membership"][source+"_inlier"])
        candidate = dict(row["candidates"][source], support_points=data["native"][source+"_xyz"][mask],
            context_depths={v["id"]: self_depth_buffer(data["native"][source+"_xyz"], v,
                config["self_visibility"]["downsample"], config["self_visibility"]["splat_radius"]) for v in views})
        prepared[source] = _prepare_candidate(candidate, cfg)
    centers = pairs_by_source["mvs"][selected["pair_id"]]["reference_pixel_centers"]
    pixels = _patch_pixels(views[0], prepared, cfg, centers)
    reference = _sample_gray(pixels, views[0], cfg)
    warps = {s: _warp(pixels, *views, prepared[s], cfg) for s in ("mvs", "als")}
    common = warps["mvs"]["valid"] & warps["als"]["valid"]
    costs = {}
    for source in ("mvs", "als"):
        values, _, _ = _cost(reference, warps[source]["values"], common, cfg)
        costs[source] = values
        recorded = pairs_by_source[source][selected["pair_id"]]["cost"]
        recomputed = float(np.nanmedian(values))
        if not np.isclose(recorded, recomputed, atol=1e-6, rtol=0):
            raise ValueError(f"Saved/recomputed patch scores disagree: {source} {recorded} vs {recomputed}")
    scored = np.isfinite(costs["mvs"]) & np.isfinite(costs["als"])
    choices = np.where(scored, common.sum(1), -1)
    anchor = int(np.argmax(choices))
    target_pixels = {}
    for source in ("mvs", "als"):
        xyz, _ = _intersect(pixels[anchor:anchor+1], views[0], prepared[source], 0, cfg)
        target_pixels[source] = project(xyz, views[1])[0][0]
    return dict(pair=selected, views=views, pixels=pixels, reference=reference,
                warps=warps, common=common, costs=costs, anchor=anchor,
                target_pixels=target_pixels, cfg=cfg,
                record={"pair_id": selected["pair_id"], "anchor_index": anchor,
                        "anchor_selection": "maximum common pixels among scored anchors; ties first",
                        "reference_pixel_center": centers[anchor],
                        "same_mask_score_reproduction": "PASS_ATOL_1E-6",
                        "patch_costs": {s: float(costs[s][anchor]) for s in costs},
                        "common_pixels": int(common[anchor].sum()),
                        "images": [{"path": v["path"], "sha256": v["sha256"],
                                    "image_id": v["id"]} for v in views]})


def image_crop(ax, view, projected, title, reference=False):
    coordinates = np.concatenate(list(projected.values()))
    coordinates = coordinates[np.isfinite(coordinates).all(1)]
    if not len(coordinates):
        empty(ax, "Projection outside original image"); return
    low = np.maximum(np.floor(coordinates.min(0)-30).astype(int), 0)
    high = np.minimum(np.ceil(coordinates.max(0)+31).astype(int), [view["width"], view["height"]])
    x0, y0 = low; x1, y1 = high
    if x1 <= x0 or y1 <= y0:
        empty(ax, "Projection outside original image"); return
    ax.imshow(view["rgb"][y0:y1, x0:x1], extent=[x0-.5, x1-.5, y1-.5, y0-.5], interpolation="nearest")
    for source, points in projected.items():
        points = points[np.isfinite(points).all(1)]
        if not len(points):
            continue
        lo, hi = points.min(0), points.max(0)
        color = "white" if reference else COLORS[source]
        ax.add_patch(Rectangle(lo-.5, *(hi-lo+1), fill=False, edgecolor=color, linewidth=1.8,
                               linestyle="-" if source == "mvs" else "--"))
        ax.plot(points[len(points)//2, 0], points[len(points)//2, 1],
                marker="+" if source == "mvs" else "x", color=color, ms=8)
    ax.set(title=title, xlabel="Original calibrated pixel u", ylabel="Pixel v")


def case_figure(region, data, cell_id, reasons, config, output, manifest):
    row = next(r for r in data["rows"] if r["cell_id"] == cell_id)
    observation, decision = data["observations"][cell_id], data["decisions"][cell_id]
    evaluation = data["evaluation"].get(cell_id, {})
    evidence = warp_evidence(data, row, observation, config)
    fig = plt.figure(figsize=(16.5, 12.8), layout="constrained")
    grid = fig.add_gridspec(3, 4, height_ratios=[1., 1.2, .9])
    ax3 = fig.add_subplot(grid[0, 0], projection="3d")
    side, pair_ax, profile_ax = [fig.add_subplot(grid[0, i]) for i in range(1, 4)]
    for source, marker in (("mvs", "."), ("als", "^")):
        xyz = data["native"][source+"_xyz"][data["membership"][source+"_cell"] == cell_id]
        shown = sample(xyz, 3000)
        if len(shown):
            ax3.scatter(*shown.T, s=3, color=COLORS[source], marker=marker, rasterized=True)
            side.scatter(shown[:, 0], shown[:, 2], s=5, color=COLORS[source], marker=marker,
                         alpha=.7, label=f"{LABELS[source]}: {len(xyz)} points", rasterized=True)
    ax3.set(title="1. Native candidate XYZ (m)", xlabel="X (m)", ylabel="Y (m)", zlabel="")
    ax3.tick_params(labelsize=7); ax3.view_init(elev=25, azim=-55)
    side.set(title="1. Native X–Z projection", xlabel="Scene-local X (m)", ylabel="Scene-local Z (m)")
    handles, labels = side.get_legend_handles_labels()
    if handles:
        side.legend(fontsize=7, frameon=False)
    for source, marker in (("mvs", "o"), ("als", "^")):
        pairs = observation["candidates"][source]["pairs"]
        pair_ax.plot(np.arange(len(pairs))+1, [p["cost"] if finite(p["cost"]) else np.nan for p in pairs],
                     marker=marker, ms=3.5, color=COLORS[source], lw=.8, label=LABELS[source])
        profile = observation["candidates"][source]["profile"]
        if profile:
            profile_ax.plot([p["offset_m"] for p in profile],
                            [p.get("paired_delta_cost") if finite(p.get("paired_delta_cost")) else np.nan for p in profile],
                            marker=marker, ms=4, color=COLORS[source], label=LABELS[source])
    pair_ax.set(title="2. Exact matched camera-pair costs", xlabel="Saved geometry-selected pair order", ylabel="Cost (lower is better)", ylim=(0, 1))
    pair_ax.legend(fontsize=7, frameon=False)
    profile_ax.axhline(0, color=INK, ls="--", lw=.8)
    profile_ax.set(title="2. Matched-mask geometric controls", xlabel="Candidate normal shift (m)", ylabel="Shifted minus nominal cost")
    profile_ax.legend(fontsize=7, frameon=False)
    ref_ax, target_ax = fig.add_subplot(grid[1, :2]), fig.add_subplot(grid[1, 2:])
    patch_axes = [fig.add_subplot(grid[2, i]) for i in range(4)]
    if evidence is not None:
        a, width = evidence["anchor"], evidence["cfg"].patch_width
        image_crop(ref_ax, evidence["views"][0], {"mvs": evidence["pixels"][a]},
                   "2. Original anchor image: "+evidence["views"][0]["name"], reference=True)
        image_crop(target_ax, evidence["views"][1], evidence["target_pixels"],
                   f"2. Original target image ID {evidence['views'][1]['id']}: blue=MVS, orange=ALS")
        mask = evidence["common"][a].reshape(width, width)
        for ax, source in zip(patch_axes[:3], ("reference", "mvs", "als")):
            values = evidence["reference"][a] if source == "reference" else evidence["warps"][source]["values"][a]
            gray = np.repeat((values.reshape(width, width)/255.)[..., None], 3, axis=2)
            gray[~mask] = [.73, .75, .77]
            ax.imshow(np.clip(gray, 0, 1), interpolation="nearest")
            ax.set_xticks([]); ax.set_yticks([])
            label = "Current-image anchor patch" if source == "reference" else LABELS[source]+" plane warp"
            cost = "" if source == "reference" else f"; patch cost={evidence['costs'][source][a]:.3f}"
            ax.set_title(label+cost, fontsize=10)
        patch_axes[3].imshow(mask, cmap=ListedColormap([GRAY, INK]), vmin=0, vmax=1, interpolation="nearest")
        patch_axes[3].set_title(f"Exact common support: {mask.sum()}/{mask.size} pixels\nGray excluded / dark scored", fontsize=10)
        patch_axes[3].set_xticks([]); patch_axes[3].set_yticks([])
    else:
        for ax in (ref_ax, target_ax, *patch_axes):
            empty(ax, "No saved common scored pair.\nOriginal image/warp evidence is unavailable for this cell.")
    evaluation_note = (f"Post-freeze native-inlier NN errors: MVS {fmt(evaluation.get('mvs_error_m'))} m; "
        f"ALS {fmt(evaluation.get('als_error_m'))} m; selected {fmt(evaluation.get('selected_error_m'))} m; "
        f"regret {fmt(evaluation.get('regret_m'))} m; reference n={evaluation.get('reference_count', 0)}")
    fig.suptitle(f"{region} cell {cell_id} | {decision['action']} | source height gap {fmt(row['height_difference_m'])} m\n"
                 + decision["reason"]+"\n"+evaluation_note, fontsize=12)
    selection = "; ".join(reasons)
    fig.supxlabel("Case rule: "+textwrap.fill(selection, 155)+
                  "\nNative points only; no synthesized geometry. Gray patch pixels excluded. Source-model visibility is not proof of currentness.", fontsize=8)
    save(fig, output, f"{region}_case_{cell_id:04d}", manifest,
         {"question": "Which original observations support or fail this source judgment?",
          "family": "native 3D/side projection, paired cost/profile lines, original-image crops and exact plane warps",
          "grain": "one fixed cell, one saved camera pair, one shared reference-pixel patch",
          "native_display_cap_per_source": 3000, "reference_used_for_case_selection": any(r.startswith("POST_") for r in reasons)},
         {"region": region, "cell_id": cell_id, "selection_rules": reasons,
          "action": decision["action"], "reason": decision["reason"],
          "warp_evidence": evidence["record"] if evidence else None,
          "evaluation": evaluation})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution is required")
    cv2.setNumThreads(1)
    run, output = Path(args.run), Path(args.output)
    if output.exists():
        raise FileExistsError("Use a new figure output directory: "+str(output))
    output.mkdir(parents=True)
    config = read(run/"config.json")
    seal = read(run/"method_seal.json")
    for relative, expected in seal["files"].items():
        if sha(run/relative) != expected:
            raise ValueError("Method seal no longer matches "+relative)
    evaluation_path = run/"evaluation"/"per_cell.json"
    evaluation = read(evaluation_path) if evaluation_path.exists() else []
    if isinstance(evaluation, dict):
        evaluation = evaluation.get("rows", evaluation.get("cells", []))
    manifest = {"schema": "jointbuildgs.source_candidate.figures.v1", "task_id": config["task_id"],
        "scientific_verdict": None, "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"script": str(Path(__file__).resolve()), "script_sha256": sha(__file__),
                   "photometry_sha256": sha(Path("src/phd/source_candidate_v1/photometry.py")),
                   "geometry_sha256": sha(Path("src/phd/source_candidate_v1/geometry.py")),
                   "config_sha256": sha(run/"config.json"), "method_seal_sha256": sha(run/"method_seal.json"),
                   "evaluation_sha256": sha(evaluation_path) if evaluation_path.exists() else None,
                   "method_source_snapshot_sha256": seal.get("source_snapshot_sha256")},
        "palette": {"policy": "hard two-root cap plus neutrals", "current_mvs": BLUE,
                    "existing_als": ORANGE, "abstain_or_excluded": GRAY},
        "runtime_versions": {"numpy": np.__version__, "opencv": cv2.__version__,
                             "matplotlib": matplotlib.__version__},
        "limitations": ["Figures reproduce development observations, not a scientific verdict.",
                        "Point display subsampling does not alter processing/scoring/evaluation membership.",
                        "Reference errors are read from a post-freeze evaluation artifact, never recomputed here.",
                        "Maximum-regret cases are explicitly post-reference diagnostics, not representative examples."],
        "inputs": {}, "figures": []}
    regions = {}
    for region, spec in config["regions"].items():
        native_path, views_path = Path("/inputs")/region/"native.npz", Path("/inputs")/region/"views.json"
        if sha(native_path) != spec["native_sha256"] or sha(views_path) != spec["views_sha256"]:
            raise ValueError("Native input identity changed for "+region)
        with np.load(native_path, allow_pickle=False) as archive:
            native = {k: archive[k] for k in archive.files}
        with np.load(run/region/"membership.npz", allow_pickle=False) as archive:
            membership = {k: archive[k] for k in archive.files}
        regions[region] = {"native": native, "membership": membership,
            "rows": read(run/region/"candidates.json"),
            "observations": {r["cell_id"]: r["observation"] for r in read(run/region/"observations.json")},
            "decisions": {r["cell_id"]: r for r in read(run/region/"decisions.json")},
            "evaluation": {r["cell_id"]: r for r in evaluation if r["region"] == region},
            "views": read(views_path)["views"]}
        manifest["inputs"][region] = {"native_sha256": sha(native_path), "views_sha256": sha(views_path),
            "method_files": {name: sha(run/region/name) for name in
                             ("candidates.json", "membership.npz", "observations.json", "decisions.json")}}
    summary(regions, output, manifest)
    for region, data in regions.items():
        overview(region, data, config, output, manifest)
        for cell_id, reasons in select_cases(data).items():
            case_figure(region, data, cell_id, reasons, config, output, manifest)
            print(json.dumps({"region": region, "case_cell_id": cell_id, "status": "FIGURE_EXPORTED"}), flush=True)
    write(output/"figure_manifest.json", manifest)
    print(json.dumps({"status": "FIGURES_EXPORTED", "figures": len(manifest["figures"]),
                      "manifest": str(output/"figure_manifest.json"), "scientific_verdict": None}), flush=True)


if __name__ == "__main__":
    main()
