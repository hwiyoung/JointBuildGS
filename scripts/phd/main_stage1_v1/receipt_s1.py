"""PHD-MAIN-STAGE1-v1 receipt (jointbuildgs:dev, CPU): commit, uncommitted files at the receipt, Docker image ids, hashes of scripts /
configs / modules / tests / key inputs / outputs, step times. Made at each report (prep, interim, final).

  JBGS_GIT_COMMIT=... JBGS_GIT_UNCOMMITTED=<file> JBGS_IMAGE_ID=... JBGS_FORK_IMAGE_ID=... python receipt_s1.py <stage-tag>

Large outputs (models, meshes, depth masks) are listed by size and modification time; the rest is hashed. Writes receipt_<tag>.json and
receipt_task.json (the latest). scientific_verdict: null."""
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from s1_common import DR, MF, MT, OUT, PREP, S0

REPO = Path("/repo")
BIG = 50 * 1024 * 1024


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


def main(tag):
    unc = os.environ.get("JBGS_GIT_UNCOMMITTED")
    rec = dict(task_id="PHD-MAIN-STAGE1-v1", stage=tag, scientific_verdict=None, finished=datetime.datetime.now().isoformat(),
               clock_note="'finished' is the container clock (UTC); queue.log and the reports use KST (UTC + 9 h)",
               git_branch="exp/main-experiment", git_commit=os.environ.get("JBGS_GIT_COMMIT"),
               uncommitted_files_at_receipt=(Path(unc).read_text().splitlines() if unc and Path(unc).exists() else None),
               docker_image="jointbuildgs:dev", docker_image_id=os.environ.get("JBGS_IMAGE_ID"),
               gpu_image="jointbuildgs:geogs-conf-guided-v1", gpu_image_id=os.environ.get("JBGS_FORK_IMAGE_ID"),
               execution="docker run --network none --user 1000:1000; inputs read-only (/s0, /mt, /mf, /dr, /prep, /art, /repo); at most two trainings + one other Docker job")
    rec["scripts"] = tree(REPO / "scripts/phd/main_stage1_v1")
    rec["configs"] = tree(REPO / "configs/phd/main_stage1_v1")
    rec["module_metrics_v3"] = tree(REPO / "src/phd/metrics_v3", "*.py")
    rec["modules_unchanged"] = {k: tree(REPO / f"src/phd/{k}", "*.py") for k in ("metrics_v1", "metrics_v2", "prior_propagation_v6")}
    rec["fork_r12"] = tree(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12", "*.py")
    rec["tests"] = tree(REPO / "tests/phd", "test_metrics_v*.py")
    inp = {}
    for b in ("B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"):
        for f in ("gt_points.npz", "gt_summary.json", "exclusion_cells.npz"):
            inp[f"/dr/s52/box_gt/{b}/{f}"] = sha(DR / "s52/box_gt" / b / f)
        for f in ("fork_inputs.json", "split.json"):
            inp[f"/s0/fork_inputs/s61/{b}/{f}"] = sha(S0 / "fork_inputs/s61" / b / f)
        for p in ("LoD2", "ALS"):
            inp[f"/s0/s61/box/{b}/{p}/units.npz"] = sha(S0 / "s61/box" / b / p / "units.npz")
            inp[f"/mf/regions_v2/regions_ext_v2_{b}_{p}.npz"] = sha(MF / "regions_v2" / f"regions_ext_v2_{b}_{p}.npz")
    for r in ("b1_LoD2", "b2_LoD2", "b1_ALS", "b2_ALS"):
        for rel in ("post/mesh_tsdf.ply", "model/dump/iteration_30000/gaussians.npz", "receipt.json"):
            inp[f"/s0/stage0/{r}/{rel}"] = sha(S0 / "stage0" / r / rel)
    inp["/prep/step06/boxes_v1.json"] = sha(PREP / "step06/boxes_v1.json")
    rec["inputs"] = inp
    outs, big = {}, {}
    for p in sorted(OUT.rglob("*")):
        if not p.is_file() or "logs" in p.parts or p.name.startswith("receipt"):
            continue
        rel = str(p.relative_to(OUT))
        st = p.stat()
        if st.st_size > BIG or "/model/" in f"/{rel}" or rel.startswith("sens/conf/"):
            big[rel] = dict(bytes=st.st_size, mtime=datetime.datetime.fromtimestamp(st.st_mtime).isoformat())
        else:
            outs[rel] = sha(p)
    rec["outputs"] = outs
    rec["outputs_listed_not_hashed"] = big
    q = OUT / "logs/queue.log"
    steps = []
    if q.exists():
        for line in q.read_text().splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) (\S+) rc=(\d+) (\d+)s", line)
            if m:
                steps.append(dict(end=m.group(1), job=m.group(2), rc=int(m.group(3)), seconds=int(m.group(4))))
    rec["queue_jobs"] = steps
    rec["queue_failures_kept_visible"] = [s for s in steps if s["rc"] != 0]
    trains = {}
    for r in sorted((OUT / "stage1").glob("*/*/receipt.json")):
        j = json.loads(r.read_text())
        trains[f"{j.get('site')}/{j.get('result')}"] = dict(status=j.get("status"), wall_seconds=j.get("wall_seconds"), gpu=j.get("gpu"),
                                                           gpu_memory_used_mib=j.get("gpu_memory_used_mib"))
    rec["trainings"] = trains
    (OUT / f"receipt_{tag}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    (OUT / "receipt_task.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print("receipt", tag, rec["git_commit"], len(outs), "hashed", len(big), "listed", len(inp), "inputs")


if __name__ == "__main__":
    main(sys.argv[1])
