"""Conditional fixed-8000 diagnostic; strict main-run evaluation is unchanged."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys
import time

POLICY_PATH = "contracts/sfm_prefix8000_diagnostic_v1.json"
POLICY_SHA = "a312c4999ff590d757116dc0f4a90695020e3ac70130df24fdf6e02a0eb769f0"
ROLE = "SUPPLEMENTARY_PREFIX_DIAGNOSTIC"
PUBLIC_ROOT = "/task/evaluation/no_anchor_sfm_prefix8000_v1"
CONDITION = "SFM_noanchor_D005_Pnative_PREFIX8000"


def core(args):
    if not hasattr(args, "_core"):
        spec = importlib.util.spec_from_file_location("prefix_scoring_core", args.core_evaluator)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args._core = module
    return args._core


def condition(iteration):
    if iteration != 8000:
        raise ValueError("Only the fixed 8000 prefix is authorized")
    return CONDITION


def policy(args):
    c = core(args)
    path = args.task / POLICY_PATH
    value = c.read_json(path)
    if (c.sha(path) != POLICY_SHA or value.get("schema") != "GEOGS_SFM_PREFIX_DIAGNOSTIC_POLICY_v1"
            or value.get("scientific_verdict") is not None or value.get("prefix_iteration") != 8000
            or value.get("analysis_role") != ROLE or value.get("main_experiment_replaced") is not False):
        raise ValueError("Frozen conditional prefix policy differs")
    if args.experiment != args.task / value["selected_attempts"][args.region]:
        raise ValueError("Prefix attempt selection differs from the fixed regional policy")
    if args.public_root != "/task/" + value["evaluation_root"]:
        raise ValueError("Prefix public outputs must be isolated from main results")
    if not args.out.samefile(args.task / value["evaluation_root"]):
        raise ValueError("Writable output mount is not the policy's separate prefix evaluation root")
    return value


def binding(args, seal_sha=None):
    return dict(experiment="no_anchor_sfm_prefix8000_v1", region=args.region,
        condition=CONDITION, optimizer_updates=8000,
        planned_total_updates=30000, analysis_role=ROLE, main_experiment_replaced=False,
        experiment_source_relative=str(args.experiment.relative_to(args.task)),
        execution_attempt_id=args.experiment.name, **getattr(args, "execution_metadata", {}),
        initialization="frozen_image_SfM_sparse", anchor_executed=False,
        prior_depth_coefficient=.005, protection_policy="native",
        trajectory="fixed_8000_prefix_of_original_30000_schedule",
        budget_interpretation="8000 updates; primary comparator ALS Anchor8000; final30000 context only",
        pure_anchor_only_ablation=False, independent_confirmatory=False,
        historical_sfm_evaluation_image_influence_removed=False,
        comparison_scope="CONDITIONAL_SUPPLEMENTARY_PREFIX_NOT_IMAGE_ONLY",
        new_condition_seal_sha256=seal_sha, policy_sha256=POLICY_SHA,
        scientific_verdict=None)


def validate_proof(args, bind):
    """Accept a separately validated prefix, never reinterpret a parent FAIL as PASS."""
    c = core(args)
    contract = policy(args)
    root = args.task / contract["producer_root"] / args.region
    path = root / "validation/receipt.json"
    proof = c.read_json(path)
    required = dict(schema="GEOGS_SFM_PREFIX_VALIDATION_v1", status="PREFIX_8000_VALIDATED", validation_pass=True,
        analysis_role=ROLE, iteration=8000, actual_optimizer_updates=8000,
        planned_total_updates=30000, scientific_verdict=None, region=args.region,
        policy_sha256=POLICY_SHA, reference_accessed=False, establishes_22000_or_30000_completion=False,
        selected_experiment=str(args.experiment.relative_to(args.task)))
    if any(key not in proof or proof[key] != value for key, value in required.items()):
        raise ValueError("Dedicated 8000-prefix validation did not pass")
    bound = bind(path)
    if not proof.get("files"):
        raise ValueError("Prefix validator supplied no bound source files")
    for row in proof["files"]:
        if bind(args.task / row["path"]) != row:
            raise ValueError("Prefix validation source changed: " + row["path"])
    for key in ("parent_training_receipt", "snapshot_ply", "snapshot_checkpoint", "snapshot_capture_receipt", "activation_receipt"):
        if bind(args.task / proof[key]["path"]) != proof[key]:
            raise ValueError("Prefix proof record changed: " + key)
    activation = c.read_json(args.task / proof["activation_receipt"]["path"])
    if (activation.get("status") != "PREFIX_DIAGNOSTIC_ACTIVATED" or activation.get("all_selected_producer_jobs_closed") is not True
            or activation.get("selected_attempts") != contract["selected_attempts"] or activation.get("scientific_verdict") is not None
            or activation.get("quality_or_reference_selection") is not False or not activation.get("failure_evidence")):
        raise ValueError("The conditional diagnostic was not activated by closed producer failures")
    for record in activation["files"]:
        if bind(args.task / record["path"]) != record:
            raise ValueError("Conditional activation producer evidence changed")
    failures = 0
    for rid, selected in contract["selected_attempts"].items():
        selected_run = args.task / selected / "runs" / rid / c.RUN_CONDITION
        pending = [(selected_run / "receipt.json", "train", None)]
        while pending:
            receipt_path, phase, iteration = pending.pop(0)
            value = c.read_json(receipt_path)
            if (value.get("status") not in ("PASS", "FAIL") or value.get("region") != rid or value.get("phase") != phase
                    or value.get("iteration") != iteration or value.get("condition_id") != c.RUN_CONDITION
                    or value.get("scientific_verdict") is not None or type(value.get("native_exit_code")) is not int
                    or type(value.get("validated_exit_code")) is not int or not isinstance(value.get("finished_unix"), (int,float))
                    or value["finished_unix"] < value.get("started_unix", float("inf"))
                    or (value["status"] == "PASS") != (value["native_exit_code"] == 0 and value["validated_exit_code"] == 0)):
                raise ValueError("Every selected producer must have a valid closed receipt")
            bind(receipt_path)
            failures += value["status"] == "FAIL"
            if phase == "train" and value["status"] == "PASS":
                pending += [(selected_run / "exports" / ("iteration_"+str(n)) / "receipt.json", "export", n) for n in (22000,30000)]
    if not failures:
        raise ValueError("No selected planned training or export failure activates the 8k diagnostic")
    parent_path = args.experiment / "runs" / args.region / c.RUN_CONDITION / "receipt.json"
    if proof["parent_training_receipt"]["path"] != str(parent_path.relative_to(args.task)):
        raise ValueError("Prefix parent receipt names a different run")
    parent = c.read_json(parent_path)
    if (parent.get("status") not in ("PASS", "FAIL") or parent.get("status") != proof["parent_training_status"]
            or parent.get("phase") != "train" or parent.get("region") != args.region
            or parent.get("condition_id") != c.RUN_CONDITION or parent.get("scientific_verdict") is not None):
        raise ValueError("Closed parent training status must remain explicit")
    capture = c.read_json(args.task / proof["snapshot_capture_receipt"]["path"])
    if (capture.get("schema") != "JBGS_GEOGS_COMPLETE_STATE_v1" or capture.get("iteration") != 8000
            or capture.get("after_protection_registration") is not True or capture.get("scientific_verdict") is not None
            or capture.get("ply_sha256") != proof["snapshot_ply"]["sha256"]
            or capture.get("checkpoint_sha256") != proof["snapshot_checkpoint"]["sha256"]):
        raise ValueError("Complete-state hashes or post-step snapshot identity differ")
    return contract, root, proof, bound, parent


def seal_stage(args):
    import numpy as np
    from PIL import Image
    from parse_extraction import parse_extraction_log
    c = core(args)
    files = {}
    def bind(path):
        row = c.source_file(args.task, path)
        files[row["path"]] = row
        return row
    contract, root, proof, proof_record, parent = validate_proof(args, bind)
    bind(args.task / POLICY_PATH)
    run = args.experiment / "runs" / args.region / c.RUN_CONDITION
    export = root / "export"
    producer = c.read_json(export / "receipt.json")
    configuration = bind(run / "config_snapshot.json")
    cfg = c.read_json(args.task / "contracts/execution_v1.json")
    sfm_root = args.experiment / "inputs" / args.region
    sfm = c.read_json(sfm_root / "initialization_manifest.json")
    sfm_record = bind(sfm_root / "initialization_manifest.json")
    expected_producer = dict(status="PASS", phase="export", iteration=8000,
        native_exit_code=0, validated_exit_code=0, scientific_verdict=None,
        reference_accessed=False, region=args.region, condition_id=c.RUN_CONDITION,
        config_sha256=configuration["sha256"], sfm_manifest_sha256=sfm_record["sha256"],
        original_input_manifest_sha256=sfm["original_input_manifest"]["sha256"],
        runtime_image_id=parent["runtime_image_id"])
    if any(key not in producer or producer[key] != value for key, value in expected_producer.items()):
        raise ValueError("Official prefix export did not pass its exact identity and completion checks")
    if producer.get("prefix_validation_receipt") != proof_record or producer.get("source_sha256") != parent["source_sha256"]:
        raise ValueError("Export prefix proof or actual source differs")
    if bind(export / "config_snapshot.json")["sha256"] != configuration["sha256"]:
        raise ValueError("Prefix export changed the training configuration")
    bind(export / "receipt.json")
    bind(export / "invocation.json")
    args.execution_metadata = c.recovery_metadata(args, parent, producer, configuration, bind)
    args.execution_metadata.update(prefix_validation_receipt=proof_record,
        parent_training_receipt=proof["parent_training_receipt"], parent_training_status=parent["status"],
        parent_training_native_exit_code=parent["native_exit_code"],
        prefix_snapshot_available=True, full_experiment_completion_inferred=False)
    command = producer["command"]
    for flag, value in (("--iteration", "8000"), ("--mesh_res", "512"), ("--num_cluster", "50"), ("-s", "/sfm_input/scene")):
        if command.count(flag) != 1 or command[command.index(flag) + 1] != value:
            raise ValueError("Official prefix extraction command differs: " + flag)
    extraction = parse_extraction_log(export / "native.log", 512, 50)
    if [r["realized_extraction"] for r in producer["validation"] if "realized_extraction" in r] != [extraction]:
        raise ValueError("Realized prefix TSDF settings differ")
    bind(export / "native.log")
    model = export / "model"
    rendered_snapshot = bind(model / "point_cloud/iteration_8000/point_cloud.ply")
    if rendered_snapshot["sha256"] != proof["snapshot_ply"]["sha256"]:
        raise ValueError("Renderer did not consume the exact validated 8000 snapshot")
    if bind(model / "cfg_args")["sha256"] != bind(run / "model/cfg_args")["sha256"]:
        raise ValueError("Renderer configuration differs from original training")
    initial = c.read_json(run / "model/jbgs_no_anchor/initialization.json")
    first = c.read_json(run / "model/jbgs_no_anchor/first_step.json")
    bind(run / "model/jbgs_no_anchor/initialization.json")
    bind(run / "model/jbgs_no_anchor/first_step.json")
    if (initial.get("status") != "PASS_PREOPTIMIZATION_PROTECTION"
            or first.get("status") != "PASS_FIRST_STEP_DIRECT_REFINEMENT"
            or first.get("anchor_iterations_executed") != 0):
        raise ValueError("Fresh-SfM first-step checks differ")
    def exported(path):
        actual = bind(path)
        declared = [r for r in producer["outputs"] if r["path"] == str(path.relative_to(export))]
        if len(declared) != 1 or any(declared[0][key] != actual[key] for key in ("sha256", "bytes")):
            raise ValueError("Native export output identity differs: " + str(path))
        return actual
    meshes = {kind: exported(model / "train/ours_8000" / name)
              for kind, name in (("raw", "fuse.ply"), ("post", "fuse_post.ply"))}
    scene = args.task / "inputs" / args.region / "scene"
    split = c.read_json(scene / "split_manifest_da3_v2.json")
    expected = sorted(split["evaluation"], key=lambda row: row["name"])
    if len(expected) != cfg["regions"][args.region]["expected_test"] or {r["name"] for r in expected} & {r["name"] for r in split["train"]}:
        raise ValueError("Frozen photo split differs")
    for path in (args.task / "contracts/execution_v1.json", scene / "split_manifest_da3_v2.json", scene / "jbgs_calibration.json", scene / "scene_reference_frame.json"):
        bind(path)
    render_dir = model / "test/ours_8000"
    if len(list((render_dir / "renders").glob("*.png"))) != len(expected):
        raise ValueError("Native evaluation photo count differs")
    rows = []
    for index, view in enumerate(expected):
        photo = scene / "images" / view["name"]
        if bind(photo)["sha256"] != view["sha256"]:
            raise ValueError("Frozen evaluation photograph changed")
        png = render_dir / "renders" / ("%05d.png" % index)
        gt = render_dir / "gt" / ("%05d.png" % index)
        rendered, exported_gt = exported(png), exported(gt)
        with Image.open(png) as image:
            if image.size != (view["width"], view["height"]) or image.mode not in ("RGB", "RGBA"):
                raise ValueError("Native render dimensions differ")
        with Image.open(photo) as image:
            original = np.asarray(image.convert("RGB"), dtype=np.uint8)
        with Image.open(gt) as image:
            if not np.array_equal(((original.astype(np.float32) / 255.) * 255.).astype(np.uint8), np.asarray(image.convert("RGB"), dtype=np.uint8)):
                raise ValueError("Native GT pixels do not establish frozen camera order")
        rows.append(dict(name=view["name"], evaluation_index=index, image_id=view["image_id"], camera_id=view["camera_id"],
            render_path=rendered["path"], render_sha256=rendered["sha256"], exported_gt_sha256=exported_gt["sha256"],
            exported_gt_matches_original_pixels=True, pose_binding="frozen camera and exact native GT pixels"))
    c.write_json(c.seal_path(args), dict(schema="GEOGS_SFM_PREFIX8000_SEAL_v1",
        status="PREFIX_SNAPSHOT_AND_RENDER_BYTES_SEALED", **binding(args),
        iteration=8000, mesh_res=512, realized_extraction=extraction, source_meshes=meshes,
        snapshot=proof["snapshot_ply"], rendered_ply=rendered_snapshot,
        initial_protected_gaussians=initial["protected_gaussians"], initial_protected_fraction=initial["protected_fraction"],
        render_records=rows, files=list(files.values()), reference_accessed=False,
        prefix_proof=proof_record, producer_receipts=[c.source_file(args.task, export / "receipt.json")],
        core_evaluator_sha256=c.sha(args.core_evaluator), script_sha256=c.sha(__file__), created_unix=time.time()))


def load_seal(args):
    c = core(args)
    policy(args)
    path = c.seal_path(args)
    value = c.read_json(path)
    if (value.get("status") != "PREFIX_SNAPSHOT_AND_RENDER_BYTES_SEALED" or value.get("analysis_role") != ROLE
            or value.get("optimizer_updates") != 8000 or value.get("planned_total_updates") != 30000
            or value.get("region") != args.region or value.get("scientific_verdict") is not None
            or value.get("experiment_source_relative") != str(args.experiment.relative_to(args.task))
            or value.get("core_evaluator_sha256") != c.sha(args.core_evaluator)):
        raise ValueError("Prefix seal identity, scope or scoring implementation differs")
    for row in value["files"]:
        c.check_file(args.task, row)
    args.execution_metadata = {key: value[key] for key in (
        "resource_recovery_applied", "memory_recovery_amendment_path", "memory_recovery_amendment_sha256",
        "original_failed_run_receipt", "prior_resource_attempts", "prior_initialization_failure", "execution_deviations",
        "arithmetic_or_scientific_controls_changed", "prefix_validation_receipt", "parent_training_receipt",
        "parent_training_status", "parent_training_native_exit_code", "prefix_snapshot_available", "full_experiment_completion_inferred") if key in value}
    if "prior_initialization_failure" in value:
        if c.prior_initialization_failure(args.task, value["prior_initialization_failure"], args.region,
                lambda source: c.source_file(args.task, source)) != value["prior_initialization_failure"]:
            raise ValueError("Original initialization failure evidence changed")
    return value, c.sha(path)


def summary_stage(args):
    from summarize import optical_summary
    c = core(args)
    seal, digest = load_seal(args)
    destination = args.out / "summary" / args.region / "R8000"
    destination.mkdir(parents=True, exist_ok=False)
    geometry_source = args.task / "evaluation/summary/geometry_anchor_refinement_512.csv"
    render_source = args.task / "evaluation/summary/render_summary.csv"
    wanted = {"D005_Pnative." + stage + "." + kind for stage in ("anchor_512", "mesh_512") for kind in ("raw", "post")}
    old = [dict(r, comparison_role="PRIMARY_EQUAL_UPDATES" if ".anchor_512." in r["candidate"] else "CONTEXT_DIFFERENT_30000_BUDGET")
           for r in csv.DictReader(geometry_source.open()) if r["region"] == args.region and r["candidate"] in wanted]
    new = list(csv.DictReader((args.out / "geometry" / args.region / "R8000_metrics.csv").open()))
    if {r["candidate"] for r in old} != wanted or any(r["mesh_res"] != "512" for r in old):
        raise ValueError("Required existing matched512 Anchor and final context rows are absent")
    if {r["candidate"] for r in new} != {CONDITION + ".mesh_512." + k for k in ("raw", "post")} or any(r["new_condition_seal_sha256"] != digest for r in new):
        raise ValueError("New prefix geometry rows differ")
    old_rgb = [dict(r, comparison_role="PRIMARY_EQUAL_UPDATES" if r["stage"] == "anchor_512" else "CONTEXT_DIFFERENT_30000_BUDGET")
        for r in csv.DictReader(render_source.open()) if r["region"] == args.region and r["condition"] == "D005_Pnative" and r["stage"] in ("anchor_512", "final")]
    if {(r["stage"], r["domain"]) for r in old_rgb} != {(s,d) for s in ("anchor_512", "final") for d in ("full_frame", "fixed_prism_projected_bbox")}:
        raise ValueError("Existing Anchor8000 RGB and final30000 context are incomplete")
    receipt = c.read_json(args.out / "renders" / args.region / CONDITION / "refinement_only/receipt.json")
    if receipt["sealed_render_manifest_sha256"] != digest or receipt["condition"] != CONDITION or receipt["region"] != args.region or len(receipt["rows"]) != 2*len(seal["render_records"]):
        raise ValueError("Prefix RGB identity or photo count differs")
    summaries = [optical_summary([r for r in receipt["rows"] if r["domain"] == domain], **binding(args, digest),
        stage="refinement_only", domain=domain, comparison_role="PRIMARY_EQUAL_UPDATES", aggregation="REGIONAL_UNWEIGHTED_PER_IMAGE_MEAN")
        for domain in ("full_frame", "fixed_prism_projected_bbox")]
    c.write_csv(destination / "geometry_comparison.csv", old + [dict(r, comparison_role="PRIMARY_EQUAL_UPDATES") for r in new])
    c.write_csv(destination / "render_comparison.csv", old_rgb + summaries)
    c.write_csv(destination / "new_render_per_image.csv", receipt["rows"])
    c.write_json(destination / "receipt.json", dict(status="PREFIX8000_COMPARISON_READY", **binding(args, digest),
        baseline_metrics_recomputed=False, baseline_inputs=[c.source_file(args.task,p) for p in (geometry_source,render_source)],
        scoring_core_sha256=c.sha(args.core_evaluator), scientific_scope="Fixed prefix only; no final convergence or main-run completion claim"))


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--task",type=Path,required=True)
    p.add_argument("--experiment",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--region",choices=("P1","P2","P3"),required=True)
    p.add_argument("--stage",choices=("seal","geometry","renders","summary"),required=True)
    p.add_argument("--public-root",default=PUBLIC_ROOT)
    p.add_argument("--reference-root",type=Path,default=Path("/reference"))
    p.add_argument("--official-source",type=Path,default=Path("/source"))
    p.add_argument("--weights",type=Path,default=Path("/weights"))
    p.add_argument("--device",choices=("cpu","cuda"),default="cpu")
    p.add_argument("--evaluation-lib",type=Path,required=True)
    p.add_argument("--core-evaluator",type=Path,default=Path(__file__).resolve().parents[1]/"evaluate.py")
    a=p.parse_args();a.iteration=8000
    sys.path.insert(0,str(a.evaluation_lib));sys.path.insert(0,str(a.evaluation_lib.parent))
    policy(a)
    try:
        if a.stage == "geometry":
            core(a).geometry_stage(a,binding=binding,condition=condition,load_seal=load_seal,comparison_family="sfm_no_anchor_prefix8000_512")
        elif a.stage == "renders":
            core(a).renders_stage(a,binding=binding,condition=condition,load_seal=load_seal)
        else:
            globals()[a.stage+"_stage"](a)
    except Exception as error:
        core(a).write_json(a.out/"failures"/(a.region+"_R8000_"+a.stage+"_"+str(time.time_ns())+".json"),dict(status="FAIL",**binding(a),stage=a.stage,error=repr(error)))
        raise


if __name__ == "__main__":
    main()
