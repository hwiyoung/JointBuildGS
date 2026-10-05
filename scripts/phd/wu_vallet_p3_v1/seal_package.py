"""Seal this additive development package; performs metadata checks only."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import tarfile
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.artifact_root / "phase-payloads/phd/wu_vallet_p3_v1"
    archive = base / "preservation_20260907T0547"
    before = json.loads((archive / "preservation.json").read_text())
    handoff = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
    unchanged, changed, missing = [], [], []
    for record in before["files"]:
        current = args.repo / record["path"]
        if not current.is_file():
            missing.append(record["path"])
        elif sha256(current) == record["sha256"]:
            unchanged.append(record["path"])
        else:
            changed.append(record["path"])
    assert missing == [] and changed == [handoff], (changed, missing)
    with tarfile.open(archive / "preexisting_work.tar.gz", "r:gz") as source:
        old_handoff = source.extractfile(handoff).read().decode()
    current_handoff = (args.repo / handoff).read_text()
    assert current_handoff.split("\n", 1)[0] == old_handoff.split("\n", 1)[0]
    assert current_handoff.endswith(old_handoff.split("\n\n", 1)[1])

    roots = [args.repo / prefix / "phd/wu_vallet_p3_v1" for prefix in
             ("src", "scripts", "configs", "docs/experiments")]
    current_files = sorted({p for root in roots for p in root.rglob("*") if p.is_file()}
                           | set((args.repo / "tests/phd").glob("test_wu_vallet_*.py")))
    syntax_counts = {"python": 0, "json": 0}
    for path in current_files:
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
            syntax_counts["python"] += 1
        elif path.suffix == ".json":
            json.loads(path.read_text())
            syntax_counts["json"] += 1
        for number, line in enumerate(path.read_text().splitlines(), 1):
            assert line.rstrip() == line, (str(path), number, "trailing whitespace")

    successful = {
        "common_input": "PHD-WU-VALLET-P3-v1-r2/manifest.json",
        "controlled_ray_update": "PHD-WU-VALLET-RAY-FIXTURE-v1-r2/run/receipt.json",
        "current_image_sensor_mesh": "PHD-WU-VALLET-P3-IMAGE-SENSOR-MESH-v2/run/receipt.json",
        "source_conditioned_b": "PHD-WU-VALLET-P3-B-DEVELOPMENT-v1/run/result.json",
        "reference_evaluation": "PHD-WU-VALLET-P3-EVALUATION-v1-r2/evaluation/evaluation.json",
        "viewer": "PHD-WU-VALLET-P3-VIEWER-v1-r2/viewer/viewer_manifest.json",
        "browser_qa": "PHD-WU-VALLET-P3-BROWSER-QA-v1-r2/browser_qa.json",
    }
    receipts = {}
    for role, relative in successful.items():
        path = base / relative
        result = json.loads(path.read_text())
        assert result.get("scientific_verdict") is None
        receipts[role] = {"path": str(path.relative_to(args.artifact_root)),
                          "sha256": sha256(path), "status": result.get("status")}
    qa = json.loads((base / successful["browser_qa"]).read_text())
    assert qa["status"] == "PASS" and all(row["pass"] for row in qa["checks"])
    log = base / "PHD-WU-VALLET-P3-FINAL-VALIDATION-v1/unittest.log"
    assert "Ran 27 tests" in log.read_text() and log.read_text().rstrip().endswith("OK")

    # Hash run payloads, receipts and literature. CUDA caches and complete source
    # copies are excluded; their immutable SOURCE_MANIFEST files are included.
    payloads = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        top = path.relative_to(base).parts[0]
        if top.endswith("_cache"):
            continue
        if top.endswith("_source") and path.name != "SOURCE_MANIFEST.json":
            continue
        payloads.append({"path": str(path.relative_to(args.artifact_root)),
                         "bytes": path.stat().st_size, "sha256": sha256(path)})

    manifest = {
        "schema": "jointbuildgs.phd.wu_vallet_p3.technical_package.v1",
        "task_id": "PHD-WU-VALLET-P3-v1", "status": "PARTIAL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_verdict": None,
        "artifact_root_env": "JBGS_ARTIFACT_ROOT",
        "host_artifact_root_relative_to_repository": "../JointBuildGS-artifacts",
        "container_artifact_root": str(args.artifact_root),
        "git_head_at_start": before["head"],
        "full_original_p3_reproduced": False,
        "actual_A_to_B_executed": False,
        "completed_receipts": receipts,
        "full_reproduction_missing": [
            "ALS optical-center trajectory and native scan/beam topology",
            "author implementation/settings/checkpoint unavailable",
            "PSMNet original matching lineage replaced by explicit COLMAP depth component",
            "paper-omitted ray/triangle/small-region choices require sensitivity/equivalence checks",
        ],
        "interpretation_limits": [
            "B uses source-conditioned hypotheses, not validated P3 A authority",
            "historically used imagery and exact937-derived geometry: non-confirmatory",
            "reference EPSG:32632 versus working EPSG:25832: raw-shift numerical comparison only",
            "rendered geometry depth is alpha-transmittance weighted expected plane-hit depth",
            "bounded Gaussian center motion does not bound extracted surface motion",
        ],
        "preservation": {
            "files_checked": len(before["files"]), "unchanged_hash_count": len(unchanged),
            "missing": missing, "changed": changed,
            "original_handoff_title_and_entire_body_preserved": True,
            "archive": str(archive.relative_to(args.artifact_root)),
            "commit_or_push_performed": False,
        },
        "validation": {"docker_unit_tests": 27, "unit_test_status": "PASS",
                       "unit_test_log": str(log.relative_to(args.artifact_root)),
                       "browser_checks": len(qa["checks"]), "browser_status": "PASS",
                       "syntax": syntax_counts, "whitespace": "PASS"},
        "viewer_url": "http://127.0.0.1:8897/",
        "repo_files": [{"path": str(p.relative_to(args.repo)), "sha256": sha256(p)}
                       for p in current_files + [args.repo / handoff]],
        "payloads": payloads,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": manifest["status"], "payload_files": len(payloads),
                      "preserved_files": len(unchanged), "handoff_addendum": True,
                      "tests": 27, "browser_checks": len(qa["checks"])}))


if __name__ == "__main__":
    main()
