"""Read-only interim preservation verification; no scientific payload decoding."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


repo = Path("/repo")
out = Path("/out")
baseline_path = Path("/baseline/workspace_before.json")
baseline = json.loads(baseline_path.read_text())


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-c", "safe.directory=/repo", "-C", str(repo), *args])


def byte_check_allowed(name):
    """Conservative input gate: source/docs/config/manifests only at this stage."""
    p = Path(name)
    source_suffixes = {".py", ".sh", ".js", ".mjs", ".cjs", ".css", ".html", ".md",
                       ".cpp", ".awk", ".tpl", ".ps1", ".diff", ".lock", ".env"}
    if p.suffix in source_suffixes or p.name.startswith("Dockerfile"):
        return True
    if p.suffix in {".yaml", ".yml"}:
        return True
    if p.suffix == ".json" and (name.startswith("configs/") or name.startswith("artifacts/manifests/")):
        return True
    if "/" not in name and p.suffix in {".txt", ""}:
        return True
    return False


task_prefixes = ["configs/phd/geogs_p1p2p3_v1/", "scripts/phd/geogs_p1p2p3_v1/",
                 "docs/experiments/phd/geogs_p1p2p3_v1/", "src/apps/geogs_p1p2p3_v1/",
                 "tests/phd/geogs_p1p2p3_v1/"]
task_exact = {"Dockerfile.geogs-v1", "Dockerfile.geogs-compat-v1", "Dockerfile.geogs-da3-v1",
              "artifacts/manifests/geogs_p1p2p3_v1.yaml", "tests/phd/test_geogs_input_v1.py",
              "tests/phd/test_geogs_state_v1.py"}


def task_new(name):
    return name in task_exact or any(name.startswith(prefix) for prefix in task_prefixes)


rows, changed, missing, deferred = [], [], [], []
for record in baseline["files"]:
    name = record["path"]
    path = repo / name
    row = {"path": name, "baseline_bytes": record["bytes"], "baseline_sha256": record["sha256"]}
    if not path.exists():
        row["status"] = "MISSING"; missing.append(name)
    elif path.is_symlink() or not path.resolve().is_relative_to(repo):
        row.update(status="METADATA_ONLY_SYMLINK_OR_EXTERNAL", byte_check_deferred=True)
        deferred.append(name)
    elif not path.is_file():
        row["status"] = "NOT_A_REGULAR_FILE"; changed.append(name)
    else:
        row["current_bytes"] = path.stat().st_size
        if row["current_bytes"] != record["bytes"]:
            row["size_matches"] = False; changed.append(name)
        else:
            row["size_matches"] = True
        if byte_check_allowed(name):
            row["current_sha256"] = sha(path)
            row["status"] = "PASS_BYTES" if row["current_sha256"] == record["sha256"] else "CHANGED_BYTES"
            if row["status"] == "CHANGED_BYTES" and name not in changed: changed.append(name)
        else:
            row.update(status="METADATA_ONLY_PENDING_OPAQUE_HASH_AFTER_CANDIDATE_SEAL", byte_check_deferred=True)
            deferred.append(name)
    rows.append(row)

head = git("rev-parse", "HEAD").decode().strip()
current_paths = {x.decode() for x in (set(git("ls-files", "-z").split(b"\0")) |
                                   set(git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0"))) if x}
baseline_names = {r["path"] for r in baseline["files"]}
new_paths = sorted(current_paths - baseline_names)
known_new = [name for name in new_paths if task_new(name)]
other_new = [name for name in new_paths if not task_new(name)]
status_before = Path("/baseline/status_before.txt").read_text()
status_now = git("status", "--short").decode()
before_tracked = [line for line in status_before.splitlines() if not line.startswith("??")]
now_tracked = [line for line in status_now.splitlines() if not line.startswith("??")]

services_baseline_path = Path("/baseline/services_before.txt")
current_services = [json.loads(line) for line in Path("/services_current.jsonl").read_text().splitlines() if line]
service_checks = []
baseline_ids = []
for line in services_baseline_path.read_text().splitlines():
    old_id, old_name, old_image, remainder = line.split(maxsplit=3)
    baseline_ids.append(old_id)
    matches = [row for row in current_services if row["ID"].startswith(old_id)]
    current = matches[0] if len(matches) == 1 else None
    old_ports_match = re.search(r"(?:\d+\.\d+\.\d+\.\d+:|\[::\]:|\d+/tcp|\d+/udp)", remainder)
    old_ports = remainder[old_ports_match.start():] if old_ports_match else ""
    if current:
        id_name = current["Names"] == old_name
        image_match = current["Image"] == old_image
        if re.fullmatch(r"[0-9a-f]{12}", old_image): image_match = current["Image"].removeprefix("sha256:").startswith(old_image)
        ports_match = sorted(x.strip() for x in old_ports.split(",") if x.strip()) == sorted(x.strip() for x in current["Ports"].split(",") if x.strip())
        running = current.get("State") == "running"
    else:
        id_name = image_match = ports_match = running = False
    service_checks.append({"baseline_id": old_id, "baseline_name": old_name, "baseline_image_descriptor": old_image,
                           "baseline_ports": old_ports, "current": current,
                           "same_id_and_name": id_name, "same_image_descriptor": image_match,
                           "same_published_ports": ports_match, "still_running": running,
                           "status": "PASS_IDENTITY" if all((id_name, image_match, ports_match, running)) else "DIFFERENCE_REQUIRES_REVIEW"})

new_services = [row for row in current_services if not any(row["ID"].startswith(old) for old in baseline_ids)]
problems = bool(changed or missing or head != baseline["head"] or other_new or any(r["status"] != "PASS_IDENTITY" for r in service_checks))
report = {"schema": "geogs_preservation_interim_v1", "scientific_verdict": None,
          "checked_at_utc": datetime.now(timezone.utc).isoformat(), "runtime_revision": "allocator_v2",
          "status": "DIFFERENCES_REQUIRING_REVIEW" if problems else "PARTIAL_SOURCE_AND_SERVICE_IDENTITIES_PASS_PAYLOAD_BYTES_DEFERRED",
          "baseline_sha256": sha(baseline_path), "source_script_sha256": sha(__file__),
          "head": {"baseline": baseline["head"], "current": head, "unchanged": head == baseline["head"]},
          "summary": {"baseline_files": len(rows), "byte_checks_pass": sum(r["status"] == "PASS_BYTES" for r in rows),
                      "metadata_only_pending_byte_checks": len(deferred), "changed": len(changed), "missing": len(missing),
                      "baseline_services": len(service_checks), "service_identity_pass": sum(r["status"] == "PASS_IDENTITY" for r in service_checks)},
          "preexisting_changed_files": changed, "preexisting_missing_files": missing,
          "tracked_dirty_status": {"before": before_tracked, "current": now_tracked, "unchanged": before_tracked == now_tracked},
          "new_task_paths": known_new, "new_paths_outside_task_allowlist": other_new,
          "new_task_path_allowlist": {"prefixes": task_prefixes, "exact": sorted(task_exact)},
          "files": rows, "services": service_checks, "services_not_in_baseline": new_services,
          "limitations": ["Conservative source/docs/config/manifest byte checks only; potential reference/geometry/image/tabular payloads checked for existence and size only until candidate seal.",
                          "All baseline entries checked; no baseline file excluded because it was dirty. Existing dirty thesis edits are compared to baseline bytes, not HEAD.",
                          "Service baseline stores IDs/names/image descriptors/ports/status, not immutable image SHA or start timestamp for every service. Same ID does not prove no intervening restart.",
                          "No UAS payload decoding or hashing, no existing service mutation, no checkout/index mutation, no backup/durability or final scientific-result claim."]}
with (out / "interim_allocator_v2.json").open("x") as stream: json.dump(report, stream, indent=2, ensure_ascii=False)
print(json.dumps({k: report[k] for k in ("status", "head", "summary", "preexisting_changed_files", "preexisting_missing_files", "new_paths_outside_task_allowlist")}, ensure_ascii=False))
