"""Fresh-SfM/no-anchor protection and first-step audit for a copied GeoGS runtime.

Copied into the prepared source as jbgs_no_anchor.py. It reuses native protection
functions, never adds prior points, and never restores a model or optimizer.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


SCHEMA = "jointbuildgs.geogs.no_anchor_initialization_audit.v1"
INITIALIZATION_SCHEMA = "jointbuildgs.geogs.sfm_initialization.v1"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def write_new(path: Path, payload: dict) -> None:
    with path.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)


def register_args(parser) -> None:
    parser.add_argument("--jbgs_sfm_initialization_manifest", required=True,
                        help="Manifest proving the nonempty image-SfM initialization")


def validate_args(args) -> None:
    if args.stage_switch_iter != 0:
        raise ValueError("This runtime requires stage_switch_iter=0")
    if args.start_checkpoint or args.jbgs_resume_full:
        raise ValueError("Fresh SfM requires no model/optimizer checkpoint restore")
    if args.lod_init or args.sparse_dir_name not in ("", "sparse"):
        raise ValueError("Fresh SfM must use the manifest-bound sparse/0 directory")
    if args.dynamic_stage_switch or args.enable_gaussian_completion or args.jbgs_release_protection:
        raise ValueError("Dynamic stage, Gaussian completion, and protection release are disabled")
    if not args.freeze_onlybldg or not args.protect_bldg:
        raise ValueError("Both native protection flags must be explicit")
    if args.lod2_building_xyz_lr_scale != 0.01 or args.protect_bldg_lr_scale != 0.01:
        raise ValueError("Native position/rotation/scale gradient factors must remain 0.01")
    if not args.lod2_pcd_path:
        raise ValueError("Native protection needs the frozen prior matching PLY")
    if args.iterations != 30000 or args.position_lr_max_steps != 30000:
        raise ValueError("One 30000-step trajectory supplies both 22000 and 30000 outputs")
    # Extra early checkpoints are allowed; these are the required observations.
    args.jbgs_capture_iterations = sorted(set(args.jbgs_capture_iterations) | {1, 22000, 30000})
    args.save_iterations = sorted(set(args.save_iterations) | {22000, 30000})


def verify_sfm_initialization(env) -> dict:
    import numpy as np
    import torch
    from plyfile import PlyData

    args, g = env["args"], env["gaussians"]
    manifest_path = Path(args.jbgs_sfm_initialization_manifest).resolve(strict=True)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != INITIALIZATION_SCHEMA:
        raise ValueError("Unrecognized SfM initialization manifest")
    if manifest.get("source_kind") != "image_sfm" or manifest.get("contains_als_points") is not False:
        raise ValueError("Initialization must contain image-SfM points and no ALS points")
    relative = Path(manifest["points_ply_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("SfM PLY path must be contained relative to its manifest")
    ply_path = (manifest_path.parent / relative).resolve(strict=True)
    scene_ply = (Path(args.source_path) / "sparse/0/points3D.ply").resolve(strict=True)
    if ply_path != scene_ply:
        raise ValueError("Training sparse PLY differs from the initialization manifest path")
    expected = manifest["points_ply_sha256"]
    if digest(ply_path) != expected or digest(Path(args.model_path) / "input.ply") != expected:
        raise ValueError("Source/loaded initialization PLY hash mismatch")
    vertices = PlyData.read(ply_path)["vertex"]
    xyz = np.stack([np.asarray(vertices[name]) for name in ("x", "y", "z")], axis=1).astype(np.float32)
    count = len(xyz)
    if count <= 0 or count != manifest["point_count"] or not np.isfinite(xyz).all():
        raise ValueError("SfM points must be nonempty, finite, and match the declared count")
    if len(g.get_xyz) != count or not torch.equal(g.get_xyz.detach().cpu(), torch.from_numpy(xyz)):
        raise ValueError("Initial Gaussian XYZ/order does not exactly equal SfM PLY float32 XYZ")
    if len(g.optimizer.state) != 0:
        raise ValueError("Expected a fresh optimizer with no pretrained moment state")
    if g.completed_mask is not None and bool(g.completed_mask.any()):
        raise ValueError("No prior completion Gaussians are allowed")
    return {
        "manifest": str(manifest_path), "manifest_sha256": digest(manifest_path),
        "source_kind": "image_sfm", "contains_als_points": False,
        "point_count": count, "points_ply": str(ply_path), "points_ply_sha256": expected,
        "source_points3D_sha256": manifest.get("source_points3D_sha256"),
        "region": manifest.get("region"),
        "gaussian_xyz_matches_sfm_float32_order": True,
        "fresh_optimizer_state_entries": 0,
    }


def initialize_protection(env, functions):
    import torch

    args, g, prior = env["args"], env["gaussians"], env["lod2_pcd"]
    audit_root = Path(args.model_path) / "jbgs_no_anchor"
    audit_root.mkdir(parents=False, exist_ok=False)
    try:
        validate_args(args)
        if env["first_iter"] != 0 or env["freeze_done"]:
            raise ValueError("Initialization must precede the first optimizer step")
        if prior is None or prior.numel() == 0:
            raise ValueError("Frozen prior matching point set is missing or empty")
        initial = verify_sfm_initialization(env)
        count_before = len(g.get_xyz)
        # The native switch block runs under no_grad: retain its bounded matching
        # memory and install gradient hooks without building a distance graph.
        with torch.no_grad():
            mask = functions["find_building_mask_from_pcd"](
                g, prior, args.lod2_match_thresh, chunk_size=args.lod2_match_chunk)
            if mask is None or mask.shape != (count_before,):
                raise ValueError("Native matching returned an invalid protection mask")
            functions["attenuate_building_xyz_lr"](g, mask, args.lod2_building_xyz_lr_scale)
            functions["attenuate_building_other_lr"](
                g, mask, args.protect_bldg_lr_scale, apply_rotation=True, apply_scaling=True)
            g.set_frozen_mask(mask)
        if len(g.get_xyz) != count_before or len(g.optimizer.state) != 0:
            raise RuntimeError("Native protection must not insert points or optimize")
        protected = int(mask.sum().item())
        initial.update(
            schema=SCHEMA, status="PASS_PREOPTIMIZATION_PROTECTION", scientific_verdict=None,
            iteration=0, optimizer_steps=0, pretrained_model_or_optimizer_loaded=False,
            als_gaussians_inserted=0, gaussian_count_before=count_before,
            gaussian_count_after=len(g.get_xyz), protection_applied_before_first_step=True,
            protected_gaussians=protected, protected_fraction=protected / count_before,
            protection_status="ACTIVE_INITIAL_MATCHES" if protected else "NO_SFM_POINTS_WITHIN_PRIOR_THRESHOLD",
            matching_only_prior_ply=str(Path(args.lod2_pcd_path)),
            matching_only_prior_sha256=digest(Path(args.lod2_pcd_path)),
            matching_distance_m=args.lod2_match_thresh,
            native_xyz_gradient_scale=args.lod2_building_xyz_lr_scale,
            native_rotation_scale_gradient_scale=args.protect_bldg_lr_scale,
            protection_semantics="original native helper applied to fresh SfM membership at step 0",
            lambda_lod_anchor=args.lambda_lod_anchor,
            training_entry_stage=2, normal_activates_after_iteration=7000,
            densify_until_iteration_exclusive=args.densify_until_iter,
            continued_resume_supported=False)
        write_new(audit_root / "initialization.json", initial)
        print(f"[JBGS no-anchor] BEFORE step1: SfM={count_before}, protected={protected}, "
              f"optimizer states=0, ALS Gaussians added=0; {initial['protection_status']}")
        return mask
    except Exception as error:
        write_new(audit_root / "failure.json", {
            "schema": SCHEMA, "status": "FAILED_BEFORE_FIRST_OPTIMIZER_STEP",
            "scientific_verdict": None, "error_type": type(error).__name__, "error": str(error)})
        raise


def capture_initial_state(env, functions) -> None:
    import torch

    root = Path(env["args"].model_path) / "jbgs_no_anchor" / "iteration_0"
    root.mkdir(exist_ok=False)
    try:
        snapshot_env = dict(env, iteration=0)
        state = functions["jbgs_state"].capture_state(snapshot_env)
        state["no_anchor_fresh_sfm"] = True
        state["scientific_verdict"] = None
        torch.save(state, root / "checkpoint.pth")
        env["gaussians"].save_ply(str(root / "point_cloud.ply"))
        write_new(root / "receipt.json", {
            "schema": SCHEMA, "status": "PASS_INITIAL_STATE_CAPTURED",
            "scientific_verdict": None, "iteration": 0, "optimizer_steps": 0,
            "after_initial_native_protection": True, "continued_resume_supported": False,
            "checkpoint_sha256": digest(root / "checkpoint.pth"),
            "ply_sha256": digest(root / "point_cloud.ply")})
    except Exception as error:
        write_new(root / "failure.json", {
            "schema": SCHEMA, "status": "FAILED_INITIAL_STATE_CAPTURE",
            "scientific_verdict": None, "optimizer_steps": 0,
            "error_type": type(error).__name__, "error": str(error)})
        raise


def audit_first_step(env) -> None:
    if env["iteration"] != 1:
        return
    g, args = env["gaussians"], env["args"]
    root = Path(args.model_path) / "jbgs_no_anchor"
    initial = json.loads((root / "initialization.json").read_text())
    try:
        if not env["stage2_active"] or env["just_switched"] or env["freeze_done"]:
            raise RuntimeError("Step1 did not run direct refinement with local protection")
        if env["current_lod_weight"] != args.lambda_lod_anchor:
            raise RuntimeError("Step1 used the anchor-stage LoD weight")
        if len(g.get_xyz) != initial["gaussian_count_after"]:
            raise RuntimeError("Unexpected Gaussian insertion/removal before first-step audit")
        protected = int(g.frozen_mask.sum().item()) if g.frozen_mask is not None else 0
        if protected != initial["protected_gaussians"]:
            raise RuntimeError("Step1 lost initial protection membership")
        loss = float(env["total_loss"].item())
        if not math.isfinite(loss) or len(g.optimizer.state) == 0:
            raise RuntimeError("First step has invalid loss or absent optimizer state")
        write_new(root / "first_step.json", {
            "schema": SCHEMA, "status": "PASS_FIRST_STEP_DIRECT_REFINEMENT",
            "scientific_verdict": None, "iteration": 1, "stage2_active": True,
            "anchor_iterations_executed": 0, "pretrained_optimizer_loaded": False,
            "als_gaussians_inserted": 0, "protected_gaussians": protected,
            "optimizer_state_entries": len(g.optimizer.state),
            "lod_weight": env["current_lod_weight"], "da_weight": env["current_da_weight"],
            "normal_weight": env["lambda_normal_default"], "total_loss": loss,
            "camera": env["cam_name"],
            "full_state_written_next_by": "jbgs_state.after_step:jbgs_complete/iteration_1"})
    except Exception as error:
        write_new(root / "first_step_failure.json", {
            "schema": SCHEMA, "status": "FAILED_FIRST_STEP_AUDIT",
            "scientific_verdict": None, "error_type": type(error).__name__, "error": str(error)})
        raise
