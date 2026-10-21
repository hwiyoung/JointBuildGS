"""PHD-MAIN-VISCMP-v4 shared paths, the name table (request 2), the result-file resolvers and small helpers (jointbuildgs:dev).
Payload paths in the earlier tasks' records are short prefixes (S0/, S1/, SB/, SF/, SL/, MT/, MF/, PH/ ...); resolve() turns them into the
mounted paths. scientific_verdict: null"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/repo/scripts/phd/main_photofig_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")

ART = Path("/art")
PH = ART / "phase-payloads/phd"
VC = Path("/vc")
DOCS = Path("/docs")
REPO = Path("/repo")
ROOTS = {"S0": PH / "main_stage0_v1/PHD-MAIN-STAGE0-v1", "S1": PH / "main_stage1_v1/PHD-MAIN-STAGE1-v1", "S2": PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1",
         "S3": PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1", "SB": PH / "main_baselines_v1/PHD-MAIN-BASELINES-v1", "SF": PH / "main_fix_v1/PHD-MAIN-FIX-v1",
         "SL": PH / "main_fill_v1/PHD-MAIN-FILL-v1", "MT": PH / "metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1", "MF": PH / "metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1",
         "FT": PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1", "SD": PH / "main_dist71_v1/PHD-MAIN-DIST71-v1", "PF": PH / "main_photofig_v1/PHD-MAIN-PHOTOFIG-v1",
         "PH": PH, "DR": PH / "main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1", "V2": PH / "main_viscmp_v2/PHD-MAIN-VISCMP-v2"}
SD, FT, SL, S1, S0 = ROOTS["SD"], ROOTS["FT"], ROOTS["SL"], ROOTS["S1"], ROOTS["S0"]
DENSE_IMG = ART / "phase-payloads/p0-audit/data/work/mvs/colmap_dense/images"
CFG = REPO / "configs/phd/main_viscmp_v4/viscmp_v4.json"
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}


def res_name(method, prior):
    """request 2: the result name of a panel."""
    return {"본 방법": f"prop_{prior}_s0", "본 방법 씨앗 1": f"prop_{prior}_s1", "2DGS": "imgonly_2dgs_s0",
            "GeoGS": "trust_LoD2_fix1" if prior == "LoD2" else "geogs_ALS_fix1", "결합": f"mvsfuse_{prior}",
            "학습 전 사전 정보": f"samepath_{prior}", "결측 지키기": f"fixB_{prior}_s0", "CDGS": f"cdgsnofit_{prior}_s0"}[method]


def resolve(s):
    s = str(s)
    pre, rest = s.split("/", 1)
    return ROOTS[pre] / rest if pre in ROOTS else Path(s)


def jl(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def jdump(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, indent=1, ensure_ascii=False, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)))


def now():
    """KST (the container clock is UTC)."""
    return time.strftime("%Y-%m-%d %H:%M:%S KST", time.gmtime(time.time() + 9 * 3600))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def dist_file(site, prior, res):
    """the new distance metric's per-point file (fix-test task first, then the distance task)."""
    for b in (FT / "dist", SD / "dist"):
        f = b / f"{site}_{prior}__{res}.npz"
        if f.exists():
            return f
    return None


def mesh_path(site, prior, res):
    """the TSDF mesh the metric used: the distance json's 'mesh' (both tasks), else the fix-test run's post mesh. None = no result."""
    for b in (FT / "dist", SD / "dist"):
        j = jl(b / f"{site}_{prior}__{res}.json")
        if j and j.get("mesh"):
            p = resolve(j["mesh"])
            if p.exists():
                return p
    p = FT / "runs" / site / res / "post/mesh_tsdf.ply"
    return p if p.exists() else None


def virtual_mesh(site, prior, res):
    """the virtual-view mesh and the wall entry the fill task's virtual component counted (SL/work/virtual/metrics)."""
    j = jl(SL / "work/virtual/metrics" / site / f"{res}__{prior}.json")
    if not j or not j.get("mesh"):
        return None, None
    p = resolve(j["mesh"])
    return (p if p.exists() else None), j.get("wall")
