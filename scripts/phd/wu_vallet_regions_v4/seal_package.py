"""Seal v4 receipts and verify original workspace/result preservation."""
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
    base = artifacts / "phase-payloads/phd/wu_vallet_regions_v4"
    before = read(base / "preservation_start_v4/preservation.json")
    handoff = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
    unchanged, edited = [], []
    for row in before["files"]:
        actual = sha(repo / row["path"])
        if actual == row["sha256"]:
            unchanged.append(row["path"])
        else:
            assert row["path"] == handoff, f"Unexpected modification: {row['path']}"
            edited.append(row["path"])
    assert edited == [handoff]
    with tarfile.open(base / "preservation_start_v4/preexisting_work.tar.gz") as archive:
        member = next(m for m in archive.getmembers() if m.name.endswith(handoff))
        old_text = archive.extractfile(member).read().decode()
    now_text = (repo / handoff).read_text()
    assert re.sub(r"> \*\*2026-09-07 v4 실행.*?\n\n", "", now_text, count=1) == old_text
    old_counts = {}
    for version in (2, 3):
        previous = read(repo / f"artifacts/manifests/phd/wu_vallet_p3_v{version}/technical_result_manifest_v{version}.json")
        for row in previous["payloads"]:
            assert sha(artifacts / row["path"]) == row["sha256"], row["path"]
        old_counts[f"v{version}"] = len(previous["payloads"])
    roots = {
        "evaluation_primary": "PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/receipt.json",
        "evaluation_visible": "PHD-WU-VALLET-VISIBLE-EVALUATION-v4/run/receipt.json",
        "comparison": "PHD-WU-VALLET-REGIONS-COMPARISON-v4/run/receipt.json",
        "decision_support": "PHD-WU-VALLET-DECISION-SUPPORT-v4/run/receipt.json",
        "viewer": "PHD-WU-VALLET-REGIONS-VIEWER-v4-r2/run/viewer_manifest.json",
        "browser_qa": "PHD-WU-VALLET-REGIONS-BROWSER-QA-v4-r2/browser_qa.json",
        "sensor_tests": "PHD-WU-VALLET-REGIONS-VALIDATION-v4/sensor_test_receipt.json",
        "evaluation_tests": "PHD-WU-VALLET-VISIBLE-EVALUATION-v4/unit_test_receipt.json",
        "visible_integrity": "PHD-WU-VALLET-VISIBLE-INTEGRITY-v4/receipt.json",
        "recovered_wrapper_exception": "PHD-WU-VALLET-VISIBLE-EVALUATION-v4/wrapper_completion_exception.json",
    }
    for region in ("P1", "P2"):
        for stage in ("INPUT", "ACQUISITION", "TRAJECTORY", "UPDATE", "VISIBLE-INPUT", "VISIBLE-UPDATE", "VISIBLE-IMAGE-SUPPORT"):
            roots[f"{region}_{stage}"] = f"PHD-WU-VALLET-{region}-{stage}-v4/run/receipt.json"
    receipts = {key: dict(path=str((base / rel).relative_to(artifacts)), sha256=sha(base / rel))
                for key, rel in roots.items()}
    qa = read(base / roots["browser_qa"])
    assert qa["status"] == "PASS" and all(c["pass"] for c in qa["checks"])
    comparison = read(base / roots["comparison"])
    assert [r["id"] for r in comparison["regions"]] == ["P1", "P1_visible", "P2", "P2_visible", "P3"]
    for key in ("sensor_tests", "evaluation_tests"):
        assert read(base / roots[key])["status"] == "PASS"
    payloads = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if any("source" in part.lower() for part in rel.parts[:-1]) and path.name != "SOURCE_MANIFEST.json":
            continue
        payloads.append(dict(path=str(path.relative_to(artifacts)), bytes=path.stat().st_size, sha256=sha(path)))
    repo_files = []
    for folder in ("scripts/phd/wu_vallet_regions_v4", "configs/phd/wu_vallet_regions_v4",
                   "docs/experiments/phd/wu_vallet_regions_v4", "src/apps/wu_vallet_regions_v4"):
        repo_files.extend(p for p in (repo / folder).rglob("*") if p.is_file())
    repo_files.extend([repo / handoff, repo / "tests/phd/test_wu_vallet_regions_evaluation_v4.py"])
    head = subprocess.check_output(["git", "-c", f"safe.directory={repo}", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert head == before["head"]
    result = dict(schema="jointbuildgs.phd.wu_vallet.regional_comparison_package.v4",
                  task_id="PHD-WU-VALLET-REGIONS-v4", status="P1_P2_UPDATES_AND_P1_P2_P3_COMPARISON_COMPLETE",
                  scientific_verdict=None, full_author_reproduction=False, GS_executed=False,
                  git_head=head, commit_or_push_performed=False,
                  created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  host_artifact_root_relative_to_repository="../JointBuildGS-artifacts",
                  container_artifact_root="/artifacts/JointBuildGS", viewer_url="http://127.0.0.1:8900/",
                  cases=[r["id"] for r in comparison["regions"]], arms_per_case=5,
                  completed_receipts=receipts,
                  preservation=dict(start_files=len(before["files"]), unchanged_files=len(unchanged),
                                    additive_handoff_only=edited, original_handoff_content_exact=True,
                                    prior_payload_hashes_verified=old_counts),
                  validation=dict(sensor_filter_tests=read(base / roots["sensor_tests"])["tests"],
                                  evaluation_tests=read(base / roots["evaluation_tests"])["tests"],
                                  browser_checks=len(qa["checks"]), browser_assets=qa.get("asset_count"),
                                  browser_screenshots=len(qa["screenshots"]), browser_status=qa["status"]),
                  interpretation="Paper-based native point updates with declared substitutes; demonstrated improvements and remaining failures are both reported. No confirmed paper failure, final contribution or official quality verdict.",
                  repo_files=[dict(path=str(p.relative_to(repo)), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(repo_files)],
                  payloads=payloads)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(dict(status=result["status"], preservation=result["preservation"], validation=result["validation"], payloads=len(payloads))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.repo, args.artifacts, args.output)
