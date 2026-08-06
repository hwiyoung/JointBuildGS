#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

run_tools python scripts/p2/e1_e6_techdev_v1/prepare_inventory.py \
  --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/00_inventory.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_prior_geometry.py \
  --artifact-root /artifacts/JointBuildGS --prep-root "/artifacts/JointBuildGS/${task_rel}/prep" \
  >"${logs_root}/00_prior_geometry.log" 2>&1
run_tools python scripts/p2/e1_e6_techdev_v1/compute_dsm_wb.py \
  --artifact-root /artifacts/JointBuildGS --prep-root "/artifacts/JointBuildGS/${task_rel}/prep" \
  >"${logs_root}/00_dsm_wb.log" 2>&1
run_tools python scripts/p2/e1_e6_techdev_v1/prepare_mvs_seed.py \
  --artifact-root /artifacts/JointBuildGS --prep-root "/artifacts/JointBuildGS/${task_rel}/prep" \
  >"${logs_root}/00_seed_dense.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_als_prior.py \
  --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/00_als_prior.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_lod_assets.py \
  --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/00_lod_prior.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_seed_unions.py \
  --prep-root "/artifacts/JointBuildGS/${task_rel}/prep" \
  >"${logs_root}/00_seed_unions.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/make_sanity.py \
  --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/00_sanity.log" 2>&1

printf 'Phase 0/1 preparation complete: %s\n' "${prep_root}"
