#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

run_tools python -c 'import json,pathlib; p=pathlib.Path("/artifacts/JointBuildGS/'"${task_rel}"'/prep/inventory.json"); x=json.loads(p.read_text()); assert x["exact_view_manifest"]["count"]==937; assert x["depth_map_files"]==1874; assert x["normal_map_files"]==1874; print("exact Gate-S0 MVS reused: 937 views, 1874 depth, 1874 normal")' \
  >"${logs_root}/01_mvs.log" 2>&1

printf 'MVS common-base validation complete; no duplicate reconstruction executed.\n'
