"""Read-only result verification and descriptive trend summaries (no verdict)."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import cv2
import torch
from src.stage2.loss.data_fitting import masked_ssim


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(8<<20),b""):h.update(block)
    return h.hexdigest()


def array_hash(value):return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def summarize_metrics(rows, key):
    values=[r[key] for r in rows if r[key]["mae"] is not None]
    n=sum(r["pixels"] for r in values)
    return {"pixels":n,"mean_view_mae":float(np.mean([r["mae"] for r in values])),
            "pixel_weighted_mae":sum(r["mae"]*r["pixels"] for r in values)/n}


def inspect_arm(path,label):
    result=json.loads((path/"result.json").read_text())
    before=np.load(path/"gaussians_initial.npz",allow_pickle=False)
    after=np.load(path/"gaussians_final.npz",allow_pickle=False)
    checks={}
    raw_sh=after["sh0"] if "sh0" in after.files else torch.load(path/"gaussians_final.pt",map_location="cpu",weights_only=True)["sh0"].numpy()
    decoded=raw_sh[:,0]*.28209479177387814+.5
    checks["raw_SH0_color_domain"]=bool(((decoded>=-1e-6)&(decoded<=1+1e-6)).all())
    checks["exported_rgb_matches_actual_SH0"]=bool(np.allclose(after["rgb"],decoded,atol=1e-6,rtol=0))
    for phase,p in [("initial",before),("final",after)]:
        count=len(p["xyz"])
        checks[phase+"_all_parameters_finite"]=all(np.isfinite(p[k]).all().item() for k in ["xyz","scales","quats","opacity","rgb"])
        checks[phase+"_aligned_parameter_counts"]=all(len(p[k])==count for k in ["scales","quats","opacity","rgb","group"])
        checks[phase+"_unit_quaternions"]=bool(np.max(np.abs(np.linalg.norm(p["quats"],axis=1)-1))<1e-5)
        checks[phase+"_positive_scales"]=bool((p["scales"]>0).all())
        checks[phase+"_decoded_color_domain"]=bool(((p["rgb"]>=0)&(p["rgb"]<=1)).all())
        checks[phase+"_opacity_domain"]=bool(((p["opacity"]>=0)&(p["opacity"]<=1)).all())
    if result["arm"]=="geometry_fixed":
        checks["fixed_geometry_exact"]=all(np.array_equal(before[k],after[k]) for k in ["xyz","scales","quats","opacity"])
    if result["arm"]=="color_fixed":checks["fixed_color_exact"]=bool(np.allclose(before["rgb"],after["rgb"],atol=1e-7,rtol=0))
    if result["arm"] in {"structured_detail","color_fixed"}:
        checks["coarse_translation_bound"]=bool(np.linalg.norm(after["coarse_displacement"],axis=1).max()<=.150002)
    unsupported=after["observation_count"]<3
    checks["unsupported_detail_zero"]=bool(np.max(np.abs(after["detail_displacement"][unsupported]),initial=0)<=1e-7)
    rows=[json.loads(s) for s in (path/"training.jsonl").read_text().splitlines()]
    checks["complete_step_log"]=len(rows)==result["fit"]["steps"] and rows[-1]["step"]==len(rows)
    checks["finite_losses_gradients"]=all(np.isfinite(r["loss"]) and all(np.isfinite(v) for v in r["gradients"].values()) for r in rows)
    gradient_summary={k:{"positive_steps":sum(r["gradients"].get(k,0)>0 for r in rows),
                         "median_norm":float(np.median([r["gradients"].get(k,0) for r in rows]))} for k in rows[0]["gradients"]}
    trends=[]
    for offset in range(0,len(rows),256):
        window=rows[offset:offset+256]
        trends.append({"end_step":window[-1]["step"],"mean_photo":float(np.mean([r["photo"] for r in window])),
                       "mean_total":float(np.mean([r["loss"] for r in window]))})
    evaluation_trend=[{"step":r["step"],"views":r["evaluation_development_trend"]} for r in rows if "evaluation_development_trend" in r]
    mvc_rows=[r for r in rows if "mvc_valid_pixels" in r]
    mvc_execution={"called_steps":len(mvc_rows),"nonzero_loss_steps":sum(r["multiview"]>0 for r in mvc_rows),
        "at_least32_valid_pixels_steps":sum(r["mvc_valid_pixels"]>=32 for r in mvc_rows),
        "valid_pixels_sum":sum(r["mvc_valid_pixels"] for r in mvc_rows),
        "valid_pixels_median":float(np.median([r["mvc_valid_pixels"] for r in mvc_rows])) if mvc_rows else None,
        "logging_phase":"all2048steps in training.jsonl; MVC displays1,5,... while console displays64,128,..."}
    initial={key:summarize_metrics(result["initial_metrics"],key) for key in ["fixed_initial_support","conditional_observation_support","whole_valid_crop"]}
    final={key:summarize_metrics(result["final_metrics"],key) for key in initial}
    ssim_rows=[]
    with torch.no_grad():
        for frame in result["frames"]["final"]:
            iid=frame["image_id"]
            def rgb(name):return torch.tensor(cv2.cvtColor(cv2.imread(str(path/name)),cv2.COLOR_BGR2RGB),device="cuda",dtype=torch.float32)/255
            target=rgb(frame["target"])
            mask=torch.tensor(cv2.imread(str(path/f"observation_support_{iid}.png"),cv2.IMREAD_GRAYSCALE)>0,device="cuda")
            if not bool(mask.any()):continue
            a=masked_ssim(rgb(f"initial_rgb_{iid}.png"),target,mask)
            b=masked_ssim(rgb(frame["rgb"]),target,mask)
            ssim_rows.append({"image_id":iid,"pixels":int(mask.sum()),"initial":float(a),"final":float(b)})
    return {"label":label,"path":str(path),"checks":checks,"pass":all(checks.values()),
            "seed_count":len(after["xyz"]),"initial_array_hashes":{k:array_hash(before[k]) for k in ["xyz","scales","quats","opacity","rgb","group"]},
            "state_sha256":{"initial":sha(path/"gaussians_initial.npz"),"final":sha(path/"gaussians_final.npz")},
            "geometry_displacement_rms_m":float(np.sqrt(np.mean(np.sum((after["xyz"]-before["xyz"])**2,axis=1)))),
            "detail_rms_m":float(np.sqrt(np.mean(np.sum(after["detail_displacement"]**2,axis=1)))),
            "coarse_rms_m":float(np.sqrt(np.mean(np.sum(after["coarse_displacement"]**2,axis=1)))),
            "detail_nonzero_1mm":int((np.linalg.norm(after["detail_displacement"],axis=1)>.001).sum()),
            "runtime_seconds":result["fit"]["runtime_seconds"],"gradients":gradient_summary,
            "multiview_execution":mvc_execution,
            "training_windows":trends,"evaluation_trend":evaluation_trend,"initial_appearance":initial,"final_appearance":final,
            "surface_initial_points":len(np.load(path/"initial_extracted_surface.npz")["xyz"]),
            "surface_final_points":len(np.load(path/"extracted_surface.npz")["xyz"]),
            "source_support_removed_pixels":sum(r["removed_initial_pixels"] for r in result["final_metrics"]),
            "source_support_added_pixels":sum(r["added_pixels"] for r in result["final_metrics"]),
            "surface_depth_change_mean_of_view_means_m":float(np.mean([r["surface_depth_abs_change_mean_m"] for r in result["final_metrics"] if r["surface_depth_abs_change_mean_m"] is not None])),
            "conditional_observation_support_ssim_png8bit":{"views":ssim_rows,
                "initial_mean_view":float(np.mean([r["initial"] for r in ssim_rows])),
                "final_mean_view":float(np.mean([r["final"] for r in ssim_rows])),
                "definition":"existing masked_ssim11 on saved clamped/quantized8-bit RGB; no reference geometry; method-dependent mask across different G0"},
            "scientific_verdict":None}


def main(config_path):
    source_before=sha(__file__)
    Path("/output/b_verify_source.py").write_bytes(Path(__file__).read_bytes())
    Path("/output/config.json").write_bytes(Path(config_path).read_bytes())
    cfg=json.loads(Path(config_path).read_text())
    results=[inspect_arm(Path(cfg["base_root"])/r["path"],r["label"]) for r in cfg["results"]]
    shared={}
    for group,labels in cfg["matched_initialization_groups"].items():
        selected=[r for r in results if r["label"] in labels]
        shared[group]=all(r["initial_array_hashes"]==selected[0]["initial_array_hashes"] for r in selected)
    output={"status":"PASS" if all(r["pass"] for r in results) and all(shared.values()) else "FAIL",
            "results":results,"matched_initialization":shared,"excluded_results":cfg["excluded_results"],
            "input_config_sha256":sha(config_path),"source_sha256":source_before,
            "source_unchanged_during_verification":source_before==sha(__file__),
            "versions":{"torch":torch.__version__,"cv2":cv2.__version__,"numpy":np.__version__},"scientific_verdict":None}
    if not output["source_unchanged_during_verification"]:raise RuntimeError("verification source changed during execution")
    Path("/output/verification.json").write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":output["status"],"result_count":len(results),"matched_initialization":shared}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
