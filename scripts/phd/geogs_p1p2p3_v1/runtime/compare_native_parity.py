"""Collect exact comparisons without converting numerical differences to PASS."""
import json
from pathlib import Path
import subprocess
import time

comparisons = {
    "uninterrupted_vs_resumed_8100": (
        "/uninterrupted/jbgs_complete/iteration_8100/checkpoint.pth",
        "/resumed/jbgs_complete/iteration_8100/checkpoint.pth"),
    "native_vs_instrumented_independent_8100": (
        "/native/chkpnt8100.pth", "/uninterrupted/jbgs_complete/iteration_8100/checkpoint.pth"),
}
rows = []
for name, (left, right) in comparisons.items():
    output = Path("/output") / (name + ".json")
    command = ["python", "/audit/compare_states.py", "--left", left, "--right", right, "--output", str(output)]
    started = time.monotonic()
    with output.with_suffix(".log").open("x") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    report = json.loads(output.read_text()) if output.exists() else {}
    rows.append({"name": name, "command": command, "exit_code": result.returncode,
                 "wall_seconds": time.monotonic() - started, "status": report.get("status", "EXECUTION_FAILED"),
                 "nonmatching_entries": report.get("nonmatching_entries")})
report = {"task_id": "PHD-GEOGS-P1P2P3-v1", "scientific_verdict": None, "comparisons": rows,
          "all_exact": all(row["status"] == "EXACT_PARITY" for row in rows),
          "no_posthoc_tolerance_promotion": True}
with Path("/output/comparison_receipt.json").open("x") as stream:
    json.dump(report, stream, indent=2)
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["all_exact"] else 2)
