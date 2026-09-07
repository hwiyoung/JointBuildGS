"""Reaggregate preserved paired arrays on exactly matched reference membership."""
import csv
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

I = Path("/input")
O = Path("/out")
cfg = json.loads((O / "config.json").read_text())
sources = {}


def bind(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            h.update(chunk)
    value = {"sha256": h.hexdigest(), "bytes": path.stat().st_size}
    sources[str(path)] = value
    return value


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def median(x):
    good = np.asarray(x)[np.isfinite(x)]
    return float(np.median(good)) if len(good) else float("nan")


def aggregate(values, groups, count):
    out = np.full(count, np.nan)
    order = np.argsort(groups)
    g, v = groups[order], np.asarray(values)[order]
    starts = np.r_[0, np.flatnonzero(np.diff(g)) + 1]
    ends = np.r_[starts[1:], len(g)]
    for start, end in zip(starts, ends):
        out[g[start]] = median(v[start:end])
    return out


def show(ax, values, nx, ny, extent, title, vmin, vmax, cmap="RdBu_r", unit="m"):
    cm = plt.get_cmap(cmap).copy()
    cm.set_bad("#e0e3e7")
    im = ax.imshow(values.reshape(ny, nx), origin="lower", extent=extent,
                   cmap=cm, vmin=vmin, vmax=vmax, interpolation="nearest")
    ax.set(title=title, xlabel="Local X (m)", ylabel="Local Y (m)")
    plt.colorbar(im, ax=ax, shrink=.82, label=unit, extend="both")


bind(I / "receipt.json")
bind(I / "error_cohort_transitions.csv")
plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "figure.facecolor": "white"})
cell_rows, tile_rows = [], []
for rid in cfg["regions"]:
    p = I / (rid + ".paired.npz")
    bind(p)
    a = dict(np.load(p))
    e = a["strict_target_world_z_error_median"]
    strict = np.isfinite(e)
    d0 = a["reference_to_anchor_distance"]
    points = a["reference_points"]
    idx = a["xy_cell_index"]
    xy = a["xy_cell_centres"]
    ncell = len(xy)
    nx, ny = len(np.unique(xy[:, 0])), len(np.unique(xy[:, 1]))
    assert nx * ny == ncell
    spacing = cfg["cell_size_m"]
    extent = [xy[:, 0].min() - spacing / 2, xy[:, 0].max() + spacing / 2,
              xy[:, 1].min() - spacing / 2, xy[:, 1].max() + spacing / 2]
    groups = idx[strict]
    counts = np.bincount(groups, minlength=ncell)
    ec = aggregate(e[strict], groups, ncell)
    d0c = aggregate(d0[strict], groups, ncell)
    vc = aggregate(a["strict_view_count"][strict], groups, ncell)
    maps, finals = {}, {}
    for condition in cfg["conditions"]:
        d1 = a[condition + "_reference_distance"]
        assert np.isfinite(d0).all() and np.isfinite(d1).all()
        dc = aggregate((d1 - d0)[strict], groups, ncell)
        fc = aggregate(d1[strict], groups, ncell)
        assert np.array_equal(np.isfinite(ec), np.isfinite(dc))
        assert np.array_equal(np.isfinite(ec), counts > 0)
        maps[condition], finals[condition] = dc, fc
        for i in np.flatnonzero(counts):
            cell_rows.append(dict(region=rid, condition=condition, cell_id=int(i),
                x=float(xy[i, 0]), y=float(xy[i, 1]), strict_reference_count=int(counts[i]),
                da3_target_z_error_median_m=float(ec[i]),
                anchor_distance_median_m=float(d0c[i]),
                final_distance_median_m=float(fc[i]),
                paired_distance_change_median_m=float(dc[i]),
                reference_all_height_span_m=float(a["reference_z_span_cell"][i])))
    tiles = []
    for case in cfg["representative_cases"]:
        if case["region"] != rid:
            continue
        m = strict.copy()
        if case["cohort"] == "above1":
            m &= e > 1
        elif case["cohort"] == "below1":
            m &= e < -1
        else:
            m &= np.abs(e) <= .5
        m &= (d0 < .5) if case["initial"] == "near" else (d0 >= .5)
        tile_size = cfg["representative_tile_size_m"]
        tiles_xy, inverse, sizes = np.unique(np.floor(points[m, :2] / tile_size).astype(int),
                                             axis=0, return_inverse=True, return_counts=True)
        winner = int(np.argmax(sizes))
        chosen = np.flatnonzero(m)[inverse == winner]
        lower = tiles_xy[winner] * tile_size
        tiles.append((case["id"], lower))
        for condition in cfg["conditions"]:
            d1 = a[condition + "_reference_distance"][chosen]
            tile_rows.append(dict(case_id=case["id"], region=rid, cohort=case["cohort"],
                initial=case["initial"], condition=condition,
                x_min_m=float(lower[0]), y_min_m=float(lower[1]), width_m=tile_size,
                reference_count=len(chosen), da3_target_z_error_median_m=median(e[chosen]),
                anchor_distance_median_m=median(d0[chosen]), final_distance_median_m=median(d1),
                paired_distance_change_median_m=median(d1 - d0[chosen]),
                final_within_0_5m_fraction=float(np.mean(d1 < .5)),
                selection="maximum cohort point count; posthoc illustrative"))
    native, changed = cfg["main_conditions"]
    contrast = aggregate((a[changed + "_reference_distance"] - a[native + "_reference_distance"])[strict], groups, ncell)
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    fig.suptitle(f"{rid} | DA3 target mismatch and paired surface change at the SAME reference points\n"
                 "Raw512 Anchor8k -> final30k; grey = unsupported. Association, not DA3-only effect.", fontsize=14)
    show(axes[0, 0], ec, nx, ny, extent, "DA3 target-height error\nRed = above UAS; blue = below", -3, 3)
    show(axes[0, 1], d0c, nx, ny, extent, "Anchor distance to UAS\nBefore refinement", 0, 2, "magma_r")
    show(axes[0, 2], maps[native], nx, ny, extent, "Native: final minus Anchor distance\nRed = farther; blue = closer", -1, 1)
    show(axes[1, 0], maps[changed], nx, ny, extent, "Prior-depth weight 1/10: change\nDA3 weight was NOT reduced", -1, 1)
    show(axes[1, 1], contrast, nx, ny, extent, "Prior-depth 1/10 minus native\nRed = farther under prior relaxation", -1, 1)
    show(axes[1, 2], vc, nx, ny, extent, "Qualifying near-nadir views\nMedian count on the same points", 0, max(1, int(a["strict_view_count"].max())), "viridis", "views")
    for ax in axes.ravel():
        for label, lower in tiles:
            ax.add_patch(Rectangle(lower, 2, 2, fill=False, edgecolor="black", linewidth=1))
            ax.text(lower[0] + 1, lower[1] + 1, label, ha="center", va="center", fontsize=9,
                    bbox=dict(facecolor="white", edgecolor="black", alpha=.9, pad=1))
    fig.savefig(O / (rid + ".matched_maps.png"), dpi=135)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    fig.suptitle(f"{rid} | Six conditions: same-point distance change from Anchor\n"
                 "Same strict support and colour scale; red farther / blue closer", fontsize=14)
    for ax, condition in zip(axes.ravel(), cfg["conditions"]):
        show(ax, maps[condition], nx, ny, extent, condition, -1, 1)
    fig.savefig(O / (rid + ".six_conditions.png"), dpi=135)
    plt.close(fig)
    print(rid, "PASS exact same-point cell membership", int(strict.sum()), flush=True)

write_csv(O / "same_point_cells.csv", cell_rows)
write_csv(O / "representative_tiles.csv", tile_rows)
cohorts = list(csv.DictReader((I / "error_cohort_transitions.csv").open()))
case_rows, labels = [], []
names = {"above1": "STRICT_TARGET_ABOVE_1M", "below1": "STRICT_TARGET_BELOW_MINUS1M", "within05": "STRICT_TARGET_WITHIN_0.5M"}
for case in cfg["representative_cases"]:
    label = f'{case["region"]}: DA3 ' + {"above1": "> +1m", "below1": "< -1m", "within05": "within +/-0.5m"}[case["cohort"]]
    label += "\n" + ("Preservation (Anchor <0.5m)" if case["initial"] == "near" else "Recovery (Anchor >=0.5m)")
    rows = [next(r for r in cohorts if r["region"] == case["region"] and r["condition"] == c
                 and r["cohort"] == names[case["cohort"]] and r["initial"] == "anchor_" + case["initial"])
            for c in cfg["main_conditions"]]
    labels.append(label + f'\nN={int(rows[0]["reference_count"]):,}')
    case_rows.append(rows)
fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
y = np.arange(len(labels))
for ci, (c, color, label) in enumerate(zip(cfg["main_conditions"], ["#2878b5", "#d97706"], ["Native prior depth", "Prior depth weight 1/10"])):
    values = [float(rows[ci]["final_recall_0.5"]) * 100 for rows in case_rows]
    bars = ax.barh(y + (ci - .5) * .34, values, .32, color=color, label=label)
    ax.bar_label(bars, fmt="%.1f%%", fontsize=9, padding=3)
ax.set(yticks=y, yticklabels=labels, xlim=(0, 105), xlabel="Same UAS reference points within 0.5m of the final extracted surface (%)",
       title="DA3 mismatch x initial structure: preservation and recovery\nWhole named cohorts, not the illustrative 2m tiles. Observed association; not a DA3-off experiment.")
ax.invert_yaxis()
ax.legend(loc="lower right")
ax.grid(axis="x", alpha=.2)
fig.savefig(O / "cohort_summary.png", dpi=150)
plt.close(fig)
outputs = {p.name: bind(p) for p in O.iterdir() if p.suffix in [".csv", ".png"]}
bind(O / "config.json")
bind(Path(__file__))
(O / "receipt.json").write_text(json.dumps(dict(status="PASS_SAME_POINT_CORRESPONDENCE",
    scientific_verdict=None, sources=sources, outputs=outputs, config=cfg,
    python=platform.python_version(), numpy=np.__version__, matplotlib=matplotlib.__version__), indent=2) + "\n")
