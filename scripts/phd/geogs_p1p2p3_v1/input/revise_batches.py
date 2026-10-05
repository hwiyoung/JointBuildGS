"""Add balanced, nondegenerate train-only DA3 batches after a technical failure."""
import argparse
import json
import math
import os
from pathlib import Path
import numpy as np

from .prepare import read_pose_metadata, write_colmap, write_json, sha,record


def run(scene,policy_path):
    if not Path("/.dockerenv").exists():raise RuntimeError("Docker required")
    policy=json.loads(policy_path.read_text())
    old_path=scene/"split_manifest.json"
    split=json.loads(old_path.read_text())
    ordered=sorted(split["train"],key=lambda view:Path(view["name"]).stem)
    evaluation={view["name"] for view in split["evaluation"]}
    count=math.ceil(len(ordered)/policy["da3"]["max_batch_views"])
    groups=np.array_split(np.arange(len(ordered)),count)
    root=scene/"da3_batches_v2"
    root.mkdir(exist_ok=False)
    cameras,poses=read_pose_metadata(scene)
    batches=[]
    for index,group in enumerate(groups):
        views=[ordered[int(i)] for i in group]
        if len(views)<policy["da3"]["min_batch_views"]:raise ValueError("Batch smaller than configured minimum")
        centers=np.array([-np.asarray(view["t"])@np.asarray(view["R"]) for view in views])
        centered=centers-centers.mean(axis=0)
        singular=np.linalg.svd(centered,compute_uv=False)
        tolerance=float(singular[0]*max(centered.shape)*np.finfo(centered.dtype).eps)
        rank=int((singular>tolerance).sum())
        if rank<policy["da3"]["source_camera_center_rank_min"]:raise ValueError("DA3 source camera-center batch is degenerate")
        folder=root/f"batch_{index:03d}"
        write_colmap(folder/"sparse/0",cameras,[poses[view["image_id"]] for view in views],empty_points=True)
        (folder/"images").mkdir()
        for view in views:
            if view["name"] in evaluation:raise ValueError("Evaluation membership leaked into DA3 batch")
            source=scene/"images"/view["name"]
            if sha(source)!=view["sha256"]:raise ValueError("Frozen RGB source changed")
            os.link(source,folder/"images"/view["name"])
        batches.append(dict(batch_id=index,scene=str(folder),count=len(views),image_ids=[view["image_id"] for view in views],
            names=[view["name"] for view in views],camera_center_singular_values_m=singular.tolist(),
            camera_center_rank=rank,camera_center_rank_tolerance=tolerance))
    split["da3_batches"]=batches
    split["da3_policy"]="Balanced contiguous numpy.array_split into ceil(train_count/8) groups; train-only RGB; minimum3 views and centered camera positions rank>=2."
    split["da3_batch_revision"]=2
    split["original_split_manifest"]=record(old_path)
    split["da3_revision_policy"]=record(policy_path)
    destination=scene/"split_manifest_da3_v2.json"
    write_json(destination,split)
    # Both requested resolver names identify the exact same immutable bytes.
    os.link(destination,scene/"split_manifest_v2.json")
    (scene/"da3_batch_revision_v2.json").write_bytes(policy_path.read_bytes())
    write_json(scene/"da3_batch_revision_receipt_v2.json",dict(status="BALANCED_TRAIN_ONLY_DA3_BATCHES_PREPARED",scientific_verdict=None,
        policy=record(policy_path),old_split=record(old_path),new_split=record(destination),batch_sizes=[batch["count"] for batch in batches],
        minimum_camera_center_rank=min(batch["camera_center_rank"] for batch in batches),
        original_batches_preserved=True,old_da3_depth_results_reused=False,source_sha256=sha(__file__)))
    print(json.dumps({"region":split["region"],"batch_sizes":[batch["count"] for batch in batches],"minimum_rank":min(batch["camera_center_rank"] for batch in batches)}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene",required=True,type=Path)
    parser.add_argument("--policy",required=True,type=Path)
    args=parser.parse_args()
    run(args.scene,args.policy)
