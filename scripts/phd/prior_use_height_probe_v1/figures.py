"""Standalone scientific figures for the conditional, discrete height probe.

This module plots supplied measurements and decisions; it does not load imagery,
recompute scores, choose a favorable parameter setting, or assign current-use
actions.  Representatives are the first rows of each observed transition in the
caller's complete configuration order.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


_STATE_LABELS = {
    "SCORE_PASS": "Score pass",
    "SCORE_FAIL": "Score fail",
    "UNTESTABLE": "Untestable",
    "MODEL_MISMATCH": "Model mismatch",
    "UNRESOLVED_BOUNDARY": "Unresolved boundary",
    "GRID_CONDITIONAL_SUPPORT": "Grid conditional support",
    "GRID_OPPOSITION": "Grid opposition",
    "GRID_UNRESOLVED": "Grid unresolved",
}
_BAND_COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7")


def _number(value: Any) -> str:
    if value is None:
        return "NA"
    value = float(value)
    if not np.isfinite(value):
        return "NA"
    return f"{value:.3g}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _group_label(index: int, groups: list) -> str:
    group = groups[index]
    label = f"G{index:03d}"
    if isinstance(group, dict) and "patch_id" in group:
        label += f" | patch {group['patch_id']}"
    return label


def _save(fig: Any, output: Path, stem: str) -> dict[str, str]:
    paths = {}
    for extension in ("png", "pdf"):
        path = output / f"{stem}.{extension}"
        fig.savefig(path, dpi=200, facecolor="white", bbox_inches="tight")
        paths[extension] = str(path)
    return paths


def make_figures(
    output: Path,
    heights: np.ndarray,
    curves: dict[str, np.ndarray],
    groups: list,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write all-group and representative PNG/PDF figures; return a JSON-safe manifest.

    ``curves`` maps angle maxima (e.g. "20", "60") to [height, group] median
    ZNCC arrays.  ``rows`` follows the full sensitivity configuration order and
    contains group_index, angle_max_deg, threshold, tolerance_m, extent_m,
    baseline, decision, common_pairs, candidate_score, B, U,
    compatible_heights_m, and intervals_m.  The rows and measurements are not
    modified.  Paths in the manifest have the same absolute/relative convention
    as ``output``.  Source photographs are deliberately handled by the caller.
    """
    import matplotlib

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    heights = np.asarray(heights, dtype=np.float64)
    if heights.ndim != 1 or len(heights) < 2 or not np.isfinite(heights).all():
        raise ValueError("heights must contain at least two finite grid positions")
    if not np.all(np.diff(heights) > 0):
        raise ValueError("height grid must be strictly increasing")
    if not groups or not curves:
        raise ValueError("at least one group and one angle-band curve are required")
    n_groups = len(groups)
    bands = sorted(curves, key=float)
    data = {}
    for band in bands:
        data[band] = np.asarray(curves[band], dtype=np.float64)
        if data[band].shape != (len(heights), n_groups):
            raise ValueError(f"curve {band}: expected [H, G] shape")
        if np.isinf(data[band]).any():
            raise ValueError(f"curve {band}: infinity is not a missing-score representation")

    representatives = []
    seen = set()
    for row_index, row in enumerate(rows):
        group = int(row["group_index"])
        band = format(float(row["angle_max_deg"]), "g")
        if not 0 <= group < n_groups or band not in data:
            raise ValueError(f"comparison row {row_index}: group or angle band not found")
        transition = (str(row["baseline"]), str(row["decision"]))
        if transition not in seen:
            seen.add(transition)
            representatives.append((row_index, row))

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    colors = {band: _BAND_COLORS[i % len(_BAND_COLORS)] for i, band in enumerate(bands)}
    xmin, xmax = float(heights[0]), float(heights[-1])
    manifest: dict[str, Any] = {
        "schema": "jointbuildgs.phd.prior_use_height_probe.figures.v1",
        "scientific_verdict": None,
        "full_current_use_action": None,
        "representative_selection": "first row per observed baseline -> decision transition in input row order",
        "n_comparison_rows": len(rows),
        "n_groups": n_groups,
        "angle_bands_deg": [float(band) for band in bands],
        "representatives": [],
        "interpretation": "conditional discrete-grid diagnostics; visibility unverified; lines are visual guides",
    }
    style = {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "medium",
        "axes.linewidth": 0.6,
        "pdf.fonttype": 42,
    }
    with plt.rc_context(style):
        ncols = min(8, n_groups)
        nrows = (n_groups + ncols - 1) // ncols
        fig, axes = plt.subplots(
            nrows, ncols, figsize=(2.7 * ncols, 2.05 * nrows + 1.5),
            sharex=True, sharey=True, squeeze=False,
        )
        for gi, ax in enumerate(axes.flat):
            if gi >= n_groups:
                ax.set_visible(False)
                continue
            any_finite = False
            for band in bands:
                values = data[band][:, gi]
                any_finite |= bool(np.isfinite(values).any())
                ax.plot(heights, values, color=colors[band], lw=1.15, marker=".", ms=2.5)
            ax.axvline(0, color="#666666", lw=0.7, ls=":")
            ax.axhline(0, color="#D3D3D3", lw=0.5)
            ax.set(xlim=(xmin, xmax), ylim=(-1.04, 1.04), yticks=(-1, 0, 1))
            ax.set_title(_group_label(gi, groups), fontsize=8.5, loc="left", pad=4)
            ax.tick_params(labelsize=8, length=2.5)
            ax.grid(axis="y", alpha=0.16, lw=0.5)
            if not any_finite:
                ax.text(0.5, 0.5, "No common measurement", transform=ax.transAxes,
                        ha="center", va="center", color="#666666", fontsize=8)
        handles = [Line2D([0], [0], color=colors[band], lw=1.6, marker=".",
                          label=f"Pair angle <= {band} deg") for band in bands]
        fig.suptitle("Prior-only height probe: every sampled group", fontsize=16, y=0.991)
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.970),
                   ncol=min(4, len(handles)), frameon=False, fontsize=11)
        fig.supxlabel("Scene-coordinate Z offset (m)", y=0.040)
        fig.supylabel("Median ZNCC on fixed common pairs and native points", x=0.005)
        fig.text(0.5, 0.010,
                 "Dots are tested heights; lines only guide the eye. FOV checked; visibility and current geometry are unverified.",
                 ha="center", fontsize=9, color="#444444")
        fig.tight_layout(rect=(0.018, 0.055, 1, 0.94), h_pad=1.0, w_pad=0.65)
        manifest["all_groups"] = _save(fig, output, "all_group_score_curves")
        plt.close(fig)

        if representatives:
            ncols = min(2, len(representatives))
            nrows = (len(representatives) + ncols - 1) // ncols
            fig = plt.figure(figsize=(7.0 * ncols, 5.1 * nrows + 1.2))
            outer = fig.add_gridspec(nrows, ncols, left=0.07, right=0.98,
                                    top=0.91, bottom=0.055, hspace=0.31, wspace=0.22)
            for panel, (row_index, row) in enumerate(representatives):
                sub = outer[panel // ncols, panel % ncols].subgridspec(
                    2, 1, height_ratios=(3.2, 1.4), hspace=0.34)
                ax = fig.add_subplot(sub[0])
                note = fig.add_subplot(sub[1])
                note.axis("off")
                gi = int(row["group_index"])
                band = format(float(row["angle_max_deg"]), "g")
                threshold = float(row["threshold"])
                tolerance = float(row["tolerance_m"])
                extent = float(row["extent_m"])
                values = data[band][:, gi]
                accepted = np.asarray(row["compatible_heights_m"], dtype=np.float64)
                ax.axvspan(-tolerance, tolerance, color="#CCE1EE", alpha=0.52,
                           label="Candidate tolerance band")
                if -extent > xmin:
                    ax.axvspan(xmin, -extent, color="#EEEEEE", alpha=0.85)
                if extent < xmax:
                    ax.axvspan(extent, xmax, color="#EEEEEE", alpha=0.85)
                ax.plot(heights, values, color=colors[band], lw=1.4, marker=".", ms=4)
                ax.axhline(threshold, color="#555555", lw=1.0, ls="--")
                ax.axvline(0, color="#333333", lw=0.7, ls=":")
                for endpoint in (-extent, extent):
                    ax.axvline(endpoint, color="#777777", lw=0.7, ls="--")
                if len(accepted):
                    selected = np.any(np.isclose(heights[:, None], accepted[None, :],
                                                rtol=0, atol=1e-10), axis=1)
                    ax.scatter(heights[selected], values[selected], s=32,
                               facecolors="none", edgecolors="#6F3C80", linewidths=1.2,
                               zorder=4, label="Compatible tested heights K")
                if not np.isfinite(values).any():
                    ax.text(0.5, 0.5, "No common measurement", transform=ax.transAxes,
                            ha="center", va="center", fontsize=11, color="#555555")
                before = _STATE_LABELS.get(str(row["baseline"]), str(row["baseline"]))
                after = _STATE_LABELS.get(str(row["decision"]), str(row["decision"]))
                ax.set_title(f"{_group_label(gi, groups)} | angle <= {band} deg\n{before} -> {after}",
                             fontsize=11, loc="left", pad=8)
                ax.set(xlim=(xmin, xmax), ylim=(-1.04, 1.04), xlabel="Scene-coordinate Z offset (m)",
                       ylabel="Median ZNCC", yticks=(-1, -0.5, 0, 0.5, 1))
                ax.grid(axis="y", alpha=0.16, lw=0.5)
                k_range = (f"[{_number(np.min(accepted))}, {_number(np.max(accepted))}] m"
                           if len(accepted) else "empty")
                annotations = (
                    f"tau={_number(threshold)}; epsilon={_number(tolerance)} m; tested endpoints=[-{_number(extent)}, +{_number(extent)}] m\n"
                    f"S(0)={_number(row['candidate_score'])}; common pairs={int(row['common_pairs'])}; B={_number(row['B'])}; U={_number(row['U'])}\n"
                    f"K min/max: {k_range}; grid points={len(accepted)}; sampled components={len(row['intervals_m'])}\n"
                    "Blue band: +/-epsilon. Purple rings: K. Gray outside: excluded from this extent."
                )
                note.text(0, 1.0, annotations, transform=note.transAxes, va="top", fontsize=9,
                          linespacing=1.5, color="#333333")
                manifest["representatives"].append({
                    "panel_index": panel,
                    "comparison_row_index": row_index,
                    "group_label": _group_label(gi, groups),
                    "row": _json_safe(row),
                })
            fig.suptitle("First observed example of each conditional decision transition", fontsize=16, y=0.985)
            fig.text(0.5, 0.951, "Representatives follow the full configuration row order; no best-scoring setting is selected.",
                     ha="center", fontsize=10, color="#444444")
            fig.text(0.5, 0.017,
                     "Finite height grid only; lines are visual guides. Visibility is unverified. These states do not grant current-use authority.",
                     ha="center", fontsize=9, color="#444444")
            manifest["representative_figures"] = _save(fig, output, "representative_score_curves")
            plt.close(fig)
        else:
            manifest["representative_figures"] = None
    return _json_safe(manifest)
