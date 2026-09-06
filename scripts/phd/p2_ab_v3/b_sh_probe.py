"""Separate SH3 capacity probe; the completed SH0 probe remains immutable."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
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
from src.phd.p2_ab_v3.appearance import image_quality,weighted_rgb_l1
from src.phd.p2_ab_v3.appearance_sh import StructuredGaussians,render_view,freeze_except_color
from src.phd.p2_ab_v2.reconstruction import crop_view,render_view as sh0_render_view
from scripts.phd.p2_ab_v2.b_run import load_views,initialize_texture_and_support,readout_validity
from src.stage2.loss.data_fitting import masked_ssim


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(8<<20),b""):h.update(block)
    return h.hexdigest()


def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def array_hash(array):return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def geometry_hash(state):return {k:array_hash(state[k]) for k in ["xyz","quats","scales","opacity","group"]}


def quality(view,cfg):
    return image_quality(view.image,view.mask,low=cfg["quality_low"],high=cfg["quality_high"],clipped_weight=cfg["clipped_quality_weight"])


def photo_loss(model,view,cfg,gain):
    out=render_view(model,view);q,_=quality(view,cfg)
    l1,meta=weighted_rgb_l1(out["rgb"],view.image,q,gain=gain,cap=cfg["residual_cap"],scale_floor=cfg["residual_scale_floor"])
    ss=masked_ssim(out["rgb"].clamp(0,1),view.image,view.mask)
    loss=(1-cfg["ssim_fraction"])*l1+cfg["ssim_fraction"]*(1-ss)
    return loss,dict(weighted_l1=float(l1.detach()),ssim=float(ss.detach()),**meta)


@torch.no_grad()
def evaluate(model,views,destination,cfg,initial_dir=None,save=True):
    metrics=[];frames=[];checks={}
    for view in views:
        out=render_view(model,view);validity=readout_validity(out);q,clipped=quality(view,cfg)
        error=(out["rgb"].clamp(0,1)-view.image).abs().mean(-1)
        mask=view.mask;n=int(mask.sum());qm=float(q.sum())
        row=dict(image_id=view.image_id,conditional_pixels=n,quality_mass=qm,clipped_support_pixels=int(clipped.sum()),
            fixed_support_mae=float(error[mask].mean()) if n else None,
            fixed_quality_mae=float((q*error).sum()/q.sum()) if qm else None,
            masked_ssim=float(masked_ssim(out["rgb"].clamp(0,1),view.image,mask)) if n else None)
        metrics.append(row)
        if not save:continue
        frame=dict(image_id=view.image_id,geometry_readout_validity=validity)
        rgb=np.round(out["rgb"].clamp(0,1).cpu().numpy()*255).astype(np.uint8)
        name=f"rgb_{view.image_id}.png";cv2.imwrite(str(destination/name),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR));frame["rgb"]=name
        for key in ["depth","geometry_mass","alpha"]:
            value=out[key].cpu().numpy().astype(np.float32);name=f"{key}_{view.image_id}.npy"
            np.save(destination/name,value);frame[key]=name
            if initial_dir is not None:checks[f"{view.image_id}_{key}_exact"]=np.array_equal(value,np.load(initial_dir/name))
        if initial_dir is None:
            cv2.imwrite(str(destination/f"target_{view.image_id}.png"),cv2.cvtColor(np.round(view.image.cpu().numpy()*255).astype(np.uint8),cv2.COLOR_RGB2BGR))
            cv2.imwrite(str(destination/f"support_{view.image_id}.png"),mask.cpu().numpy().astype(np.uint8)*255)
            np.save(destination/f"quality_{view.image_id}.npy",q.cpu().numpy())
        frames.append(frame)
    return dict(metrics=metrics,frames=frames,geometry_checks=checks,
        fixed_support_pixel_weighted_mae=sum(r["conditional_pixels"]*r["fixed_support_mae"] for r in metrics if r["conditional_pixels"])/sum(r["conditional_pixels"] for r in metrics),
        fixed_quality_weighted_mae=sum(r["quality_mass"]*r["fixed_quality_mae"] for r in metrics if r["quality_mass"])/sum(r["quality_mass"] for r in metrics),
        mean_view_mae=float(np.mean([r["fixed_support_mae"] for r in metrics if r["conditional_pixels"]])),
        mean_view_ssim=float(np.mean([r["masked_ssim"] for r in metrics if r["conditional_pixels"]])))


def main(config_path):
    output=Path("/output")
    if any(output.iterdir()):raise ValueError("new empty output required")
    cfg=json.loads(Path(config_path).read_text());write(output/"STARTED.json",dict(utc=datetime.now(timezone.utc).isoformat(),scientific_verdict=None))
    start=time.monotonic()
    try:
        torch.set_num_threads(2);cv2.setNumThreads(1);torch.manual_seed(cfg["seed"])
        root=Path(cfg["source_run"]);base_cfg=json.loads((root/"config.json").read_text())
        frozen=json.loads(Path(cfg["frozen_source_manifest"]).read_text())
        frozen_before={p:sha(p) for p in frozen["source_hashes"]}
        if frozen_before!=frozen["source_hashes"]:raise ValueError("v2 source differs from frozen manifest")
        parent=json.loads((root/"result.json").read_text())
        for filename,h in parent["geometry_adapter_hashes"].items():
            if sha(Path("/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc")/filename)!=h:raise ValueError("wrong CUDA adapter")
        sources=[Path(__file__),Path("src/phd/p2_ab_v3/appearance.py"),Path("src/phd/p2_ab_v3/appearance_sh.py"),Path(config_path),Path("tests/phd/test_p2_ab_v3_appearance_sh.py")]
        source_hashes={str(p):sha(p) for p in sources}
        for p in sources:
            dest=output/"source_snapshot"/str(p).lstrip("/");dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        inputs=[root/"als_source_seeds.npz",root/cfg["source_arm"]/"gaussians_initial.npz",root/"config.json",root/"result.json",Path(cfg["frozen_source_manifest"])]
        input_hashes={str(p):sha(p) for p in inputs}
        write(output/"config.json",cfg)
        seed=dict(np.load(root/"als_source_seeds.npz",allow_pickle=False))
        g0=np.load(root/cfg["source_arm"]/"gaussians_initial.npz",allow_pickle=False)
        template=StructuredGaussians(seed,base_cfg)
        views=load_views(Path(base_cfg["common_root"]),base_cfg)
        init=initialize_texture_and_support(template,views)
        with torch.no_grad():template.sh0.copy_(torch.tensor(g0["sh0"],device="cuda"))
        actual=template.state_arrays(seed)
        if geometry_hash(actual)!=geometry_hash(g0):raise ValueError("diagnostic G0 geometry differs from source")
        initial_state={k:v.detach().clone() for k,v in template.state_dict().items()}
        np.savez_compressed(output/"gaussians_initial.npz",**actual)
        write(output/"views.json",dict(views=[v.provenance for v in views],initialization=init))
        train=[v for v in views if v.role=="train"];ev=[v for v in views if v.role=="eval"]
        initial_dir=output/"initial";initial_dir.mkdir()
        initial=evaluate(template,ev,initial_dir,cfg)
        with torch.no_grad():
            zero_sh_checks={str(v.image_id):torch.equal(render_view(template,v)["rgb"],sh0_render_view(template,v)["rgb"]) for v in ev}
        if not all(zero_sh_checks.values()):raise ValueError("zero high-order SH changes initial RGB")
        write(output/"zero_sh_initial_rgb_checks.json",zero_sh_checks)
        write(initial_dir/"result.json",initial)
        centers=[torch.nonzero(v.mask).cpu().numpy() for v in train]
        if any(len(x)==0 for x in centers):raise ValueError("empty training support: record before defining new schedule")
        results=[]
        for arm,gain in cfg["arms"].items():
            dest=output/arm;dest.mkdir();model=StructuredGaussians(seed,base_cfg);model.load_state_dict(initial_state)
            color_params=freeze_except_color(model)
            optimizer=torch.optim.Adam([dict(params=[color_params[0]],lr=cfg["color_lr"]),dict(params=[color_params[1]],lr=cfg["color_lr"]*cfg["higher_sh_lr_factor"])],eps=1e-15)
            random=np.random.default_rng(cfg["seed"]);arm_start=time.monotonic()
            for step in range(cfg["steps"]):
                i=step%len(train);yc,xc=centers[i][random.integers(len(centers[i]))]
                view=crop_view(train[i],[xc,yc],base_cfg["training_tile_dimension_px"])
                optimizer.param_groups[0]["lr"]=cfg["color_lr"]*(1-.9*step/cfg["steps"])
                optimizer.param_groups[1]["lr"]=optimizer.param_groups[0]["lr"]*cfg["higher_sh_lr_factor"]
                optimizer.zero_grad(set_to_none=True);loss,row=photo_loss(model,view,cfg,gain)
                if not bool(torch.isfinite(loss)):raise FloatingPointError("nonfinite loss")
                loss.backward()
                if not bool(torch.isfinite(model.sh0.grad).all()):raise FloatingPointError("nonfinite color gradient")
                if not bool(torch.isfinite(model.sh_rest.grad).all()):raise FloatingPointError("nonfinite high-order gradient")
                if any(p.grad is not None for name,p in model.named_parameters() if name not in {"sh0","sh_rest"}):raise RuntimeError("geometry gradient leak")
                row.update(step=step+1,image_id=view.image_id,loss=float(loss.detach()),color_gradient_norm=float(model.sh0.grad.norm()),
                    higher_sh_gradient_norm=float(model.sh_rest.grad.norm()),geometry_gradients_absent=True,tile=view.provenance["tile_xywh"],elapsed_seconds=time.monotonic()-arm_start)
                torch.nn.utils.clip_grad_norm_(color_params,10.)
                optimizer.step()
                with torch.no_grad():model.sh0.clamp_(-.5/.28209479177387814,.5/.28209479177387814)
                if (step+1)%cfg["evaluation_every"]==0:row["evaluation"]=evaluate(model,ev,dest,cfg,save=False)
                with (dest/"training.jsonl").open("a") as f:f.write(json.dumps(row,allow_nan=False)+"\n")
                if (step+1)%cfg["log_every"]==0:print(arm,step+1,float(loss.detach()),flush=True)
            after=model.state_arrays(seed);np.savez_compressed(dest/"gaussians_final.npz",**after)
            final=evaluate(model,ev,dest,cfg,initial_dir=initial_dir)
            checks=dict(geometry_parameters_exact=geometry_hash(after)==geometry_hash(actual),
                geometry_and_alpha_renders_exact=all(final["geometry_checks"].values()),
                higher_sh_nonzero=bool(np.any(after["sh_rest"]!=0)),
                raw_sh0_export_matches=bool(np.allclose(after["sh0"][:,0]*.28209479177387814+.5,after["rgb"],atol=1e-6,rtol=0)))
            result=dict(arm=arm,residual_gain=gain,initial=initial,final=final,checks=checks,steps=cfg["steps"],runtime_seconds=time.monotonic()-arm_start,
                sh_degree=3,higher_sh_l2=float(np.linalg.norm(after["sh_rest"])),
                status="PASS" if all(checks.values()) else "FAIL",scientific_verdict=None)
            write(dest/"result.json",result);results.append(result);del model;torch.cuda.empty_cache()
        unchanged=all(sha(p)==h for p,h in frozen_before.items())
        status="COMPLETED_DIAGNOSTIC" if unchanged and all(r["status"]=="PASS" for r in results) else "FAIL"
        write(output/"result.json",dict(status=status,arms=results,source_hashes=source_hashes,input_hashes=input_hashes,
            frozen_v2_source_unchanged=unchanged,geometry_contract=parent["geometry_contract"],geometry_adapter_hashes=parent["geometry_adapter_hashes"],
            geometry_adapter_audit=parent["geometry_adapter_audit"],runtime_seconds=time.monotonic()-start,
            versions=dict(torch=torch.__version__,cuda=torch.version.cuda,gsplat=__import__("gsplat").__version__,
                docker_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD")),
            purpose=cfg["scope"],scientific_verdict=None))
        print(json.dumps(dict(status=status,arms=len(results),frozen_v2_unchanged=unchanged)),flush=True)
    except Exception as exc:
        write(output/"FAILED.json",dict(error=repr(exc),traceback=traceback.format_exc(),scientific_verdict=None));raise


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
