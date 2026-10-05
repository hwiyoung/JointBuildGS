"""Post-selection evidence only: bind native depth pixels to the real photograph.

ROI examples deliberately use reference discrepancy to inspect outcomes. They are
not a random sample, a change/outlier ground truth, or inputs to any algorithm.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write(path, obj):
    with Path(path).open("x") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def main(config_path, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution required")
    cfg = json.loads(config_path.read_text())
    root = Path(cfg["filter_root"])
    # All processing here occurs after corrected candidates were sealed.
    receipt_path = root / "candidate_receipt.json"
    receipt_hash = sha(receipt_path)
    sealed = json.loads(receipt_path.read_text())
    assert sealed["reference_accessed"] is False
    for arm in sealed["arms"]:
        for filename, digest in arm["outputs"].items():
            assert sha(root / arm["name"] / filename) == digest
    output.mkdir(parents=True, exist_ok=False)
    (output / "photos").mkdir()
    (output / "figures").mkdir()
    write(output / "config.json", cfg)
    assert sha(cfg["photo"]) == cfg["photo_sha256"]
    assert sha(cfg["reference"]) == cfg["reference_sha256"]
    shutil.copy2(cfg["photo"], output / "photos/master_133.jpg")
    photo = np.asarray(Image.open(cfg["photo"]).convert("RGB"))
    assert list(photo.shape[:2]) == cfg["photo_shape"]
    data = np.load(root / "diagnostic_points.npz")
    xyz, old = data["new_xyz"], data["old_xyz"]
    pixel_id = data["new_pixel_id"]
    dh, dw = cfg["depth_shape"]
    ph, pw = cfg["photo_shape"]
    pixels = np.c_[pixel_id % dw * pw / dw, pixel_id // dw * ph / dh]
    views = json.loads(Path(cfg["views"]).read_text())
    rows = views["views"] if isinstance(views, dict) else views
    view = next(r for r in rows if int(r["image_id"]) == cfg["image_id"])
    camera = xyz @ np.asarray(view["R"]).T + np.asarray(view["t"])
    projected = camera @ np.asarray(view["K"]).T
    projected = projected[:, :2] / projected[:, 2:]
    projection_error = np.linalg.norm(projected - pixels, axis=1)
    assert np.all(camera[:, 2] > 0) and projection_error.max() < 1e-4
    before = data[cfg["baseline_arm"] + "_new_keep"]
    after = data[cfg["corrected_arm"] + "_new_keep"]
    dist = data["new_reference_distance_m"]
    removed = before & ~after
    large = dist > cfg["diagnostic_large_distance_m"]
    sor_file = Path(cfg["sor_root"]) / "masks.npz"
    sor = np.load(sor_file)
    assert np.array_equal(sor["p3_native_pixel_id"], pixel_id)
    evidence = dict(pixel_xy=pixels, new_reference_distance_m=dist,
                    original_keep=before, corrected_keep=after, region_removed=removed,
                    sor_survives=sor["p3_keep_with_context"],
                    component_id=data["new_largest_incident_changed_component_id"],
                    component_area_m2=data["new_largest_incident_changed_area_m2"])
    np.savez_compressed(output / "evidence.npz", **evidence)
    reference = np.load(cfg["reference"])["uas_xyz"]
    ref_tree = cKDTree(reference)
    categories = [
        ("removed_large", "수정 후 제외 · 참조 편차 >2m", removed & large, "#00bdcf"),
        ("remaining_large", "수정 후 잔존 · 참조 편차 >2m", after & large, "#ff334a"),
        ("accepted_close", "수정 후 채택 · 참조 편차 <0.25m", after & (dist < cfg["diagnostic_close_distance_m"]), "#44df78"),
    ]
    figures, rois, points = [], [], []
    fig, ax = plt.subplots(figsize=(14, 10.13))
    ax.imshow(photo)
    ax.scatter(pixels[before, 0], pixels[before, 1], s=.35, c="#ffbd40", alpha=.5, label="v2 admitted")
    for key, label, mask, color in categories[:2]:
        ax.scatter(pixels[mask, 0], pixels[mask, 1], s=2, c=color, label=key.replace("_", " "))
    ax.set(xlim=(0, pw), ylim=(ph, 0), title="Actual master 133: corrected exclusions and remaining reference discrepancy")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(output / "figures/photo_overview.png", dpi=150)
    plt.close(fig)
    figures.append(dict(id="photo_overview", label="실제 사진 위 필터 전후", path="figures/photo_overview.png"))
    bins = (pixels // cfg["roi_bin_px"]).astype(int)
    for key, label, mask, color in categories:
        ids = np.flatnonzero(mask)
        if not len(ids):
            continue
        unique, inverse, counts = np.unique(bins[ids], axis=0, return_inverse=True, return_counts=True)
        best_bin = int(np.argmax(counts))
        candidates = ids[inverse == best_bin]
        center = (unique[best_bin] + .5) * cfg["roi_bin_px"]
        reps = candidates[np.argsort(np.linalg.norm(pixels[candidates] - center, axis=1), kind="stable")[:5]]
        rep = int(reps[0])
        center = pixels[rep]
        hw, hh = cfg["roi_half_size_px"]
        bbox = [max(0, int(center[0] - hw)), max(0, int(center[1] - hh)),
                min(pw, int(center[0] + hw)), min(ph, int(center[1] + hh))]
        caption = f"사후 진단 사례. {label}; 참조로 점군을 수정하지 않았으며 오류/변화 정답을 뜻하지 않습니다."
        rois.append(dict(id=key, label=label, bbox_xyxy=bbox, caption=caption,
                         representative_new_index=rep, case_type=key,
                         selection="Most populated fixed 80px bin for this post-hoc category; nearest bin-centre pixel"))
        for idx in reps:
            idx = int(idx)
            nn_dist, nn_idx = ref_tree.query(xyz[idx])
            points.append(dict(new_native_index=idx, pixel_x=float(pixels[idx, 0]), pixel_y=float(pixels[idx, 1]),
                               xyz=xyz[idx].tolist(), uas_distance_m=float(nn_dist),
                               nearest_reference_xyz=reference[nn_idx].tolist(), roi_id=key, reason=label,
                               original_keep=bool(before[idx]), corrected_keep=bool(after[idx]),
                               sor_survives=bool(evidence["sor_survives"][idx]),
                               component_id=int(evidence["component_id"][idx]),
                               component_area_m2=float(evidence["component_area_m2"][idx])))
        anchor = xyz[rep]
        radius = cfg["local_geometry_radius_m"]
        new_mask = np.linalg.norm(xyz[:, :2] - anchor[:2], axis=1) < radius
        old_mask = np.linalg.norm(old[:, :2] - anchor[:2], axis=1) < radius
        ref_mask = np.linalg.norm(reference[:, :2] - anchor[:2], axis=1) < radius
        ref_ids = np.flatnonzero(ref_mask)
        ref_ids = ref_ids[::max(1, int(np.ceil(len(ref_ids) / 40000)))]
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        axes[0].imshow(photo)
        for _, _, category_mask, category_color in categories:
            axes[0].scatter(pixels[category_mask, 0], pixels[category_mask, 1], s=4, c=category_color)
        axes[0].scatter(*pixels[rep], marker="x", c="white", s=70)
        axes[0].set(xlim=(bbox[0], bbox[2]), ylim=(bbox[3], bbox[1]), title=key + " | actual photo")
        for axis, horizontal in zip(axes[1:], [0, 1]):
            axis.scatter(reference[ref_ids, horizontal], reference[ref_ids, 2], s=.3, c="gray", alpha=.3, label="UAS reference")
            axis.scatter(old[old_mask, horizontal], old[old_mask, 2], s=1, c="#2062db", label="Original ALS")
            for m, c, l in [(new_mask & after, "#e59c00", "Corrected admitted"),
                            (new_mask & removed, "#00bdcf", "Removed by correction"),
                            (new_mask & after & large, "#ff334a", "Retained, reference >2m")]:
                axis.scatter(xyz[m, horizontal], xyz[m, 2], s=2, c=c, label=l)
            axis.scatter(anchor[horizontal], anchor[2], marker="x", c="black", s=60, zorder=5)
            axis.set(xlabel=["X (m)", "Y (m)"][horizontal], ylabel="Z (m)", title=f"Local {'XZ' if horizontal == 0 else 'YZ'} projection: XY radius {radius:g}m")
        axes[2].legend(fontsize=7)
        fig.suptitle("Post-hoc selected evidence; local projections are not thin cross-sections; native point positions unchanged")
        fig.tight_layout()
        rel = f"figures/{key}.png"
        fig.savefig(output / rel, dpi=160)
        plt.close(fig)
        figures.append(dict(id=key, label=label, path=rel))
    write(output / "points.json", dict(points=points, selection_role="post-hoc forensic examples, not representative accuracy sample"))
    outputs = {str(p.relative_to(output)): sha(p) for p in output.rglob("*") if p.is_file()}
    write(output / "receipt.json", dict(status="PHOTO_POINT_FORENSICS_COMPLETE", task_id=cfg["task_id"],
          scientific_verdict=None, image_id=cfg["image_id"], depth_shape=cfg["depth_shape"],
          photo=dict(path="photos/master_133.jpg", width=pw, height=ph, image_id=cfg["image_id"]),
          evidence_npz="evidence.npz", points_json="points.json", rois=rois, figures=figures,
          pixel_count=len(xyz), projection_max_error_px=float(projection_error.max()),
          counts=dict(original_admitted=int(before.sum()), corrected_admitted=int(after.sum()),
                      removed=int(removed.sum()), removed_large=int((removed & large).sum()),
                      retained_large=int((after & large).sum())),
          candidate_receipt_sha256=receipt_hash, output_hashes=outputs,
          reference_role="Evaluation only. Raw shift, no calibrated CRS/epoch reconciliation. Distances are not error/change ground truth.",
          display_role="Pixel evidence uses every native point; static reference projections are display subsamples only.",
          source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"), container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
          source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
          input_hashes={str(p): sha(p) for p in [config_path, receipt_path, root / "diagnostic_points.npz", sor_file, Path(cfg["views"])]},
          versions={k: importlib.metadata.version(k) for k in ["numpy", "scipy", "matplotlib", "Pillow"]}))
    assert sha(receipt_path) == receipt_hash
    print(json.dumps(dict(status="PHOTO_POINT_FORENSICS_COMPLETE", output=str(output), rois=len(rois), selected_points=len(points))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.config, args.output)
