#!/usr/bin/env bash
# Synthetic CPU tests only; no failed-run, model, input, reference or GPU mount.
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(cd "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1" && pwd)"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
root="$task_root/runtime/native_repeat_retry_validation_v1"
mkdir -p "$root"
attempt="$(mktemp -d "$root/attempt.XXXXXX")"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/validation_launcher.sh"
printf '%s\n' "$image" > "$attempt/image_id.txt"
git -C "$repo_root" rev-parse HEAD > "$attempt/repository_head.txt"
command=(docker run --rm --read-only --network none --cpus 1 --memory 256m
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --workdir /repo
  --tmpfs /tmp:rw,exec,size=32m --mount "type=bind,src=$repo_root,dst=/repo,readonly"
  --mount "type=bind,src=$attempt,dst=/verification" "$image" python -c '
import hashlib,json,time,unittest
from pathlib import Path
start=time.monotonic()
names=["scripts/phd/geogs_p1p2p3_v1/runtime/verify_failed_repeat_archive.py","scripts/phd/geogs_p1p2p3_v1/runtime/archive_failed_repeat.sh","configs/phd/geogs_p1p2p3_v1/native_repeat_retry_v1.json","tests/phd/geogs_p1p2p3_v1/test_failed_repeat_archive.py"]
files=[dict(path=name,sha256=hashlib.sha256(Path(name).read_bytes()).hexdigest(),bytes=Path(name).stat().st_size) for name in names]
suite=unittest.defaultTestLoader.loadTestsFromName("tests.phd.geogs_p1p2p3_v1.test_failed_repeat_archive")
result=unittest.TextTestRunner(verbosity=2).run(suite)
receipt=dict(status="PASS" if result.wasSuccessful() and not result.skipped else "FAIL",scientific_verdict=None,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),wall_seconds=time.monotonic()-start,source_files=files,synthetic_only=True,actual_archive_moved=False,actual_failed_payloads_mounted=False,gpu_mounted=False)
with Path("/verification/test_receipt.json").open("x") as f: json.dump(receipt,f,indent=2)
raise SystemExit(0 if receipt["status"]=="PASS" else 1)')
printf '%q ' "${command[@]}" > "$attempt/command.sh"
printf '\n' >> "$attempt/command.sh"
if "${command[@]}" > "$attempt/stdout.log" 2> "$attempt/stderr.log"; then status=0; else status=$?; fi
printf '%s\n' "$status" > "$attempt/exit_code.txt"
cat "$attempt/stdout.log" "$attempt/stderr.log"
printf 'Synthetic archive validation: %s\n' "$attempt"
exit "$status"
