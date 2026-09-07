"""Bind completed official-derived initial points into new task scene metadata."""
import argparse
from pathlib import Path
import json
import shutil

from .prepare import record,sha,write_json


def run(root):
    if not Path("/.dockerenv").exists():raise RuntimeError("Docker required")
    if "PHD-GEOGS-P1P2P3-v1/inputs/" not in str(root.resolve()):raise ValueError("Task scope mismatch")
    initial=root/"initialization"
    receipt=json.loads((initial/"receipt.json").read_text())
    if receipt["status"]!="OFFICIAL_INITIALIZATION_WITH_EXPLICIT_VISIBLE_RAY_CORRECTION":raise ValueError("Initialization incomplete")
    target=root/"scene/sparse_lod/0"
    camera_before={name:sha(target/name) for name in ("images.bin","images.txt","cameras.bin","cameras.txt")}
    copies={}
    for name in ("points3D.ply","points3D.txt"):
        destination=target/name
        if destination.exists():raise FileExistsError(destination)
        source=initial/"sparse_lod/0"/name
        expected=receipt["outputs"]["sparse_lod/0/"+name]["sha256"]
        if sha(source)!=expected:raise ValueError("Initialization source changed after completion")
        shutil.copyfile(source,destination)
        copies[name]=record(destination,expected)
    if any(sha(target/name)!=value for name,value in camera_before.items()):raise ValueError("Frozen camera metadata changed")
    write_json(root/"scene/initialization_binding_receipt.json",dict(status="INITIALIZATION_BOUND_CAMERA_METADATA_UNCHANGED",
        scientific_verdict=None,initialization_receipt=record(initial/"receipt.json"),files=copies,
        protection_ply=record(initial/"lod2_pcd.ply"),camera_sha256=camera_before,
        reason="Native readers ignore points2D observations; full source poses retain native train/eval split without evaluation RGB use.",source_sha256=sha(__file__)))
    print(json.dumps({"status":"INITIALIZATION_BOUND","region":root.name,"count":receipt["counts"]["retained"]}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-root",type=Path,required=True)
    run(parser.parse_args().region_root)
