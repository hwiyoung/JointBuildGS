#!/usr/bin/env bash
set -euo pipefail
v6_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
v6_artifacts=$(realpath "$v6_repo/../JointBuildGS-artifacts")
v6_browser_profile=$(mktemp -d /tmp/jbgs-p2-ab-v6-qa.XXXXXX)
v6_browser_run=${1:-PHD-P2-AB-V6-BROWSER-QA-v1}
v6_browser_output="$v6_artifacts/phase-payloads/phd/p2_ab_v6/$v6_browser_run"
v6_browser_url=${2:-http://127.0.0.1:8896/PHD-P2-AB-V6-VIEWER-v1/viewer/?view=333}
v6_browser_port=${3:-9232}
if [[ -e "$v6_browser_output" ]]; then echo "New QA output required" >&2; exit 1; fi
if ss -ltn "sport = :$v6_browser_port" | tail -n +2 | read -r _; then
  echo "Dedicated browser QA port is already occupied" >&2
  exit 1
fi
google-chrome --headless=new --enable-automation --no-first-run --no-default-browser-check \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$v6_browser_port" \
  --user-data-dir="$v6_browser_profile" --disable-dev-shm-usage about:blank \
  >"$v6_browser_profile/chrome.log" 2>&1 &
v6_browser_pid=$!
trap 'kill "$v6_browser_pid" 2>/dev/null || true' EXIT
for v6_attempt in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$v6_browser_port/json/version" >/dev/null; then break; fi
  sleep .25
done
node "$v6_repo/scripts/phd/p2_ab_v6/browser_qa.mjs" \
  "$v6_browser_url" "$v6_browser_output" "$v6_browser_profile" "$v6_browser_port"
