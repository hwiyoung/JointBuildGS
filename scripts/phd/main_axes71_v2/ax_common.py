"""PHD-MAIN-AXES71-v2 common definitions (jointbuildgs:dev, CPU; no training, no GPU). Paths, the locked config, the results and their
meshes and per-point files, the cells of 5.1. The distance task's definitions are used as they are (scripts/phd/main_dist71_v1/dm_common.py:
SiteGT, Unit, owner_of_scene_points, result_sample, mesh_paths). scientific_verdict: null."""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
sys.path.insert(0, "/repo")

import dm_common as DMC  # noqa: E402
from dm_common import S1, SB, SF, FL, PH, SiteGT, Unit, jdump, jl, short  # noqa: E402,F401

AX = PH / "main_axes71_v2/PHD-MAIN-AXES71-v2"
DM = DMC.DM
FT = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
V4 = PH / "main_viscmp_v4/PHD-MAIN-VISCMP-v4"
DOCS = Path("/docs")
CFGP = Path("/repo/configs/phd/main_axes71_v2/axes71_v2.json")
CFG = json.loads(CFGP.read_text())
WORK, DIST, TAB, FIG = AX / "work", AX / "dist", AX / "tables", AX / "figures"
for _d in (WORK, DIST, TAB, FIG):
    _d.mkdir(parents=True, exist_ok=True)

CASES = [tuple(c) for c in CFG["cases"]]
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")
PRIORS = ("LoD2", "ALS")
SITE_KO, PRIOR_KO = CFG["site_ko"], CFG["prior_ko"]
ORDER = CFG["results"]["order"]
RES_KO = CFG["results"]["ko"]
CELLS = CFG["cells"]["order"]
CELL_KO = CFG["cells"]["ko"]
SUMS = {k: (v[0], v[1]) for k, v in CFG["cells"]["sums"].items()}
VIRTUAL_CELLS = set(CFG["cells"]["virtual"])
CID = {c: i for i, c in enumerate(CELLS)}
KST = dt.timezone(dt.timedelta(hours=9))


def now():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def log(*a):
    print(dt.datetime.now(KST).strftime("%H:%M:%S"), *a, flush=True)


def case_ko(site, prior):
    return f"{SITE_KO[site]} · {PRIOR_KO[prior]}"


# ------------------------------------------------------------------------------------------------ results
def results_of(key, prior):
    """the result names of one result key on a prior (the method: two seeds)."""
    n = CFG["results"]["names"][key]
    if isinstance(n, dict):
        return [n[prior]]
    if isinstance(n, list):
        return [x.format(p=prior) for x in n]
    return [n.format(p=prior)]


def all_results(site, keys=None):
    """(result name, key, priors) of a site for the given result keys."""
    out = []
    for prior in PRIORS:
        for k in keys or (ORDER + ["mvs_b"] + CFG["results"]["extra_item7"]):
            for r in results_of(k, prior):
                e = next((x for x in out if x[0] == r), None)
                if e is None:
                    out.append((r, k, [prior]))
                else:
                    e[2].append(prior)
    return out


def mesh_of(site, res):
    """(training-view mesh, virtual-view mesh or None, where from)."""
    if res in ("mvs_a", "mvs_b"):
        return AX / "mvs" / site / f"mesh_{res}.ply", None, "AX/mvs (일 1 MVS 표면) [새로 만듦]"
    if res.startswith("fix"):
        R = FT / "runs" / site / res
        return R / "post/mesh_tsdf.ply", R / "gpu/virtual/mesh_virtual.ply", "FT/runs (고친 판 시험)"
    return DMC.mesh_paths(site, res)


def dist_file(site, prior, res):
    """the per-point distance file (the distance task's form): the distance task's, the fix test's, or this task's."""
    for D in (DM / "dist", FT / "dist", DIST):
        f = D / f"{site}_{prior}__{res}.npz"
        if f.exists():
            return f
    return None


def b0gt_file(site, prior, res):
    for D in (DM / "dist", FT / "dist", DIST):
        f = D / f"{site}_{prior}__{res}__b0gt.npz"
        if f.exists():
            return f
    return None


def x_file(site, prior, res):
    """this task's result-side extras (normal distance, lateral distance, nearest-patch distance) of the result sample."""
    return DIST / f"{site}_{prior}__{res}__x.npz"


# ------------------------------------------------------------------------------------------------ the cells of 5.1
def obs_masked(site, prior):
    return np.load(FL / "work/obs_masked" / f"region_{site}_{prior}.npz")


def cells_of(site, prior, R=None):
    """cell index per patch (CID; -1 = outside the evaluation range) by the locked rule (config cells.rule), and the facts used."""
    R = R if R is not None else np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    code = R["code_ext_v3"].astype(np.int64)
    ev = R["in_eval"].astype(bool)
    pv = R["premise_violation"].astype(bool)
    wt = R["obs_within_threshold"].astype(bool)
    obs = obs_masked(site, prior)["obs"].astype(bool)
    r = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    has = np.zeros(len(code), bool)
    has[np.unique(r["patch"])] = True
    ratio = np.abs(R["gt_med"].astype(np.float64)) / R["tau"].astype(np.float64)
    cell = np.full(len(code), -1, np.int8)
    free = ev.copy()

    def put(name, m):
        m = m & free
        cell[m] = CID[name]
        free[m] = False
        return int(m.sum())
    n = {}
    n["c_nogt"] = put("c_nogt", (code == 0) | ~has)
    n["c_limit"] = put("c_limit", (code == 3) & pv)
    n["c_keep_mask"] = put("c_keep_mask", obs)
    n["c_keep_in"] = put("c_keep_in", (code == 3) & wt)
    n["c_refine"] = put("c_refine", code == 2)
    n["c_corr4p"] = put("c_corr4p", (code == 11) & (ratio >= 4.0))
    n["c_corr14"] = put("c_corr14", code == 11)
    n["c_double"] = put("c_double", code == 12)
    n["c_inh_miss"] = put("c_inh_miss", code == 4)
    n["c_miss_wrong"] = put("c_miss_wrong", code == 13)
    n["c_inh_invis"] = put("c_inh_invis", code == 5)
    n["c_invis_wrong"] = put("c_invis_wrong", code == 14)
    facts = dict(unassigned_in_eval=int(free.sum()), unassigned_codes=sorted(set(code[free].tolist())),
                 code11_ratio_below1=int((ev & (code == 11) & has & (ratio < 1.0)).sum()),
                 obs_and_code2=int((ev & obs & (code == 2) & has).sum()), obs_and_limit=int((ev & obs & (code == 3) & pv & has).sum()),
                 obs_and_code4=int((ev & obs & (code == 4) & has).sum()), code0_with_rows=int((ev & (code == 0) & has).sum()),
                 nonzero_code_without_rows=int((ev & (code != 0) & ~has).sum()), patches_per_cell=n)
    return cell, facts


def cell_mask(cell, key):
    """patch mask of a cell, a sum (s_*) or 'all' (every in-range patch)."""
    if key == "all":
        return cell >= 0
    if key in SUMS:
        return np.isin(cell, [CID[c] for c in SUMS[key][1]])
    return cell == CID[key]


KEYS = CELLS + list(SUMS)            # the twelve cells and the three sums
KEY_KO = dict(CELL_KO, **{k: v[0] for k, v in SUMS.items()}, all="전체")
