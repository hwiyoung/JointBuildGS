#!/usr/bin/env bash
# OS-owned continuation of the existing queue. No agent/API calls or parameter tuning.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
driver="$repo/scripts/phd/local_complementary_refinement_v1"
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
main="$task_root/main_v2"
state="$main/automation_v2"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
main_pid=${JBGS_MAIN_QUEUE_PID:?Existing main queue PID required}
registered_retry_pid=${JBGS_REGISTERED_RETRY_PID:?Existing P3 native retry PID required}
[[ $main_pid =~ ^[0-9]+$ && $registered_retry_pid =~ ^[0-9]+$ ]]
mkdir -p "$state"
exec 8>"$state/owner.lock"
flock -n 8 || { echo 'Automation already owns this task' >&2; exit 2; }
[[ ! -e "$state/completion.json" && ! -e "$state/started.txt" ]]
date --iso-8601=seconds > "$state/started.txt"
event(){ printf '%s %s\n' "$(date --iso-8601=seconds)" "$*" >> "$state/events.log"; }
trap 'code=$?; event "ERROR exit=$code line=$LINENO current_stage=${stage:-initialization}; frozen outputs preserved"; printf "%s\n" "$code" > "$state/exit_code.txt"; exit "$code"' ERR
trap 'code=$?; if (( code != 0 )) && [[ ! -e "$state/exit_code.txt" ]]; then event "ERROR exit=$code current_stage=${stage:-initialization}; outputs preserved"; printf "%s\n" "$code" > "$state/exit_code.txt"; fi' EXIT
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
# Freeze the continuation implementation in its own receipt directory. It does
# not modify the separately frozen train/runtime tuple or existing run queue.
mkdir "$state/source_snapshot"
cp "$driver"/*_v2.py "$driver"/*_v2.sh "$state/source_snapshot/"
cp "$driver"/*_v2.mjs "$state/source_snapshot/"
cp "$repo/configs/phd/local_complementary_refinement_v1/review_sources_v2.json" "$state/initial_review_sources_v2.json"
sha256sum "$state/source_snapshot/"* > "$state/source_sha256.txt"
# Fail closed if any executing analysis launcher/module or viewer source changes
# after this worker starts. Snapshot copies retain the exact original bytes.
code_paths=("$driver"/*.py "$driver"/*.sh "$driver"/*.mjs "$repo/src/apps/local_complementary_review_v2/"*)
while IFS= read -r -d '' file; do code_paths+=("$file"); done < <(rg --files --null -g '*.py' -g '*.sh' "$repo/scripts/phd/geogs_p1p2p3_v1")
if [[ -d "$repo/src/apps/local_complementary_3d_v2" ]]; then
 while IFS= read -r -d '' file; do code_paths+=("$file"); done < <(rg --files --null "$repo/src/apps/local_complementary_3d_v2")
fi
sha256sum "${code_paths[@]}" > "$state/executing_source_sha256.txt"
printf 'main_queue_pid=%s\nregistered_P3_retry_pid=%s\n' "$main_pid" "$registered_retry_pid" > "$state/existing_processes.txt"
verify_code(){ sha256sum --check --status "$state/executing_source_sha256.txt"; }
alive_as(){
 local pid=$1 script=$2
 kill -0 "$pid" 2>/dev/null && [[ $(ps -p "$pid" -o args=) == *"$script"* ]]
}
helper(){
 verify_code
 docker run --rm --read-only --network none --cpus 1 --memory 512m --memory-swap 512m \
  --tmpfs /tmp:rw,size=64m -w /tmp --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$state/source_snapshot,dst=/audit,readonly" \
  --mount "type=bind,src=$task_root,dst=/task,readonly" \
  --mount "type=bind,src=$state,dst=/task/main_v2/automation_v2" \
  "$image" python /audit/automation_state_v2.py --task /task/main_v2 "$@"
}
run_stage(){
 stage=$1;shift
 verify_code
 event "START $stage"
 "$@" > "$batch/$stage.log" 2>&1
 verify_code
 event "PASS $stage"
}
bundle(){
 local region=$1 mode=$2 evaluation summary figures maps sources region_slug
 region_slug=${region//,/_}
 batch="$state/analysis_$(date -u +%Y%m%dT%H%M%S)_${region_slug}_${mode}"
 mkdir "$batch"
 local partial=()
 if [[ $mode == partial ]]; then partial=(--allow-partial); fi
 run_stage environment bash "$driver/capture_environment_v2.sh" "automation_$(basename "$batch")"
 if [[ $mode == partial ]]; then
  run_stage evaluate bash "$driver/run_evaluation_v2.sh" evaluate --region "$region" --allow-partial
 else
  run_stage evaluate bash "$driver/run_evaluation_v2.sh" evaluate --run-selection /task/main_v2/run_selection_v2.json
 fi
 evaluation=$(helper extract "/task/main_v2/automation_v2/$(basename "$batch")/evaluate.log" receipt)
 run_stage summary bash "$driver/run_summary_v2.sh" "$evaluation" "${partial[@]}"
 summary=$(helper extract "/task/main_v2/automation_v2/$(basename "$batch")/summary.log" output)
 run_stage figures bash "$driver/run_evaluation_v2.sh" figures "$evaluation"
 figures=$(helper resolve figures "$evaluation")
 run_stage maps bash "$driver/run_maps_v2.sh" "$evaluation"
 maps=$(helper resolve maps "$evaluation")
 run_stage figure_qa bash "$driver/run_figure_review_v2.sh" "$evaluation" "$figures" "${partial[@]}"
 run_stage map_qa bash "$driver/run_map_review_v2.sh" "$evaluation" "$maps" "${partial[@]}"
 if [[ $mode == full ]]; then
  run_stage strata bash "$driver/run_strata_v2.sh" "$evaluation"
  run_stage matrix bash "$driver/run_matrix_figures_v2.sh" "$summary"
  run_stage trace bash "$driver/run_trace_v2.sh" --selection /task/main_v2/run_selection_v2.json
  run_stage photo_cases bash "$driver/run_photo_case_summary_v2.sh" /task/main_v2/photo_target_audit/attempt_20260910T232336_211760Z "$evaluation"
  run_stage attempt_costs bash "$driver/run_attempt_costs_v2.sh"
 fi
 sources="/task/main_v2/automation_v2/$(basename "$batch")/sources.json"
 helper sources "$evaluation" "$region" "$sources"
 # Review builder mounts main_v2 as /task, unlike evaluation's parent /task.
 run_stage publish bash "$driver/build_review_v2.sh" "/task/automation_v2/$(basename "$batch")/sources.json"
 run_stage publish_3d bash "$driver/build_review_3d_v2.sh"
 run_stage browser_3d_qa bash "$driver/browser_review_3d_v2.sh"
 if [[ $mode == full ]]; then
  helper complete "$evaluation" /task/main_v2/automation_v2/completion.json --batch "/task/main_v2/automation_v2/$(basename "$batch")"
 fi
 event "PUBLISHED $region $mode evaluation=$evaluation; manual interpretation of new figures pending"
}
event 'STARTED independent OS worker; fixed policy; no agent/API calls; CPU analysis may overlap GPU training'
while [[ ! -s "$main/queue/model_phases_exit_code.txt" ]]; do
 stage=main_queue_liveness
 alive_as "$main_pid" run_queue_v2.sh || [[ -s "$main/queue/model_phases_exit_code.txt" ]]
 helper pending > "$state/pending_regions.txt"
 while IFS= read -r region; do
  [[ $region =~ ^P[123]$ ]]
  bundle "$region" partial
 done < "$state/pending_regions.txt"
 # Bounded low-cost shell timer, not an assistant wait or scheduled LLM turn.
 sleep 60
done
event 'MAIN_QUEUE_FINISHED; resolve registered retry or same-policy CUDA OOM retry'
while :; do
 helper retries > "$state/retry_plan.tsv"
 pending_retry=0
 while IFS=$'\t' read -r action region condition attempt; do
  case $action in
   SELECT) ;;
   WAIT)
    stage=registered_retry_liveness
    [[ $attempt == P3_LC_D0005_Pnative_attempt2 ]]
    alive_as "$registered_retry_pid" retry_after_queue_v2.sh || [[ -s "$main/retry_queue/$attempt/exit_code.txt" ]]
    pending_retry=1
    ;;
   RUN)
    pending_retry=1;batch="$state/retry_$attempt";mkdir "$batch"
    run_stage same_policy_retry bash "$driver/retry_after_queue_v2.sh" "$region" "$condition" "$attempt"
    ;;
   *) echo 'Invalid retry action' >&2; exit 2 ;;
  esac
 done < "$state/retry_plan.tsv"
 (( pending_retry == 0 )) && break
 sleep 60
done
selection_args=()
while IFS=$'\t' read -r action region condition attempt; do
 [[ $action == SELECT ]]
 selection_args+=(--retry "$region/$condition=retries/$attempt")
done < "$state/retry_plan.tsv"
stage=run_selection
event 'START full18 phase receipt and same-policy attempt selection validation'
docker run --rm --read-only --network none --cpus 1 --memory 1g --memory-swap 1g \
 --tmpfs /tmp:rw,size=128m -w /tmp --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
 --mount "type=bind,src=$state/source_snapshot,dst=/audit,readonly" \
 --mount "type=bind,src=$task_root,dst=/task,readonly" \
 --mount "type=bind,src=$main,dst=/task/main_v2" \
 "$image" python /audit/run_selection_v2.py build --task /task/main_v2 \
 --config /task/contracts/main_v2/experiment_v2.json --binding /task/contracts/main_v2/input_binding.json \
 --selection /task/main_v2/run_selection_v2.json "${selection_args[@]}" > "$state/selected_runs.tsv" 2> "$state/selection.stderr.log"
bundle P1,P2,P3 full
event 'COMPLETE full18 evaluation, figures, original-source QA, trace, costs, cases and review publication; scientific_verdict=null'
printf '0\n' > "$state/exit_code.txt"
