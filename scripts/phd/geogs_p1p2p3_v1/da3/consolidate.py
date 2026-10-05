"""Seal one complete train-only DA3 run as a new regional input package."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil

import numpy as np
from acquire_weights import MODEL, REVISION, WEIGHT_SHA256, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists() or Path("/artifacts").exists():
        raise RuntimeError("Use isolated Docker mounts")
    if any(args.output.iterdir()):
        raise FileExistsError("Final input package must be new and empty")
    source = json.loads((args.generated / "receipt.json").read_text())
    split = json.loads(args.split.read_text())
    if source["status"] != "PASS_TRAIN_ONLY_DEPTH_GENERATION" or not source["full_region"]:
        raise ValueError("A successfully completed whole-region run is required")
    if source["model"] != MODEL or source["model_revision"] != REVISION or source["model_sha256"] != WEIGHT_SHA256:
        raise ValueError("Model identity changed")
    if source["region"] != split["region"] or source["split_sha256"] != sha(args.split):
        raise ValueError("Regional split identity changed")
    expected = {Path(item["name"]).stem: item for item in split["train"]}
    excluded = {Path(item["name"]).stem for item in split["evaluation"]}
    generated = {path.stem for path in (args.generated / "raw_depth_upsampled").glob("*.npy")}
    if generated != set(expected) or generated & excluded:
        raise ValueError("Final depth membership must contain every train image and no evaluation images")
    records = {}
    for batch in source["batches"]:
        for name in batch["names"]:
            if Path(name).stem in records:
                raise ValueError("Duplicate batch membership")
            records[Path(name).stem] = batch
    if set(records) != set(expected):
        raise ValueError("Inference receipts do not cover exact training membership")
    for folder in ("raw_depth", "raw_depth_inference", "confidence", "confidence_inference"):
        (args.output / folder).mkdir()
    ledger = []
    for stem in sorted(expected):
        view = expected[stem]
        batch = records[stem]
        files = {}
        for original, final in (("raw_depth_upsampled", "raw_depth"), ("raw_depth", "raw_depth_inference"),
                                ("confidence_upsampled", "confidence"), ("confidence", "confidence_inference")):
            path = args.generated / original / f"{stem}.npy"
            digest = sha(path)
            if batch["files"][f"{original}/{stem}.npy"] != digest:
                raise ValueError("Generated data changed since inference receipt")
            array = np.load(path, allow_pickle=False)
            if array.dtype != np.float32 or array.ndim != 2:
                raise ValueError("Expected original floating-point depth/confidence array")
            if final in ("raw_depth", "confidence") and array.shape != (view["height"], view["width"]):
                raise ValueError("Depth map is not at original image resolution")
            target = args.output / final / path.name
            try:
                os.link(path, target)
                mode = "hardlink"
            except OSError:
                shutil.copyfile(path, target)
                mode = "copy"
            if sha(target) != digest:
                raise ValueError("Final package copy failed byte validation")
            files[f"{final}/{path.name}"] = dict(sha256=digest, shape=list(array.shape), bytes=target.stat().st_size,
                                                source=f"{original}/{path.name}", transfer=mode)
        ledger.append(dict(image_id=view["image_id"], camera_id=view["camera_id"], name=view["name"],
                           rgb_sha256=view["sha256"], batch_id=batch["batch_id"], files=files))
    shutil.copyfile(args.generated / "receipt.json", args.output / "inference_receipt.json")
    for name, key in (("config_executed.json", "config_sha256"), ("batch_policy_executed.json", "batch_policy_sha256")):
        if sha(args.generated / name) != source[key]:
            raise ValueError("Executed configuration does not match inference receipt")
        shutil.copyfile(args.generated / name, args.output / name)
    receipt = dict(schema="jointbuildgs.geogs.da3.regional_input.v1", task_id=source["task_id"],
                   scientific_verdict=None, region=source["region"], status="PASS_SEALED_TRAIN_ONLY_DA3_INPUT",
                   model=MODEL, model_revision=REVISION, model_sha256=WEIGHT_SHA256,
                   source_commit=source["source_commit"], official_script_sha256=source["official_script_sha256"],
                   inference_receipt_sha256=sha(args.generated / "receipt.json"), split_sha256=sha(args.split),
                   config_sha256=source["config_sha256"], policy=source["policy"],
                   batch_policy_sha256=source["batch_policy_sha256"],
                   training_depth_directory="raw_depth", training_depth_resolution="original",
                   native_inference_directory="raw_depth_inference", depth_units="metres",
                   upsample="official GeoGS cv2.INTER_CUBIC", train_count=len(expected), evaluation_depth_count=0,
                   reference_accessed=False, evaluation_rgb_accessed=False, images=ledger)
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"region": source["region"], "status": receipt["status"], "maps": len(expected),
                      "receipt_sha256": sha(args.output / "receipt.json")}), flush=True)


if __name__ == "__main__":
    main()
