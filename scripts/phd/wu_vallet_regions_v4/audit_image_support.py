"""Reference-free audit of selected-image support in frozen P1/P2 prisms.

Endpoint-before-prism is a geometric relation, not a verified occlusion label.
No crop, selected image, depth, candidate point or downstream decision is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np
from PIL import Image


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False, ensure_ascii=False)
        f.write("\n")


def quantiles(values):
    values = np.asarray(values)
    if not len(values):
        return dict(count=0)
    return dict(count=len(values), **{name: float(np.quantile(values, q)) for name, q in
                                     (("min", 0.), ("p01", .01), ("p10", .1), ("median", .5),
                                      ("p90", .9), ("p99", .99), ("max", 1.))})


def slab(origin, direction, domain):
    lower = np.zeros(direction.shape[:-1])
    upper = np.full(direction.shape[:-1], np.inf)
    valid = np.ones(direction.shape[:-1], bool)
    for axis, key in enumerate(("x", "y", "z")):
        if key not in domain:
            continue
        d = direction[..., axis]
        moving = np.abs(d) > 1e-15
        a = np.divide(domain[key][0] - origin[axis], d, out=np.zeros_like(d), where=moving)
        b = np.divide(domain[key][1] - origin[axis], d, out=np.zeros_like(d), where=moving)
        lower = np.where(moving, np.maximum(lower, np.minimum(a, b)), lower)
        upper = np.where(moving, np.minimum(upper, np.maximum(a, b)), upper)
        valid &= moving | ((origin[axis] >= domain[key][0]) & (origin[axis] < domain[key][1]))
    valid &= (upper > lower) & (upper > 0)
    return valid, lower, upper


def cell_ids(xyz, domain, spacing):
    nxy = np.ceil([(domain[k][1] - domain[k][0]) / spacing for k in ("x", "y")]).astype(int)
    keep = np.logical_and.reduce([(xyz[:, i] >= domain[k][0]) & (xyz[:, i] < domain[k][1])
                                  for i, k in enumerate(("x", "y"))])
    xy = np.floor((xyz[keep, :2] - [domain["x"][0], domain["y"][0]]) / spacing).astype(int)
    return np.unique(xy[:, 1] * nxy[0] + xy[:, 0]), nxy


def view_audit(view, domain, native_mvs, spacing):
    spec = view["maps"]["depth"]
    path = Path(spec["path"])
    if sha(path) != spec["sha256"]:
        raise ValueError("Frozen depth changed")
    with path.open("rb") as f:
        f.seek(spec["header_bytes"])
        depth = np.fromfile(f, np.float32).reshape((spec["width"], spec["height"], spec["channels"]), order="F").transpose(1, 0, 2)[..., 0].copy()
    K, R, t = np.asarray(spec["K"]), np.asarray(view["R"]), np.asarray(view["t"])
    yy, xx = np.indices(depth.shape)
    rays = np.stack((xx, yy, np.ones_like(xx)), axis=-1) @ np.linalg.inv(K).T
    direction, origin = rays @ R, -t @ R
    xyz = origin + direction * depth[..., None]
    valid = np.isfinite(depth) & (depth > 0)
    xy = valid & (xyz[..., 0] >= domain["x"][0]) & (xyz[..., 0] < domain["x"][1]) & (xyz[..., 1] >= domain["y"][0]) & (xyz[..., 1] < domain["y"][1])
    below = xy & (xyz[..., 2] < domain["z"][0])
    above = xy & (xyz[..., 2] >= domain["z"][1])
    exact = xy & ~below & ~above
    crossing, near, far = slab(origin, direction, domain)
    before = crossing & valid & (depth < near)
    after = crossing & valid & (depth >= far)
    invalid = crossing & ~valid
    # Slab faces are evaluated numerically; endpoint membership uses exact
    # half-open source crop. Count boundary disagreements explicitly.
    ray_inside = crossing & valid & ~before & ~after
    boundary_disagreements = int(np.count_nonzero(ray_inside != exact))
    ray_class = np.zeros(depth.shape, np.uint8)
    ray_class[invalid] = 1
    ray_class[before] = 2
    ray_class[after] = 3
    ray_class[exact] = 4
    native_ids, nxy = cell_ids(native_mvs, domain, spacing)
    exact_ids, _ = cell_ids(xyz[exact], domain, spacing)
    xy_ids, _ = cell_ids(xyz[xy], domain, spacing)
    overlap = np.intersect1d(native_ids, exact_ids)
    pc = native_mvs @ R.T + t
    proj = pc @ K.T
    uv = proj[:, :2] / proj[:, 2:3]
    inframe = (pc[:, 2] > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < depth.shape[1]) & (uv[:, 1] >= 0) & (uv[:, 1] < depth.shape[0])
    ids = np.flatnonzero(inframe)
    pixels = np.floor(uv[ids]).astype(int)
    sample = depth[pixels[:, 1], pixels[:, 0]]
    sampled_valid = np.isfinite(sample) & (sample > 0)
    difference = sample[sampled_valid] - pc[ids[sampled_valid], 2]
    corners = np.asarray([[x, y, z] for x in domain["x"] for y in domain["y"] for z in domain["z"]])
    corner_pc = corners @ R.T + t
    corner_proj = corner_pc @ K.T
    corner_uv = corner_proj[:, :2] / corner_proj[:, 2:3]
    corner_inside = (corner_pc[:, 2] > 0) & (corner_uv[:, 0] >= 0) & (corner_uv[:, 0] < depth.shape[1]) & (corner_uv[:, 1] >= 0) & (corner_uv[:, 1] < depth.shape[0])
    row = dict(image_id=view["image_id"], hash_rank=view["hash_rank"], valid_depth_pixels=int(valid.sum()),
               xy_endpoint_pixels_ignoring_z=int(xy.sum()), exact_xyz_endpoint_pixels=int(exact.sum()),
               xy_endpoint_below_z_pixels=int(below.sum()), xy_endpoint_above_z_pixels=int(above.sum()),
               xy_endpoint_z_m=quantiles(xyz[..., 2][xy]),
               rays_crossing_prism=int(crossing.sum()), crossing_ray_invalid_depth=int(invalid.sum()),
               crossing_ray_endpoint_before_prism=int(before.sum()), crossing_ray_endpoint_after_prism=int(after.sum()),
               ray_endpoint_crop_boundary_disagreements=boundary_disagreements,
               native_mvs_points=len(native_mvs), native_mvs_in_frame=int(inframe.sum()),
               native_mvs_projected_valid_depth=int(sampled_valid.sum()),
               depth_minus_native_mvs_camera_z_m=quantiles(difference),
               prism_corners_in_frame=int(corner_inside.sum()), prism_corner_depth_pixel_uv=corner_uv.tolist(),
               camera_origin_scene_xyz=origin.tolist(),
               cells=dict(spacing_m=spacing, all_prism_xy_cells=int(np.prod(nxy)), native_mvs_occupied=len(native_ids),
                          image_exact_xyz_occupied=len(exact_ids), image_xy_ignoring_z_occupied=len(xy_ids),
                          image_exact_xyz_and_native_overlap=len(overlap), native_mvs_cells_without_image_exact=len(np.setdiff1d(native_ids, exact_ids))))
    data = dict(depth=depth, xyz=xyz, exact=exact, xy=xy, below=below, above=above, crossing=crossing,
                invalid=invalid, before=before, after=after, ray_class=ray_class, corner_uv=corner_uv,
                native_ids=native_ids, exact_ids=exact_ids, xy_ids=xy_ids, nxy=nxy)
    return row, data


def figure(view, region, domain, data, row, path):
    if sha(view["path"]) != view["sha256"]:
        raise ValueError("Selected photo hash changed")
    photo = np.asarray(Image.open(view["path"]).convert("RGB"))
    h, w = photo.shape[:2]
    dh, dw = data["depth"].shape
    uv = data["corner_uv"] * [w / dw, h / dh]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes[0, 0].imshow(photo)
    axes[0, 0].set_title(f"{region}: actual selected photo {view['image_id']} + frozen prism")
    for a in range(8):
        for b in range(a + 1, 8):
            if bin(a ^ b).count("1") == 1:
                axes[0, 0].plot(uv[[a, b], 0], uv[[a, b], 1], color="#ffb000", linewidth=1)
    for mask, color, label in [(data["exact"], "#00ffff", "inside XYZ"),
                                (data["below"], "#ffe35b", "same XY, below Z"),
                                (data["above"], "#fa7ee2", "same XY, above Z")]:
        yy, xx = np.nonzero(mask)
        stride = max(1, len(xx) // 12000)
        axes[0, 0].scatter(xx[::stride] * w / dw, yy[::stride] * h / dh, s=.3, c=color, label=label, alpha=.7)
    axes[0, 0].set_xlim(0, w)
    axes[0, 0].set_ylim(h, 0)
    axes[0, 0].legend(loc="lower right", markerscale=5, fontsize=7)
    colors = ["#e7e9ed", "#555555", "#b65133", "#e7b53d", "#168c92"]
    axes[0, 1].imshow(data["ray_class"], cmap=ListedColormap(colors), vmin=0, vmax=4)
    axes[0, 1].set_title("Gray: invalid | red: before prism | yellow: beyond | cyan: inside")
    low, high = data["corner_uv"].min(axis=0) - 10, data["corner_uv"].max(axis=0) + 10
    axes[0, 1].set_xlim(max(0, low[0]), min(dw, high[0]))
    axes[0, 1].set_ylim(min(dh, high[1]), max(0, low[1]))
    nxy = data["nxy"]
    grid = np.zeros(int(np.prod(nxy)), np.uint8)
    grid[data["native_ids"]] = 1
    grid[data["exact_ids"]] += 2
    axes[1, 0].imshow(grid.reshape(nxy[1], nxy[0]), origin="lower",
                       extent=domain["x"] + domain["y"],
                       cmap=ListedColormap(["#f0f1f4", "#536eac", "#d49c25", "#16978b"]), vmin=0, vmax=3)
    axes[1, 0].set_title("0.5 m XY cells: blue=MVS only, gold=image only, teal=both")
    axes[1, 0].set_xlabel("Scene X (m)")
    axes[1, 0].set_ylabel("Scene Y (m)")
    z = data["xyz"][..., 2][data["xy"]]
    if len(z):
        axes[1, 1].hist(z, bins=80, color="#377d9a")
    axes[1, 1].axvline(domain["z"][0], color="#b34c34", linestyle="--")
    axes[1, 1].axvline(domain["z"][1], color="#b34c34", linestyle="--")
    axes[1, 1].set_title("Current depth endpoints in XY prism; dashed=frozen Z limits")
    axes[1, 1].set_xlabel("Scene Z (m)")
    axes[1, 1].set_ylabel("Native depth pixels")
    fig.suptitle(f"{region} support audit only: before={row['crossing_ray_endpoint_before_prism']:,}, "
                 f"inside={row['exact_xyz_endpoint_pixels']:,}, invalid={row['crossing_ray_invalid_depth']:,}; no UAS / no recrop")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run(config_path, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    cfg = json.loads(Path(config_path).read_text())
    regions = json.loads(Path(cfg["regions_config"]).read_text())
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write(output / "config.json", cfg)
    all_rows, inputs = {}, {str(config_path): sha(config_path), cfg["regions_config"]: sha(cfg["regions_config"])}
    for region_id in cfg["regions"]:
        spec = regions["regions"][region_id]
        common = Path(spec["common_root"])
        vp, npz, mp = common / "views.json", common / "native.npz", common / "selected_master.json"
        for path in (vp, npz, mp):
            inputs[str(path)] = sha(path)
        views = json.loads(vp.read_text())["views"]
        master = json.loads(mp.read_text())["image_id"]
        native = np.load(npz)["mvs_xyz"].astype(float)
        selected, rows = None, []
        for view in views:
            if view["role"] != "decision":
                continue
            row, data = view_audit(view, spec["domain"], native, cfg["xy_cell_size_m"])
            rows.append(row)
            inputs[view["maps"]["depth"]["path"]] = view["maps"]["depth"]["sha256"]
            if view["image_id"] == master:
                selected = row
                inputs[view["path"]] = view["sha256"]
                figure(view, region_id, spec["domain"], data, row, output / f"{region_id}_selected_support.png")
                np.savez_compressed(output / f"{region_id}_selected_masks.npz", **{
                    k: data[k] for k in ("exact", "xy", "below", "above", "crossing", "invalid", "before", "after", "ray_class")})
        if selected is None:
            raise ValueError("Frozen selected master absent")
        all_rows[region_id] = dict(selected=selected, decision_views=rows,
                  largest_exact_support_view=max(rows, key=lambda r: r["exact_xyz_endpoint_pixels"]),
                  largest_xy_support_view=max(rows, key=lambda r: r["xy_endpoint_pixels_ignoring_z"]),
                  native_mvs_z_m=quantiles(native[:, 2]))
        print(json.dumps({"region": region_id, "selected": selected}), flush=True)
    receipt = dict(status="IMAGE_SUPPORT_DIAGNOSTIC_COMPLETE", scientific_verdict=None, reference_accessed=False,
                   candidate_or_selection_modified=False, regions=all_rows, input_hashes=inputs,
                   scope=cfg["scope"], elapsed_seconds=time.monotonic() - started,
                   source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
                   source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"), container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                   outputs={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    write(output / "receipt.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output)
