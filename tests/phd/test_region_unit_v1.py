from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import numpy as np

from scripts.phd.region_unit_v1 import run as t0


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/phd/region_unit_v1/run_v1.json"

PROFILE = {
    "cell_size_m": 0.25,
    "normal_radius_m": 1.0,
    "normal_min_neighbors": 8,
    "seed_max_surface_variation": 0.02,
    "grow_max_normal_angle_deg": 15.0,
    "grow_max_plane_distance_m": 0.15,
    "grow_radius_m": 0.6,
    "refit_condition_ratio": 0.05,
    "minimum_unit_area_m2": 1.0,
    "maximum_unit_extent_m": 8.0,
    "rough_component_radius_m": 0.6,
    "rough_attach_radius_m": 1.0,
    "pair_normal_half_length_m": 3.0,
    "pair_rough_radius_m": 1.0,
    "pair_inplane_radius_m": 1.0,
    "prior_layer_split_offset_m": 0.30,
    "prior_layer_min_cells": 4,
    "resolver_radius_m": 1.0,
    "adjacency_radius_m": 0.6,
}
UP = np.array([0.0, 0.0, 1.0])


def plane_xy(x0, x1, y0, y1, z, spacing, hole=None):
    xs = np.arange(x0, x1, spacing)
    ys = np.arange(y0, y1, spacing)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    pts = np.column_stack((gx.ravel(), gy.ravel(), np.full(gx.size, float(z))))
    if hole is not None:
        hx0, hx1, hy0, hy1 = hole
        keep = ~((pts[:, 0] >= hx0) & (pts[:, 0] < hx1) & (pts[:, 1] >= hy0) & (pts[:, 1] < hy1))
        pts = pts[keep]
    return pts


def wall_x(x, y0, y1, z0, z1, spacing):
    ys = np.arange(y0, y1, spacing)
    zs = np.arange(z0, z1, spacing)
    gy, gz = np.meshgrid(ys, zs, indexing="ij")
    return np.column_stack((np.full(gy.size, float(x)), gy.ravel(), gz.ravel()))


def domain(x, y, z):
    return {"x": list(x), "y": list(y), "z": list(z)}


def synthetic_scene():
    """MVS: ground with a hole, roof, two walls.  ALS: ground, slightly higher old roof, a demolished high shed."""
    mvs = np.concatenate([
        plane_xy(0, 20, 0, 20, 0.0, 0.2, hole=(5, 15, 5, 15)),
        plane_xy(5, 15, 5, 15, 6.0, 0.2),
        wall_x(5.0, 5, 15, 0, 6, 0.2),
        wall_x(15.0, 5, 15, 0, 6, 0.2),
    ])
    als = np.concatenate([
        plane_xy(0, 20, 0, 20, 0.02, 0.5, hole=(5, 15, 5, 15)),
        plane_xy(5, 15, 5, 15, 6.3, 0.5),
        plane_xy(16, 19, 1, 4, 9.0, 0.5),
    ])
    return mvs.astype(np.float32), als.astype(np.float32), domain((-1, 21), (-1, 21), (-1, 12))


class RegionUnitV1Test(unittest.TestCase):
    def test_config_contract_and_prohibited_tokens(self):
        cfg = t0.load_config(CONFIG)
        self.assertIsNone(cfg["scientific_verdict"])
        self.assertEqual(cfg["algorithm"]["selected_profile"], "base")
        self.assertEqual(cfg["inputs"]["gravity_checkpoint"]["use"], "DESCRIPTIVE_TILT_ONLY_NOT_SEGMENTATION")
        broken = copy.deepcopy(json.loads(CONFIG.read_text(encoding="utf-8")))
        broken["inputs"]["partitions"]["mvs"]["relative_path"] = "partition/lod2/x.bin"
        path = Path("/tmp/region_unit_broken.json")
        path.write_text(json.dumps(broken), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "prohibited input token"):
            t0.load_config(path)

    def test_voxelize_covers_every_point_deterministically(self):
        rng = np.random.default_rng(0)
        pts = rng.uniform(0, 5, size=(2000, 3))
        first = t0.voxelize(pts, np.zeros(3), 0.25)
        second = t0.voxelize(pts[::-1].copy(), np.zeros(3), 0.25)
        self.assertEqual(len(first["point_cell"]), len(pts))
        self.assertEqual(int(first["counts"].sum()), len(pts))
        np.testing.assert_array_equal(first["keys"], second["keys"])
        np.testing.assert_allclose(first["centroids"], second["centroids"])
        self.assertTrue(np.all(np.diff(first["keys"][:, 0] * 10**6 + first["keys"][:, 1] * 10**3 + first["keys"][:, 2]) > 0))

    def test_normals_and_variation_on_horizontal_plane(self):
        cells = t0.voxelize(plane_xy(0, 6, 0, 6, 1.0, 0.2), np.zeros(3), 0.25)
        normals, variation, valid = t0.estimate_normals(cells["centroids"], 1.0, 8)
        self.assertTrue(np.all(valid))
        self.assertTrue(np.all(np.abs(normals[:, 2]) > 0.999))
        self.assertTrue(np.all(normals[:, 2] > 0))
        self.assertLess(float(np.nanmax(variation)), 1e-6)

    def test_region_growing_separates_roof_wall_and_ground(self):
        pts = np.concatenate([plane_xy(0, 12, 0, 12, 0.0, 0.2, hole=(4, 8, 4, 8)),
                              plane_xy(4, 8, 4, 8, 4.0, 0.2), wall_x(4.0, 4, 8, 0, 4, 0.2)])
        cells = t0.voxelize(pts, np.array([-1.0, -1.0, -1.0]), 0.25)
        normals, variation, valid = t0.estimate_normals(cells["centroids"], 1.0, 8)
        segment, segments = t0.region_growing(cells["centroids"], normals, variation, valid, PROFILE)
        self.assertGreaterEqual(len(segments), 3)
        # the three largest segments must be one horizontal ground, one horizontal roof, one vertical wall
        largest = sorted(segments, key=lambda s: -len(s["members"]))[:3]
        tilts = sorted(round(t0.tilt_from_up(s["normal"], UP)) for s in largest)
        self.assertEqual(tilts[:2], [0, 0])
        self.assertEqual(tilts[2], 90)
        heights = sorted(round(float(cells["centroids"][s["members"], 2].mean()), 1) for s in largest if abs(s["normal"][2]) > 0.9)
        self.assertEqual(heights, [0.0, 4.0])
        # D-1b step 2: crease cells with blurred normals are recovered by the distance test
        self.assertLess(int(np.count_nonzero(segment == 0)), 12)
        roof = [s for s in largest if abs(s["normal"][2]) > 0.9 and cells["centroids"][s["members"], 2].mean() > 3.5][0]
        self.assertGreaterEqual(len(roof["members"]), 240)  # 4 x 4 m at 0.25 m = 256 cells, minus the crease line

    def test_projected_area_of_square_plane(self):
        pts = plane_xy(0, 4, 0, 4, 0.0, 0.25)
        centre, normal, e1, e2 = t0.fit_plane(pts)
        area = t0.projected_area(pts, centre, e1, e2, 0.25)
        self.assertAlmostEqual(area, 16.0, delta=1.5)

    def test_split_caps_extent_and_keeps_children_connected(self):
        pts = plane_xy(0, 20, 0, 4, 0.0, 0.25)
        members = np.arange(len(pts))
        children = t0.split_segment(members, pts, PROFILE)
        self.assertGreater(len(children), 1)
        total = np.concatenate([c["members"] for c in children])
        self.assertEqual(len(np.unique(total)), len(pts))
        for child in children:
            sub = pts[child["members"]]
            self.assertLessEqual(float(np.ptp(sub[:, 0])), 2 * PROFILE["maximum_unit_extent_m"] + 1e-6)
            self.assertEqual(len(np.unique(t0.component_labels(sub, PROFILE["grow_radius_m"]))), 1)
            self.assertEqual(child["split_child"], 1)

    def test_rough_noise_becomes_rough_unit_with_full_coverage(self):
        rng = np.random.default_rng(1)
        noise = rng.uniform(0, 3, size=(4000, 3))
        pts = np.concatenate([plane_xy(4, 10, 0, 6, 0.0, 0.2), noise])
        cells = t0.voxelize(pts, np.array([-1.0, -1.0, -1.0]), 0.25)
        normals, variation, valid = t0.estimate_normals(cells["centroids"], 1.0, 8)
        segment_of, role, segments = t0.unitize_source(cells["centroids"], normals, variation, valid, PROFILE)
        self.assertTrue(np.all(segment_of > 0))
        kinds = {s["kind"] for s in segments}
        self.assertIn(t0.KIND_ROUGH, kinds)
        self.assertIn(t0.KIND_PLANAR, kinds)

    def test_rough_components_respect_extent_cap(self):
        rng = np.random.default_rng(2)
        blob = np.column_stack((rng.uniform(0, 30, 20000), rng.uniform(0, 4, 20000), rng.uniform(0, 3, 20000)))
        cells = t0.voxelize(blob, np.array([-1.0, -1.0, -1.0]), 0.25)
        normals, variation, valid = t0.estimate_normals(cells["centroids"], 1.0, 8)
        segment_of, role, segments = t0.unitize_source(cells["centroids"], normals, variation, valid, PROFILE)
        self.assertTrue(np.all(segment_of > 0))
        rough = [s for s in segments if s["kind"] == t0.KIND_ROUGH]
        self.assertGreater(len(rough), 2)
        for item in rough:
            pts = cells["centroids"][item["all_members"]]
            self.assertLessEqual(float(np.max(np.ptp(pts, axis=0))), 2 * PROFILE["maximum_unit_extent_m"] + 1e-6)

    def test_pairing_window_matches_m3c2_projection(self):
        mvs = plane_xy(0, 10, 0, 10, 0.0, 0.2)
        near = plane_xy(0, 10, 0, 10, 0.5, 0.5)
        far = plane_xy(2, 6, 2, 6, 5.0, 0.5)
        als = np.concatenate([near, far])
        built = t0.build_region_units(mvs.astype(np.float32), als.astype(np.float32),
                                      domain((-1, 11), (-1, 11), (-1, 7)), PROFILE, UP, "test")
        cells, units = built["cells"], built["units"]
        als_cells = cells[cells["source"] == t0.SOURCE_ALS]
        near_mask = als_cells["z"] < 2.0
        near_units = units[als_cells["unit_id"][near_mask] - 1]
        self.assertTrue(np.all(near_units["primary_source"] == t0.SOURCE_MVS))
        self.assertTrue(np.all(np.abs(als_cells["pair_distance_m"][near_mask] - 0.5) < 0.05))
        rules = als_cells["pair_rule"][near_mask]
        self.assertGreater(float(np.mean(rules == t0.PAIR_PLANAR_ALS_NORMAL)), 0.8)
        self.assertTrue(np.all(np.isin(rules, [t0.PAIR_PLANAR_ALS_NORMAL, t0.PAIR_PLANAR_SEGMENT_NORMAL])))
        far_units = units[als_cells["unit_id"][~near_mask] - 1]
        self.assertTrue(np.all(far_units["primary_source"] == t0.SOURCE_ALS))
        self.assertTrue(np.all(far_units["kind"] == t0.KIND_PLANAR))
        self.assertTrue(np.all(np.isnan(als_cells["pair_distance_m"][~near_mask])))
        mvs_units = units[units["primary_source"] == t0.SOURCE_MVS]
        self.assertGreater(float(np.nanmin(mvs_units["prior_support_fraction"])), 0.5)

    def test_full_pipeline_is_covering_deterministic_and_lineaged(self):
        mvs, als, dom = synthetic_scene()
        first = t0.build_region_units(mvs, als, dom, PROFILE, UP, "test")
        second = t0.build_region_units(mvs, als, dom, PROFILE, UP, "test")
        for key in ("cells", "units", "adjacency"):
            self.assertEqual(t0.array_digest(first[key]), t0.array_digest(second[key]))
        cells, units, adjacency = first["cells"], first["units"], first["adjacency"]
        self.assertTrue(np.all(cells["unit_id"] > 0))
        np.testing.assert_array_equal(units["unit_id"], np.arange(1, len(units) + 1))
        self.assertEqual(len(set(map(bytes, units["unit_uid"]))), len(units))
        self.assertTrue(np.all(units["component_count"] == 1))
        self.assertTrue(np.all(adjacency["unit_a"] < adjacency["unit_b"]))
        self.assertTrue(np.all(adjacency["contact_mvs_mvs"] + adjacency["contact_als_als"] + adjacency["contact_cross"] == adjacency["contact_pairs"]))
        self.assertGreater(int(adjacency["contact_mvs_mvs"].sum()), 0)
        self.assertEqual(len(first["point_cell_mvs"]), len(mvs))
        self.assertEqual(len(first["point_cell_als"]), len(als))
        self.assertTrue(np.all(cells["source"][first["point_cell_als"]] == t0.SOURCE_ALS))
        acc = first["accounting"]
        self.assertEqual(acc["criterion_2_coverage"]["cells_unassigned"], 0)
        self.assertGreaterEqual(acc["criterion_4_pairing"]["prior_only_units"], 1)
        self.assertGreater(acc["criterion_4_pairing"]["als_cells_paired"], 0)
        self.assertEqual(acc["criterion_3_scale"]["units_over_extent_cap"], 0)
        # every unit below the minimum area is flagged small (also after crease absorption re-fits)
        area = units["area_m2"]
        self.assertTrue(np.all(units["small"][area < PROFILE["minimum_unit_area_m2"]] == 1))
        layered = (units["primary_source"] == 0) & (np.nan_to_num(units["prior_offset_spread_m"]) > PROFILE["prior_layer_split_offset_m"])
        self.assertTrue(np.all((units["mixed_prior"][layered] == 1) | (units["split_reason"][layered] == t0.SPLIT_PRIOR_LAYER)))
        # walls exist as vertical MVS units, roof and ground as horizontal
        tilts = units["tilt_from_up_deg"][(units["primary_source"] == 0) & (units["kind"] == 0)]
        self.assertTrue(np.any(tilts > 80))
        self.assertTrue(np.any(tilts < 5))

    def test_wall_does_not_capture_als_roof_when_mvs_roof_is_missing(self):
        # H_M case: MVS has ground + walls but no roof; the ALS roof must become a prior-only unit
        mvs = np.concatenate([plane_xy(0, 20, 0, 20, 0.0, 0.2, hole=(5, 15, 5, 15)),
                              wall_x(5.0, 5, 15, 0, 6, 0.2), wall_x(15.0, 5, 15, 0, 6, 0.2)])
        als = np.concatenate([plane_xy(0, 20, 0, 20, 0.02, 0.5, hole=(5, 15, 5, 15)), plane_xy(5.5, 14.5, 5.5, 14.5, 6.0, 0.5)])
        built = t0.build_region_units(mvs.astype(np.float32), als.astype(np.float32),
                                      domain((-1, 21), (-1, 21), (-1, 8)), PROFILE, UP, "test")
        cells, units = built["cells"], built["units"]
        roof = cells[(cells["source"] == t0.SOURCE_ALS) & (cells["z"] > 5.0)]
        roof_units = units[roof["unit_id"] - 1]
        self.assertGreater(float(np.mean(roof_units["primary_source"] == t0.SOURCE_ALS)), 0.9)
        self.assertGreater(float(np.mean(roof["pair_rule"] == t0.PAIR_NONE)), 0.9)
        # ALS ground next to the walls stays paired to horizontal MVS ground units, never to a wall unit
        ground = cells[(cells["source"] == t0.SOURCE_ALS) & (cells["z"] < 1.0)]
        ground_units = units[ground["unit_id"] - 1]
        paired_ground = ground_units[ground["pair_rule"] > 0]
        self.assertTrue(np.all(paired_ground["tilt_from_up_deg"] < 10))

    def test_prior_layer_split_separates_demolished_shed(self):
        mvs = plane_xy(0, 20, 0, 20, 0.0, 0.2)
        als = np.concatenate([plane_xy(0, 20, 0, 20, 0.02, 0.5, hole=(8, 12, 8, 12)), plane_xy(8, 12, 8, 12, 2.5, 0.5)])
        built = t0.build_region_units(mvs.astype(np.float32), als.astype(np.float32),
                                      domain((-1, 21), (-1, 21), (-1, 4)), PROFILE, UP, "test")
        cells, units = built["cells"], built["units"]
        shed_cells = cells[(cells["source"] == t0.SOURCE_ALS) & (cells["z"] > 2.0)]
        self.assertTrue(np.all(shed_cells["pair_rule"] > 0))
        shed_units = np.unique(shed_cells["unit_id"])
        self.assertEqual(len(shed_units), 1)
        shed = units[shed_units[0] - 1]
        self.assertEqual(int(shed["primary_source"]), t0.SOURCE_MVS)
        self.assertEqual(int(shed["split_reason"]), t0.SPLIT_PRIOR_LAYER)
        self.assertAlmostEqual(float(shed["prior_offset_median_m"]), 2.5, delta=0.1)
        self.assertAlmostEqual(float(shed["area_m2"]), 16.0, delta=6.0)
        ground = units[(units["primary_source"] == t0.SOURCE_MVS) & (units["unit_id"] != shed["unit_id"])]
        self.assertTrue(np.all(np.abs(np.nan_to_num(ground["prior_offset_median_m"])) < 0.1))
        self.assertTrue(np.all(units["tilt_from_up_deg"][(units["primary_source"] == 0) & (units["kind"] == 0)] < 10))
        self.assertEqual(built["accounting"]["criterion_3b_prior_layer"]["mvs_units_layered_but_unflagged"], 0)
        # D-1h: the shed prior side (2.5 m above the MVS plane) resolves to the shed unit
        resolver = t0.UnitResolver(cells, units, PROFILE["resolver_radius_m"])
        ids, dist = resolver.resolve(np.column_stack((shed_cells["x"], shed_cells["y"], shed_cells["z"])))
        self.assertTrue(np.all(ids == shed["unit_id"]))
        self.assertTrue(np.all(dist == 0))

    def test_thin_planar_slivers_keep_the_parent_normal(self):
        # a 24.1 m ground strip leaves a one-row remainder after the 8 m grid: it must not become a 'wall'
        pts = plane_xy(0, 24.1, 0, 4, 0.0, 0.25)
        rng = np.random.default_rng(5)
        pts[:, 2] += rng.normal(0, 0.02, len(pts))
        cells = t0.voxelize(pts, np.array([-1.0, -1.0, -1.0]), 0.25)
        normals, variation, valid = t0.estimate_normals(cells["centroids"], 1.0, 8)
        segment_of, role, segments = t0.unitize_source(cells["centroids"], normals, variation, valid, PROFILE)
        for item in segments:
            if item["kind"] == t0.KIND_PLANAR:
                centre, normal, _, _ = t0.reference_frame(cells["centroids"][item["members"]], item["parent_normal"], PROFILE)
                self.assertLess(t0.tilt_from_up(normal, UP), 10.0)

    def test_adjusted_rand_index_matches_known_values(self):
        a = np.array([0, 0, 1, 1, 2, 2]); b = np.array([1, 1, 0, 0, 5, 5]); c = np.array([0, 0, 0, 1, 1, 1])
        self.assertAlmostEqual(t0.adjusted_rand_index(a, b), 1.0)
        self.assertLess(t0.adjusted_rand_index(a, c), 0.5)
        self.assertAlmostEqual(t0.adjusted_rand_index(a, np.zeros(6, dtype=int)), 0.0)

    def test_input_row_permutation_gives_identical_units(self):
        mvs, als, dom = synthetic_scene()
        rng = np.random.default_rng(3)
        first = t0.build_region_units(mvs, als, dom, PROFILE, UP, "test")
        second = t0.build_region_units(mvs[rng.permutation(len(mvs))], als[rng.permutation(len(als))], dom, PROFILE, UP, "test")
        self.assertEqual(set(map(bytes, first["units"]["unit_uid"])), set(map(bytes, second["units"]["unit_uid"])))
        self.assertEqual(t0.array_digest(first["cells"]), t0.array_digest(second["cells"]))

    def test_relation_cores_map_to_units_by_cell_key(self):
        mvs, als, dom = synthetic_scene()
        cores = {"row": np.array([0, 1, 2], dtype=np.uint32),
                 "xyz": np.array([[1.0, 1.0, 0.0], [10.0, 10.0, 6.0], [17.0, 2.0, 9.0]], dtype=np.float32),
                 "source": np.array([0, 0, 1]), "relation_class": np.array([1, 2, 4])}
        built = t0.build_region_units(mvs, als, dom, PROFILE, UP, "test", cores)
        core_map = built["core_map"]
        self.assertTrue(np.all(core_map["unit_id"] > 0))
        self.assertTrue(np.all(built["cells"]["source"][core_map["cell_index"]] == core_map["core_source"]))
        self.assertEqual(int(built["units"]["core_count_total"].sum()), 3)
        self.assertEqual(int(built["units"]["core_count_class_4"].sum()), 1)
        self.assertIn("4", built["accounting"]["criterion_4_pairing"]["bank_core_crosstab"])

    def test_resolver_maps_cells_to_own_unit_and_flags_far_points(self):
        mvs, als, dom = synthetic_scene()
        built = t0.build_region_units(mvs, als, dom, PROFILE, UP, "test")
        cells, units = built["cells"], built["units"]
        resolver = t0.UnitResolver(cells, units, PROFILE["resolver_radius_m"])
        ids, dist = resolver.resolve(np.column_stack((cells["x"], cells["y"], cells["z"])))
        np.testing.assert_array_equal(ids, cells["unit_id"])
        self.assertTrue(np.all(dist == 0))
        jitter = np.column_stack((cells["x"], cells["y"], cells["z"])) + 0.05
        ids_j, _ = resolver.resolve(jitter)
        self.assertGreater(float(np.mean(ids_j == cells["unit_id"])), 0.95)
        far_ids, far_dist = resolver.resolve(np.array([[100.0, 100.0, 100.0]]))
        self.assertEqual(int(far_ids[0]), 0)
        self.assertTrue(np.isnan(far_dist[0]))


if __name__ == "__main__":
    unittest.main()
