#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
task_name="P2-C1-C2-C3-UTARGET199-C3-2-GPU0-RECOVERY-v1"
task_root="${artifact_root}/phase-payloads/p2/c1_c2_c3_utarget199_v1/${task_name}"
prior_name="P2-C1-C2-C3-UTARGET199-TORCH-CACHE-RECOVERY-v1"
prior_root="${artifact_root}/phase-payloads/p2/c1_c2_c3_utarget199_v1/${prior_name}"
seed_name="P2-C1-C2-C3-UTARGET199-FRAME-RECOVERY-v1"
seed_root="${artifact_root}/phase-payloads/p2/c1_c2_c3_utarget199_v1/${seed_name}"
semantic_host="${artifact_root}/phase-payloads/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1/c3/prep/semantic_937_colmap_undistorted_r2/output/masks"
config="configs/p2/c1_c2_c3_utarget199_v1/c3_2_sem_depth_seed0_gpu0_recovery.yaml"
image="jointbuildgs:dev"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
expected_c3_1_bytes="86802780"
expected_c3_1_sha256="b4f8ce6d97da6d7cef216b4edb3239ac005cc44f4d45cb459a25644ed79b62ea"
gpu_index="0"

if [[ -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "C3-2 recovery requires a clean source checkout" >&2
  exit 2
fi
if [[ "$(git -C "${repo_root}" rev-parse HEAD)" != "$(git -C "${repo_root}" rev-parse origin/main)" ]]; then
  echo "C3-2 recovery requires HEAD=origin/main" >&2
  exit 2
fi
if [[ "$(docker image inspect "${image}" --format '{{.Id}}')" != "${expected_image}" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
if [[ -e "${task_root}" ]]; then
  echo "add-once task namespace already exists: ${task_root}" >&2
  exit 2
fi
prior_final="${prior_root}/c3/c3_1_sem/seed0/ckpt/final.pt"
if [[ ! -f "${prior_final}" || -L "${prior_final}" ]]; then
  echo "sealed C3-1 final checkpoint missing/non-regular" >&2
  exit 2
fi
if [[ "$(stat -c %s "${prior_final}")" != "${expected_c3_1_bytes}" \
  || "$(sha256sum "${prior_final}" | cut -d' ' -f1)" != "${expected_c3_1_sha256}" ]]; then
  echo "sealed C3-1 final checkpoint identity mismatch" >&2
  exit 2
fi
if [[ ! -f "${seed_root}/c3/common/neutral_dense_seed.ply" ]]; then
  echo "sealed seed missing" >&2
  exit 2
fi
docker run --rm --network none \
  -v "${semantic_host}:/inputs/semantic_masks:ro" \
  "${image}" python -c \
  "from pathlib import Path; p=Path('/inputs/semantic_masks'); assert p.is_dir() and len(list(p.iterdir())) == 937"
free_mib="$(nvidia-smi --id="${gpu_index}" --query-gpu=memory.free --format=csv,noheader,nounits | tr -d ' ')"
if (( free_mib < 22000 )); then
  echo "GPU0 does not satisfy the 22000 MiB free recovery gate: ${free_mib}" >&2
  exit 2
fi
gpu_uuid="$(nvidia-smi --id="${gpu_index}" --query-gpu=uuid --format=csv,noheader)"

mkdir -p \
  "${task_root}/control/torch_extensions" \
  "${task_root}/control/cache" \
  "${task_root}/c3/c3_1_sem/seed0/ckpt" \
  "${task_root}/c3/common" \
  "${task_root}/scratch"
cp --reflink=auto -- "${prior_final}" "${task_root}/c3/c3_1_sem/seed0/ckpt/final.pt"
nvidia-smi -q -i "${gpu_index}" > "${task_root}/control/gpu_before.txt"
git -C "${repo_root}" rev-parse HEAD > "${task_root}/control/source_commit.txt"
printf '%s\n' "index=${gpu_index}" "uuid=${gpu_uuid}" "free_mib=${free_mib}" > "${task_root}/control/selected_gpu.txt"
printf '%s\n' "${prior_final}" > "${task_root}/control/reused_c3_1_final_path.txt"

docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${task_root}/c3/c3_1_sem/seed0/ckpt/final.pt:/checkpoint/final.pt:ro" \
  -w /workspace/JointBuildGS "${image}" -c \
  "import torch; p=torch.load('/checkpoint/final.pt',map_location='cpu',weights_only=False); assert int(p['it']) == 30000 and int(p['n_prim']) == 333738"

docker run --rm --network none --shm-size 16g \
  --name jbgs-ut199-c3-2-gpu0-recovery \
  --gpus "device=${gpu_index}" \
  --user "$(id -u):$(id -g)" \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e HOME=/tmp \
  -e XDG_CACHE_HOME="/artifacts/JointBuildGS/phase-payloads/p2/c1_c2_c3_utarget199_v1/${task_name}/control/cache" \
  -e TORCH_EXTENSIONS_DIR="/artifacts/JointBuildGS/phase-payloads/p2/c1_c2_c3_utarget199_v1/${task_name}/control/torch_extensions" \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -v "${semantic_host}:/inputs/semantic_masks:ro" \
  -w /workspace/JointBuildGS "${image}" \
  python -m src.stage2.train --config "${config}" 2>&1 | tee "${task_root}/control/c3-2.log"

nvidia-smi -q -i "${gpu_index}" > "${task_root}/control/gpu_after.txt"
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" \
  -v "${task_root}:/task:rw" "${image}" -c \
  "from pathlib import Path; import hashlib,json,torch; root=Path('/task'); specs=(('C3_1_SEM','c3/c3_1_sem/seed0/ckpt/final.pt'),('C3_2_SEM_DEPTH','c3/c3_2_sem_depth/seed0/ckpt/final.pt')); rows=[]; [rows.append({'condition':n,'path':r,'bytes':(p:=root/r).stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'iteration':int((q:=torch.load(p,map_location='cpu',weights_only=False))['it']),'primitive_count':int(q['n_prim'])}) for n,r in specs]; assert all(x['iteration']==30000 for x in rows); (root/'control/c3_pair_completion.json').write_text(json.dumps({'schema':'jointbuildgs.c3_utarget199_pair_completion.v1','status':'COMPLETED_RECOVERED_GPU0','rows':rows,'gpu_selection':(root/'control/selected_gpu.txt').read_text().splitlines(),'sequential':True,'c3_1_reused_exact':True,'scientific_verdict':None},indent=2,sort_keys=True)+'\n')"

echo "C3 pair completed through GPU0 recovery: ${task_root}"
