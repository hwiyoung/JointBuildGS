"""Seal this additive audit after verifying the pre-existing workspace bytes."""
import hashlib
import json
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


repo, audit = Path("/workspace"), Path("/audit")
before = json.loads((audit / "preservation/before.json").read_text())
handoff = "docs/experiments/phd/thesis_topic_v1/04_NEXT_SESSION_HANDOFF_ko_v1.md"
unchanged, changed = [], []
for entry in before["files"]:
    path = repo / entry["path"]
    if path.is_file() and digest(path) == entry["sha256"]:
        unchanged.append(entry["path"])
    else:
        changed.append(entry["path"])
if changed != [handoff]:
    raise RuntimeError(f"Unexpected pre-existing changes: {changed}")
with tarfile.open(audit / "preservation/preexisting_dirty.tar.gz", "r:gz") as tar:
    original = tar.extractfile(handoff).read()
if not (repo / handoff).read_bytes().endswith(original):
    raise RuntimeError("Original handoff bytes are not retained")

source = json.loads((audit / "sources/manifest.json").read_text())
for entry in source["files"]:
    if digest(audit / "sources/GeoGS" / entry["path"]) != entry["sha256"]:
        raise RuntimeError(f"Source changed: {entry['path']}")
receipt = json.loads((audit / "probe_v1/receipt.json").read_text())
for name, key in (("scripts/phd/geogs_contribution_v1/probe.py", "script_sha256"),
                  ("configs/phd/geogs_contribution_v1/probe_v1.json", "config_sha256")):
    if digest(repo / name) != receipt[key]:
        raise RuntimeError(f"Executed source/config changed: {name}")

target = repo / "artifacts/manifests/phd/geogs_contribution_v1/technical_result_manifest_v1.json"
links = 0
for doc in (repo / "docs/experiments/phd/geogs_contribution_v1").glob("*.md"):
    for link in re.findall(r"\]\(([^)]+)\)", doc.read_text()):
        if link.startswith(("http:", "https:", "#")):
            continue
        path = (doc.parent / link.split("#")[0]).resolve()
        if path != target and not path.exists():
            raise RuntimeError(f"Broken local link: {doc}: {link}")
        links += 1

new_paths = []
for root in ("docs/experiments/phd/geogs_contribution_v1", "scripts/phd/geogs_contribution_v1",
             "configs/phd/geogs_contribution_v1"):
    new_paths.extend(p for p in (repo / root).rglob("*") if p.is_file())
new_paths.append(repo / handoff)
files = [{"path": str(p.relative_to(repo)), "sha256": digest(p), "bytes": p.stat().st_size}
         for p in sorted(new_paths)]
payloads = [{"path": str(p.relative_to(audit)), "sha256": digest(p), "bytes": p.stat().st_size}
            for p in sorted(audit.rglob("*")) if p.is_file() and ".git" not in p.relative_to(audit).parts]
example_receipt = audit / "example_source/receipt.json"
example = json.loads(example_receipt.read_text()) if example_receipt.exists() else {"status": "NOT_COMPLETED"}
manifest = {
    "task_id": "PHD-GEOGS-CONTRIBUTION-v1", "status": "SOURCE_CONTROL_DIAGNOSTIC_COMPLETE",
    "created_utc": datetime.now(timezone.utc).isoformat(), "scientific_verdict": None,
    "git_head": before["git_head"], "source_commit": source["commit"],
    "external_root": "phase-payloads/phd/geogs_contribution_v1/PHD-GEOGS-CONTRIBUTION-v1",
    "scene_training_runs": 0, "native_performance_reproduction": False,
    "contribution_proven": False, "fulltext_available": False,
    "preservation": {"before_files": len(before["files"]), "unchanged": len(unchanged),
                     "additive_handoff": handoff, "original_handoff_exact_suffix": True,
                     "dirty_files_archived": len(before["dirty_files"]),
                     "external_old_results_reexecuted_or_modified": False},
    "validation": {"source_files_verified": len(source["files"]), "local_links_checked": links,
                   "executed_script_config_hashes": "PASS", "official_ast_probe": "COMPLETED",
                   "figure_visually_checked": True},
    "example_acquisition": example, "repo_files": files, "payloads": payloads,
}
target.parent.mkdir(parents=True, exist_ok=True)
with target.open("x") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print(json.dumps({"manifest": str(target), "preservation": manifest["preservation"],
                  "validation": manifest["validation"], "payload_files": len(payloads)}, ensure_ascii=False))
