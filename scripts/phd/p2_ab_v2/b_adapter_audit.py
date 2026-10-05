"""Actual gsplat forward and finite-difference audit for the two-pass adapter."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from gsplat import rasterization_2dgs
from src.stage2.model import quaternion_from_positive_z_normals


def raster(means,quats,scales,opacity,colors,K,V,width,height,geometry):
    if geometry:
        features=torch.zeros((len(means),8),device=means.device,dtype=means.dtype)
        mode="RGB"
    else:features=colors;mode="RGB+ED"
    output=rasterization_2dgs(means=means,quats=quats,scales=scales,opacities=opacity,
        colors=features,viewmats=V[None],Ks=K[None],width=width,height=height,
        sh_degree=None,render_mode=mode,near_plane=.01,far_plane=1e10)
    mass=output[1][0,...,0];s=output[5][0,...,0]
    return dict(rgb=output[0][0,...,:3],alpha=mass,normal_sum=output[2][0],depth_sum=s,
                depth=s/mass.clamp_min(1e-10),raw=output)


def tensors(points,normals,opacities,scale=.16):
    p=torch.tensor(points,device="cuda",dtype=torch.float32)
    n=torch.nn.functional.normalize(torch.tensor(normals,device="cuda",dtype=torch.float32),dim=-1)
    q=quaternion_from_positive_z_normals(n)
    scales=torch.tensor([[scale,scale,1e-6]]*len(points),device="cuda")
    o=torch.tensor(opacities,device="cuda",dtype=torch.float32)
    c=torch.tensor([[.7,.3,.2]]*len(points),device="cuda")
    return p,q,scales,o,c


def main(config_path,mode):
    cfg=json.loads(Path(config_path).read_text());out=Path("/output")
    device="cuda";torch.set_num_threads(2)
    K=torch.tensor([[80.,0,32.5],[0,80.,32.5],[0,0,1]],device=device)
    V=torch.eye(4,device=device)
    p,q,s,o,c=tensors([[0,0,3]],[[.3,.2,.9327]],[.5])
    rgb=raster(p,q,s,o,c,K,V,65,65,False)
    synthetic={k:rgb[k].detach().cpu().numpy() for k in ["rgb","alpha"]}
    arm=Path(cfg["baseline_arm"]);state=np.load(arm/"gaussians_initial.npz")
    view=next(r for r in json.loads((arm.parent/"views.json").read_text())["views"] if r["image_id"]==cfg["image_id"])
    rk=torch.tensor(view["K"],device=device,dtype=torch.float32);rv=torch.tensor(view["viewmat"],device=device,dtype=torch.float32)
    real=[torch.tensor(state[k],device=device) for k in ["xyz","quats","scales","opacity","rgb"]]
    rendered=raster(*real,rk,rv,view["width"],view["height"],False)
    actual={k:rendered[k].detach().cpu().numpy() for k in ["rgb","alpha"]}
    np.savez_compressed(out/"rgb_reference.npz",synthetic_rgb=synthetic["rgb"],synthetic_alpha=synthetic["alpha"],
                        real_rgb=actual["rgb"],real_alpha=actual["alpha"])
    if mode=="baseline":
        (out/"baseline.json").write_text(json.dumps({"status":"BASELINE_SAVED","scientific_verdict":None})+"\n");return
    baseline=np.load(Path(cfg["audit_root"])/"baseline"/"rgb_reference.npz")
    checks={"synthetic_rgb_byte_equal":np.array_equal(baseline["synthetic_rgb"],synthetic["rgb"]),
            "synthetic_alpha_byte_equal":np.array_equal(baseline["synthetic_alpha"],synthetic["alpha"]),
            "real_rgb_byte_equal":np.array_equal(baseline["real_rgb"],actual["rgb"]),
            "real_alpha_byte_equal":np.array_equal(baseline["real_alpha"],actual["alpha"])}
    geo=raster(p,q,s,o,c,K,V,65,65,True)
    u,v=34,33
    normal=torch.nn.functional.normalize(torch.tensor([.3,.2,.9327],device=device),dim=0)
    ray=torch.linalg.inv(K)@torch.tensor([u+.5,v+.5,1.],device=device)
    expected=(normal@p[0])/(normal@ray)
    checks["slanted_single_plane_depth"]=abs(float(geo["depth"][v,u]-expected))<2e-5
    checks["single_plane_mass_positive"]=0<float(geo["alpha"][v,u])<1
    # A nonidentity camera verifies that the native normal head is world-frame.
    angle=torch.tensor(.35,device=device);co,si=angle.cos(),angle.sin()
    rotation=torch.eye(3,device=device);rotation[0,0]=co;rotation[0,2]=si;rotation[2,0]=-si;rotation[2,2]=co
    rotated_view=torch.eye(4,device=device);rotated_view[:3,:3]=rotation
    rotated_points=p @ rotation
    ng=raster(rotated_points,q,s,o,c,K,rotated_view,65,65,True)
    world_normal=ng["normal_sum"][32,32]/ng["alpha"][32,32]
    checks["nonidentity_world_normal_mass_contract"]=abs(float((world_normal*normal).sum().abs())-1)<2e-5
    pix=torch.tensor([[32.5,32.5,1.],[33.5,32.5,1.],[32.5,33.5,1.]],device=device)
    depths=torch.stack((ng["depth"][32,32],ng["depth"][32,33],ng["depth"][33,32]))
    cp=(pix@torch.linalg.inv(K).T)*depths[:,None]
    derived=torch.nn.functional.normalize(torch.cross(cp[1]-cp[0],cp[2]-cp[0],dim=0),dim=0)@rotation
    checks["nonidentity_depth_normal_same_world_frame"]=abs(float((derived*normal).sum().abs())-1)<2e-5
    # Screen-only foreground must not occlude the independent plane compositor.
    front=tensors([[.015,0,3],[0,0,3.5]],[[1,0,1e-6],[0,0,1]],[.9,.7],scale=.16)
    with_front=raster(*front,K,V,65,65,True)
    back=tuple(x[1:] for x in front)
    without_front=raster(*back,K,V,65,65,True)
    checks["screen_only_front_does_not_change_geometry_depth"]=abs(float(with_front["depth"][32,32]-without_front["depth"][32,32]))<2e-5
    checks["screen_only_front_does_not_change_geometry_mass"]=abs(float(with_front["alpha"][32,32]-without_front["alpha"][32,32]))<2e-6
    front_only=tuple(x[:1] for x in front)
    nohit=raster(*front_only,K,V,65,65,True)
    checks["grazing_screen_only_is_geometry_missing"]=float(nohit["alpha"][32,32])==0 and float(nohit["depth"][32,32])==0
    # C4 appearance gradients must remain finite even with unsafe old hit depths.
    fp=[x.clone().detach().requires_grad_(i<4) for i,x in enumerate(front_only)]
    frgb=raster(*fp,K,V,65,65,False)
    grads=torch.autograd.grad(frgb["rgb"].sum(),fp[:4],allow_unused=True)
    checks["grazing_RGB_gradients_finite"]=all(g is None or bool(torch.isfinite(g).all()) for g in grads)
    # Exact two parallel planes checks the normalized denominator and front alpha.
    pair=tensors([[0,0,3],[0,0,3.4]],[[0,0,1],[0,0,1]],[.4,.55])
    pair=[x.clone().detach().requires_grad_(i in [0,3]) for i,x in enumerate(pair)]
    pg=raster(*pair,K,V,65,65,True);A=.4+.6*.55;D=(.4*3+.6*.55*3.4)/A
    checks["two_plane_mass_formula"]=abs(float(pg["alpha"][32,32])-A)<2e-6
    checks["two_plane_depth_formula"]=abs(float(pg["depth"][32,32])-D)<2e-5
    gp,go=torch.autograd.grad(pg["depth"][32,32],[pair[0],pair[3]])
    analytic_opacity=[.55*(3-3.4)/A**2,.4*.6*(3.4-3)/A**2]
    checks["normalized_depth_opacity_gradient_formula"]=np.allclose(go.cpu().numpy(),analytic_opacity,atol=2e-5,rtol=1e-4)
    checks["normalized_depth_z_gradient_formula"]=np.allclose(gp[:,2].cpu().numpy(),[.4/A,.6*.55/A],atol=2e-5,rtol=1e-4)
    # Opacity saturation must leave the direct hit-depth derivative intact.
    sat=list(tensors([[0,0,3]],[[0,0,1]],[2.]));sat[0].requires_grad_()
    sg=raster(*sat,K,V,65,65,True)
    sp=torch.autograd.grad(sg["depth"][32,32],sat[0])[0]
    checks["saturated_alpha_direct_depth_gradient"]=abs(float(sp[0,2])-1)<2e-5 and abs(float(sg["depth"][32,32])-3)<2e-5
    opaque=list(tensors([[0,0,3],[0,0,3.4],[0,0,4]],[[0,0,1],[0,0,1],[0,0,1]],[.95,2.,.8]))
    opaque[0].requires_grad_();opaque[3].requires_grad_()
    og=raster(*opaque,K,V,65,65,True)
    opaque_mass=.95+.05*.999
    opaque_depth=(.95*3+.05*.999*3.4)/opaque_mass
    op,oo=torch.autograd.grad(og["depth"][32,32],[opaque[0],opaque[3]])
    checks["crossing_plane_included_before_geometry_stop"]=abs(float(og["alpha"][32,32])-opaque_mass)<2e-6
    checks["crossing_depth_and_terminated_tail_gradient"]=abs(float(og["depth"][32,32])-opaque_depth)<2e-5 and float(op[2].abs().max())==0 and float(oo[2].abs())==0
    for label,points,normals,opacities in [
        ("behind_camera",[[0,0,-3]],[[0,0,1]],[.8]),
        ("zero_opacity",[[0,0,3]],[[0,0,1]],[0.]),
        ("exact_parallel",[[.015,0,3]],[[1,0,0]],[.8])]:
        special=tensors(points,normals,opacities)
        result=raster(*special,K,V,65,65,True)
        checks[label+"_missing_finite"]=float(result["alpha"][32,32])==0 and float(result["depth"][32,32])==0 and all(bool(torch.isfinite(result[k]).all()) for k in ["alpha","depth","normal_sum"])
    empty=raster(*(x[:0] for x in tensors([[0,0,3]],[[0,0,1]],[.8])),K,V,65,65,True)
    checks["empty_scene_missing_finite"]=float(empty["alpha"].sum())==0 and float(empty["depth"].sum())==0 and bool(torch.isfinite(empty["normal_sum"]).all())
    fd_rows=[]
    base=tensors([[.012,.008,3],[-.006,.013,3.4]],[[.3,.2,.9327],[-.15,.05,.9874]],[.4,.55])
    params=[x.clone().detach().requires_grad_(i<4) for i,x in enumerate(base)]
    def objective(values):
        r=raster(*values,K,V,65,65,True)
        return r["depth"][33,34]+.2*r["alpha"][33,34]+.1*r["normal_sum"][33,34,0]
    value=objective(params);gradients=torch.autograd.grad(value,params[:4])
    for index,name,coordinate,eps in [(0,"mean_x",(0,0),.001),(0,"mean_z",(0,2),.001),
            (1,"quat_y",(0,2),.0005),(2,"scale_x",(0,0),.0005),(3,"opacity",(0,),.001)]:
        plus=[x.detach().clone() for x in base];minus=[x.detach().clone() for x in base]
        plus[index][coordinate]+=eps;minus[index][coordinate]-=eps
        fd=float((objective(plus)-objective(minus))/(2*eps));ad=float(gradients[index][coordinate])
        error=abs(fd-ad);passed=error<=cfg["fd_absolute_tolerance"]+cfg["fd_relative_tolerance"]*abs(fd)
        fd_rows.append(dict(parameter=name,autograd=ad,finite_difference=fd,abs_error=error,pass_check=passed))
        checks["finite_difference_"+name]=passed and np.isfinite(ad)
    rg=raster(*real,rk,rv,view["width"],view["height"],True)
    checks["real361_all_geometry_outputs_finite"]=all(bool(torch.isfinite(rg[k]).all()) for k in ["alpha","depth","normal_sum"])
    checks["real361_mass_range_and_missing_depth"]=bool(((rg["alpha"]>=0)&(rg["alpha"]<=1.000001)).all()) and bool((rg["depth"][rg["alpha"]==0]==0).all())
    u,v=cfg["pixel_uv"]
    real_z=(real[0]@rv[:3,:3].T+rv[:3,3])[:,2]
    checks["real361_extreme_tail_removed"]=float(rg["depth"][v,u])<float(real_z.max())+1 and float(rg["depth"][v,u])>0
    np.savez_compressed(out/"real_geometry.npz",geometry_mass=rg["alpha"].detach().cpu().numpy(),depth=rg["depth"].detach().cpu().numpy())
    result={"status":"PASS" if all(checks.values()) else "FAIL","checks":{k:bool(v) for k,v in checks.items()},
        "finite_difference":fd_rows,"real361":{"pixel_uv":cfg["pixel_uv"],"geometry_mass":float(rg["alpha"][v,u]),
            "geometry_depth_m":float(rg["depth"][v,u]),"old_depth_m":4261.00927734375,
            "geometry_support_pixels":int((rg["alpha"]>=.5).sum()),"rgb_support_pixels":int((rendered["alpha"]>=.5).sum()),
            "supported_depth_quantiles_m":torch.quantile(rg["depth"][rg["alpha"]>=.5],torch.tensor([0.,.1,.5,.9,1.],device=device)).cpu().tolist()},"scientific_verdict":None}
    source_paths=[Path(__file__),Path("/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_fwd.cu"),Path("/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_bwd.cu")]
    result["source_hashes"]={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    result["input_precondition"]="finite Gaussian means/quaternions/positive scales/opacities; nonfinite model inputs are errors, not missing surface observations"
    for p in source_paths:(out/p.name).write_bytes(p.read_bytes())
    (out/"audit.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n");print(json.dumps(result),flush=True)
    if result["status"]!="PASS":raise RuntimeError("geometry adapter audit failed")


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);p.add_argument("--mode",choices=["baseline","corrected"],required=True)
    a=p.parse_args();main(a.config,a.mode)
