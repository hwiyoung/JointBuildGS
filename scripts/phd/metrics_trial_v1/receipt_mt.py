"""PHD-MAIN-METRICS-TRIAL-v1 receipt (jointbuildgs:dev, CPU): commit, uncommitted files at the receipt, Docker image ids, hashes
of scripts / config / module / tests / inputs / outputs, step times.

  JBGS_GIT_COMMIT=... JBGS_GIT_UNCOMMITTED=<file> JBGS_IMAGE_ID=... JBGS_FORK_IMAGE_ID=... python receipt_mt.py

Step seconds: logs/queue.log (every Docker job of the task) and the per-result seconds of metrics/<result>.json.
Writes receipt_task.json. scientific_verdict: null."""
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from mt_common import DR, MCFG, OUT, PREP, S0

REPO = Path("/repo")


def sha(p, buf=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def tree(root, pattern="*", rel=REPO):
    return {str(p.relative_to(rel)): sha(p) for p in sorted(Path(root).rglob(pattern)) if p.is_file() and "__pycache__" not in p.parts}


def main():
    unc = os.environ.get("JBGS_GIT_UNCOMMITTED")
    rec = dict(task_id="PHD-MAIN-METRICS-TRIAL-v1", scientific_verdict=None, finished=datetime.datetime.now().isoformat(),
               clock_note="'finished' is the container clock (UTC); queue.log and the report use KST (UTC + 9 h)",
               git_branch="exp/main-experiment", git_commit=os.environ.get("JBGS_GIT_COMMIT"),
               uncommitted_files_at_receipt=(Path(unc).read_text().splitlines() if unc and Path(unc).exists() else None),
               docker_image="jointbuildgs:dev", docker_image_id=os.environ.get("JBGS_IMAGE_ID"),
               gpu_image="jointbuildgs:geogs-conf-guided-v1", gpu_image_id=os.environ.get("JBGS_FORK_IMAGE_ID"),
               execution="docker run --network none --user 1000:1000, inputs read-only (/s0, /dr, /prep, /art, /repo); at most three Docker jobs; one TSDF job at a time (GPU container capped at 46 GB)",
               training="none", downloads="none", config_in_use=MCFG["version"])
    rec["scripts"] = tree(REPO / "scripts/phd/metrics_trial_v1")
    rec["config"] = tree(REPO / "configs/phd/metrics_trial_v1")
    rec["module_metrics_v1"] = tree(REPO / "src/phd/metrics_v1", "*.py")
    rec["tests"] = tree(REPO / "tests/phd", "test_metrics_v1.py")
    rec["configs_read"] = {k: sha(REPO / k) for k in ("configs/phd/main_stage0_v1/stage0_v1.json", "configs/phd/main_prep_measure_v1/prep_v5.json",
                                                    "configs/phd/main_prep_discard_rule_v1/discard_v1.json")}
    inp = {}
    site = MCFG["site"]
    for r in ("b1_LoD2", "b1_ALS", "b2_LoD2", "b2_ALS"):
        for rel in ("post/mesh_tsdf.ply", "model/dump/iteration_30000/gaussians.npz", "receipt.json"):
            inp[f"/s0/stage0/{r}/{rel}"] = sha(S0 / "stage0" / r / rel)
    for p in sorted((S0 / "regions").glob("regions_*.npz")):
        inp[f"/s0/{p.relative_to(S0)}"] = sha(p)
    for p in sorted((S0 / "s61/box_gt").glob("*/*.npz")):
        inp[f"/s0/{p.relative_to(S0)}"] = sha(p)
    for prior in ("LoD2", "ALS"):
        for s in ("B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"):
            inp[f"/s0/s61/box/{s}/{prior}/units.npz"] = sha(S0 / "s61/box" / s / prior / "units.npz")
    for p in sorted((DR / "s02_box" / site).glob("*")):
        inp[f"/dr/{p.relative_to(DR)}"] = sha(p)
    inp["/prep/step06/boxes_v1.json"] = sha(PREP / "step06/boxes_v1.json")
    inp["/s0/fork_inputs/s61/B173nb_b10/split.json"] = sha(S0 / "fork_inputs/s61/B173nb_b10/split.json")
    rec["inputs"] = inp
    outs = {}
    for sub in ("regions_ext", "defs", "paths", "metrics", "tables"):
        for p in sorted((OUT / sub).glob("*")):
            if p.is_file():
                outs[str(p.relative_to(OUT))] = sha(p)
    for p in sorted((OUT / "gpu").rglob("*")):
        if p.is_file():
            outs[str(p.relative_to(OUT))] = sha(p)
    rec["outputs"] = outs
    q = OUT / "logs/queue.log"
    steps = []
    if q.exists():
        for line in q.read_text().splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) (\S+) rc=(\d+) (\d+)s", line)
            if m:
                steps.append(dict(end=m.group(1), job=m.group(2), rc=int(m.group(3)), seconds=int(m.group(4))))
    rec["queue_jobs"] = steps
    rec["queue_failures_kept_visible"] = [s for s in steps if s["rc"] != 0]
    fb = OUT / "logs/gpu_fallback.txt"
    rec["virtual_mesh_fallbacks"] = fb.read_text().splitlines() if fb.exists() else []
    rec["metric_seconds"] = {p.stem: json.loads(p.read_text()).get("seconds") for p in sorted((OUT / "metrics").glob("*.json"))}
    (OUT / "receipt_task.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print("receipt", rec["git_commit"], len(outs), "outputs")


if __name__ == "__main__":
    main()
