"""PHD-MAIN-FIXTEST-v1: stage 3's GPU post steps (gpu_s3.py post | run = stage 1's gpu_s1 renders, image quality, TSDF 0.05 m in the box,
Gaussians by origin; evaluation-view points, floaters, the virtual-view mesh where the site has unseen wall patches) on this task's
results, after ft_common re-pointed s3_common at this payload (gpu_root = this payload's). jointbuildgs:geogs-conf-guided-v1, /source =
fork r14 (the renderer; unchanged since r12); run_gpu_ft.sh.
  python gpu_ft.py post|run <site> <result>
scientific_verdict: null."""
import runpy
import sys

sys.path.insert(0, "/repo/scripts/phd/main_fixtest_v1")
import ft_common  # noqa: F401,E402

runpy.run_path("/repo/scripts/phd/main_stage3_v1/gpu_s3.py", run_name="__main__")
