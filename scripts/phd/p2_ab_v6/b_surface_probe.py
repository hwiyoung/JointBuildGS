"""Matched P2 normal-update ablations; A decision images never enter RGB fitting."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import time
import traceback
import cv2
import numpy as np
import torch
from src.phd.p2_ab_v6.surface_budget import SurfaceGaussians, Evidence, SurfaceGuard
from src.phd.p2_ab_v3.appearance_sh import render_view
from src.phd.p2_ab_v2.reconstruction import crop_view, extract_surface, appearance_geometry_metrics
from scripts.phd.p2_ab_v2.b_run import load_views, initialize_texture_and_support, readout_validity
from scripts.phd.p2_ab_v4.b_mvs_appearance_probe import sha, write, photo_loss, geometry_hash


@torch.no_grad()
def residual_mask(model, view, out):
    error=(out["rgb"].clamp(0,1)-view.image).abs().mean(-1)
    cam=model.means@view.viewmat[:3,:3].T+view.viewmat[:3,3]
    p=cam@view.K.T;uv=p[:,:2]/p[:,2:].clamp_min(.01)
    x,y=uv[:,0].long(),uv[:,1].long()
    inside=(cam[:,2]>0)&(x>=0)&(y>=0)&(x<view.width)&(y<view.height)
    x=x.clamp(0,view.width-1);y=y.clamp(0,view.height-1)
    threshold=error[view.mask].median()
    return inside & view.mask[y,x] & (error[y,x]>=threshold)


@torch.no_grad()
def mask_image(model,view,active):
    # Centre projections are explicitly a mask diagnostic, never a Gaussian RGB render.
    cam=model.means@view.viewmat[:3,:3].T+view.viewmat[:3,3];p=cam@view.K.T
    uv=p[:,:2]/p[:,2:].clamp_min(.01);x,y=uv[:,0].long(),uv[:,1].long()
    good=active&(cam[:,2]>0)&(x>=0)&(y>=0)&(x<view.width)&(y<view.height)
    canvas=np.zeros((view.height,view.width),np.uint8)
    canvas[y[good].cpu().numpy(),x[good].cpu().numpy()]=255
    return cv2.dilate(canvas,np.ones((3,3),np.uint8))


@torch.no_grad()
def evaluate(model,views,seed,dest,cfg,initial=None,active=None):
    dest.mkdir(exist_ok=True);rows=[];surfaces=[];renders={}
    absolute=squared=0.;pixels=0
    for view in views:
        out=render_view(model,view);readout_validity(out)
        cpu={k:out[k].detach().cpu().numpy().astype(np.float32) for k in ("depth","geometry_mass","alpha","normal_render")}
        rgb=np.round(out["rgb"].clamp(0,1).cpu().numpy()*255).astype(np.uint8)
        target=np.round(view.image.cpu().numpy()*255).astype(np.uint8)
        common=cv2.imread(str(Path(cfg["common_viewer"])/"images"/str(view.image_id)/"common_support.png"),0)
        if common is None or common.shape!=rgb.shape[:2]:raise ValueError("fixed common evaluation mask missing")
        mask=common>0;err=(rgb.astype(np.float64)-target.astype(np.float64))/255
        a=float(np.abs(err[mask]).sum());s=float(np.square(err[mask]).sum());n=int(mask.sum())
        absolute+=a;squared+=s;pixels+=n
        row=dict(image_id=view.image_id,pixels=n,mae=a/(3*n),psnr_db=float(-10*np.log10(max(s/(3*n),1e-15))))
        if initial is not None:
            old=initial[view.image_id]
            keep=mask&(old["geometry_mass"]>=.5)&(cpu["geometry_mass"]>=.5)
            delta=np.abs(cpu["depth"]-old["depth"])
            row.update(removed_pixels=int((mask&(old["geometry_mass"]>=.5)&(cpu["geometry_mass"]<.5)).sum()),
                added_pixels=int((mask&(old["geometry_mass"]<.5)&(cpu["geometry_mass"]>=.5)).sum()),
                retained_pixels=int(keep.sum()),depth_change_sum_m=float(delta[keep].sum()),
                depth_change_p90_m=float(np.quantile(delta[keep],.9)) if keep.any() else None)
            heat=np.minimum(delta/.3,1);heat[~keep]=0
            cv2.imwrite(str(dest/f"depth_change_{view.image_id}.png"),cv2.applyColorMap(np.round(heat*255).astype(np.uint8),cv2.COLORMAP_TURBO))
        cv2.imwrite(str(dest/f"rgb_{view.image_id}.png"),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(dest/f"target_{view.image_id}.png"),cv2.cvtColor(target,cv2.COLOR_RGB2BGR))
        normal=cpu["normal_render"];norm=np.linalg.norm(normal,axis=-1,keepdims=True)
        normal_rgb=np.round((normal/np.maximum(norm,1e-8)*.5+.5)*255).astype(np.uint8)
        normal_rgb[cpu["geometry_mass"]<.5]=0
        cv2.imwrite(str(dest/f"normal_{view.image_id}.png"),cv2.cvtColor(normal_rgb,cv2.COLOR_RGB2BGR))
        if active is not None:cv2.imwrite(str(dest/f"mask_{view.image_id}.png"),mask_image(model,view,active))
        for key,value in cpu.items():np.save(dest/f"{key}_{view.image_id}.npy",value)
        surfaces.append(extract_surface(out,view,seed,stride=2));rows.append(row);renders[view.image_id]=cpu
    np.savez_compressed(dest/"extracted_surface.npz",**{k:np.concatenate([s[k] for s in surfaces]) for k in surfaces[0]})
    summary=dict(pixels=pixels,mae=absolute/(3*pixels),psnr_db=float(-10*np.log10(squared/(3*pixels))),
        views=rows,absolute_rgb_sum=absolute,squared_rgb_sum=squared)
    write(dest/"appearance.json",summary)
    return summary,renders


def main(path):
    cfg=json.loads(Path(path).read_text());output=Path("/output")
    if any(output.iterdir()):raise ValueError("new empty output required")
    started=time.monotonic();write(output/"STARTED.json",dict(scientific_verdict=None))
    try:
        torch.set_num_threads(2);cv2.setNumThreads(1);torch.manual_seed(cfg["seed"])
        root=Path(cfg["source_run"]);base_cfg=json.loads((root/"config.json").read_text())
        seed=dict(np.load(root/"mvs_source_seeds.npz",allow_pickle=False))
        g0=dict(np.load(root/"image_only/gaussians_initial.npz",allow_pickle=False))
        aroot=Path(cfg["a_root"]);handoff=dict(np.load(aroot/"handoff_mvs.npz",allow_pickle=False))
        profiles=dict(np.load(aroot/"mvs_profiles.npz",allow_pickle=False))
        areceipt=json.loads((aroot/"technical_receipt.json").read_text())
        inputs=[root/"mvs_source_seeds.npz",root/"image_only/gaussians_initial.npz",root/"config.json",
            aroot/"handoff_mvs.npz",aroot/"mvs_profiles.npz",aroot/"technical_receipt.json",Path(cfg["schedule"])]
        input_hashes={str(p):sha(p) for p in inputs}
        sources=[Path(__file__),Path("src/phd/p2_ab_v6/surface_budget.py"),Path(path),Path(cfg.get("driver","scripts/phd/p2_ab_v6/b_surface_docker.sh"))]
        source_hashes={str(p):sha(p) for p in sources}
        for p in sources:
            dest=output/"source_snapshot"/str(p).lstrip("/");dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        write(output/"config.json",cfg)
        model=SurfaceGaussians(seed,base_cfg);views=load_views(Path(base_cfg["common_root"]),base_cfg)
        initialize_texture_and_support(model,views)
        with torch.no_grad():model.sh0.copy_(torch.as_tensor(g0["sh0"],device="cuda"))
        if geometry_hash(model.state_arrays(seed))!=geometry_hash(g0):raise ValueError("G0 differs from frozen MVS")
        initial_state={k:v.clone() for k,v in model.state_dict().items()}
        train=[v for v in views if v.role=="train"];ev=[v for v in views if v.role=="eval"]
        evidence=Evidence(handoff,profiles,seed)
        if not bool(evidence.observable.any()):raise ValueError("No observational A envelope; no fake B mechanism result")
        initial,initial_renders=evaluate(model,ev,seed,output/"initial",cfg,active=evidence.observable)
        np.savez_compressed(output/"initial/gaussians.npz",**model.state_arrays(seed))
        guard=SurfaceGuard(model,train,seed,evidence,cfg)
        initial_guard=guard.check(model)
        if not initial_guard["passed"]:raise ValueError("No valid initial protected surface rays")
        write(output/"initial_guard.json",initial_guard)
        write(output/"views.json",dict(views=[v.provenance for v in views],A_receipt=areceipt))
        schedule=[json.loads(x) for x in Path(cfg["schedule"]).read_text().splitlines()]
        by_id={v.image_id:v for v in train};tiles=[]
        for row in schedule[:cfg["steps"]]:
            x,y,w,h=row["tile"];v=crop_view(by_id[row["image_id"]],[x+w//2,y+h//2],base_cfg["training_tile_dimension_px"])
            if v.provenance["tile_xywh"]!=row["tile"]:raise ValueError("schedule mismatch")
            tiles.append(v)
        results=[]
        for arm in cfg["arms"]:
            name=arm["name"];dest=output/name;dest.mkdir();model.load_state_dict(initial_state)
            geometry=arm["mode"]!="fixed";model.trainable(geometry)
            groups=[dict(params=[model.sh0],lr=cfg["color_lr"]),dict(params=[model.sh_rest],lr=cfg["color_lr"]*cfg["higher_sh_lr_factor"])]
            if geometry:groups.append(dict(params=[model.normal_offset],lr=cfg["normal_lr"]))
            optimizer=torch.optim.Adam(groups,eps=1e-15)
            last_safe=model.normal_offset.detach().clone();ever=torch.zeros(len(seed["xyz"]),device="cuda",dtype=torch.bool)
            previous_mask=ever.clone();mask_switches=0;guard_rows=[];last_mask=ever.clone()
            for step,view in enumerate(tiles):
                factor=1-.9*step/cfg["steps"]
                for group,lr in zip(optimizer.param_groups,[cfg["color_lr"],cfg["color_lr"]*cfg["higher_sh_lr_factor"],cfg["normal_lr"]]):group["lr"]=lr*factor
                optimizer.zero_grad(set_to_none=True)
                loss,row=photo_loss(model,view,cfg,0.)
                before=model.normal_offset.detach().clone()
                if arm["mode"] in {"static","dynamic"}:loss=loss+cfg["evidence_weight"]*evidence.loss(model.normal_offset)
                if not bool(torch.isfinite(loss)):raise FloatingPointError("nonfinite objective")
                if arm["mode"]=="residual":
                    with torch.no_grad():rout=render_view(model,view);last_mask=residual_mask(model,view,rout)
                loss.backward()
                torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],10.)
                optimizer.step()
                with torch.no_grad():
                    model.sh0.clamp_(-.5/.28209479177387814,.5/.28209479177387814)
                    if geometry:
                        proposed=model.normal_offset.detach().clone()
                        if arm["mode"]=="residual":proposed=proposed.clamp(-cfg["normal_search_limit_m"],cfg["normal_search_limit_m"])
                        else:
                            proposed=evidence.constrain(proposed)
                            last_mask=evidence.observable if arm["mode"]=="static" else evidence.dynamic_accept(before,proposed)
                        model.normal_offset.copy_(torch.where(last_mask,proposed,before))
                        # Rejected scalar steps must not retain hidden optimizer momentum.
                        state=optimizer.state[model.normal_offset]
                        for key in ("exp_avg","exp_avg_sq"):state[key][~last_mask]=0
                        moved=(model.normal_offset-before).abs()>1e-9;ever|=moved
                    else:last_mask.zero_()
                    mask_switches+=int((last_mask!=previous_mask).sum());previous_mask=last_mask.clone()
                    row.update(step=step+1,image_id=view.image_id,tile=view.provenance["tile_xywh"],
                        loss=float(loss),geometry_mask_count=int(last_mask.sum()),ever_updated_count=int(ever.sum()),
                        mask_switches=mask_switches,normal_offset_rms_m=float(model.normal_offset.square().mean().sqrt()))
                    if arm.get("surface_guard") and ((step+1)%cfg["guard_every"]==0 or step+1==cfg["steps"]):
                        projected=guard.project(model,last_safe,evidence if arm.get("joint_recheck") else None);last_safe=model.normal_offset.detach().clone()
                        if projected["accepted_factor"]<1:
                            for key in ("exp_avg","exp_avg_sq"):optimizer.state[model.normal_offset][key].zero_()
                        projected["step"]=step+1;guard_rows.append(projected);row["surface_guard"]=projected
                    if (step+1)%cfg["log_every"]==0:
                        np.savez_compressed(dest/f"mask_step_{step+1}.npz",active=last_mask.cpu().numpy(),normal_offset_m=model.normal_offset.cpu().numpy())
                with (dest/"training.jsonl").open("a") as stream:stream.write(json.dumps(row,allow_nan=False)+"\n")
                if (step+1)%cfg["log_every"]==0:print(name,step+1,row["loss"],row["geometry_mask_count"],flush=True)
            final_active=model.normal_offset.detach().abs()>.001
            final,_=evaluate(model,ev,seed,dest,cfg,initial_renders,final_active)
            shutil.copy2(output/"initial/extracted_surface.npz",dest/"initial_extracted_surface.npz")
            state=model.state_arrays(seed);np.savez_compressed(dest/"gaussians_final.npz",**state)
            np.savez_compressed(dest/"mask_final.npz",active=last_mask.cpu().numpy(),ever=ever.cpu().numpy(),final_changed_gt1mm=final_active.cpu().numpy())
            final_guard=guard.check(model)
            offset=state["normal_offset_m"];obs=np.asarray(handoff["observable"],bool)
            use=np.maximum(np.abs(offset-handoff["observation_low_m"]),np.abs(offset-handoff["observation_high_m"]))
            eligible=obs&(use<=cfg["epsilon_m"]+1e-6)
            unresolved=obs&~eligible
            costs=evidence.cost_at(model.normal_offset).detach()
            worse=(costs>evidence.cost_at(evidence.zero)+2e-6).any(0).cpu().numpy()&obs
            changed=np.abs(offset)>1e-7
            np.savez_compressed(dest/"conditional_status.npz",seed_id=seed["seed_id"],
                observable=obs,conditional_eligible=eligible,unresolved=unresolved,
                evidence_worse_than_initial=worse,changed=changed)
            result=dict(arm=name,mode=arm["mode"],appearance=final,
                normal_offset_rms_m=float(np.sqrt(np.mean(offset**2))),normal_offset_max_m=float(np.abs(offset).max()),
                changed_gt1mm=int((np.abs(offset)>.001).sum()),ever_updated_count=int(ever.sum()),mask_switches=mask_switches,
                observation_envelope_count=int(obs.sum()),conditional_use_error_violations=int((use[obs]>cfg["epsilon_m"]+1e-6).sum()),
                conditional_eligible_count=int(eligible.sum()),unresolved_count=int(unresolved.sum()),
                changed_outside_allowable_count=int((changed&unresolved).sum()),
                evidence_worse_than_initial_count=int(worse.sum()),
                final_mask_semantics="Gaussian centres with final absolute normal offset greater than 1mm; initial mask is A-observable centres",
                protected_surface=final_guard,projection_history=guard_rows,
                frozen_shape_parameters=all(np.array_equal(state[k],g0[k]) for k in ("quats","scales","opacity")),
                systematic_error_calibrated=False,scientific_verdict=None)
            if arm.get("surface_guard") and not final_guard["passed"]:raise ValueError("final guarded surface contract failed")
            if arm.get("joint_recheck") and (result["changed_outside_allowable_count"] or result["evidence_worse_than_initial_count"]):
                raise ValueError("jointly guarded updates violate A interval or image-group cost; unchanged unresolved base is not accepted")
            if not result["frozen_shape_parameters"]:raise ValueError("unapproved primitive shape update")
            write(dest/"result.json",result);results.append(result)
            print(json.dumps(dict(arm=name,mae=final["mae"],guard_violations=final_guard["violations"],changed=result["changed_gt1mm"])),flush=True)
        if any(sha(p)!=h for p,h in input_hashes.items()):raise ValueError("input changed during execution")
        write(output/"result.json",dict(status="COMPLETED_CONDITIONAL_SURFACE_PROBE",arms=results,
            initial=initial,source_hashes=source_hashes,input_hashes=input_hashes,runtime_seconds=time.monotonic()-started,
            git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
            A_scope="actual P2 image profiles; absolute two-source error calibration not completed",
            B_scope="normal-only local surface refinement; no densification/new topology/semantic detail claim",
            scientific_verdict=None))
    except Exception as exc:
        write(output/"FAILED.json",dict(error=repr(exc),traceback=traceback.format_exc(),scientific_verdict=None));raise


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--config",required=True);main(parser.parse_args().config)
