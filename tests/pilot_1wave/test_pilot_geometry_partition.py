#!/usr/bin/env python3
"""Focused CPU tests for the first-wave geometry-only grouping partition."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import torch

from src.stage2.geometry_partition import (
    GeometryPartitionError,
    assign_partition_ids,
    load_xy_partitions,
    partition_logits,
)
from src.stage2.grouping import group_primitives_g2_partitioned


def feature(building_id: str, coordinates: list[list[list[float]]]) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "building_id": building_id,
            # These forbidden-looking values demonstrate that the loader never
            # reads semantic or height properties.
            "roof_type": "must-not-be-consumed",
            "lod2_z": 9999,
        },
        "geometry": {"type": "Polygon", "coordinates": coordinates},
    }


class GeometryPartitionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        payload = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:25832"}},
            "features": [
                feature(
                    "DEBY_LOD2_A",
                    [[[100.0, 200.0], [110.0, 200.0], [110.0, 210.0], [100.0, 210.0], [100.0, 200.0]]],
                ),
                feature(
                    "DEBY_LOD2_B",
                    [[[108.0, 200.0], [118.0, 200.0], [118.0, 210.0], [108.0, 210.0], [108.0, 200.0]]],
                ),
            ],
        }
        self.path = self.root / "footprints.geojson"
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ordered_overlap_and_outside_assignment(self) -> None:
        partitions = load_xy_partitions(self.path, ["A", "B"])
        local = torch.tensor(
            [
                [5.0, 5.0, -12.0],   # A only, after +[100,200]
                [9.0, 5.0, 123.0],   # A/B overlap: A wins caller order
                [16.0, 5.0, 0.0],    # B only
                [30.0, 5.0, 0.0],    # outside
                [0.0, 0.0, 0.0],     # numerical boundary belongs to A
            ],
            dtype=torch.float32,
        )
        ids = assign_partition_ids(local, partitions, world_offset_xy=[100.0, 200.0])
        self.assertEqual(ids.tolist(), [1, 1, 2, 0, 1])

        logits = partition_logits(ids, n_partitions=2)
        self.assertFalse(logits.requires_grad)
        self.assertEqual(logits.argmax(dim=-1).tolist(), ids.tolist())

    def test_partition_order_is_explicit_and_changes_overlap_owner(self) -> None:
        partitions = load_xy_partitions(self.path, ["B", "A"])
        ids = assign_partition_ids(
            torch.tensor([[9.0, 5.0, 0.0]]),
            partitions,
            world_offset_xy=[100.0, 200.0],
        )
        self.assertEqual(ids.tolist(), [1])
        self.assertEqual(partitions[0].building_id, "DEBY_LOD2_B")

    def test_requires_locked_crs_and_complete_unique_ids(self) -> None:
        with self.assertRaises(GeometryPartitionError):
            load_xy_partitions(self.path, ["A", "A"])
        with self.assertRaises(GeometryPartitionError):
            load_xy_partitions(self.path, ["missing"])
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["crs"]["properties"]["name"] = "EPSG:4326"
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(GeometryPartitionError):
            load_xy_partitions(self.path, ["A"])

    def test_g2_partitioned_does_not_use_or_merge_semantic_classes(self) -> None:
        centers = torch.tensor(
            [
                [0.00, 0.00, 1.00],
                [0.05, 0.00, 1.00],
                [0.00, 0.05, 1.00],
                [0.01, 0.01, 1.00],
                [0.06, 0.01, 1.00],
                [0.01, 0.06, 1.00],
                [5.00, 5.00, 1.00],  # outside every footprint partition
            ],
            dtype=torch.float32,
        )
        normals = torch.tensor([[0.0, 0.0, 1.0]]).repeat(len(centers), 1)
        scales = torch.ones((len(centers), 3), dtype=torch.float32)
        partitions = torch.tensor([1, 1, 1, 2, 2, 2, 0], dtype=torch.int64)
        groups, rep_n, rep_d = group_primitives_g2_partitioned(
            centers,
            normals,
            partitions,
            scales,
            voxel_size=2.0,
            min_group_size=2,
        )
        self.assertEqual(int(groups[-1]), -1)
        self.assertEqual(rep_n.shape, (2, 3))
        self.assertEqual(rep_d.shape, (2,))
        self.assertEqual(len(set(groups[:3].tolist())), 1)
        self.assertEqual(len(set(groups[3:6].tolist())), 1)
        self.assertNotEqual(int(groups[0]), int(groups[3]))


if __name__ == "__main__":
    unittest.main()
