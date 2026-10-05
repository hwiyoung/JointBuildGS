"""Same-P2 source-routing fixture; never a calibrated judgment experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform

import numpy as np

from src.phd.p2_ab_v3.handoff import Candidate, assemble_selected_geometry


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    common = Path(cfg["common_root"])
    native_path = common / "native_geometry.npz"
    manifest_path = common / "sample_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    native_hash = sha(native_path)
    # The common manifest's own file table pins the unchanged original payload.
    expected = [value["sha256"] for value in manifest.values()
                if isinstance(value, dict) and "native_geometry.npz" in value
                for value in [value["native_geometry.npz"]]]
    if len(expected) != 1 or expected[0] != native_hash:
        raise ValueError("common native geometry does not match frozen manifest")
    native = np.load(native_path, allow_pickle=False)
    candidates, decisions = {}, []
    for source, action in [("als", "PRIOR"), ("mvs", "IMAGE")]:
        xyz = native[f"{source}_xyz"]
        keep = xyz[:, 0] < cfg["fixture_split_x_m"]
        if source == "mvs":
            keep = ~keep
        identifier = source + ":fixture_region"
        candidate = Candidate(identifier, action, xyz[keep], native[f"{source}_normals"][keep],
            native[f"{source}_tile_rows"][keep], (native_hash + ":" + source,), "unchanged_common_v1")
        candidates[identifier] = candidate
        decisions.append(dict(region_id=identifier, candidate_id=identifier, action=action,
            geometry_sha256=candidate.fingerprint(), eligibility="FIXTURE_NOT_INFERRED",
            calibration_status="UNAVAILABLE", appearance_allowed=np.ones(len(candidate.xyz), bool),
            detail_allowed=np.zeros(len(candidate.xyz), bool),
            components=[dict(component="normal_position", unit="m",
                candidate_error_upper=cfg["fixture_normal_error_upper_m"],
                required_error=cfg["fixture_normal_required_error_m"]) ]))
    decisions.append(dict(region_id="abstention_wiring_record_no_physical_region",
                          action="ABSTAIN", candidate_id=None))
    arrays, receipt = assemble_selected_geometry(candidates, decisions, fixture=True)
    offset, checks = 0, []
    for candidate in candidates.values():
        count = len(candidate.xyz)
        checks.append(bool(np.array_equal(arrays["xyz"][offset:offset + count], candidate.xyz)
                           and np.array_equal(arrays["native_rows"][offset:offset + count],
                                              candidate.native_rows)))
        offset += count
    if not all(checks) or arrays["detail_allowed"].any():
        raise AssertionError("source routing or detail permission changed")
    arrays_path = output / "selected_geometry_fixture.npz"
    np.savez_compressed(arrays_path, **arrays)
    source_paths = [Path(__file__), Path("src/phd/p2_ab_v3/handoff.py"),
                    Path("tests/phd/test_p2_ab_v3_handoff.py"), Path(args.config)]
    receipt.update(task_id=cfg["task_id"], config=cfg, source_hashes={str(p): sha(p) for p in source_paths},
        input_hashes={str(native_path): native_hash, str(manifest_path): sha(manifest_path)},
        output_sha256=sha(arrays_path), checks=dict(exact_selected_geometry=all(checks),
        no_detail_permission=not bool(arrays["detail_allowed"].any()), abstention_adds_zero=True),
        versions=dict(python=platform.python_version(), numpy=np.__version__,
            git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
            container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID")),
        frame=manifest["frame"], actual_A_decisions_used=False, GS_training_executed=False)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(dict(status=receipt["status"], point_count=len(arrays["xyz"]),
                          checks=receipt["checks"])))


if __name__ == "__main__":
    main()
