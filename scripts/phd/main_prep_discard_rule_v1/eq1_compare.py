"""PHD-MAIN-PREP-DISCARD-RULE-v1 equivalence check 1 (jointbuildgs:dev, CPU): the module-v5 re-runs against the prep v1.1
outputs (same inputs), element by element.

  python eq1_compare.py [--items R1 R2 ... B0_b10 ...] [--out eq1/compare.json]

Meshes (s02 / s02_box vs prep step02 / step06/mesh): every array of lod2_mesh, lod2_store, als_mesh, als_store and the
surface tables. Stage 1 (eq1/s03 / eq1/box vs prep step03 / step06/box_stage1): tolerance, registration shift, every array
of units.npz (store, states, votes, propagated and patch judgments, E, counts), unit_view_pairs (view, loc, npix, na1),
the ALS unplanted point index, the LoD2 unplanted patches, coverage tables and gap probes. Integer arrays must be identical;
float arrays are reported with their largest absolute difference (identical expected). scientific_verdict: null."""
import argparse
import json
from pathlib import Path

import numpy as np

from common import OUT, PREP, jdump, log

RANGES = ["R1", "R2", "R3", "R3E", "R4", "R5", "SW", "B0"]
BOXES = ["B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"]


def cmp_npz(a, b):
    za, zb = np.load(a, allow_pickle=False), np.load(b, allow_pickle=False)
    out = dict(keys_only_new=sorted(set(za.files) - set(zb.files)), keys_only_prep=sorted(set(zb.files) - set(za.files)), arrays={})
    ok = True
    for k in sorted(set(za.files) & set(zb.files)):
        x, y = za[k], zb[k]
        if x.shape != y.shape:
            out["arrays"][k] = dict(equal=False, shape_new=list(x.shape), shape_prep=list(y.shape)); ok = False; continue
        if x.dtype.kind in "fc":
            same = bool(np.array_equal(x, y, equal_nan=True))
            d = float(np.nanmax(np.abs(x.astype(np.float64) - y.astype(np.float64)))) if x.size and not same else 0.0
            out["arrays"][k] = dict(equal=same, max_abs_diff=d)
        else:
            same = bool(np.array_equal(x, y))
            out["arrays"][k] = dict(equal=same, n_diff=int((x != y).sum()) if not same else 0)
        ok &= same
    out["equal"] = ok
    return out


def cmp_json(a, b, drop=()):
    ja, jb = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    for k in drop:
        if isinstance(ja, dict):
            ja.pop(k, None); jb.pop(k, None)
    return dict(equal=ja == jb)


def mesh_pair(item):
    if item in BOXES:
        return OUT / "s02_box" / item, PREP / "step06/mesh" / item
    return OUT / "s02" / item, PREP / "step02" / item


def stage1_pair(item, prior):
    if item in BOXES:
        return OUT / "eq1/box" / item / prior, PREP / "step06/box_stage1" / item / prior
    return OUT / "eq1/s03" / item / prior, PREP / "step03" / item / prior


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--items", nargs="*", default=RANGES + BOXES); ap.add_argument("--out", default="eq1/compare.json")
    a = ap.parse_args()
    rep = {}
    all_ok = True
    for it in a.items:
        r = dict(mesh={}, stage1={})
        mn, mp = mesh_pair(it)
        if (mn / "lod2_mesh.npz").exists():
            for f in ("lod2_mesh.npz", "lod2_store.npz", "als_mesh.npz", "als_store.npz"):
                r["mesh"][f] = cmp_npz(mn / f, mp / f)
            for f in ("lod2_surfaces.json", "als_surfaces.json", "footprints.json", "range.json"):
                r["mesh"][f] = cmp_json(mn / f, mp / f)
        else:
            r["mesh"] = dict(missing=True)
        for pr in ("LoD2", "ALS"):
            sn, sp = stage1_pair(it, pr)
            if not (sn / "summary.json").exists():
                r["stage1"][pr] = dict(missing=True); all_ok = False; continue
            jn, jp = json.loads((sn / "summary.json").read_text()), json.loads((sp / "summary.json").read_text())
            q = dict(tau_roof=[jn["tolerance"]["roof"]["tau"], jp["tolerance"]["roof"]["tau"]],
                     tau_wall=[jn["tolerance"]["wall"]["tau"], jp["tolerance"]["wall"]["tau"]],
                     shift=[jn["registration"]["shift_applied"], jp["registration"]["shift_applied"]],
                     states_equal=jn["states"] == jp["states"], support_vote_equal=jn["support_vote"] == jp["support_vote"],
                     missing_judgment_equal=jn["missing_judgment"] == jp["missing_judgment"], unplanted_equal=jn["unplanted"] == jp["unplanted"],
                     knn_check=jn.get("knn_check"))
            q["tau_equal"] = q["tau_roof"][0] == q["tau_roof"][1] and q["tau_wall"][0] == q["tau_wall"][1]
            q["shift_equal"] = q["shift"][0] == q["shift"][1]
            q["units"] = cmp_npz(sn / "units.npz", sp / "units.npz")
            pn, pp = np.load(sn / "unit_view_pairs.npz"), np.load(sp / "unit_view_pairs.npz")
            q["pairs_equal"] = all(np.array_equal(pn[k], pp[k]) for k in ("view", "loc", "npix", "na1", "views"))
            if pr == "ALS":
                q["unplanted_index_equal"] = bool(np.array_equal(np.load(sn / "unplanted_point_index.npy"), np.load(sp / "unplanted_point_index.npy")))
            for f in ("coverage_views.json", "coverage_footprints.json", "coverage_surfaces.json") + (("gaps.json",) if pr == "LoD2" and (sp / "gaps.json").exists() else ()):
                q[f] = cmp_json(sn / f, sp / f)["equal"]
            ok = (q["tau_equal"] and q["shift_equal"] and q["states_equal"] and q["support_vote_equal"] and q["missing_judgment_equal"]
                  and q["unplanted_equal"] and q["units"]["equal"] and q["pairs_equal"] and q.get("unplanted_index_equal", True)
                  and all(q[f] for f in q if f.endswith(".json")) and all((q["knn_check"] or {}).values()))
            q["equal"] = bool(ok)
            r["stage1"][pr] = q
            all_ok &= ok
        if isinstance(r["mesh"], dict) and not r["mesh"].get("missing"):
            mesh_ok = all(v.get("equal", False) for v in r["mesh"].values())
            r["mesh_equal"] = mesh_ok; all_ok &= mesh_ok
        rep[it] = r
        log(it, "mesh", r.get("mesh_equal"), "stage1", {p: r["stage1"][p].get("equal") for p in r["stage1"]})
    jdump(OUT / a.out, dict(rule=__doc__.split("\n\n")[1], items=rep, all_equal=bool(all_ok), scientific_verdict=None))
    print("EQ1 ALL EQUAL" if all_ok else "EQ1 DIFFERENCES FOUND")


if __name__ == "__main__":
    main()
