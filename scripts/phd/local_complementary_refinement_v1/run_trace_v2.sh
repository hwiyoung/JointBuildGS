#!/usr/bin/env bash
# Snapshot existing G/LC traces in a new attempt. Project analysis runs in Docker.
# Usage: run_trace_v2.sh [--no-plots] [--selection /task/main_v2/run_selection_v2.json]
set -euo pipefail
no_plots=0
selection=''
while (( $# )); do
  case "$1" in
    --no-plots) no_plots=1; shift ;;
    --selection) (( $# >= 2 )) || exit 2; selection="$2"; shift 2 ;;
    -h|--help) echo 'Usage: run_trace_v2.sh [--no-plots] [--selection /task/main_v2/run_selection_v2.json]'; exit 0 ;;
    *) echo 'Unexpected trace argument' >&2; exit 2 ;;
  esac
done
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$(readlink -f "$repo_root/../JointBuildGS-artifacts")"
task_root="$artifact_root/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent_runs="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runs_allocator_v2"
new_runs="$task_root/main_v2/runs"
config="$task_root/contracts/main_v2/experiment_v2.json"
binding="$task_root/contracts/main_v2/input_binding.json"
analyzer="$repo_root/scripts/phd/local_complementary_refinement_v1/summarize_traces_v2.py"
image_tag='jointbuildgs:geogs-official-db40c95-compat-v1'
image_id='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
[[ "$(docker image inspect --format '{{.Id}}' "$image_tag")" == "$image_id" ]] || {
  echo 'Trace image differs from the pinned main-v2 image' >&2; exit 1;
}
for required in "$config" "$binding" "$analyzer"; do test -s "$required"; done
test -d "$parent_runs"
test -d "$new_runs"
output_root="$task_root/main_v2/trace_monitor"
mkdir -p "$output_root"
attempt="$(mktemp -d "$output_root/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX_trace_v2")"
mkdir "$attempt/implementation"
cp -- "${BASH_SOURCE[0]}" "$attempt/implementation/run_trace_v2.sh"
cp -- "$analyzer" "$attempt/implementation/summarize_traces_v2.py"
printf 'host_source\tcontainer_target\taccess\n' > "$attempt/input_mount_manifest.tsv"
mounts=()
mount_readonly_file() {
  local host_source="$1" container_target="$2"
  [[ -f "$host_source" ]] || return 0
  [[ "$host_source" != *','* && "$host_source" != *$'\t'* && "$host_source" != *$'\n'* ]] || {
    echo 'Unsupported bind path separator' >&2; exit 1;
  }
  mounts+=(--mount "type=bind,src=$host_source,dst=$container_target,readonly")
  printf '%s\t%s\treadonly\n' "$host_source" "$container_target" >> "$attempt/input_mount_manifest.tsv"
}
declare -A selected_run=()
if [[ -n "$selection" ]]; then
  [[ "$selection" == /task/main_v2/*.json && "$selection" != *'..'* ]] || exit 2
  selection_host="$task_root/${selection#/task/}"
  [[ "$(readlink -f "$selection_host")" == "$task_root/main_v2/"* ]] || exit 2
  cp -- "$repo_root/scripts/phd/local_complementary_refinement_v1/run_selection_v2.py" "$attempt/implementation/run_selection_v2.py"
  cp -- "$selection_host" "$attempt/selection_snapshot.json"
  mount_readonly_file "$config" /contracts/experiment_v2.json
  mount_readonly_file "$binding" /contracts/input_binding.json
  mount_readonly_file "$attempt/implementation/run_selection_v2.py" /implementation/run_selection_v2.py
  mount_readonly_file "$attempt/selection_snapshot.json" /task/main_v2/run_selection_v2.json
  # Preflight exposes only attempt receipts and logs, including failed history.
  # No model, reference, image, or evaluation payload directory is mounted.
  shopt -s nullglob
  for metadata in "$new_runs"/P[123]/*/{train_receipt,render_receipt,metrics_receipt}.json \
      "$new_runs"/P[123]/*/train.log \
      "$task_root"/main_v2/retries/*/{train_receipt,render_receipt,metrics_receipt}.json \
      "$task_root"/main_v2/retries/*/train.log; do
    mount_readonly_file "$metadata" "/task/${metadata#"$task_root/"}"
  done
  mv "$attempt/input_mount_manifest.tsv" "$attempt/selection_preflight_mount_manifest.tsv"
  docker run --rm --read-only --network none --cpus 1 --memory 512m --memory-swap 512m \
    -e PYTHONDONTWRITEBYTECODE=1 "${mounts[@]}" --entrypoint python "$image_id" \
    /implementation/run_selection_v2.py export --task /task/main_v2 \
    --config /contracts/experiment_v2.json --binding /contracts/input_binding.json \
    --selection /task/main_v2/run_selection_v2.json > "$attempt/selected_runs.tsv" 2> "$attempt/selection_preflight.stderr.log"
  while IFS=$'\t' read -r region condition relative; do
    selected_run["$region/$condition"]="$task_root/main_v2/$relative"
  done < "$attempt/selected_runs.tsv"
  (( ${#selected_run[@]} == 18 )) || exit 1
  mounts=()
  printf 'host_source\tcontainer_target\taccess\n' > "$attempt/input_mount_manifest.tsv"
  mount_readonly_file "$attempt/selection_snapshot.json" /contracts/run_selection_v2.json
fi
mount_readonly_file "$config" /contracts/experiment_v2.json
mount_readonly_file "$binding" /contracts/input_binding.json
mount_readonly_file "$attempt/implementation/run_trace_v2.sh" /implementation/run_trace_v2.sh
mount_readonly_file "$attempt/implementation/summarize_traces_v2.py" /implementation/summarize_traces_v2.py

# Host shell enumerates only whitelisted filenames; JSON parsing and all project
# processing happen below in Docker. Absent live files stay absent in this snapshot.
# No run directory, raw input, source tree, model payload or prior report is mounted.
shopt -s nullglob
for side in G LC; do
  if [[ "$side" == G ]]; then run_root="$parent_runs"; else run_root="$new_runs"; fi
  for run_dir in "$run_root"/P[123]/*; do
    [[ -d "$run_dir" ]] || continue
    condition="${run_dir##*/}"
    region="$(basename "$(dirname "$run_dir")")"
    case "$side:$condition" in
      G:D005_Pnative|G:D005_Prelease|G:D0005_Pnative|G:D0005_Prelease|G:D0_Pnative|G:D0_Prelease|\
      LC:LC_D005_Pnative|LC:LC_D005_Prelease|LC:LC_D0005_Pnative|LC:LC_D0005_Prelease|LC:LC_D0_Pnative|LC:LC_D0_Prelease) ;;
      *) continue ;;
    esac
    if [[ "$side" == LC && -n "$selection" ]]; then
      run_dir="${selected_run["$region/$condition"]}"
    fi
    inputs=("$run_dir/train_invocation.json" "$run_dir/train_receipt.json"
      "$run_dir/model/jbgs_trace.jsonl" "$run_dir"/model/jbgs_complete/iteration_*/receipt.json)
    if [[ "$side" == LC ]]; then inputs+=("$run_dir/model/local_trace.jsonl"); fi
    for input_file in "${inputs[@]}"; do
      [[ -f "$input_file" ]] || continue
      [[ "$(readlink -f "$input_file")" == "$run_dir/"* ]] || {
        echo 'Trace input resolves outside its run root' >&2; exit 1;
      }
      relative="${input_file#"$run_dir/"}"
      mount_readonly_file "$input_file" "/runs/$side/$region/$condition/$relative"
    done
  done
done
docker_command=(docker run --rm -i --read-only --network none --cpus 2 --memory 4g --memory-swap 4g
  --user "$(id -u):$(id -g)" --tmpfs /tmp:rw,size=256m
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e MPLCONFIGDIR=/tmp/mpl
  -e "JBGS_TRACE_IMAGE_ID=$image_id" -e "JBGS_TRACE_NO_PLOTS=$no_plots"
  "${mounts[@]}" --mount "type=bind,src=$attempt,dst=/output"
  --entrypoint python "$image_id" -)
printf '%q ' "${docker_command[@]}" > "$attempt/docker_command.sh"
printf '\n' >> "$attempt/docker_command.sh"
set +e
"${docker_command[@]}" > "$attempt/docker.stdout.log" 2> "$attempt/docker.stderr.log" <<'PY'
import csv, hashlib, json, os, pathlib, resource, subprocess, sys, time, traceback
p = pathlib.Path('/output')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
started = time.time()
command = [sys.executable, '/implementation/summarize_traces_v2.py', '--parent-runs', '/runs/G',
           '--new-runs', '/runs/LC', '--config', '/contracts/experiment_v2.json',
           '--binding', '/contracts/input_binding.json', '--output', '/output/analysis']
if os.environ['JBGS_TRACE_NO_PLOTS'] == '1':
    command.append('--no-plots')
receipt = dict(schema='JBGS_TRACE_LAUNCH_v2', scientific_verdict=None, reference_accessed=False,
    command=command, started_unix=started, runtime_image_id=os.environ['JBGS_TRACE_IMAGE_ID'],
    python_version=sys.version, cgroup_cpu_max=pathlib.Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
    cgroup_memory_max=pathlib.Path('/sys/fs/cgroup/memory.max').read_text().strip(),
    network='none', gpu_requested=False, raw_gt_or_checkpoint_payload_mounted=False,
    launcher_sha256=digest(p/'implementation/run_trace_v2.sh'),
    analyzer_sha256=digest(p/'implementation/summarize_traces_v2.py'),
    input_mount_manifest_sha256=digest(p/'input_mount_manifest.tsv'),
    docker_command_sha256=digest(p/'docker_command.sh'),
    snapshot_scope='Existing whitelisted file bind mounts at launcher discovery; live JSONL inputs read separately by analyzer. Not a filesystem-atomic multi-file training snapshot.')
if (p/'selection_snapshot.json').exists():
    receipt['run_selection'] = dict(sha256=digest(p/'selection_snapshot.json'),
        resolver_sha256=digest(p/'implementation/run_selection_v2.py'),
        selected_runs_tsv_sha256=digest(p/'selected_runs.tsv'),
        preflight_mount_manifest_sha256=digest(p/'selection_preflight_mount_manifest.tsv'),
        policy='Full18 hash-verified first successful same-policy attempts; failed OOM history retained')
returncode = 1
try:
    config = json.loads(pathlib.Path('/contracts/experiment_v2.json').read_text())
    if config['runtime']['image_id'] != os.environ['JBGS_TRACE_IMAGE_ID']:
        raise ValueError('Frozen config runtime image differs from launcher image')
    mounts = list(csv.DictReader((p/'input_mount_manifest.tsv').open(), delimiter='\t'))
    receipt['readonly_input_files'] = len(mounts)
    receipt['readonly_input_targets'] = [row['container_target'] for row in mounts]
    # Analyzer already owns bound identities, live-tail parsing, status and plots.
    result = subprocess.run(command, capture_output=True, text=True)
    (p/'analyzer.stdout.log').write_text(result.stdout)
    (p/'analyzer.stderr.log').write_text(result.stderr)
    returncode = result.returncode
    if returncode:
        raise RuntimeError('Trace analyzer failed; see analyzer.stderr.log and analysis/trace_summary_failure.json if present')
    report = json.loads((p/'analysis/trace_summary.json').read_text())
    receipt.update(status='PASS', analyzer_status_counts=report['status_counts'],
        paired_iterations=report['paired_iterations'], analysis='analysis/trace_summary.json',
        matrix_status='COMPLETE_MATRIX' if report['status_counts'].get('PASS', 0) == len(config['regions'])*len(config['conditions']) else 'PARTIAL_MATRIX',
        config_sha256=report['config_sha256'], input_binding_sha256=report['input_binding_sha256'],
        report_revision=report['report_revision'], limitations=report['limitations'])
except Exception as error:
    returncode = returncode or 1
    receipt.update(status='FAIL', exception_type=type(error).__name__, exception=str(error))
    traceback.print_exc()
finally:
    receipt.update(finished_unix=time.time(), analyzer_returncode=returncode,
        analyzer_child_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024)
    receipt['outputs'] = [dict(path=str(f.relative_to(p)), bytes=f.stat().st_size, sha256=digest(f))
        for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ('docker.stdout.log', 'docker.stderr.log')]
    with (p/'runtime_receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write('\n')
print(json.dumps({k:receipt.get(k) for k in ('status', 'matrix_status', 'analyzer_status_counts', 'paired_iterations', 'scientific_verdict')}))
sys.exit(returncode)
PY
docker_exit=$?
set -e
printf '%s\n' "$docker_exit" > "$attempt/docker_exit_code.txt"
cat "$attempt/docker.stdout.log"
if (( docker_exit )); then cat "$attempt/docker.stderr.log" >&2; fi
printf 'Trace attempt: %s\n' "$attempt"
exit "$docker_exit"
