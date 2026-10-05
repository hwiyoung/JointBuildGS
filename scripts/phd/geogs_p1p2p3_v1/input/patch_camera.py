"""Install the explicit camera adapter in a task-owned instrumented copy only."""
import argparse
from pathlib import Path
import shutil


def patch(source):
    if "GeoGS-state" not in str(source.resolve()):
        raise ValueError("Camera patch is restricted to the task-owned instrumented source")
    path = source / "utils/camera_utils.py"
    content = path.read_text()
    old = '    return Camera(colmap_id=cam_info.uid, R=cam_info.R, T=cam_info.T, '
    tail = '                  image_name=cam_info.image_name, uid=id, data_device=args.data_device)'
    if content.count(old) != 1 or content.count(tail) != 1 or "maybe_calibrate_camera" in content:
        raise ValueError("Unexpected upstream camera constructor; patch refused")
    adapter = source / "jbgs_camera_adapter.py"
    if adapter.exists():
        raise FileExistsError(adapter)
    shutil.copy2(Path(__file__).with_name("jbgs_camera_adapter.py"), adapter)
    updated = content.replace("from scene.cameras import Camera", "from scene.cameras import Camera\nfrom jbgs_camera_adapter import maybe_calibrate_camera")
    updated = updated.replace(old, old.replace("return Camera", "camera = Camera"))
    updated = updated.replace(tail, tail + "\n    return maybe_calibrate_camera(camera, args, cam_info)")
    path.write_text(updated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    patch(parser.parse_args().source)
