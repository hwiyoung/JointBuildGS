"""PHD-MAIN-FIXTEST-v1: the post steps of stage 3 on this task's results (container side; jointbuildgs:dev or geogs-conf-guided-v1).
Stage 3's s3_common re-points stage 2's helpers at stage 3's payload; here its two globals are re-pointed at THIS payload before
anything else uses them: S3 -> /ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1 (mounted read-write there) and S3_RESULTS -> the results of
ft_plan.RUNS. Every function of s3_common (run_dir, result_paths, stage_root, metrics_file, patch, ...) reads these globals at call time,
so the stage-2 / stage-1 steps run unchanged and write their outputs (metrics, measure, bands, support, fates, gpu_root) into this payload.
The results of earlier tasks (stage 1, stage 2, stage 3, fix) resolve where they lived (read-only). scientific_verdict: null."""
import sys

sys.path.insert(0, "/repo/scripts/phd/main_stage3_v1")
sys.path.insert(0, "/repo/scripts/phd/main_fixtest_v1")
import s3_common as S3C  # noqa: E402
import ft_plan as FP  # noqa: E402

FT = S3C.PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S3C.S3 = FT
S3C.S3_RESULTS = {(r["site"], r["result"]) for r in FP.RUNS}
S3C.patch()
