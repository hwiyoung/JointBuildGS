"""PHD-MAIN-PREP-DISCARD-RULE-v1 receipt (jointbuildgs:dev, CPU; adapted from the prep measure step13): commit, Docker images, hashes, step times.

  JBGS_GIT_COMMIT=... JBGS_IMAGE_ID=... JBGS_COLMAP_IMAGE=... python receipt.py

Hashes: every script and config of the task (sha256), the inputs (sha256 of each file; the 937-image MVS depth maps as one
sha256 over the sorted 'name size sha256' lines), step seconds from logs/queue.log and the COLMAP receipts.
Writes receipt_task.json. scientific_verdict: null."""
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from common import ART, CFG, DCFG, DENSE, OUT, PREP, REPO, SURVEY, ULS


def sha(p, buf=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    rec = dict(task_id="PHD-MAIN-PREP-DISCARD-RULE-v1", scientific_verdict=None, finished=datetime.datetime.now().isoformat(),
               git_commit=os.environ.get("JBGS_GIT_COMMIT"), git_dirty_note=os.environ.get("JBGS_GIT_DIRTY", ""),
               docker_image="jointbuildgs:dev", docker_image_id=os.environ.get("JBGS_IMAGE_ID"),
               colmap_image=os.environ.get("JBGS_COLMAP_IMAGE"), fork_image="jointbuildgs:geogs-conf-guided-v1", fork_image_id=os.environ.get("JBGS_FORK_IMAGE_ID"),
               clock_note="'finished' is the container clock (UTC); the logs and the report use KST (UTC + 9 h)", execution="docker run --network none --user 1000:1000, inputs read-only; COLMAP patch-match on GPU 0/1",
               training=False, training_code="fork r11 initialisation only (dry init); protection and penalty: code tests on a 40-Gaussian scene",
               downloads="none", existing_outputs_modified=False, config_in_use=DCFG.get("version"),
               config_files=sorted(p.name for p in (REPO / "configs/phd/main_prep_discard_rule_v1").glob("*.json")),
               base_config=CFG["version"])
    rec["scripts"] = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "scripts/phd/main_prep_discard_rule_v1").rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
    rec["module_v5"] = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "src/phd/prior_propagation_v5").glob("*.py"))}
    rec["tests"] = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "tests/phd").glob("test_prior_propagation_v5*.py"))}
    rec["configs"] = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "configs/phd/main_prep_discard_rule_v1").glob("*.json"))}
    rec["base_config"] = {str((REPO / "configs/phd/main_prep_measure_v1/prep_v5.json").relative_to(REPO)): sha(REPO / "configs/phd/main_prep_measure_v1/prep_v5.json")}
    br = OUT / "provenance/build_report_r11.json"
    rec["fork_r11_build"] = json.loads(br.read_text()) if br.exists() else None
    inp = {}
    for p in sorted((ART / "phase-payloads/p0-audit/data/raw/als").glob("*.laz")):
        inp[str(p.relative_to(ART))] = sha(p)
    inp[str(ULS.relative_to(ART))] = sha(ULS)
    for p in (SURVEY / "derived.npz", SURVEY / "s1/rasters_als_mvs_uls.npz", SURVEY / "s1/lod2_buildings.json",
              DENSE / "sparse/cameras.bin", DENSE / "sparse/images.bin"):
        if p.exists():
            inp[str(p.relative_to(ART))] = sha(p)
    for rel in ("step01/views.json", "step01/ranges.json", "step01/b0.json", "step06/boxes_v1.json", "step06/box_views.json", "step06/box_ranges.json"):
        inp[f"prep/{rel}"] = sha(PREP / rel)
    lines = []
    for p in sorted((DENSE / "stereo/depth_maps").glob("*.bin")):
        lines.append(f"{p.name} {p.stat().st_size} {sha(p)}")
    inp["mvs_depth_maps_937 (sha256 of sorted 'name size sha256' lines; equivalence check 1)"] = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    inp["mvs_depth_maps_count"] = len(lines)
    g = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/evaluation_reference/r1_b1_sub002_transformed.ply"
    if g.exists():
        inp[str(g.relative_to(ART))] = sha(g)
    rec["inputs"] = inp
    steps = []
    q = OUT / "logs/queue.log"
    if q.exists():
        for line in q.read_text().splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) (\S+) rc=(\d+) (\d+)s", line)
            if m:
                steps.append(dict(end=m.group(1), job=m.group(2), rc=int(m.group(3)), seconds=int(m.group(4))))
    rec["queue_jobs"] = steps
    ms = []
    if q.exists():
        for line in q.read_text().splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) (.+) (start|done)$", line)
            if m:
                ms.append(dict(time=m.group(1), step=m.group(2), event=m.group(3)))
    rec["queue_milestones"] = ms
    pr = OUT / "logs/progress.md"
    rec["progress_log_sha256"] = sha(pr) if pr.exists() else None
    docd = REPO / "docs/experiments/phd/main_prep_discard_rule_v1"
    rec["report"] = {str(q.relative_to(REPO)): sha(q) for q in sorted(docd.glob("*.md"))} if docd.exists() else None   # report + decision request
    figd = REPO / "docs/experiments/phd/main_prep_discard_rule_v1/figures"
    rec["report_figures"] = {p_.name: sha(p_) for p_ in sorted(figd.glob("*.png"))} if figd.exists() else None
    rec["queue_failures_kept_visible"] = [s for s in steps if s["rc"] != 0]
    rec["colmap_receipts"] = {p.parent.name: json.loads(p.read_text()) for p in sorted((OUT / "mvs").glob("*/colmap_receipt.json"))}
    rec["outputs_top"] = sorted(str(p.relative_to(OUT)) for p in OUT.iterdir())
    (OUT / "receipt_task.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print("receipt", len(rec["scripts"]), "scripts", len(inp), "inputs", len(steps), "jobs")


if __name__ == "__main__":
    main()
