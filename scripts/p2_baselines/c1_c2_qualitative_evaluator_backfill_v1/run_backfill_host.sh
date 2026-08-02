#!/usr/bin/env bash
set -euo pipefail

# Exact CPU-only launcher. The render container receives only Git (ro), the
# sealed R3 derived namespace (ro), one compact reference-cell CSV (ro), and a
# fresh task output namespace (rw). Promotion is a second no-source-write
# container with no R3 or compact-cell mount.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_backfill_host.sh ABS_ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing exact project image ID}"
SOURCE_COMMIT="${3:?missing exact source commit}"
RUN_ID="${4:?missing exact run ID}"
HANDOFF_ID="P2-W2C-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1"
TASK_ID="P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1"
PACKET_REL="docs/handoffs/P2_W2C_C1_C2_QUALITATIVE_EVALUATOR_BACKFILL_v1.md"
CONFIG_REL="configs/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/render_v1.json"
ACCEPTED_REL="artifacts/manifests/handoffs/${HANDOFF_ID}/100-accepted.json"
AUTHORITY_PARSER="${REPO}/scripts/p2_baselines/c1_c2_feasibility_pilot_v1/parse_execution_authority.awk"
R3_REL="phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
COMPACT_REL="phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1/reference/reference_candidate_cells_v1.csv"
OUTPUT_REL="phase-payloads/p2-baselines/c1_c2_qualitative_evaluator_backfill_v1/P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1"
R3_ROOT="${ARTIFACT_ROOT}/${R3_REL}"
COMPACT_CELLS="${ARTIFACT_ROOT}/${COMPACT_REL}"
OUTPUT_ROOT="${ARTIFACT_ROOT}/${OUTPUT_REL}"
WALL_SECONDS=1800
OUTPUT_CAP_BYTES=2000000000
START_UNIX="$(date +%s)"

remaining_seconds() {
  local elapsed remaining
  elapsed="$(( $(date +%s) - START_UNIX ))"
  remaining="$(( WALL_SECONDS - elapsed ))"
  if (( remaining <= 0 )); then
    echo "total task wall-clock cap exhausted" >&2
    exit 2
  fi
  echo "${remaining}"
}

if [[ "${ARTIFACT_ROOT}" != /* || ! -d "${ARTIFACT_ROOT}" || -L "${ARTIFACT_ROOT}" ]]; then
  echo "artifact root must be an existing absolute non-symlink directory" >&2
  exit 2
fi
if [[ ! "${PROJECT_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ || ! "${SOURCE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "project image/source commit identity is invalid" >&2
  exit 2
fi
if [[ "${RUN_ID}" != "P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-RUN-v1" ]]; then
  echo "run ID is not the exact frozen task run" >&2
  exit 2
fi

timeout 300 git -C "${REPO}" fetch origin main
HEAD_SHA="$(git -C "${REPO}" rev-parse HEAD)"
ORIGIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"
DIRTY="$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)"
PACKET_SOURCE_COMMIT="$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
PACKET_PROJECT_IMAGE_ID="$(sed -n 's/^- project_image_id: `\(sha256:[0-9a-f]\{64\}\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
PACKET_RUN_ID="$(sed -n 's/^- run_id: `\([^`]*\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
PACKET_EXECUTION_MODE="$(sed -n 's/^- execution_mode: `\([^`]*\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
CONFIG_PROJECT_IMAGE_ID="$(sed -n 's/^  "project_image_id": "\(sha256:[0-9a-f]\{64\}\)",.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_RUN_ID="$(sed -n 's/^  "run_id": "\([^"]*\)",.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_NETWORK="$(sed -n 's/^    "network": "\([^"]*\)",.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_CPUS="$(sed -n 's/^    "cpus": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_MEMORY="$(sed -n 's/^    "memory_bytes": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_PIDS="$(sed -n 's/^    "pids_limit": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_WALL="$(sed -n 's/^    "wall_clock_seconds_hard": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_OUTPUT_CAP="$(sed -n 's/^    "new_output_bytes_hard": \([0-9]*\).*$/\1/p' "${REPO}/${CONFIG_REL}")"
if [[ "${HEAD_SHA}" != "${ORIGIN_SHA}" || -n "${DIRTY}" \
  || "${PACKET_SOURCE_COMMIT}" != "${SOURCE_COMMIT}" \
  || "${PACKET_PROJECT_IMAGE_ID}" != "${PROJECT_IMAGE_ID}" \
  || "${PACKET_RUN_ID}" != "${RUN_ID}" \
  || "${PACKET_EXECUTION_MODE}" != "QUALITATIVE_EVALUATOR_BACKFILL_REUSE_ONLY" \
  || "${CONFIG_PROJECT_IMAGE_ID}" != "${PROJECT_IMAGE_ID}" || "${CONFIG_RUN_ID}" != "${RUN_ID}" \
  || "${CONFIG_NETWORK}" != "none" || "${CONFIG_CPUS}" != "2" || "${CONFIG_MEMORY}" != "8000000000" \
  || "${CONFIG_PIDS}" != "512" || "${CONFIG_WALL}" != "${WALL_SECONDS}" || "${CONFIG_OUTPUT_CAP}" != "${OUTPUT_CAP_BYTES}" ]]; then
  echo "clean HEAD/origin or exact packet/config authority mismatch" >&2
  exit 2
fi
if ! awk -f "${AUTHORITY_PARSER}" "${REPO}/${PACKET_REL}"; then
  echo "task packet is not explicitly activated" >&2
  exit 2
fi
if [[ ! -f "${REPO}/${ACCEPTED_REL}" || -L "${REPO}/${ACCEPTED_REL}" ]]; then
  echo "exact 100-accepted receipt is absent or symlinked" >&2
  exit 2
fi
ACCEPTED_COMMIT="$(git -C "${REPO}" log -1 --format=%H -- "${ACCEPTED_REL}")"
if [[ "${ACCEPTED_COMMIT}" != "${HEAD_SHA}" ]]; then
  echo "100-accepted receipt is not the exact current commit" >&2
  exit 2
fi
if [[ "$(docker image inspect "${PROJECT_IMAGE_ID}" --format '{{.Id}}')" != "${PROJECT_IMAGE_ID}" ]]; then
  echo "local Docker image does not match exact accepted image ID" >&2
  exit 2
fi

# Git/receipt authority validation receives no artifact mount.
timeout "$(remaining_seconds)" docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --entrypoint /opt/conda/bin/python \
  -e EXPECTED_HANDOFF_ID="${HANDOFF_ID}" -e EXPECTED_TASK_ID="${TASK_ID}" \
  -e EXPECTED_IMAGE="${PROJECT_IMAGE_ID}" -e EXPECTED_ACCEPTED_COMMIT="${ACCEPTED_COMMIT}" \
  -e EXPECTED_R3_REL="${R3_REL}" -e EXPECTED_COMPACT_REL="${COMPACT_REL}" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" -c '
import hashlib, json, os, re, subprocess
path = "artifacts/manifests/handoffs/" + os.environ["EXPECTED_HANDOFF_ID"] + "/100-accepted.json"
p = json.load(open(path, encoding="utf-8"))
assert p["schema"] == "jointbuildgs.two_host_handoff.v1" and p["template_only"] is False
assert p["handoff_id"] == os.environ["EXPECTED_HANDOFF_ID"] and p["task_id"] == os.environ["EXPECTED_TASK_ID"]
assert p["state"] == "accepted" and p["direction"] == "work_to_experiment"
assert p["sender_role"] == "work_host" and p["receiver_role"] == "experiment_host"
assert p["receiver_ack"]["role"] == "experiment_host" and p["receiver_ack"]["status"] == "accepted"
assert p["transport"]["exclusive_writer_ack"] is True and p["commits"]["receipt_head"] == "SELF"
assert p["verification"]["docker_image_digest"] == os.environ["EXPECTED_IMAGE"]
pre_name = "exact 25-record pre-push SHA-256 verification"
post_name = "exact 25-record post-push SHA-256 verification"
pre = [row for row in p["verification"]["tests"] if row.get("name") == pre_name]
post = [row for row in p["verification"]["tests"] if row.get("name") == post_name]
assert len(pre) == 1 and pre[0]["passed"] == 25 and pre[0]["failed"] == 0
assert len(post) == 1 and post[0]["passed"] == 25 and post[0]["failed"] == 0
commands = [str(value).upper() for value in p["verification"]["commands"]]
assert any("PRE-PUSH" in value and "EXACT 25-RECORD ALLOWLIST" in value for value in commands)
assert any("POST-PUSH" in value and "EXACT 25-RECORD ALLOWLIST" in value for value in commands)
required = {"docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1", "artifacts/manifests/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1"}
assert required.issubset(set(p["scope"]["allowed_paths"]))
allow = json.load(open("configs/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/artifact_allowlist_v1.json", encoding="utf-8"))
assert allow["record_count"] == 25 and len(allow["records"]) == 25
canonical = json.dumps(allow["records"], sort_keys=True, separators=(",", ":")).encode()
assert allow["total_bytes"] == sum(row["bytes"] for row in allow["records"])
assert allow["record_identity_sha256"] == hashlib.sha256(canonical).hexdigest()
expected = set()
for row in allow["records"]:
    if row["source"] == "COMPACT_REFERENCE":
        assert row["path"] == os.environ["EXPECTED_COMPACT_REL"]
    relative = os.environ["EXPECTED_R3_REL"] + "/" + row["path"] if row["source"] == "R3" else row["path"]
    expected.add(("artifact://JointBuildGS/" + relative, row["bytes"], row["sha256"]))
observed = {(row["uri"], row["bytes"], row["sha256"]) for row in p["artifacts"]["records"]}
assert observed == expected
assert len(p["artifacts"]["records"]) == 25
for row in p["artifacts"]["records"]:
    assert row["verification_method"] == "sha256_rehash" and row["verified_by"] == "experiment_host"
    assert re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[^ ]+", row["verified_at"])
assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == os.environ["EXPECTED_ACCEPTED_COMMIT"]
assert p["scientific"]["scientific_verdict"] is None
'

if [[ ! -d "${R3_ROOT}" || -L "${R3_ROOT}" ]]; then
  echo "sealed R3 derived namespace is absent or symlinked" >&2
  exit 2
fi
if [[ ! -f "${COMPACT_CELLS}" || -L "${COMPACT_CELLS}" ]]; then
  echo "exact compact reference-cell CSV is absent or symlinked" >&2
  exit 2
fi
if [[ -e "${OUTPUT_ROOT}" ]]; then
  echo "fresh external task namespace already exists" >&2
  exit 2
fi
mkdir -p "${OUTPUT_ROOT}"

timeout "$(remaining_seconds)" docker run --rm --network none --read-only \
  --cpus 2 --memory 8g --pids-limit 512 --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -e MPLCONFIGDIR=/tmp/matplotlib -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${R3_ROOT}:/sealed_r3:ro" \
  -v "${COMPACT_CELLS}:/bound_inputs/reference_candidate_cells_v1.csv:ro" \
  -v "${OUTPUT_ROOT}:/task_output:rw" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/render_fixed_views.py \
    --config "/workspace/JointBuildGS/${CONFIG_REL}" \
    --repository-root /workspace/JointBuildGS --artifact-root /no_broad_artifact_mount \
    --r3-root /sealed_r3 --compact-reference-cells /bound_inputs/reference_candidate_cells_v1.csv \
    --output-dir /task_output

OUTPUT_BYTES="$(du -sb "${OUTPUT_ROOT}" | awk '{print $1}')"
if (( OUTPUT_BYTES > OUTPUT_CAP_BYTES )) || [[ ! -f "${OUTPUT_ROOT}/fixed_view_manifest_v1.json" ]]; then
  echo "external output cap or manifest completion check failed" >&2
  exit 2
fi

# Promotion has no R3, compact-cell, raw-source, validation, or held-out mount.
if [[ "$(git -C "${REPO}" rev-parse HEAD)" != "${ACCEPTED_COMMIT}" \
  || "$(git -C "${REPO}" rev-parse origin/main)" != "${ACCEPTED_COMMIT}" \
  || -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "promotion authority changed after rendering" >&2
  exit 2
fi
timeout "$(remaining_seconds)" docker run --rm --network none --read-only \
  --cpus 1 --memory 2g --pids-limit 256 --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:rw" \
  -v "${OUTPUT_ROOT}:/task_output:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/promote_results.py \
    --external-manifest /task_output/fixed_view_manifest_v1.json \
    --repo-root /workspace/JointBuildGS --promotion-parent-commit "${ACCEPTED_COMMIT}" \
    --source-commit "${SOURCE_COMMIT}" --project-image-id "${PROJECT_IMAGE_ID}" --run-id "${RUN_ID}"

echo "C1/C2 qualitative evaluator backfill render and no-source-write promotion completed."
