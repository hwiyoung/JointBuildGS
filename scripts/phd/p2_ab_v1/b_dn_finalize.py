"""Publish DN evaluation through the additive B comparison schema."""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from scripts.phd.p2_ab_v1.b_run import sha, write_json


def main(task, source):
    task, source = Path(task), Path(source)
    native_final, initial = task / "evaluation", task / "evaluation_initial"
    alias = task / "dn_splatter_original_v2"
    if alias.exists() or (task / "result.json").exists():
        raise ValueError("DN result adapter already exists")
    alias.mkdir()
    final = alias
    for path in native_final.iterdir():
        if path.name.startswith("target_") or path.name.startswith("initial_"):
            continue
        (final / path.name).symlink_to("../evaluation/" + path.name)
    (final / "initial_extracted_surface.npz").symlink_to("../evaluation_initial/extracted_surface.npz")
    shutil.copyfile(source / "views.json", task / "views.json")
    if (task / "handoff_receipt.json").exists():
        raise ValueError("DN handoff receipt already exists")
    shutil.copyfile(source / "handoff_receipt.json", task / "handoff_receipt.json")
    views = json.loads((source / "views.json").read_text())["views"]
    appearance, guard = [], []
    for view in views:
        if view.get("role") != "eval":
            continue
        iid = view["image_id"]
        from PIL import Image
        source_target = source / "surface_texturing" / f"target_{iid}.png"
        old_target = native_final / f"target_{iid}.png"
        if not np.array_equal(np.asarray(Image.open(old_target)), np.asarray(Image.open(source_target))):
            raise ValueError(f"Target decoded pixels mismatch {iid}")
        shutil.copyfile(source_target, final / f"target_{iid}.png")
        before = np.load(initial / f"render_{iid}.npz")
        after = np.load(final / f"render_{iid}.npz")
        target = np.asarray(Image.open(final / f"target_{iid}.png")).astype(np.float32) / 255.
        support, predicted = before["alpha"] >= .5, after["alpha"] >= .5
        overlap = support & predicted
        error = after["rgb"][support] - target[support]
        n = int(support.sum())
        appearance.append({"image_id": iid, "pixels": n, "mae": float(np.abs(error).mean()) if n else None,
                           "psnr_db": float(-10 * np.log10(max(float(np.square(error).mean()), 1e-12))) if n else None,
                           "missing_initial_support_pixels": int((support & ~predicted).sum())})
        removed, added = int((support & ~predicted).sum()), int((predicted & ~support).sum())
        delta = float(np.abs(after["depth"][overlap] - before["depth"][overlap]).max()) if overlap.any() else None
        guard.append({"image_id": iid, "pass": removed == added == 0 and delta == 0,
                      "removed_pixels": removed, "added_pixels": added,
                      "initial_pixels": n, "final_pixels": int(predicted.sum()),
                      "overlap_pixels": int(overlap.sum()), "max_depth_displacement_m": delta,
                      "depth_tolerance_m": 0., "finite_depth": bool(np.isfinite(after["depth"][predicted]).all())})
        (final / f"initial_rgb_{iid}.png").symlink_to(f"../evaluation_initial/rgb_{iid}.png")
    upstream = json.loads((final / "metrics.json").read_text())
    source_result = json.loads((source / "result.json").read_text())
    result = {"status": "PINNED_UPSTREAM_BOUNDED_DEVELOPMENT_COMPLETE", "decision_method": "FIXED_PRIOR",
              "condition": "REAL", "units": source_result["units"], "scientific_verdict": None,
              "input_hashes": {"source_result": sha(source / "result.json"), "adapter": sha(task / "data/adapter_receipt.json")},
              "arms": [{"arm": "dn_splatter_original_v2", "decision_method": "FIXED_PRIOR", "condition": "REAL",
                        "scope": "pinned upstream DN-Splatter with selected-source depth adapter, 96 development steps",
                        "appearance": appearance, "evaluation_surface_guard": guard,
                        "surface_points": upstream["surface_points"], "gaussians": upstream["gaussians"],
                        "train_views": 33, "eval_views": 11, "accepted_geometry_steps": 96,
                        "rejected_geometry_steps": 0, "runtime_seconds": None,
                        "upstream": upstream, "scientific_verdict": None,
                        "initialization_comparison": "same exact selected source points; different upstream 3DGS scales/opacity/PCA-normal initialization; initial model rerendered from seed0/config"}]}
    write_json(task / "result.json", result)
    write_json(task / "finalization_receipt.json", {"target_png_exact_byte_matches": 11,
               "views_source_sha256": sha(source / "views.json"), "views_copy_sha256": sha(task / "views.json"),
               "scientific_verdict": None})
    print(json.dumps({"result": str(task / "result.json"), "views": 11, "surface_points": upstream["surface_points"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    main(args.task, args.source)
