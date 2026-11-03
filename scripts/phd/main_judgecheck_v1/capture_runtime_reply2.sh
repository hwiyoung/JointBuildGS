#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
DEST="$OUT/r2/resources/runtime"
mkdir -p "$DEST"
deadline=$((SECONDS+259200))
while [[ ! -f "$OUT/r2/delivery_receipt.json" && $SECONDS -lt $deadline ]]; do
  while read -r container_id; do
    [[ -n "$container_id" && ! -f "$DEST/$container_id.json" ]] || continue
    if docker inspect --format '{{ $commit := "" }}{{ $declared := "" }}{{ range .Config.Env }}{{ if eq (printf "%.18s" .) "JUDGECHECK_COMMIT=" }}{{ $commit = . }}{{ end }}{{ if eq (printf "%.17s" .) "JUDGECHECK_IMAGE=" }}{{ $declared = . }}{{ end }}{{ end }}{"container_id":{{json .Id}},"name":{{json .Name}},"started_at":{{json .State.StartedAt}},"actual_image_id":{{json .Image}},"image_tag":{{json .Config.Image}},"git_commit_environment":{{json $commit}},"declared_image_environment":{{json $declared}},"entrypoint":{{json .Config.Entrypoint}},"command":{{json .Config.Cmd}},"memory_limit_bytes":{{json .HostConfig.Memory}},"memory_swap_limit_bytes":{{json .HostConfig.MemorySwap}},"nano_cpus":{{json .HostConfig.NanoCpus}},"user":{{json .Config.User}},"read_only_rootfs":{{json .HostConfig.ReadonlyRootfs}},"scientific_verdict":null}' "$container_id" > "$DEST/$container_id.json.tmp" 2>/dev/null; then
      mv "$DEST/$container_id.json.tmp" "$DEST/$container_id.json"
      date -Is > "$DEST/$container_id.observed_at.txt"
      sha256sum "$REPO/scripts/phd/main_judgecheck_v1/photo_score_reply2.py" "$REPO/scripts/phd/main_judgecheck_v1/photo_score_group_reply2.py" "$REPO/configs/phd/main_judgecheck_v1/judgecheck_v1.json" > "$DEST/$container_id.sources.sha256"
    fi
  done < <(docker ps -q --no-trunc --filter name=jbgs-judgecheck-)
  [[ "${1:-}" == once ]] && break
  sleep 5
done
