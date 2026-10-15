"""PHD-CH6-FACTS64-v1 task receipt: order, environment, runs (queue log), writers, scripts, main inputs and outputs with sha256.
(jointbuildgs:dev, CPU, standard library)
  python receipt.py --image <docker image id of jointbuildgs:dev> --commit-at-start <hash> [--commit <hash>]
Writes /out/receipt_task.json. scientific_verdict: null."""
import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path("/out"); REPO = Path("/repo"); ART = Path("/art/phase-payloads/phd")
DOCS = REPO / "docs/experiments/phd/ch6_facts64_v1"; SCR = REPO / "scripts/phd/ch6_facts64_v1"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def files(root, base):
    return {str(p.relative_to(base)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--image", required=True); ap.add_argument("--commit-at-start", required=True)
    ap.add_argument("--commit", default=None)
    a = ap.parse_args()
    kst = timezone(timedelta(hours=9))
    runs = [l.split() for l in (OUT / "logs/queue.log").read_text().splitlines() if l.strip()]
    J = json.loads((OUT / "final/facts_6_4.json").read_text()); EV = json.loads((OUT / "final/evidence_index.json").read_text())
    rec = dict(
        task_id="PHD-CH6-FACTS64-v1",
        order=dict(path="docs/experiments/phd/ch6_facts64_v1/발주문_v1.md", sha256=sha(DOCS / "발주문_v1.md"),
                   sender="document session (6장·7장)", title="6.4 사실 확인과 6.3 마무리 발주문 v1"),
        started="2026-10-15T23:40:02+09:00", receipt_written=datetime.now(kst).isoformat(timespec="seconds"),
        branch="exp/main-experiment", commit_at_start=a.commit_at_start, commit=a.commit,
        environment=dict(image="jointbuildgs:dev", image_id=a.image, runner="scripts/phd/ch6_facts64_v1/run_queue.sh (docker, --network none, "
                         "CPU only, at most 2 jobs; the PHD-MAIN-FILL-v1 queue ran on the same host and was not touched)", gpu="none"),
        rule="tasks 1-6 and 8: facts from existing files only (no training, MVS, judgment or metric re-run); task 7: Figure 6.1 redrawn "
             "from the existing stage-1 region files v3. New counts: the Figure 6.1 site table (asked by order 2.7) and the B0 target "
             "building wall point counts (facts row 2.8-4, outside order 1.1, disclosed in the row).",
        runs=[dict(time=r[0], job=r[1], rc=r[2], seconds=r[3]) for r in runs],
        writers=dict(A=dict(tasks="1, 6, appendix D (order section 3)", started="23:42", finished="00:22", files=files(OUT / "agents/A", OUT)),
                     B=dict(tasks="2, 3.1-3.4", started="23:42", finished="00:20", files=files(OUT / "agents/B", OUT)),
                     C=dict(tasks="4, 5", started="23:42", finished="00:11", files=files(OUT / "agents/C", OUT)),
                     M=dict(tasks="3.5, 7, 8, review, assembly", files=files(OUT / "agents/M", OUT))),
        review=dict(status_changes=["2.4-5", "2.5-9", "2.5-11"],
                    rechecked="every 'different' fact against its source lines; the evaluation-image overlap recounted for the four boxes"),
        counts=J["counts"], evidence=EV["counts"],
        inputs={k: str(v) for k, v in dict(
            regions_v3="S1/v3/regions (stage-1 region files v3, read by t7_fig61.py)", box_gt_v3="S1/v3/box_gt/B0_b10 (t8_b0_walls.py)",
            patch_store="S0/s61/box/B0_b10/LoD2/units.npz", lod2_surfaces="DR/s02_box/<box>/lod2_surfaces.json",
            orthos="CH6/t3 (orthophotos of the support task)", support_scripts="scripts/phd/ch6_support_v1 (ch6_common.py, t3_fig61.py v2)").items()},
        scripts=files(SCR, REPO),
        outputs=dict(docs=files(DOCS, REPO), payload={**files(OUT / "final", OUT), **files(OUT / "t7", OUT), **files(OUT / "t8", OUT)}),
        scientific_verdict=None)
    (OUT / "receipt_task.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    print("receipt", len(rec["runs"]), "runs,", len(rec["scripts"]), "scripts,", len(rec["outputs"]["docs"]), "doc files")


if __name__ == "__main__":
    main()
