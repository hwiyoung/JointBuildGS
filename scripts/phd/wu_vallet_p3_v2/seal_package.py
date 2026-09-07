"""Metadata-only sealing of the completed additive v2 package; run in Docker."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import tarfile

from scripts.phd.wu_vallet_p3_v2.update_points import sha, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists(): raise RuntimeError("Docker required")
    base = args.artifact_root / "phase-payloads/phd/wu_vallet_p3_v2"
    preservation = base / "preservation_start_v2"
    before = json.loads((preservation / "preservation.json").read_text())
    missing, changed, unchanged = [], [], []
    handoff = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
    for item in before["files"]:
        path = args.repo / item["path"]
        if not path.is_file(): missing.append(item["path"])
        elif sha(path) != item["sha256"]: changed.append(item["path"])
        else: unchanged.append(item["path"])
    assert not missing and changed == [handoff], (missing, changed)
    with tarfile.open(preservation / "preexisting_work.tar.gz") as archive:
        old = archive.extractfile(handoff).read().decode()
    new = (args.repo / handoff).read_text()
    assert new.split("\n", 1)[0] == old.split("\n", 1)[0]
    assert new.endswith(old.split("\n\n", 1)[1])
    sources = []
    for prefix in ("src", "scripts", "configs", "docs/experiments"):
        sources.extend(p for p in (args.repo / prefix / "phd/wu_vallet_p3_v2").rglob("*") if p.is_file())
    sources += [args.repo / "tests/phd" / name for name in (
        "test_wu_vallet_acquisition_v2.py", "test_wu_vallet_trajectory_v2.py", "test_wu_vallet_ray_runtime_v2.py")]
    for path in sources:
        text = path.read_text()
        assert all(line.rstrip() == line for line in text.splitlines()), path
        if path.suffix == ".py": ast.parse(text, filename=str(path))
        if path.suffix == ".json": json.loads(text)
    log = base / "PHD-WU-VALLET-P3-VALIDATION-v2/unit_tests.log"
    assert "Ran 35 tests" in log.read_text() and log.read_text().rstrip().endswith("OK")
    qa_path = base / args.qa / "browser_qa.json"
    qa = json.loads(qa_path.read_text())
    assert qa["status"] == "PASS"
    receipts = {
        "acquisition": "PHD-WU-VALLET-P3-ACQUISITION-v2/receipt.json",
        "trajectory": "PHD-WU-VALLET-P3-TRAJECTORY-v2/receipt.json",
        "native_point_update": "PHD-WU-VALLET-P3-UPDATE-v2/run/receipt.json",
        "origin_sensitivity": "PHD-WU-VALLET-P3-ORIGIN-SENSITIVITY-v2/receipt.json",
        "reference_evaluation": "PHD-WU-VALLET-P3-EVALUATION-v2/run/evaluation.json",
        "viewer": "PHD-WU-VALLET-P3-VIEWER-v2-r2/run/viewer_manifest.json",
        "browser_qa": str(qa_path.relative_to(base)),
    }
    records = {}
    for name, rel in receipts.items():
        path = base / rel; obj = json.loads(path.read_text())
        assert obj.get("scientific_verdict") is None
        records[name] = {"path": str(path.relative_to(args.artifact_root)), "sha256": sha(path), "status": obj.get("status")}
    update = json.loads((base / receipts["native_point_update"]).read_text())
    assert len(update["arms"]) == 12 and update["estimated_bidirectional_executed"]
    assert update["reference_accessed"] is False and update["GS_executed"] is False
    payloads = []
    for path in sorted(base.rglob("*")):
        if not path.is_file(): continue
        if any(part.endswith("_source") for part in path.relative_to(base).parts) and path.name != "SOURCE_MANIFEST.json": continue
        payloads.append({"path": str(path.relative_to(args.artifact_root)), "bytes": path.stat().st_size, "sha256": sha(path)})
    result = {
        "schema": "jointbuildgs.phd.wu_vallet_p3.technical_package.v2",
        "task_id": "PHD-WU-VALLET-P3-UPDATE-v2", "status": "PAPER_BASED_POINT_UPDATE_COMPLETE",
        "scientific_verdict": None, "created_utc": datetime.now(timezone.utc).isoformat(),
        "host_artifact_root_relative_to_repository": "../JointBuildGS-artifacts",
        "artifact_root_env": "JBGS_ARTIFACT_ROOT", "container_artifact_root": str(args.artifact_root),
        "git_head_at_start": before["head"], "commit_or_push_performed": False,
        "full_author_reproduction": False, "GS_executed": False,
        "estimated_bidirectional_point_update_executed": True,
        "completed_receipts": records,
        "remaining_reproduction_limits": update["adaptations"],
        "preservation": {"files_checked": len(before["files"]), "unchanged_hash_count": len(unchanged),
                         "missing": missing, "changed": changed, "handoff_entire_prior_body_preserved": True},
        "validation": {"unit_tests": 35, "unit_tests_status": "PASS", "browser_status": "PASS",
                       "browser_checks": len(qa.get("checks", [])), "syntax_and_whitespace": "PASS"},
        "viewer_url": "http://127.0.0.1:8898/",
        "repo_files": [{"path": str(p.relative_to(args.repo)), "sha256": sha(p)} for p in sorted(sources) + [args.repo / handoff]],
        "payloads": payloads,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True); write(args.output, result)
    print(json.dumps({"status": result["status"], "preserved": len(unchanged), "payload_files": len(payloads),
                      "unit_tests": 35, "browser_status": "PASS"}))


if __name__ == "__main__": main()
