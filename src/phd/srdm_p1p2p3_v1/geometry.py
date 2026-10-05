"""Calibrated single-pair input geometry; no current-reference access or fitting.

All input XYZ and camera translations are in the preserved scene-local frame.
Rectification uses zero distortion because the source images are undistorted.
The sparse projection is ALS self-visibility, not a currentness decision.
"""
from __future__ import annotations

from itertools import combinations, product
import math

import cv2
import numpy as np


def inside_box(xyz, bbox_min, bbox_max):
    xyz = np.asarray(xyz)
    return np.all((xyz >= bbox_min) & (xyz < bbox_max), axis=-1)


def box_points(bbox_min, bbox_max, count=2):
    lo, hi = np.asarray(bbox_min, float), np.asarray(bbox_max, float)
    if lo.shape != (3,) or hi.shape != (3,) or not np.all(hi > lo) or count < 2:
        raise ValueError("A finite nonempty XYZ box and at least two samples are required")
    if not np.isfinite(np.r_[lo, hi]).all():
        raise ValueError("Nonfinite ROI")
    return np.array(list(product(*(np.linspace(a, b, count) for a, b in zip(lo, hi)))))


def project(xyz, K, R, t):
    camera_xyz = np.asarray(xyz, float) @ np.asarray(R, float).T + np.asarray(t, float)
    homogeneous = camera_xyz @ np.asarray(K, float).T
    uv = np.full((len(camera_xyz), 2), np.nan)
    good = np.isfinite(camera_xyz).all(axis=1) & (camera_xyz[:, 2] > 0)
    uv[good] = homogeneous[good, :2] / homogeneous[good, 2:3]
    return uv, camera_xyz[:, 2]


def camera_center(view):
    return -np.asarray(view["R"], float).T @ np.asarray(view["t"], float)


def rectification(left, right, alpha=0.0):
    size = (int(left["width"]), int(left["height"]))
    if size != (int(right["width"]), int(right["height"])):
        raise ValueError("Pair image sizes differ")
    Kl, Kr = np.asarray(left["K"], float), np.asarray(right["K"], float)
    Rl, Rr = np.asarray(left["R"], float), np.asarray(right["R"], float)
    tl, tr = np.asarray(left["t"], float), np.asarray(right["t"], float)
    relative_R = Rr @ Rl.T
    relative_t = tr - relative_R @ tl
    if np.linalg.norm(relative_t) < 1e-9:
        raise ValueError("Zero stereo baseline")
    R1, R2, P1, P2, Q, valid1, valid2 = cv2.stereoRectify(
        Kl, np.zeros(5), Kr, np.zeros(5), size, relative_R, relative_t,
        flags=cv2.CALIB_ZERO_DISPARITY, alpha=float(alpha), newImageSize=size,
    )
    if abs(P2[1, 3]) > abs(P2[0, 3]):
        raise ValueError("Vertical rectification is outside this horizontal-disparity adapter")
    if not all(np.isfinite(a).all() for a in (R1, R2, P1, P2, Q)):
        raise ValueError("Nonfinite rectification")
    return dict(R1=R1, R2=R2, P1=P1, P2=P2, Q=Q,
                valid_rect_left=list(valid1), valid_rect_right=list(valid2),
                relative_R=relative_R, relative_t=relative_t)


def rectified_projection(xyz, view, Rrect, P):
    R = np.asarray(Rrect) @ np.asarray(view["R"], float)
    t = np.asarray(Rrect) @ np.asarray(view["t"], float)
    # P2's translation is already represented by the right camera pose.
    # Adding its fourth column here would apply the stereo baseline twice.
    return project(xyz, np.asarray(P)[:, :3], R, t)


def in_image(uv, depth, width, height):
    return (np.isfinite(uv).all(axis=1) & (depth > 0) &
            (uv[:, 0] >= 0) & (uv[:, 0] < width - 1) &
            (uv[:, 1] >= 0) & (uv[:, 1] < height - 1))


def clipped_projection_area(uv, width, height):
    if not np.isfinite(uv).all() or len(uv) < 3:
        return 0.0
    hull = cv2.convexHull(np.asarray(uv, np.float32))
    frame = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    area, _ = cv2.intersectConvexConvex(hull, frame)
    return max(0.0, float(area))


def select_pair(views, bbox_min, bbox_max, settings):
    """Rank every eligible train-only pair using fixed camera/ROI geometry.

    No image pixels, ALS points, MVS geometry, or evaluation reference is read.
    A fixed volume lattice measures common projected coverage. The rank is
    coverage * sin(center-ray angle) * smaller clipped rectified ROI area.
    """
    samples = box_points(bbox_min, bbox_max, int(settings["grid_axis_count"]))
    corners = box_points(bbox_min, bbox_max)
    center = (np.asarray(bbox_min) + np.asarray(bbox_max)) / 2
    minimum, maximum = float(settings["min_angle_deg"]), float(settings["max_angle_deg"])
    if not 0 < minimum < maximum < 90:
        raise ValueError("Invalid fixed stereo angle interval")
    ledger, eligible = [], []
    for a, b in combinations(sorted(views, key=lambda v: int(v["image_id"])), 2):
        item = {"input_ids": [int(a["image_id"]), int(b["image_id"])]}
        va, vb = center - camera_center(a), center - camera_center(b)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            item["status"] = "ROI_CENTER_AT_CAMERA"
            ledger.append(item)
            continue
        angle = math.degrees(math.acos(float(np.clip(va @ vb / denom, -1, 1))))
        item["angle_deg"] = angle
        if not minimum <= angle <= maximum:
            item["status"] = "OUTSIDE_FIXED_ANGLE_INTERVAL"
            ledger.append(item)
            continue
        try:
            rect = rectification(a, b, settings["rectification_alpha"])
            # Standardize to positive left-minus-right disparity.
            if rect["P2"][0, 3] > 0:
                a, b = b, a
                rect = rectification(a, b, settings["rectification_alpha"])
            if rect["P2"][0, 3] >= 0:
                raise ValueError("Nonpositive disparity baseline")
            ua, za = rectified_projection(samples, a, rect["R1"], rect["P1"])
            ub, zb = rectified_projection(samples, b, rect["R2"], rect["P2"])
            ca, cza = rectified_projection(corners, a, rect["R1"], rect["P1"])
            cb, czb = rectified_projection(corners, b, rect["R2"], rect["P2"])
            if (cza <= 0).any() or (czb <= 0).any():
                raise ValueError("ROI crosses a rectified camera plane")
            width, height = int(a["width"]), int(a["height"])
            # Require actual original sensor coverage as well as new frame bounds.
            oa, oza = project(samples, a["K"], a["R"], a["t"])
            ob, ozb = project(samples, b["K"], b["R"], b["t"])
            common = (in_image(ua, za, width, height) & in_image(ub, zb, width, height) &
                      in_image(oa, oza, width, height) & in_image(ob, ozb, width, height))
            coverage = float(common.mean())
            area = min(clipped_projection_area(ca, width, height), clipped_projection_area(cb, width, height))
            score = coverage * math.sin(math.radians(angle)) * area
            if not score > 0:
                raise ValueError("No common projected ROI support")
            item.update(status="ELIGIBLE", left_id=int(a["image_id"]), right_id=int(b["image_id"]),
                        common_lattice_fraction=coverage, minimum_roi_area_px2=area, score=score)
            eligible.append((score, -min(item["input_ids"]), -max(item["input_ids"]), a, b, rect, item))
        except (ValueError, cv2.error) as error:
            item.update(status="INELIGIBLE_RECTIFICATION", reason=str(error))
        ledger.append(item)
    if not eligible:
        raise ValueError("No eligible stereo pair under the frozen geometry-only rule")
    selected = max(eligible, key=lambda row: row[:3])
    return selected[3], selected[4], selected[5], selected[6], ledger


def rectify_rgb(rgb, K, Rrect, P):
    height, width = rgb.shape[:2]
    if rgb.dtype != np.uint8 or rgb.shape != (height, width, 3):
        raise ValueError("Expected native uint8 RGB image")
    mx, my = cv2.initUndistortRectifyMap(np.asarray(K, float), np.zeros(5), Rrect,
                                      P[:, :3], (width, height), cv2.CV_32FC1)
    valid = (np.isfinite(mx) & np.isfinite(my) & (mx >= 0) & (my >= 0) &
             (mx < width - 1) & (my < height - 1))
    image = cv2.remap(rgb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return image, valid


def disparity_bounds(bbox_min, bbox_max, left, right, rect, margin):
    corners = box_points(bbox_min, bbox_max)
    uv1, z1 = rectified_projection(corners, left, rect["R1"], rect["P1"])
    uv2, z2 = rectified_projection(corners, right, rect["R2"], rect["P2"])
    if (z1 <= 0).any() or (z2 <= 0).any() or not np.isfinite(uv1 - uv2).all():
        raise ValueError("ROI disparity range cannot be bounded in front of the stereo pair")
    if np.max(abs(uv1[:, 1] - uv2[:, 1])) > 1e-5:
        raise ValueError("Nonhorizontal epipolar geometry")
    values = uv1[:, 0] - uv2[:, 0]
    if values.min() <= 0 or margin < 0:
        raise ValueError("Positive disparity and nonnegative bound margin required")
    return max(0, math.floor(float(values.min())) - int(margin)), math.ceil(float(values.max())) + int(margin)


def roi_projection_mask(bbox_min, bbox_max, left, rect, shape):
    uv, depth = rectified_projection(box_points(bbox_min, bbox_max), left, rect["R1"], rect["P1"])
    if (depth <= 0).any() or not np.isfinite(uv).all():
        raise ValueError("ROI projection invalid")
    hull = cv2.convexHull(uv.astype(np.float32))
    height, width = shape
    frame = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    area, clipped = cv2.intersectConvexConvex(hull, frame)
    mask = np.zeros(shape, np.uint8)
    if area > 0 and clipped is not None:
        cv2.fillConvexPoly(mask, np.rint(clipped).astype(np.int32), 1)
    return mask.astype(bool)


def _zbuffer_winners(pixel, depth, indices, width):
    if not len(indices):
        return indices
    key = pixel[indices, 1] * width + pixel[indices, 0]
    order = np.lexsort((indices, depth[indices], key))
    sorted_key = key[order]
    return indices[order[np.r_[True, sorted_key[1:] != sorted_key[:-1]]]]


def sparse_als_projection(xyz, source_row, source_file, left, right, rect,
                          left_valid, right_valid, minimum, maximum):
    """Nearest-point z buffers in both images, with complete raw-row provenance.

    State 0: invalid/behind/out of either image, 2: loses either ALS z buffer,
    3: emitted sparse seed, 4: outside the fixed ROI disparity search interval.
    This point raster cannot certify visibility against the current scene.
    """
    xyz, source_row, source_file = np.asarray(xyz), np.asarray(source_row), np.asarray(source_file)
    if xyz.shape != (len(source_row), 3) or len(source_file) != len(xyz) or not np.isfinite(xyz).all():
        raise ValueError("Finite ALS coordinates and equal-length source identities required")
    height, width = left_valid.shape
    if right_valid.shape != left_valid.shape:
        raise ValueError("Rectified mask sizes differ")
    uv1, z1 = rectified_projection(xyz, left, rect["R1"], rect["P1"])
    uv2, z2 = rectified_projection(xyz, right, rect["R2"], rect["P2"])
    p1, p2 = np.zeros_like(uv1, dtype=np.int64), np.zeros_like(uv2, dtype=np.int64)
    finite = np.isfinite(uv1).all(axis=1) & np.isfinite(uv2).all(axis=1)
    p1[finite], p2[finite] = np.rint(uv1[finite]).astype(np.int64), np.rint(uv2[finite]).astype(np.int64)
    valid = finite & (z1 > 0) & (z2 > 0)
    for p in (p1, p2):
        valid &= (p[:, 0] >= 0) & (p[:, 0] < width) & (p[:, 1] >= 0) & (p[:, 1] < height)
    indices = np.flatnonzero(valid)
    valid[indices] &= left_valid[p1[indices, 1], p1[indices, 0]] & right_valid[p2[indices, 1], p2[indices, 0]]
    indices = np.flatnonzero(valid)
    winners_left = _zbuffer_winners(p1, z1, indices, width)
    winners_right = _zbuffer_winners(p2, z2, indices, width)
    winners = np.intersect1d(winners_left, winners_right, assume_unique=True)
    state = np.zeros(len(xyz), np.int8)
    state[indices] = 2
    disparity = uv1[:, 0] - uv2[:, 0]
    bounded = np.isfinite(disparity[winners]) & (disparity[winners] >= minimum) & (disparity[winners] <= maximum)
    state[winners[~bounded]] = 4
    winners = winners[bounded]
    state[winners] = 3
    sparse = np.full((height, width), np.nan, np.float32)
    mapping = np.full((height, width), -1, np.int64)
    sparse[p1[winners, 1], p1[winners, 0]] = disparity[winners]
    mapping[p1[winners, 1], p1[winners, 0]] = winners
    rows = np.full((height, width), -1, np.int64)
    files = np.full((height, width), -1, np.int16)
    rows[p1[winners, 1], p1[winners, 0]] = source_row[winners]
    files[p1[winners, 1], p1[winners, 0]] = source_file[winners]
    return dict(sparse_disparity=sparse, sparse_source_index=mapping,
                sparse_source_row=rows, sparse_source_file_index=files,
                als_pixel_xy=uv1, als_right_pixel_xy=uv2,
                als_rectified_depth=z1, als_projection_state=state)


def reproject_disparity(disparity, Q, rectified_left_to_world_R, rectified_left_to_world_t):
    """Return full HxWx3 local XYZ; nonfinite/nonpositive disparity is NaN."""
    disparity = np.asarray(disparity, np.float32)
    xyz = cv2.reprojectImageTo3D(disparity, np.asarray(Q, float)).astype(np.float64)
    xyz = xyz @ np.asarray(rectified_left_to_world_R, float).T + np.asarray(rectified_left_to_world_t, float)
    invalid = ~np.isfinite(disparity) | (disparity <= 0) | ~np.isfinite(xyz).all(axis=2)
    xyz[invalid] = np.nan
    return xyz
