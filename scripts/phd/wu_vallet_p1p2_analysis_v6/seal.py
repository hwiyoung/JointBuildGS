"""Seal focused analysis without changing any completed v5 artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(repo, artifacts, output):
    base = artifacts / "phase-payloads/phd/wu_vallet_p1p2_analysis_v6"
    before = json.loads((base / "preservation_start_v6/preservation.json").read_text())
    handoff = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
    changed = [r["path"] for r in before["files"] if sha(repo / r["path"]) != r["sha256"]]
    assert changed == [handoff], changed
    with tarfile.open(base / "preservation_start_v6/preexisting_work.tar.gz") as tar:
        old = tar.extractfile(handoff).read().decode()
    assert re.sub(r"> \*\*2026-09-07 v6 P1·P2 분석.*?\n\n", "", (repo / handoff).read_text(), count=1) == old
    p5 = repo / "artifacts/manifests/phd/wu_vallet_matched_v5/technical_result_manifest_v5.json"
    previous = json.loads(p5.read_text())
    for row in previous["payloads"]:
        assert sha(artifacts / row["path"]) == row["sha256"], row["path"]
    run = base / "PHD-WU-VALLET-P1P2-ANALYSIS-v6"
    analysis = json.loads((run / "run/receipt.json").read_text())
    assert analysis["status"] == "P1_P2_FROZEN_UPDATE_QUALITY_ANALYSIS_COMPLETE"
    assert json.loads((run / "completion.json").read_text())["exit_code"] == 0
    assert analysis["new_update_runs"] == 0 and analysis["candidate_outputs_modified"] is False
    for path, expected in analysis["input_hashes"].items():
        assert sha(path) == expected
    for name, expected in analysis["outputs"].items():
        assert sha(run / "run" / name) == expected
    repo_files = [repo / handoff]
    for folder in ("scripts/phd/wu_vallet_p1p2_analysis_v6", "configs/phd/wu_vallet_p1p2_analysis_v6", "docs/experiments/phd/wu_vallet_p1p2_analysis_v6"):
        repo_files.extend(p for p in (repo / folder).rglob("*") if p.is_file())
    result = dict(status="P1_P2_FOCUSED_ANALYSIS_COMPLETE", scientific_verdict=None, task_id=analysis["task_id"],
        full_author_reproduction=False, new_update_runs=0, new_posthoc_analysis_runs=1,
        previous_package=dict(path=str(p5.relative_to(repo)), sha256=sha(p5), payload_hashes_verified=len(previous["payloads"])),
        preservation=dict(start_files=len(before["files"]), unchanged_files=len(before["files"])-1, additive_handoff_only=changed, original_handoff_exact=True),
        repo_files=[dict(path=str(p.relative_to(repo)), sha256=sha(p)) for p in sorted(repo_files)],
        payloads=[dict(path=str(p.relative_to(artifacts)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(base.rglob("*")) if p.is_file()],
        viewer_url="http://127.0.0.1:8901/", viewer_instructions="Select P1 or P2 in the region selector; no region query URL is supported")
    with output.open("x") as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write("\n")
    print(json.dumps({k:result[k] for k in ("status","new_update_runs","new_posthoc_analysis_runs","previous_package","preservation")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    main(args.repo,args.artifacts,args.output)
