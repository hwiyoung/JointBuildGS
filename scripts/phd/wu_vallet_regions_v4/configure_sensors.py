"""Generate exact-target sensor configs from sealed native-array metadata."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def main(repo, artifacts, region):
    base = "phase-payloads/phd/wu_vallet_regions_v4"
    rel = f"{base}/PHD-WU-VALLET-{region}-INPUT-v4/run/common/als_native.npz"
    native = artifacts / rel
    with zipfile.ZipFile(native) as archive, archive.open("als_xyz.npy") as stream:
        assert stream.read(6) == b"\x93NUMPY"
        major, minor = stream.read(2)
        length_size = 2 if major == 1 else 4
        length = struct.unpack("<H" if major == 1 else "<I", stream.read(length_size))[0]
        header = ast.literal_eval(stream.read(length).decode())
    count = int(header["shape"][0])
    assert header["shape"][1] == 3 and count > 0
    acq = json.loads((repo / "configs/phd/wu_vallet_p3_v2/acquisition_v2.json").read_text())
    acq.pop("expected_p3_points")
    acq.update(schema="jointbuildgs.wu_vallet.regional_acquisition.v4", region_id=region,
               task_id=f"PHD-WU-VALLET-{region}-ACQUISITION-v4", native_relative_path=rel,
               native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(), expected_region_points=count,
               output_relative_path=f"{base}/PHD-WU-VALLET-{region}-ACQUISITION-v4/run",
               scope="Exact regional ALS raw-row replay, pulse and scan order; same frozen P3 v2 algorithm/settings. No reference or imagery used.")
    traj = json.loads((repo / "configs/phd/wu_vallet_p3_v2/trajectory_v2.json").read_text())
    traj.update(schema="jointbuildgs.wu_vallet.regional_estimated_trajectory.v4", region_id=region,
                task_id=f"PHD-WU-VALLET-{region}-TRAJECTORY-v4",
                acquisition_relative_path=f"{base}/PHD-WU-VALLET-{region}-ACQUISITION-v4/run/acquisition.npz",
                output_relative_path=f"{base}/PHD-WU-VALLET-{region}-TRAJECTORY-v4/run")
    for stage, cfg in [("acquisition", acq), ("trajectory", traj)]:
        path = repo / f"configs/phd/wu_vallet_regions_v4/{region}_{stage}_v4.json"
        with path.open("x") as stream:
            json.dump(cfg, stream, indent=2)
            stream.write("\n")
    print(json.dumps(dict(region=region, expected_points=count, native_sha256=acq["native_sha256"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--region", choices=["P1", "P2"], required=True)
    args = parser.parse_args()
    main(args.repo, args.artifacts, args.region)
