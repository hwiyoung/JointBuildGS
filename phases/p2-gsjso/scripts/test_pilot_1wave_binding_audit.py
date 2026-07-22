#!/usr/bin/env python3
"""CPU-only synthetic tests for P1W-BINDING-AUDIT."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, mapping


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pilot_1wave_binding_audit as audit


IDS = ("BUILDING_A", "BUILDING_B", "BUILDING_C")
CONDITION = "01"
SEED = 1001
TRANSFORM = {"scale": [0.1, 0.1, 0.1], "translate": [100.0, 200.0, 0.0]}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": audit.sha256_file(path)}


def repo_record(path: Path, *, include_size: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        "path": audit.repo_relative(path),
        "sha256": audit.sha256_file(path),
    }
    if include_size:
        value["size"] = path.stat().st_size
    return value


def polygons() -> dict[str, Polygon | MultiPolygon]:
    return {
        "BUILDING_A": Polygon(
            [(100, 200), (110, 200), (110, 210), (100, 210), (100, 200)],
            holes=[[(103, 203), (107, 203), (107, 207), (103, 207), (103, 203)]],
        ),
        "BUILDING_B": MultiPolygon(
            [
                Polygon([(120, 200), (124, 200), (124, 204), (120, 204), (120, 200)]),
                Polygon([(126, 200), (130, 200), (130, 204), (126, 204), (126, 200)]),
            ]
        ),
        "BUILDING_C": Polygon(
            [(140, 200), (150, 200), (150, 210), (140, 210), (140, 200)]
        ),
    }


def polygon_parts(value: Polygon | MultiPolygon) -> list[Polygon]:
    return [value] if isinstance(value, Polygon) else list(value.geoms)


def feature_for(
    building_id: str,
    value: Polygon | MultiPolygon,
    *,
    zero_roof: bool = False,
) -> dict[str, Any]:
    vertices: list[list[int]] = []
    boundaries: list[list[list[int]]] = []
    for polygon in polygon_parts(value):
        surface: list[list[int]] = []
        for coordinates in [polygon.exterior.coords, *(ring.coords for ring in polygon.interiors)]:
            indices: list[int] = []
            for x, y in coordinates:
                indices.append(len(vertices))
                vertices.append(
                    [
                        round((x - TRANSFORM["translate"][0]) / TRANSFORM["scale"][0]),
                        round((y - TRANSFORM["translate"][1]) / TRANSFORM["scale"][1]),
                        10,
                    ]
                )
            surface.append(indices)
        boundaries.append(surface)
    child_id = f"{building_id}-part"
    geometry: list[dict[str, Any]] = []
    if not zero_roof:
        geometry = [
            {
                "type": "MultiSurface",
                "lod": "2.2",
                "boundaries": boundaries,
                "semantics": {
                    "surfaces": [{"type": "RoofSurface"}],
                    "values": [0 for _ in boundaries],
                },
            }
        ]
    return {
        "type": "CityJSONFeature",
        "id": building_id,
        "CityObjects": {
            building_id: {
                "type": "Building",
                "attributes": {
                    "building_id": building_id,
                    "rf_extrusion_mode": "skip" if zero_roof else "standard",
                    "rf_pointcloud_unusable": bool(zero_roof),
                },
                "children": [child_id],
                "geometry": [],
            },
            child_id: {
                "type": "BuildingPart",
                "parents": [building_id],
                "geometry": geometry,
            },
        },
        "vertices": vertices,
    }


def reencode_feature_for_merged(feature: Mapping[str, Any], offset: int) -> dict[str, Any]:
    def offset_indices(value: Any) -> Any:
        if isinstance(value, list):
            if value and all(isinstance(item, int) for item in value):
                return [item + offset for item in value]
            return [offset_indices(item) for item in value]
        return value

    output = json.loads(json.dumps(feature["CityObjects"]))
    for obj in output.values():
        for geometry in obj.get("geometry", []):
            geometry["boundaries"] = offset_indices(geometry["boundaries"])
    return output


class Fixture:
    def __init__(
        self,
        root: Path,
        *,
        geometry_owner: Mapping[str, str] | None = None,
        output_geometry: Mapping[str, Polygon | MultiPolygon] | None = None,
        zero_ids: set[str] | None = None,
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.ids = IDS
        self.polygons = polygons()
        geometry_owner = geometry_owner or {building_id: building_id for building_id in IDS}
        output_geometry = output_geometry or {}
        zero_ids = zero_ids or set()

        self.pilot = root / "pilot.csv"
        with self.pilot.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["selection_rank", "building_id"])
            writer.writeheader()
            writer.writerows(
                {"selection_rank": index, "building_id": building_id}
                for index, building_id in enumerate(IDS, start=1)
            )
        self.pilot_manifest = root / "pilot_manifest.json"
        write_json(
            self.pilot_manifest,
            {
                "selection": {
                    "selection_count": len(IDS),
                    "selected_ids_in_rank_order": list(IDS),
                    "selection_sha256": "synthetic-selection",
                    "ordered_ids_sha256": "synthetic-ordered-ids",
                }
            },
        )

        self.roofprints = root / "locked_roofprints.geojson"
        footprint_payload = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::25832"},
            },
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "building_id": building_id,
                        "selection_rank": index,
                        "class": 6,
                    },
                    "geometry": mapping(self.polygons[building_id]),
                }
                for index, building_id in enumerate(IDS, start=1)
            ],
        }
        write_json(self.roofprints, footprint_payload)
        normalized = audit.load_roofprints(self.roofprints, IDS)
        self.footprint_record = {
            "path": str(self.roofprints),
            "sha256": normalized["sha256"],
            "feature_count": len(IDS),
            "building_ids": list(IDS),
            "feature_properties": [dict(value) for value in normalized["feature_properties"]],
            "ordered_feature_geometry_sha256": normalized[
                "ordered_feature_geometry_sha256"
            ],
            "crs": audit.CRS,
            "coordinate_dimension": 2,
        }

        contract = {
            "schema": "jointbuildgs.pilot_1wave.readout_crop_contract.v1",
            "crs": audit.CRS,
            "crop": {
                "mode": "single_locked_global_bbox",
                "bbox_utm": [90.0, 190.0, 160.0, 220.0],
                "area_m2": 2100.0,
            },
            "population": {
                "count": len(IDS),
                "ordered_building_ids": list(IDS),
                "ordered_ids_sha256": "synthetic-ordered-ids",
            },
            "pilot_set_csv": {
                "path": str(self.pilot),
                "sha256": audit.sha256_file(self.pilot),
            },
            "pilot_set_manifest": {
                "path": str(self.pilot_manifest),
                "sha256": audit.sha256_file(self.pilot_manifest),
            },
            "footprint_source": record(self.roofprints),
        }
        crop_json = audit.canonical_json(contract)
        crop_sha = hashlib.sha256(crop_json.encode()).hexdigest()
        self.lineage = {
            "schema": "synthetic-lineage.v1",
            "condition_id": CONDITION,
            "seed": SEED,
            "crop_contract_json": crop_json,
            "crop_contract_sha256": crop_sha,
        }
        self.normalized_crop = {
            "schema": contract["schema"],
            "json": crop_json,
            "sha256": crop_sha,
            "ordered_building_ids": list(IDS),
        }
        self.scene_npz = root / "scene.npz"
        np.savez(
            self.scene_npz,
            P_utm_clean=np.asarray([[100.0, 200.0, 1.0]]),
            crop_contract_json=np.array(crop_json),
            crop_contract_sha256=np.array(crop_sha),
            readout_lineage_json=np.array(audit.canonical_json(self.lineage)),
        )
        self.scene_provenance = root / "scene.npz.provenance.json"
        write_json(
            self.scene_provenance,
            {
                "schema": "jointbuildgs.pilot_1wave.readout_extraction.v1",
                "state": "complete",
                "output_npz": record(self.scene_npz),
                "readout_lineage": self.lineage,
                "geometry_only": True,
                "crs": audit.CRS,
                "crop_contract_json": crop_json,
                "crop_contract_sha256": crop_sha,
            },
        )
        self.pointcloud = root / "classified.laz"
        self.pointcloud.write_bytes(b"synthetic classified pointcloud")
        self.classification = root / "classification.json"
        write_json(
            self.classification,
            {
                "schema": "jointbuildgs.pilot_1wave.scene_classification.v1",
                "state": "complete",
                "crs": audit.CRS,
                "source_scene_npz": record(self.scene_npz),
                "classified_las": record(self.pointcloud),
                "roofprints": self.footprint_record,
                "crop_contract": self.normalized_crop,
                "readout_lineage": self.lineage,
            },
        )
        self.features = [
            feature_for(
                building_id,
                output_geometry.get(building_id, self.polygons[geometry_owner[building_id]]),
                zero_roof=building_id in zero_ids,
            )
            for building_id in IDS
        ]
        self.jsonseq = root / "raw_jsonseq" / "scene.city.jsonl"
        self.jsonseq.parent.mkdir(parents=True)
        header = {
            "type": "CityJSON",
            "version": "2.0",
            "transform": TRANSFORM,
            "CityObjects": {},
            "vertices": [],
        }
        with self.jsonseq.open("w", encoding="utf-8") as stream:
            stream.write(audit.canonical_json(header) + "\n")
            for feature in self.features:
                stream.write(audit.canonical_json(feature) + "\n")

        merged_objects: dict[str, Any] = {}
        merged_vertices: list[list[int]] = []
        for feature in self.features:
            offset = len(merged_vertices)
            merged_objects.update(reencode_feature_for_merged(feature, offset))
            merged_vertices.extend(feature["vertices"])
        self.cityjson = root / "assembled.city.json"
        write_json(
            self.cityjson,
            {
                "type": "CityJSON",
                "version": "2.0",
                "transform": TRANSFORM,
                "CityObjects": merged_objects,
                "vertices": merged_vertices,
            },
        )
        self.argv = root / "roofer_argv.json"
        write_json(
            self.argv,
            {
                "schema": "jointbuildgs.pilot_1wave.roofer_argv.v1",
                "condition_id": CONDITION,
                "seed": SEED,
                "image": audit.ROOFER_IMAGE,
                "arguments": ["roofer"],
            },
        )
        self.prepare = root / "roofer_prepare.json"
        write_json(
            self.prepare,
            {
                "schema": "jointbuildgs.pilot_1wave.roofer_prepare.v1",
                "state": "prepared",
                "condition_id": CONDITION,
                "seed": SEED,
                "selection_sha256": "synthetic-selection",
                "ordered_ids_sha256": "synthetic-ordered-ids",
                "ordered_building_ids": list(IDS),
                "runtime_contract": {"docker_sentinel": "/.dockerenv"},
                "roofer_image": audit.ROOFER_IMAGE,
                "roofer_parameters": "synthetic parameters",
                "footprints": self.footprint_record,
                "roofer_argv": {
                    **repo_record(self.argv),
                    "schema": "jointbuildgs.pilot_1wave.roofer_argv.v1",
                    "condition_id": CONDITION,
                    "seed": SEED,
                    "image": audit.ROOFER_IMAGE,
                    "arguments": ["roofer"],
                },
                "pointcloud_path": str(self.pointcloud),
                "pointcloud_sha256": audit.sha256_file(self.pointcloud),
                "pointcloud": record(self.pointcloud),
                "classification_receipt": record(self.classification),
                "readout_lineage": self.lineage,
                "crop_contract": self.normalized_crop,
                "outputs": {
                    "runtime_dir": str(root),
                    "raw_jsonseq_dir": str(self.jsonseq.parent),
                    "merged_cityjson_path": str(self.cityjson),
                    "marker_path": str(root / "roofer_invocation.json"),
                },
            },
        )
        self.container_id = "a" * 64
        self.container_name = (
            f"{audit.ROOFER_CONTAINER_NAME_PREFIX}-{CONDITION}-seed{SEED}-roofer"
        )
        self.job_id = f"{CONDITION}_seed{SEED}"
        self.contract_sha256 = audit.sha256_json(
            {
                "job_id": self.job_id,
                "prepare_sha256": audit.sha256_file(self.prepare),
                "argv_sha256": audit.sha256_file(self.argv),
                "image": audit.ROOFER_IMAGE,
                "arguments": ["roofer"],
            }
        )
        self.start_attempts = [{"attempt": 1, "state": "started"}]
        self.repo_bind = f"/host-mount/JointBuildGS:{audit.ROOFER_CONTAINER_REPO}"
        self.launch = root / "container_launch.json"
        self.process = root / "process_complete.json"
        self.container_log = root / "container.log"
        write_json(
            self.launch,
            {
                "job_id": self.job_id,
                "container_id": self.container_id,
                "container_name": self.container_name,
                "start_attempts": self.start_attempts,
                "start_attempt_count": 1,
                "contract_sha256": self.contract_sha256,
                "create_command": [
                    "docker", "create", "-v", self.repo_bind, audit.ROOFER_IMAGE,
                ],
            },
        )
        write_json(
            self.process,
            {
                "job_id": self.job_id,
                "container_name": self.container_name,
                "contract_sha256": self.contract_sha256,
                "exit_code": 0,
                "wait_exit_code": 0,
            },
        )
        self.container_log.write_text("synthetic Roofer log\n", encoding="utf-8")
        self.execution_receipt = root / "roofer_execution_receipt.json"
        self.normalized_execution = {
            "schema": audit.ROOFER_EXECUTION_SCHEMA,
            "state": "complete",
            "condition_id": CONDITION,
            "seed": SEED,
            "job_id": self.job_id,
            "roofer_invocation_count": 1,
            "prepare_receipt": repo_record(self.prepare),
            "roofer_argv": repo_record(self.argv),
            "roofer_image_reference": audit.ROOFER_IMAGE,
            "roofer_local_image_id": audit.ROOFER_IMAGE_ID,
            "container_id": self.container_id,
            "container_name": self.container_name,
            "roofer_entrypoint": list(audit.ROOFER_ENTRYPOINT),
            "roofer_command": ["roofer"],
            "contract_sha256": self.contract_sha256,
            "container_labels": {
                "jointbuildgs.p1w.job": self.job_id,
                "jointbuildgs.p1w.contract": self.contract_sha256,
            },
            "network_mode": "none",
            "repo_bind": {
                "source": "/host-mount/JointBuildGS",
                "target": str(audit.ROOFER_CONTAINER_REPO),
                "mode": "rw",
                "docker_value": self.repo_bind,
                "launch_value": self.repo_bind,
            },
            "docker_state": "exited",
            "wait_exit_code": 0,
            "start_attempt_count": 1,
            "restart_count": 0,
            "launch_receipt": repo_record(self.launch),
            "process_receipt": repo_record(self.process),
            "logs": repo_record(self.container_log, include_size=True),
        }
        write_json(
            self.execution_receipt,
            {
                "schema": audit.ROOFER_EXECUTION_SCHEMA,
                "state": "complete",
                "condition_id": CONDITION,
                "seed": SEED,
                "job_id": self.job_id,
                "roofer_invocation_count": 1,
                "prepare_receipt": repo_record(self.prepare),
                "roofer_argv": repo_record(self.argv),
                "container": {
                    "image_reference": audit.ROOFER_IMAGE,
                    "image_id": audit.ROOFER_IMAGE_ID,
                    "config_image": audit.ROOFER_IMAGE,
                    "entrypoint": list(audit.ROOFER_ENTRYPOINT),
                    "cmd": ["roofer"],
                    "labels": {
                        "jointbuildgs.p1w.job": self.job_id,
                        "jointbuildgs.p1w.contract": self.contract_sha256,
                    },
                    "binds": [self.repo_bind],
                    "network_mode": "none",
                    "restart_count": 0,
                    "id": self.container_id,
                    "name": self.container_name,
                },
                "execution": {
                    "docker_state": "exited",
                    "wait_exit_code": 0,
                    "start_attempt_count": 1,
                    "start_attempts": self.start_attempts,
                },
                "launch_receipt": repo_record(self.launch),
                "process_receipt": repo_record(self.process),
                "logs": repo_record(self.container_log, include_size=True),
            },
        )
        self.roofer = root / "roofer_invocation.json"
        self.refresh_roofer_marker()

        self.score_csv = root / "scores.csv"
        self.write_scores(list(IDS))
        self.score_marker = root / "score_marker.json"
        self.refresh_score_marker()

    def refresh_roofer_marker(self) -> None:
        city = json.loads(self.cityjson.read_text(encoding="utf-8"))
        objects = city["CityObjects"]
        child_count = sum(
            1 for value in objects.values() if value.get("type") == "BuildingPart"
        )
        roots = [key for key, value in objects.items() if value.get("type") == "Building"]
        raw_file_record = {
            **record(self.jsonseq),
            "size_bytes": self.jsonseq.stat().st_size,
        }
        write_json(
            self.roofer,
            {
                "schema": "jointbuildgs.pilot_1wave.roofer_invocation.v2",
                "state": "complete",
                "condition_id": CONDITION,
                "seed": SEED,
                "roofer_invocation_count": 1,
                "selection_sha256": "synthetic-selection",
                "ordered_ids_sha256": "synthetic-ordered-ids",
                "ordered_building_ids": list(IDS),
                "runtime_contract": {"docker_sentinel": "/.dockerenv"},
                "roofer_image": audit.ROOFER_IMAGE,
                "roofer_parameters": "synthetic parameters",
                "pointcloud_path": str(self.pointcloud),
                "pointcloud_sha256": audit.sha256_file(self.pointcloud),
                "pointcloud": record(self.pointcloud),
                "classification_receipt": record(self.classification),
                "prepare_receipt": record(self.prepare),
                "execution_receipt": repo_record(self.execution_receipt),
                "roofer_execution": self.normalized_execution,
                "roofer_argv": {
                    **repo_record(self.argv),
                    "schema": "jointbuildgs.pilot_1wave.roofer_argv.v1",
                    "condition_id": CONDITION,
                    "seed": SEED,
                    "image": audit.ROOFER_IMAGE,
                    "arguments": ["roofer"],
                },
                "readout_lineage": self.lineage,
                "crop_contract": self.normalized_crop,
                "footprints": self.footprint_record,
                "raw_jsonseq": {
                    "directory_path": str(self.jsonseq.parent),
                    "file_count": 1,
                    "files": [raw_file_record],
                    "bundle_sha256": audit.sha256_json({"files": [raw_file_record]}),
                    "feature_count": len(self.features),
                    "feature_ids_in_read_order": [feature["id"] for feature in self.features],
                    "root_building_count": len(self.features),
                    "root_building_ids": [feature["id"] for feature in self.features],
                    "child_count": len(self.features),
                },
                "cityjson_path": str(self.cityjson),
                "cityjson_sha256": audit.sha256_file(self.cityjson),
                "merged_cityjson": {
                    **record(self.cityjson),
                    "size_bytes": self.cityjson.stat().st_size,
                    "root_building_count": len(roots),
                    "root_building_ids": roots,
                    "child_count": child_count,
                },
            },
        )

    def write_scores(self, ids: list[str]) -> None:
        with self.score_csv.open("w", newline="", encoding="utf-8") as stream:
            fields = [
                "condition_id",
                "seed",
                "selection_rank",
                "building_id",
                "cityjson_sha256",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for index, building_id in enumerate(ids, start=1):
                writer.writerow(
                    {
                        "condition_id": CONDITION,
                        "seed": SEED,
                        "selection_rank": index,
                        "building_id": building_id,
                        "cityjson_sha256": audit.sha256_file(self.cityjson),
                    }
                )

    def refresh_score_marker(self) -> None:
        write_json(
            self.score_marker,
            {
                "schema": "jointbuildgs.pilot_1wave.score_invocation.v1",
                "state": "complete",
                "condition_id": CONDITION,
                "seed": SEED,
                "score_invocation_count": 1,
                "cityjson_path": str(self.cityjson),
                "cityjson_sha256": audit.sha256_file(self.cityjson),
                "roofer_marker_path": str(self.roofer),
                "roofer_marker_sha256": audit.sha256_file(self.roofer),
                "classification_receipt_path": str(self.classification),
                "classification_receipt_sha256": audit.sha256_file(self.classification),
                "score_output_path": str(self.score_csv),
                "score_output_sha256": audit.sha256_file(self.score_csv),
                "score_output_row_count": len(IDS),
            },
        )

    def inputs(self) -> audit.RunInputs:
        return audit.RunInputs(
            condition_id=CONDITION,
            seed=SEED,
            pilot_set=self.pilot,
            pilot_manifest=self.pilot_manifest,
            scene_npz=self.scene_npz,
            scene_provenance=self.scene_provenance,
            classification_receipt=self.classification,
            roofprint_prepare_marker=self.prepare,
            roofer_marker=self.roofer,
            merged_cityjson=self.cityjson,
            score_marker=self.score_marker,
            score_csv=self.score_csv,
        )

    def run(self, suffix: str = "") -> dict[str, Any]:
        return audit.audit_run(
            self.inputs(),
            building_output=self.root / f"binding{suffix}.csv",
            matrix_output=self.root / f"matrix{suffix}.csv",
            receipt_output=self.root / f"receipt{suffix}.json",
            strict_locked_population=False,
        )


class PilotOneWaveBindingAuditTests(unittest.TestCase):
    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(prefix=".p1w_binding_", dir=SCRIPT_DIR)

    def test_identity_holes_multipolygon_transform_and_determinism(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(Path(raw))
            first = fixture.run()
            before = {
                path.name: path.read_bytes()
                for path in (fixture.root / "binding.csv", fixture.root / "matrix.csv", fixture.root / "receipt.json")
            }
            second = fixture.run()
            after = {
                path.name: path.read_bytes()
                for path in (fixture.root / "binding.csv", fixture.root / "matrix.csv", fixture.root / "receipt.json")
            }
            self.assertEqual(first, second)
            self.assertEqual(before, after)
            self.assertTrue(first["hard_gate_passed"])
            self.assertEqual(first["owner_assignment_gate"]["diagonal_sum"], 3)
            self.assertEqual(first["containment_mismatch_count"], 0)
            with (fixture.root / "binding.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["expected_building_id"] for row in rows], list(IDS))
            self.assertAlmostEqual(float(rows[0]["roof_union_area_m2"]), 84.0, places=6)
            self.assertAlmostEqual(float(rows[1]["roof_union_area_m2"]), 32.0, places=6)

    def test_swapped_labels_are_caught_despite_identical_set(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(
                Path(raw),
                geometry_owner={
                    "BUILDING_A": "BUILDING_B",
                    "BUILDING_B": "BUILDING_A",
                    "BUILDING_C": "BUILDING_C",
                },
            )
            receipt = fixture.run()
            self.assertFalse(receipt["hard_gate_passed"])
            self.assertEqual(receipt["owner_assignment_gate"]["diagonal_sum"], 1)
            self.assertEqual(receipt["owner_assignment_gate"]["offdiagonal_sum"], 2)
            with (fixture.root / "binding.csv").open(newline="", encoding="utf-8") as stream:
                buildings = list(csv.DictReader(stream))
            with (fixture.root / "matrix.csv").open(newline="", encoding="utf-8") as stream:
                matrix = list(csv.DictReader(stream))
            self.assertEqual(len(buildings), 3)
            self.assertEqual(len(matrix), 9)
            self.assertEqual(buildings[0]["spatial_owner_building_id"], "BUILDING_B")
            self.assertEqual(buildings[1]["spatial_owner_building_id"], "BUILDING_A")
            self.assertEqual(buildings[0]["all_four_match"], "false")
            self.assertEqual(buildings[1]["all_four_match"], "false")

    def test_roofer_output_serialization_reorder_passes(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(Path(raw))
            fixture.features = [
                fixture.features[index] for index in (2, 0, 1)
            ]
            header = {
                "type": "CityJSON",
                "version": "2.0",
                "transform": TRANSFORM,
                "CityObjects": {},
                "vertices": [],
            }
            with fixture.jsonseq.open("w", encoding="utf-8") as stream:
                stream.write(audit.canonical_json(header) + "\n")
                for feature in fixture.features:
                    stream.write(audit.canonical_json(feature) + "\n")

            merged = json.loads(fixture.cityjson.read_text(encoding="utf-8"))
            objects = merged["CityObjects"]
            merged["CityObjects"] = {
                object_id: objects[object_id] for object_id in reversed(tuple(objects))
            }
            write_json(fixture.cityjson, merged)
            fixture.write_scores(list(IDS))
            fixture.refresh_roofer_marker()
            fixture.refresh_score_marker()

            receipt = fixture.run()
            self.assertTrue(receipt["hard_gate_passed"])
            output_orders = receipt["roofer_output_orders"]
            self.assertEqual(
                output_orders["raw_feature_ids_in_read_order"],
                ["BUILDING_C", "BUILDING_A", "BUILDING_B"],
            )
            self.assertEqual(
                output_orders["merged_root_ids_in_serialization_order"],
                ["BUILDING_C", "BUILDING_B", "BUILDING_A"],
            )
            with (fixture.root / "binding.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["expected_building_id"] for row in rows], list(IDS))
            self.assertTrue(all(row["all_four_match"] == "true" for row in rows))

    def test_missing_and_extra_parent_fail(self) -> None:
        for mutation, expected in (("missing", "parent IDs count"), ("extra", "parent IDs count")):
            with self.subTest(mutation=mutation), self.temporary_directory() as raw:
                fixture = Fixture(Path(raw))
                city = json.loads(fixture.cityjson.read_text(encoding="utf-8"))
                if mutation == "missing":
                    del city["CityObjects"]["BUILDING_C"]
                else:
                    city["CityObjects"]["EXTRA"] = {
                        "type": "Building",
                        "attributes": {"building_id": "EXTRA"},
                        "children": [],
                        "geometry": [],
                    }
                write_json(fixture.cityjson, city)
                fixture.refresh_roofer_marker()
                fixture.refresh_score_marker()
                with self.assertRaisesRegex(RuntimeError, expected):
                    fixture.run()

    def test_orphan_and_shared_child_fail(self) -> None:
        for mutation, expected in (("orphan", "orphan"), ("shared", "child parent|shared child")):
            with self.subTest(mutation=mutation), self.temporary_directory() as raw:
                fixture = Fixture(Path(raw))
                city = json.loads(fixture.cityjson.read_text(encoding="utf-8"))
                if mutation == "orphan":
                    city["CityObjects"]["orphan-part"] = {
                        "type": "BuildingPart",
                        "parents": ["BUILDING_A"],
                        "geometry": [],
                    }
                else:
                    city["CityObjects"]["BUILDING_B"]["children"].append(
                        "BUILDING_A-part"
                    )
                write_json(fixture.cityjson, city)
                fixture.refresh_roofer_marker()
                fixture.refresh_score_marker()
                with self.assertRaisesRegex(RuntimeError, expected):
                    fixture.run()

    def test_duplicate_score_id_fails(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(Path(raw))
            fixture.write_scores(["BUILDING_A", "BUILDING_A", "BUILDING_C"])
            fixture.refresh_score_marker()
            with self.assertRaisesRegex(RuntimeError, "uniqueness"):
                fixture.run()

    def test_source_tamper_fails_before_identity_claim(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(Path(raw))
            with fixture.scene_npz.open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(RuntimeError, "SHA256"):
                fixture.run()

    def test_roofer_execution_log_tamper_fails_closed(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(Path(raw))
            with fixture.container_log.open("a", encoding="utf-8") as stream:
                stream.write("tamper\n")
            with self.assertRaisesRegex(RuntimeError, "SHA256|size"):
                fixture.run()

    def test_repository_bind_accepts_host_alias_but_requires_sealed_volume(self) -> None:
        raw = f"/host-mount/JointBuildGS:{audit.ROOFER_CONTAINER_REPO}"
        launch = {"create_command": ["docker", "create", "-v", raw]}
        normalized = audit.validate_repository_bind([raw], launch)
        self.assertEqual(normalized["source"], "/host-mount/JointBuildGS")
        self.assertEqual(normalized["target"], str(audit.ROOFER_CONTAINER_REPO))
        self.assertEqual(normalized["mode"], "rw")
        self.assertNotEqual(normalized["source"], str(audit.REPO.resolve()))
        with self.assertRaisesRegex(RuntimeError, "absolute host path"):
            audit.validate_repository_bind(
                [f"relative/path:{audit.ROOFER_CONTAINER_REPO}"],
                {"create_command": [
                    "docker", "create", "-v",
                    f"relative/path:{audit.ROOFER_CONTAINER_REPO}",
                ]},
            )
        with self.assertRaisesRegex(RuntimeError, "launch/inspect bind source"):
            audit.validate_repository_bind(
                [raw],
                {"create_command": [
                    "docker", "create", "-v",
                    f"/other-host/JointBuildGS:{audit.ROOFER_CONTAINER_REPO}",
                ]},
            )

    def test_zero_roof_is_flagged_without_owner_or_invented_geometry(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(Path(raw), zero_ids={"BUILDING_C"})
            receipt = fixture.run()
            self.assertFalse(receipt["hard_gate_passed"])
            self.assertEqual(receipt["zero_roof_count"], 1)
            self.assertEqual(receipt["containment_mismatch_count"], 1)
            self.assertEqual(receipt["owner_assignment_gate"]["diagonal_sum"], 2)
            with (fixture.root / "binding.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            zero = rows[2]
            self.assertEqual(zero["zero_roof"], "true")
            self.assertEqual(zero["spatial_owner_building_id"], "")
            self.assertEqual(zero["all_four_match"], "false")
            with (fixture.root / "matrix.csv").open(newline="", encoding="utf-8") as stream:
                matrix = list(csv.DictReader(stream))
            column = [row for row in matrix if row["output_parent_id"] == "BUILDING_C"]
            self.assertEqual(sum(row["owner_assignment"] == "true" for row in column), 0)

    def test_tie_and_no_overlap_emit_full_evidence_with_false_gate(self) -> None:
        with self.temporary_directory() as raw:
            tie = MultiPolygon(
                [
                    Polygon([(100, 200), (102, 200), (102, 202), (100, 202), (100, 200)]),
                    Polygon([(120, 200), (122, 200), (122, 202), (120, 202), (120, 200)]),
                ]
            )
            no_overlap = Polygon(
                [(160, 200), (164, 200), (164, 204), (160, 204), (160, 200)]
            )
            fixture = Fixture(
                Path(raw),
                output_geometry={"BUILDING_A": tie, "BUILDING_C": no_overlap},
            )
            receipt = fixture.run()
            self.assertFalse(receipt["hard_gate_passed"])
            self.assertEqual(receipt["owner_assignment_gate"]["containment_mismatch_count"], 2)
            with (fixture.root / "binding.csv").open(newline="", encoding="utf-8") as stream:
                buildings = list(csv.DictReader(stream))
            with (fixture.root / "matrix.csv").open(newline="", encoding="utf-8") as stream:
                matrix = list(csv.DictReader(stream))
            self.assertEqual(len(buildings), 3)
            self.assertEqual(len(matrix), 9)
            self.assertEqual(buildings[0]["spatial_owner_candidate_count"], "2")
            self.assertEqual(buildings[0]["spatial_owner_building_id"], "")
            self.assertEqual(buildings[2]["spatial_owner_candidate_count"], "0")
            self.assertEqual(buildings[2]["spatial_owner_building_id"], "")
            self.assertEqual(buildings[0]["outside_owner_area_m2"], "8.000000000000")
            self.assertEqual(buildings[2]["outside_owner_area_m2"], "16.000000000000")

    def test_unique_owner_outside_area_fails_literal_containment_gate(self) -> None:
        with self.temporary_directory() as raw:
            spilling = Polygon(
                [(100, 200), (112, 200), (112, 210), (100, 210), (100, 200)]
            )
            fixture = Fixture(Path(raw), output_geometry={"BUILDING_A": spilling})
            receipt = fixture.run()
            self.assertFalse(receipt["hard_gate_passed"])
            self.assertEqual(receipt["containment_mismatch_count"], 1)
            with (fixture.root / "binding.csv").open(newline="", encoding="utf-8") as stream:
                row = list(csv.DictReader(stream))[0]
            self.assertEqual(row["spatial_owner_building_id"], "BUILDING_A")
            self.assertEqual(row["spatial_owner_matches_parent"], "true")
            self.assertEqual(row["owner_contained"], "false")
            self.assertAlmostEqual(float(row["outside_owner_area_m2"]), 36.0, places=6)
            self.assertAlmostEqual(float(row["owner_containment_ratio"]), 0.7, places=6)
            self.assertAlmostEqual(float(row["containment_tolerance_m2"]), 1.2e-6, places=12)

    def test_owner_row_collision_emits_full_evidence_with_false_gate(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(
                Path(raw), output_geometry={"BUILDING_B": polygons()["BUILDING_A"]}
            )
            receipt = fixture.run()
            gate = receipt["owner_assignment_gate"]
            self.assertFalse(receipt["hard_gate_passed"])
            self.assertEqual(gate["row_sums"][1], 2)
            self.assertEqual(gate["row_sums"][2], 0)
            with (fixture.root / "binding.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 3)
            with (fixture.root / "matrix.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 9)

    def test_batch_helper_emits_deterministic_aggregate_files(self) -> None:
        with self.temporary_directory() as raw:
            fixture = Fixture(Path(raw) / "run")
            spec_path = Path(raw) / "batch.json"
            inputs = fixture.inputs()
            write_json(
                spec_path,
                {
                    "schema": "jointbuildgs.pilot_1wave.binding_batch_spec.v1",
                    "runs": [
                        {
                            "condition_id": inputs.condition_id,
                            "seed": inputs.seed,
                            "pilot_set": str(inputs.pilot_set),
                            "pilot_manifest": str(inputs.pilot_manifest),
                            "scene_npz": str(inputs.scene_npz),
                            "scene_provenance": str(inputs.scene_provenance),
                            "classification_receipt": str(inputs.classification_receipt),
                            "roofprint_prepare_marker": str(inputs.roofprint_prepare_marker),
                            "roofer_marker": str(inputs.roofer_marker),
                            "merged_cityjson": str(inputs.merged_cityjson),
                            "score_marker": str(inputs.score_marker),
                            "score_csv": str(inputs.score_csv),
                        }
                    ],
                },
            )
            output = Path(raw) / "aggregate"
            first = audit.audit_batch(
                spec_path,
                output,
                strict_expected_runs=False,
                strict_locked_population=False,
            )
            payloads = {path.name: path.read_bytes() for path in output.iterdir()}
            second = audit.audit_batch(
                spec_path,
                output,
                strict_expected_runs=False,
                strict_locked_population=False,
            )
            self.assertEqual(first, second)
            self.assertEqual(payloads, {path.name: path.read_bytes() for path in output.iterdir()})
            self.assertEqual(first["building_row_count"], 3)
            self.assertEqual(first["spatial_matrix_row_count"], 9)
            self.assertTrue(first["global_g1"]["pass"])
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                [
                    "binding_audit.csv",
                    "binding_audit_receipt.json",
                    "binding_audit_spatial_matrix.csv",
                ],
            )


if __name__ == "__main__":
    unittest.main()
