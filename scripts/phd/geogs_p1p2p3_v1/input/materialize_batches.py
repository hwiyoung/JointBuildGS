"""Materialize this task's new DA3 batch links for isolated single-batch mounts."""
import argparse
import os
from pathlib import Path
import json

from .prepare import sha, write_json


def run(scene):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    scene = scene.resolve()
    if "PHD-GEOGS-P1P2P3-v1/inputs/" not in str(scene):
        raise ValueError("Only this task's new scene inputs may be materialized")
    destination = scene / "batch_materialization_receipt.json"
    if destination.exists():
        raise FileExistsError(destination)
    manifest = scene / "split_manifest.json"
    split = json.loads(manifest.read_text())
    train = {view["name"]: view for view in split["train"]}
    evaluation = {view["name"] for view in split["evaluation"]}
    records = []
    for batch in split["da3_batches"]:
        folder = scene / "da3_batches" / f"batch_{batch['batch_id']:03d}" / "images"
        for name in batch["names"]:
            if name not in train or name in evaluation:
                raise ValueError("DA3 split boundary violated")
            path = folder / name
            source = scene / "images" / name
            expected = train[name]["sha256"]
            if not path.is_symlink() or path.resolve() != source or sha(source) != expected:
                raise ValueError(f"Unexpected batch input state: {path}")
            temporary = path.with_suffix(path.suffix + ".materializing")
            os.link(source, temporary)
            previous = os.readlink(path)
            os.replace(temporary, path)
            if path.is_symlink() or sha(path) != expected:
                raise ValueError("Hardlink materialization failed")
            records.append(dict(path=str(path), previous_symlink=previous, sha256=expected,
                                inode_equal=path.stat().st_ino == source.stat().st_ino))
    write_json(destination, dict(status="TRAIN_ONLY_BATCH_FILES_SELF_CONTAINED", records=records,
               original_split_manifest_sha256=sha(manifest), scientific_verdict=None,
               operation="Materialize same-byte hardlinks in new task inputs; no source RGB content changed.",
               source_sha256=sha(__file__)))
    print(json.dumps({"region": split["region"], "materialized": len(records)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", required=True, type=Path)
    run(parser.parse_args().scene)
