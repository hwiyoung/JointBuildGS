"""Read corrected frozen results; validate geometry contract and summarize changes."""
import argparse
import json
from pathlib import Path
import numpy as np
from scripts.phd.p2_ab_v2.b_verify import inspect_arm,sha


def corrected_checks(path):
    root=path.parent
    receipt=json.loads((root/"result.json").read_text())
    audit=receipt["geometry_adapter_audit"]
    manifest=json.loads(Path(audit["adapter_manifest_path"]).read_text())
    checks={"completed_corrected_contract":receipt["status"]=="COMPLETED_DEVELOPMENT" and receipt["geometry_contract"]=="independent_plane_hit_v1",
        "audit_sha_matches":sha(audit["path"])==audit["sha256"],
        "adapter_manifest_sha_matches":sha(audit["adapter_manifest_path"])==audit["adapter_manifest_sha256"],
        "adapter_hashes_match":manifest["output_hashes"]==receipt["geometry_adapter_hashes"]}
    checks["snapshotted_CUDA_matches"]=all(sha(root/"source_snapshot/gsplat"/k)==h for k,h in manifest["output_hashes"].items())
    result=json.loads((path/"result.json").read_text())
    frame_stats=[]
    for phase,frames in result["frames"].items():
        for frame in frames:
            m=np.load(path/frame["geometry_mass"]);d=np.load(path/frame["depth"]);a=np.load(path/frame["alpha"])
            n=np.load(path/frame["normal_render"]);present=m>=.5
            checks[f"{phase}_{frame['image_id']}_finite_valid_mass"]=bool(np.isfinite(m).all() and np.isfinite(d).all() and np.isfinite(a).all() and np.isfinite(n).all() and ((m>=0)&(m<=1.000001)).all() and (d[m==0]==0).all() and (d[present]>0).all())
            frame_stats.append(dict(phase=phase,image_id=frame["image_id"],geometry_support_pixels=int(present.sum()),
                rgb_without_geometry_pixels=int(((a>=.5)&~present).sum()),
                depth_quantiles_m=np.quantile(d[present],[0,.1,.5,.9,1]).tolist() if present.any() else None))
            if path.name=="geometry_fixed" and phase=="final":
                checks[f"fixed_readout_{frame['image_id']}_exact"]=np.array_equal(d,np.load(path/f"initial_depth_{frame['image_id']}.npy")) and np.array_equal(m,np.load(path/f"initial_geometry_mass_{frame['image_id']}.npy"))
    surfaces={}
    for phase,filename in [("initial","initial_extracted_surface.npz"),("final","extracted_surface.npz")]:
        z=np.load(path/filename);xyz=z["xyz"]
        checks[phase+"_surface_finite_aligned"]=bool(np.isfinite(xyz).all() and all(len(z[k])==len(xyz) for k in z.files))
        outside=(xyz[:,0]<110)|(xyz[:,0]>=158)|(xyz[:,1]<86)|(xyz[:,1]>=132)
        surfaces[phase]=dict(points=len(xyz),outside_fixed_P2_XY=int(outside.sum()),bbox=[xyz.min(0).tolist(),xyz.max(0).tolist()] if len(xyz) else None,
            seed_association_distance_quantiles_m=np.quantile(z["association_distance_m"],[0,.5,.9,.99,1]).tolist() if len(xyz) else None)
    return checks,frame_stats,surfaces


def main(config_path):
    cfg=json.loads(Path(config_path).read_text());output=Path("/output")
    if any(output.iterdir()):raise ValueError("empty new verification output required")
    source=Path(__file__);(output/"b_verify_corrected.py").write_bytes(source.read_bytes())
    (output/"b_verify.py").write_bytes(Path("scripts/phd/p2_ab_v2/b_verify.py").read_bytes())
    (output/"config.json").write_bytes(Path(config_path).read_bytes())
    results=[]
    for row in cfg["results"]:
        path=Path(cfg["base_root"])/row["path"]
        r=inspect_arm(path,row["label"])
        checks,frames,surfaces=corrected_checks(path)
        r["checks"].update(checks);r["pass"]=all(r["checks"].values())
        r["geometry_readout_frames"]=frames;r["geometry_readout_surfaces"]=surfaces
        results.append(r);print(json.dumps({"label":row["label"],"pass":r["pass"]}),flush=True)
    matched={}
    for name,labels in cfg["matched_initialization_groups"].items():
        selected=[r for r in results if r["label"] in labels]
        matched[name]=all(r["initial_array_hashes"]==selected[0]["initial_array_hashes"] for r in selected)
    value=dict(status="PASS" if all(r["pass"] for r in results) and all(matched.values()) else "FAIL",
        results=results,matched_initialization=matched,excluded_results=cfg["excluded_results"],
        source_sha256=sha(source),config_sha256=sha(config_path),scientific_verdict=None)
    (output/"verification.json").write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":value["status"],"results":len(results),"matched_initialization":matched}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
