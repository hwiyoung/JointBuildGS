"""Bind the completed v3 artifacts and verify preservation (stdlib only)."""
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
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main(repo, artifacts, output):
    base = artifacts / "phase-payloads/phd/wu_vallet_p3_v3"
    before = read(base / "preservation_start_v3/preservation.json")
    allowed = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
    unchanged, edited = [], []
    for row in before["files"]:
        path = repo / row["path"]
        assert path.is_file(), f"Missing preserved file: {path}"
        if sha(path) == row["sha256"]:
            unchanged.append(row["path"])
        else:
            assert row["path"] == allowed, f"Unexpected change to preserved file: {path}"
            edited.append(row["path"])
    assert len(edited) == 1
    # Prove the handoff was additive: remove only the new v3 paragraph.
    with tarfile.open(base / "preservation_start_v3/preexisting_work.tar.gz") as archive:
        member = next(m for m in archive.getmembers() if m.name.endswith(allowed))
        old_handoff = archive.extractfile(member).read().decode()
    new_handoff = (repo / allowed).read_text()
    without_addendum = re.sub(r"> \*\*2026-09-07 v3 교정·가시화.*?\n\n", "", new_handoff, count=1)
    assert without_addendum == old_handoff, "Handoff original content changed"
    old_package = read(repo / "artifacts/manifests/phd/wu_vallet_p3_v2/technical_result_manifest_v2.json")
    for row in old_package["payloads"]:
        assert sha(artifacts / row["path"]) == row["sha256"], f"Changed v2 payload: {row['path']}"
    roots = {
        "filter": "PHD-WU-VALLET-P3-FILTER-v3/run/candidate_receipt.json",
        "evaluation": "PHD-WU-VALLET-P3-FILTER-v3/run/evaluation.json",
        "sor": "PHD-WU-VALLET-P3-SOR-DIAGNOSTIC-v3/run/receipt.json",
        "forensics": "PHD-WU-VALLET-P3-FORENSICS-v3/run/receipt.json",
        "viewer": "PHD-WU-VALLET-P3-VIEWER-v3/run/viewer_manifest.json",
        "browser_qa": "PHD-WU-VALLET-P3-BROWSER-QA-v3/browser_qa.json",
        "unit_tests": "PHD-WU-VALLET-P3-FILTER-v3/unit_test_receipt.json",
    }
    receipts = {key: dict(path=str((base / rel).relative_to(artifacts)), sha256=sha(base / rel))
                for key, rel in roots.items()}
    qa = read(base / roots["browser_qa"])
    assert qa["status"] == "PASS" and all(c["pass"] for c in qa["checks"])
    filter_receipt = read(base / roots["filter"])
    for arm in filter_receipt["arms"]:
        for filename, digest in arm["outputs"].items():
            assert sha(base / "PHD-WU-VALLET-P3-FILTER-v3/run" / arm["name"] / filename) == digest
    payloads = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        # Frozen source trees are bound by their complete per-file manifests.
        if any("source" in part.lower() for part in rel.parts[:-1]) and path.name != "SOURCE_MANIFEST.json":
            continue
        payloads.append(dict(path=str(path.relative_to(artifacts)), bytes=path.stat().st_size, sha256=sha(path)))
    repo_paths = []
    for folder in ("scripts/phd/wu_vallet_p3_v3", "configs/phd/wu_vallet_p3_v3", "docs/experiments/phd/wu_vallet_p3_v3"):
        repo_paths.extend(p for p in (repo / folder).rglob("*") if p.is_file())
    repo_paths.extend([repo / "tests/phd/test_wu_vallet_filter_v3.py", repo / allowed])
    head = subprocess.check_output(["git", "-c", f"safe.directory={repo}", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert head == before["head"]
    result = dict(schema="jointbuildgs.phd.wu_vallet_p3.technical_package.v3",
                  task_id="PHD-WU-VALLET-P3-FILTER-v3", status="CORRECTED_POINT_UPDATE_AND_PHOTO_VIEWER_COMPLETE",
                  scientific_verdict=None, full_author_reproduction=False, GS_executed=False,
                  created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  host_artifact_root_relative_to_repository="../JointBuildGS-artifacts",
                  container_artifact_root="/artifacts/JointBuildGS", git_head=head,
                  commit_or_push_performed=False, viewer_url="http://127.0.0.1:8899/",
                  previous_viewer_url="http://127.0.0.1:8898/", completed_receipts=receipts,
                  preservation=dict(start_files=len(before["files"]), unchanged_files=len(unchanged),
                                    additive_handoff_only=edited, original_handoff_content_exact=True,
                                    frozen_v2_payloads_sha256_verified=len(old_package["payloads"])),
                  validation=dict(browser_checks=len(qa["checks"]), browser_assets=qa["asset_count"],
                                  browser_screenshots=len(qa["screenshots"]), browser_status=qa["status"],
                                  unit_tests=read(base / roots["unit_tests"])),
                  limits=["Paper-based reproduction with declared PSMNet/multi-view and trajectory substitutions",
                          "Size threshold, edge connectivity and mixed vertex precedence are declared choices",
                          "Reference discrepancy is evaluation only, not confirmed outlier/change ground truth",
                          "SOR is a separate fixed-setting diagnostic, not the Wu paper filter"],
                  repo_files=[dict(path=str(p.relative_to(repo)), sha256=sha(p), bytes=p.stat().st_size) for p in sorted(repo_paths)],
                  payloads=payloads)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(dict(status=result["status"], preservation=result["preservation"],
                          browser_checks=len(qa["checks"]), payloads=len(payloads))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.repo, args.artifacts, args.output)
