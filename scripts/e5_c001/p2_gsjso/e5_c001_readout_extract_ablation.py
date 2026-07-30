#!/usr/bin/env python3
"""E5 C001 ③a readout-ablation extractor.

This is a task-scoped variant of ``tum_mob_tsdf_extract.py``.  It keeps the
checkpoint/render path unchanged, but exposes readout-only switches needed for
the C001 ablation: min-observation gate, voxel size, and SOR strength/off.

Frame: GS local + [690953, 5336071, 604] -> EPSG:25832.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, "/workspace/JointBuildGS")

from gsplat import rasterization_2dgs
from pilot_1wave_readout_lineage import (
    CONDITION_ARMS,
    FULL_STATE_CHECKPOINT_FORMAT,
    LINEAGE_SCHEMA,
    canonical_repo_path,
    sha256_file,
    validate_full_state_binding,
)
from src.stage2.colmap_io import read_cameras_bin, read_images_bin


REPO = "/workspace/JointBuildGS"
DENSE = f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense"
SHIFT = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
REPO_PATH = Path(__file__).resolve().parents[3]
C001_SHORT_IDS = [
    "108247349",
    "108247350",
    "108247351",
    "4907184",
    "4907185",
    "4907186",
    "4907188",
    "4907194",
    "4907195",
    "4907198",
    "4907199",
    "4907202",
    "4908168",
    "4908178",
    "4908179",
    "60098",
    "8568391",
    "8568392",
]
PILOT_CROP_CONTRACT_SCHEMA = "jointbuildgs.pilot_1wave.readout_crop_contract.v1"
PILOT_CROP_BBOX_UTM = (
    690764.89,
    5335918.4,
    690964.53,
    5336202.0,
)
PILOT_CROP_AREA_M2 = 56617.904
PILOT_BUILDING_IDS = (
    "DEBY_LOD2_4906966",
    "DEBY_LOD2_4907178",
    "DEBY_LOD2_4907183",
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4907185",
    "DEBY_LOD2_4907186",
    "DEBY_LOD2_4907188",
    "DEBY_LOD2_4907195",
    "DEBY_LOD2_4907196",
    "DEBY_LOD2_4907198",
    "DEBY_LOD2_4907201",
    "DEBY_LOD2_4907202",
    "DEBY_LOD2_4907204",
    "DEBY_LOD2_4907205",
    "DEBY_LOD2_4907206",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_60098",
    "DEBY_LOD2_4907207",
    "DEBY_LOD2_4907165",
    "DEBY_LOD2_4907177",
    "DEBY_LOD2_4907179",
    "DEBY_LOD2_42364665",
    "DEBY_LOD2_4906965",
    "DEBY_LOD2_42364667",
    "DEBY_LOD2_4907176",
    "DEBY_LOD2_4907180",
    "DEBY_LOD2_4906967",
    "DEBY_LOD2_4908023",
    "DEBY_LOD2_4908024",
)
PILOT_ORDERED_IDS_SHA256 = (
    "ae5cbc664941c3b8bb4238767f1d0833a1f7684928a03837047065f85093bb01"
)
PILOT_SET_CSV_REL = Path(
    "phases/p2-gsjso/runs/pilot_1wave/20260721_pilot_1wave/pilot_1wave_pilot_set.csv"
)
PILOT_SET_CSV_SHA256 = (
    "db5ecb6c838499dd3a5f96a4b1abae85414c3d38318d976b7ee598982b566ffc"
)
PILOT_SET_MANIFEST_REL = Path(
    "phases/p2-gsjso/runs/pilot_1wave/20260721_pilot_1wave/"
    "pilot_1wave_pilot_set_manifest.json"
)
PILOT_SET_MANIFEST_SHA256 = (
    "803d18862db926fff353c641e08a03c5938cedf3fb49cc4859751189e83855e2"
)
PILOT_FOOTPRINT_REL = Path("results/tum_transfer/analysis/footprints_aoi.geojson")
PILOT_FOOTPRINT_SHA256 = (
    "ca7f5b13a52368e1d2ac47b77cc78f12887bad4d598d122ad57b882eb4920a82"
)
PILOT_INVENTORY_REL = Path(
    "phases/p2-gsjso/runs/pilot_1wave/20260721_pilot_1wave/calibration/scaffolds/"
    "materialized_input_inventory.json"
)
PILOT_INVENTORY_SHA256 = (
    "30a3387275ee9ed29ad75bbdf7cb1979f2b8b2cd52640225e9dbe00895666450"
)
PILOT_INVENTORY_RECORDS_SHA256 = (
    "b99c38d31b37b59f1827537e520c20c76ca5a0ee0bfbc5baaaa879d4fff57271"
)
PILOT_VIEW_COUNT = 481
PILOT_DATA_ROOT_REL = Path(
    "phases/p2-gsjso/runs/pilot_1wave/20260721_pilot_1wave/prep_artifacts/data"
)
KC = 4
OFF = 1 << 20
MUL = 1 << 21
ROOF = 1
WALL = 2
_STEP_RE = re.compile(r"^step_(\d{6,})\.pt$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--downscale", type=float, default=1.0)
    ap.add_argument("--voxel", type=float, default=0.05)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--min-obs", type=int, default=3)
    ap.add_argument("--sor", choices=["on", "off"], default="on")
    ap.add_argument("--sor-std", type=float, default=2.0)
    ap.add_argument("--sor-neighbors", type=int, default=20)
    ap.add_argument("--buffer", type=float, default=None)
    ap.add_argument("--geojson", default=None)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--max-views", type=int, default=0)
    ap.add_argument("--sh-degree", type=int, default=3)
    ap.add_argument("--targets", nargs="*", default=None)
    ap.add_argument("--no-sem", action="store_true")
    ap.add_argument("--coverage-csv", default=None)
    ap.add_argument("--metrics-json", default=None)
    ap.add_argument("--provenance-json", default=None)
    ap.add_argument("--condition", choices=tuple(CONDITION_ARMS), default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--checkpoint-step", type=int, default=None)
    ap.add_argument("--full-state-manifest", default=None)
    ap.add_argument("--coverage-grid", type=float, default=0.5)
    return ap.parse_args()


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} mismatch: {actual!r} != {expected!r}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _ordered_ids_sha256(building_ids: list[str] | tuple[str, ...]) -> str:
    return hashlib.sha256(
        ("\n".join(building_ids) + "\n").encode("utf-8")
    ).hexdigest()


def _load_locked_json(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    _require_equal(sha256_file(path), expected_sha256, f"{label} SHA256")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} root must be an object: {path}")
    return payload


def _validate_locked_bbox(values: Any, label: str) -> None:
    try:
        bbox = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must contain four numeric coordinates") from exc
    _require_equal(bbox, PILOT_CROP_BBOX_UTM, label)


def build_pilot_crop_contract(*, repo_root: Path = REPO_PATH) -> dict[str, Any]:
    """Build the immutable expanded-pilot crop contract from locked sources.

    Every source is whole-file SHA checked before any field is trusted.  The
    redundant content checks make the intended 30-building order, one global
    crop box, and 481-view materialized input explicit rather than relying on
    the legacy C001 defaults in this extractor.
    """

    repo_root = repo_root.resolve()
    csv_path = repo_root / PILOT_SET_CSV_REL
    manifest_path = repo_root / PILOT_SET_MANIFEST_REL
    footprint_path = repo_root / PILOT_FOOTPRINT_REL
    inventory_path = repo_root / PILOT_INVENTORY_REL

    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    _require_equal(
        sha256_file(csv_path), PILOT_SET_CSV_SHA256, "pilot set CSV SHA256"
    )
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    _require_equal(len(rows), len(PILOT_BUILDING_IDS), "pilot set row count")
    csv_ids = tuple(str(row.get("building_id", "")) for row in rows)
    _require_equal(csv_ids, PILOT_BUILDING_IDS, "pilot set ordered building IDs")
    _require_equal(
        tuple(int(row.get("selection_rank", -1)) for row in rows),
        tuple(range(1, len(PILOT_BUILDING_IDS) + 1)),
        "pilot set selection ranks",
    )
    for row in rows:
        _validate_locked_bbox(
            (
                row.get("training_crop_aoi_minx"),
                row.get("training_crop_aoi_miny"),
                row.get("training_crop_aoi_maxx"),
                row.get("training_crop_aoi_maxy"),
            ),
            f"pilot CSV training crop bbox for {row.get('building_id')}",
        )
        _require_equal(row.get("footprint_source_sha256"), PILOT_FOOTPRINT_SHA256,
                       f"pilot CSV footprint SHA256 for {row.get('building_id')}")
        _require_equal(row.get("crs"), "EPSG:25832",
                       f"pilot CSV CRS for {row.get('building_id')}")

    ordered_ids_sha = _ordered_ids_sha256(csv_ids)
    _require_equal(
        ordered_ids_sha, PILOT_ORDERED_IDS_SHA256, "ordered building IDs SHA256"
    )

    manifest = _load_locked_json(
        manifest_path, PILOT_SET_MANIFEST_SHA256, "pilot set manifest"
    )
    _require_equal(
        manifest.get("schema"),
        "jointbuildgs.pilot_1wave.pilot_set.v1",
        "pilot set manifest schema",
    )
    selection = manifest.get("selection")
    if not isinstance(selection, Mapping):
        raise RuntimeError("pilot set manifest selection must be an object")
    _require_equal(
        int(selection.get("selection_count", -1)),
        len(PILOT_BUILDING_IDS),
        "pilot manifest selection count",
    )
    _require_equal(
        tuple(selection.get("selected_ids_in_rank_order", [])),
        PILOT_BUILDING_IDS,
        "pilot manifest ordered building IDs",
    )
    _require_equal(
        selection.get("ordered_ids_sha256"),
        PILOT_ORDERED_IDS_SHA256,
        "pilot manifest ordered IDs SHA256",
    )
    _validate_locked_bbox(selection.get("training_crop_bbox"),
                          "pilot manifest training crop bbox")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise RuntimeError("pilot set manifest outputs must be an object")
    csv_record = outputs.get(PILOT_SET_CSV_REL.name)
    if not isinstance(csv_record, Mapping):
        raise RuntimeError("pilot set manifest lacks its CSV record")
    _require_equal(
        csv_record.get("sha256"), PILOT_SET_CSV_SHA256,
        "pilot manifest CSV SHA256",
    )
    _require_equal(
        int(csv_record.get("row_count", -1)), len(PILOT_BUILDING_IDS),
        "pilot manifest CSV row count",
    )

    footprint_payload = _load_locked_json(
        footprint_path, PILOT_FOOTPRINT_SHA256, "footprint source"
    )
    features = footprint_payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError("footprint source features must be an array")
    footprint_counts: dict[str, int] = {}
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            continue
        building_id = str(properties.get("building_id", ""))
        if building_id in PILOT_BUILDING_IDS:
            footprint_counts[building_id] = footprint_counts.get(building_id, 0) + 1
    missing = [building_id for building_id in PILOT_BUILDING_IDS
               if footprint_counts.get(building_id, 0) == 0]
    duplicates = [building_id for building_id in PILOT_BUILDING_IDS
                  if footprint_counts.get(building_id, 0) != 1
                  and footprint_counts.get(building_id, 0) > 0]
    if missing or duplicates:
        raise RuntimeError(
            "locked footprint population drift: "
            f"missing={missing}, duplicate={duplicates}"
        )

    inventory = _load_locked_json(
        inventory_path, PILOT_INVENTORY_SHA256, "materialized input inventory"
    )
    _require_equal(
        inventory.get("schema"),
        "jointbuildgs.pilot_1wave.materialized_input_inventory.v1",
        "materialized input inventory schema",
    )
    records = inventory.get("records")
    if not isinstance(records, list):
        raise RuntimeError("materialized input inventory records must be an array")
    _require_equal(
        _json_sha256(records), PILOT_INVENTORY_RECORDS_SHA256,
        "materialized input records SHA256",
    )
    _require_equal(
        inventory.get("records_sha256"), PILOT_INVENTORY_RECORDS_SHA256,
        "materialized inventory records SHA256",
    )
    _require_equal(
        int(inventory.get("view_count", -1)), PILOT_VIEW_COUNT,
        "materialized input view count",
    )
    view_ids = inventory.get("view_ids")
    if not isinstance(view_ids, list):
        raise RuntimeError("materialized input view_ids must be an array")
    _require_equal(len(view_ids), PILOT_VIEW_COUNT, "materialized view ID count")
    _require_equal(len(set(view_ids)), PILOT_VIEW_COUNT,
                   "materialized unique view ID count")
    _require_equal(
        inventory.get("data_root"), PILOT_DATA_ROOT_REL.as_posix(),
        "materialized input data root",
    )

    width = Decimal(str(PILOT_CROP_BBOX_UTM[2])) - Decimal(
        str(PILOT_CROP_BBOX_UTM[0])
    )
    height = Decimal(str(PILOT_CROP_BBOX_UTM[3])) - Decimal(
        str(PILOT_CROP_BBOX_UTM[1])
    )
    _require_equal(
        width * height, Decimal(str(PILOT_CROP_AREA_M2)), "pilot crop area m2"
    )

    return {
        "schema": PILOT_CROP_CONTRACT_SCHEMA,
        "crs": "EPSG:25832",
        "crop": {
            "mode": "single_locked_global_bbox",
            "bbox_utm": list(PILOT_CROP_BBOX_UTM),
            "area_m2": PILOT_CROP_AREA_M2,
        },
        "population": {
            "count": len(PILOT_BUILDING_IDS),
            "ordered_building_ids": list(PILOT_BUILDING_IDS),
            "ordered_ids_sha256": PILOT_ORDERED_IDS_SHA256,
        },
        "pilot_set_csv": {
            "path": PILOT_SET_CSV_REL.as_posix(),
            "sha256": PILOT_SET_CSV_SHA256,
        },
        "pilot_set_manifest": {
            "path": PILOT_SET_MANIFEST_REL.as_posix(),
            "sha256": PILOT_SET_MANIFEST_SHA256,
        },
        "footprint_source": {
            "path": PILOT_FOOTPRINT_REL.as_posix(),
            "sha256": PILOT_FOOTPRINT_SHA256,
            "allowed_content": "LoD2 GroundSurface XY only",
        },
        "materialized_input_inventory": {
            "path": PILOT_INVENTORY_REL.as_posix(),
            "sha256": PILOT_INVENTORY_SHA256,
            "records_sha256": PILOT_INVENTORY_RECORDS_SHA256,
            "view_count": PILOT_VIEW_COUNT,
            "view_ids_sha256": _ordered_ids_sha256(tuple(str(x) for x in view_ids)),
            "data_root": PILOT_DATA_ROOT_REL.as_posix(),
        },
    }


def _encode_crop_contract(contract: Mapping[str, Any]) -> tuple[str, str]:
    _require_equal(
        contract.get("schema"), PILOT_CROP_CONTRACT_SCHEMA,
        "crop contract schema",
    )
    encoded = _canonical_json(contract)
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _attach_crop_contract(
    lineage: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    if lineage.get("verified_full_state") is not True:
        raise RuntimeError("crop contract may only bind a verified full-state readout")
    encoded, digest = _encode_crop_contract(contract)
    return {
        **dict(lineage),
        "crop_contract_json": encoded,
        "crop_contract_sha256": digest,
    }


def _validated_crop_contract_binding(
    lineage: Mapping[str, Any],
) -> tuple[str, str] | None:
    encoded = lineage.get("crop_contract_json")
    digest = lineage.get("crop_contract_sha256")
    if lineage.get("verified_full_state") is True:
        if not isinstance(encoded, str) or not isinstance(digest, str):
            raise RuntimeError("verified readout lineage lacks crop contract binding")
        _require_equal(
            hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            digest,
            "crop contract SHA256",
        )
        try:
            contract = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise RuntimeError("crop contract JSON is invalid") from exc
        if not isinstance(contract, dict):
            raise RuntimeError("crop contract JSON root must be an object")
        _require_equal(
            contract.get("schema"), PILOT_CROP_CONTRACT_SCHEMA,
            "crop contract schema",
        )
        _require_equal(
            contract,
            build_pilot_crop_contract(),
            "crop contract locked contents",
        )
        return encoded, digest
    if encoded is not None or digest is not None:
        raise RuntimeError("unverified legacy lineage must not carry a pilot crop contract")
    return None


def _crop_contract_fields(lineage: Mapping[str, Any]) -> dict[str, np.ndarray]:
    binding = _validated_crop_contract_binding(lineage)
    if binding is None:
        return {}
    encoded, digest = binding
    return {
        "crop_contract_json": np.array(encoded),
        "crop_contract_sha256": np.array(digest),
    }


def _canonical_condition_seed(checkpoint_path: Path) -> tuple[str | None, int | None]:
    """Infer only the canonical ``runs/<condition>/seed_<seed>/ckpt`` layout."""

    parts = checkpoint_path.resolve().parts
    if len(parts) < 4 or parts[-2] != "ckpt" or not parts[-3].startswith("seed_"):
        return None, None
    condition = parts[-4]
    try:
        seed = int(parts[-3].removeprefix("seed_"))
    except ValueError:
        return None, None
    if condition not in CONDITION_ARMS:
        return None, None
    return condition, seed


def _checkpoint_identity(
    checkpoint_path: Path,
    payload: Mapping[str, Any],
    *,
    condition: str | None,
    seed: int | None,
    checkpoint_step: int | None,
    full_state_manifest: str | None,
) -> tuple[Mapping[str, torch.Tensor], dict[str, Any]]:
    """Return a model state and immutable provenance for both checkpoint formats."""

    inferred_condition, inferred_seed = _canonical_condition_seed(checkpoint_path)
    condition_id = condition or inferred_condition
    resolved_seed = seed if seed is not None else inferred_seed
    if condition_id is None or resolved_seed is None:
        raise RuntimeError(
            "checkpoint condition/seed are not canonical; pass --condition and --seed"
        )
    if condition is not None and inferred_condition is not None and condition != inferred_condition:
        raise RuntimeError(
            f"checkpoint path/--condition mismatch: {inferred_condition} != {condition}"
        )
    if seed is not None and inferred_seed is not None and int(seed) != inferred_seed:
        raise RuntimeError(f"checkpoint path/--seed mismatch: {inferred_seed} != {seed}")

    checkpoint_path = checkpoint_path.resolve()
    checkpoint_sha = sha256_file(checkpoint_path)
    if payload.get("checkpoint_format") == FULL_STATE_CHECKPOINT_FORMAT:
        model = payload.get("model")
        if not isinstance(model, Mapping) or not isinstance(model.get("state_dict"), Mapping):
            raise RuntimeError("full-state checkpoint lacks model.state_dict")
        completed_steps = int(payload.get("completed_steps", -1))
        if checkpoint_step is not None and int(checkpoint_step) != completed_steps:
            raise RuntimeError(
                f"checkpoint payload/--checkpoint-step mismatch: "
                f"{completed_steps} != {checkpoint_step}"
            )
        manifest_path = (
            Path(full_state_manifest)
            if full_state_manifest
            else checkpoint_path.parent.parent / "full_state_manifest.json"
        )
        lineage = validate_full_state_binding(
            checkpoint_path=checkpoint_path,
            checkpoint_sha256=checkpoint_sha,
            completed_steps=completed_steps,
            condition_id=condition_id,
            seed=int(resolved_seed),
            manifest_path=manifest_path,
            checkpoint_binding_sha256=payload.get("binding_sha256"),
        )
        return model["state_dict"], lineage

    state_dict = payload.get("state_dict")
    if not isinstance(state_dict, Mapping):
        raise RuntimeError(
            "unsupported checkpoint: expected full-state model.state_dict or legacy state_dict"
        )
    match = _STEP_RE.fullmatch(checkpoint_path.name)
    payload_step = payload.get("it")
    completed_steps = (
        int(checkpoint_step)
        if checkpoint_step is not None
        else int(payload_step)
        if payload_step is not None
        else int(match.group(1))
        if match is not None
        else -1
    )
    if completed_steps < 0:
        raise RuntimeError("legacy checkpoint step is unknown; pass --checkpoint-step")
    if payload_step is not None and int(payload_step) != completed_steps:
        raise RuntimeError(
            f"legacy checkpoint payload/step mismatch: {payload_step} != {completed_steps}"
        )
    lineage = {
        "schema": LINEAGE_SCHEMA,
        "condition_id": condition_id,
        "seed": int(resolved_seed),
        "checkpoint": {
            "format": "legacy_state_dict",
            "path": canonical_repo_path(checkpoint_path),
            "sha256": checkpoint_sha,
            "completed_steps": completed_steps,
            "step_semantics": "legacy_iteration",
        },
        "full_state_manifest": None,
        "training_config": None,
        "verified_full_state": False,
        "eligible_20k_full_state": False,
    }
    return state_dict, lineage


def _write_provenance(
    args: argparse.Namespace,
    *,
    lineage: Mapping[str, Any],
    point_count: int,
    footprint_path: Path,
) -> Path:
    output = Path(args.out).resolve()
    path = (
        Path(args.provenance_json).resolve()
        if args.provenance_json
        else Path(f"{output}.provenance.json")
    )
    crop_binding = _validated_crop_contract_binding(lineage)
    payload: dict[str, Any] = {
        "schema": "jointbuildgs.pilot_1wave.readout_extraction.v1",
        "state": "complete",
        "output_npz": {
            "path": str(output),
            "sha256": sha256_file(output),
            "point_count": int(point_count),
        },
        "readout_lineage": dict(lineage),
        "geometry_only": bool(args.no_sem),
        "crs": "EPSG:25832",
        "reference_inputs": {
            "groundsurface_xy_footprint": str(footprint_path.resolve()),
            "lod2_z": False,
            "roofsurface": False,
            "semantic_class": False,
            "als": False,
        },
    }
    if crop_binding is not None:
        payload["crop_contract_json"], payload["crop_contract_sha256"] = crop_binding
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def target_ids(short_ids: list[str] | None) -> list[str]:
    return [f"DEBY_LOD2_{sid}" for sid in (short_ids or C001_SHORT_IDS)]


def _load_footprints_for_ids(
    path: Path, ordered_ids: list[str] | tuple[str, ...]
) -> dict[str, np.ndarray]:
    wanted = set(ordered_ids)
    payload = json.loads(path.read_text(encoding="utf-8"))
    found: dict[str, np.ndarray] = {}
    for feat in payload["features"]:
        bid = feat.get("properties", {}).get("building_id")
        if bid not in wanted:
            continue
        if bid in found:
            raise RuntimeError(f"duplicate target footprint: {bid}")
        geom = feat["geometry"]
        coords = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
        ring = np.asarray(coords, dtype=np.float64)[:, :2]
        found[bid] = ring
    missing = [building_id for building_id in ordered_ids if building_id not in found]
    if missing:
        raise RuntimeError(f"missing target footprints: {missing}")
    return {building_id: found[building_id] for building_id in ordered_ids}


def load_footprints(
    path: str, target_short_ids: list[str] | None
) -> tuple[dict[str, np.ndarray], list[list[float]]]:
    """Legacy C001 footprint-box behavior for unverified checkpoints only."""

    rings = _load_footprints_for_ids(Path(path), target_ids(target_short_ids))
    boxes: list[list[float]] = []
    for ring in rings.values():
        x0, y0 = ring[:, 0].min(), ring[:, 1].min()
        x1, y1 = ring[:, 0].max(), ring[:, 1].max()
        boxes.append([x0 - SHIFT[0], y0 - SHIFT[1], x1 - SHIFT[0], y1 - SHIFT[1]])
    return rings, boxes


def _resolve_readout_scope(
    args: argparse.Namespace,
    lineage: Mapping[str, Any],
    *,
    repo_root: Path = REPO_PATH,
) -> tuple[
    dict[str, np.ndarray],
    list[list[float]],
    Path,
    Path,
    dict[str, Any],
    tuple[str, ...] | None,
]:
    """Resolve either the locked P1W scene crop or the legacy C001 fallback."""

    if lineage.get("verified_full_state") is True:
        if args.targets is not None:
            raise RuntimeError(
                "verified P1W readout forbids --targets; the locked 30-ID order is mandatory"
            )
        if args.buffer is not None:
            raise RuntimeError(
                "verified P1W readout forbids --buffer; the locked global bbox is mandatory"
            )
        if int(args.max_views) != 0:
            raise RuntimeError(
                "verified P1W readout forbids --max-views; all 481 locked views are mandatory"
            )

        repo_root = repo_root.resolve()
        footprint_path = (repo_root / PILOT_FOOTPRINT_REL).resolve()
        data_root = (repo_root / PILOT_DATA_ROOT_REL).resolve()
        if args.geojson is not None:
            _require_equal(
                Path(args.geojson).resolve(),
                footprint_path,
                "verified P1W footprint source path",
            )
        if args.data_root is not None:
            _require_equal(
                Path(args.data_root).resolve(),
                data_root,
                "verified P1W materialized data root",
            )

        contract = build_pilot_crop_contract(repo_root=repo_root)
        footprints = _load_footprints_for_ids(footprint_path, PILOT_BUILDING_IDS)
        global_box = contract["crop"]["bbox_utm"]
        boxes = [[
            float(global_box[0]) - SHIFT[0],
            float(global_box[1]) - SHIFT[1],
            float(global_box[2]) - SHIFT[0],
            float(global_box[3]) - SHIFT[1],
        ]]
        inventory = json.loads(
            (repo_root / PILOT_INVENTORY_REL).read_text(encoding="utf-8")
        )
        expected_view_ids = tuple(str(value) for value in inventory["view_ids"])
        return (
            footprints,
            boxes,
            footprint_path,
            data_root,
            _attach_crop_contract(lineage, contract),
            expected_view_ids,
        )

    footprint_path = Path(
        args.geojson
        or f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"
    ).resolve()
    data_root = Path(args.data_root or DENSE).resolve()
    target_short_ids = args.targets if args.targets else C001_SHORT_IDS
    footprints, boxes = load_footprints(str(footprint_path), target_short_ids)
    return footprints, boxes, footprint_path, data_root, dict(lineage), None


def points_in_poly(points: np.ndarray, ring: np.ndarray) -> np.ndarray:
    if len(points) == 0:
        return np.zeros(0, dtype=bool)
    x = points[:, 0]
    y = points[:, 1]
    xv = ring[:, 0]
    yv = ring[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    j = len(ring) - 1
    for i in range(len(ring)):
        cond = ((yv[i] > y) != (yv[j] > y)) & (x < (xv[j] - xv[i]) * (y - yv[i]) / ((yv[j] - yv[i]) + 1e-12) + xv[i])
        inside ^= cond
        j = i
    return inside


def footprint_grid(ring: np.ndarray, spacing: float) -> np.ndarray:
    minx, miny = ring.min(axis=0)
    maxx, maxy = ring.max(axis=0)
    xs = np.arange(minx + spacing / 2.0, maxx, spacing)
    ys = np.arange(miny + spacing / 2.0, maxy, spacing)
    if xs.size == 0 or ys.size == 0:
        c = ring.mean(axis=0, keepdims=True)
        return c
    xx, yy = np.meshgrid(xs, ys)
    pts = np.column_stack([xx.ravel(), yy.ravel()])
    mask = points_in_poly(pts, ring)
    if not np.any(mask):
        return ring.mean(axis=0, keepdims=True)
    return pts[mask]


def coverage_rows(points: np.ndarray, classes: np.ndarray | None, footprints: dict[str, np.ndarray], stage: str, spacing: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if classes is not None and len(classes) == len(points):
        mask = (classes == ROOF) | (classes == WALL)
        use = points[mask]
    else:
        use = points
    for bid, ring in footprints.items():
        grid = footprint_grid(ring, spacing)
        if len(grid) == 0:
            rows.append({"stage": stage, "building_id": bid, "occupied_cells": 0, "grid_total_cells": 0, "coverage_frac": ""})
            continue
        cell_xy = np.floor(grid / spacing).astype(np.int64)
        total = len({(int(a), int(b)) for a, b in cell_xy})
        if len(use) == 0:
            occupied = 0
        else:
            in_fp = points_in_poly(use[:, :2], ring)
            q = np.floor(use[in_fp, :2] / spacing).astype(np.int64)
            grid_set = {(int(a), int(b)) for a, b in cell_xy}
            occupied = len({(int(a), int(b)) for a, b in q if (int(a), int(b)) in grid_set})
        frac = min(1.0, occupied / total) if total else 0.0
        rows.append(
            {
                "stage": stage,
                "building_id": bid,
                "occupied_cells": occupied,
                "grid_total_cells": total,
                "coverage_frac": frac,
            }
        )
    return rows


def decode_keys(keys: torch.Tensor, voxel: float,
                chunk_size: int = 1_000_000) -> np.ndarray:
    """Decode voxel keys with the original arithmetic and bounded temporaries."""

    if keys.ndim != 1:
        raise ValueError(f"voxel keys must be one-dimensional, got {keys.shape}")
    if chunk_size <= 0:
        raise ValueError(f"decode chunk size must be positive, got {chunk_size}")
    encoded = keys.detach().cpu().numpy()
    result = np.empty((len(encoded), 3), dtype=np.float64)
    for start in range(0, len(encoded), chunk_size):
        stop = min(start + chunk_size, len(encoded))
        work = encoded[start:stop].astype(np.int64, copy=True)
        result[start:stop, 2] = (
            ((work % MUL) - OFF).astype(np.float64) + 0.5
        ) * voxel + SHIFT[2]
        work //= MUL
        result[start:stop, 1] = (
            ((work % MUL) - OFF).astype(np.float64) + 0.5
        ) * voxel + SHIFT[1]
        work //= MUL
        result[start:stop, 0] = (
            (work - OFF).astype(np.float64) + 0.5
        ) * voxel + SHIFT[0]
    return result


def write_csv(path: str | None, rows: list[dict[str, Any]]) -> None:
    if path is None:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    dev = "cuda"

    checkpoint_path = Path(args.ckpt).resolve()
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, Mapping):
        raise RuntimeError("checkpoint payload must be a mapping")
    sd, readout_lineage = _checkpoint_identity(
        checkpoint_path,
        ckpt,
        condition=args.condition,
        seed=args.seed,
        checkpoint_step=args.checkpoint_step,
        full_state_manifest=args.full_state_manifest,
    )
    del ckpt
    readout_lineage = {
        **readout_lineage,
        "geometry_only": bool(args.no_sem),
    }
    (
        footprints,
        boxes,
        footprint_path,
        data_root,
        readout_lineage,
        expected_view_ids,
    ) = _resolve_readout_scope(args, readout_lineage)
    crop_mode = (
        "single locked global bbox"
        if readout_lineage.get("verified_full_state") is True
        else "legacy per-footprint boxes"
    )
    print(f"[boxes] {len(boxes)} crop box(es); mode={crop_mode}")

    means = sd["means"].to(dev)
    quats = sd["quats"].to(dev)
    scales = torch.exp(sd["log_scales"]).to(dev)
    opac = torch.sigmoid(sd["opacities_raw"]).to(dev).ravel()
    colors = torch.cat([sd["sh0"], sd["shN"]], dim=1).to(dev)
    sem = sd.get("sem_logits")
    do_sem = (sem is not None) and (not args.no_sem)
    if do_sem:
        sem = sem.to(dev)
        sem = sem.unsqueeze(0) if sem.ndim == 2 else sem
        print(f"[sem] GS-semantic feature pass ON (K={sem.shape[-1]})")
    else:
        sem = None
        print("[sem] GS-semantic OFF")
    # GPU tensors above own the read-out values.  The full CPU state dict is
    # no longer needed and retaining it adds 1--2 GiB for the larger arms.
    del sd
    print(
        f"[model] N={means.shape[0]} ckpt={args.ckpt} "
        f"condition={readout_lineage['condition_id']} "
        f"seed={readout_lineage['seed']} "
        f"step={readout_lineage['checkpoint']['completed_steps']}"
    )

    sparse_dir = data_root / "sparse"
    if (sparse_dir / "0" / "cameras.bin").exists():
        sparse_dir = sparse_dir / "0"
    cams = read_cameras_bin(sparse_dir / "cameras.bin")
    imgs = list(read_images_bin(sparse_dir / "images.bin").values())
    if args.max_views:
        imgs = imgs[: args.max_views]
    if expected_view_ids is not None:
        actual_view_ids = tuple(str(image.name) for image in imgs)
        _require_equal(len(actual_view_ids), PILOT_VIEW_COUNT,
                       "verified P1W COLMAP view count")
        _require_equal(len(set(actual_view_ids)), PILOT_VIEW_COUNT,
                       "verified P1W unique COLMAP view count")
        _require_equal(set(actual_view_ids), set(expected_view_ids),
                       "verified P1W COLMAP view IDs")

    keylist: list[torch.Tensor] = []
    clslist: list[torch.Tensor] = []

    def add_keys(points: torch.Tensor, cls: torch.Tensor | None = None) -> None:
        q = torch.floor(points / args.voxel).to(torch.int64) + OFF
        k = (q[:, 0] * MUL + q[:, 1]) * MUL + q[:, 2]
        if cls is None:
            keylist.append(torch.unique(k).cpu())
            return
        uk_v, inv_v = torch.unique(k, return_inverse=True)
        hist = torch.zeros((uk_v.shape[0], KC), device=points.device)
        hist.index_add_(0, inv_v, torch.nn.functional.one_hot(cls, KC).float())
        keylist.append(uk_v.cpu())
        clslist.append(hist.argmax(1).to(torch.int64).cpu())

    n_surf = 0
    zlo, zhi = -120.0, 80.0
    for i, image in enumerate(imgs):
        cam = cams[image.camera_id]
        k0 = cam.K()
        w0, h0 = cam.width, cam.height
        scale = 1.0 / args.downscale
        width, height = int(round(w0 * scale)), int(round(h0 * scale))
        k_mat = k0.copy()
        k_mat[:2, :] *= scale
        kt = torch.tensor(k_mat, dtype=torch.float32, device=dev)
        uu, vv = np.meshgrid(np.arange(width), np.arange(height))
        uu = uu.ravel()
        vv = vv.ravel()
        ud = torch.tensor((uu - k_mat[0, 2]) / k_mat[0, 0], dtype=torch.float32, device=dev)
        vd = torch.tensor((vv - k_mat[1, 2]) / k_mat[1, 1], dtype=torch.float32, device=dev)
        r_mat = torch.tensor(image.R(), dtype=torch.float32, device=dev)
        t_vec = torch.tensor(image.tvec, dtype=torch.float32, device=dev)
        viewmat = torch.eye(4, device=dev)
        viewmat[:3, :3] = r_mat
        viewmat[:3, 3] = t_vec
        with torch.no_grad():
            out = rasterization_2dgs(
                means=means,
                quats=quats,
                scales=scales,
                opacities=opac,
                colors=colors,
                viewmats=viewmat.unsqueeze(0),
                Ks=kt.unsqueeze(0),
                width=width,
                height=height,
                near_plane=0.01,
                far_plane=1e10,
                render_mode="RGB+ED",
                depth_mode="expected",
                sh_degree=args.sh_degree,
            )
            cls_pix = None
            if do_sem:
                fout = rasterization_2dgs(
                    means=means,
                    quats=quats,
                    scales=scales,
                    opacities=opac,
                    colors=sem,
                    viewmats=viewmat.unsqueeze(0),
                    Ks=kt.unsqueeze(0),
                    width=width,
                    height=height,
                    near_plane=0.01,
                    far_plane=1e10,
                    render_mode="RGB",
                    sh_degree=None,
                )
                cls_pix = fout[0][0].reshape(-1, sem.shape[-1]).argmax(-1)
        alpha = out[1][0, ..., 0].reshape(-1)
        median_depth = out[5][0, ..., 0].reshape(-1)
        mask = (alpha > args.alpha) & (median_depth > 0) & (median_depth < 500)
        if mask.sum() == 0:
            continue
        depth = median_depth[mask]
        xc = ud[mask] * depth
        yc = vd[mask] * depth
        x_cam = torch.stack([xc, yc, depth], dim=1)
        x_world = (x_cam - t_vec) @ r_mat
        sel = (x_world[:, 2] >= zlo) & (x_world[:, 2] <= zhi)
        inbox = torch.zeros_like(sel)
        for bx in boxes:
            inbox |= (x_world[:, 0] >= bx[0]) & (x_world[:, 0] <= bx[2]) & (x_world[:, 1] >= bx[1]) & (x_world[:, 1] <= bx[3])
        keep = sel & inbox
        x_world = x_world[keep]
        if len(x_world):
            if do_sem and cls_pix is not None:
                add_keys(x_world, cls_pix[mask][keep])
            else:
                add_keys(x_world)
            n_surf += len(x_world)
        if (i + 1) % 200 == 0:
            print(f"  view {i + 1}/{len(imgs)}", flush=True)

    del means, quats, scales, opac, colors, sem
    torch.cuda.empty_cache()

    if not keylist:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        empty = np.empty((0, 3), dtype=np.float64)
        np.savez(
            args.out,
            P_utm=empty,
            P_utm_clean=empty,
            voxel=args.voxel,
            downscale=args.downscale,
            readout_lineage_json=np.array(
                json.dumps(
                    readout_lineage,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            ),
            **_crop_contract_fields(readout_lineage),
        )
        write_csv(args.coverage_csv, [])
        provenance_path = _write_provenance(
            args,
            lineage=readout_lineage,
            point_count=0,
            footprint_path=footprint_path,
        )
        if args.metrics_json:
            Path(args.metrics_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.metrics_json).write_text(
                json.dumps(
                    {
                        "surf_backproj": 0,
                        "fused_all": 0,
                        "readout_lineage": readout_lineage,
                        "provenance_json": str(provenance_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
        print(f"[done] no points -> {args.out} provenance={provenance_path}")
        return

    all_keys = torch.cat(keylist)
    keylist.clear()
    del keylist
    if do_sem:
        all_classes = torch.cat(clslist)
        clslist.clear()
        del clslist
        uk_all, inv_all = torch.unique(all_keys, return_inverse=True)
        counts = torch.bincount(inv_all, minlength=uk_all.shape[0])
        hist = torch.zeros((uk_all.shape[0], KC))
        hist.index_add_(0, inv_all, torch.nn.functional.one_hot(all_classes, KC).float())
        classes_all = hist.argmax(1)
        keep = counts >= args.min_obs
        uk = uk_all[keep]
        classes = classes_all[keep]
    else:
        clslist.clear()
        del clslist
        uk_all, counts = torch.unique(all_keys, return_counts=True)
        classes_all = None
        keep = counts >= args.min_obs
        uk = uk_all[keep]
        classes = None
    fused_all_count = int(len(uk_all))
    minobs_kept_count = int(len(uk))
    print(
        f"[consensus] min_obs={args.min_obs}: "
        f"kept {minobs_kept_count}/{fused_all_count} voxels"
    )

    p_class_all = (
        classes_all.numpy().astype(np.int32) if classes_all is not None else None
    )
    p_class = classes.numpy().astype(np.int32) if classes is not None else None
    del all_keys, counts, keep
    if do_sem:
        del all_classes, inv_all, hist, classes_all, classes

    p_all = decode_keys(uk_all, args.voxel)
    del uk_all
    p_utm = decode_keys(uk, args.voxel)
    del uk

    # Preserve the original CSV row order while releasing the all-voxel array
    # before Open3D builds its SOR neighbor index.  P_all is not an NPZ output.
    coverage: list[dict[str, Any]] = []
    coverage.extend(coverage_rows(
        p_all, p_class_all, footprints, "voxel_all_pre_minobs", args.coverage_grid
    ))
    del p_all, p_class_all
    coverage.extend(coverage_rows(
        p_utm, p_class, footprints, "minobs_post_gate_pre_sor", args.coverage_grid
    ))

    p_utm_clean = p_utm
    p_class_clean = p_class
    sor_status = "off"
    if args.sor == "on":
        try:
            import open3d as o3d

            pc = o3d.geometry.PointCloud()
            pc.points = o3d.utility.Vector3dVector(p_utm)
            pc2, ind = pc.remove_statistical_outlier(nb_neighbors=args.sor_neighbors, std_ratio=args.sor_std)
            p_utm_clean = np.asarray(pc2.points)
            if p_class is not None:
                p_class_clean = p_class[np.asarray(ind, dtype=np.int64)]
            sor_status = "on"
            print(f"[sor] std={args.sor_std} kept {len(p_utm_clean)}/{len(p_utm)}")
        except Exception as exc:  # noqa: BLE001 - preserve extraction even if Open3D fails.
            print("[sor] skipped:", repr(exc))
            sor_status = f"error:{exc!r}"
    else:
        print("[sor] off")

    coverage.extend(coverage_rows(
        p_utm_clean, p_class_clean, footprints, "sor_post_clean", args.coverage_grid
    ))
    write_csv(args.coverage_csv, coverage)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    save = {
        "P_utm": p_utm,
        "P_utm_clean": p_utm_clean,
        "voxel": args.voxel,
        "downscale": args.downscale,
        "min_obs": args.min_obs,
        "alpha": args.alpha,
        "sor": np.array(args.sor),
        "sor_std": args.sor_std,
        "sor_neighbors": args.sor_neighbors,
        "readout_lineage_json": np.array(
            json.dumps(
                readout_lineage,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        ),
    }
    save.update(_crop_contract_fields(readout_lineage))
    if p_class is not None:
        save.update(
            {
                "P_class": p_class,
                "P_class_clean": p_class_clean,
                "class_names": np.array(["BG", "Roof", "Wall", "Terrain"]),
            }
        )
        uniq, cnt = np.unique(p_class_clean, return_counts=True)
        names = ["BG", "Roof", "Wall", "Terrain"]
        print("[sem] fused class dist:", {names[int(a)]: int(b) for a, b in zip(uniq, cnt)})
    np.savez(args.out, **save)

    metrics = {
        "surf_backproj": int(n_surf),
        "fused_all": fused_all_count,
        "minobs_kept": int(len(p_utm)),
        "sor_kept": int(len(p_utm_clean)),
        "minobs": int(args.min_obs),
        "voxel": float(args.voxel),
        "alpha": float(args.alpha),
        "sor": args.sor,
        "sor_status": sor_status,
        "sor_std": float(args.sor_std),
        "sor_neighbors": int(args.sor_neighbors),
    }
    provenance_path = _write_provenance(
        args,
        lineage=readout_lineage,
        point_count=len(p_utm_clean),
        footprint_path=footprint_path,
    )
    metrics["readout_lineage"] = readout_lineage
    metrics["provenance_json"] = str(provenance_path)
    if args.metrics_json:
        Path(args.metrics_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.metrics_json).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[done] surf_backproj={n_surf} fused={len(p_utm)} "
        f"clean={len(p_utm_clean)} -> {args.out} provenance={provenance_path}"
    )


if __name__ == "__main__":
    main()
