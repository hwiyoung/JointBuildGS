"""Close input preparation by validating preserved bytes and split boundaries."""
import argparse
import json
from pathlib import Path

from .prepare import sha,write_json


def run(task,output):
    if not Path("/.dockerenv").exists():raise RuntimeError("Docker required")
    rows=[]
    for region in ("P1","P2","P3"):
        root=task/"inputs"/region
        original=json.loads((root/"scene/split_manifest.json").read_text())
        revised=json.loads((root/"scene/split_manifest_da3_v2.json").read_text())
        if any(original[key]!=revised[key] for key in ("all","train","evaluation")):
            raise ValueError("DA3 revision changed the regional camera split")
        train={Path(view["name"]).stem for view in original["train"]}
        evaluation={Path(view["name"]).stem for view in original["evaluation"]}
        inferred=[Path(name).stem for batch in revised["da3_batches"] for name in batch["names"]]
        if len(inferred)!=len(train) or set(inferred)!=train or train&evaluation:
            raise ValueError("DA3 train/evaluation boundary differs")
        if any(not 3<=batch["count"]<=8 or batch["camera_center_rank"]<2 for batch in revised["da3_batches"]):
            raise ValueError("DA3 batch degeneracy gate differs")
        if {path.stem for path in (root/"prior/raw_depth").glob("*.npy")}!=train:
            raise ValueError("Structural depth membership differs from exact train split")
        validated=0
        stages={}
        for directory,filename in (("scene","camera_receipt.json"),("surface","surface_receipt.json"),
                                   ("prior","receipt.json"),("initialization","receipt.json")):
            receipt=json.loads((root/directory/filename).read_text())
            expected=receipt["config"]["sha256"] if "config" in receipt else receipt["inputs"][0]["sha256"]
            if sha(root/directory/"run_config_snapshot.json")!=expected:
                raise ValueError("Preserved executed config does not match receipt")
            for name,record in receipt["outputs"].items():
                if sha(root/directory/name)!=record["sha256"]:
                    raise ValueError(f"Completed stage output changed: {directory}/{name}")
                validated+=1
            stages[directory]={"receipt_sha256":sha(root/directory/filename),"executed_config_sha256":expected}
        init=json.loads((root/"initialization/receipt.json").read_text())
        surface=json.loads((root/"surface/surface_receipt.json").read_text())
        prior=json.loads((root/"prior/receipt.json").read_text())
        hashes={sha(root/path) for path in ("scene/sparse_lod/0/points3D.ply", "initialization/sparse_lod/0/points3D.ply", "initialization/lod2_pcd.ply")}
        if len(hashes)!=1:raise ValueError("Scene initialization and protection cloud bytes differ")
        rows.append(dict(region=region,status="GEOMETRY_CAMERA_INPUTS_READY",all_views=len(original["all"]),
            train_views=len(train),evaluation_views=len(evaluation),prior_depth_views=len(prior["rows"]),
            da3_batch_revision=2,batch_sizes=[batch["count"] for batch in revised["da3_batches"]],
            initialization=init["counts"],als_surface=surface["counts"],als_surface_area_m2=surface["area_m2"],
            protection_and_initialization_sha256=next(iter(hashes)),stage_hashes=stages,
            validated_recorded_outputs=validated,reference_accessed=False,
            source_scene=str(root/"scene"),lod_depth_path=str(root/"prior"),lod2_pcd_path=str(root/"initialization/lod2_pcd.ply")))
    receipt=dict(status="P1_P2_P3_GEOMETRY_AND_CAMERA_INPUTS_VERIFIED",scientific_verdict=None,regions=rows,
        da3_inference_completion="separate owner; this check validates DA3 membership metadata only",
        known_adaptations=["ALS scan-layer surface replaces author LoD2.","Nearest-ray visibility correction replaces source fallback.",
                          "Source principal-point metadata adapter required for regional cameras.","Balanced train-only DA3 batch revision2.",
                          "Protection points exactly equal retained initialization samples, including nonsemantic context surfaces."],
        reference_role="UAS absent from preparation; existing local frame/ALS scalar Z bridge remain uncalibrated against absolute datum.",
        source_sha256=sha(__file__))
    write_json(output,receipt)
    print(json.dumps(receipt,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    run(args.task_root,args.output)
