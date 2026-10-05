"""Audit preserved surface tails without changing the rendering or point stream."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from src.stage2.model import quat_to_rotmat


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(config_path):
    cfg=json.loads(Path(config_path).read_text());root=Path(cfg["run_root"]);arm=root/cfg["arm"]
    points=np.load(arm/"initial_extracted_surface.npz",allow_pickle=False)
    state=np.load(arm/"gaussians_initial.npz",allow_pickle=False)
    views={r["image_id"]:r for r in json.loads((root/"views.json").read_text())["views"]}
    xyz=points["xyz"].astype(np.float64)
    source=state["xyz"].astype(np.float64)
    frames=quat_to_rotmat(torch.tensor(state["quats"],dtype=torch.float64)).numpy()
    normal=frames[:,:,2]
    x0,x1,y0,y1=cfg["source_prism_xy"]
    inside=(xyz[:,0]>=x0)&(xyz[:,0]<x1)&(xyz[:,1]>=y0)&(xyz[:,1]<y1)
    error_rows=[]
    for iid in np.unique(points["image_id"]):
        ii=np.flatnonzero(points["image_id"]==iid);v=views[int(iid)]
        V=np.asarray(v["viewmat"]);K=np.asarray(v["K"])
        depth=np.load(arm/f"initial_depth_{iid}.npy")
        uv=points["pixel_uv"][ii];saved=depth[uv[:,1],uv[:,0]]
        camera=xyz[ii]@V[:3,:3].T+V[:3,3]
        error_rows.append({"image_id":int(iid),"point_count":len(ii),
            "reprojected_camera_z_minus_saved_depth_abs_max_m":float(np.max(np.abs(camera[:,2]-saved))),
            "saved_depth_range_m":[float(saved.min()),float(saved.max())],
            "source_center_camera_z_range_m":[float((source@V[:3,:3].T+V[:3,3])[:,2].min()),float((source@V[:3,:3].T+V[:3,3])[:,2].max())]})
    far=int(np.linalg.norm(xyz-source.mean(0),axis=1).argmax())
    iid=int(points["image_id"][far]);u,v=points["pixel_uv"][far];view=views[iid]
    V=np.asarray(view["viewmat"]);K=np.asarray(view["K"])
    ray_cam=np.array([u+.5,v+.5,1.])@np.linalg.inv(K).T
    ray=ray_cam@V[:3,:3];origin=-V[:3,3]@V[:3,:3]
    denom=normal@ray
    with np.errstate(divide="ignore",invalid="ignore",over="ignore"):
        plane_z=np.sum((source-origin)*normal,axis=1)/denom
        hit=origin+plane_z[:,None]*ray
        local=np.einsum("nc,nci->ni",hit-source,frames[:,:,:2])/state["scales"][:,:2]
        rho_plane=(local**2).sum(1)
        camera=source@V[:3,:3].T+V[:3,3]
        projection=camera@K.T;means2d=projection[:,:2]/projection[:,2:]
        rho_screen=cfg["filter_inv_square"]*((means2d-np.array([u+.5,v+.5]))**2).sum(1)
        alpha=np.minimum(.999,state["opacity"]*np.exp(-.5*np.minimum(rho_plane,rho_screen)))
    candidates=np.flatnonzero(np.isfinite(plane_z)&np.isfinite(alpha)&(alpha>=1/255)&(camera[:,2]>0))
    candidates=candidates[np.argsort(camera[candidates,2],kind="stable")]
    T=1.;terms=[]
    for i in candidates:
        next_T=T*(1-alpha[i])
        if next_T<=1e-4:break
        weight=T*alpha[i]
        terms.append({"seed_index":int(i),"center_camera_z_m":float(camera[i,2]),
          "ray_plane_denom":float(denom[i]),"plane_hit_camera_z_m":float(plane_z[i]),
          "rho_plane":float(rho_plane[i]),"rho_screen":float(rho_screen[i]),
          "lowpass_branch":bool(rho_screen[i]<rho_plane[i]),"alpha":float(alpha[i]),
          "compositing_weight":float(weight),"weighted_intersection_depth":float(weight*plane_z[i])})
        T=next_T
    estimated=sum(t["weighted_intersection_depth"] for t in terms)/(1-T)
    terms.sort(key=lambda r:abs(r["weighted_intersection_depth"]),reverse=True)
    d=np.load(arm/f"initial_depth_{iid}.npy");a=np.load(arm/f"initial_alpha_{iid}.npy")
    output={"status":"DIAGNOSTIC_COMPLETE","point_count":len(xyz),"bbox":[xyz.min(0).tolist(),xyz.max(0).tolist()],
        "inside_fixed_xy_count":int(inside.sum()),"outside_fixed_xy_count":int((~inside).sum()),
        "backprojection_checks":error_rows,"extreme_sample":{"image_id":iid,"pixel_uv":[int(u),int(v)],
          "xyz":xyz[far].tolist(),"saved_depth_m":float(d[v,u]),"saved_alpha":float(a[v,u]),
          "analytic_alpha_without_CUDA_tile_culling":float(1-T),
          "analytic_expected_depth_m_without_CUDA_tile_culling":float(estimated),"largest_contributions":terms[:10]},
        "scope":"Double-precision analytical plane/lowpass calculation follows kernel algebra but does not reproduce CUDA tile culling or float32 near-parallel arithmetic; not an exact rasterizer replay",
        "config_sha256":sha(config_path),"source_sha256":sha(__file__),"scientific_verdict":None}
    Path("/output/surface_audit.json").write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:output[k] for k in ["status","point_count","outside_fixed_xy_count","extreme_sample"]}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
