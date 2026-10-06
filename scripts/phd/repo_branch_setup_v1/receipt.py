"""PHD-REPO-BRANCH-SETUP-v1 3.5 receipt (jointbuildgs:dev, stdlib): commit, images, script / config hashes, step times,
results. Host facts come in as environment variables from run_all.sh (JBGS_*). Writes /v/receipt_task.json.
scientific_verdict: null."""
import hashlib
import json
import os
from pathlib import Path

REPO, V = Path("/repo"), Path("/v")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    steps = [json.loads(x) for x in (V / "logs/steps.jsonl").read_text().splitlines() if x.strip()]
    res = {}
    for name, p in (("tests", None), ("r11", V / "rebuild/compare_r11.json"), ("runs", V / "compare/compare_chk.json")):
        if p is not None and p.exists():
            d = json.loads(p.read_text())
            res[name] = d.get("summary") or {k: d[k] for k in ("rebuilt_vs_original", "committed_vs_original_without_submodules",
                                                              "build_reports_agree") if k in d}
    tl = V / "logs/tests.log"
    if tl.exists():
        tail = [x for x in tl.read_text().splitlines() if x.startswith(("Ran ", "OK", "FAILED"))]
        res["tests"] = tail
    runs = sorted((V / "fork_runs/chk").glob("*/receipt.json"))
    rec = dict(
        task_id="PHD-REPO-BRANCH-SETUP-v1", step="3.5 clean-checkout checks", scientific_verdict=None,
        checkout=os.environ.get("JBGS_CHECKOUT"), branch=os.environ.get("JBGS_BRANCH"), git_commit=os.environ.get("JBGS_COMMIT"),
        git_dirty_note=os.environ.get("JBGS_DIRTY"),
        docker_images={os.environ.get("JBGS_DEV"): os.environ.get("JBGS_DEV_ID"), os.environ.get("JBGS_FORK"): os.environ.get("JBGS_FORK_ID")},
        execution="docker run --network none --user <uid>:<gid>; the original payloads and the r10 sources mounted read-only; "
                  "only this task's payload is written",
        training=False,
        config={"configs/phd/repo_branch_setup_v1/checks_v1.json": sha(REPO / "configs/phd/repo_branch_setup_v1/checks_v1.json")},
        scripts={str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "scripts/phd/repo_branch_setup_v1").iterdir()) if p.is_file()},
        called_unchanged={str(p.relative_to(REPO)): sha(p) for p in (
            REPO / "scripts/phd/main_prep_discard_rule_v1/run_fork.py", REPO / "scripts/phd/main_prep_discard_rule_v1/fork_checks.py",
            REPO / "scripts/phd/main_prep_discard_rule_v1/build_fork_r11.py", REPO / "scripts/phd/main_prep_discard_rule_v1/common.py")},
        steps=steps,
        fork_runs=[dict(run=json.loads(p.read_text())["run"], gpu=json.loads(p.read_text())["gpu"],
                        seconds=json.loads(p.read_text())["seconds"], status=json.loads(p.read_text())["status"]) for p in runs],
        results=res)
    (V / "receipt_task.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print("receipt written", len(steps), "steps", len(runs), "fork runs")


if __name__ == "__main__":
    main()
