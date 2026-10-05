#!/usr/bin/env bash
# Sealed aggregate CSVs only. The existing analyzer owns scientific validation.
set -euo pipefail
source_path=${1:?Expected exact /task/main_v2/evaluation/attempt_*}
[[ $# == 1 && $source_path =~ ^/task/main_v2/evaluation/attempt_[A-Za-z0-9_]+$ ]]
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
source_host=$(realpath "$task_root/${source_path#/task/}")
[[ $source_host == "$task_root/main_v2/evaluation/${source_path##*/}" ]]
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
output_root="$task_root/main_v2/strata_diagnostic"
mkdir -p "$output_root"
attempt=attempt_$(date -u +%Y%m%dT%H%M%S_%NZ)
[[ ! -e "$output_root/$attempt" ]]
args=(--rm -i --network none --read-only --cpus 2 --memory 2g --memory-swap 2g
      --tmpfs /tmp:rw,size=128m --user "$(id -u):$(id -g)"
      -e PYTHONDONTWRITEBYTECODE=1 -e "JBGS_RUNTIME_IMAGE_ID=$image"
      -e "JBGS_STRATA_SOURCE=$source_path" -e "JBGS_STRATA_OUTPUT=/task/main_v2/strata_diagnostic/$attempt")
for file in receipt.json config_snapshot.json paired_transitions.csv anchor_global_local_transitions.csv coverage.csv; do
    test -s "$source_host/$file"
    [[ $(realpath "$source_host/$file") == "$source_host/$file" ]]
    args+=(--mount "type=bind,src=$source_host/$file,dst=$source_path/$file,readonly")
done
args+=(--mount "type=bind,src=$repo_root/scripts/phd/local_complementary_refinement_v1/analyze_strata_v2.py,dst=/audit/analyze_strata_v2.py,readonly"
       --mount "type=bind,src=$repo_root/scripts/phd/local_complementary_refinement_v1/run_strata_v2.sh,dst=/audit/run_strata_v2.sh,readonly"
       --mount "type=bind,src=$output_root,dst=/task/main_v2/strata_diagnostic")
exec docker run "${args[@]}" "$image" python - <<'PY'
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def digest(data):return hashlib.sha256(data).hexdigest()
def record(path):
    path=Path(path)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path.read_bytes()))
def write_new(path,data):
    with Path(path).open('xb') as stream:stream.write(data)

source=Path(os.environ['JBGS_STRATA_SOURCE']);output=Path(os.environ['JBGS_STRATA_OUTPUT'])
if output.exists():raise FileExistsError(output)
analyzer_bytes=Path('/audit/analyze_strata_v2.py').read_bytes()
launcher_bytes=Path('/audit/run_strata_v2.sh').read_bytes()
# Execute the captured bytes, so a concurrent checkout edit cannot change this run.
captured=Path('/tmp/analyze_strata_v2.py');write_new(captured,analyzer_bytes)
command=[sys.executable,str(captured),'--source',str(source),'--output',str(output)]
started=time.time()
process=subprocess.run(command,capture_output=True)
if not output.exists():output.mkdir(parents=False,exist_ok=False)
write_new(output/'launcher_snapshot.sh',launcher_bytes)
write_new(output/'launcher_stdout.log',process.stdout)
write_new(output/'launcher_stderr.log',process.stderr)
runtime=dict(image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'],python=sys.version,
    cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
    memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
    memory_swap_max=Path('/sys/fs/cgroup/memory.swap.max').read_text().strip(),
    network='none',gpu_requested=False,raw_gt_models_or_parent_mounted=False)
receipt=dict(schema='jbgs.local_complementary_strata_launcher.v2',
    status='PASS' if process.returncode==0 else 'FAIL_ANALYZER',scientific_verdict=None,
    created_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.time()-started,
    command=command,source_evaluation=str(source),output=str(output),exit_code=process.returncode,
    analyzer_sha256=digest(analyzer_bytes),launcher_sha256=digest(launcher_bytes),runtime=runtime,
    validation_authority='Unmodified analyze_strata_v2.py; launcher does not alter thresholds, counts, partitions or verdict',
    inputs=[record(source/name) for name in ('receipt.json','config_snapshot.json','paired_transitions.csv',
            'anchor_global_local_transitions.csv','coverage.csv')],
    outputs=[dict(record(path),path=str(path.relative_to(output))) for path in sorted(output.rglob('*')) if path.is_file()])
write_new(output/'launcher_receipt.json',(json.dumps(receipt,indent=2,allow_nan=False)+'\n').encode())
sys.stdout.buffer.write(process.stdout);sys.stderr.buffer.write(process.stderr)
print(json.dumps(dict(status=receipt['status'],output=str(output),scientific_verdict=None,
    launcher_receipt_sha256=digest((output/'launcher_receipt.json').read_bytes()))),flush=True)
raise SystemExit(process.returncode)
PY
