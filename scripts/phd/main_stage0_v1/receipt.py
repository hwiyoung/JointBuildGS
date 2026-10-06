"""PHD-MAIN-STAGE0-v1 receipt (jointbuildgs:dev, CPU; adapted from the discard task's receipt.py): commit, uncommitted files at the
run, Docker image ids, hashes of scripts / configs / module / fork / inputs, step times.

  JBGS_GIT_COMMIT=... JBGS_GIT_UNCOMMITTED=<file> JBGS_IMAGE_ID=... JBGS_FORK_IMAGE_ID=... JBGS_COLMAP_IMAGE=... python receipt.py

Step seconds: logs/queue.log (CPU jobs, fork runs), the COLMAP receipts, the stage-0 receipts and post.json. Writes
receipt_task.json. scientific_verdict: null."""
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from common import ART, CFG, DENSE, DR, OUT, PREP, REPO, SCFG, ULS


def sha(p, buf=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def tree(root, pattern="*"):
    return {str(p.relative_to(REPO)): sha(p) for p in sorted(Path(root).rglob(pattern)) if p.is_file() and "__pycache__" not in p.parts}


def main():
    unc = os.environ.get("JBGS_GIT_UNCOMMITTED")
    rec = dict(task_id="PHD-MAIN-STAGE0-v1", scientific_verdict=None, finished=datetime.datetime.now().isoformat(),
               clock_note="'finished' is the container clock (UTC); logs and the report use KST (UTC + 9 h)",
               git_branch="exp/main-experiment", git_commit=os.environ.get("JBGS_GIT_COMMIT"),
               uncommitted_files_at_receipt=(Path(unc).read_text().splitlines() if unc and Path(unc).exists() else None),
               docker_image="jointbuildgs:dev", docker_image_id=os.environ.get("JBGS_IMAGE_ID"),
               fork_image="jointbuildgs:geogs-conf-guided-v1", fork_image_id=os.environ.get("JBGS_FORK_IMAGE_ID"),
               colmap_image=os.environ.get("JBGS_COLMAP_IMAGE"),
               execution="docker run --network none --user 1000:1000, inputs read-only; at most three Docker jobs; trainings one per GPU",
               downloads="none", config_in_use=SCFG["version"], base_config=CFG["version"])
    rec["scripts"] = tree(REPO / "scripts/phd/main_stage0_v1")
    rec["configs"] = tree(REPO / "configs/phd/main_stage0_v1")
    rec["configs_read"] = {k: sha(REPO / k) for k in ("configs/phd/main_prep_measure_v1/prep_v5.json", "configs/phd/main_prep_discard_rule_v1/discard_v1.json",
                                                    "configs/phd/main_prep_discard_rule_v1/sites_v1.json")}
    rec["module_v6"] = tree(REPO / "src/phd/prior_propagation_v6", "*.py")
    rec["tests"] = tree(REPO / "tests/phd", "test_prior_propagation_v6.py")
    rec["fork_r12"] = dict(files=len(tree(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12")),
                           sha256_of_sorted_file_hashes=hashlib.sha256("\n".join(f"{k} {v}" for k, v in tree(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12").items()).encode()).hexdigest(),
                           build_report=json.loads((REPO / "docs/experiments/phd/main_stage0_v1/provenance/build_report_r12.json").read_text()))
    inp = {}
    for rel in ("step01/views.json", "step01/ranges.json", "step01/b0.json", "step06/boxes_v1.json", "step06/box_views.json", "step06/box_ranges.json"):
        inp[f"/prep/{rel}"] = sha(PREP / rel)
    for p in sorted((DR / "s52/s03").glob("*/*/summary.json")):
        inp[f"/dr/{p.relative_to(DR)}"] = sha(p)
    for p in sorted((DR / "s02_box").glob("*/*.npz")) + sorted((DR / "s02_box").glob("*/*.json")):
        inp[f"/dr/{p.relative_to(DR)}"] = sha(p)
    for p in sorted((DR / "s52/box_gt").glob("*/gt_points.npz")) + sorted((DR / "s52/box_gt").glob("*/exclusion_cells.npz")):
        inp[f"/dr/{p.relative_to(DR)}"] = sha(p)
    for p in (DENSE / "sparse/cameras.bin", DENSE / "sparse/images.bin", ULS):
        inp[str(p.relative_to(ART))] = sha(p)
    rec["inputs"] = inp
    q = OUT / "logs/queue.log"
    steps, ms = [], []
    if q.exists():
        for line in q.read_text().splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) (\S+) rc=(\d+) (\d+)s", line)
            if m:
                steps.append(dict(end=m.group(1), job=m.group(2), rc=int(m.group(3)), seconds=int(m.group(4))))
            m = re.match(r"(\d\d:\d\d:\d\d) (.+) (start|done)$", line)
            if m:
                ms.append(dict(time=m.group(1), step=m.group(2), event=m.group(3)))
    rec["queue_jobs"] = steps; rec["queue_milestones"] = ms
    rec["queue_failures_kept_visible"] = [s for s in steps if s["rc"] != 0]
    rec["colmap_receipts"] = {p.parent.name: json.loads(p.read_text()) for p in sorted((OUT / "mvs").glob("*/colmap_receipt.json"))}
    rec["stage0"] = {}
    for d in sorted((OUT / "stage0").glob("b*_*")):
        if (d / "receipt.json").exists():
            r = json.loads((d / "receipt.json").read_text())
            rec["stage0"][d.name] = {k: r.get(k) for k in ("status", "seed", "gpu", "wall_seconds", "exit_code", "gpu_memory_used_mib", "stop_signal", "error", "started_at", "finished_at")}
            if (d / "post/post.json").exists():
                rec["stage0"][d.name]["post_seconds"] = json.loads((d / "post/post.json").read_text())["seconds"]
    rec["progress_md_sha256"] = sha(OUT / "progress.md") if (OUT / "progress.md").exists() else None
    docd = REPO / "docs/experiments/phd/main_stage0_v1"
    rec["report"] = {str(p.relative_to(REPO)): sha(p) for p in sorted(docd.glob("*.md"))}
    rec["report_figures"] = {p.name: sha(p) for p in sorted((docd / "figures").glob("*.png"))}
    rec["outputs_top"] = sorted(str(p.relative_to(OUT)) for p in OUT.iterdir())
    (OUT / "receipt_task.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print("receipt", len(rec["scripts"]), "scripts", len(inp), "inputs", len(steps), "jobs")


if __name__ == "__main__":
    main()
