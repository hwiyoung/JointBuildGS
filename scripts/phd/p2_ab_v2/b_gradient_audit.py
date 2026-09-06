"""Loss-component gradients on a frozen real state, with no optimizer or update."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from scripts.phd.p2_ab_v2.b_run import load_views,initialize_texture_and_support,write_json,sha
from src.phd.p2_ab_v2.reconstruction import StructuredGaussians,render_view,crop_view,normal_consistency,multiview_loss
from src.stage2.loss.data_fitting import l_photo


def main(config_path):
    audit=json.loads(Path(config_path).read_text())
    cfg=json.loads(Path(audit["solver_config"]).read_text())
    root=Path(audit["run_root"]);state=root/audit["arm"]/"gaussians_final.pt"
    seed=dict(np.load(root/"als_source_seeds.npz",allow_pickle=False))
    model=StructuredGaussians(seed,cfg)
    views=load_views(Path(cfg["common_root"]),cfg)
    initialize_texture_and_support(model,views)
    model.load_state_dict(torch.load(state,map_location="cuda",weights_only=True))
    train=[v for v in views if v.role=="train"]
    source=train[0]
    c0=-source.viewmat[:3,:3].T@source.viewmat[:3,3]
    others=sorted(train[1:],key=lambda v:float(torch.linalg.vector_norm(-v.viewmat[:3,:3].T@v.viewmat[:3,3]-c0)))
    target=others[0]
    coords=torch.nonzero(source.mask)
    yc,xc=coords[len(coords)//2].cpu().numpy()
    src=crop_view(source,[xc,yc],cfg["training_tile_dimension_px"])
    with torch.no_grad():
        ray=torch.tensor([xc+.5,yc+.5,1.],dtype=torch.float32,device="cuda")@torch.linalg.inv(source.K).T
        world=(ray*source.initial_depth[yc,xc]-source.viewmat[:3,3])@source.viewmat[:3,:3]
        cam=world@target.viewmat[:3,:3].T+target.viewmat[:3,3];uv=cam@target.K.T
        ref=crop_view(target,(uv[:2]/uv[2]).cpu().numpy(),cfg["training_tile_dimension_px"])
        reference=render_view(model,ref)
    parameters={name:p for name,p in model.named_parameters() if name!="sh0"}
    results={}
    for component in ["rgb_ssim","normal","multiview"]:
        output=render_view(model,src)
        metadata={}
        if component=="rgb_ssim":loss=l_photo(output["rgb"],src.image,lam=.2,mask=src.mask)
        elif component=="normal":loss=normal_consistency(output,src.mask)
        else:loss,metadata=multiview_loss(src,output,ref,reference,cfg["mvc_pixel_stride"])
        gradients=torch.autograd.grad(loss,list(parameters.values()),allow_unused=True)
        norms={name:{"norm":float(g.norm()) if g is not None else 0.,
                     "finite":bool(torch.isfinite(g).all()) if g is not None else True,
                     "nonzero_entries":int((g!=0).sum()) if g is not None else 0}
               for (name,_),g in zip(parameters.items(),gradients)}
        results[component]={"loss":float(loss.detach()),"gradients":norms,**metadata}
    ok=all(all(v["finite"] for v in r["gradients"].values()) and
           all(r["gradients"][k]["norm"]>0 for k in ["structure","detail","rotation"]) for r in results.values())
    result={"status":"PASS" if ok else "FAIL","source_image_id":src.image_id,"target_image_id":ref.image_id,
       "source_tile":src.provenance["tile_xywh"],"reference_tile":ref.provenance["tile_xywh"],
       "components":results,"optimizer_steps":0,"state_sha256":sha(state),"script_sha256":sha(__file__),
       "config_sha256":sha(config_path),"scientific_verdict":None}
    write_json("/output/gradient_audit.json",result);print(json.dumps(result),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
