"""One common, non-GT Stage-3 contract for the five Gate S0 conditions.

This module does not run a building-quality comparison.  It derives the polygon
required by Roofer exclusively from the condition's class-6 point evidence and
serializes a deterministic synthetic CityJSONSeq smoke payload.  An external or
reference-derived roofprint is rejected at the API boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
from shapely.geometry import MultiPoint, Polygon


CONDITIONS = (
    "C1_L_upper",
    "C2_MVS",
    "C3_GS_image",
    "C4_GS_lidar_prior",
    "C5_GS_lod1_prior",
)


@dataclass(frozen=True)
class DerivedRoofprint:
    condition_id: str
    protocol: str
    coordinates: tuple[tuple[float, float], ...]
    building_point_count: int
    source: str = "condition_class6_points_only"

    def as_dict(self) -> dict[str, object]:
        return {
            "condition_id": self.condition_id,
            "protocol": self.protocol,
            "coordinates": [list(p) for p in self.coordinates],
            "building_point_count": self.building_point_count,
            "source": self.source,
        }


def _condition(condition_id: str) -> str:
    if condition_id not in CONDITIONS:
        raise ValueError(f"unknown condition_id: {condition_id}")
    return condition_id


def derive_roofprint(
    condition_id: str,
    points_xyz_class: Iterable[Sequence[float]],
    *,
    external_roofprint: object | None = None,
) -> DerivedRoofprint:
    """Derive a closed convex polygon from class-6 evidence only.

    Convex hull is intentionally the small, deterministic Gate-S0 interface
    proof.  It is not the final P2 adapter or a scientific-quality selection.
    """

    _condition(condition_id)
    if external_roofprint is not None:
        raise ValueError("external/reference roofprints are prohibited")
    array = np.asarray(list(points_xyz_class), dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 4:
        raise ValueError("points_xyz_class must have shape (N, 4)")
    building = array[array[:, 3] == 6, :2]
    if len(building) < 3:
        raise ValueError("at least three class-6 points are required")
    polygon = MultiPoint(building).convex_hull
    if not isinstance(polygon, Polygon) or polygon.area <= 0:
        raise ValueError("class-6 points do not form a polygon")
    coordinates = tuple((round(float(x), 6), round(float(y), 6)) for x, y in polygon.exterior.coords)
    return DerivedRoofprint(
        condition_id=condition_id,
        protocol="R_DERIVED_NON_GT_CONVEX_HULL_V1",
        coordinates=coordinates,
        building_point_count=int(len(building)),
    )


def make_roofer_request(
    condition_id: str,
    points_xyz_class: Iterable[Sequence[float]],
    gravity: Sequence[float],
    *,
    crs: str = "EPSG:25832",
    external_roofprint: object | None = None,
) -> dict[str, object]:
    roofprint = derive_roofprint(
        condition_id,
        points_xyz_class,
        external_roofprint=external_roofprint,
    )
    vector = np.asarray(gravity, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    if vector.shape != (3,) or not np.isfinite(norm) or norm <= 0:
        raise ValueError("gravity must be a finite non-zero 3-vector")
    vector = vector / norm
    return {
        "schema": "jointbuildgs.stage3_common_request.v1",
        "condition_id": condition_id,
        "crs": crs,
        "class_contract": {"ground": 2, "building": 6},
        "gravity": [round(float(v), 12) for v in vector],
        "roofprint": roofprint.as_dict(),
        "external_roofprint": None,
        "roofer_output_role": "Roofer-generated LoD2.2 semantic building model",
    }


def synthetic_smoke_payload() -> bytes:
    """Return deterministic CityJSONSeq bytes for interface-only smoke testing."""

    points = [
        (0.0, 0.0, 0.0, 2),
        (10.0, 0.0, 0.0, 2),
        (10.0, 8.0, 0.0, 2),
        (0.0, 8.0, 0.0, 2),
        (1.0, 1.0, 5.0, 6),
        (9.0, 1.0, 5.0, 6),
        (9.0, 7.0, 5.0, 6),
        (1.0, 7.0, 5.0, 6),
    ]
    requests = [make_roofer_request(condition, points, (0.01, -0.02, -0.99975)) for condition in CONDITIONS]
    header: Mapping[str, object] = {
        "type": "CityJSON",
        "version": "2.0",
        "transform": {"scale": [0.001, 0.001, 0.001], "translate": [0.0, 0.0, 0.0]},
        "metadata": {
            "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832",
            "jointbuildgsSmokeOnly": true_value(),
                "qualityComparison": False,
        },
        "CityObjects": {},
        "vertices": [],
    }
    lines = [json.dumps(header, sort_keys=True, separators=(",", ":"))]
    for request in requests:
        lines.append(
            json.dumps(
                {
                    "type": "CityJSONFeature",
                    "id": f"synthetic-{request['condition_id']}",
                    "CityObjects": {},
                    "vertices": [],
                    "jointbuildgsStage3Request": request,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def true_value() -> bool:
    """Named helper keeps the deterministic header visually explicit in tests."""

    return True
