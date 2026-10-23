"""PHD-MAIN-UNCERT-v1 common definitions (CPU, no GPU, no training): container paths (run_cpu_uc.sh), the locked config, the frame, the
crop rectangle, the cells of 1.6 (the AXES71 locked rule, scripts/phd/main_axes71_v2/ax_common.cells_of, re-written here), small
helpers. scientific_verdict: null."""
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

OUT = Path("/out")                                    # PH/main_uncert_v1/PHD-MAIN-UNCERT-v1
PH = Path("/ph")
S0, S1, S2, DR, ART = Path("/s0"), Path("/s1"), Path("/s2"), Path("/dr"), Path("/art")
AX = PH / "main_axes71_v2/PHD-MAIN-AXES71-v2"
FL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
FT = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
V4 = PH / "main_viscmp_v4/PHD-MAIN-VISCMP-v4"
PF = PH / "main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
DOCS = Path("/docs")
REPO = Path("/repo")
CFGP = REPO / "configs/phd/main_uncert_v1/uncert_v1.json"
CFG = json.loads(CFGP.read_text())
D = dict(CFG["defs"])
PTS, WORK, PV, TAB, FIG, LOG = OUT / "points", OUT / "work", OUT / "patch_values", OUT / "tables", OUT / "figures", OUT / "logs"

SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")
PRIORS = ("LoD2", "ALS")
CASES = [tuple(c) for c in CFG["cases"]]
SITE_KO, PRIOR_KO, DATA_KO = CFG["site_ko"], CFG["prior_ko"], CFG["data_ko"]
SITE_ID = {s: i for i, s in enumerate(SITES)}
SET_ID = {"LoD2": 0, "ALS": 1}
DATA_ID = {"mvs_a": 0, "mvs_b": 1, "als": 2, "gt": 3}
R_ID = {1.0: 0, 1.5: 1, 3.0: 2}
CELLS = CFG["cells"]["order"]
CELL_KO = CFG["cells"]["ko"]
SUMS = {k: (v[0], v[1]) for k, v in CFG["cells"]["sums"].items()}
CID = {c: i for i, c in enumerate(CELLS)}
KEY_KO = dict(CELL_KO, **{k: v[0] for k, v in SUMS.items()}, all="전체")
SHIFT = np.array([690953.0, 5336071.0, 604.0])         # configs/phd/main_prep_measure_v1/prep_v5.json frame.world_shift_xyz_m
ZB = 45.7                                             # frame.z_bridge_als_lod2_m
UV_DEG = 70.0                                         # frame.u_axis_angle_degrees_ccw_from_easting
KST = dt.timezone(dt.timedelta(hours=9))
for _d in (PTS, WORK, PV, TAB, FIG, LOG):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def now():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def log(*a):
    print(dt.datetime.now(KST).strftime("%H:%M:%S"), *a, flush=True)


def case_ko(site, prior):
    return f"{SITE_KO[site]} · {PRIOR_KO[prior]}"


def sha256(p, chunk=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def jdump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def conv(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return None if not np.isfinite(o) else float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, Path):
            return str(o)
        raise TypeError(type(o))
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=conv))


def jl(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def peak_gb():
    import resource
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 2)


class Timer:
    def __init__(self):
        self.t0 = time.time()
        self.marks = {}

    def mark(self, k):
        self.marks[k] = round(time.time() - self.t0, 1)
        return self.marks[k]


def env():
    return dict(image=os.environ.get("UC_IMAGE"), image_id=os.environ.get("UC_IMAGE_ID"), cpus=os.environ.get("UC_CPUS"),
                mem=os.environ.get("UC_MEM"), config_sha256=sha256(CFGP))


# ------------------------------------------------------------------------------------------------ frame and crop
def uv_basis():
    a = np.radians(UV_DEG)
    return np.array([[np.cos(a), np.sin(a)], [np.sin(a), -np.cos(a)]])


def xy_to_uv(xy):
    return np.asarray(xy, np.float64)[..., :2] @ uv_basis().T


def site_range(site):
    return json.loads((DR / "s02_box" / site / "range.json").read_text())


def crop_rect(site, extra=3.0):
    """uv rectangle of the experiment region (evaluation range + 10 m band) widened by `extra` m (order 1.2-6)."""
    r = site_range(site)
    return np.array([[r["u_m"][0] - extra, r["v_m"][0] - extra], [r["u_m"][1] + extra, r["v_m"][1] + extra]])


def in_rect_uv(P, rect):
    uv = xy_to_uv(P[:, :2])
    return (uv[:, 0] >= rect[0, 0]) & (uv[:, 0] <= rect[1, 0]) & (uv[:, 1] >= rect[0, 1]) & (uv[:, 1] <= rect[1, 1])


# ------------------------------------------------------------------------------------------------ the cells of 1.6
def regions(site, prior):
    return np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")


def cells_of(site, prior, R=None):
    """cell index per patch (CID; -1 = outside the evaluation range): the AXES71 locked rule (axes71_v2.json cells.rule), same order."""
    R = R if R is not None else regions(site, prior)
    code = R["code_ext_v3"].astype(np.int64)
    ev = R["in_eval"].astype(bool)
    pv = R["premise_violation"].astype(bool)
    wt = R["obs_within_threshold"].astype(bool)
    obs = np.load(FL / "work/obs_masked" / f"region_{site}_{prior}.npz")["obs"].astype(bool)
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
                 code11_ratio_below1=int((ev & (code == 11) & has & (ratio < 1.0)).sum()), patches_per_cell=n)
    return cell, facts


def cell_mask(cell, key):
    if key == "all":
        return cell >= 0
    if key in SUMS:
        return np.isin(cell, [CID[c] for c in SUMS[key][1]])
    return cell == CID[key]


KEYS = CELLS + list(SUMS)


def patches(site, prior):
    """the patch table written by u1_patches.py (work/patches_<site>_<prior>.npz)."""
    return np.load(WORK / f"patches_{site}_{prior}.npz", allow_pickle=False)
