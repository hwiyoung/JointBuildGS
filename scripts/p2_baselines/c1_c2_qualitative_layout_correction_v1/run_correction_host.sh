#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_correction_host.sh ABS_ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing project image ID}"
SOURCE_COMMIT="${3:?missing source commit}"
RUN_ID="${4:?missing run ID}"
HANDOFF_ID="P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1"
TASK_ID="P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1"
PACKET_REL="docs/handoffs/P2_W2C_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R4_v1.md"
CONFIG_REL="configs/p2_baselines/c1_c2_qualitative_layout_correction_v1/render_v1.json"
ACCEPTED_REL="artifacts/manifests/handoffs/${HANDOFF_ID}/100-accepted.json"
COMPACT_REL="phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1/reference/reference_candidate_cells_v1.csv"
OUTPUT_REL="phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r4_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1"
COMPACT_CELLS="${ARTIFACT_ROOT}/${COMPACT_REL}"
OUTPUT_ROOT="${ARTIFACT_ROOT}/${OUTPUT_REL}"
WALL_SECONDS=600
OUTPUT_CAP_BYTES=100000000
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
if [[ "${RUN_ID}" != "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-RUN-v1" \
  || ! "${PROJECT_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ || ! "${SOURCE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "run/image/source identity mismatch" >&2
  exit 2
fi

timeout "$(remaining_seconds)" git -C "${REPO}" fetch origin main
HEAD_SHA="$(git -C "${REPO}" rev-parse HEAD)"
ORIGIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"
DIRTY="$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)"
PACKET_SOURCE="$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
PACKET_IMAGE="$(sed -n 's/^- project_image_id: `\(sha256:[0-9a-f]\{64\}\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
PACKET_RUN="$(sed -n 's/^- run_id: `\([^`]*\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
PACKET_MODE="$(sed -n 's/^- execution_mode: `\([^`]*\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
CONFIG_IMAGE="$(sed -n 's/^  "project_image_id": "\(sha256:[0-9a-f]\{64\}\)",.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_RUN="$(sed -n 's/^  "run_id": "\([^"]*\)",.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_NETWORK="$(sed -n 's/^    "network": "\([^"]*\)",.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_CPUS="$(sed -n 's/^    "cpus": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_MEMORY="$(sed -n 's/^    "memory_bytes": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_PIDS="$(sed -n 's/^    "pids_limit": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_WALL="$(sed -n 's/^    "wall_clock_seconds_hard": \([0-9]*\),.*$/\1/p' "${REPO}/${CONFIG_REL}")"
CONFIG_OUTPUT_CAP="$(sed -n 's/^    "new_output_bytes_hard": \([0-9]*\).*$/\1/p' "${REPO}/${CONFIG_REL}")"
if [[ "${HEAD_SHA}" != "${ORIGIN_SHA}" || -n "${DIRTY}" || "${PACKET_SOURCE}" != "${SOURCE_COMMIT}" \
  || "${PACKET_IMAGE}" != "${PROJECT_IMAGE_ID}" || "${PACKET_RUN}" != "${RUN_ID}" \
  || "${PACKET_MODE}" != "ELIGIBILITY_LAYOUT_ONLY_CLOSED_ATTESTATION_REUSE" \
  || "${CONFIG_IMAGE}" != "${PROJECT_IMAGE_ID}" || "${CONFIG_RUN}" != "${RUN_ID}" \
  || "${CONFIG_NETWORK}" != "none" || "${CONFIG_CPUS}" != "1" || "${CONFIG_MEMORY}" != "2000000000" \
  || "${CONFIG_PIDS}" != "256" || "${CONFIG_WALL}" != "${WALL_SECONDS}" \
  || "${CONFIG_OUTPUT_CAP}" != "${OUTPUT_CAP_BYTES}" ]]; then
  echo "clean exact packet/config/HEAD authority mismatch" >&2
  exit 2
fi
if ! awk -f "${REPO}/scripts/p2_baselines/c1_c2_feasibility_pilot_v1/parse_execution_authority.awk" "${REPO}/${PACKET_REL}"; then
  echo "task packet is not activated" >&2
  exit 2
fi
if [[ ! -f "${REPO}/${ACCEPTED_REL}" || -L "${REPO}/${ACCEPTED_REL}" ]]; then
  echo "accepted receipt is absent" >&2
  exit 2
fi
ACCEPTED_COMMIT="$(git -C "${REPO}" log -1 --format=%H -- "${ACCEPTED_REL}")"
if [[ "${ACCEPTED_COMMIT}" != "${HEAD_SHA}" ]]; then
  echo "accepted receipt is not exact HEAD" >&2
  exit 2
fi
if [[ "$(docker image inspect "${PROJECT_IMAGE_ID}" --format '{{.Id}}')" != "${PROJECT_IMAGE_ID}" ]]; then
  echo "project image mismatch" >&2
  exit 2
fi

# Validate canonical ownership plus exact closed-attestation reuse with no artifact mount.
timeout "$(remaining_seconds)" docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --entrypoint /opt/conda/bin/python \
  -e EXPECTED_HANDOFF_ID="${HANDOFF_ID}" -e EXPECTED_TASK_ID="${TASK_ID}" \
  -e EXPECTED_IMAGE="${PROJECT_IMAGE_ID}" -e EXPECTED_ACCEPTED_COMMIT="${ACCEPTED_COMMIT}" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" -c '
import hashlib, json, os, subprocess, sys
accepted_rel = "artifacts/manifests/handoffs/" + os.environ["EXPECTED_HANDOFF_ID"] + "/100-accepted.json"
subprocess.run([
    sys.executable, "scripts/repository/validate_two_host_handoff.py", accepted_rel,
    "--repo", ".", "--origin-ref", "origin/main", "--head-ref", "HEAD",
], check=True)
p = json.load(open("artifacts/manifests/handoffs/" + os.environ["EXPECTED_HANDOFF_ID"] + "/100-accepted.json", encoding="utf-8"))
assert p["handoff_id"] == os.environ["EXPECTED_HANDOFF_ID"] and p["task_id"] == os.environ["EXPECTED_TASK_ID"]
assert p["state"] == "accepted" and p["transport"]["exclusive_writer_ack"] is True
assert p["verification"]["docker_image_digest"] == os.environ["EXPECTED_IMAGE"]
assert p["scientific"]["scientific_verdict"] is None
rows = p["artifacts"]["records"]
assert len(rows) == 25 and sum(int(row["bytes"]) for row in rows) == 30432763
assert all(row["verification_method"] == "closed_attestation_reuse" for row in rows)
reuse = p["artifacts"]["attestation_reuse"]
source_path = "artifacts/manifests/handoffs/P2-W2C-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1/300-closed.json"
source_bytes = open(source_path, "rb").read()
source = json.loads(source_bytes)
assert hashlib.sha256(source_bytes).hexdigest() == "7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64"
assert [(r["uri"], r["bytes"], r["sha256"]) for r in rows] == [(r["uri"], r["bytes"], r["sha256"]) for r in source["artifacts"]["records"]]
assert reuse["source_handoff_id"] == "P2-W2C-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1"
assert reuse["source_task_id"] == "P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1"
assert reuse["source_receipt_path"] == source_path
assert reuse["source_receipt_commit"] == "57205adf16def5382322ee57136b1cd66e9d07bc"
assert reuse["source_receipt_sha256"] == "7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64"
assert reuse["record_identity_sha256"] == "903b0f744c982f83106099ba280ca98d5fb362cc77867f301a31183a30bb804c"
zero = [row for row in p["verification"]["tests"] if row.get("name") == "acceptance artifact source full-read or hash passes"]
assert len(zero) == 1 and zero[0]["passed"] == 0 and zero[0]["failed"] == 0
assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == os.environ["EXPECTED_ACCEPTED_COMMIT"]
'

if [[ ! -f "${COMPACT_CELLS}" || -L "${COMPACT_CELLS}" || -e "${OUTPUT_ROOT}" ]]; then
  echo "exact compact input absent/symlinked or fresh output namespace already exists" >&2
  exit 2
fi
mkdir -p "${OUTPUT_ROOT}"

timeout "$(remaining_seconds)" docker run --rm --network none --read-only --cpus "${CONFIG_CPUS}" --memory "${CONFIG_MEMORY}" --pids-limit "${CONFIG_PIDS}" \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -e MPLCONFIGDIR=/tmp/matplotlib -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${COMPACT_CELLS}:/bound_inputs/reference_candidate_cells_v1.csv:ro" \
  -v "${OUTPUT_ROOT}:/task_output:rw" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/render_eligibility_correction.py \
    --config "/workspace/JointBuildGS/${CONFIG_REL}" --repository-root /workspace/JointBuildGS \
    --compact-reference-cells /bound_inputs/reference_candidate_cells_v1.csv --output-dir /task_output

if [[ ! -f "${OUTPUT_ROOT}/layout_correction_manifest_v1.json" \
  || "$(find "${OUTPUT_ROOT}" -maxdepth 1 -type f | wc -l)" -ne 2 \
  || "$(du -sb "${OUTPUT_ROOT}" | awk '{print $1}')" -gt "${OUTPUT_CAP_BYTES}" ]]; then
  echo "layout-correction output completion/cap mismatch" >&2
  exit 2
fi

# Promotion receives no scientific input mount and does not reopen the new PNG.
if [[ -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "repository changed before promotion" >&2
  exit 2
fi
timeout "$(remaining_seconds)" docker run --rm --network none --read-only --cpus 1 --memory 1g --pids-limit 128 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:rw" -v "${OUTPUT_ROOT}:/task_output:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/promote_results.py \
    --external-manifest /task_output/layout_correction_manifest_v1.json \
    --repo-root /workspace/JointBuildGS --source-commit "${SOURCE_COMMIT}" --accepted-commit "${ACCEPTED_COMMIT}"

echo "C1/C2 eligibility layout correction rendered and promoted pending original-pixel review."
