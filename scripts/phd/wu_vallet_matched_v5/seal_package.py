"""Verify preservation and seal the completed matched three-region package."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main(repo, artifacts, output):
    base = artifacts / "phase-payloads/phd/wu_vallet_matched_v5"
    before = read(base / "preservation_start_v5/preservation.json")
    handoff = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
    changed = [r["path"] for r in before["files"] if sha(repo / r["path"]) != r["sha256"]]
    assert changed == [handoff], changed
    with tarfile.open(base / "preservation_start_v5/preexisting_work.tar.gz") as archive:
        member = next(m for m in archive.getmembers() if m.name == handoff)
        old_text = archive.extractfile(member).read().decode()
    assert re.sub(r"> \*\*2026-09-07 v5 동등조건.*?\n\n", "", (repo / handoff).read_text(), count=1) == old_text
    verified = {}
    for folder, version in (("wu_vallet_p3_v2", 2), ("wu_vallet_p3_v3", 3), ("wu_vallet_regions_v4", 4)):
        previous = read(repo / f"artifacts/manifests/phd/{folder}/technical_result_manifest_v{version}.json")
        for row in previous["payloads"]:
            assert sha(artifacts / row["path"]) == row["sha256"], row["path"]
        verified[folder] = len(previous["payloads"])
    keys = {
        "core_audit": "PHD-WU-VALLET-MATCHED-CORE-AUDIT-v5/run/receipt.json",
        "core_author_predicate_correction": "PHD-WU-VALLET-MATCHED-CORE-AUDIT-v5/AUTHOR_PREDICATE_CLARIFICATION.json",
        "evaluation_tests": "PHD-WU-VALLET-MATCHED-EVALUATION-TESTS-v5/run/receipt.json",
        "evaluation": "PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/receipt.json",
        "matched_gate": "PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/MATCHED_PROTOCOL.json",
        "comparison": "PHD-WU-VALLET-MATCHED-COMPARISON-v5/run/receipt.json",
        "previous_comparison": "PHD-WU-VALLET-MATCHED-PREVIOUS-COMPARISON-v5/run/receipt.json",
        "decision_support": "PHD-WU-VALLET-MATCHED-DECISION-SUPPORT-v5/run/receipt.json",
        "viewer": "PHD-WU-VALLET-MATCHED-VIEWER-v5/run/viewer_manifest.json",
        "browser_qa": "PHD-WU-VALLET-MATCHED-BROWSER-QA-v5/browser_qa.json",
    }
    for rid in ("P1", "P2", "P3"):
        for stage in ("INPUT", "UPDATE"):
            keys[f"{rid}_{stage}"] = f"PHD-WU-VALLET-{rid}-{stage}-v5/run/receipt.json"
            receipt = read(base / keys[f"{rid}_{stage}"])
            assert receipt["reference_accessed"] is False
        assert read(base / f"PHD-WU-VALLET-{rid}-UPDATE-v5/LAUNCH_COMPLETED.json")["exit_code"] == 0
    qa = read(base / keys["browser_qa"])
    assert qa["status"] == "PASS" and all(r["pass"] for r in qa["checks"])
    assert read(base / keys["core_audit"])["status"] == "PASS"
    assert read(base / keys["evaluation_tests"])["status"] == "PASS"
    gate = read(base / keys["matched_gate"])
    assert gate["status"] == "PASS_MATCHED_THREE_REGION_PROTOCOL_BEFORE_REFERENCE"
    assert [r["id"] for r in gate["regions"]] == ["P1", "P2", "P3"]
    receipts = {key: dict(path=str((base / rel).relative_to(artifacts)), sha256=sha(base / rel)) for key, rel in keys.items()}
    payloads = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any("source" in part.lower() for part in path.relative_to(base).parts[:-1]) and path.name != "SOURCE_MANIFEST.json":
            continue
        payloads.append(dict(path=str(path.relative_to(artifacts)), bytes=path.stat().st_size, sha256=sha(path)))
    repo_files = []
    for folder in ("scripts/phd/wu_vallet_matched_v5", "configs/phd/wu_vallet_matched_v5", "src/phd/wu_vallet_matched_v5", "src/apps/wu_vallet_matched_v5", "docs/experiments/phd/wu_vallet_matched_v5"):
        repo_files.extend(p for p in (repo / folder).rglob("*") if p.is_file())
    repo_files.extend((repo / "tests/phd").glob("test_wu_vallet_matched_v5*.py"))
    repo_files.append(repo / handoff)
    head = subprocess.check_output(["git", "-c", f"safe.directory={repo}", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert head == before["head"]
    result = dict(schema="jointbuildgs.phd.wu_vallet.matched_package.v5", task_id="PHD-WU-VALLET-MATCHED-v5", status="MATCHED_THREE_REGION_EXECUTION_EVALUATION_AND_VIEWER_COMPLETE", scientific_verdict=None, full_author_reproduction=False, GS_executed=False, git_head=head, commit_or_push_performed=False, created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), container_artifact_root="/artifacts/JointBuildGS", host_artifact_root_relative_to_repository="../JointBuildGS-artifacts", viewer_url="http://127.0.0.1:8901/", cases=["P1", "P2", "P3"], arms_per_case=5, completed_receipts=receipts, preservation=dict(start_files=len(before["files"]), unchanged_files=len(before["files"])-len(changed), additive_handoff_only=changed, original_handoff_content_exact=True, prior_payload_hashes_verified=verified), validation=dict(core_tests=59, evaluation_and_gate_tests=18, browser_checks=len(qa["checks"]), browser_assets=qa.get("asset_count"), browser_screenshots=len(qa["screenshots"])), repo_files=[dict(path=str(p.relative_to(repo)), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(set(repo_files))], payloads=payloads)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "preservation", "validation")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.repo, args.artifacts, args.output)
