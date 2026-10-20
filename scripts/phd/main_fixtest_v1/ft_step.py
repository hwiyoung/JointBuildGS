"""PHD-MAIN-FIXTEST-v1: one CPU post step of stage 3 (s3_step.py: metrics_s2 / measure_s2 / bands_s2 / support_s2 / fates_s2; or stage 3's
nan_clean_s3.py) on this task's results, after ft_common re-pointed s3_common at this payload (jointbuildgs:dev; run_step_ft.sh).
  python ft_step.py <script.py> [its args ...]
scientific_verdict: null."""
import runpy
import sys

import ft_common  # noqa: F401  (re-points s3_common and patches stage 2's helpers)

script = sys.argv[1]
if script.endswith("_s3.py"):
    sys.argv = [script] + sys.argv[2:]
    runpy.run_path(f"/repo/scripts/phd/main_stage3_v1/{script}", run_name="__main__")
else:
    sys.argv = ["s3_step.py"] + sys.argv[1:]
    runpy.run_path("/repo/scripts/phd/main_stage3_v1/s3_step.py", run_name="__main__")
