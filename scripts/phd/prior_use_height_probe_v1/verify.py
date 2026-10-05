"""Synthetic arithmetic and support checks; no photographs or research labels."""
from __future__ import annotations

import json

import numpy as np

from src.stage2.colmap_io import Camera, Image
from scripts.phd.prior_use_height_probe_v1.photometry import measure_height_sweep


def _fixture():
    width, height = 80, 60
    cameras = {1: Camera(1, "PINHOLE", width, height,
                         np.array([40.0, 40.0, 40.5, 30.5]))}
    ids = [11, 17, 23]
    translations = ([4.0, 0.0, 0.0], [-4.0, 0.0, 0.0], [0.0, 4.0, 0.0])
    images = {iid: Image(iid, np.array([1.0, 0.0, 0.0, 0.0]),
                         np.array(t), 1, f"synthetic_{iid}")
              for iid, t in zip(ids, translations)}
    points, labels = [], []
    for group, ys in enumerate(([-6.0, -3.0], [3.0, 6.0])):
        for y in ys:
            for x in [-17.0, -12.0, -6.0, -3.0, 0.0, 3.0, 6.0, 12.0, 17.0]:
                points.append([x, y, 20.0])
                labels.append(group)
    xyz, groups = np.array(points), np.array(labels, dtype=np.int64)
    heights = np.array([-4.0, 0.0, 4.0])
    for array in (xyz, groups, heights):
        array.setflags(write=False)
    params = {"min_pair_angle_deg": 0.0, "max_pair_angle_deg": 90.0,
              "max_distance_ratio": 2.0, "min_points": 4, "min_gray_std": 0.01}
    return xyz, groups, heights, cameras, images, ids, params


def _project(point, camera, image):
    """Scalar pinhole reference independent of the imported projection helper."""
    x, y, z = image.R() @ point + image.tvec
    fx, fy, cx, cy = camera.params
    u, v = fx * x / z + cx, fy * y / z + cy
    inside = (z > 1e-6 and 1.0 <= u < camera.width - 2.0
              and 1.0 <= v < camera.height - 2.0)
    return float(u), float(v), bool(inside)


def _sample(gray, u, v):
    """Scalar interpolation through NumPy interp, with COLMAP pixel centres."""
    x, y = u - 0.5, v - 0.5
    row = int(np.floor(y))
    columns = np.arange(gray.shape[1])
    lower = np.interp(x, columns, gray[row])
    upper = np.interp(x, columns, gray[row + 1])
    return float(np.float32(np.interp(y, [row, row + 1], [lower, upper])))


def _reference_support(xyz, heights, cameras, images, pair):
    keep = []
    for row, point in enumerate(xyz):
        if all(_project(point + [0.0, 0.0, h],
                        cameras[images[iid].camera_id], images[iid])[2]
               for h in heights for iid in pair):
            keep.append(row)
    return np.asarray(keep, dtype=np.int64)


def verify_photometry() -> dict:
    """Return JSON-safe checks; raise AssertionError on any arithmetic failure."""
    xyz, groups, heights, cameras, images, ids, params = _fixture()
    immutable = [array.tobytes() for array in (xyz, groups, heights)]
    yy, xx = np.indices((60, 80), dtype=np.float32)
    gradient = 3.0 * xx + 5.0 * yy
    gains = {11: 1.0, 17: 2.5, 23: -1.75}
    affine = {iid: (gains[iid] * gradient + 400.0).astype(np.float32) for iid in ids}
    result = measure_height_sweep(xyz, groups, heights, cameras, images, ids,
                                  affine.__getitem__, params)
    assert result["rho"].shape == (3, 3, 2), "synthetic pair/group coverage drift"
    assert result["texture_ok"].all(), "affine fixture must have usable texture"
    for pi, (a, b) in enumerate(result["pair_view_ids"]):
        expected = np.sign(gains[int(a)] * gains[int(b)])
        np.testing.assert_allclose(result["rho"][:, pi], expected, atol=2e-6, rtol=0)

    boundary_removed = 0
    supports = []
    for pi, pair in enumerate(result["pair_view_ids"]):
        support = _reference_support(xyz, heights, cameras, images, pair)
        supports.append(support)
        lo, hi = result["support_offsets"][pi:pi + 2]
        np.testing.assert_array_equal(result["support_point_indices"][lo:hi], support)
        np.testing.assert_array_equal(result["count"][pi], np.bincount(groups[support], minlength=2))
        zero_support = _reference_support(xyz, np.array([0.0]), cameras, images, pair)
        boundary_removed += len(np.setdiff1d(zero_support, support))
    assert boundary_removed > 0, "fixture must lose some zero-height FOV points at another height"

    # A nonlinear raster supplies scores beyond the special +/-1 affine case.
    rasters = {
        11: (20.0 * np.sin(xx / 7.0) + yy + .01 * xx * yy).astype(np.float32),
        17: (15.0 * np.cos(yy / 9.0) + xx + .02 * xx * yy).astype(np.float32),
        23: (10.0 * np.sin((xx + yy) / 8.0) + .04 * xx * xx).astype(np.float32),
    }
    nonlinear = measure_height_sweep(xyz, groups, heights, cameras, images, ids,
                                     rasters.__getitem__, params)
    max_error, checked = 0.0, 0
    for pi, pair in enumerate(nonlinear["pair_view_ids"]):
        support = supports[pi]
        for hi, h in enumerate(heights):
            for group in range(2):
                native_rows = support[groups[support] == group]
                values = []
                for iid in pair:
                    image = images[iid]
                    camera = cameras[image.camera_id]
                    values.append(np.array([
                        _sample(rasters[iid], *_project(xyz[row] + [0.0, 0.0, h], camera, image)[:2])
                        for row in native_rows
                    ]))
                assert len(native_rows) >= params["min_points"]
                expected = float(np.corrcoef(values)[0, 1])
                actual = float(nonlinear["rho"][hi, pi, group])
                assert nonlinear["texture_ok"][hi, pi, group]
                np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0)
                max_error = max(max_error, abs(actual - expected))
                checked += 1

    flat = {iid: np.full((60, 80), 17.0, dtype=np.float32) for iid in ids}
    missing = measure_height_sweep(xyz, groups, heights, cameras, images, ids,
                                   flat.__getitem__, params)
    assert np.isnan(missing["rho"]).all(), "flat texture must remain missing, not zero correlation"
    assert not missing["texture_ok"].any()
    np.testing.assert_array_equal(missing["count"], result["count"])
    np.testing.assert_array_equal(missing["support_point_indices"], result["support_point_indices"])
    assert immutable == [array.tobytes() for array in (xyz, groups, heights)], "source input changed"
    return {
        "schema": "jointbuildgs.phd.prior_use_height_probe.synthetic_verification.v1",
        "status": "PASS",
        "checks": {
            "affine_intensity_positive_and_negative_correlation": "PASS",
            "fixed_native_support_including_fov_boundary": "PASS",
            "scalar_numpy_reference_all_pairs_groups_heights": "PASS",
            "missing_texture_is_nan_with_support_preserved": "PASS",
            "source_xyz_groups_heights_immutable": "PASS",
        },
        "scalar_reference_comparisons": checked,
        "maximum_absolute_score_difference": max_error,
        "zero_height_points_removed_by_full_sweep_fov": boundary_removed,
        "evidence_scope": "synthetic arithmetic and bookkeeping only; no photographs or accuracy claims",
        "scientific_verdict": None,
    }


if __name__ == "__main__":
    print(json.dumps(verify_photometry(), indent=2, allow_nan=False))
