"""Run one unchanged native example phase with a concrete command and receipt."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("--phase", required=True, choices=("train", "render", "metrics"))
parser.add_argument("--config", required=True, type=Path)
args = parser.parse_args()
config = json.loads(args.config.read_text())
output = Path("/output")
output.mkdir(parents=True, exist_ok=True)
receipt_path = output / (args.phase + "_receipt.json")
assert not receipt_path.exists()
if args.phase == "train":
    assert not (output / "model").exists()
command = config[args.phase + "_command"]
started = time.time()
with (output / (args.phase + ".log")).open("x") as log, (output / (args.phase + "_gpu.csv")).open("x") as gpu_log:
    child = subprocess.Popen(command, cwd="/source", stdout=log, stderr=subprocess.STDOUT)
    while child.poll() is None:
        subprocess.run(["nvidia-smi", "--query-gpu=timestamp,uuid,memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits"], stdout=gpu_log, stderr=subprocess.DEVNULL, check=False)
        gpu_log.flush()
        time.sleep(5)
    code = child.wait()
validation = []
if code == 0:
    if args.phase == "train":
        required = [output / "model/point_cloud/iteration_30000/point_cloud.ply"]
        required += [output / f"model/chkpnt{iteration}.pth" for iteration in (8000, 8100, 30000)]
        validation = [{"path": str(path), "exists_nonempty": path.is_file() and path.stat().st_size > 0} for path in required]
        if not all(entry["exists_nonempty"] for entry in validation):
            code = 91
    elif args.phase == "render":
        required = [output / "model/train/ours_30000/fuse.ply", output / "model/train/ours_30000/fuse_post.ply"]
        validation = [{"path": str(path), "exists_nonempty": path.is_file() and path.stat().st_size > 0} for path in required]
        if not all(entry["exists_nonempty"] for entry in validation):
            code = 92
        else:
            import numpy as np
            import open3d as o3d
            for path, entry in zip(required, validation):
                mesh = o3d.io.read_triangle_mesh(str(path))
                vertices, triangles = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
                entry.update(vertices=len(vertices), triangles=len(triangles),
                             finite_vertices=bool(np.isfinite(vertices).all()),
                             surface_area=float(mesh.get_surface_area()))
                if not (len(triangles) and entry["finite_vertices"] and entry["surface_area"] > 0):
                    code = 92
    elif args.phase == "metrics":
        try:
            aggregate = json.loads((output / "model/results.json").read_text())["ours_30000"]
            per_view = json.loads((output / "model/per_view.json").read_text())["ours_30000"]
            assert all(math.isfinite(aggregate[key]) for key in ("PSNR", "SSIM", "LPIPS"))
            assert all(len(per_view[key]) == config["test_views"] for key in ("PSNR", "SSIM", "LPIPS"))
            validation = [{"native_gs_test_count": config["test_views"], "metrics": aggregate,
                           "author_da3_evaluation_view_participation": config["da3_evaluation_view_participation"]}]
        except (AssertionError, FileNotFoundError, KeyError, ValueError) as error:
            validation = [{"error": repr(error)}]
            code = 93
receipt = {"task_id": config["task_id"], "scientific_verdict": None, "phase": args.phase,
           "command": command, "official_commit": config["official_commit"],
           "runtime_image_id": config["runtime_image_id"],
           "ld_preload": os.environ.get("LD_PRELOAD"),
           "ld_library_path": os.environ.get("LD_LIBRARY_PATH"),
           "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
           "source_file_sha256": hashlib.sha256((Path("/source") / command[1]).read_bytes()).hexdigest(),
           "started_unix": started, "finished_unix": time.time(), "wall_seconds": time.time() - started,
           "child_max_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
           "gpu_memory_metric": "5-second nvidia-smi visible-device samples, not allocator peak",
           "native_exit_code": child.returncode, "validated_exit_code": code,
           "status": "PASS" if code == 0 else "FAIL", "validation": validation}
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
raise SystemExit(code)
