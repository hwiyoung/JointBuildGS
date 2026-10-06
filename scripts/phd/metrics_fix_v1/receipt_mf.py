"""PHD-MAIN-METRICS-FIX-v1 receipt (jointbuildgs:dev, CPU): commit, uncommitted files at the receipt, Docker image ids, hashes
of scripts / configs / module / tests / inputs / outputs, step times.

  JBGS_GIT_COMMIT=... JBGS_GIT_UNCOMMITTED=<file> JBGS_IMAGE_ID=... JBGS_FORK_IMAGE_ID=... python receipt_mf.py

The box MVS depth maps (919 files) are listed by name and size (one hash of the list), not hashed one by one.
Step seconds: logs/queue.log (every Docker job of the task) and the per-result seconds of metrics/<result>.json.
Writes receipt_task.json. scientific_verdict: null."""
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from mf_common import DR, FCFG, MT, OUT, PREP, S0, SITES

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
    rec = dict(task_id="PHD-MAIN-METRICS-FIX-v1", scientific_verdict=None, finished=datetime.datetime.now().isoformat(),
               clock_note="'finished' is the container clock (UTC); queue.log and the report use KST (UTC + 9 h)",
               git_branch="exp/main-experiment", git_commit=os.environ.get("JBGS_GIT_COMMIT"),
               uncommitted_files_at_receipt=(Path(unc).read_text().splitlines() if unc and Path(unc).exists() else None),
               docker_image="jointbuildgs:dev", docker_image_id=os.environ.get("JBGS_IMAGE_ID"),
               gpu_image="jointbuildgs:geogs-conf-guided-v1", gpu_image_id=os.environ.get("JBGS_FORK_IMAGE_ID"),
               execution="docker run --network none --user 1000:1000, inputs read-only (/s0, /mt, /dr, /prep, /art, /repo); at most three Docker jobs; one TSDF job at a time (GPU container capped at 46 GB)",
               training="none", downloads="none", config_in_use=FCFG.get("version"))
    rec["scripts"] = tree(REPO / "scripts/phd/metrics_fix_v1")
    rec["config"] = tree(REPO / "configs/phd/metrics_fix_v1")
    rec["module_metrics_v2"] = tree(REPO / "src/phd/metrics_v2", "*.py")
    rec["module_metrics_v1_unchanged"] = tree(REPO / "src/phd/metrics_v1", "*.py")
    rec["tests"] = tree(REPO / "tests/phd", "test_metrics_v*.py")
    rec["configs_read"] = {k: sha(REPO / k) for k in ("configs/phd/metrics_trial_v1/metrics_trial_v1.json", "configs/phd/main_stage0_v1/stage0_v1.json",
                                                    "configs/phd/main_prep_measure_v1/prep_v5.json", "configs/phd/main_prep_discard_rule_v1/discard_v1.json")}
    inp = {}
    for r in ("b1_LoD2", "b1_ALS", "b2_LoD2", "b2_ALS"):
        for rel in ("post/mesh_tsdf.ply", "post/post.json", "model/dump/iteration_30000/gaussians.npz", "receipt.json"):
            p = S0 / "stage0" / r / rel
            if p.exists():
                inp[f"/s0/stage0/{r}/{rel}"] = sha(p)
    for p in sorted((S0 / "regions").glob("regions_*.npz")):
        inp[f"/s0/{p.relative_to(S0)}"] = sha(p)
    for p in sorted((S0 / "s61/box_gt").glob("*/*.npz")):
        inp[f"/s0/{p.relative_to(S0)}"] = sha(p)
    for s in SITES:
        for prior in ("LoD2", "ALS"):
            p = S0 / "s61/box" / s / prior / "units.npz"
            if p.exists():
                inp[f"/s0/s61/box/{s}/{prior}/units.npz"] = sha(p)
        p = S0 / "fork_inputs/s61" / s / "split.json"
        if p.exists():
            inp[f"/s0/fork_inputs/s61/{s}/split.json"] = sha(p)
        p = DR / "s52/box_gt" / s / "gt_summary.json"
        if p.exists():
            inp[f"/dr/s52/box_gt/{s}/gt_summary.json"] = sha(p)
    for sub in ("regions_ext", "defs", "metrics"):
        for p in sorted((MT / sub).glob("*")):
            if p.is_file():
                inp[f"/mt/{p.relative_to(MT)}"] = sha(p)
    for p in sorted((MT / "gpu").glob("*/mesh_virtual.ply")) + sorted((MT / "gpu").glob("*/virtual.json")):
        inp[f"/mt/{p.relative_to(MT)}"] = sha(p)
    inp["/prep/step06/boxes_v1.json"] = sha(PREP / "step06/boxes_v1.json")
    mvs = {}
    for s in SITES:
        d = PREP / "mvs" / f"box_{s}" / "stereo" / "depth_maps"
        files = sorted(d.glob("*.geometric.bin")) if d.exists() else []
        listing = "\n".join(f"{p.name} {p.stat().st_size}" for p in files)
        mvs[s] = dict(files=len(files), bytes=sum(p.stat().st_size for p in files), list_sha256=hashlib.sha256(listing.encode()).hexdigest())
    rec["inputs"] = inp
    rec["box_mvs_depth_maps"] = mvs
    outs = {}
    for sub in ("regions_v2", "obs", "height", "defs", "metrics", "tables", "figs"):
        for p in sorted((OUT / sub).glob("*")):
            if p.is_file():
                outs[str(p.relative_to(OUT))] = sha(p)
    for p in sorted((OUT / "virtual").rglob("*")):
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
    rec["metric_seconds"] = {p.stem: json.loads(p.read_text()).get("seconds") for p in sorted((OUT / "metrics").glob("*.json"))}
    (OUT / "receipt_task.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print("receipt", rec["git_commit"], len(outs), "outputs", len(inp), "inputs")


if __name__ == "__main__":
    main()
