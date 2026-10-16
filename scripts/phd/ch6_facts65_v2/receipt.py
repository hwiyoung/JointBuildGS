"""PHD-CH6-FACTS65-v2 task receipt: order, environment, runs (queue log), writers, scripts, main inputs and outputs with sha256.
(jointbuildgs:dev, CPU, standard library)
  python receipt.py --image <docker image id of jointbuildgs:dev> --commit-at-start <hash> [--commit <hash>]
Writes /out/receipt_task.json. scientific_verdict: null."""
import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path("/out"); REPO = Path("/repo")
DOCS = REPO / "docs/experiments/phd/ch6_facts65_v2"; SCR = REPO / "scripts/phd/ch6_facts65_v2"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def files(root, base):
    return {str(p.relative_to(base)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts} if root.exists() else {}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--image", required=True); ap.add_argument("--commit-at-start", required=True)
    ap.add_argument("--commit", default=None)
    a = ap.parse_args()
    kst = timezone(timedelta(hours=9))
    runs = [l.split() for l in (OUT / "logs/queue.log").read_text().splitlines() if l.strip()]
    J = json.loads((OUT / "final/facts_6_5_6_6.json").read_text()); EV = json.loads((OUT / "final/evidence_index.json").read_text())
    rec = dict(
        task_id="PHD-CH6-FACTS65-v2",
        order=dict(path="docs/experiments/phd/ch6_facts65_v2/발주문_v2.md", sha256=sha(DOCS / "발주문_v2.md"),
                   sender="document session (6장·7장)", title="6.5·6.6 사실 확인 발주문 v2"),
        started="2026-10-16T10:19:00+09:00", receipt_written=datetime.now(kst).isoformat(timespec="seconds"),
        branch="exp/main-experiment", commit_at_start=a.commit_at_start, commit=a.commit,
        environment=dict(image="jointbuildgs:dev", image_id=a.image, runner="scripts/phd/ch6_facts65_v2/run_queue.sh (docker, --network none, "
                         "CPU only, at most 2 jobs; the PHD-MAIN-FILL-v1 and PHD-MAIN-NUMBERS-v1 work on the same host was not touched)", gpu="none"),
        rule="facts from existing files only (no training, MVS, judgment or metric re-run), except the three computations the order "
             "marks [이 발주에서 냄], run on CPU: 2.7 item 5 (t7_tol_wo2.py: LoD2 tolerance of the search regions B0, R3E, R5 without the "
             "two buildings, the registration and tolerance steps of the recorded runs copied, a run with nothing left out equal bit for "
             "bit), 2.9 item 1 (t9_b0_wrong.py: B0 LoD2 prior-wrong areas from the stage-1 region file v3), 2.12 (t12_clip.py: removed "
             "shares of the tolerance samples).",
        runs=[dict(time=r[0], job=r[1], rc=r[2], seconds=r[3]) for r in runs],
        writers={w: dict(tasks=t, files=files(OUT / "agents" / w, OUT)) for w, t in
                 dict(A="2.1, 2.3", B="2.2", C="2.4, 2.5, 2.6", D="2.7 (not item 5), 2.8, 2.10, 2.11",
                      M="2.7 item 5, 2.9, 2.12, review, assembly").items()},
        counts=J["counts"], evidence=EV["counts"],
        inputs=dict(tolerance_samples="DR/s52/s03/<range>/<prior>/residual_samples.npz and summary.json (t12)",
                    search_region_runs="DR/s02/<range> meshes, DR/mvs/<range> MVS, PREP/step01/views.json and ranges.json (t7_tol_wo2)",
                    regions="S1/regions_v3/regions_ext_v3_B0_b10_LoD2.npz, S1/v3/box_gt/B0_b10 labels, DR/s02_box/B0_b10/lod2_surfaces.json (t9)"),
        scripts=files(SCR, REPO),
        outputs=dict(docs=files(DOCS, REPO), payload={**files(OUT / "final", OUT), **files(OUT / "t7_5", OUT), **files(OUT / "t9", OUT),
                                                      **files(OUT / "t12", OUT)}),
        scientific_verdict=None)
    (OUT / "receipt_task.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    print("receipt", len(rec["runs"]), "runs,", len(rec["scripts"]), "scripts,", len(rec["outputs"]["docs"]), "doc files")


if __name__ == "__main__":
    main()
