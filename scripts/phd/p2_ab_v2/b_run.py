"""Isolated v2 experiment driver; no legacy payload is writable."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback
import cv2
import numpy as np
import torch
from src.phd.p2_ab_v2.reconstruction import (
    StructuredGaussians, View, prepare_geometry, render_view, crop_view,
    fitting_loss, appearance_geometry_metrics, extract_surface, subdivide_seed,
)
from scripts.phd.p2_ab_v2.sample_depth_mapping import read_colmap_array, sample_depth_rays, depth_intrinsics


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): h.update(block)
    return h.hexdigest()


def load_views(common, cfg):
    result = []
    for row in json.loads((common / "views.json").read_text())["views"]:
        if row["role"] not in {"train", "appearance_eval"}: continue
        image_path = Path(row["path"])
        if sha(image_path) != row["sha256"]: raise ValueError(f"Image hash mismatch {image_path}")
        rgb = cv2.cvtColor(cv2.imread(str(image_path)), cv2.COLOR_BGR2RGB)
        valid = cv2.imread(row["valid_mask_path"], cv2.IMREAD_GRAYSCALE)
        if valid is None or valid.shape != rgb.shape[:2]: raise ValueError("invalid undistortion support mask")
        H, W = rgb.shape[:2]
        factor = min(1., cfg["maximum_view_dimension_px"] / max(H, W))
        width, height = int(round(W * factor)), int(round(H * factor))
        if factor < 1:
            rgb = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
            valid = cv2.resize(valid, (width, height), interpolation=cv2.INTER_NEAREST)
        K = np.asarray(row["K"], np.float32).copy()
        K[0] *= width / W; K[1] *= height / H
        depth_info=row["geometric_depth"]
        if sha(depth_info["path"]) != depth_info["sha256"]:raise ValueError("COLMAP context depth hash mismatch")
        low_depth=read_colmap_array(Path(depth_info["path"]))
        low_K=depth_intrinsics(row)
        yy,xx=np.mgrid[:height,:width]
        mapping=sample_depth_rays(row,np.stack((xx+.5,yy+.5),axis=-1),current_K=K,depth=low_depth)
        # All four neighboring map depths must be known and in front. The max
        # footprint envelope avoids treating a mixed foreground boundary as sure.
        mapped=mapping["footprint_max_z"].astype(np.float32)
        V = np.eye(4, dtype=np.float32)
        V[:3, :3], V[:3, 3] = row["R"], row["t"]
        provenance = dict(image_id=row["image_id"], role="train" if row["role"] == "train" else "eval",
                          original_crop_shape_hw=[H, W], resized_shape_hw=[height, width],
                          resize_factor_xy=[width / W, height / H], native_focal_crop=True,
                          image_path=str(image_path), image_sha256=row["sha256"], valid_mask_sha256=sha(row["valid_mask_path"]),
                          K=K.tolist(), viewmat=V.tolist(), width=width, height=height)
        provenance["context_depth"]={"path":depth_info["path"],"sha256":depth_info["sha256"],
            "shape_hw":list(low_depth.shape),"K":low_K.tolist(),"role":"conditional foreground exclusion only; unknown retained; not depth fitting target",
            "foreground_gap_m":cfg["foreground_exclusion_gap_m"],"sampling":"all_four_known footprint_max_z; no dilation into unknown"}
        result.append(View(row["image_id"], provenance["role"],
            torch.tensor(rgb, device="cuda", dtype=torch.float32) / 255,
            torch.tensor(valid > 0, device="cuda"), torch.tensor(K, device="cuda"),
            torch.tensor(V, device="cuda"), width, height, provenance))
        result[-1].context_depth=torch.tensor(mapped,device="cuda")
    return result


@torch.no_grad()
def initialize_texture_and_support(model, views):
    samples = []
    observation_counts = np.zeros(len(model.base), np.int32)
    for view in views:
        out = render_view(model, view)
        validity=readout_validity(out)
        view.rgb_source_mask=view.valid&(out["alpha"]>=.5)
        view.source_mask = view.valid & (out["geometry_mass"] >= .5)
        known = view.context_depth > 0
        foreground=known & (view.context_depth + model.cfg["foreground_exclusion_gap_m"] < out["depth"])
        view.foreground=foreground & view.source_mask
        view.mask = view.source_mask & ~view.foreground
        view.provenance["conditional_observation_mask"]={"source_support_pixels":int(view.source_mask.sum()),
            "geometry_readout_validity":validity,
            "support_contract":"independent plane geometry_mass>=.5; RGB alpha remains separate",
            "rgb_source_support_pixels":int(view.rgb_source_mask.sum()),
            "rgb_source_without_geometry_pixels":int((view.rgb_source_mask&~view.source_mask).sum()),
            "foreground_excluded_pixels":int(view.foreground.sum()),"retained_observation_pixels":int(view.mask.sum()),
            "unknown_context_depth_source_pixels":int((view.source_mask & ~known).sum()),
            "known_context_depth_source_pixels":int((view.source_mask & known).sum()),
            "unknown_policy":"retain RGB evidence as conditional visibility; do not reject prior from missing MVS depth"}
        view.initial_depth = out["depth"].detach()
        if view.role != "train": continue
        camera = model.base @ view.viewmat[:3, :3].T + view.viewmat[:3, 3]
        projection = camera @ view.K.T
        uv = projection[:, :2] / projection[:, 2:].clamp_min(.01)
        x, y = uv[:, 0].long(), uv[:, 1].long()
        inside = (camera[:, 2] > 0) & (x >= 0) & (y >= 0) & (x < view.width) & (y < view.height)
        xx, yy = x.clamp(0, view.width-1), y.clamp(0, view.height-1)
        # Self-surface visibility is explicitly conditional on the source G0.
        visible = inside & view.valid[yy, xx] & ~view.foreground[yy,xx] & (out["geometry_mass"][yy, xx] >= .3)
        visible &= (out["depth"][yy, xx] - camera[:, 2]).abs() < torch.maximum(model.scale * 2, torch.full_like(model.scale, .15))
        array = np.full((len(model.base), 3), np.nan, np.float32)
        good = visible.cpu().numpy()
        array[good] = view.image[yy[visible], xx[visible]].cpu().numpy()
        observation_counts += good.astype(np.int32)
        samples.append(array)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        rgb = np.nanmedian(np.stack(samples), axis=0)
    rgb[~np.isfinite(rgb).all(1)] = .5
    model.sh0.copy_(torch.tensor((rgb - .5) / .28209479177387814, device="cuda")[:, None])
    model.set_observations(observation_counts)
    return {"visibility_kind": "G0_independent_plane_depth_and_geometry_mass; conditional source occlusion, not independent current usability",
            "color_initialization": "median RGB of visible training projections; missing=.5",
            "zero_observation_count": int((observation_counts == 0).sum()),
            "fewer_than_minimum_detail_views": int((observation_counts < model.cfg["minimum_detail_views"]).sum()),
            "observation_count_quantiles": np.quantile(observation_counts, [0,.1,.5,.9,1]).tolist()}


def readout_validity(out):
    for key in ["rgb","alpha","geometry_mass","depth","normal_render"]:
        if not bool(torch.isfinite(out[key]).all()):raise FloatingPointError(f"nonfinite renderer output: {key}")
    mass=out["geometry_mass"];depth=out["depth"]
    if not bool(((mass>=0)&(mass<=1.000001)).all()):raise ValueError("geometry mass outside [0,1]")
    if not bool((depth[mass==0]==0).all()):raise ValueError("missing geometry has nonzero placeholder depth")
    support=mass>=.5
    if bool(support.any()) and not bool((depth[support]>0).all()):raise ValueError("nonpositive supported geometry depth")
    return dict(finite=True,geometry_support_pixels=int(support.sum()),rgb_support_pixels=int((out["alpha"]>=.5).sum()),
        rgb_without_geometry_pixels=int(((out["alpha"]>=.5)&~support).sum()),
        mass_minmax=[float(mass.min()),float(mass.max())],
        supported_depth_quantiles_m=torch.quantile(depth[support],torch.tensor([0.,.1,.5,.9,1.],device=depth.device)).cpu().tolist() if bool(support.any()) else None,
        cancelled_normal_on_geometry_support_pixels=int((support&(out["normal_render"].norm(dim=-1)<1e-5)).sum()),
        normal_frame="world / scene-local axes; weighted sum, normalize only when nonzero")


def save_frame(destination, phase, view, out):
    paths = {"geometry_readout_validity":readout_validity(out)}
    rgb = np.round(out["rgb"].detach().clamp(0,1).cpu().numpy() * 255).astype(np.uint8)
    name = f"{phase}_rgb_{view.image_id}.png"
    cv2.imwrite(str(destination/name), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)); paths["rgb"] = name
    for key in ["depth", "alpha", "geometry_mass", "normal_render"]:
        name = f"{phase}_{key}_{view.image_id}.npy"
        np.save(destination/name, out[key].detach().cpu().numpy().astype(np.float32)); paths[key] = name
    name = f"target_{view.image_id}.png"
    target = np.round(view.image.cpu().numpy()*255).astype(np.uint8)
    cv2.imwrite(str(destination/name), cv2.cvtColor(target, cv2.COLOR_RGB2BGR)); paths["target"] = name
    name = f"valid_{view.image_id}.png"
    cv2.imwrite(str(destination/name), view.valid.cpu().numpy().astype(np.uint8)*255); paths["valid"] = name
    name = f"initial_support_{view.image_id}.png"
    cv2.imwrite(str(destination/name), view.source_mask.cpu().numpy().astype(np.uint8)*255); paths["initial_support"] = name
    for label,array in [("observation_support",view.mask),("foreground_excluded",view.foreground),
                        ("context_depth_unknown",view.context_depth<=0),("rgb_source_support",view.rgb_source_mask)]:
        name=f"{label}_{view.image_id}.png";cv2.imwrite(str(destination/name),array.cpu().numpy().astype(np.uint8)*255);paths[label]=name
    return paths


@torch.no_grad()
def save_evaluation(model, seed, views, destination, phase, cfg, initial=None):
    surfaces, rows, frames = [], [], []
    for view in views:
        out = render_view(model, view)
        frames.append({"image_id": view.image_id, **save_frame(destination, phase, view, out)})
        surfaces.append(extract_surface(out, view, seed, cfg["surface_pixel_stride"]))
        if initial is None:
            before = out
        else:
            before = {key: torch.tensor(np.load(destination/f"initial_{key}_{view.image_id}.npy"), device="cuda")
                      for key in ["depth", "alpha", "geometry_mass", "normal_render"]}
        rows.append(appearance_geometry_metrics(before, out, view))
    name = "initial_extracted_surface.npz" if phase == "initial" else "extracted_surface.npz"
    np.savez_compressed(destination/name, **{k: np.concatenate([s[k] for s in surfaces]) for k in surfaces[0]})
    return rows, frames


def train_arm(model, views, evaluate, arm, cfg, destination):
    geometry = arm != "geometry_fixed"
    color = arm != "color_fixed"
    structured = arm in {"structured_detail", "color_fixed"}
    groups = []
    names = {"structure": cfg["lr_structure"], "detail": cfg["lr_detail"], "rotation": cfg["lr_rotation"],
             "log_scales": cfg["lr_scale"], "opacity_raw": cfg["lr_opacity"], "sh0": cfg["lr_color"]}
    for name, value in model.named_parameters():
        value.requires_grad_(color if name == "sh0" else geometry)
        if value.requires_grad: groups.append({"params": [value], "lr": names[name], "name": name, "base_lr": names[name]})
    optimizer = torch.optim.Adam(groups, eps=1e-15)
    random = np.random.default_rng(cfg["seed"])
    centers = [torch.nonzero(v.mask, as_tuple=False).cpu().numpy() for v in views]
    unavailable=[views[i].image_id for i,c in enumerate(centers) if len(c)<64]
    cameras = np.array([(-v.viewmat[:3,:3].T @ v.viewmat[:3,3]).cpu().numpy() for v in views])
    neighbors = np.argsort(np.linalg.norm(cameras[:,None]-cameras[None,:], axis=-1), axis=1)[:,1:5]
    start = time.monotonic()
    history = destination / "training.jsonl"
    for step in range(cfg["steps"]):
        i = step % len(views)
        if len(centers[i])<64:
            row=dict(step=step+1,image_id=views[i].image_id,skipped_observation=True,
                skip_reason="fewer_than64_conditional_geometry_support_pixels",train_mask_pixels=len(centers[i]),
                loss=0.,photo=0.,coverage=0.,normal=0.,prior=0.,multiview=0.,gradients={},projection={},
                elapsed_seconds=time.monotonic()-start)
            with history.open("a") as stream:stream.write(json.dumps(row)+"\n")
            continue
        yc, xc = centers[i][random.integers(len(centers[i]))]
        view = crop_view(views[i], [xc,yc], cfg["training_tile_dimension_px"])
        lr_factor = max(.1, 1 - step / cfg["steps"] * .9)
        for group in optimizer.param_groups:
            warm = min(1., (step+1)/cfg["geometry_lr_ramp_steps"]) if group["name"] != "sh0" else 1
            group["lr"] = group["base_lr"] * lr_factor * warm
        reference = None
        if geometry and step % cfg["multiview_every"] == 0:
            j = int(neighbors[i, (step // len(views)) % len(neighbors[i])])
            vref = views[j]
            with torch.no_grad():
                pixel = torch.tensor([xc+.5,yc+.5,1.], device="cuda", dtype=torch.float32)
                world = (torch.linalg.inv(views[i].K) @ pixel * views[i].initial_depth[yc,xc] - views[i].viewmat[:3,3]) @ views[i].viewmat[:3,:3]
                camera = vref.viewmat[:3,:3] @ world + vref.viewmat[:3,3]
                uv = vref.K @ camera; uv = (uv[:2]/uv[2]).cpu().numpy()
                ref_view = crop_view(vref, uv, cfg["training_tile_dimension_px"])
                reference = (ref_view, render_view(model, ref_view))
        optimizer.zero_grad(set_to_none=True)
        out = render_view(model, view)
        loss, row = fitting_loss(model, view, out, cfg, geometry, arm.startswith("soft_prior"), reference)
        if not torch.isfinite(loss): raise FloatingPointError(f"nonfinite loss at {arm}:{step}")
        loss.backward()
        gradients = {}
        for group in optimizer.param_groups:
            p = group["params"][0]
            if p.grad is None: raise RuntimeError(f"Missing gradient for {group['name']}")
            if not bool(torch.isfinite(p.grad).all()): raise FloatingPointError(f"nonfinite gradient: {group['name']}")
            gradients[group["name"]] = float(p.grad.detach().norm())
        torch.nn.utils.clip_grad_norm_([g["params"][0] for g in optimizer.param_groups], cfg["gradient_norm_clip"])
        optimizer.step()
        projection = model.enforce_domain(structured) if geometry else {}
        if not geometry:
            # Same decoded SH0 domain as every geometry-active comparison arm.
            with torch.no_grad():model.sh0.clamp_(-.5/.28209479177387814,.5/.28209479177387814)
        row.update(step=step+1, image_id=view.image_id, elapsed_seconds=time.monotonic()-start,
                   gradients=gradients, projection=projection, learning_rate_factor=lr_factor,
                   tile_xywh=view.provenance["tile_xywh"])
        if (step+1) % cfg["log_every"] == 0 or step == 0:
            row["dof"] = model.dof_metrics()
            print(arm, json.dumps(row), flush=True)
        if (step+1) % cfg["evaluation_every"] == 0 or step == 0:
            with torch.no_grad():
                checks=[]
                for v in evaluate[::max(1,len(evaluate)//3)]:
                    now=render_view(model,v)
                    has_support=bool(v.mask.any())
                    mae=float((now["rgb"].clamp(0,1)-v.image).abs()[v.mask].mean()) if has_support else None
                    checks.append(dict(image_id=v.image_id, conditional_observation_support_mae=mae,
                        initial_support_pixels=int(v.mask.sum()), retained_initial_fraction=float((now["geometry_mass"][v.mask]>=.5).float().mean()) if has_support else None))
                row["evaluation_development_trend"] = checks
                np.savez_compressed(destination/f"gaussians_step_{step+1:05d}.npz", **model.state_arrays({k: np.arange(len(model.base)) for k in ["seed_id","native_row","unit_index","native_patch_id"]})) if cfg.get("intermediate_state",False) else None
        with history.open("a") as stream: stream.write(json.dumps(row,allow_nan=False)+"\n")
    return {"runtime_seconds": time.monotonic()-start, "steps":cfg["steps"],
            "unavailable_training_views":unavailable,
            "actual_optimizer_steps":sum(step%len(views) not in [i for i,c in enumerate(centers) if len(c)<64] for step in range(cfg["steps"])),
            "parameter_groups": names, "trainable_groups":[g["name"] for g in optimizer.param_groups],
            "dof":model.dof_metrics(), "convergence_claim":None}


def main(config_path):
    cfg = json.loads(Path(config_path).read_text())
    inherited = cfg.get("extends")
    if inherited:
        cfg = {**json.loads(Path(inherited).read_text()), **cfg}
    output = Path("/output")
    if any(output.iterdir()): raise ValueError("new empty output required")
    write_json(output/"STARTED.json", {"time_utc":datetime.now(timezone.utc).isoformat(),"scientific_verdict":None})
    start=time.monotonic()
    try:
        cv2.setNumThreads(1); torch.set_num_threads(2); torch.manual_seed(cfg["seed"])
        common=Path(cfg["common_root"])
        inputs={str(p):sha(p) for p in [Path(config_path),common/"sample_manifest.json",common/"views.json",common/"native_geometry.npz"]}
        if inherited: inputs[inherited]=sha(inherited)
        write_json(output/"config.json",cfg)
        sourcepaths=[Path(__file__), Path("src/phd/p2_ab_v2/reconstruction.py"),Path("scripts/phd/p2_ab_v2/b_run_corrected_docker.sh"),Path("scripts/phd/p2_ab_v2/b_prepare_geometry_adapter.py"),Path("scripts/phd/p2_ab_v2/b_adapter_audit.py"),Path("scripts/phd/p2_ab_v2/sample_depth_mapping.py"),Path("src/stage2/renderer.py"),Path("src/stage2/model.py"),Path("src/stage2/loss/data_fitting.py")]
        sourcehash={}
        for path in sourcepaths:
            dest=output/"source_snapshot"/str(path).lstrip("/")
            dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,dest);sourcehash[str(path)]=sha(path)
        overlay_manifest_path=Path(cfg["geometry_adapter_root"])/"adapter_manifest.json"
        overlay_manifest=json.loads(overlay_manifest_path.read_text())
        overlay_expected=overlay_manifest["output_hashes"]
        audit_path=Path(cfg["geometry_adapter_audit"])
        audit=json.loads(audit_path.read_text())
        if audit["status"]!="PASS" or not all(audit["checks"].values()):raise ValueError("geometry adapter audit did not pass")
        audit_receipt=dict(path=str(audit_path),sha256=sha(audit_path),adapter_manifest_path=str(overlay_manifest_path),
            adapter_manifest_sha256=sha(overlay_manifest_path),cuda_source_hashes=overlay_expected)
        write_json(output/"geometry_adapter_audit_receipt.json",audit_receipt)
        shutil.copy2(audit_path,output/"geometry_adapter_audit.json")
        shutil.copy2(overlay_manifest_path,output/"geometry_adapter_manifest.json")
        for filename,expected in overlay_expected.items():
            path=Path("/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc")/filename
            if sha(path)!=expected:raise ValueError("unexpected gsplat surface overlay bytes")
            if audit["source_hashes"].get(str(path))!=expected:raise ValueError("executed CUDA source differs from audited CUDA source")
            dest=output/"source_snapshot"/"gsplat"/filename;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest);sourcehash[str(path)]=expected
        write_json(output/"source_provenance.json",dict(source_hashes=sourcehash,input_hashes=inputs,
            overlay_contract=overlay_manifest["contract"],geometry_adapter_manifest_sha256=sha(overlay_manifest_path),
            geometry_contract="independent_plane_hit_v1",geometry_adapter_audit=audit_receipt,
            scientific_verdict=None))
        native=np.load(common/"native_geometry.npz",allow_pickle=False)
        views=load_views(common,cfg)
        (output/"context_depth").mkdir()
        for v in views:np.save(output/"context_depth"/f"{v.image_id}.npy",v.context_depth.cpu().numpy())
        train=[v for v in views if v.role=="train"]; evaluate=[v for v in views if v.role=="eval"]
        write_json(output/"views.json", {"views":[v.provenance for v in views]})
        summaries=[]
        for source in ["als","mvs"]:
            arms=[a for a in cfg["arms"] if (a=="image_only")== (source=="mvs")]
            if not arms:continue
            source_cfg=dict(cfg,seed_voxel_m=cfg["als_seed_voxel_m"] if source=="als" else cfg["mvs_seed_voxel_m"])
            source_xyz=native[f"{source}_xyz"].copy()
            if source=="als":source_xyz += np.asarray(cfg.get("source_shift_xyz_m",[0.,0.,0.]),np.float32)
            seed=prepare_geometry(source_xyz, native[f"{source}_normals"],native[f"{source}_patch_id"],
                 native[f"{source}_tile_rows"],native[f"{source}_unit_index"],source_cfg)
            if cfg.get("seed_subdivision",1)==4:seed=subdivide_seed(seed,source_cfg)
            elif cfg.get("seed_subdivision",1)!=1:raise ValueError("seed_subdivision must be1 or4")
            np.savez_compressed(output/f"{source}_source_seeds.npz",**seed)
            template=StructuredGaussians(seed,cfg)
            texture=initialize_texture_and_support(template,views)
            write_json(output/f"{source}_views.json",{"views":[v.provenance for v in views]})
            observed_per_group=np.bincount(seed["group"],weights=template.observable.cpu().numpy(),minlength=len(seed["group_counts"]))
            ranks=torch.linalg.matrix_rank(template.gram_pinv,rtol=1e-5).cpu().numpy()
            detail_dof=3*np.maximum(observed_per_group-ranks,0)
            write_json(output/f"{source}_detail_dof.json",dict(
                group_id=list(range(len(ranks))),observed_points=observed_per_group.astype(int).tolist(),
                affine_rank=ranks.tolist(),position_detail_dof=detail_dof.astype(int).tolist(),
                groups_with_zero_position_detail_dof=int((detail_dof==0).sum()),
                total_position_detail_dof=int(detail_dof.sum()),scientific_verdict=None))
            initial_state={k:v.detach().clone() for k,v in template.state_dict().items()}
            write_json(output/f"{source}_initialization.json",dict(source=source,seed_count=len(seed["xyz"]),
                original_input_count=int(seed["original_input_count"]), groups=int(seed["group"].max()+1),
                native_input_count=int(seed.get("native_input_count",seed["original_input_count"])),
                seed_subdivision=cfg.get("seed_subdivision",1),
                source_shift_xyz_m=cfg.get("source_shift_xyz_m",[0.,0.,0.]) if source=="als" else [0.,0.,0.],
                group_counts_quantiles=np.quantile(seed["group_counts"],[0,.1,.5,.9,1]).tolist(),
                scale_quantiles_m=np.quantile(seed["scale"],[0,.1,.5,.9,1]).tolist(), texture=texture,
                structure_reference="initial source local affine position and mean orientation", scientific_verdict=None))
            for arm in arms:
                print("ARM_START",arm,flush=True)
                dest=output/arm;dest.mkdir()
                model=StructuredGaussians(seed,cfg);model.load_state_dict(initial_state)
                np.savez_compressed(dest/"gaussians_initial.npz",**model.state_arrays(seed))
                initial_metrics,initial_frames=save_evaluation(model,seed,evaluate,dest,"initial",cfg)
                arm_cfg=dict(cfg)
                if arm.startswith("soft_prior"):
                    arm_cfg["soft_prior_weight"]=cfg["soft_prior_weights"][arm]
                fitted=train_arm(model,train,evaluate,arm,arm_cfg,dest)
                np.savez_compressed(dest/"gaussians_final.npz",**model.state_arrays(seed))
                torch.save(model.state_dict(),dest/"gaussians_final.pt")
                final_metrics,final_frames=save_evaluation(model,seed,evaluate,dest,"final",cfg,initial=True)
                result=dict(arm=arm,status="COMPLETED_DEVELOPMENT",source=source,initial_seed_count=len(seed["xyz"]),
                    conditional_source_use="ALS reuse assumed by predeclared B solver experiment; no A current-use authorization" if source=="als" else "image-derived MVS development baseline",
                    initialization_comparison="shared identical ALS G0 within each declared arm group; native has seven prior arms; image_only has different MVS G0",
                    fit=fitted,soft_prior_weight=arm_cfg["soft_prior_weight"] if arm.startswith("soft_prior") else 0,
                    initial_metrics=initial_metrics,final_metrics=final_metrics,
                    frames={"initial":initial_frames,"final":final_frames}, scientific_verdict=None)
                write_json(dest/"result.json",result);summaries.append(result)
                write_json(output/"progress.json",dict(completed_arms=[r["arm"] for r in summaries]))
                del model;torch.cuda.empty_cache()
            del template,initial_state
        write_json(output/"result.json",dict(status="COMPLETED_DEVELOPMENT",arms=summaries,input_hashes=inputs,
            source_hashes=sourcehash,configuration=cfg,runtime_seconds=time.monotonic()-start,
            versions=dict(torch=torch.__version__,cuda=torch.version.cuda,gsplat=__import__("gsplat").__version__,
              docker_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD")),
            surface_definition="independent C8 plane-alpha/T expected ray-surfel depth_sum/geometry_mass; C4 RGB alpha is separate; centerZ sort and tile support retained",
            geometry_adapter_contract=overlay_manifest["contract"],geometry_adapter_hashes=overlay_expected,
            geometry_contract="independent_plane_hit_v1",geometry_adapter_audit=audit_receipt,
            geometry_presence_contract="geometry_mass>=.5 with finitepositive depth; RGB alpha alone never supplies a surface",
            crs="EPSG:25832",coordinates="scene-local metres; exact shift and input transforms in common frame_audit.json",
            scientific_verdict=None))
    except Exception as exc:
        write_json(output/"FAILED.json",dict(error=repr(exc),traceback=traceback.format_exc(),scientific_verdict=None))
        raise


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--config",required=True)
    main(parser.parse_args().config)
