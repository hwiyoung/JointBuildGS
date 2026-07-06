#!/usr/bin/env python3
"""P2 ① follow-up: is the semantic-seed cloud USABLE MATERIAL for CityGML?

The acceptance check (seed_semantic_verify.py) already showed seeds get *created*
(0 -> hundreds/thousands) inside the textureless footprints. This audit answers the
next question, the one the go/no-go gate before the ~10 h step-② training run needs:

    "Are these seeds material a CityGML roof could plausibly be built from,
     and are they positioned so step ② can turn them into a surface?"

OBSERVATION ONLY -- it produces numbers, not a verdict (the verdict is 김휘영's call,
per CLAUDE.md §2). For each of the 8 buildings, reusing the EXACT step-① carve
(src/stage2/semantic_seed), it reports:

  creation     : seeds_in_fp, roof/wall split, SfM-only count (OFF baseline)   [tier 1]
  xy coverage  : fraction of the footprint whose roof columns hold >=1 seed     [tier 1]
  depth now    : roof-seed column thickness (median / p90) + seed z-range        [tier 1]
  parallax     : max pairwise view angle over the footprint -- low angle means
                 the column is data-limited "D" and ② is unlikely to collapse it [tier 1]
  bracketing   : does the seed z-range CONTAIN the reference roof height? i.e. is
                 the answer even inside the cloud for ② to find?         [tier 2, needs --ref]
  survival     : seed init opacity vs prune threshold; wall-seed share           [tier 1]

Tier 1 runs with the inputs step-① already used. Tier 2 activates only if --ref is
given (reference roof heights). usable_material_obs is a convenience flag combining
parallax/coverage/bracketing -- it is an OBSERVATION, not a pass/fail judgement.

Run in the dev container exactly like seed_semantic_verify.py:

    docker exec jointbuildgs-dev python3 phases/p2-gsjso/scripts/seed_material_audit.py \
        [--ref <ref_heights.csv | reference.city.json>] [--er3-diag er3_diag.json]

Frame: GS-LOCAL z = Hoehe_orthometric + geoid - 604. Reference (orthometric) heights
are mapped to GS-local with --geoid-val (default 45.7 for E5 canonical, baked into
semantic labels via shift_z = 604-45.7 = 558.3). Confirm the geoid value per scene.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

from src.stage2.dataloader import ColmapDataset
from src.stage2.semantic_seed import (  # noqa: E402
    build_semantic_seeds, cameras_from_frames, ROOF_CODE_DEFAULT, WALL_CODE_DEFAULT,
)
try:
    from src.stage2.model import SEED_INIT_OPACITY
except Exception:  # pragma: no cover
    SEED_INIT_OPACITY = 0.25

REPO = "/workspace/JointBuildGS"
DATA_ROOT = f"{REPO}/results/tum_transfer/data"
SEMANTIC_DIR = f"{REPO}/results/tum_transfer/clean_labels_geoidfix/semantic"
FOOTPRINTS = f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"
OUT_DIR = Path(f"{REPO}/results/tum_transfer/mob_analysis")
WORLD_OFFSET = np.array([690953.0, 5336071.0, 604.0])

TEXTURELESS_5 = {"42364609", "4907182", "4908050", "4908166", "4908176"}
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510",
           "4908050", "4908166", "4908176"]
PRUNE_OPA = 0.005  # configs/tum_mob/seed_semantic.yaml


# --------------------------------------------------------------------------- #
# geometry helpers
# --------------------------------------------------------------------------- #
def footprint_ring(geo, bid):
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    co = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    return np.asarray(co)[:, :2]


def poly_area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def column_thickness(xy, z, voxel):
    """Per-(x,y)-column z-extent of roof seeds. Thin (~voxel) = depth localized,
    thick (~band) = depth-ambiguous. Returns (median_m, p90_m, n_columns)."""
    if len(z) == 0:
        return None, None, 0
    keys = np.round(np.asarray(xy) / voxel).astype(np.int64)
    k = keys[:, 0] * 100003 + keys[:, 1]
    th = []
    for u in np.unique(k):
        zz = z[k == u]
        th.append((zz.max() - zz.min()) + voxel)
    th = np.asarray(th, float)
    return float(np.median(th)), float(np.percentile(th, 90)), int(len(th))


def max_pairwise_angle_deg(dirs):
    if len(dirs) < 2:
        return 0.0
    d = np.asarray(dirs, float)
    d /= (np.linalg.norm(d, axis=1, keepdims=True) + 1e-12)
    cos = np.clip(d @ d.T, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos.min())))


def fp_parallax(cams, centers, centroid_local):
    """Cameras whose view contains the footprint centroid, and the max pairwise
    angle between their centroid-rays (geometric approximation of E-R3 C1/C2)."""
    X = np.asarray(centroid_local, float).reshape(3)
    dirs = []
    for cam, C in zip(cams, centers):
        Xc = cam.R @ X + cam.t
        if Xc[2] <= 1e-6:
            continue
        fx, fy, cx, cy = cam.K
        u = fx * Xc[0] / Xc[2] + cx
        v = fy * Xc[1] / Xc[2] + cy
        if 0 <= u < cam.W and 0 <= v < cam.H:
            dirs.append(X - C)
    return len(dirs), max_pairwise_angle_deg(dirs)


# --------------------------------------------------------------------------- #
# reference roof heights (optional -- tier 2)
# --------------------------------------------------------------------------- #
def load_ref_heights(path, geoid_val):
    """{building_id: (z_ground_local, z_roof_local)} or {}.
    Accepts a CSV (columns building_id,h_ground,h_roof in orthometric m) or a
    CityJSON (.json). z_local = h_ortho + geoid_val - 604."""
    if not path:
        return {}
    p = Path(path)
    out = {}
    if p.suffix.lower() in (".csv", ".tsv"):
        delim = "\t" if p.suffix.lower() == ".tsv" else ","
        for row in csv.DictReader(open(p), delimiter=delim):
            bid = row.get("building_id") or row.get("id") or row.get("gml_id")
            try:
                hg, hr = float(row["h_ground"]), float(row["h_roof"])
            except (KeyError, ValueError, TypeError):
                continue
            if bid:
                out[str(bid)] = (hg + geoid_val - 604.0, hr + geoid_val - 604.0)
        return out
    cj = json.load(open(p))  # CityJSON
    verts = np.asarray(cj["vertices"], float)
    if "transform" in cj:
        verts = verts * np.asarray(cj["transform"]["scale"], float) \
            + np.asarray(cj["transform"]["translate"], float)
    z = verts[:, 2]
    for oid, obj in cj.get("CityObjects", {}).items():
        idxs = []

        def walk(b):
            if isinstance(b, int):
                idxs.append(b)
            elif isinstance(b, list):
                for e in b:
                    walk(e)
        for g in obj.get("geometry", []) or []:
            walk(g.get("boundaries", []))
        if idxs:
            zz = z[np.asarray(sorted(set(idxs)))]
            out[str(oid)] = (float(zz.min()) + geoid_val - 604.0,
                             float(zz.max()) + geoid_val - 604.0)
    return out


def match_key(bid, d):
    if bid in d:
        return d[bid]
    for k, v in d.items():
        if bid in k or k in bid:
            return v
    return None


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None,
                    help="reference roof heights: CSV(building_id,h_ground,h_roof) or CityJSON")
    ap.add_argument("--er3-diag", default=None, help="er3_diag.json (use its C1/C2 if present)")
    ap.add_argument("--geoid-val", type=float, default=45.7)
    ap.add_argument("--voxel", type=float, default=1.0)
    ap.add_argument("--theta-min", type=float, default=15.0,
                    help="parallax(deg) below this = data-limited 'D'")
    ap.add_argument("--cov-min", type=float, default=0.6,
                    help="xy coverage below this = holey roof")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    geo = json.load(open(FOOTPRINTS))["features"]
    ref = load_ref_heights(args.ref, args.geoid_val)
    er3 = {}
    if args.er3_diag and Path(args.er3_diag).exists():
        for r in json.load(open(args.er3_diag)).get("rows", []):
            er3[str(r["building"])] = r
    if args.ref and not ref:
        print(f"[warn] --ref {args.ref} parsed 0 buildings; bracketing (tier 2) skipped")

    print("[load] ColmapDataset ...")
    ds = ColmapDataset(root=DATA_ROOT, downscale=1.0, load_depth=False, load_normal=False)
    cams = cameras_from_frames(ds.frames)
    centers = [(-c.R.T @ c.t) for c in cams]
    print(f"[load] frames={len(cams)} SfM_pts={ds.points_xyz.shape[0]}")

    print("[carve] building semantic seeds (step-① reuse) ...")
    seeds = build_semantic_seeds(
        cameras=cams, semantic_dir=SEMANTIC_DIR, footprints_path=FOOTPRINTS,
        buildings=[f"DEBY_LOD2_{t}" for t in TARGETS],
        scene_rgb=ds.points_rgb.mean(axis=0), id_field="building_id",
        world_offset=WORLD_OFFSET, z_min=-55.0, z_max=5.0, voxel=args.voxel,
        tau=0.6, min_obs=5, roof_code=1, wall_code=2, max_seeds_per_building=0, verbose=False)
    sxyz, ssem = seeds.xyz, seeds.sem                    # GS-local frame
    sxyz_xy_utm = sxyz[:, :2] + WORLD_OFFSET[:2]
    sfm_xy_utm = ds.points_xyz[:, :2] + WORLD_OFFSET[:2]

    rows = []
    for t in TARGETS:
        bid = f"DEBY_LOD2_{t}"
        ring = footprint_ring(geo, bid)
        fp = MplPath(ring)
        in_seed = fp.contains_points(sxyz_xy_utm)
        in_sfm = fp.contains_points(sfm_xy_utm)
        cls = ssem[in_seed]
        roof_sel = in_seed.copy()
        roof_sel[in_seed] = (cls == ROOF_CODE_DEFAULT)
        n_seed = int(in_seed.sum())
        n_roof = int((cls == ROOF_CODE_DEFAULT).sum())
        n_wall = int((cls == WALL_CODE_DEFAULT).sum())

        rxy, rz = sxyz[roof_sel][:, :2], sxyz[roof_sel][:, 2]
        th_med, th_p90, n_col = column_thickness(rxy, rz, args.voxel)
        z_lo = float(rz.min()) if len(rz) else None
        z_hi = float(rz.max()) if len(rz) else None
        z_med = float(np.median(rz)) if len(rz) else None

        area = poly_area(ring)
        cov = min(n_col / max(area / args.voxel ** 2, 1.0), 1.0)

        cx_l = (ring[:, 0].min() + ring[:, 0].max()) / 2 - WORLD_OFFSET[0]
        cy_l = (ring[:, 1].min() + ring[:, 1].max()) / 2 - WORLD_OFFSET[1]
        cz_l = z_med if z_med is not None else -30.0
        n_view, par = fp_parallax(cams, centers, [cx_l, cy_l, cz_l])
        if bid in er3:                                   # prefer the real E-R3 carve metrics
            n_view = er3[bid].get("C1_roof_views", n_view)
            par = float(er3[bid].get("C2_parallax_deg", par))

        brk = off = zg = zr = None
        rr = match_key(bid, ref)
        if rr and z_lo is not None:
            zg, zr = rr
            brk = bool(z_lo - args.voxel <= zr <= z_hi + args.voxel)
            off = float(z_med - zr)

        par_ok = par >= args.theta_min
        cov_ok = cov >= args.cov_min
        usable = bool(par_ok and cov_ok and (brk if brk is not None else True))
        rows.append(dict(
            building=bid, textureless5=(t in TEXTURELESS_5),
            sfm_in_fp_OFF=int(in_sfm.sum()), seeds_in_fp=n_seed,
            seed_roof=n_roof, seed_wall=n_wall, wall_share=round(n_wall / max(n_seed, 1), 2),
            fp_area_m2=round(float(area), 1), xy_coverage=round(cov, 2),
            roof_col_thick_med_m=(round(th_med, 1) if th_med is not None else None),
            roof_col_thick_p90_m=(round(th_p90, 1) if th_p90 is not None else None),
            seed_z_lo=(round(z_lo, 1) if z_lo is not None else None),
            seed_z_med=(round(z_med, 1) if z_med is not None else None),
            seed_z_hi=(round(z_hi, 1) if z_hi is not None else None),
            views_see_fp=int(n_view), parallax_deg=round(float(par), 1),
            ref_z_ground=(round(zg, 1) if zg is not None else None),
            ref_z_roof=(round(zr, 1) if zr is not None else None),
            roof_bracketed=brk, z_offset_to_ref=(round(off, 1) if off is not None else None),
            parallax_ok=bool(par_ok), coverage_ok=bool(cov_ok),
            usable_material_obs=usable))

    # ---- console table ----
    print("\n%-20s %4s %6s %5s %6s %6s %5s %6s  %s" %
          ("building", "tex5", "seeds", "cov", "par°", "thick", "brkt", "Δref", "usable?(obs)"))
    for r in rows:
        print("%-20s %4s %6d %5.2f %6.1f %6s %5s %6s  %s" % (
            r["building"], "Y" if r["textureless5"] else "-", r["seeds_in_fp"],
            r["xy_coverage"], r["parallax_deg"],
            ("%.1f" % r["roof_col_thick_med_m"]) if r["roof_col_thick_med_m"] is not None else "-",
            ("Y" if r["roof_bracketed"] else "N") if r["roof_bracketed"] is not None else "-",
            ("%+.1f" % r["z_offset_to_ref"]) if r["z_offset_to_ref"] is not None else "-",
            "yes" if r["usable_material_obs"] else "** FLAG **"))

    summary = dict(
        scope="P2 ① material-quality audit (observation only, no verdict)",
        params=dict(voxel=args.voxel, theta_min=args.theta_min, cov_min=args.cov_min,
                    geoid_val=args.geoid_val, seed_init_opacity=SEED_INIT_OPACITY,
                    prune_opa=PRUNE_OPA, z_band=[-55.0, 5.0], tau=0.6, min_obs=5),
        ref_source=args.ref, er3_diag=args.er3_diag,
        n_sfm=int(ds.points_xyz.shape[0]), n_seeds_total=int(len(sxyz)), rows=rows)
    (OUT_DIR / "seed_material_audit.json").write_text(json.dumps(summary, indent=2))
    with open(OUT_DIR / "seed_material_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n[done] -> {OUT_DIR/'seed_material_audit.json'} (+ .csv)")

    # ---- fig 1: seed roof z-range (bar) vs reference roof/ground ----
    fig, ax = plt.subplots(figsize=(11, 5))
    for i, r in enumerate(rows):
        if r["seed_z_lo"] is None:
            continue
        col = "#d8572f" if r["textureless5"] else "#1d9e75"
        ax.plot([i, i], [r["seed_z_lo"], r["seed_z_hi"]], color=col, lw=8, alpha=0.4,
                solid_capstyle="butt")
        ax.plot(i, r["seed_z_med"], "o", color=col, ms=6)
        if r["ref_z_roof"] is not None:
            ax.plot([i - 0.33, i + 0.33], [r["ref_z_roof"]] * 2, "k-", lw=2.2)
        if r["ref_z_ground"] is not None:
            ax.plot([i - 0.25, i + 0.25], [r["ref_z_ground"]] * 2, color="0.5", lw=1.2, ls="--")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([r["building"].replace("DEBY_LOD2_", "") for r in rows],
                       rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("GS-local z (m)")
    ax.set_title("Seed roof z-range (bar) vs reference roof (black) / ground (grey dash)\n"
                 "orange = textureless · green = control · tall bar = depth-ambiguous column")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "seed_material_zrange.png", dpi=120)

    # ---- fig 2: parallax vs column thickness (identify data-limited 'D') ----
    fig, ax = plt.subplots(figsize=(7.5, 6))
    for r in rows:
        if r["roof_col_thick_med_m"] is None:
            continue
        col = "#d8572f" if r["textureless5"] else "#1d9e75"
        ax.scatter(r["parallax_deg"], r["roof_col_thick_med_m"],
                   s=30 + r["seeds_in_fp"] / 20.0, c=col, edgecolor="k", lw=0.5, alpha=0.85)
        ax.annotate(r["building"].replace("DEBY_LOD2_", ""),
                    (r["parallax_deg"], r["roof_col_thick_med_m"]),
                    fontsize=7, xytext=(4, 3), textcoords="offset points")
    ax.axvline(args.theta_min, color="k", ls="--", lw=1)
    ax.set_xlabel("max pairwise view angle over footprint (deg) — low = can't disambiguate depth")
    ax.set_ylabel("roof seed column thickness, median (m)")
    ax.set_title("Parallax vs seed column thickness\n"
                 "left of dashed line = data-limited 'D' (② unlikely to recover height)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "seed_material_parallax.png", dpi=120)
    print(f"[done] -> {OUT_DIR/'seed_material_zrange.png'}, {OUT_DIR/'seed_material_parallax.png'}")


if __name__ == "__main__":
    main()
