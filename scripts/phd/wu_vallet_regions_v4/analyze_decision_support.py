"""Post-hoc source/status audit; never imported by any candidate generator."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(comparison, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    cfg = json.loads(comparison.read_text())
    output.mkdir(parents=True, exist_ok=False)
    records, rows = {str(comparison): sha(comparison)}, []
    for region in cfg["regions"]:
        point_path = Path(region["updated_npz"])
        distance_path = Path(region["evaluation_json"]).parent / "source_distances.npz"
        records[str(point_path)] = sha(point_path)
        records[str(distance_path)] = sha(distance_path)
        with np.load(point_path) as points, np.load(distance_path) as distances:
            groups = {}
            for side in ("old", "new"):
                status = points[f"{side}_vertex_status"]
                keep = points[f"{side}_keep_mask"]
                distance = distances[f"{side}_reference_distance_m"]
                assert len(status) == len(keep) == len(distance)
                assert np.isfinite(distance).all()
                groups[side] = {}
                for label in np.unique(status):
                    mask = status == label
                    selected = distance[mask]
                    groups[side][str(label)] = dict(points=int(mask.sum()), retained=int((mask & keep).sum()),
                        retained_reference_over_2m=int((mask & keep & (distance > 2)).sum()),
                        retained_reference_within_0_5m=int((mask & keep & (distance <= .5)).sum()),
                        removed_reference_over_2m=int((mask & ~keep & (distance > 2)).sum()),
                        removed_reference_within_0_5m=int((mask & ~keep & (distance <= .5)).sum()),
                        median_reference_distance_m=float(np.median(selected)),
                        p90_reference_distance_m=float(np.quantile(selected, .9)))
            rows.append(dict(id=region["id"], primary_arm=region["primary_arm"], groups=groups))
    for path, expected in records.items():
        assert sha(path) == expected
    receipt = dict(status="POSTHOC_DECISION_SUPPORT_ANALYSIS_COMPLETE", scientific_verdict=None, regions=rows,
                   input_hashes=records, algorithm_outputs_modified=False,
                   thresholds_role="Fixed 0.5m/2m reporting only; neither change truth nor source usability gates",
                   status_role="Raw-single is original SINGLE-face incidence, not certified currentness or true single-source coverage. Unassessed means mesh support missing.",
                   candidate_changes=0, source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
                   container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                   versions={"numpy": importlib.metadata.version("numpy")})
    with (output / "receipt.json").open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({r["id"]: r["groups"] for r in rows}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.comparison, args.output)
