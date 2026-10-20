"""PHD-MAIN-PHOTOFIG-v1 shared helpers (jointbuildgs:dev, CPU; no training, no GPU).

Frame = the study's working frame (configs/phd/main_prep_measure_v1/prep_v5.json 'frame': EPSG:25832 minus [690953, 5336071, 604] m;
uv = box axes, scripts/phd/main_stage0_v1/common.py:53-60). Boxes and evaluation ranges: DR/s02_box/<site>/range.json.
Settings: configs/phd/main_photofig_v1/photofig_v1.json (locked before the first figure). scientific_verdict: null."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

ART = Path("/art")
PH = ART / "phase-payloads/phd"
PF = Path("/pf")
DOCS = Path("/docs")
REPO = Path("/repo")
PCFG = json.loads((REPO / "configs/phd/main_prep_measure_v1/prep_v5.json").read_text())
SHIFT = np.array(PCFG["frame"]["world_shift_xyz_m"], np.float64)
ANG = np.deg2rad(PCFG["frame"]["u_axis_angle_degrees_ccw_from_easting"])
DR = PH / "main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
S0 = PH / "main_stage0_v1/PHD-MAIN-STAGE0-v1"
S1 = PH / "main_stage1_v1/PHD-MAIN-STAGE1-v1"
S2 = PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
SL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
SD = PH / "main_dist71_v1/PHD-MAIN-DIST71-v1"
FT = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
B0R = PH / "main_b0ref_v1/PHD-MAIN-B0REF-v1"
PREP = PH / "main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
LAS = {"nadir": ART / "phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz",
       "manual": B0R / "dl/zenodo_v120_manual/TUM_Downtown_ULS_20241217_manual.laz",
       "fill": B0R / "dl/zenodo_v120_fillparts/TUM_Downtown_ULS_20241217_manual_5mm_fillparts.laz"}
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")


def cfg():
    return json.loads((REPO / "configs/phd/main_photofig_v1/photofig_v1.json").read_text())


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def jdump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


def jl(path):
    return json.loads(Path(path).read_text())


def sha256(p, chunk=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def basis():
    """= scripts/phd/main_stage0_v1/common.py:53-55 (v = the reflected axis)."""
    return np.array([[np.cos(ANG), np.sin(ANG)], [np.sin(ANG), -np.cos(ANG)]])


def xy_to_uv(xy):
    return np.asarray(xy, np.float64)[..., :2] @ basis().T


def uv_to_xy(uv):
    return np.asarray(uv, np.float64) @ basis()


def box(site):
    b = jl(DR / "s02_box" / site / "range.json")
    return dict(u=b["u_m"], v=b["v_m"], eval_u=b["eval_u"], eval_v=b["eval_v"], label=b.get("label"))


def in_rect(xy, site, which="eval", margin=0.0):
    b = box(site)
    uv = xy_to_uv(xy)
    u, v = (b["eval_u"], b["eval_v"]) if which == "eval" else (b["u"], b["v"])
    return (uv[:, 0] >= u[0] - margin) & (uv[:, 0] <= u[1] + margin) & (uv[:, 1] >= v[0] - margin) & (uv[:, 1] <= v[1] + margin)


def return_class(rn, nr):
    rn = rn.astype(np.int64); nr = nr.astype(np.int64)
    c = np.full(len(rn), -1, np.int8)
    c[(nr == 1) & (rn == 1)] = 0
    many = nr > 1
    c[many & (rn == 1)] = 1
    c[many & (rn > 1) & (rn < nr)] = 2
    c[many & (rn == nr)] = 3
    return c


def nmad(x):
    x = np.asarray(x, np.float64)
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else None
