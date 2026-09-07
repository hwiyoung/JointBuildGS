"""Add explicit camera metadata to new task scenes without touching RGB or poses."""
import argparse
import json
from pathlib import Path

from .prepare import sha, write_json


def run(scene):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    split_path = scene / "split_manifest.json"
    split = json.loads(split_path.read_text())
    images = {Path(view["name"]).stem: {"width": view["width"], "height": view["height"], "K": view["K"]}
              for view in split["all"]}
    write_json(scene / "jbgs_calibration.json", dict(schema="jointbuildgs.geogs.source_calibration.v1",
        source_split_manifest_sha256=sha(split_path), images=images, scientific_verdict=None,
        policy="Original image bytes and PINHOLE K retained; adapter restores native rasterizer projection principal point.",
        remaining_native_convention="point_utils and original LoD2Depth pixel-center half-offset documented in projection fixture."))
    print(json.dumps({"region":split["region"],"calibrated_views":len(images)}))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene",type=Path,required=True)
    run(parser.parse_args().scene)
