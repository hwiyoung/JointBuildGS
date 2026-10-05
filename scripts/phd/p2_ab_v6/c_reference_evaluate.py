"""Reference-only v6 evaluation, launched after B completes. Never imported by fitting."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from scipy.spatial import cKDTree
from src.phd.p2_ab_v2.geometry_evaluation import GeometryEvaluator
from src.phd.p2_ab_v2.evaluation import paired_detail_metrics, rasterize_median, detail_residual, common_detail_fields
from scripts.phd.p2_ab_v4.b_mvs_appearance_probe import sha, write


def main(root,output):
    start=time.monotonic();output.mkdir(parents=True,exist_ok=False)
    result=json.loads((root/"result.json").read_text());cfg=json.loads((root/"config.json").read_text())
    reference_root=Path("/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-COMMON-v2/evaluation_v2")
    reference_path=reference_root/"evaluation_reference.npz"
    reference=np.load(reference_path)["uas_xyz"].astype(np.float64)
    common=Path("/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-COMMON-v1/sample_manifest.json")
    domain=json.loads(common.read_text())["domain"]
    bounds=np.array([[domain["x"][0],domain["y"][0]],[domain["x"][1],domain["y"][1]]])
    inside=lambda x:((x[:,:2]>=bounds[0])&(x[:,:2]<bounds[1])).all(1)
    reference=reference[inside(reference)];evaluator=GeometryEvaluator(reference,workers=4)
    seed=dict(np.load(Path(cfg["source_run"])/"mvs_source_seeds.npz"))
    handoff=dict(np.load(Path(cfg["a_root"])/"handoff_mvs.npz"))
    # Fixed observational region membership from A, before seeing UAS errors.
    tree=cKDTree(seed["xyz"])
    def a_region(points):
        distance,ids=tree.query(points,workers=4)
        return (distance<=.75)&handoff["observable"][ids]
    roi_reference=reference[a_region(reference)]
    roi_eval=GeometryEvaluator(roi_reference,workers=4)
    initial=np.load(root/"initial/extracted_surface.npz")["xyz"].astype(np.float64);initial=initial[inside(initial)]
    im=evaluator.measure(initial);irm=roi_eval.measure(initial[a_region(initial)])
    spacings=(.25,.5,1.);fields={s:{} for s in spacings}
    ref_fields={s:detail_residual(rasterize_median(reference,bounds,s)[0]) for s in spacings}
    rows=[];inputs={str(p):sha(p) for p in [root/"result.json",root/"config.json",reference_path,common,root/"initial/extracted_surface.npz",Path(cfg["a_root"])/"handoff_mvs.npz"]}
    for arm in result["arms"]:
        name=arm["arm"];path=root/name/"extracted_surface.npz";inputs[str(path)]=sha(path)
        points=np.load(path)["xyz"].astype(np.float64);points=points[inside(points)]
        metric=evaluator.measure(points);roi_metric=roi_eval.measure(points[a_region(points)])
        detail=paired_detail_metrics(initial,points,reference,bounds,spacings)
        rows.append(dict(arm=name,initial=im,final=metric,initial_A_region=irm,final_A_region=roi_metric,detail=detail))
        for s in spacings:fields[s][name]={"initial":detail_residual(rasterize_median(initial,bounds,s)[0]),"final":detail_residual(rasterize_median(points,bounds,s)[0])}
        print(json.dumps(dict(arm=name,p90_m=metric["prediction_to_reference"]["p90_m"],A_region_p90_m=roi_metric["prediction_to_reference"]["p90_m"])),flush=True)
    payload=dict(status="REFERENCE_ONLY_DEVELOPMENT_EVALUATION_COMPLETE",arms=rows,reference_points=len(reference),
        A_region_reference_points=len(roi_reference),cross_arm_detail=[dict(spacing_m=s,**common_detail_fields(fields[s],ref_fields[s])) for s in spacings],
        input_hashes=inputs,source_hashes={str(Path(__file__)):sha(__file__)},elapsed_seconds=time.monotonic()-start,
        limits=["UAS datum/epoch and measurement precision are not newly calibrated.","A region selected by source position and observation mask, not reference errors.","2.5D height residual is a detail diagnostic, not a window/ridge semantic restoration verdict."],scientific_verdict=None)
    if any(sha(p)!=h for p,h in inputs.items()):raise ValueError("evaluation input changed")
    write(output/"evaluation.json",payload)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--b-root",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();main(args.b_root,args.output)
