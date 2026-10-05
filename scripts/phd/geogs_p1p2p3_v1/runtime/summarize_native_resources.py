"""Summarize native phase receipts and sampled device resources without reruns."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output-root", required=True, type=Path)
args = parser.parse_args()
rows = []
for phase in ("train", "render", "metrics"):
    receipt_path = args.output_root / f"{phase}_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "PASS"
    with (args.output_root / f"{phase}_gpu.csv").open() as stream:
        samples = [[value.strip() for value in row] for row in csv.reader(stream) if row]
    rows.append({"phase": phase, "wall_seconds": receipt["wall_seconds"],
                 "child_peak_rss_bytes": receipt["child_max_rss_kib"] * 1024,
                 "gpu_sample_count": len(samples),
                 "sampled_device_memory_peak_mib": max(float(row[2]) for row in samples),
                 "sampled_device_utilization_mean_percent": sum(float(row[3]) for row in samples) / len(samples),
                 "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()})
summary = {"task_id": "PHD-GEOGS-P1P2P3-v1", "scientific_verdict": None,
           "status": "PASS_NATIVE_30000_TRAIN_RENDER_METRICS", "phases": rows,
           "total_successful_phase_wall_seconds": sum(row["wall_seconds"] for row in rows),
           "setup_failed_runs_and_parity_preflights_excluded_from_this_successful_run_total": True,
           "memory_definition": "5-second nvidia-smi device-used samples; includes CUDA context, not allocator peak",
           "metric_receipt_terminology_clarification": {
               "preserved_field": "metrics_receipt.json validation independent_test_count",
               "correct_meaning": "Two images withheld from native GS training; author DA3 evaluation-image participation is UNKNOWN, so full-pipeline independence is not established",
               "regional_performance_evidence": False}}
with (args.output_root / "resource_summary_v1.json").open("x") as stream:
    json.dump(summary, stream, indent=2)
print(json.dumps(summary, indent=2))
