"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 9 (jointbuildgs:dev, CPU): the pre-measurement of r9 (tables 가-마) with the r10
rules and inputs, only the rows that change beside the r9 values, and the pre-training angles of check 'ra'. No training.

  python premeasure_v5.py      # after stage1_products_r10.py, prepare_r10_inputs.py and the dry initialisations
  mounts: /artifacts (ro), /repo (ro), /p9 (ro), /p10 (rw)

Expected changes (order r10, 3): LoD2 only -- party-wall faces, area, patches, sample points, first protection.
  가 tolerance per prior and surface kind (r10 vs r9)
  나 patches: the party-wall polygons and the whole setting (count / area by state), r9 -> r10 patch correspondence (same
     surface, same cell centre: same state and vote), cells of r9's cell rule (faces.party_wall_cells) against the cut
  다 prior pixels and the pixels where the prior depth term acts (first g_p of the dry runs)
  라 initialisation by origin and region, 마 first protection by the same groups (eq. 7 with the patch judgment, u = 0)
  ra angles between the vertex normal (r9) and the cell normal of every planted airborne LiDAR prior point on a patch,
     by patch state (support / agree, support / conflict, missing, invisible)
Writes /p10/premeasure_v5/tables.json."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v3 import faces as FA3  # noqa: E402  (r9's cell rule)
from src.phd.prior_propagation_v4 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v4 import rule  # noqa: E402

P9 = Path("/p9"); P10 = Path("/p10"); OUT = P10 / "premeasure_v5"; OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path("/repo/configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json").read_text())
V = CFG["values"]; CELL = V["cell_m"]
res = {}


def load(root, setting):
    var = "poly" if setting.startswith("M") else "lod2"
    st = locs.load_store(root / "stage1/products" / setting / f"store_{var}_c{CELL}.npz")
    table = {r["ext"]: r for r in json.loads((root / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
    return st, table


_JCACHE = {}


def counts(st, sel):
    state, vote = st["state_data"], st["vote_data"]
    if id(st) not in _JCACHE:
        _JCACHE[id(st)] = locs.propagate(st, state, vote, V["majority"], V["min_evidence_locations"], V["max_distance_m"])[0]
    J = _JCACHE[id(st)]
    a = st["loc_area"]
    out = {}
    for name, m in (("all", sel), ("support", sel & (state == rule.ST_SUPPORT)),
                    ("agree", sel & (state == rule.ST_SUPPORT) & (vote == rule.V_AGREE)),
                    ("conflict", sel & (state == rule.ST_SUPPORT) & (vote == rule.V_CONFLICT)),
                    ("missing", sel & (state == rule.ST_MISSING)),
                    ("missing_conflict", sel & (state == rule.ST_MISSING) & (J == rule.J_CONFLICT)),
                    ("missing_agree", sel & (state == rule.ST_MISSING) & (J == rule.J_AGREE)),
                    ("missing_mixed", sel & (state == rule.ST_MISSING) & (J == rule.J_MIXED)),
                    ("missing_insufficient", sel & (state == rule.ST_MISSING) & (J == rule.J_INSUFF)),
                    ("invisible", sel & (state == rule.ST_INVISIBLE))):
        out[name] = [int(m.sum()), float(a[m].sum())]
    return out


# ------------------------------------------------------------------ 가
t9 = json.loads((P9 / "stage1/tolerance.json").read_text())["priors"]; t10 = json.loads((P10 / "stage1/tolerance.json").read_text())["priors"]
res["ga"] = {p: {k: dict(r10=t10[p][k]["tau"], r9=t9[p][k]["tau"], n_r10=t10[p][k]["stats"].get("n"), n_r9=t9[p][k]["stats"].get("n"),
                         median_r10=t10[p][k]["stats"].get("median_after"), nmad_r10=t10[p][k]["stats"].get("nmad_after"))
                 for k in ("roof", "wall")} for p in ("M", "L")}

# ------------------------------------------------------------------ 나
res["na"] = {}
for setting in ("M_N", "M_B"):
    st10, tab10 = load(P10, setting); st9, tab9 = load(P9, setting)
    cuts = json.loads((P10 / "stage1/meshes" / f"cuts_{setting}.json").read_text())
    cut_polys = {int(p) for p in cuts["polygons"]}
    tgt_cut = {int(p) for p, r in cuts["polygons"].items() if r["target"]}
    e9 = st9["surf_ext"][st9["loc_surface"]]; e10 = st10["surf_ext"][st10["loc_surface"]]
    out = dict(cut_polygons_in_crop_r9=int(len(set(np.unique(e9)) & cut_polys)), cut_polygons_in_crop_r10=int(len(set(np.unique(e10)) & cut_polys)),
               surfaces_r9=int(len(st9["surf_ext"])), surfaces_r10=int(len(st10["surf_ext"])),
               party_polygons_r9=counts(st9, np.isin(e9, list(cut_polys))), party_polygons_r10=counts(st10, np.isin(e10, list(cut_polys))),
               target_party_r9=counts(st9, np.isin(e9, list(tgt_cut))), target_party_r10=counts(st10, np.isin(e10, list(tgt_cut))),
               all_r9=counts(st9, np.ones(len(e9), bool)), all_r10=counts(st10, np.ones(len(e10), bool)),
               cut_area_in_store_m2=float(st9["loc_area"][np.isin(e9, list(cut_polys))].sum() - st10["loc_area"][np.isin(e10, list(cut_polys))].sum()))
    # correspondence r9 -> r10 (same surface, same cell centre)
    key10 = {(int(e), tuple(np.round(c, 4))): i for i, (e, c) in enumerate(zip(e10, st10["loc_center"]))}
    m9 = np.array([key10.get((int(e), tuple(np.round(c, 4))), -1) for e, c in zip(e9, st9["loc_center"])])
    both = m9 >= 0
    same = both.copy(); same[both] = (st9["state_data"][both] == st10["state_data"][m9[both]]) & (st9["vote_data"][both] == st10["vote_data"][m9[both]])
    extra9 = st9["loc_extra"]
    out["correspondence"] = dict(r9=int(len(e9)), r10=int(len(e10)), matched=int(both.sum()), same_state_vote=int(same.sum()),
                                 changed=int((both & ~same).sum()), r9_only=int((~both).sum()), r10_unmatched=int(len(e10) - both.sum()),
                                 r9_only_by_state={rule.ST_NAMES[k]: int(((~both) & (st9["state_data"] == k)).sum()) for k in rule.ST_NAMES},
                                 r9_only_extra_locations=int(((~both) & extra9).sum()),
                                 changed_examples=[dict(ext=int(e9[i]), r9=[int(st9["state_data"][i]), int(st9["vote_data"][i])],
                                                        r10=[int(st10["state_data"][m9[i]]), int(st10["vote_data"][m9[i]])]) for i in np.nonzero(both & ~same)[0][:10]])
    # r9's cell rule against the cut (wall cells of r9's store)
    mz = np.load(P9 / "stage1/meshes" / f"{setting}.npz"); fz = np.load(P9 / "stage1/meshes" / f"faces_{setting}.npz")
    nout = {int(p): fz["normal_outward"][i] for i, p in enumerate(fz["ids"])}
    wall_t = np.isin(mz["tri_type"], ["WallSurface"])
    cells = np.nonzero(st9["loc_kind"] == 2)[0]
    c_ext = e9[cells]
    keep_c = np.array([int(e) in nout for e in c_ext])
    cells, c_ext = cells[keep_c], c_ext[keep_c]
    c_bld = np.array([tab9[int(e)]["building"] for e in c_ext]); c_n = np.stack([nout[int(e)] for e in c_ext])
    shared, dist, partner = FA3.party_wall_cells(st9["loc_center"][cells], c_bld, c_n, mz["V"], mz["F"][wall_t], mz["tri_building"][wall_t],
                                                 np.stack([nout[int(p)] for p in mz["tri_poly"][wall_t]]))
    cut_cell = ~both[cells]
    out["r9_cell_rule_vs_cut"] = dict(wall_cells_r9=int(len(cells)), r9_party_cells=int(shared.sum()), cut_cells=int(cut_cell.sum()),
                                      both=int((shared & cut_cell).sum()), r9_party_kept=int((shared & ~cut_cell).sum()),
                                      cut_not_r9_party=int((~shared & cut_cell).sum()),
                                      r9_party_kept_by_state={rule.ST_NAMES[k]: int((shared & ~cut_cell & (st9["state_data"][cells] == k)).sum()) for k in rule.ST_NAMES},
                                      cut_not_r9_party_by_state={rule.ST_NAMES[k]: int((~shared & cut_cell & (st9["state_data"][cells] == k)).sum()) for k in rule.ST_NAMES},
                                      cut_not_r9_party_distance_m=dict(p50=float(np.median(dist[~shared & cut_cell])) if (~shared & cut_cell).any() else None,
                                                                       max=float(np.max(dist[~shared & cut_cell])) if (~shared & cut_cell).any() else None))
    np.savez_compressed(OUT / f"cells_{setting}.npz", r9_to_r10=m9, wall_cells_r9=cells, r9_party=shared, cut=cut_cell, dist=dist)
    res["na"][setting] = out
    print(setting, "na", json.dumps({k: v for k, v in out.items() if k in ("correspondence", "r9_cell_rule_vs_cut")})[:1200], flush=True)

# ------------------------------------------------------------------ 다 (prior pixels, g_p of the dry runs)
res["da_px"] = {}
for setting in ("M_N", "M_B", "L_N", "L_B"):
    r10 = json.loads((P10 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())["prior_weight"]["totals"]
    r9 = json.loads((P9 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())["prior_weight"]["totals"]
    res["da_px"][setting] = dict(r10=r10, r9=r9)
    if setting.startswith("M"):
        rc = json.loads((P10 / "stage1/ids/render_check.json").read_text())
        res["da_px"][setting]["prior_px_full_res"] = dict(r10=sum(v["prior_px_r10"] for v in rc["settings"][setting]),
                                                          r9=sum(v["prior_px_r9"] for v in rc["settings"][setting]),
                                                          cut_rays=rc[f"{setting}_cut_rays"], r9_prior_px_on_cut=rc[f"{setting}_r9_prior_px_on_cut"])

# ------------------------------------------------------------------ 라 / 마
GROUPS = ["image", "support", "support_conflict", "missing_conflict", "missing_agree", "missing_other", "invisible", "no_patch"]


def groups_of(z, J):
    pr = z["origin"] == 1; has = pr & (z["seat"] >= 0) & (z["location"] >= 0)
    stt = z["state"]; jt = z["judgment"]; jl = z["unit_judgment"]
    return {"image": ~pr, "support": has & (stt == rule.ST_SUPPORT), "support_conflict": has & (stt == rule.ST_SUPPORT) & (jl == rule.J_CONFLICT),
            "missing_conflict": has & (stt == rule.ST_MISSING) & (jt == rule.J_CONFLICT), "missing_agree": has & (stt == rule.ST_MISSING) & (jt == rule.J_AGREE),
            "missing_other": has & (stt == rule.ST_MISSING) & np.isin(jt, [rule.J_MIXED, rule.J_INSUFF]),
            "invisible": has & (stt == rule.ST_INVISIBLE), "no_patch": pr & ~has}


res["ra_ma"] = {}
for setting in ("M_N", "M_B", "L_N", "L_B"):
    out = {}
    for tag, root in (("r10", P10), ("r9", P9)):
        z = np.load(root / "runs" / f"dry_{setting}" / "model/monitor/init_points.npz")
        g = groups_of(z, None)
        pl = z["planted"]; pr = z["origin"] == 1
        lock, _, _, _ = rule.protected(pl & pr, z["E_first"], 0.5, np.zeros(len(pl)), 1.0, z["unit_judgment"])
        out[tag] = {k: dict(candidates=int(m.sum()), planted=int((m & pl).sum()), protected=int((m & lock).sum())) for k, m in g.items()}
        out[tag]["total"] = dict(candidates=int(len(pl)), planted=int(pl.sum()), protected=int(lock.sum()))
        if tag == "r9" and setting.startswith("M"):   # r9 points that r10 removed (on cut parts of party walls)
            rm = np.zeros(len(pl), bool); rm[np.load(P10 / "inputs" / setting / "removed_party_points.npy")] = True
            out["r9_removed_in_r10"] = {k: dict(candidates=int((m & rm).sum()), planted=int((m & rm & pl).sum()), protected=int((m & rm & lock).sum()))
                                        for k, m in g.items()}
    res["ra_ma"][setting] = out

# ------------------------------------------------------------------ check 'ra': vertex vs cell normal before training
res["ra_angles"] = {}
for setting in ("L_N", "L_B"):
    z = np.load(P10 / "runs" / f"dry_{setting}_cell" / "model/monitor/init_points.npz")
    pl = z["planted"] & (z["origin"] == 1)
    a = z["face_normal_file"].astype(np.float64); b = z["face_normal_cell"].astype(np.float64)
    ok = pl & np.isfinite(a).all(1) & np.isfinite(b).all(1)
    ang = np.full(len(pl), np.nan)
    ang[ok] = np.degrees(np.arctan2(np.linalg.norm(np.cross(a[ok], b[ok]), axis=1), np.abs((a[ok] * b[ok]).sum(1))))
    stt, jl = z["state"], z["unit_judgment"]
    grp = {"support_agree": ok & (stt == rule.ST_SUPPORT) & (jl == rule.J_AGREE), "support_conflict": ok & (stt == rule.ST_SUPPORT) & (jl == rule.J_CONFLICT),
           "missing": ok & (stt == rule.ST_MISSING), "invisible": ok & (stt == rule.ST_INVISIBLE), "all_on_patch": ok}
    out = {}
    for k, m in grp.items():
        x = ang[m]
        out[k] = dict(n=int(m.sum()), p50=float(np.median(x)) if len(x) else None, p95=float(np.percentile(x, 95)) if len(x) else None,
                      max=float(x.max()) if len(x) else None, share_gt_5deg=float((x > 5).mean()) if len(x) else None,
                      share_gt_20deg=float((x > 20).mean()) if len(x) else None)
    out["no_patch_or_no_cell"] = dict(n=int((pl & ~ok).sum()), rule="vertex normal in both methods")
    out["sign_flips"] = int((ok & ((a * b).sum(1) < 0)).sum())
    rep = json.loads((P10 / "runs" / f"dry_{setting}_cell" / "model/monitor/init_report.json").read_text())["init"]["orientation"]
    out["fork"] = rep
    res["ra_angles"][setting] = out
    print(setting, "angles", json.dumps({k: (v.get("n"), v.get("p50"), v.get("p95"), v.get("max")) for k, v in out.items() if isinstance(v, dict) and "n" in v}), flush=True)
(OUT / "tables.json").write_text(json.dumps(res, indent=1, default=float))
print("written", OUT / "tables.json")
