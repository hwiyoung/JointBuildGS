"""Reproduce unchanged native extraction and metrics on the native 8000 PLY."""
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


config_path = Path("/config/native_example_route_8000_v1.json")
config = json.loads(config_path.read_text())
output = Path("/output")
ply_relative = "point_cloud/iteration_8000/point_cloud.ply"
(output / "model" / ply_relative).parent.mkdir(parents=True, exist_ok=False)
for relative in ("cfg_args", ply_relative):
    shutil.copyfile(Path("/checkpoint") / relative, output / "model" / relative)
    assert sha(Path("/checkpoint") / relative) == sha(output / "model" / relative)
phases = []
for phase in ("render", "metrics"):
    command = config[phase + "_command"]
    started = time.time()
    with (output / (phase + ".log")).open("x") as log, (output / (phase + "_gpu.csv")).open("x") as gpu_log:
        child = subprocess.Popen(command, cwd="/source", stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            subprocess.run(["nvidia-smi", "--query-gpu=timestamp,uuid,memory.used,utilization.gpu",
                            "--format=csv,noheader,nounits"], stdout=gpu_log, stderr=subprocess.DEVNULL, check=False)
            gpu_log.flush()
            time.sleep(5)
        code = child.wait()
    phases.append({"phase": phase, "command": command, "native_exit_code": code,
                   "source_sha256": sha(Path("/source") / command[1]), "started_unix": started,
                   "wall_seconds": time.time() - started,
                   "child_max_rss_kib_cumulative": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss})

import numpy as np
import open3d as o3d
meshes = []
for name in ("fuse.ply", "fuse_post.ply"):
    path = output / "model/train/ours_8000" / name
    row = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        mesh = o3d.io.read_triangle_mesh(str(path))
        row.update(sha256=sha(path), vertices=len(mesh.vertices), triangles=len(mesh.triangles),
                   finite_vertices=bool(np.isfinite(np.asarray(mesh.vertices)).all()),
                   area=float(mesh.get_surface_area()))
    row["valid_surface"] = bool(row.get("triangles", 0) and row.get("finite_vertices") and row.get("area", 0) > 0)
    meshes.append(row)
metrics = {}
try:
    aggregate = json.loads((output / "model/results.json").read_text())["ours_8000"]
    per_view = json.loads((output / "model/per_view.json").read_text())["ours_8000"]
    assert all(math.isfinite(aggregate[key]) for key in ("PSNR", "SSIM", "LPIPS"))
    assert all(len(per_view[key]) == config["test_views"] for key in ("PSNR", "SSIM", "LPIPS"))
    metrics = {"valid": True, "aggregate": aggregate, "test_views": config["test_views"]}
except (AssertionError, FileNotFoundError, KeyError, ValueError) as error:
    metrics = {"valid": False, "error": repr(error)}
okay = all(row["native_exit_code"] == 0 for row in phases) and all(row["valid_surface"] for row in meshes) and metrics["valid"]
receipt = {"task_id": config["task_id"], "scientific_verdict": None, "config": config,
           "config_sha256": sha(config_path), "source_ply_sha256": sha(output / "model" / ply_relative),
           "ld_preload": os.environ.get("LD_PRELOAD"), "ld_library_path": os.environ.get("LD_LIBRARY_PATH"),
           "status": "PASS_NATIVE_8000_ROUTE" if okay else "FAIL_NATIVE_8000_ROUTE",
           "phases": phases, "meshes": meshes, "metrics": metrics}
with (output / "receipt.json").open("x") as stream:
    json.dump(receipt, stream, indent=2, allow_nan=False)
print(json.dumps(receipt, indent=2))
raise SystemExit(0 if okay else 2)
