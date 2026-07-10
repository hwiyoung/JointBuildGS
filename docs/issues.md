# issues.md — 무인 런 실패·스킵 로그

> 무인 드라이버(run_overnight.sh)가 항목 실패 시 여기에 타임스탬프로 append. 아침에 검토(판정=김휘영).
> (셋업 중 d12_buckets 경로 버그로 1회 "p0c_verdict missing"가 기록됐으나 경로 수정 후 정상 — 무시. 실제 런 buckets OK·all64=64.)
- 2026-07-09 corrected-S1 w=100 full runs: distortion tail share median 2.97-3.44%, below preregistered rough 5-15% target; scene_scale_sq/prune repair still executed and evaluated as observation material, not verdict.
- 2026-07-09 corrected-S1 recheck Step 5-B: local Omnidata/DSINE mono-normal runtime and model weights not found; COLMAP/PatchMatch normals were not used as a substitute because the requested check is mono-normal. Logged as observation limitation, not verdict.
- 2026-07-09 S1 full factor B-1: first two long train wrapper logs missing after detached tool sessions; final checkpoints and audit CSVs present, fingerprint marks final_ckpt_present_log_missing (results/tum_transfer/e5_s1_full_factor/C001/train_logs)
- 2026-07-10 S2 evaluate: Docker image lacks `ogr2ogr`; evaluation initially stopped at footprint GPKG conversion. Recovered by using the existing `w2_city3d/footprints_scene_aoi.geojson` cache, then reran evaluation in Docker.
- 2026-07-10 S2 B-2: initial pipeline-strip render failed because cache defaulted to `/.cache`; recovered by setting writable cache defaults and rerunning strips with 0 final strip issues.
