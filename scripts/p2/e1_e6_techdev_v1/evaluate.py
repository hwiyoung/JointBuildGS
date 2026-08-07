from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import laspy
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union
import torch
from gsplat import rasterization_2dgs

from src.stage2.colmap_io import read_cameras_bin, read_images_bin


SHIFT = np.asarray([690953.0, 5336071.0, 604.0])
AOI = [690791.74, 5335864.05, 691154.65, 5336353.85]


def project_depth(points_local: np.ndarray, image, camera) -> tuple[np.ndarray, np.ndarray]:
    k = camera.K(); xyz = points_local @ image.R().T + image.tvec
    front = xyz[:, 2] > 0.1; uvw = xyz @ k.T; uv = np.zeros((len(xyz),2)); uv[front] = uvw[front,:2] / uvw[front,2:3]
    h,w=int(camera.height),int(camera.width); inside=front&(uv[:,0]>=0)&(uv[:,0]<w)&(uv[:,1]>=0)&(uv[:,1]<h); selected=np.flatnonzero(inside)
    depth=np.zeros((h,w),np.float32); mask=np.zeros((h,w),bool)
    if len(selected):
        x=np.rint(uv[selected,0]).astype(np.int32).clip(0,w-1); y=np.rint(uv[selected,1]).astype(np.int32).clip(0,h-1); key=y.astype(np.int64)*w+x; order=np.lexsort((xyz[selected,2],key)); first=np.r_[True,key[order][1:]!=key[order][:-1]]; chosen=selected[order[first]]; x=np.rint(uv[chosen,0]).astype(np.int32).clip(0,w-1); y=np.rint(uv[chosen,1]).astype(np.int32).clip(0,h-1); depth[y,x]=xyz[chosen,2]; mask[y,x]=True
    return depth,mask


def render_metrics(checkpoint: Path, data_root: Path, roles: dict, eval_points_local: np.ndarray) -> dict:
    ck=torch.load(checkpoint,map_location="cuda",weights_only=False); s=ck["state_dict"]; means=s["means"].cuda(); quats=s["quats"].cuda(); scales=torch.exp(s["log_scales"]).cuda(); opac=torch.sigmoid(s["opacities_raw"]).flatten().cuda(); colors=torch.cat([s["sh0"],s["shN"]],1).cuda()
    sparse=data_root/"sparse"; sparse=sparse/"0" if (sparse/"0/cameras.bin").is_file() else sparse; cameras=read_cameras_bin(sparse/"cameras.bin"); images={im.name:im for im in read_images_bin(sparse/"images.bin").values()}
    sq=rel=0.0; valid=gt_total=0
    for index,name in enumerate(roles["eval_views"]):
        image=images[name]; camera=cameras[image.camera_id]; gt,gt_mask=project_depth(eval_points_local,image,camera); w,h=int(camera.width),int(camera.height); k=torch.tensor(camera.K(),dtype=torch.float32,device="cuda"); view=torch.eye(4,dtype=torch.float32,device="cuda"); view[:3,:3]=torch.tensor(image.R(),dtype=torch.float32,device="cuda"); view[:3,3]=torch.tensor(image.tvec,dtype=torch.float32,device="cuda")
        with torch.no_grad(): out=rasterization_2dgs(means=means,quats=quats,scales=scales,opacities=opac,colors=colors,viewmats=view[None],Ks=k[None],width=w,height=h,near_plane=.01,far_plane=500,render_mode="RGB+ED",depth_mode="expected",sh_degree=3)
        pred=out[0][0,...,3].float().cpu().numpy(); alpha=out[1][0,...,0].cpu().numpy(); mask=gt_mask&(alpha>=.5)&np.isfinite(pred)&(pred>0); delta=pred[mask]-gt[mask]; sq+=float(np.square(delta).sum()); rel+=float((np.abs(delta)/np.maximum(gt[mask],1e-3)).sum()); valid+=int(mask.sum()); gt_total+=int(gt_mask.sum())
        if (index+1)%10==0: print(f"[eval depth] {index+1}/{len(roles['eval_views'])}",flush=True)
    return {"valid_pixel_ratio":valid/max(1,gt_total),"valid_pixel_count":valid,"reference_valid_pixel_count":gt_total,"rmse_m":math.sqrt(sq/max(1,valid)),"absrel":rel/max(1,valid)}


def dsm(points: np.ndarray) -> np.ndarray:
    resolution=.5; width=int(math.ceil((AOI[2]-AOI[0])/resolution)); height=int(math.ceil((AOI[3]-AOI[1])/resolution)); output=np.full(width*height,np.nan,np.float32); x=np.floor((points[:,0]-AOI[0])/resolution).astype(int); y=np.floor((points[:,1]-AOI[1])/resolution).astype(int); keep=(x>=0)&(x<width)&(y>=0)&(y<height); key=y[keep]*width+x[keep]; order=np.argsort(key); keys=key[order]; z=points[keep,2][order]; starts=np.r_[0,np.flatnonzero(keys[1:]!=keys[:-1])+1]; output[keys[starts]]=np.maximum.reduceat(z,starts); return output.reshape(height,width)


def mesh_and_change_metrics(mesh_path: Path, cloud_path: Path, eval_points: np.ndarray, change_union) -> dict:
    mesh=o3d.io.read_triangle_mesh(str(mesh_path)); cloud=o3d.io.read_point_cloud(str(cloud_path)); method=np.asarray(cloud.points); sampled=np.asarray(mesh.sample_points_uniformly(min(2_000_000,max(100_000,len(mesh.triangles)*2))).points); tree=cKDTree(eval_points); distance,_=tree.query(sampled,k=1,workers=-1)
    method_dsm=dsm(method); eval_dsm=dsm(eval_points); h,w=method_dsm.shape; xx=AOI[0]+(np.arange(w)+.5)*.5; yy=AOI[1]+(np.arange(h)+.5)*.5; gx,gy=np.meshgrid(xx,yy); region=contains_xy(change_union,gx,gy); both=region&np.isfinite(method_dsm)&np.isfinite(eval_dsm); ghost=float(np.maximum(method_dsm[both]-eval_dsm[both],0).sum()*.25); holes=float((region&np.isfinite(eval_dsm)&~np.isfinite(method_dsm)).sum()*.25)
    return {"mesh_to_cloud_mean_m":float(distance.mean()),"mesh_to_cloud_rms_m":float(np.sqrt(np.square(distance).mean())),"distance_engine":"OPEN3D_SCIPY_FALLBACK_CLOUDCOMPARE_CLI_UNAVAILABLE","change_region_ghost_volume_m3":ghost,"change_region_hole_area_m2":holes,"mesh_polygon_count":int(len(mesh.triangles))}


def cityjson_vertices(path: Path) -> np.ndarray:
    data=json.loads(path.read_text()); transform=data.get("transform",{"scale":[1,1,1],"translate":[0,0,0]}); return np.asarray(data["vertices"])*np.asarray(transform["scale"])+np.asarray(transform["translate"])


def screenshots(run_root: Path, condition: str, report_assets: Path) -> list[str]:
    report_assets.mkdir(parents=True,exist_ok=True); cloud=np.asarray(o3d.io.read_point_cloud(str(run_root/"pointcloud/depth_fusion.ply")).voxel_down_sample(1.0).points); city=cityjson_vertices(run_root/"roofer/assembled.city.json"); paths=[]
    for suffix,points,title,color in (("mesh",cloud,f"{condition} shaded mesh proxy","#74839a"),("roofer",city,f"{condition} Roofer vertices","#df8f2b")):
        path=report_assets/f"{condition}_{suffix}.png"; fig=plt.figure(figsize=(8,6),dpi=130); ax=fig.add_subplot(111,projection="3d"); sample=points[::max(1,len(points)//150000)]; ax.scatter(sample[:,0],sample[:,1],sample[:,2],s=.15,c=color); ax.set_title(title); ax.view_init(55,-65); fig.tight_layout(); fig.savefig(path); plt.close(fig); paths.append(str(path))
    return paths


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--artifact-root",type=Path,required=True); parser.add_argument("--task-root",type=Path,required=True); args=parser.parse_args(); task=args.task_root.resolve(); prep=task/"prep"; roles=json.loads((prep/"view_roles.json").read_text()); scan=laspy.read(prep/"semantic_gt/current_eval_csf_voxel025.laz"); eval_points=np.column_stack((scan.x,scan.y,scan.z)); eval_local=eval_points-SHIFT; footprints=json.loads((args.artifact_root/"phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/shared_footprints_199.geojson").read_text()); by_id={str(f["properties"]["stable_id"]):shape(f["geometry"]) for f in footprints["features"]}; changes=json.loads((prep/"synthetic_changes.json").read_text()); region=unary_union([by_id[c["stable_id"]] for c in changes["changes"]]); names={"E3":"E3_GS_IMAGE","E4":"E4_GS_ALS_UNWEIGHTED","E5":"E5_GS_ALS_WB","E6":"E6_GS_LOD2_PLANES_DIAGNOSTIC"}; rows=[]
    for condition,run_name in names.items():
        run=task/"runs"/run_name; metrics_path=run/"metrics.json"
        if metrics_path.is_file(): metrics=json.loads(metrics_path.read_text())
        else:
            depth=render_metrics(run/"ckpt/final.pt",args.artifact_root/"phase-payloads/p0-audit/data/work/mvs/colmap_dense",roles,eval_local); geometry=mesh_and_change_metrics(run/"mesh/tsdf_mesh.ply",run/"pointcloud/depth_fusion.ply",eval_points,region); operation=json.loads((run/"control/operation.json").read_text()); ck=torch.load(run/"ckpt/final.pt",map_location="cpu",weights_only=False); metrics={"schema":"jointbuildgs.p2.e1_e6.metrics.v1","condition":condition,"depth_held_out":depth,"mesh":geometry,"operation":{"training_wall_seconds":operation["wall_seconds"],"max_vram_mib":int(operation["max_vram_mib"]),"gaussian_count":int(ck["n_prim"]),"mesh_polygon_count":geometry["mesh_polygon_count"]},"scientific_verdict":None}; metrics_path.write_text(json.dumps(metrics,indent=2)+"\n"); screenshots(run,condition,task/"report_assets")
        rows.append(metrics)
    e4=next(x for x in rows if x["condition"]=="E4"); e5=next(x for x in rows if x["condition"]=="E5"); gate=e4["mesh"]["change_region_ghost_volume_m3"]>e5["mesh"]["change_region_ghost_volume_m3"]
    lines=["# E1-E6 prior-fusion technical report","","Non-confirmatory technical-development readout. `scientific_verdict` remains null.","","| condition | depth RMSE m | AbsRel | valid ratio | mesh-cloud mean m | RMS m | ghost m3 | holes m2 | Gaussians |","|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        d=row["depth_held_out"]; m=row["mesh"]; o=row["operation"]; lines.append(f"| {row['condition']} | {d['rmse_m']:.4f} | {d['absrel']:.4f} | {d['valid_pixel_ratio']:.4f} | {m['mesh_to_cloud_mean_m']:.4f} | {m['mesh_to_cloud_rms_m']:.4f} | {m['change_region_ghost_volume_m3']:.3f} | {m['change_region_hole_area_m2']:.3f} | {o['gaussian_count']} |")
    lines.extend(["",f"E4 change-region ghost volume > E5: **{gate}** ({e4['mesh']['change_region_ghost_volume_m3']:.3f} vs {e5['mesh']['change_region_ghost_volume_m3']:.3f} m3).", "","CloudCompare CLI was unavailable in the pinned images; the receipt explicitly records the Open3D/SciPy nearest-neighbour fallback.","","Representative shaded-mesh and Roofer screenshots are under `report_assets/`."])
    (task/"report.md").write_text("\n".join(lines)+"\n"); (task/"evaluation_receipt.json").write_text(json.dumps({"schema":"jointbuildgs.p2.e1_e6.evaluation.v1","e4_ghost_gt_e5":gate,"scientific_verdict":None},indent=2)+"\n")
    if not gate: raise RuntimeError("completion gate failed: E4 ghost volume is not greater than E5")
    return 0


if __name__=="__main__": raise SystemExit(main())
