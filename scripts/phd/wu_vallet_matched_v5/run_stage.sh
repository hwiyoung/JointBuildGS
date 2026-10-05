#!/usr/bin/env bash
set -euo pipefail
wv5_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$wv5_script_dir/run_stage.py" "$@"
