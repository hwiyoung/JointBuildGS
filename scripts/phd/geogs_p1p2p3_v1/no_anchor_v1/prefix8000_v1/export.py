#!/usr/bin/env python3
"""Official 8k render/mesh export after independent conditional-prefix proof."""
import argparse
import importlib.util
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
import traceback

import common as c
from validate import identity


def verify_prefix_records(region, proof):
    c.require(proof.get("schema") == "GEOGS_SFM_PREFIX_VALIDATION_v1"
              and proof.get("status") == "PREFIX_8000_VALIDATED" and proof.get("validation_pass") is True
              and proof.get("region") == region and proof.get("scientific_verdict") is None
              and proof.get("selected_experiment") == c.SELECTED[region]
              and proof.get("iteration") == proof.get("actual_optimizer_updates") == 8000
              and proof.get("planned_total_updates") == 30000 and proof.get("analysis_role") == c.ROLE,
              "Independent 8k proof is absent or differs")
    roots = [(c.run_relative(region) + "/", Path("/trained")),
             (c.SELECTED[region] + "/inputs/" + region + "/", Path("/sfm_input")),
             (c.SELECTED[region] + "/source/", Path("/source")),
             (f"inputs/{region}/", Path("/input")),
             (f"completed_prefix8000_v1/{region}/validation/", Path("/validation")),
             ("completed_prefix8000_v1/activation/", Path("/activation"))]
    exact = {c.SELECTED[region] + "/config.json": Path("/config.json"),
             c.SELECTED[region] + "/amendment.json": Path("/amendment.json")}
    for item in proof["files"]:
        relative = c.relative(item["path"])
        path = exact.get(relative)
        if path is None:
            for prefix, root in roots:
                if relative.startswith(prefix):
                    path = root / relative[len(prefix):]
                    break
        c.require(path is not None and c.record(path, relative) == item, "Validated prefix file changed: " + relative)
    return proof


def check_outputs(output, iteration, base, region, *, split_path=Path("/input/scene/split_manifest_da3_v2.json"),
                  parser_path=Path("/audit/parse_extraction.py")):
    import numpy as np
    import open3d as o3d
    from PIL import Image
    spec = importlib.util.spec_from_file_location("prefix_parse_extraction", parser_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = [dict(realized_extraction=module.parse_extraction_log(output / "native.log", 512, 50))]
    outputs = []
    model = output / "model"
    for filename in ("fuse.ply", "fuse_post.ply"):
        file = model / "train" / f"ours_{iteration}" / filename
        mesh = o3d.io.read_triangle_mesh(str(file))
        vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
        c.require(len(vertices) > 0 and len(faces) > 0 and np.isfinite(vertices).all()
                  and faces.min() >= 0 and faces.max() < len(vertices)
                  and np.isfinite(mesh.get_surface_area()) and mesh.get_surface_area() > 0,
                  "Invalid official extracted surface: " + filename)
        checks.append(dict(file=filename, vertices=len(vertices), triangles=len(faces), area_m2=mesh.get_surface_area()))
        outputs.append(c.record(file, str(file.relative_to(output))))
        del mesh, vertices, faces
    split = c.read(split_path)
    for role, key, expected_key in (("train", "train", "expected_train"), ("test", "evaluation", "expected_test")):
        members = split[key]
        expected = base["regions"][region][expected_key]
        c.require(len(members) == expected, "Frozen camera split count differs")
        names = {f"{index:05d}.png" for index in range(expected)}
        allowed_dimensions = {(row["width"], row["height"]) for row in members}
        for category in ("renders", "gt"):
            directory = model / role / f"ours_{iteration}" / category
            files = list(directory.glob("*.png"))
            c.require({file.name for file in files} == names, "Official image membership differs: " + role + "/" + category)
            for file in sorted(files):
                with Image.open(file) as image:
                    image.load()
                    c.require(image.size in allowed_dimensions and image.mode in ("RGB", "RGBA"), "Invalid actual rendered/GT PNG")
                outputs.append(c.record(file, str(file.relative_to(output))))
        checks.append({"evaluation_render_count" if role == "test" else "training_render_count": expected,
                       "actual_png_decode_verified": True, "render_gt_index_membership_verified": True})
    return checks, outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=tuple(c.SELECTED), required=True)
    args = parser.parse_args()
    output = Path("/output")
    c.scope()
    c.require(output.is_dir() and not (output / "receipt.json").exists(), "Fresh export output required")
    started, timer = time.time(), time.monotonic()
    native_code, validated_code, invocation = None, 91, {}
    checks, outputs = [], []
    try:
        c.policy("/policy.json")
        c.verify_activation(Path("/activation/receipt.json"), Path("/parents"), Path("/policy.json"))
        expected = identity(args.region)
        c.require(os.environ.get("JBGS_RUNTIME_IMAGE_ID") == c.IMAGE
                  and os.environ.get("PYTORCH_CUDA_ALLOC_CONF") == expected["cfg"]["resources"]["allocator"], "Runtime image/allocator differs")
        proof = verify_prefix_records(args.region, c.read("/validation/receipt.json"))
        c.require(proof["source_sha256"] == c.method_source_map(expected["source_map"])
                  and proof["parent_training_status"] == expected["parent"]["status"], "Export source/parent differs from validation")
        model = output / "model"
        target = model / "point_cloud/iteration_8000"
        target.mkdir(parents=True, exist_ok=False)
        shutil.copyfile("/trained/model/jbgs_complete/iteration_8000/point_cloud.ply", target / "point_cloud.ply")
        c.require(c.sha(target / "point_cloud.ply") == proof["snapshot_ply"]["sha256"], "Export model copy differs")
        shutil.copyfile("/trained/model/cfg_args", model / "cfg_args")
        c.require(c.sha(model / "cfg_args") == proof["model_cfg_args"]["sha256"], "Export cfg_args copy differs")
        shutil.copyfile("/config.json", output / "config_snapshot.json")
        shutil.copyfile("/amendment.json", output / "memory_recovery_amendment_snapshot.json")
        command = [sys.executable, "render.py", "-s", "/sfm_input/scene", "-m", str(model),
                   "--iteration", "8000", "--mesh_res", "512", "--num_cluster", "50"]
        invocation = dict(task_id=expected["cfg"]["task_id"], scientific_verdict=None,
            region=args.region, condition_id=c.CONDITION, phase="export", iteration=8000,
            analysis_role=c.ROLE, actual_optimizer_updates=8000, planned_total_updates=30000,
            selected_experiment=c.SELECTED[args.region], parent_training_status=expected["parent"]["status"],
            parent_training_receipt=proof["parent_training_receipt"], parent_failure_status_preserved=True,
            prefix_validation_receipt=c.record(Path("/validation/receipt.json"),
                f"completed_prefix8000_v1/{args.region}/validation/receipt.json"),
            activation_receipt=proof["activation_receipt"], policy_sha256=c.POLICY_SHA,
            command=command, cwd="/source", config_sha256=c.sha("/config.json"),
            source_sha256=c.method_source_map(expected["source_map"]),
            producer_code_sha256=c.driver_hashes(), parser_sha256=c.sha("/audit/parse_extraction.py"),
            sfm_manifest_sha256=c.sha("/sfm_input/initialization_manifest.json"),
            original_input_manifest_sha256=c.sha("/input/input_manifest.json"),
            runtime_image_id=c.IMAGE, reference_accessed=False, started_unix=started,
            memory_recovery_amendment_sha256=c.sha("/amendment.json"),
            memory_recovery_amendment_path=c.SELECTED[args.region] + "/amendment.json",
            establishes_22000_or_30000_completion=False,
            measurement_scope="Official render.py child launch through raw/post mesh and actual PNG validation")
        c.write(output / "invocation.json", invocation)
        with (output / "native.log").open("x") as log, (output / "gpu.csv").open("x") as gpu:
            child = subprocess.Popen(command, cwd="/source", stdout=log, stderr=subprocess.STDOUT)
            while child.poll() is None:
                subprocess.run(["nvidia-smi", "--query-gpu=timestamp,uuid,memory.used,utilization.gpu",
                                "--format=csv,noheader,nounits"], stdout=gpu, stderr=subprocess.DEVNULL)
                gpu.flush()
                time.sleep(5)
            native_code = child.wait()
        validated_code = native_code
        if native_code == 0:
            checks, outputs = check_outputs(output, 8000, expected["base"], args.region)
    except Exception:
        validated_code = 91
        checks.append(dict(validation_error=traceback.format_exc()))
        with (output / "failure.log").open("x") as log:
            log.write(checks[-1]["validation_error"])
    c.write(output / "receipt.json", dict(invocation, schema="GEOGS_SFM_PREFIX_EXPORT_v1",
        status="PASS" if validated_code == 0 else "FAIL", scientific_verdict=None,
        phase="export", region=args.region, iteration=8000, analysis_role=c.ROLE,
        native_exit_code=native_code, validated_exit_code=validated_code,
        started_unix=started, finished_unix=time.time(), wall_seconds=time.monotonic() - timer,
        child_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
        validation=checks, outputs=outputs, reference_accessed=False))
    print({"region": args.region, "iteration": 8000, "status": "PASS" if validated_code == 0 else "FAIL"})
    return validated_code


if __name__ == "__main__":
    raise SystemExit(main())
