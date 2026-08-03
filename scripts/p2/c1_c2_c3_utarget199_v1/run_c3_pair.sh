#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
task_name="P2-C1-C2-C3-UTARGET199-SEED-RECOVERY-v1"
task_root="${artifact_root}/phase-payloads/p2/c1_c2_c3_utarget199_v1/${task_name}"
image="jointbuildgs:dev"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
gpu_index=""

if [[ "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)" != "" ]]; then
  echo "production C3 pair requires a clean source checkout" >&2
  exit 2
fi
if [[ "$(docker image inspect "$image" --format '{{.Id}}')" != "$expected_image" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
if [[ -e "$task_root" ]]; then
  echo "add-once task namespace already exists: $task_root" >&2
  exit 2
fi

while IFS=, read -r index free; do
  index="${index// /}"
  free="${free// /}"
  if (( free >= 22000 )); then
    gpu_index="$index"
    break
  fi
done < <(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits)
if [[ -z "$gpu_index" ]]; then
  echo "no exclusive GPU has the required 22000 MiB free" >&2
  exit 2
fi
free_mib="$(nvidia-smi --id="$gpu_index" --query-gpu=memory.free --format=csv,noheader,nounits)"
gpu_uuid="$(nvidia-smi --id="$gpu_index" --query-gpu=uuid --format=csv,noheader)"

mkdir -p "$task_root/control" "$task_root/c3/common" "$task_root/scratch"
nvidia-smi -q -i "$gpu_index" > "$task_root/control/gpu_before.txt"
git -C "$repo_root" rev-parse HEAD > "$task_root/control/source_commit.txt"
printf '%s\n' "index=$gpu_index" "uuid=$gpu_uuid" "free_mib=$free_mib" > "$task_root/control/selected_gpu.txt"

common=(
  docker run --rm --network none --shm-size 16g
  --user "$(id -u):$(id -g)"
  -v "$repo_root:/workspace/JointBuildGS:ro"
  -v "$artifact_root:/artifacts/JointBuildGS"
  -w /workspace/JointBuildGS
  "$image"
)

"${common[@]}" python scripts/stage2/prepare_c3_dense_seed.py \
  --utarget199-neutral \
  --input /artifacts/JointBuildGS/phase-payloads/p0-audit/data/work/mvs/openmvs/dim_dense.ply \
  --output "/artifacts/JointBuildGS/phase-payloads/p2/c1_c2_c3_utarget199_v1/${task_name}/c3/common/neutral_dense_seed.ply" \
  --receipt "/artifacts/JointBuildGS/phase-payloads/p2/c1_c2_c3_utarget199_v1/${task_name}/c3/common/neutral_dense_seed.receipt.json" \
  --temp-parent "/artifacts/JointBuildGS/phase-payloads/p2/c1_c2_c3_utarget199_v1/${task_name}/scratch" \
  > "$task_root/control/neutral_dense_seed.stdout.json"

python - "$task_root/c3/common/neutral_dense_seed.receipt.json" <<'PY'
import json
import sys
receipt = json.load(open(sys.argv[1], encoding="utf-8"))
count = int(receipt["output"]["vertex_count"])
if not 0 < count <= 220_000:
    raise SystemExit(f"neutral dense count outside memory contract: {count}")
if receipt["training_side_contract"]["classification_or_semantic_filtering"]:
    raise SystemExit("neutral seed unexpectedly used classification")
print(f"neutral dense seed points={count}; max initial={count + 371_808}")
PY

run_train() {
  local name="$1"
  local config="$2"
  local log="$task_root/control/${name}.log"
  free_mib="$(nvidia-smi --id="$gpu_index" --query-gpu=memory.free --format=csv,noheader,nounits)"
  if (( free_mib < 22000 )); then
    echo "selected GPU no longer has the required 22000 MiB before ${name}: ${free_mib}" >&2
    exit 2
  fi
  docker run --rm --network none --shm-size 16g \
    --name "jbgs-ut199-${name}" \
    --gpus "device=${gpu_index}" \
    --user "$(id -u):$(id -g)" \
    -e CUDA_VISIBLE_DEVICES=0 \
    -v "$repo_root:/workspace/JointBuildGS:ro" \
    -v "$artifact_root:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$image" \
    python -m src.stage2.train --config "$config" 2>&1 | tee "$log"
}

run_train c3-1 configs/p2/c1_c2_c3_utarget199_v1/c3_1_sem_seed0.yaml
run_train c3-2 configs/p2/c1_c2_c3_utarget199_v1/c3_2_sem_depth_seed0.yaml

nvidia-smi -q -i "$gpu_index" > "$task_root/control/gpu_after.txt"
python - "$task_root" <<'PY'
from pathlib import Path
import json
import sys
import torch

root = Path(sys.argv[1])
rows = []
for name, rel in (
    ("C3_1_SEM", "c3/c3_1_sem/seed0/ckpt/final.pt"),
    ("C3_2_SEM_DEPTH", "c3/c3_2_sem_depth/seed0/ckpt/final.pt"),
):
    path = root / rel
    payload = torch.load(path, map_location="cpu", weights_only=False)
    rows.append({
        "condition": name,
        "path": rel,
        "bytes": path.stat().st_size,
        "iteration": int(payload.get("it", -1)),
        "primitive_count": int(payload["n_prim"]),
    })
if any(row["iteration"] != 30_000 for row in rows):
    raise SystemExit("paired final checkpoint iteration mismatch")
(root / "control/c3_pair_completion.json").write_text(
    json.dumps({
        "schema": "jointbuildgs.c3_utarget199_pair_completion.v1",
        "status": "COMPLETED",
        "rows": rows,
        "gpu_selection": (root / "control/selected_gpu.txt").read_text(encoding="utf-8").splitlines(),
        "sequential": True,
        "scientific_verdict": None,
    }, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

echo "C3 pair completed: $task_root"
