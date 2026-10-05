"""Audit native TSDF depth cutoff against frozen prisms using cameras only.

No model, RGB, depth map, ALS/MVS geometry or evaluation reference is opened.
COLMAP metadata is read by the exact GeoGS loader. Native getWorld2View2 and
focus_point_fn run unchanged, on CPU, with the native float32 camera convention.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import resource
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


SEALED_MANIFESTS = {
    "P1": "3257b3604f630a64948606605c3ae46f2e22d4d5829b5ad49a7d46b342a42112",
    "P2": "6493c602332144510526a54f31700c28cb31eb648250e690d6528fcffe5162a2",
    "P3": "5f22de0224d255765adc126d3ba587388e56f3234b93a3657c821921c4d8911a",
}
CONFIG_SHA256 = "b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4"
STATES = ("FULL_PRISM_DEPTH_INCLUDED", "PRISM_DEPTH_PARTIALLY_INCLUDED",
          "FULL_PRISM_BEYOND_DEPTH_TRUNC", "FULL_PRISM_BEHIND_CAMERA")
COLORS = dict(zip(STATES, ("#26734d", "#d78b17", "#ba3434", "#767676")))


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def interval_status(z_min, z_max, depth_trunc):
    if not np.isfinite([z_min, z_max, depth_trunc]).all() or z_min > z_max or depth_trunc <= 0:
        raise ValueError("Finite ordered depth interval and positive cutoff required")
    if z_max <= 0:
        return STATES[3]
    if z_min > depth_trunc:
        return STATES[2]
    if z_min > 0 and z_max <= depth_trunc:
        return STATES[0]
    return STATES[1]


def plot_intervals(region, rows, depth_trunc, path):
    fig, axis = plt.subplots(figsize=(15, 7), constrained_layout=True)
    for row in rows:
        alpha = 1.0 if row["projected_bbox_nonempty"] else 0.25
        axis.vlines(row["train_index"], row["prism_camera_z_min_m"], row["prism_camera_z_max_m"],
                    color=COLORS[row["depth_status"]], linewidth=1.6, alpha=alpha)
    axis.axhline(depth_trunc, color="#173b70", linestyle="--", linewidth=1.8,
                 label=f"Native depth_trunc = {depth_trunc:.6f} m")
    axis.axhline(0, color="#222222", linewidth=0.7)
    axis.set(xlabel="Training view index: official filename-stem order", ylabel="Camera-Z of fixed prism enclosure (m)",
             title=f"{region}: native TSDF cutoff vs frozen prism | camera metadata only\n"
                   "Each line spans all prism corner depths; faint = no projected bbox intersection")
    axis.grid(alpha=0.18)
    handles, labels = axis.get_legend_handles_labels()
    handles += [Line2D([0], [0], color=COLORS[state], lw=3) for state in STATES]
    labels += [state.replace("_", " ").lower() for state in STATES]
    axis.legend(handles, labels, loc="best", fontsize=8)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    started = time.monotonic()
    out, inputs, source = Path("/out"), Path("/inputs"), Path("/source")
    if sha("/config.json") != CONFIG_SHA256:
        raise ValueError("Frozen scientific configuration changed")
    config = json.loads(Path("/config.json").read_text())
    sys.path.insert(0, str(source))
    from utils.graphics_utils import getWorld2View2
    from utils.render_utils import focus_point_fn
    loader = load_module("native_colmap_loader", source / "scene/colmap_loader.py")
    roi = load_module("roi_contract", "/roi_contract.py")
    # Domain boundary checks verify interpretation, not copied native functions.
    for values, expected in [((1, 2, 3), STATES[0]), ((1, 4, 3), STATES[1]),
                             ((4, 5, 3), STATES[2]), ((-2, 0, 3), STATES[3]),
                             ((-1, 2, 3), STATES[1]), ((1, 3, 3), STATES[0])]:
        assert interval_status(*values) == expected
    native_paths = ["utils/graphics_utils.py", "utils/render_utils.py", "utils/mesh_utils.py",
                    "scene/colmap_loader.py", "scene/cameras.py", "scene/dataset_readers.py",
                    "scene/__init__.py", "render.py"]
    policy = dict(task_id=config["task_id"], schema="GEOGS_INPUT_ONLY_EXTRACTION_DOMAIN_v1",
        scientific_verdict=None, created_utc=datetime.now(timezone.utc).isoformat(),
        source_commit=config["official_commit"], config_sha256=sha("/config.json"),
        script_sha256=sha(__file__), roi_contract_sha256=sha("/roi_contract.py"),
        source_files={str(path): sha(source / path) for path in native_paths},
        native_functions_executed=["read_extrinsics_binary", "qvec2rotmat", "getWorld2View2", "focus_point_fn"],
        camera_convention="Official COLMAP quaternion -> R.T -> getWorld2View2(R.T,t) float32; inverse on NumPy float32; native OpenGL axis flip only for focus",
        camera_order="Official image basename split at first dot, ascending; train membership from sealed split",
        formula="focus=focus_point_fn(c2ws[:,:3,:] @ diag(1,-1,-1,1)); radius=min(norm(c2w_center-focus)); depth_trunc=2*radius; voxel=depth_trunc/mesh_res; sdf_trunc=5*voxel",
        bounds="Fixed half-open scientific prism; corner extrema use its closed enclosure, conservative at the excluded upper faces",
        depth_domain="0 < camera_Z <= depth_trunc; per-view interval classification does not measure prism volume fraction",
        pixel_domain="Shared projected_prism_bbox with near=1e-4; nonempty bounding rectangle is only a possible image-domain intersection, not exact silhouette/frustum visibility",
        no_depth_margin_added=True, no_parameter_change=True, reference_accessed=False,
        rgb_accessed=False, model_or_output_surface_accessed=False,
        limitations=["Camera-Z inclusion does not prove valid rendered depth, surface reconstruction, observation or lack of occlusion.",
                     "Prism interval endpoints may lie outside the image, so partial interval inclusion is conservative and not lost visible-surface fraction.",
                     "A view wholly beyond the cutoff cannot contribute a depth sample located in this prism through native bounded TSDF at that view.",
                     "Some other train views may still support the region; these counts do not establish final holes or error.",
                     "The radius is camera-focus distance, not an object/prism enclosing radius.",
                     "Mesh-resolution sensitivities retain the same depth cutoff and therefore do not restore depth samples beyond it."])
    write_json(out / "policy.json", policy)
    summaries, all_rows, input_ledger = {}, [], []
    for region, settings in config["regions"].items():
        folder = inputs / region
        manifest_path, split_path = folder / "input_manifest.json", folder / "scene/split_manifest_da3_v2.json"
        if sha(manifest_path) != SEALED_MANIFESTS[region]:
            raise ValueError(f"{region}: exact input manifest changed")
        manifest = json.loads(manifest_path.read_text())
        if sha(split_path) != manifest["split_sha256"] or manifest["config_sha256"] != CONFIG_SHA256:
            raise ValueError(f"{region}: sealed split/config identity mismatch")
        binary_path = folder / "scene/sparse/0/images.bin"
        file_records = {item["path"]: item for item in manifest["files"]}
        binary_sha = sha(binary_path)
        if binary_sha != file_records["scene/sparse/0/images.bin"]["sha256"]:
            raise ValueError(f"{region}: native extraction camera bytes changed")
        split = json.loads(split_path.read_text())
        train = sorted(split["train"], key=lambda row: Path(row["name"]).name.split(".")[0])
        if len(train) != settings["expected_train"] or len({row["name"] for row in train}) != len(train):
            raise ValueError(f"{region}: unexpected or duplicate train membership")
        if {row["name"] for row in train} & {row["name"] for row in split["evaluation"]}:
            raise ValueError(f"{region}: train/evaluation membership overlap")
        cameras = loader.read_extrinsics_binary(binary_path)
        by_name = {cam.name: cam for cam in cameras.values()}
        if len(by_name) != len(cameras) or set(by_name) != {row["name"] for row in split["all"]}:
            raise ValueError(f"{region}: COLMAP camera membership differs from frozen split")
        w2vs, errors = [], []
        for view in train:
            camera = by_name[view["name"]]
            if camera.id != view["image_id"] or camera.camera_id != view["camera_id"]:
                raise ValueError(f"{region}: native camera identity mismatch")
            rotation = loader.qvec2rotmat(camera.qvec)
            transform = getWorld2View2(rotation.T, camera.tvec)
            split_transform = getWorld2View2(np.asarray(view["R"]).T, np.asarray(view["t"]))
            error = float(np.abs(transform-split_transform).max())
            if not np.array_equal(transform, split_transform):
                raise ValueError(f"{region}: COLMAP/split native float32 transform mismatch: {error}")
            w2vs.append(transform)
            errors.append(error)
        w2vs = np.asarray(w2vs)
        c2ws = np.array([np.linalg.inv(transform) for transform in w2vs])
        poses = c2ws[:, :3, :] @ np.diag([1, -1, -1, 1])
        focus = focus_point_fn(poses)
        camera_distances = np.linalg.norm(c2ws[:, :3, 3]-focus, axis=-1)
        radius = float(camera_distances.min())
        depth_trunc = 2.0 * radius
        if not np.isfinite(depth_trunc) or depth_trunc <= 0:
            raise ValueError(f"{region}: invalid native cutoff")
        bounds = settings["domain"]
        corners = np.array(list(itertools.product(*(bounds[axis] for axis in "xyz"))))
        rows = []
        for index, (view, transform) in enumerate(zip(train, w2vs)):
            depths = (corners @ transform[:3, :3].T + transform[:3, 3])[:, 2]
            z_min, z_max = float(depths.min()), float(depths.max())
            bbox = roi.projected_prism_bbox(bounds, transform[:3, :3], transform[:3, 3],
                                            view["K"], view["width"], view["height"])
            rows.append(dict(region=region, train_index=index, image_id=view["image_id"],
                camera_id=view["camera_id"], name=view["name"],
                camera_center_x_m=float(c2ws[index, 0, 3]), camera_center_y_m=float(c2ws[index, 1, 3]),
                camera_center_z_m=float(c2ws[index, 2, 3]), camera_to_focus_m=float(camera_distances[index]),
                native_radius_m=radius, depth_trunc_m=depth_trunc,
                prism_camera_z_min_m=z_min, prism_camera_z_max_m=z_max,
                cutoff_minus_prism_z_max_m=depth_trunc-z_max,
                depth_status=interval_status(z_min, z_max, depth_trunc),
                projected_bbox_nonempty=bbox is not None,
                projected_bbox_pixels=0 if bbox is None else (bbox[2]-bbox[0])*(bbox[3]-bbox[1]),
                projected_bbox_json=json.dumps(bbox),
                native_vs_split_float32_w2v_max_abs_difference=errors[index]))
        status_counts = {state: sum(row["depth_status"] == state for row in rows) for state in STATES}
        possible_counts = {state: sum(row["depth_status"] == state and row["projected_bbox_nonempty"] for row in rows)
                           for state in STATES}
        summary = dict(train_views=len(rows), fixed_prism=bounds, focus_xyz_m=focus.tolist(),
            native_radius_m=radius, depth_trunc_m=depth_trunc,
            nearest_focus_camera_name=train[int(np.argmin(camera_distances))]["name"],
            native_tsdf_settings={str(res): dict(mesh_res=res, depth_trunc_m=depth_trunc,
                voxel_size_m=depth_trunc/res, sdf_trunc_m=5*depth_trunc/res)
                for res in [config["extraction"]["mesh_res"], *config["extraction"]["sensitivity_mesh_res"]]},
            status_counts_all_train_views=status_counts,
            status_counts_projected_bbox_nonempty=possible_counts,
            projected_bbox_nonempty_views=sum(row["projected_bbox_nonempty"] for row in rows),
            min_prism_camera_z_m=min(row["prism_camera_z_min_m"] for row in rows),
            max_prism_camera_z_m=max(row["prism_camera_z_max_m"] for row in rows),
            min_cutoff_minus_prism_z_max_m=min(row["cutoff_minus_prism_z_max_m"] for row in rows),
            max_cutoff_minus_prism_z_max_m=max(row["cutoff_minus_prism_z_max_m"] for row in rows),
            all_native_vs_split_float32_w2v_byte_equal=all(value == 0 for value in errors),
            interpretation_status=("CAMERA_DEPTH_CUTOFF_EXCLUDES_SOME_PRISM_VIEWS"
                if possible_counts[STATES[2]] or possible_counts[STATES[1]] else "NO_CUTOFF_EXCLUSION_IN_POSSIBLE_PROJECTED_VIEWS"),
            scientific_verdict=None)
        summaries[region] = summary
        all_rows.extend(rows)
        input_ledger.append(dict(region=region, input_manifest_sha256=sha(manifest_path),
            split_sha256=sha(split_path), native_images_bin_sha256=binary_sha,
            native_camera_file="scene/sparse/0/images.bin"))
        write_json(out / f"{region}_summary.json", summary)
        plot_intervals(region, rows, depth_trunc, out / f"{region}_camera_depth_intervals.png")
    with (out / "per_training_view.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    write_json(out / "summary.json", dict(schema=policy["schema"], regions=summaries, scientific_verdict=None))
    write_json(out / "input_ledger.json", input_ledger)
    receipt = dict(task_id=config["task_id"], status="INPUT_ONLY_EXTRACTION_DOMAIN_AUDIT_COMPLETE",
        scientific_verdict=None, reference_accessed=False, rgb_accessed=False,
        model_or_output_surface_accessed=False, settings_changed=False,
        training_camera_count=len(all_rows), wall_seconds=time.monotonic()-started,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        versions=dict(python=sys.version, numpy=np.__version__, matplotlib=matplotlib.__version__),
        files={path.name: sha(path) for path in sorted(out.iterdir()) if path.is_file() and path.name != "run.log"})
    write_json(out / "receipt.json", receipt)
    print(json.dumps(dict(status=receipt["status"], regions=summaries), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
