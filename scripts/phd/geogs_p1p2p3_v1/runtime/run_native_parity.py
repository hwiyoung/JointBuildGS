"""Run the fixed native-example complete-state diagnostic in an isolated container."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("uninterrupted", "resumed"), required=True)
parser.add_argument("--config", type=Path, required=True)
args = parser.parse_args()
config = json.loads(args.config.read_text())
assert sha("/source/train.py") == config["source_train_sha256"]
assert sha("/source/jbgs_state.py") == config["source_sidecar_sha256"]
assert sha("/input_manifest.json") == config["input_manifest_sha256"]
assert not Path("/scene/jbgs_calibration.json").exists()
output = Path("/output")
assert not (output / "model").exists()
command = config["base_command"] + config[args.mode + "_options"]
implementation = {str(p.relative_to("/source")): sha(p) for p in sorted(Path("/source").rglob("*.py"))
                  if "submodules" not in p.parts and "__pycache__" not in p.parts}
with (output / "preflight.json").open("x") as stream:
    json.dump({"config": config, "command": command, "implementation_sha256": implementation,
               "scientific_verdict": None}, stream, indent=2)
started = time.time()
with (output / "train.log").open("x") as log, (output / "gpu.csv").open("x") as gpu_log:
    child = subprocess.Popen(command, cwd="/source", stdout=log, stderr=subprocess.STDOUT)
    while child.poll() is None:
        subprocess.run(["nvidia-smi", "--query-gpu=timestamp,uuid,memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits"], stdout=gpu_log, stderr=subprocess.DEVNULL, check=False)
        gpu_log.flush()
        time.sleep(5)
    code = child.wait()
captures = (8000, 8100) if args.mode == "uninterrupted" else (8100,)
required = [output / f"model/jbgs_complete/iteration_{iteration}/{name}" for iteration in captures
            for name in ("checkpoint.pth", "point_cloud.ply", "receipt.json")]
if args.mode == "resumed":
    required.append(output / "model/jbgs_restore.json")
validation = [{"path": str(p), "exists_nonempty": p.is_file() and p.stat().st_size > 0} for p in required]
if code == 0 and not all(row["exists_nonempty"] for row in validation):
    code = 91
receipt = {"task_id": config["task_id"], "scientific_verdict": None,
           "mode": args.mode, "status": "PASS" if code == 0 else "FAIL", "command": command,
           "runtime_image_id": config["runtime_image_id"], "config_sha256": sha(args.config),
           "input_manifest_sha256": sha("/input_manifest.json"), "implementation_sha256": implementation,
           "ld_preload": os.environ.get("LD_PRELOAD"), "ld_library_path": os.environ.get("LD_LIBRARY_PATH"),
           "started_unix": started, "finished_unix": time.time(), "wall_seconds": time.time() - started,
           "child_max_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
           "gpu_memory_metric": "5-second nvidia-smi visible-device samples, not allocator peak",
           "native_exit_code": child.returncode, "validated_exit_code": code, "validation": validation}
with (output / "receipt.json").open("x") as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt, indent=2))
raise SystemExit(code)
