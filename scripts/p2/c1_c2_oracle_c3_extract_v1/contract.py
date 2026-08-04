"""Frozen contracts shared by the C1/C2 oracle and C3 extraction drivers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET

import numpy as np
from shapely import contains_xy
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union
import torch

from src.stage2.model import quat_to_rotmat


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json"
CONDITIONS = ("C1_LIDAR_GT_FOOTPRINT_ORACLE", "C2_MVS_GT_FOOTPRINT_ORACLE")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any] | None = None, *, require_activation: bool = False) -> dict[str, Any]:
    cfg = dict(config or load_config())
    authority = cfg.get("execution_authority") or {}
    if cfg.get("task_id") != "P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v13":
        raise RuntimeError("recovery task identity drifted")
    if cfg.get("handoff_id") is not None:
        raise RuntimeError("local execution must not claim a handoff ID")
    if cfg.get("execution_record_id") != "P2-LOCAL-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v13":
        raise RuntimeError("local execution record identity drifted")
    if authority.get("mode") != "DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST":
        raise RuntimeError("local execution authority is missing")
    if authority.get("execution_host_role") != "experiment_host":
        raise RuntimeError("execution host role drifted")
    if authority.get("write_ownership_transfer_performed") is not False:
        raise RuntimeError("this task must not claim a write-ownership transfer")
    if authority.get("two_host_receipt_required") is not False:
        raise RuntimeError("this local execution must not require or fabricate two-host receipts")
    scope = cfg.get("scope") or {}
    ids = list(scope.get("building_ids") or ())
    if ids != ["DEBY_LOD2_4907177", "DEBY_LOD2_4906975", "DEBY_LOD2_108580336"]:
        raise RuntimeError("representative building binding drifted")
    if scope.get("c1_c2_mode") != "GT_GROUNDSURFACE_XY_FOOTPRINT_ORACLE_DIAGNOSTIC_NOT_OFFICIAL_HONEST_ARM":
        raise RuntimeError("C1/C2 oracle label is missing")
    if scope.get("c3_mode") != "EXACT_CHECKPOINT_RESULT_EXTRACTION_ONLY_NO_TRAINING":
        raise RuntimeError("C3 extraction-only binding drifted")
    if scope.get("c4_c5_access_allowed") is not False:
        raise RuntimeError("C4/C5 must remain inaccessible")
    prep = cfg.get("c1_c2_preparation") or {}
    if prep.get("gt_footprint_used") is not True or prep.get("roofsurface_used") is not False:
        raise RuntimeError("GT input-field boundary drifted")
    presentation = cfg.get("presentation") or {}
    if presentation.get("c3_gaussian_display_policy") != "QUATERNION_SCALE_OPACITY_ORIENTED_ELLIPSES_NOT_CENTER_POINT_SCATTER":
        raise RuntimeError("C3 Gaussian visualization contract drifted")
    if presentation.get("c3_footprint_display_policy") != "GT_GROUNDSURFACE_XY_DISPLAY_ONLY_ON_ALL_3D_ROWS":
        raise RuntimeError("C3 footprint display contract drifted")
    if presentation.get("c3_comparison_layout") != "ONE_BUILDING_PER_SHEET_C3_1_THEN_C3_2_SHARED_FOUR_VIEWS":
        raise RuntimeError("C3 comparison layout contract drifted")
    if len(presentation.get("c3_rows") or ()) != 12:
        raise RuntimeError("C3 comparison must have twelve rows")
    if presentation.get("rgb_roofline_stroke_px") != {"dark_casing": 12, "yellow_line": 6}:
        raise RuntimeError("RGB roofline stroke contract drifted")
    mesh = (cfg.get("c3_extraction") or {}).get("roof_semantic_mesh_recovery") or {}
    if mesh != {
        "source": "INHERITED_RENDERED_DEPTH_FUSED_SURFACE_POINTS_NO_RERENDER",
        "semantic_class": 1,
        "semantic_class_name": "ROOF",
        "footprint_buffer_m": 1.0,
        "minimum_point_count": 100,
        "poisson_depth": 8,
        "insufficient_evidence_status": "INSUFFICIENT_ROOF_SEMANTIC_EVIDENCE",
    }:
        raise RuntimeError("C3 roof-semantic mesh recovery contract drifted")
    roofer_oracle = cfg.get("c3_roofer_oracle") or {}
    if roofer_oracle != {
        "mode": "GT_GROUNDSURFACE_XY_FOOTPRINT_ORACLE_DIAGNOSTIC_NOT_OFFICIAL_HONEST_STAGE3",
        "building_source": "C3_RENDERED_DEPTH_FUSED_SEMANTIC_CLASS_1_INSIDE_GT_FOOTPRINT",
        "shared_terrain_source": "C2_EXACT_COMMON_IMAGE_MVS_CLASS_2_SUPPORT",
        "deterministic_voxel_m": 0.2,
        "minimum_class6_points": 100,
        "expected_invocations": 4,
        "expected_pre_roofer_failures": 2,
        "roofsurface_reference_used_as_input": False,
    }:
        raise RuntimeError("C3 oracle Roofer contract drifted")
    counters = cfg.get("execution_counters") or {}
    expected = {
        "expected_roofer_invocations_this_recovery": 0,
        "expected_roofer_invocations_total_lineage": 8,
        "expected_pre_roofer_reference_alignment_failures": 2,
        "expected_g2_invocations": 0,
        "expected_gs_training_invocations": 0,
        "expected_c3_extraction_invocations_this_recovery": 0,
        "expected_c3_completed_extractions_total_lineage": 2,
        "expected_metric_recomputations": 0,
        "expected_c4_c5_accesses": 0,
    }
    if any(int(counters.get(key, -1)) != value for key, value in expected.items()):
        raise RuntimeError("execution counter contract drifted")
    provenance = cfg.get("c3_training_provenance") or {}
    if int(provenance.get("completed_independent_runs", -1)) != 2:
        raise RuntimeError("C3 successful run count drifted")
    rows = list(provenance.get("conditions") or ())
    if [row.get("condition_id") for row in rows] != ["C3_1_SEM", "C3_2_SEM_DEPTH"]:
        raise RuntimeError("C3 condition order drifted")
    if provenance.get("seed_ids") != [0] or provenance.get("claimed_two_repeats_per_condition") is not False:
        raise RuntimeError("C3 seed/repeat disclosure drifted")
    if not math.isclose(float(provenance.get("successful_runtime_minutes_sequential", -1)), 216.5):
        raise RuntimeError("C3 runtime disclosure drifted")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must be null")
    if cfg.get("official_G3_G4_PASS_usable", "missing") is not None:
        raise RuntimeError("official G3/G4/PASS must be null")
    if require_activation and cfg.get("status") != "APPROVED_FOR_EXECUTION":
        raise RuntimeError("config is not activated")
    return {
        "status": "PASS",
        "building_count": 3,
        "c1_c2_building_method_record_count": 6,
        "c1_c2_expected_roofer_operation_count": 4,
        "c1_c2_expected_alignment_failure_count": 2,
        "c3_completed_training_runs": 2,
        "c3_training_invocations_this_task": 0,
        "c3_expected_roofer_operation_count": 4,
        "c3_expected_pre_roofer_failure_count": 2,
        "execution_authority_mode": authority["mode"],
        "write_ownership_transfer_performed": False,
        "scientific_verdict": None,
    }


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_id(element: ET.Element) -> str | None:
    for key, value in element.attrib.items():
        if key == "id" or key.endswith("}id"):
            return str(value)
    return None


def _ring_from_boundary(boundary: ET.Element) -> np.ndarray | None:
    pos_list = next((node for node in boundary.iter() if _local_name(node.tag) == "posList"), None)
    if pos_list is None or not pos_list.text:
        return None
    values = np.fromstring(pos_list.text, sep=" ", dtype=np.float64)
    dimension = int(pos_list.attrib.get("srsDimension", "3"))
    if dimension not in (2, 3) or len(values) < dimension * 3 or len(values) % dimension:
        raise RuntimeError("invalid GML polygon boundary")
    ring = values.reshape((-1, dimension))
    if dimension == 2:
        ring = np.column_stack((ring, np.zeros(len(ring), dtype=np.float64)))
    if not np.allclose(ring[0], ring[-1]):
        ring = np.vstack((ring, ring[0]))
    return ring


@dataclass(frozen=True)
class BuildingReference:
    stable_id: str
    footprint: Polygon | MultiPolygon
    ground_rings_xyz: tuple[np.ndarray, ...]
    roof_rings_xyz: tuple[np.ndarray, ...]
    surface_rings: tuple[tuple[str, np.ndarray], ...]


def load_building_references(path: Path, building_ids: Sequence[str]) -> dict[str, BuildingReference]:
    wanted = set(map(str, building_ids))
    found: dict[str, BuildingReference] = {}
    for _event, building in ET.iterparse(path, events=("end",)):
        if _local_name(building.tag) != "Building":
            continue
        stable_id = _element_id(building)
        if stable_id in wanted:
            polygons: list[Polygon] = []
            ground_rings: list[np.ndarray] = []
            roof_rings: list[np.ndarray] = []
            surface_rings: list[tuple[str, np.ndarray]] = []
            for surface in building.iter():
                surface_type = _local_name(surface.tag)
                if surface_type not in {"GroundSurface", "RoofSurface", "WallSurface"}:
                    continue
                for polygon_element in surface.iter():
                    if _local_name(polygon_element.tag) != "Polygon":
                        continue
                    exterior_node = next(
                        (node for node in polygon_element if _local_name(node.tag) == "exterior"),
                        None,
                    )
                    if exterior_node is None:
                        continue
                    exterior = _ring_from_boundary(exterior_node)
                    if exterior is None:
                        continue
                    surface_rings.append((surface_type, exterior))
                    if surface_type == "RoofSurface":
                        roof_rings.append(exterior)
                    if surface_type != "GroundSurface":
                        continue
                    interiors = []
                    for node in polygon_element:
                        if _local_name(node.tag) == "interior":
                            ring = _ring_from_boundary(node)
                            if ring is not None:
                                interiors.append(ring[:, :2])
                    polygon = Polygon(exterior[:, :2], interiors)
                    if not polygon.is_valid:
                        polygon = polygon.buffer(0)
                    if polygon.is_empty:
                        raise RuntimeError(f"empty GroundSurface footprint: {stable_id}")
                    polygons.append(polygon)
                    ground_rings.append(exterior)
            if not polygons:
                raise RuntimeError(f"GroundSurface footprint missing: {stable_id}")
            footprint = unary_union(polygons)
            if not isinstance(footprint, (Polygon, MultiPolygon)):
                raise RuntimeError(f"unsupported footprint geometry: {stable_id} {footprint.geom_type}")
            found[str(stable_id)] = BuildingReference(
                stable_id=str(stable_id),
                footprint=footprint,
                ground_rings_xyz=tuple(ground_rings),
                roof_rings_xyz=tuple(roof_rings),
                surface_rings=tuple(surface_rings),
            )
        building.clear()
    missing = sorted(wanted - set(found))
    if missing:
        raise RuntimeError(f"building references missing: {missing}")
    return found


def footprint_geojson(reference: BuildingReference) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "GT GroundSurface XY footprint oracle diagnostic",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "stable_id": reference.stable_id,
                "input_role": "GT_GROUNDSURFACE_XY_FOOTPRINT_ORACLE_DIAGNOSTIC",
            },
            "geometry": mapping(reference.footprint),
        }],
    }


def deterministic_voxel_one(points: np.ndarray, voxel_m: float) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64)
    if not len(values):
        return values.reshape((0, 3))
    keys = np.floor(values / float(voxel_m)).astype(np.int64)
    order = np.lexsort((values[:, 2], values[:, 1], values[:, 0], keys[:, 2], keys[:, 1], keys[:, 0]))
    ordered_keys = keys[order]
    keep = np.ones(len(order), dtype=bool)
    keep[1:] = np.any(ordered_keys[1:] != ordered_keys[:-1], axis=1)
    return values[order[keep]]


def estimate_local_ground(points: np.ndarray, inside: np.ndarray, cell_m: float) -> float:
    outside = np.asarray(points, dtype=np.float64)[~inside]
    if len(outside) < 10:
        outside = np.asarray(points, dtype=np.float64)
    if not len(outside):
        raise RuntimeError("cannot estimate local ground from empty point crop")
    keys = np.floor(outside[:, :2] / float(cell_m)).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    minima = np.full(int(inverse.max()) + 1, np.inf, dtype=np.float64)
    np.minimum.at(minima, inverse, outside[:, 2])
    finite = minima[np.isfinite(minima)]
    if not len(finite):
        raise RuntimeError("local ground cell minima are empty")
    return float(np.median(finite))


def classify_oracle_crop(
    points: np.ndarray,
    reference: BuildingReference,
    *,
    crop_buffer_m: float,
    ground_ring_inner_buffer_m: float,
    minimum_building_height_m: float,
    ground_cell_m: float,
    ground_keep_above_m: float,
    voxel_m: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    values = np.asarray(points, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("points must be Nx3")
    x, y = values[:, 0], values[:, 1]
    footprint = reference.footprint
    in_crop = contains_xy(footprint.buffer(float(crop_buffer_m)), x, y)
    values = values[in_crop]
    x, y = values[:, 0], values[:, 1]
    inside = contains_xy(footprint, x, y)
    outside_inner = ~contains_xy(footprint.buffer(float(ground_ring_inner_buffer_m)), x, y)
    ground_z = estimate_local_ground(values[outside_inner | inside], inside[outside_inner | inside], ground_cell_m)
    building = values[inside & (values[:, 2] >= ground_z + float(minimum_building_height_m))]
    ground = values[(~inside) & outside_inner & (values[:, 2] <= ground_z + float(ground_keep_above_m))]
    building = deterministic_voxel_one(building, voxel_m)
    ground = deterministic_voxel_one(ground, voxel_m)
    if not len(ground):
        raise RuntimeError(f"empty ground support for {reference.stable_id}")
    return building, ground, {
        "source_crop_point_count": int(len(values)),
        "building_class6_count": int(len(building)),
        "ground_class2_count": int(len(ground)),
        "local_ground_z": ground_z,
        "minimum_building_z": None if not len(building) else float(np.min(building[:, 2])),
        "maximum_building_z": None if not len(building) else float(np.max(building[:, 2])),
        "footprint_area_m2": float(reference.footprint.area),
    }


def write_las(path: Path, building: np.ndarray, ground: np.ndarray) -> None:
    import laspy

    xyz = np.vstack((building, ground))
    classes = np.concatenate((np.full(len(building), 6, dtype=np.uint8), np.full(len(ground), 2, dtype=np.uint8)))
    header = laspy.LasHeader(point_format=3, version="1.2")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.floor(np.min(xyz, axis=0) / 1000.0) * 1000.0
    header.system_identifier = "JOINTBUILDGS"
    header.generating_software = "C1C2-ORACLE-v1"
    las = laspy.LasData(header)
    las.x, las.y, las.z = xyz.T
    las.classification = classes
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"refusing to overwrite LAS: {path}")
    las.write(path)


def gaussian_full_ply(state: Mapping[str, torch.Tensor], shift_xyz: Sequence[float]) -> bytes:
    means = state["means"].detach().cpu().numpy().astype(np.float64)
    quats = state["quats"].detach().cpu().numpy().astype(np.float32)
    scales = torch.exp(state["log_scales"].detach().cpu()).numpy().astype(np.float32)
    opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().reshape(-1).astype(np.float32)
    sh0 = state["sh0"].detach().cpu().numpy()
    rgb = np.clip(sh0[:, 0, :] * 0.28209479177387814 + 0.5, 0, 1)
    rgb = np.rint(rgb * 255).astype(np.uint8)
    logits = state["sem_logits"].detach().cpu().numpy().astype(np.float32)
    labels = np.argmax(logits, axis=1).astype(np.uint8)
    normals = quat_to_rotmat(state["quats"].detach().cpu().to(torch.float64))[:, :, 2].numpy().astype(np.float32)
    xyz = means + np.asarray(shift_xyz, dtype=np.float64)
    dtype = np.dtype([
        ("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
        ("quat_w", "<f4"), ("quat_x", "<f4"), ("quat_y", "<f4"), ("quat_z", "<f4"),
        ("scale_x", "<f4"), ("scale_y", "<f4"), ("scale_z", "<f4"), ("opacity", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("semantic_class", "u1"),
        ("semantic_logit_0", "<f4"), ("semantic_logit_1", "<f4"),
        ("semantic_logit_2", "<f4"), ("semantic_logit_3", "<f4"),
    ])
    rows = np.empty(len(xyz), dtype=dtype)
    rows["x"], rows["y"], rows["z"] = xyz.T
    rows["nx"], rows["ny"], rows["nz"] = normals.T
    rows["quat_w"], rows["quat_x"], rows["quat_y"], rows["quat_z"] = quats.T
    rows["scale_x"], rows["scale_y"], rows["scale_z"] = scales.T
    rows["opacity"] = opacity
    rows["red"], rows["green"], rows["blue"] = rgb.T
    rows["semantic_class"] = labels
    for index in range(4):
        rows[f"semantic_logit_{index}"] = logits[:, index]
    properties = "\n".join(
        [
            "property double x", "property double y", "property double z",
            "property float nx", "property float ny", "property float nz",
            "property float quat_w", "property float quat_x", "property float quat_y", "property float quat_z",
            "property float scale_x", "property float scale_y", "property float scale_z", "property float opacity",
            "property uchar red", "property uchar green", "property uchar blue", "property uchar semantic_class",
            "property float semantic_logit_0", "property float semantic_logit_1",
            "property float semantic_logit_2", "property float semantic_logit_3",
        ]
    )
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment JointBuildGS exact full 2D Gaussian parameter export; EPSG:25832\n"
        f"element vertex {len(rows)}\n{properties}\nend_header\n"
    ).encode("ascii")
    return header + rows.tobytes()


def display_proxy_mask(
    state: Mapping[str, torch.Tensor],
    shift_xyz: Sequence[float],
    *,
    opacity_min: float,
    maximum_in_plane_scale_m: float,
    aoi_bbox: Sequence[float],
) -> np.ndarray:
    means = state["means"].detach().cpu().numpy() + np.asarray(shift_xyz, dtype=np.float64)
    scales = torch.exp(state["log_scales"].detach().cpu()).numpy()
    opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().reshape(-1)
    x0, y0, x1, y1 = map(float, aoi_bbox)
    return (
        (opacity >= float(opacity_min))
        & (np.max(scales[:, :2], axis=1) <= float(maximum_in_plane_scale_m))
        & (means[:, 0] >= x0) & (means[:, 0] <= x1)
        & (means[:, 1] >= y0) & (means[:, 1] <= y1)
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
