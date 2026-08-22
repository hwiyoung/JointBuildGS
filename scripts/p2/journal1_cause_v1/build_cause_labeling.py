"""Cause-attribution labeling build — narrative open item ⑥ (E2-collapse layer).

Prepares (does NOT decide): the target list = frozen-93 ∩ E2 comp@0.25(gt=e1)<0.9
(baseline-only standard reporting cut, 45 buildings), the E9-0 classification-hole
auto tags (hole >= 0.10 → CLASSIFICATION_FAILURE candidate), and a static labeling
page served next to the 8882 conditions viewer. The 5-way cause labels themselves
are made by the human reviewer in the browser and exported as JSON; the frozen
label file lands at labels/cause_attribution_v1.json (seed written here with
auto tags only, user labels null).

CPU only, sealed-artifact re-aggregation. scientific_verdict: null.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    thr = cfg["insufficient_threshold"]
    hole_thr = cfg["classification_hole_threshold"]

    sel = json.loads(Path(cfg["selection_confirm"]).read_text(encoding="utf-8"))
    ids = set(sel["effective_selected_ids"])
    assert len(ids) == 93

    tiers = {r["stable_id"]: r["tier"]
             for r in csv.DictReader(open(cfg["labels_csv"], encoding="utf-8"))}
    holes = {r["stable_id"]: r
             for r in csv.DictReader(open(cfg["holes_csv"], encoding="utf-8"))}
    ax10 = json.loads(Path(cfg["ax10_population"]).read_text(encoding="utf-8"))
    n_ids = set(ax10["tables"]["user_adjusted"]["N_stable_ids"])
    census = json.loads(Path(cfg["ax10_roofer_census"]).read_text(encoding="utf-8"))["arms"]
    cond = json.loads(Path(cfg["conditions_manifest"]).read_text(encoding="utf-8"))
    bkeys = {b["stable_id"]: b["bkey"] for b in cond["buildings"]}
    f1 = {b["stable_id"]: b.get("metrics", {}) for b in cond["buildings"]}

    e2 = {}
    for r in csv.DictReader(open(cfg["merged_rows"], encoding="utf-8")):
        if r["stable_id"] in ids and r["arm"] == "E2" and r["gt"] == "e1" and r["completeness@0.25"]:
            e2[r["stable_id"]] = {
                "comp025": float(r["completeness@0.25"]),
                "coverage": float(r["coverage"]) if r["coverage"] else None,
            }

    targets = []
    for sid in sorted(ids):
        c = e2.get(sid, {}).get("comp025")
        if c is None or c >= thr:
            continue
        h = holes.get(sid, {})
        hole = float(h["hole@0.25"]) if h.get("hole@0.25") else None
        auto = "CLASSIFICATION_FAILURE" if hole is not None and hole >= hole_thr else None
        roofer_fail = {
            arm: sid in census[arm]["empty_or_degenerate_ids"] for arm in ("E7", "E8")
        }
        m = f1.get(sid, {})
        targets.append({
            "stable_id": sid,
            "bkey": bkeys.get(sid),
            "tier": tiers.get(sid),
            "in_change_and_insufficient_N": sid in n_ids,
            "e2_comp025": round(c, 4),
            "e2_coverage": e2[sid]["coverage"],
            "comp_raw025": float(h["comp_raw@0.25"]) if h.get("comp_raw@0.25") else None,
            "comp_cls6_025": float(h["comp_cls6@0.25"]) if h.get("comp_cls6@0.25") else None,
            "hole025": hole,
            "auto_tag": auto,
            "roofer_empty_or_degenerate": roofer_fail,
            "f1_e1": {a: (m.get(a) or {}).get("f1_e1") for a in ("E2", "E8")},
        })

    targets.sort(key=lambda t: (not t["in_change_and_insufficient_N"], t["e2_comp025"]))

    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, cwd=Path(__file__).resolve().parents[3]).stdout.strip()
    except Exception:
        commit = None

    seed = {
        "schema": "journal1_cause_attribution_v1",
        "definition": {
            "population": "frozen 93 mask (selection_confirm_v1)",
            "layer": f"E2 completeness@0.25 (gt=e1) < {thr} — baseline-only standard cut",
            "categories": cfg["categories"],
            "auto_tag_rule": f"E9-0 hole@0.25 >= {hole_thr} → CLASSIFICATION_FAILURE candidate "
                             "(auto tag is a candidate, not a decision — reviewer confirms)",
        },
        "n_targets": len(targets),
        "targets": [
            {"stable_id": t["stable_id"], "bkey": t["bkey"], "auto_tag": t["auto_tag"],
             "user_label": None, "memo": None}
            for t in targets
        ],
        "git_commit": commit,
        "labels_by": None,
        "scientific_verdict": None,
    }
    seed_path = Path(cfg["seed_out"])
    if not seed_path.exists():  # never clobber reviewer labels
        seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
        seed_written = True
    else:
        seed_written = False

    out_dir = Path(cfg["viewer_out_dir"])
    manifest = {
        "schema": "journal1_cause_labeling_manifest_v1",
        "task_id": cfg["task_id"],
        "definition": seed["definition"],
        "n_targets": len(targets),
        "n_auto_tagged": sum(1 for t in targets if t["auto_tag"]),
        "targets": targets,
        "scientific_verdict": None,
    }
    (out_dir / "cause_labeling_manifest_v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(Path(__file__).parent / "cause_labeling.html", out_dir / "cause_labeling.html")

    receipt = {
        "schema": "journal1_cause_labeling_build_receipt_v1",
        "task_id": cfg["task_id"],
        "git_commit": commit,
        "inputs": {k: sha256(Path(cfg[k])) for k in
                   ("selection_confirm", "labels_csv", "merged_rows", "holes_csv",
                    "ax10_population", "ax10_roofer_census", "conditions_manifest")},
        "parameters": {"insufficient_threshold": thr,
                       "classification_hole_threshold": hole_thr},
        "scientific_verdict": None,
    }
    (out_dir / "cause_labeling_receipt_v1.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"n_targets": len(targets),
                      "n_auto_tagged": manifest["n_auto_tagged"],
                      "n_in_N": sum(1 for t in targets if t["in_change_and_insufficient_N"]),
                      "seed_written": seed_written,
                      "page": str(out_dir / "cause_labeling.html")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
