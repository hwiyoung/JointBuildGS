"""Verify and seal the additive three-region synthesis; Docker only."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import tarfile


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(repo, artifacts, output):
    assert Path("/.dockerenv").exists(), "Docker required"
    base = artifacts / "phase-payloads/phd/wu_vallet_synthesis_v7"
    before = json.loads((base / "preservation_start_v7/preservation.json").read_text())
    handoff = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
    changed = [r["path"] for r in before["files"] if sha(repo / r["path"]) != r["sha256"]]
    assert changed == [handoff], changed
    with tarfile.open(base / "preservation_start_v7/preexisting_work.tar.gz") as archive:
        old = archive.extractfile(handoff).read().decode()
    current = (repo / handoff).read_text()
    assert re.sub(r"> \*\*2026-09-07 v7 세 지역 종합.*?\n\n", "", current, count=1) == old
    previous = []
    for folder, filename in [("wu_vallet_matched_v5", "technical_result_manifest_v5.json"),
                             ("wu_vallet_p1p2_analysis_v6", "technical_result_manifest_v6.json")]:
        manifest = repo / "artifacts/manifests/phd" / folder / filename
        package = json.loads(manifest.read_text())
        for entry in package["payloads"]:
            assert sha(artifacts / entry["path"]) == entry["sha256"], entry["path"]
        previous.append(dict(path=str(manifest.relative_to(repo)), sha256=sha(manifest),
                             payload_hashes_verified=len(package["payloads"])))
    run = base / "PHD-WU-VALLET-SYNTHESIS-v7-r2"
    analysis = json.loads((run / "run/receipt.json").read_text())
    assert analysis["status"] == "THREE_REGION_FROZEN_UPDATE_QUALITY_SYNTHESIS_COMPLETE"
    assert [r["id"] for r in analysis["regions"]] == ["P1", "P2", "P3"]
    assert analysis["new_update_runs"] == 0 and not analysis["candidate_outputs_modified"]
    assert json.loads((run / "completion.json").read_text())["exit_code"] == 0
    for path, expected in analysis["input_hashes"].items():
        relative = Path(path).relative_to("/artifacts/JointBuildGS")
        assert sha(artifacts / relative) == expected
    for name, expected in analysis["outputs"].items():
        assert sha(run / "run" / name) == expected
    repo_files = [repo / handoff]
    for folder in ["scripts/phd/wu_vallet_synthesis_v7", "configs/phd/wu_vallet_synthesis_v7",
                   "docs/experiments/phd/wu_vallet_synthesis_v7"]:
        repo_files.extend(p for p in (repo / folder).rglob("*") if p.is_file())
    link_count = 0
    for path in repo_files:
        text = path.read_text()
        if path.suffix == ".py":
            ast.parse(text, filename=str(path))
        assert all(line == line.rstrip() for line in text.splitlines()), path
        if path.suffix == ".md" and path != repo / handoff:
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if link.startswith(("http:", "https:")):
                    continue
                target = Path(link) if link.startswith("/") else path.parent / link
                # Runtime records retain actual host absolute paths.
                if link.startswith("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/"):
                    target = artifacts / link.split("JointBuildGS-artifacts/", 1)[1]
                assert target.is_file(), (str(path), link)
                link_count += 1
    result = dict(status="THREE_REGION_SYNTHESIS_AND_CONTRIBUTION_AUDIT_COMPLETE",
        scientific_verdict=None, task_id=analysis["task_id"], full_author_reproduction=False,
        new_update_runs=0, new_posthoc_analysis_runs=1, new_other_method_runs=0,
        previous_packages=previous,
        preservation=dict(start_files=len(before["files"]), unchanged_files=len(before["files"])-1,
                          additive_handoff_only=changed, original_handoff_exact=True),
        validation=dict(input_hash_count=len(analysis["input_hashes"]), local_report_links=link_count,
                        python_ast=True, quantitative_receipt_sha256=sha(run / "run/receipt.json"),
                        assessment="Share with caveats", scientific_verdict=None),
        repo_files=[dict(path=str(p.relative_to(repo)), sha256=sha(p)) for p in sorted(repo_files)],
        payloads=[dict(path=str(p.relative_to(artifacts)),sha256=sha(p),bytes=p.stat().st_size)
                  for p in sorted(base.rglob("*")) if p.is_file()],
        viewer_url="http://127.0.0.1:8901/", viewer_instructions="Select P1/P2/P3 in region dropdown")
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ["status", "previous_packages", "preservation", "validation"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.repo, args.artifacts, args.output)
