"""Verify completed B artifacts without rerunning training or changing outputs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(root, output):
    root, output = Path(root), Path(output)
    if output.exists():
        raise ValueError("Verification receipt already exists")
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.phd.test_p2_ab_reconstruction")
    tested = unittest.TextTestRunner(verbosity=1).run(suite)
    if not tested.wasSuccessful():
        raise ValueError("Reconstruction tests failed")
    repo = Path("/workspace/JointBuildGS")
    source = [repo / "src/phd/p2_ab_v1/reconstruction.py", repo / "tests/phd/test_p2_ab_reconstruction.py"]
    source += sorted((repo / "scripts/phd/p2_ab_v1").glob("b_*.py"))
    for path in source:
        ast.parse(path.read_text())
    parsed_count = len(source)
    source += sorted((repo / "scripts/phd/p2_ab_v1").glob("b_*.sh"))
    source += sorted((repo / "configs/phd/p2_ab_v1").glob("b_*.json"))
    source += sorted((repo / "docs/experiments/phd/p2_ab_v1").glob("B_*.md"))
    names = ["RANGE-v1", "SCORE-v1", "BAYES-v1", "IMAGE-v1", "PRIOR-v2", "DN-v2"]
    rows, first_views = [], None
    for suffix in names:
        run = root / ("PHD-P2-AB-B-" + suffix)
        result = json.loads((run / "result.json").read_text())
        assert result["scientific_verdict"] is None
        handoff = json.loads((run / "handoff_receipt.json").read_text())
        assert handoff["strict_accepted_units"] == 0
        views = json.loads((run / "views.json").read_text())["views"]
        cameras = [(v["image_id"], v["role"], v["crop_xyxy"], v["K"], v["viewmat"]) for v in views if "excluded" not in v]
        if first_views is None:
            first_views = cameras
        assert cameras == first_views, "Comparison crops/cameras/roles are not identical"
        arms = []
        for arm in result["arms"]:
            path = run / arm["arm"]
            surf = np.load(path / "extracted_surface.npz", allow_pickle=False)
            before = np.load(path / "initial_extracted_surface.npz", allow_pickle=False)
            assert np.isfinite(surf["xyz"]).all()
            assert len(surf["xyz"]) == len(surf["unit_index"])
            for view in [v for v in views if v.get("role") == "eval"]:
                iid = view["image_id"]
                target = np.asarray(Image.open(path / f"target_{iid}.png"))
                ref = np.asarray(Image.open(root / "PHD-P2-AB-B-PRIOR-v2/surface_texturing" / f"target_{iid}.png"))
                assert np.array_equal(target, ref), "Evaluation target pixels differ"
            arms.append({"arm": arm["arm"], "surface_points": len(surf["xyz"]), "initial_surface_points": len(before["xyz"]),
                         "surface_sha256": sha(path / "extracted_surface.npz"), "initial_surface_sha256": sha(path / "initial_extracted_surface.npz")})
        rows.append({"run": run.name, "arms": arms, "result_sha256": sha(run / "result.json")})
    abstain = root / "PHD-P2-AB-B-SHARED-SHIFT-v1"
    result = json.loads((abstain / "result.json").read_text())
    assert result["status"] == "ABSTAIN_NO_GEOMETRY"
    assert len(result["units"]) == 64 and all(row["seed_count"] == 0 for row in result["units"])
    assert not (abstain / "initial_source_seeds.npz").exists()
    receipt = {"status": "PASS", "unit_tests": tested.testsRun, "source_files_parsed": parsed_count,
               "source_hashes": {str(p.relative_to(repo)): sha(p) for p in source}, "runs": rows,
               "matched_cameras_crops_roles": len(first_views), "strict_accepted_units": 0,
               "abstain_units_preserved": 64, "abstain_gaussians_created": 0, "scientific_verdict": None}
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "tests": tested.testsRun, "runs": len(rows), "camera_roles": len(first_views)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    main(args.root, args.output)
