"""Additive SfM/no-anchor evaluation; unchanged sealed GeoGS scoring functions.

The original task is read-only. Only --out is written. Seal each exported snapshot
before attaching UAS to the geometry stage. No baseline score is recomputed.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

DEFAULT_PUBLIC_ROOT = "/task/evaluation/no_anchor_sfm_v1"
RUN_CONDITION = "SFM_noanchor_D005_Pnative"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def condition(iteration):
    return RUN_CONDITION + "_R" + str(iteration)


def public(args, path):
    return args.public_root.rstrip("/") + "/" + str(Path(path).relative_to(args.out))


def binding(args, seal_sha=None):
    return dict(experiment="no_anchor_sfm_v1", region=args.region,
                experiment_source_relative=str(args.experiment.relative_to(args.task)),
                execution_attempt_id=args.experiment.name,
                **getattr(args, "execution_metadata", {}),
                condition=condition(args.iteration), optimizer_updates=args.iteration,
                initialization="frozen_image_SfM_sparse", anchor_executed=False,
                prior_depth_coefficient=0.005, protection_policy="native",
                trajectory="snapshots_of_one_fresh_optimizer_30000_update_run",
                schedule="fresh_absolute_steps_1_to_N; not the original refinement steps_8001_to_30000",
                pure_anchor_only_ablation=False, independent_confirmatory=False,
                historical_sfm_evaluation_image_influence_removed=False,
                new_condition_seal_sha256=seal_sha, scientific_verdict=None,
                comparison_scope="DEVELOPMENT_DIAGNOSTIC_NOT_IMAGE_ONLY",
                budget_interpretation=("same refinement update count as original 8000+22000"
                    if args.iteration == 22000 else "same total update count as original 8000+22000"))


def seal_path(args):
    return args.out / "seals" / args.region / ("R" + str(args.iteration) + ".json")


def source_file(task, path):
    path = Path(path)
    relative = path.relative_to(task)
    if path.resolve() != task.resolve() / relative or not path.is_file():
        raise ValueError("Expected direct immutable task file: " + str(path))
    return dict(path=str(relative), bytes=path.stat().st_size, sha256=sha(path))


def check_file(task, row):
    actual = source_file(task, task / row["path"])
    if actual != row:
        raise ValueError("Sealed source changed: " + row["path"])


def prior_resource_attempts(task, rows, region, bind):
    """Bind an intentional replacement separately from the original CUDA OOM."""
    if not isinstance(rows, list):
        raise ValueError("Prior resource attempts must be an explicit list")
    result, seen = [], set()
    for row in rows:
        receipt_path, stop_path = (task / row[key]["path"] for key in ("receipt", "stop_intent"))
        if receipt_path in seen or receipt_path.parent != stop_path.parent:
            raise ValueError("Previous receipt/stop intent must bind one unique run directory")
        seen.add(receipt_path)
        bound_receipt, bound_stop = bind(receipt_path), bind(stop_path)
        if bound_receipt["sha256"] != row["receipt"]["sha256"] or bound_stop["sha256"] != row["stop_intent"]["sha256"]:
            raise ValueError("Prior resource attempt evidence bytes changed")
        receipt, stop = read_json(receipt_path), read_json(stop_path)
        if (receipt.get("status") != "FAIL" or receipt.get("native_exit_code") != -15
                or receipt.get("phase") != "train" or receipt.get("region") != region
                or receipt.get("condition_id") != RUN_CONDITION or receipt.get("scientific_verdict") is not None
                or stop.get("cause") != "RESOURCE_TRANSFER_OPTIMIZATION" or stop.get("region") != region
                or stop.get("scientific_verdict") is not None):
            raise ValueError("Prior attempt is not the declared intentional resource-transfer replacement")
        result.append(dict(receipt=bound_receipt, stop_intent=bound_stop,
            classification="INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT",
            cause="RESOURCE_TRANSFER_OPTIMIZATION", native_exit_code=-15,
            counted_as_cuda_oom=False, quality_assessed=False))
    return result


def prior_initialization_failure(task, row, region, bind):
    """Keep a declared scheduling failure separate from measured reconstruction quality."""
    if not isinstance(row, dict) or row.get("cause") != "RESOURCE_SCHEDULING_ERROR":
        raise ValueError("Initialization failure needs an explicit scheduling-cause record")
    receipt_path, log_path = (task / row[key]["path"] for key in ("receipt", "log"))
    if receipt_path.parent != log_path.parent or receipt_path.name != "receipt.json" or log_path.name != "native.log":
        raise ValueError("Initialization failure receipt/log must name one original run")
    receipt_record, log_record = bind(receipt_path), bind(log_path)
    if receipt_record["sha256"] != row["receipt"]["sha256"] or log_record["sha256"] != row["log"]["sha256"]:
        raise ValueError("Initialization failure evidence bytes changed")
    receipt = read_json(receipt_path)
    if (receipt.get("status") != "FAIL" or receipt.get("native_exit_code") != 1
            or receipt.get("phase") != "train" or receipt.get("region") != region
            or receipt.get("condition_id") != RUN_CONDITION or receipt.get("scientific_verdict") is not None
            or "CUDA error: out of memory" not in log_path.read_text()):
        raise ValueError("Initialization failure does not match its declared producer evidence")
    first_step = receipt_path.parent / "model/jbgs_no_anchor/first_step.json"
    if first_step.exists() or first_step.is_symlink():
        raise ValueError("Prior initialization failure already has a first-step record")
    return dict(receipt=receipt_record, log=log_record, cause="RESOURCE_SCHEDULING_ERROR",
        classification="CUDA_INITIALIZATION_FAILURE", native_exit_code=1,
        first_step_record_path=str(first_step.relative_to(task)), first_step_record_absent=True,
        cuda_oom_observed=True, counted_as_training_cuda_oom=False, quality_assessed=False)


def final_retry_metadata(task, experiment, region, amendment, bind):
    import importlib.util
    spec = importlib.util.spec_from_file_location("geogs_final_retry_binding", Path(__file__).with_name("final_retry.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.bind_retry(task, experiment, region, amendment, bind)


def recovery_metadata(args, training, producer, config_record, bind):
    fields = ("memory_recovery_amendment_path", "memory_recovery_amendment_sha256")
    if any(training.get(key) != producer.get(key) for key in fields):
        raise ValueError("Training/export memory recovery amendments differ")
    path, digest = (training.get(key) for key in fields)
    if bool(path) != bool(digest):
        raise ValueError("Both memory recovery amendment path and SHA are required")
    metadata = dict(resource_recovery_applied=bool(path))
    if not path:
        if args.experiment.name != "no_anchor_sfm_v1":
            raise ValueError("A separate execution attempt requires an explicit recovery amendment")
        return metadata
    amendment_record = bind(args.task / path)
    amendment = read_json(args.task / path)
    if (amendment_record["sha256"] != digest or amendment.get("scientific_verdict") is not None
            or amendment.get("arithmetic_or_scientific_controls_changed") is not False
            or amendment.get("original_config_sha256") != config_record["sha256"]
            or not amendment.get("memory_placement_changes")):
        raise ValueError("Memory recovery amendment identity or scientific controls differ")
    prior_record = amendment["original_failed_run_receipt"]
    prior_bound = bind(args.task / prior_record["path"])
    prior = read_json(args.task / prior_record["path"])
    if (prior_bound["sha256"] != prior_record["sha256"] or prior.get("status") != "FAIL"
            or prior.get("region") != args.region or prior.get("phase") != "train"
            or prior.get("condition_id") != RUN_CONDITION):
        raise ValueError("Memory recovery must retain the exact original failed training receipt")
    metadata.update(memory_recovery_amendment_path=path, memory_recovery_amendment_sha256=digest,
        original_failed_run_receipt=prior_bound, execution_deviations=amendment["memory_placement_changes"],
        arithmetic_or_scientific_controls_changed=False)
    if "prior_resource_attempts" in amendment:
        metadata["prior_resource_attempts"] = prior_resource_attempts(
            args.task, amendment["prior_resource_attempts"], args.region, bind)
    if "prior_initialization_failure" in amendment:
        metadata["prior_initialization_failure"] = prior_initialization_failure(
            args.task, amendment["prior_initialization_failure"], args.region, bind)
    if "final_resource_retry" in amendment or args.experiment.name.startswith("no_anchor_sfm_gradient_memory_v3_"):
        metadata["final_resource_retry"] = final_retry_metadata(args.task, args.experiment, args.region, amendment, bind)
    return metadata


def seal_stage(args):
    import numpy as np
    from PIL import Image
    cfg = read_json(args.task / "contracts/execution_v1.json")
    scene = args.task / "inputs" / args.region / "scene"
    split = read_json(scene / "split_manifest_da3_v2.json")
    expected = sorted(split["evaluation"], key=lambda row: row["name"])
    if len(expected) != cfg["regions"][args.region]["expected_test"]:
        raise ValueError("Frozen evaluation count differs")
    names = [row["name"] for row in expected]
    if len(set(names)) != len(names) or set(names) & {v["name"] for v in split["train"]}:
        raise ValueError("Evaluation/train membership invalid")
    run = args.experiment / "runs" / args.region / RUN_CONDITION
    export = run / "exports" / ("iteration_" + str(args.iteration))
    model = export / "model"
    files = {}

    def bind(path):
        row = source_file(args.task, path)
        files[row["path"]] = row
        return row

    for path in [args.task / "contracts/execution_v1.json",
                 args.task / "inputs" / args.region / "input_manifest.json",
                 scene / "split_manifest_da3_v2.json", scene / "jbgs_calibration.json",
                 scene / "scene_reference_frame.json"]:
        bind(path)
    # Bind frozen camera and source sparse bytes, without estimating or changing pose.
    sparse = sorted(scene.glob("sparse*/**/*"))
    for path in sparse:
        if path.is_file():
            bind(path)
    if not any(path.name in ("cameras.bin", "cameras.txt") for path in sparse):
        raise ValueError("Frozen camera calibration is missing")
    sfm_root = args.experiment / "inputs" / args.region
    sfm_path = sfm_root / "initialization_manifest.json"
    sfm = read_json(sfm_path)
    sfm_record = bind(sfm_path)
    if (sfm.get("status") != "SFM_INITIALIZATION_PREPARED" or sfm.get("region") != args.region
            or sfm.get("scientific_verdict") is not None or sfm.get("source_kind") != "image_sfm"
            or sfm.get("contains_als_points") is not False or sfm.get("reference_geometry_read") is not False
            or sfm.get("point_count", 0) <= 0):
        raise ValueError("Fresh SfM initialization provenance differs")
    for field, path in (("original_input_manifest", args.task / "inputs" / args.region / "input_manifest.json"),
                        ("original_split", scene / "split_manifest_da3_v2.json"),
                        ("base_config", args.task / "contracts/execution_v1.json")):
        if sfm[field]["sha256"] != sha(path):
            raise ValueError("SfM input changed the original comparison: " + field)
    sfm_ply = bind(sfm_root / sfm["points_ply_path"])
    if sfm_ply["sha256"] != sfm["points_ply_sha256"]:
        raise ValueError("SfM initialization PLY changed")
    for name in ("cameras.bin", "images.bin"):
        new_camera = bind(sfm_root / "scene/sparse/0" / name)
        if new_camera["sha256"] != sfm["camera_files"][name]["sha256"] or new_camera["sha256"] != sha(scene / "sparse/0" / name):
            raise ValueError("SfM initialization changed frozen camera or pose bytes")
    experiment_config_record = bind(run / "config_snapshot.json")
    experiment_cfg = read_json(run / "config_snapshot.json")
    if (experiment_cfg["condition_id"] != RUN_CONDITION or experiment_cfg["seed"] != cfg["seed"]
            or experiment_cfg["base_config_sha256"] != sha(args.task / "contracts/execution_v1.json")
            or experiment_cfg["extraction"]["mesh_res"] != 512):
        raise ValueError("Experiment contract differs")
    t = experiment_cfg["training"]
    required_controls = dict(iterations=30000, stage_switch_iter=0, lambda_lod_anchor=.005,
        position_lr_max_steps=30000, densify_until_iter=15000, lod_init=False,
        protect_bldg=True, freeze_onlybldg=True, enable_gaussian_completion=False)
    if any(t.get(key) != value for key, value in required_controls.items()):
        raise ValueError("No-anchor training controls differ")
    if bind(export / "config_snapshot.json")["sha256"] != experiment_config_record["sha256"]:
        raise ValueError("Export and training configurations differ")
    if bind(sfm_root / "experiment_config_snapshot.json")["sha256"] != experiment_config_record["sha256"]:
        raise ValueError("SfM preparation and training configurations differ")

    def completed_producer(path, phase, iteration):
        record = read_json(path)
        expected_fields = dict(status="PASS", native_exit_code=0, validated_exit_code=0,
            scientific_verdict=None, reference_accessed=False, region=args.region,
            condition_id=RUN_CONDITION, phase=phase, iteration=iteration,
            config_sha256=experiment_config_record["sha256"], sfm_manifest_sha256=sfm_record["sha256"],
            original_input_manifest_sha256=sfm["original_input_manifest"]["sha256"],
            runtime_image_id=experiment_cfg["runtime_image_id"])
        if any(key not in record or record[key] != value for key, value in expected_fields.items()):
            raise ValueError("Producer identity, execution or completion differs: " + str(path))
        bind(path)
        bind(path.parent / "invocation.json")
        bind(path.parent / "driver_snapshot.py")
        return record

    training = completed_producer(run / "receipt.json", "train", None)
    producer_path = args.producer_receipt or export / "receipt.json"
    if producer_path != export / "receipt.json":
        raise ValueError("Producer receipt must be the exact export receipt")
    producer_record = completed_producer(producer_path, "export", args.iteration)
    args.execution_metadata = recovery_metadata(args, training, producer_record, experiment_config_record, bind)
    command = producer_record["command"]
    for flag, value in (("--iteration", str(args.iteration)), ("--mesh_res", "512"),
                        ("--num_cluster", "50"), ("-s", "/sfm_input/scene")):
        if command.count(flag) != 1 or command[command.index(flag) + 1] != value:
            raise ValueError("Native extraction invocation differs: " + flag)
    from parse_extraction import parse_extraction_log
    extraction = parse_extraction_log(export / "native.log", 512, 50)
    bind(export / "native.log")
    declared_extraction = [row["realized_extraction"] for row in producer_record["validation"] if "realized_extraction" in row]
    if declared_extraction != [extraction]:
        raise ValueError("Realized TSDF controls differ from the export receipt")
    initialization_path = run / "model/jbgs_no_anchor/initialization.json"
    initialization = read_json(initialization_path)
    bind(initialization_path)
    initial_required = dict(status="PASS_PREOPTIMIZATION_PROTECTION", scientific_verdict=None,
        iteration=0, optimizer_steps=0, pretrained_model_or_optimizer_loaded=False,
        als_gaussians_inserted=0, protection_applied_before_first_step=True,
        lambda_lod_anchor=.005, training_entry_stage=2)
    if any(initialization.get(key) != value for key, value in initial_required.items()):
        raise ValueError("Pre-optimization protection audit differs")
    first_path = run / "model/jbgs_no_anchor/first_step.json"
    first = read_json(first_path)
    bind(first_path)
    if (first.get("status") != "PASS_FIRST_STEP_DIRECT_REFINEMENT" or first.get("anchor_iterations_executed") != 0
            or first.get("pretrained_optimizer_loaded") is not False or first.get("stage2_active") is not True):
        raise ValueError("First-step direct refinement audit differs")
    snapshot = bind(run / "model/jbgs_complete" / ("iteration_" + str(args.iteration)) / "point_cloud.ply")
    rendered_ply = bind(model / "point_cloud" / ("iteration_" + str(args.iteration)) / "point_cloud.ply")
    if snapshot["sha256"] != rendered_ply["sha256"]:
        raise ValueError("Renderer did not consume the complete snapshot")
    captured_path = run / "model/jbgs_complete" / ("iteration_" + str(args.iteration)) / "receipt.json"
    captured = read_json(captured_path)
    bind(captured_path)
    if (captured["ply_sha256"] != snapshot["sha256"] or captured["iteration"] != args.iteration
            or captured["scientific_verdict"] is not None):
        raise ValueError("Snapshot does not match complete-state receipt")
    training_snapshot = [row for row in training["outputs"] if row["path"] == str((args.task / snapshot["path"]).relative_to(run))]
    if len(training_snapshot) != 1 or training_snapshot[0]["sha256"] != snapshot["sha256"]:
        raise ValueError("Snapshot is not a validated training output")
    if bind(model / "cfg_args")["sha256"] != bind(run / "model/cfg_args")["sha256"]:
        raise ValueError("Renderer model configuration differs from training")
    source_meshes = {}
    for kind, filename in (("raw", "fuse.ply"), ("post", "fuse_post.ply")):
        source_meshes[kind] = bind(model / "train" / ("ours_" + str(args.iteration)) / filename)
        declared = [row for row in producer_record["outputs"] if row["path"] == str(
            (args.task / source_meshes[kind]["path"]).relative_to(export))]
        if len(declared) != 1 or any(declared[0][key] != source_meshes[kind][key] for key in ("sha256", "bytes")):
            raise ValueError("Mesh differs from validated export output")
    render_dir = model / "test" / ("ours_" + str(args.iteration))
    if len(list((render_dir / "renders").glob("*.png"))) != len(expected):
        raise ValueError("Native evaluation render count differs")
    records = []
    for index, view in enumerate(expected):
        photo = scene / "images" / view["name"]
        photo_record = bind(photo)
        if photo_record["sha256"] != view["sha256"]:
            raise ValueError("Frozen evaluation photo differs")
        png = render_dir / "renders" / ("%05d.png" % index)
        gt = render_dir / "gt" / ("%05d.png" % index)
        rendered, exported_gt = bind(png), bind(gt)
        with Image.open(png) as image:
            if image.size != (view["width"], view["height"]) or image.mode not in ("RGB", "RGBA"):
                raise ValueError("Native render dimensions/mode differ")
        with Image.open(photo) as image:
            original = np.asarray(image.convert("RGB"), dtype=np.uint8)
        expected_gt = ((original.astype(np.float32) / 255.0) * 255.0).astype(np.uint8)
        with Image.open(gt) as image:
            actual_gt = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if not np.array_equal(expected_gt, actual_gt):
            raise ValueError("Native GT pixels do not establish camera order")
        records.append(dict(name=view["name"], evaluation_index=index,
            image_id=view["image_id"], camera_id=view["camera_id"],
            render_path=rendered["path"], render_sha256=rendered["sha256"],
            exported_gt_sha256=exported_gt["sha256"],
            exported_gt_matches_original_pixels=True,
            pose_binding="frozen calibration; native ordered export and exact GT pixels"))
    # The exporter owns schedule/protection/mesh-res execution verification.
    write_json(seal_path(args), dict(schema="GEOGS_SFM_NO_ANCHOR_CANDIDATES_v1",
        status="SNAPSHOT_AND_RENDER_BYTES_SEALED", **binding(args),
        source_task_config_sha256=sha(args.task / "contracts/execution_v1.json"),
        mesh_res=512, mesh_res_verification="exact export invocation and reparsed native TSDF log",
        realized_extraction=extraction, sfm_initialization=sfm_record,
        initial_protected_gaussians=initialization["protected_gaussians"],
        initial_protected_fraction=initialization["protected_fraction"],
        source_meshes=source_meshes, snapshot=snapshot, rendered_ply=rendered_ply,
        render_records=records, producer_receipts=[source_file(args.task, producer_path)], files=list(files.values()),
        reference_accessed=False, script_sha256=sha(__file__),
        created_unix=time.time()))


def load_seal(args):
    path = seal_path(args)
    value = read_json(path)
    if value["status"] != "SNAPSHOT_AND_RENDER_BYTES_SEALED" or value["region"] != args.region:
        raise ValueError("Wrong snapshot seal")
    if value["optimizer_updates"] != args.iteration or value["scientific_verdict"] is not None:
        raise ValueError("Wrong snapshot identity")
    expected_source = str(args.experiment.relative_to(args.task))
    if value.get("experiment_source_relative", "no_anchor_sfm_v1") != expected_source:
        raise ValueError("Evaluation requested a different execution attempt than the sealed snapshot")
    if args.experiment.name.startswith("no_anchor_sfm_gradient_memory_v3_") and "final_resource_retry" not in value:
        raise ValueError("Final retry snapshot lacks its finite policy and predecessor binding")
    args.execution_metadata = {key: value[key] for key in (
        "resource_recovery_applied", "memory_recovery_amendment_path", "memory_recovery_amendment_sha256",
        "original_failed_run_receipt", "prior_resource_attempts", "prior_initialization_failure", "final_resource_retry",
        "execution_deviations", "arithmetic_or_scientific_controls_changed") if key in value}
    if "prior_initialization_failure" in value:
        verified = prior_initialization_failure(args.task, value["prior_initialization_failure"],
            args.region, lambda source: source_file(args.task, source))
        if verified != value["prior_initialization_failure"]:
            raise ValueError("Sealed initialization failure provenance changed")
    if "final_resource_retry" in value:
        verified = final_retry_metadata(args.task, args.experiment, args.region,
            read_json(args.task / value["memory_recovery_amendment_path"]), lambda source: source_file(args.task, source))
        if verified != value["final_resource_retry"]:
            raise ValueError("Sealed final resource-retry policy or predecessor changed")
    for row in value["files"]:
        check_file(args.task, row)
    return value, sha(path)


def geometry_stage(args, *, binding=binding, condition=condition, load_seal=load_seal,
                   comparison_family="sfm_no_anchor_final512"):
    import numpy as np
    import open3d as o3d
    from geometry import evaluate_geometry, save_distance_arrays
    from run_evaluation import (REFERENCE_SHAS, export_display, section_figure,
                                distance_figure, distance_table_fields, far_surface_area_fields,
                                column_diagnostics)
    from display_export import export_clipped_mesh, original_mesh_provenance, display_candidate_state
    seal, seal_digest = load_seal(args)
    cfg = read_json(args.task / "contracts/execution_v1.json")
    ev, bounds = cfg["evaluation"], cfg["regions"][args.region]["domain"]
    reference_path = args.reference_root / args.region / "reference.npz"
    if sha(reference_path) != REFERENCE_SHAS[args.region]:
        raise ValueError("Frozen UAS identity differs")
    reference = np.load(reference_path, allow_pickle=False)["uas_xyz"]
    settings = [(ev["surface_sample_spacing_m"], ev["reference_voxel_m"])]
    settings += [(s, ev["reference_voxel_m"]) for s in ev["sample_sensitivity_m"]]
    settings += [(ev["surface_sample_spacing_m"], v) for v in ev["reference_voxel_sensitivity_m"]]
    settings = list(dict.fromkeys(settings))
    rows, candidates = [], []
    for kind in ("raw", "post"):
        identifier = condition(args.iteration) + ".mesh_512." + kind
        output = args.out / "geometry" / args.region / identifier
        output.mkdir(parents=True, exist_ok=False)
        source = args.task / seal["source_meshes"][kind]["path"]
        mesh = o3d.io.read_triangle_mesh(str(source))
        started = time.time()
        for index, (spacing, voxel) in enumerate(settings):
            key = "sample%g_reference%g" % (spacing, voxel)
            metrics, arrays = evaluate_geometry(np.asarray(mesh.vertices), np.asarray(mesh.triangles),
                reference, bounds, spacing, voxel, cfg["seed"], ev["thresholds_m"],
                xy_cell_size=ev["xy_cell_m"])
            metrics.update(**binding(args, seal_digest), candidate=identifier, iteration=args.iteration,
                mesh_res=512, mesh_kind=kind, surface_kind="triangle_surface",
                source_sha256=sha(source), reference_sha256=REFERENCE_SHAS[args.region],
                crs=cfg["crs"], comparison_family=comparison_family)
            for threshold in metrics["thresholds"]:
                threshold.update(far_surface_area_fields(metrics, threshold))
                rows.append(dict(**binding(args, seal_digest), candidate=identifier, mesh_res=512,
                    iteration=args.iteration, mesh_kind=kind, surface_kind="triangle_surface",
                    comparison_family=comparison_family, sensitivity=key,
                    status=metrics["status"], **threshold, **distance_table_fields(metrics),
                    surface_area_m2=metrics["surface_area_m2"]))
            save_distance_arrays(output / (key + ".npz"), arrays)
            write_json(output / (key + ".json"), metrics)
            if index == 0:
                write_csv(output / "height_columns.csv", column_diagnostics(arrays["prediction_surface_samples"]))
                display_dir = args.out / "viewer" / args.region
                display_dir.mkdir(parents=True, exist_ok=True)
                cloud_path = display_dir / (identifier + ".json")
                color = [198, 97, 65] if args.iteration == 22000 else [153, 91, 199]
                display = export_display(cloud_path, arrays, color, "triangle_surface", str(source), mesh, metrics)
                original = original_mesh_provenance(args.task, source, seal["files"], "changed")
                descriptor_path = display_dir / (identifier + ".mesh.json")
                descriptor = export_clipped_mesh(descriptor_path, arrays, metrics["bounds_half_open"],
                    original, color, args.out, metrics)
                # New descriptors use absolute task URLs so profile relocation cannot break binaries.
                descriptor_value = read_json(descriptor_path)
                for field in ("vertices_f64", "triangles_u32"):
                    descriptor_value[field]["url"] = args.public_root.rstrip("/") + "/" + descriptor_value[field]["url"]
                descriptor_path.write_text(json.dumps(descriptor_value, indent=2, allow_nan=False) + "\n")
                descriptor.update(url=public(args, descriptor_path), sha256=sha(descriptor_path),
                                  bytes=descriptor_path.stat().st_size)
                section_path = display_dir / (identifier + ".sections.png")
                distance_path = display_dir / (identifier + ".distance.png")
                section_figure(section_path, arrays, arrays["reference_points"], bounds, args.region, identifier)
                distance_figure(distance_path, arrays, bounds, identifier)
                state, reason = display_candidate_state(metrics, display)
                candidates.append(dict(id=identifier, label=identifier, status=state, reason=reason,
                    role="changed", evaluation_status=metrics["status"], surface_kind="triangle_surface",
                    data=dict(url=public(args, cloud_path), format="json"), mesh_data=descriptor,
                    display_metadata=display, provenance=dict(source_path=str(source),
                        source_mesh=original, no_anchor=dict(**binding(args, seal_digest),
                            initial_protected_gaussians=seal["initial_protected_gaussians"],
                            initial_protected_fraction=seal["initial_protected_fraction"])),
                    downloads=[dict(label="Metric JSON", url=public(args, output / (key + ".json"))),
                               dict(label="Official raw/post PLY", url="/task/" + original["path"])],
                    section_url=public(args, section_path), distance_url=public(args, distance_path),
                    metrics_url=public(args, output / (key + ".json"))))
        write_json(output / "run_receipt.json", dict(status="EVALUATED", **binding(args, seal_digest),
            candidate=identifier, wall_seconds=time.time()-started, script_sha256=sha(__file__)))
    root = args.out / "geometry" / args.region
    write_csv(root / ("R%d_metrics.csv" % args.iteration), rows)
    write_json(root / ("R%d_viewer_index.json" % args.iteration), dict(
        status="GEOMETRY_EVALUATED", **binding(args, seal_digest), candidates=candidates,
        source_modules={name: sha(args.evaluation_lib / name)
            for name in ("geometry.py", "run_evaluation.py", "display_export.py")}))


def renders_stage(args, *, binding=binding, condition=condition, load_seal=load_seal):
    from render_quality import NativeMetrics, evaluate_render_set
    seal, seal_digest = load_seal(args)
    cfg = read_json(args.task / "contracts/execution_v1.json")
    scene = args.task / "inputs" / args.region / "scene"
    split = read_json(scene / "split_manifest_da3_v2.json")
    records = [dict(row, render_path=str(args.task / row["render_path"])) for row in seal["render_records"]]
    scorer = NativeMetrics(args.official_source, args.weights, device=args.device, signed_lpips=True)
    output = args.out / "renders" / args.region / condition(args.iteration) / "refinement_only"
    result = evaluate_render_set(split, records, cfg["regions"][args.region]["domain"],
        scene / "images", scorer, output, args.region, condition(args.iteration),
        "refinement_only", cfg["seed"], seal_digest)
    write_json(output / "no_anchor_provenance.json", dict(status=result["status"],
        **binding(args, seal_digest), native_metric_receipt_sha256=sha(output / "receipt.json"),
        script_sha256=sha(__file__)))
    print(json.dumps(dict(status=result["status"], **binding(args, seal_digest))))


def summary_stage(args):
    from summarize import optical_summary
    seal, seal_digest = load_seal(args)
    prefix = args.out / "summary" / args.region / ("R" + str(args.iteration))
    prefix.mkdir(parents=True, exist_ok=False)
    new_geometry = list(csv.DictReader((args.out / "geometry" / args.region /
        ("R%d_metrics.csv" % args.iteration)).open()))
    old_geometry_path = args.task / "evaluation/summary/geometry_anchor_refinement_512.csv"
    baseline_ids = {c + ".mesh_512." + k for c in ("D005_Pnative", "D0005_Pnative") for k in ("raw", "post")}
    baseline_ids |= {"D005_Pnative.anchor_512." + k for k in ("raw", "post")}
    old_geometry = [r for r in csv.DictReader(old_geometry_path.open()) if r["region"] == args.region and
        r["candidate"] in baseline_ids]
    if {r["candidate"] for r in old_geometry} != baseline_ids or any(r["mesh_res"] != "512" for r in old_geometry):
        raise ValueError("Existing Anchor/native/depth-relaxed 512 metrics are incomplete")
    if ({r["candidate"] for r in new_geometry} != {condition(args.iteration) + ".mesh_512." + k for k in ("raw", "post")}
            or any(r["new_condition_seal_sha256"] != seal_digest or r["mesh_res"] != "512" for r in new_geometry)):
        raise ValueError("New geometry table identity or completeness differs")
    render_root = args.out / "renders" / args.region / condition(args.iteration) / "refinement_only"
    render_receipt = read_json(render_root / "receipt.json")
    if render_receipt["sealed_render_manifest_sha256"] != seal_digest:
        raise ValueError("RGB seal differs")
    new_render_rows = render_receipt["rows"]
    if (render_receipt["region"] != args.region or render_receipt["condition"] != condition(args.iteration)
            or render_receipt["stage"] != "refinement_only" or len(new_render_rows) != 2 * len(seal["render_records"])):
        raise ValueError("New RGB receipt identity or count differs")
    new_render_summary = []
    for domain in ("full_frame", "fixed_prism_projected_bbox"):
        selected = [r for r in new_render_rows if r["domain"] == domain]
        new_render_summary.append(optical_summary(selected, **binding(args, seal_digest),
            stage="refinement_only", domain=domain,
            aggregation="REGIONAL_UNWEIGHTED_PER_IMAGE_MEAN"))
    old_render_path = args.task / "evaluation/summary/render_summary.csv"
    old_render = [r for r in csv.DictReader(old_render_path.open()) if r["region"] == args.region and
        r["condition"] in ("D005_Pnative", "D0005_Pnative") and r["stage"] == "final"]
    if {(r["condition"], r["domain"]) for r in old_render} != {
            (c, d) for c in ("D005_Pnative", "D0005_Pnative") for d in ("full_frame", "fixed_prism_projected_bbox")}:
        raise ValueError("Existing RGB comparison rows are incomplete")
    write_csv(prefix / "geometry_comparison.csv", old_geometry + new_geometry)
    write_csv(prefix / "render_comparison.csv", old_render + new_render_summary)
    write_csv(prefix / "new_render_per_image.csv", new_render_rows)
    write_json(prefix / "receipt.json", dict(status="NEW_CONDITION_COMPARISON_READY",
        **binding(args, seal_digest), baseline_metrics_recomputed=False,
        baseline_inputs=[source_file(args.task, old_geometry_path), source_file(args.task, old_render_path)],
        new_geometry_rows=len(new_geometry), reused_geometry_rows=len(old_geometry),
        new_render_images=len(new_render_rows), script_sha256=sha(__file__)))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--public-root", default=DEFAULT_PUBLIC_ROOT)
    parser.add_argument("--region", choices=("P1", "P2", "P3"), required=True)
    parser.add_argument("--iteration", type=int, choices=(22000, 30000), required=True)
    parser.add_argument("--stage", choices=("seal", "geometry", "renders", "summary"), required=True)
    parser.add_argument("--producer-receipt", type=Path)
    parser.add_argument("--reference-root", type=Path, default=Path("/reference"))
    parser.add_argument("--official-source", type=Path, default=Path("/source"))
    parser.add_argument("--weights", type=Path, default=Path("/weights"))
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--evaluation-lib", type=Path, default=Path(__file__).resolve().parent.parent / "evaluation")
    args = parser.parse_args()
    if not args.public_root.startswith("/task/") or ".." in Path(args.public_root).parts:
        raise ValueError("Public output root must be an absolute task URL")
    if args.experiment.resolve().is_relative_to(args.out.resolve()):
        raise ValueError("Immutable experiment source may not be inside writable output")
    args.experiment.relative_to(args.task)
    sys.path.insert(0, str(args.evaluation_lib))
    sys.path.insert(0, str(args.evaluation_lib.parent))
    try:
        globals()[args.stage + "_stage"](args)
    except Exception as exc:
        failure = args.out / "failures" / ("%s_R%d_%s_%d.json" %
            (args.region, args.iteration, args.stage, time.time_ns()))
        write_json(failure, dict(status="FAIL", **binding(args), stage=args.stage,
            error=repr(exc), script_sha256=sha(__file__)))
        raise


if __name__ == "__main__":
    main()
