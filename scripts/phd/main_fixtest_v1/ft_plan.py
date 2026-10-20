"""PHD-MAIN-FIXTEST-v1 plan and commands (host side, stdlib).

The fork command is stage 3's (s3_plan.train_args = stage 2's s2_plan.train_args: the stage-1 command of the proposed method with the
stage-0 values, 30,000 iterations, -r 1 = 1024 x 741, LoD2 initial direction cell method, rule auto, the stage-0 fork inputs,
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True), on fork r16 with the records stage 3 used for every r15 training (--data_device cpu,
the memory record every 500 iterations, the out-of-memory record; records only) and the switches of this task:
  fixA   --jbgs_sw_prior_share_band 1 --jbgs_prior_width_dir /o/prep/wmaps/<site>/<prior>   (판 A)
  fixB   --jbgs_sw_own_depth_release 1                                                    (판 B)
  fixAB  both                                                                              (함께 켠 판)
Paths: /o = this payload (FT), /p = stage 0 (ro), /ph = phase-payloads/phd (ro). scientific_verdict: null."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "scripts/phd/main_stage3_v1"))
import s3_plan as P3  # noqa: E402

SP = P3.SP
ART, PH, S0, S1, S2, S3, SF, WEIGHTS, IMG = P3.ART, P3.PH, P3.S0, P3.S1, P3.S2, P3.S3, P3.SF, P3.WEIGHTS, P3.IMG
FT = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
SB = PH / "main_baselines_v1/PHD-MAIN-BASELINES-v1"
SL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
SD = PH / "main_dist71_v1/PHD-MAIN-DIST71-v1"
DR = PH / "main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
SRC = {"r15": REPO / "src/phd/forks/GeoGS-conf-guided-v1-r15", "r16": REPO / "src/phd/forks/GeoGS-conf-guided-v1-r16"}
ITS = SP.ITS
RECORDS = ["--data_device", "cpu", *P3.MEMLOG, *P3.OOMREC]     # stage 3's records of every r15 training (decisions unchanged)
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")
PRIORS = ("LoD2", "ALS")
UNITS6 = [(s, p) for s in SITES for p in PRIORS]
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
SEARCH = {"B0_b10": "B0", "B173nb_b10": "R2", "R1rep_b10": "R1"}    # the search region whose tau (and w) the site uses


def wmap_dir(site, prior, container=True, reading="L"):
    sub = "wmaps" if reading == "L" else "wmaps_T"
    return (f"/o/prep/{sub}/{site}/{prior}" if container else FT / "prep" / sub / site / prior)


def reading_of(fix):
    """fix codes: A = fix A with the w of reading L (the order's literal NMAD), AT = fix A with reading T (tau's statistic),
    B = fix B, AB = fix A (reading L) + fix B."""
    return "T" if fix.endswith("T") else "L"


def fix_args(fix, site, prior):
    out = []
    if fix.startswith("A"):
        out += ["--jbgs_sw_prior_share_band", "1", "--jbgs_prior_width_dir", wmap_dir(site, prior, reading=reading_of(fix))]
    if "B" in fix:
        out += ["--jbgs_sw_own_depth_release", "1"]
    return out


def train_args(site, prior, model, fix="", seed=0, schedule=None, sw_off=()):
    return P3.train_args(site, prior, model, list(sw_off), None, seed, schedule) + fix_args(fix, site, prior)


def docker(name, gpu, fork, site, entry, cpus=8):
    """stage 3's docker prefix with this payload as /o and the fork given."""
    hdir, I = P3.inputs_dirs(site, P3.INPUTS[site])
    return ["docker", "run", "--rm", "--name", name, "--gpus", f"device={gpu}", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
            "--cpus", str(cpus), "--shm-size", "8g",
            "-e", "PYTHONUNBUFFERED=1", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
            "-e", f"OMP_NUM_THREADS={cpus}", "-e", f"JBGS_SPLIT_JSON={I}/split.json", "-e", "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
            "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S0}:/p:ro", "-v", f"{PH}:/ph:ro", "-v", f"{FT}:/o", "-v", f"{WEIGHTS}:/weights:ro",
            "-v", f"{SRC[fork]}:/source:ro", "-v", f"{REPO}:/repo:ro", "-w", "/source", "--entrypoint", "python", IMG, *entry]


def result_name(fix, prior, seed=0):
    return f"fix{fix}_{prior}_s{seed}"


def run_command(run, gpu):
    name = f"jbgs-ftt-{run['site']}-{run['result']}".replace("_", "-").replace(".", "-").lower()[:60]
    model = f"/o/runs/{run['site']}/{run['result']}/model"
    args = train_args(run["site"], run["prior"], model, run["fix"], run["seed"])
    return name, docker(name, gpu, "r16", run["site"], ["train.py", *args, *RECORDS])


def to_container(p):
    p = Path(p)
    for host, cont in ((FT, "/o"), (S0, "/p"), (PH, "/ph")):
        try:
            return f"{cont}/{p.relative_to(host)}"
        except ValueError:
            continue
    raise ValueError(p)


def ckpt_of(site, prior, seed=0):
    """the stage-1 15,000 state of the proposed method (B173 주변: stage 0's b1 / b2 runs, as stage 3)."""
    if site == "B173nb_b10":
        m = S0 / "stage0" / f"b{seed + 1}_{prior}" / "model"
    else:
        m = S1 / "stage1" / site / f"prop_{prior}_s{seed}" / "model"
    return m / "point_cloud/iteration_15000/point_cloud.ply", m / "monitor/init_points.npz"


# ------------------------------------------------------------------------------------------- the trainings (order 8.2)
# Lane 0 (GPU 0) = fix A in the table's case order, each case with reading L (fixA) then reading T (fixAT); lane 1 (GPU 1) = fix B in
# the table's order, then A + B of R1 항공 LiDAR; A + B of B173 주변 항공 LiDAR closes lane 0. Which of them train is the saved
# configuration's (gate per reading; a reading-T run whose w equals reading L's is not trained twice).
FIX_KO = {"A": "판 A (읽기 L)", "AT": "판 A (읽기 T)", "B": "판 B", "AB": "함께 켠 판"}


def _r(order, lane, fix, site, prior):
    return dict(order=order, lane=lane, fix=fix, site=site, prior=prior, seed=0, result=result_name(fix, prior), kind="fork",
                what=f"{FIX_KO[fix]}, {SITE_KO[site]} {PRIOR_KO[prior]}", sw_off=[], values={})


RUNS = []
for _o, (_s, _p) in enumerate([("B173nb_b10", "ALS"), ("B173nb_b10", "LoD2"), ("B0_b10", "ALS"), ("R1rep_b10", "ALS"), ("B0_b10", "LoD2"),
                               ("R1rep_b10", "LoD2")], start=1):
    RUNS += [_r(_o, 0, "A", _s, _p), _r(_o, 0, "AT", _s, _p)]
for _o, (_s, _p) in enumerate([("R1rep_b10", "LoD2"), ("B173nb_b10", "ALS"), ("R1rep_b10", "ALS"), ("B0_b10", "LoD2"), ("B173nb_b10", "LoD2"),
                               ("B0_b10", "ALS")], start=1):
    RUNS.append(_r(_o, 1, "B", _s, _p))
RUNS += [_r(7, 0, "AB", "B173nb_b10", "ALS"), _r(7, 1, "AB", "R1rep_b10", "ALS")]
assert len(RUNS) == 20


def command(run, gpu):
    return run_command(run, gpu)
