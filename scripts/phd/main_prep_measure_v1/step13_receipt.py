"""PHD-MAIN-PREP-MEASURE-v1 step 13 (jointbuildgs:dev, CPU): task receipt (commit, Docker images, hashes, step times).

  JBGS_GIT_COMMIT=... JBGS_IMAGE_ID=... JBGS_COLMAP_IMAGE=... python step13_receipt.py

Hashes: every script and config of the task (sha256), the inputs (sha256 of each file; the 937-image MVS depth maps as one
sha256 over the sorted 'name size sha256' lines), step seconds from logs/queue.log and the COLMAP receipts.
Writes receipt_task.json. scientific_verdict: null."""
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from common import ART, CFG, DENSE, OUT, REPO, SURVEY, ULS


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
    rec = dict(task_id="PHD-MAIN-PREP-MEASURE-v1", scientific_verdict=None, finished=datetime.datetime.now().isoformat(),
               git_commit=os.environ.get("JBGS_GIT_COMMIT"), git_dirty_note=os.environ.get("JBGS_GIT_DIRTY", ""),
               docker_image="jointbuildgs:dev", docker_image_id=os.environ.get("JBGS_IMAGE_ID"),
               colmap_image=os.environ.get("JBGS_COLMAP_IMAGE"), execution="docker run --network none --user 1000:1000, inputs read-only; COLMAP patch-match on GPU 0/1",
               training=False, downloads="none of data; the pinned COLMAP image was pulled once with the user's approval (20:45)",
               existing_outputs_modified=False, config_in_use=CFG["version"],
               config_versions=sorted(p.name for p in (REPO / "configs/phd/main_prep_measure_v1").glob("prep_v*.json")),
               report_revisions=["v1 (2026-10-03)", "v1.1 (2026-10-04, after the user's review: nadir photo for roof rows, case 4 "
                                 "location figure, coverage CSV, reading fixes; no threshold, rule or label change)"])
    rec["scripts"] = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "scripts/phd/main_prep_measure_v1").glob("*")) if p.is_file()}
    rec["tests"] = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "tests/phd").glob("test_main_prep_measure_v1*.py"))}
    rec["configs"] = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "configs/phd/main_prep_measure_v1").glob("*.json"))}
    inp = {}
    for p in sorted((ART / "phase-payloads/p0-audit/data/raw/als").glob("*.laz")):
        inp[str(p.relative_to(ART))] = sha(p)
    inp[str(ULS.relative_to(ART))] = sha(ULS)
    for p in (SURVEY / "derived.npz", SURVEY / "s1/rasters_als_mvs_uls.npz", SURVEY / "s1/lod2_buildings.json",
              DENSE / "sparse/cameras.bin", DENSE / "sparse/images.bin"):
        if p.exists():
            inp[str(p.relative_to(ART))] = sha(p)
    lines = []
    for p in sorted((DENSE / "stereo/depth_maps").glob("*.bin")):
        lines.append(f"{p.name} {p.stat().st_size} {sha(p)}")
    inp["mvs_depth_maps_937 (sha256 of sorted 'name size sha256' lines)"] = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    inp["mvs_depth_maps_count"] = len(lines)
    g = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/evaluation_reference/r1_b1_sub002_transformed.ply"
    if g.exists():
        inp[str(g.relative_to(ART))] = sha(g)
    pdf = OUT / "step08/inputs/paper_pdf.sha256"
    if pdf.exists():
        inp["GeoGS paper PDF (local copy, outside the repository)"] = pdf.read_text().split()[0]
    rec["inputs"] = inp
    steps = []
    q = OUT / "logs/queue.log"
    if q.exists():
        for line in q.read_text().splitlines():
            m = re.match(r"(\d\d:\d\d:\d\d) (\S+) rc=(\d+) (\d+)s", line)
            if m:
                steps.append(dict(end=m.group(1), job=m.group(2), rc=int(m.group(3)), seconds=int(m.group(4))))
    rec["queue_jobs"] = steps
    rec["queue_failures_kept_visible"] = [s for s in steps if s["rc"] != 0]
    rec["colmap_receipts"] = {p.parent.name: json.loads(p.read_text()) for p in sorted((OUT / "mvs").glob("*/colmap_receipt.json"))}
    rec["outputs_top"] = sorted(str(p.relative_to(OUT)) for p in OUT.iterdir())
    (OUT / "receipt_task.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print("receipt", len(rec["scripts"]), "scripts", len(inp), "inputs", len(steps), "jobs")


if __name__ == "__main__":
    main()
