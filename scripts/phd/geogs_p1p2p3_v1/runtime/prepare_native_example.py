"""Validate and extract the immutable example into separate input/reference roots."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile

import numpy as np
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--archive", required=True, type=Path)
parser.add_argument("--output-root", required=True, type=Path)
parser.add_argument("--config", required=True, type=Path)
parser.add_argument("--source-root", required=True, type=Path)
parser.add_argument("--validate-extracted", action="store_true")
args = parser.parse_args()
config = json.loads(args.config.read_text())
digest = hashlib.sha256()
with args.archive.open("rb") as source:
    while chunk := source.read(8 * 1024 * 1024):
        digest.update(chunk)
assert digest.hexdigest() == config["archive_sha256"]
assert args.archive.stat().st_size == config["archive_bytes"]
if args.validate_extracted:
    assert args.output_root.is_dir()
    assert not (args.output_root / "input_manifest.json").exists()
else:
    args.output_root.mkdir(parents=True, exist_ok=False)
scene = args.output_root / "scene"
reference = args.output_root / "evaluation_reference"
files = []
with zipfile.ZipFile(args.archive) as archive:
    for member in archive.infolist():
        if member.is_dir():
            continue
        path = PurePosixPath(member.filename)
        if path.parts[0] != "example_scene" or ".." in path.parts or path.is_absolute():
            raise ValueError(f"Unexpected archive path: {path}")
        relative = Path(*path.parts[1:])
        if relative.parts[0] == "ground_truth":
            output = reference.joinpath(*relative.parts[1:])
            role = "evaluation_only"
        elif relative.parts[0] in {"images", "sparse", "sparse_lod", "lod2_prior", "da3_prior", "lod2_pcd.ply"}:
            output = scene / relative
            role = "native_scene_input"
        else:
            raise ValueError(f"Unclassified example member: {path}")
        output.parent.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256()
        if args.validate_extracted:
            with archive.open(member) as src:
                while chunk := src.read(8 * 1024 * 1024):
                    sha.update(chunk)
            actual = hashlib.sha256()
            with output.open("rb") as existing:
                while chunk := existing.read(8 * 1024 * 1024):
                    actual.update(chunk)
            assert actual.hexdigest() == sha.hexdigest(), output
        else:
            with archive.open(member) as src, output.open("xb") as dst:
                while chunk := src.read(8 * 1024 * 1024):
                    dst.write(chunk)
                    sha.update(chunk)
        files.append({"path": str(output.relative_to(args.output_root)), "role": role,
                      "bytes": output.stat().st_size, "sha256": sha.hexdigest()})
sys.path.insert(0, str(args.source_root))
from scene.colmap_loader import read_extrinsics_binary, read_intrinsics_binary, read_extrinsics_text, read_intrinsics_text
views = {}
for directory in ("sparse", "sparse_lod"):
    sparse = scene / directory / "0"
    if (sparse / "images.bin").is_file():
        extrinsics = read_extrinsics_binary(sparse / "images.bin")
        intrinsics = read_intrinsics_binary(sparse / "cameras.bin")
    else:
        extrinsics = read_extrinsics_text(sparse / "images.txt")
        intrinsics = read_intrinsics_text(sparse / "cameras.txt")
    views[directory] = {value.name: value for value in extrinsics.values()}
    assert len(extrinsics) == config["train_views"] + config["test_views"]
    assert all(camera.model in {"PINHOLE", "SIMPLE_PINHOLE"} for camera in intrinsics.values())
for name, view in views["sparse"].items():
    other = views["sparse_lod"][name]
    assert np.array_equal(view.qvec, other.qvec) and np.array_equal(view.tvec, other.tvec)
names = sorted(views["sparse"])
assert all((scene / directory / "0/points3D.ply").is_file() for directory in ("sparse", "sparse_lod"))
images = {name: Image.open(scene / "images" / name).size for name in names}
assert len(set(images.values())) == 1
depths = {}
for prior in ("lod2_prior", "da3_prior"):
    depths[prior] = {}
    for name in names:
        array = np.load(scene / prior / "raw_depth" / (Path(name).stem + ".npy"), mmap_mode="r")
        valid = np.isfinite(array) & (array > 0)
        assert valid.any()
        depths[prior][name] = {"shape": list(array.shape), "valid_fraction": float(valid.mean()),
                               "min_valid": float(array[valid].min()), "max_valid": float(array[valid].max())}
manifest = {"task_id": config["task_id"], "scientific_verdict": None,
            "archive_sha256": config["archive_sha256"], "status": "PASS_INPUT_CONTRACT",
            "scene_reference_separated": True, "files": files,
            "train_images": [name for i, name in enumerate(names) if i % 8 != 0],
            "test_images": [name for i, name in enumerate(names) if i % 8 == 0],
            "image_dimensions": images, "depth_inventory": depths,
            "coordinate_frame": config["coordinate_frame"],
            "da3_evaluation_view_participation": config["da3_evaluation_view_participation"]}
(args.output_root / "input_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"status": manifest["status"], "files": len(files), "train": len(manifest["train_images"]),
                  "test": len(manifest["test_images"]), "manifest": str(args.output_root / "input_manifest.json")}))
