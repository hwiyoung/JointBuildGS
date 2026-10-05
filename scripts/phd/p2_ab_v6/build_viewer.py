"""Export unmodified RGB/geometry diagnostics and worked actual A-to-B cases."""
import argparse
import json
from pathlib import Path
import shutil
import cv2
import numpy as np
from scripts.phd.p2_ab_v4.build_qualitative_viewer import sha, pixel_metrics


def main(root,evaluation,output):
    output.mkdir(parents=True,exist_ok=False)
    result=json.loads((root/"result.json").read_text());cfg=json.loads((root/"config.json").read_text())
    areceipt=json.loads((Path(cfg["a_root"])/"technical_receipt.json").read_text())
    geometry=json.loads(evaluation.read_text());geometries={r["arm"]:r for r in geometry["arms"]}
    aliases={"initial":"mvs_initial","fixed_color":"mvs_sh3_uniform","dynamic_surface_guard":"mvs_sh3_residual_weighted"}
    labels={"initial":"MVS 초기","fixed_color":"기하 고정 · 색 학습","rgb_residual":"RGB 잔차 · 기하 갱신",
        "static_evidence":"고정 관측 마스크","dynamic_evidence":"동적 관측 마스크","dynamic_surface_guard":"동적 마스크 + 표면 검사"}
    specs=[]
    for name in ["initial"]+[r["arm"] for r in result["arms"]]:
        specs.append((aliases.get(name,name),labels[name],name,"rgb"))
        for kind,title in [("normal","법선"),("mask","A 관측 위치" if name=="initial" else "최종 갱신 위치")]:specs.append((name+"_"+kind,labels[name]+" · "+title,name,kind))
        if name!="initial":specs.append((name+"_depth_change",labels[name]+" · 깊이 변화",name,"depth_change"))
    models=[dict(id=i,label=label,source="MVS",phase="initial" if name=="initial" else "final",kind=kind) for i,label,name,kind in specs]
    inputs={};outputs={}
    def copy(source,target):
        dest=output/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        inputs[str(source)]=sha(source);outputs[target]=sha(dest)
        if outputs[target]!=inputs[str(source)]:raise ValueError("copy changed actual image")
    rows=[];summaries={}
    for row in result["initial"]["views"]:
        vid=row["image_id"];target=cv2.cvtColor(cv2.imread(str(root/"initial"/f"target_{vid}.png")),cv2.COLOR_BGR2RGB)
        maskpath=Path(cfg["common_viewer"])/"images"/str(vid)/"common_support.png"
        mask=cv2.imread(str(maskpath),0)>0
        targetname=f"images/{vid}/target.png";copy(root/"initial"/f"target_{vid}.png",targetname)
        copy(maskpath,f"images/{vid}/common_support.png")
        images={};metrics={}
        for identifier,label,name,kind in specs:
            dest=f"images/{vid}/{identifier}.png";copy(root/name/f"{kind}_{vid}.png",dest);images[identifier]=dest
            if kind=="rgb":
                image=cv2.cvtColor(cv2.imread(str(root/name/f"rgb_{vid}.png")),cv2.COLOR_BGR2RGB)
                mass=np.load(root/name/f"geometry_mass_{vid}.npy")
                metrics[identifier]=pixel_metrics(image,target,mask,mass)
            else:metrics[identifier]={"mae":None,"psnr_db":None,"pixels":int(mask.sum())}
        rows.append(dict(image_id=vid,width=target.shape[1],height=target.shape[0],target=targetname,
            support=f"images/{vid}/common_support.png",common_pixels=int(mask.sum()),images=images,metrics=metrics))
    for identifier,label,name,kind in specs:
        if kind=="rgb":
            src=result["initial"] if name=="initial" else next(x["appearance"] for x in result["arms"] if x["arm"]==name)
            summaries[identifier]={k:src[k] for k in ("pixels","mae","psnr_db")}
    data=dict(default_view_id=333,models=models,views=rows,summary=summaries,
        scope=dict(A="Actual P2 raw-image offset evidence; absolute two-source error calibration incomplete",
            B="Same MVS G0; normal-only geometry updates, SH3 color; no new topology/densification",
            guard="Remaining observational normal-error budget propagated to sampled training rays; final rendered depth/presence checked",
            evaluation="All 11 fixed development views; same 5150892 pixels; UAS used only after fitting"),scientific_verdict=None)
    (output/"data.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    handoff=dict(np.load(Path(cfg["a_root"])/"handoff_mvs.npz"));profiles=dict(np.load(Path(cfg["a_root"])/"mvs_profiles.npz"))
    seed=dict(np.load(Path(cfg["source_run"])/"mvs_source_seeds.npz"));final=np.load(root/"dynamic_surface_guard/gaussians_final.npz")["normal_offset_m"]
    cases=[]
    eval_views=[v for v in json.loads((root/"views.json").read_text())["views"] if v["role"]=="eval"]
    for anchor in np.unique(handoff["anchor_id"][handoff["observable"]]):
        indices=np.flatnonzero(handoff["observable"]&(handoff["anchor_id"]==anchor));i=indices[0]
        projections=[]
        for v in eval_views:
            V=np.asarray(v["viewmat"]);K=np.asarray(v["K"]);cam=seed["xyz"][i]@V[:3,:3].T+V[:3,3];p=cam@K.T
            if cam[2]<=0:continue
            u,y=p[:2]/p[2]
            if 0<=u<v["width"] and 0<=y<v["height"]:
                dep=np.load(root/"initial"/f"depth_{v['image_id']}.npy",mmap_mode="r")
                gap=abs(float(dep[int(y),int(u)])-cam[2])
                projections.append(dict(image_id=v["image_id"],u=float(u),v=float(y),gap=float(gap)))
        projection=min(projections,key=lambda p:p["gap"]) if projections else None
        is_eligible=bool(handoff["allowed_low_m"][i]-1e-6<=final[i]<=handoff["allowed_high_m"][i]+1e-6)
        cases.append(dict(seed_id=int(seed["seed_id"][i]),xyz=seed["xyz"][i].astype(float).tolist(),projection=projection,conditional_eligible=is_eligible,
            observation=[float(handoff[k][i]) for k in ("observation_low_m","observation_high_m")],
            allowed=[float(handoff[k][i]) for k in ("allowed_low_m","allowed_high_m")],
            cost=profiles["cost"][:,anchor].astype(float).tolist(),final_offset=float(final[i]),initial_eligible=bool(handoff["initial_eligible"][i])))
    erows=[dict(label=labels[r["arm"]],mae=r["appearance"]["mae"],psnr_db=r["appearance"]["psnr_db"],changed=r["changed_gt1mm"],
        violations=r["protected_surface"]["violations"],unresolved=r["unresolved_count"],changed_outside_allowable=r["changed_outside_allowable_count"],
        p90_m=geometries[r["arm"]]["final"]["prediction_to_reference"]["p90_m"]) for r in result["arms"]]
    evidence=dict(offsets=profiles["offsets_m"].astype(float).tolist(),epsilon_m=cfg["epsilon_m"],cases=cases,results=erows,
        summary=f"{areceipt['anchors']:,}개 검사 위치 중 {areceipt['observable_anchors']:,}개에서 두 사진 그룹의 위치 범위를 얻었습니다. 전체 266,361개 Gaussian 중 {areceipt['observable_gaussians']:,}개에 전달했습니다. 이 제한된 관측 범위와 절대오차 미보정 상태를 유지합니다.")
    (output/"evidence.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    for p in Path("src/apps/p2_ab_inspector_v6").iterdir():copy(p,p.name)
    for file in ("data.json","evidence.json"):outputs[file]=sha(output/file)
    receipt=dict(status="ACTUAL_RGB_AND_SURFACE_DIAGNOSTICS_EXPORTED",input_hashes=inputs,output_sha256=outputs,
        source_hashes={str(Path(__file__)):sha(__file__)},models=len(models),views=len(rows),scientific_verdict=None)
    (output/"technical_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(dict(models=len(models),views=len(rows),cases=len(cases))))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--b-root",type=Path,required=True);parser.add_argument("--evaluation",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();main(args.b_root,args.evaluation,args.output)
