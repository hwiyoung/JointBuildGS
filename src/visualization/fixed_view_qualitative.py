"""Deterministic, CPU-only qualitative views for sealed C1/C2 pilot artifacts.

This module is deliberately a renderer, not a scientific-computation pipeline.
It reads the already sealed R3 geometry and the already promoted R4 metrics.  It
does not call Roofer, reconstruct geometry, recompute metrics, or select cases
from outcomes.  Building bounding boxes are used only as post-hoc viewports.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


SCHEMA = "jointbuildgs.c1_c2_fixed_view_qualitative_manifest.v1"
SUPPLEMENT_STATUS = "POST_HOC_FIXED_RULE_VISUALIZATION_SUPPLEMENT"
METHODS = ("C1_L_upper", "C2_MVS")


@dataclass(frozen=True)
class BBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def center(self) -> tuple[float, float]:
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def padded(self, ratio: float, minimum_m: float) -> "BBox":
        pad = max(max(self.width, self.height) * ratio, minimum_m)
        return BBox(self.min_x - pad, self.min_y - pad, self.max_x + pad, self.max_y + pad)


@dataclass
class PointSet:
    xyz: np.ndarray
    classification: np.ndarray | None = None

    @classmethod
    def empty(cls) -> "PointSet":
        return cls(np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.uint8))


@dataclass
class Surface:
    xyz: np.ndarray
    semantic: str


@dataclass
class MethodGeometry:
    points: PointSet
    surfaces: list[Surface]
    roofprint_xy: list[np.ndarray]
    operation_unit_id: str | None
    component_id: str | None
    empty_reason: str | None = None


def _require_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} is not a regular file: {path}")
    return path


def _read_json(path: Path) -> Any:
    _require_regular_file(path, "JSON input")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _read_csv(path: Path) -> list[dict[str, str]]:
    _require_regular_file(path, "CSV input")
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    _require_regular_file(path, "JSONL input")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise RuntimeError(f"JSONL row is not an object: {path}:{line_number}")
                rows.append(value)
    return rows


def _parse_jsonl_bytes(data: bytes, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError(f"{label} row is not an object at line {line_number}")
            rows.append(value)
    return rows


def _safe_relative(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise RuntimeError(f"path must be relative and traversal-free: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / value).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise RuntimeError(f"path escaped declared root: {relative}")
    return resolved


def load_las_points(path: Path, data: bytes | None = None) -> PointSet:
    """Load exactly the stored XYZ and classification fields from a sealed LAS."""
    _require_regular_file(path, "sealed LAS")
    try:
        import laspy
    except ImportError as exc:  # pragma: no cover - dependency is in project image
        raise RuntimeError("laspy is required in the project Docker image") from exc
    las = laspy.read(io.BytesIO(data)) if data is not None else laspy.read(path)
    xyz = np.column_stack((np.asarray(las.x), np.asarray(las.y), np.asarray(las.z))).astype(np.float64)
    classification = np.asarray(las.classification).astype(np.uint8)
    return PointSet(xyz=xyz, classification=classification)


def _semantic_names(geometry: Mapping[str, Any]) -> list[str]:
    surfaces = geometry.get("semantics", {}).get("surfaces", [])
    return [str(value.get("type", "UnknownSurface")) for value in surfaces]


def _face_semantic(values: Any, indices: Sequence[int], names: Sequence[str]) -> str:
    current = values
    try:
        for index in indices:
            current = current[index]
        if isinstance(current, int) and 0 <= current < len(names):
            return names[current]
    except (IndexError, TypeError):
        pass
    return "UnknownSurface"


def _transformed_vertices(vertices: Sequence[Sequence[float]], transform: Mapping[str, Any] | None) -> np.ndarray:
    array = np.asarray(vertices, dtype=np.float64)
    if array.size == 0:
        return np.empty((0, 3), dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise RuntimeError("CityJSON vertices must be Nx3")
    if transform:
        scale = np.asarray(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
        translate = np.asarray(transform.get("translate", [0.0, 0.0, 0.0]), dtype=np.float64)
        array = array * scale + translate
    return array


def _geometry_surfaces(geometry: Mapping[str, Any], vertices: np.ndarray) -> list[Surface]:
    """Extract exterior rings while retaining CityJSON semantic labels."""
    kind = geometry.get("type")
    boundaries = geometry.get("boundaries", [])
    values = geometry.get("semantics", {}).get("values", [])
    names = _semantic_names(geometry)
    faces: list[tuple[Sequence[int], str]] = []
    if kind in {"Solid", "CompositeSolid"}:
        solids = [boundaries] if kind == "Solid" else boundaries
        solid_values = [values] if kind == "Solid" else values
        for solid_index, solid in enumerate(solids):
            for shell_index, shell in enumerate(solid):
                for face_index, face in enumerate(shell):
                    if face and face[0]:
                        semantic = _face_semantic(solid_values, (solid_index, shell_index, face_index), names)
                        faces.append((face[0], semantic))
    elif kind in {"MultiSurface", "CompositeSurface"}:
        for face_index, face in enumerate(boundaries):
            if face and face[0]:
                faces.append((face[0], _face_semantic(values, (face_index,), names)))
    surfaces: list[Surface] = []
    for ring, semantic in faces:
        indices = np.asarray(ring, dtype=np.int64)
        if len(indices) >= 3 and np.all((0 <= indices) & (indices < len(vertices))):
            surfaces.append(Surface(vertices[indices], semantic))
    return surfaces


def load_cityjsonseq(path: Path, data: bytes | None = None) -> list[Surface]:
    """Load CityJSONSeq, inheriting the header transform for feature records."""
    if data is None:
        rows = _read_jsonl(path)
    else:
        rows = []
        for line_number, line in enumerate(data.decode("utf-8").splitlines(), 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise RuntimeError(f"CityJSONSeq row is not an object: {path}:{line_number}")
                rows.append(value)
    inherited_transform: Mapping[str, Any] | None = None
    surfaces: list[Surface] = []
    for row in rows:
        if row.get("type") == "CityJSON":
            inherited_transform = row.get("transform")
        transform = row.get("transform", inherited_transform)
        vertices = _transformed_vertices(row.get("vertices", []), transform)
        for city_object in row.get("CityObjects", {}).values():
            for geometry in city_object.get("geometry", []):
                surfaces.extend(_geometry_surfaces(geometry, vertices))
    return surfaces


def load_roofprint(path: Path, raw: bytes | None = None) -> list[np.ndarray]:
    data = json.loads(raw) if raw is not None else _read_json(path)
    rings: list[np.ndarray] = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry", {})
        kind = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        polygons = [coordinates] if kind == "Polygon" else coordinates if kind == "MultiPolygon" else []
        for polygon in polygons:
            if polygon and polygon[0]:
                ring = np.asarray(polygon[0], dtype=np.float64)
                if ring.ndim == 2 and ring.shape[1] >= 2:
                    rings.append(ring[:, :2])
    return rings


def _find_city_output(output_dir: Path) -> Path:
    if not output_dir.is_dir():
        raise RuntimeError(f"sealed output directory is absent: {output_dir}")
    matches = sorted(path for path in output_dir.rglob("*.city.jsonl") if path.is_file() and not path.is_symlink())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one sealed CityJSONSeq under {output_dir}, found {len(matches)}")
    return matches[0]


def _verified_record_bytes(root: Path, record: Mapping[str, Any], expected_relative: str, label: str) -> tuple[bytes, dict[str, Any]]:
    """Read and digest an input once, bound to its sealed record and exact path."""
    record_path = str(record.get("path", "")).replace("\\", "/")
    expected = Path(expected_relative).as_posix()
    if record_path != expected:
        raise RuntimeError(f"{label} record path mismatch: expected {expected}, observed {record_path}")
    path = _safe_relative(root, expected)
    _require_regular_file(path, label)
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            chunks.append(block)
            total += len(block)
    observed_sha = digest.hexdigest()
    if total != int(record.get("bytes", -1)) or observed_sha != str(record.get("sha256", "")):
        raise RuntimeError(f"{label} sealed bytes/digest mismatch: {path}")
    return b"".join(chunks), {
        "path": expected,
        "bytes": total,
        "sha256": observed_sha,
        "full_read_and_digest_passes": 1,
    }


def _bbox_from_row(row: Mapping[str, str]) -> BBox:
    return BBox(*(float(row[key]) for key in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))


def _crop_xy(points: PointSet, bbox: BBox) -> PointSet:
    if not len(points.xyz):
        return PointSet.empty()
    xyz = points.xyz
    keep = (
        (xyz[:, 0] >= bbox.min_x)
        & (xyz[:, 0] <= bbox.max_x)
        & (xyz[:, 1] >= bbox.min_y)
        & (xyz[:, 1] <= bbox.max_y)
    )
    classification = points.classification[keep] if points.classification is not None else None
    return PointSet(xyz[keep], classification)


def _z_limits(point_sets: Iterable[PointSet], surfaces: Iterable[Surface], pad_ratio: float, minimum_pad_m: float) -> tuple[float, float]:
    parts = [value.xyz[:, 2] for value in point_sets if len(value.xyz)]
    parts.extend(surface.xyz[:, 2] for surface in surfaces if len(surface.xyz))
    if not parts:
        return (0.0, 1.0)
    all_z = np.concatenate(parts)
    low, high = float(np.min(all_z)), float(np.max(all_z))
    pad = max((high - low) * pad_ratio, minimum_pad_m)
    return (low - pad, high + pad)


def _metric_note(row: Mapping[str, str] | None) -> str:
    if row is None:
        return "R4 annotation: unavailable"
    g0 = row.get("G0_generated", "")
    rmsz = row.get("RMSZ_m", "")
    coverage = row.get("reference_vertical_coverage", "")
    if str(g0).lower() not in {"true", "1"}:
        reason = row.get("failure_reasons") or "G0 false"
        return f"R4 annotation: G0={g0}; {reason}"
    rmsz_text = f"{float(rmsz):.3f} m" if rmsz not in {"", None} else "null"
    coverage_text = f"{float(coverage):.3f}" if coverage not in {"", None} else "null"
    return f"R4 annotation: RMSZ={rmsz_text}; vertical coverage={coverage_text}"


def _surface_color(semantic: str) -> str:
    return {
        "RoofSurface": "#d1495b",
        "WallSurface": "#6c757d",
        "GroundSurface": "#5b8e7d",
    }.get(semantic, "#8d6a9f")


def _scatter_top(ax: Any, points: PointSet, z_norm: Any, point_size: float, cmap: str) -> None:
    if len(points.xyz):
        ax.scatter(points.xyz[:, 0], points.xyz[:, 1], c=points.xyz[:, 2], s=point_size, cmap=cmap, norm=z_norm, linewidths=0, rasterized=True)


def _scatter_3d(ax: Any, points: PointSet, z_norm: Any, point_size: float, cmap: str) -> None:
    if len(points.xyz):
        ax.scatter(points.xyz[:, 0], points.xyz[:, 1], points.xyz[:, 2], c=points.xyz[:, 2], s=point_size, cmap=cmap, norm=z_norm, linewidths=0, depthshade=False, rasterized=True)


def _overlay_top(ax: Any, geometry: MethodGeometry, linewidth: float) -> None:
    for surface in geometry.surfaces:
        closed = np.vstack((surface.xyz, surface.xyz[0]))
        ax.plot(closed[:, 0], closed[:, 1], color=_surface_color(surface.semantic), linewidth=linewidth)
    for ring in geometry.roofprint_xy:
        ax.plot(ring[:, 0], ring[:, 1], color="#111111", linewidth=linewidth, linestyle="--")


def _overlay_3d(ax: Any, geometry: MethodGeometry, linewidth: float) -> None:
    for surface in geometry.surfaces:
        closed = np.vstack((surface.xyz, surface.xyz[0]))
        ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color=_surface_color(surface.semantic), linewidth=linewidth)


def _section_coordinates(points: np.ndarray, bbox: BBox, half_band_m: float) -> tuple[np.ndarray, np.ndarray, str]:
    """Return deterministic CRS-axis section coordinates and axis label."""
    cx, cy = bbox.center
    if bbox.width >= bbox.height:
        keep = np.abs(points[:, 1] - cy) <= half_band_m
        return points[keep, 0], points[keep, 2], "Easting (m)"
    keep = np.abs(points[:, 0] - cx) <= half_band_m
    return points[keep, 1], points[keep, 2], "Northing (m)"


def _render_case(
    *,
    output_path: Path,
    case: Mapping[str, Any],
    bbox: BBox,
    reference: PointSet,
    methods: Mapping[str, MethodGeometry],
    metrics: Mapping[tuple[str, str], Mapping[str, str]],
    style: Mapping[str, Any],
) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    viewport = bbox.padded(float(style["viewport_margin_ratio"]), float(style["viewport_minimum_margin_m"]))
    displayed = {method: _crop_xy(value.points, viewport) for method, value in methods.items()}
    all_surfaces = [surface for value in methods.values() for surface in value.surfaces]
    z_limits = _z_limits([reference, *displayed.values()], all_surfaces, float(style["z_pad_ratio"]), float(style["z_minimum_pad_m"]))
    z_norm = Normalize(*z_limits)
    half_band = max(min(bbox.width, bbox.height) * float(style["section_band_ratio"]), float(style["section_minimum_half_band_m"]))
    fig = plt.figure(figsize=tuple(style["case_figure_inches"]), dpi=int(style["dpi"]), constrained_layout=True)
    columns = ("REFERENCE", *METHODS)
    selection_role = str(case["selection_role"])
    fig.suptitle(f"{case['building_id']} — {selection_role}\n{SUPPLEMENT_STATUS}", fontsize=11)
    for column_index, column in enumerate(columns):
        if column == "REFERENCE":
            points = reference
            geometry = MethodGeometry(reference, [], [], None, None)
            title = "Independent UAS reference"
            note = f"sealed score cells={len(reference.xyz)}"
        else:
            geometry = methods[column]
            points = displayed[column]
            self_reference = " — SELF_REFERENCE_UPPER_BASELINE" if column == "C1_L_upper" else ""
            title = f"{column} component viewport{self_reference}"
            note = geometry.empty_reason or _metric_note(metrics.get((str(case["building_id"]), column)))
        top_ax = fig.add_subplot(3, 3, 1 + column_index)
        _scatter_top(top_ax, points, z_norm, float(style["point_size"]), str(style["colormap"]))
        _overlay_top(top_ax, geometry, float(style["line_width"]))
        top_ax.set(xlim=(viewport.min_x, viewport.max_x), ylim=(viewport.min_y, viewport.max_y), aspect="equal", title=title, xlabel="Easting (m)", ylabel="Northing (m)")
        top_ax.text(0.01, 0.01, note, transform=top_ax.transAxes, fontsize=7, va="bottom", bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "none"})

        oblique_ax = fig.add_subplot(3, 3, 4 + column_index, projection="3d", proj_type="ortho")
        _scatter_3d(oblique_ax, points, z_norm, float(style["point_size"]), str(style["colormap"]))
        _overlay_3d(oblique_ax, geometry, float(style["line_width"]))
        oblique_ax.set(xlim=(viewport.min_x, viewport.max_x), ylim=(viewport.min_y, viewport.max_y), zlim=z_limits, xlabel="E", ylabel="N", zlabel="Z", title="Fixed oblique")
        oblique_ax.view_init(elev=float(style["oblique_elevation_deg"]), azim=float(style["oblique_azimuth_deg"]), roll=0)
        oblique_ax.set_box_aspect((viewport.width, viewport.height, max(z_limits[1] - z_limits[0], 1.0)))

        section_ax = fig.add_subplot(3, 3, 7 + column_index)
        section_count = 0
        if len(points.xyz):
            along, z, axis_label = _section_coordinates(points.xyz, bbox, half_band)
            section_count = len(along)
            if section_count:
                section_ax.scatter(along, z, c=z, s=float(style["point_size"]), cmap=str(style["colormap"]), norm=z_norm, linewidths=0, rasterized=True)
        else:
            axis_label = "Easting (m)" if bbox.width >= bbox.height else "Northing (m)"
        along_limits = (viewport.min_x, viewport.max_x) if bbox.width >= bbox.height else (viewport.min_y, viewport.max_y)
        section_ax.set(xlim=along_limits, ylim=z_limits, xlabel=axis_label, ylabel="Z (m)", title=f"Fixed principal CRS-axis section (±{half_band:.2f} m)")
        if not section_count:
            section_ax.text(0.5, 0.5, geometry.empty_reason or "NO_POINTS_IN_FIXED_SECTION_BAND", transform=section_ax.transAxes, ha="center", va="center")
    fig.savefig(output_path, metadata={"Software": "JointBuildGS fixed-view renderer"})
    plt.close(fig)
    return {
        "building_id": case["building_id"],
        "selection_role": selection_role,
        "file": output_path.name,
        "viewport": [viewport.min_x, viewport.min_y, viewport.max_x, viewport.max_y],
        "z_limits": list(z_limits),
        "oblique": {"elevation_deg": float(style["oblique_elevation_deg"]), "azimuth_deg": float(style["oblique_azimuth_deg"]), "projection": "orthographic"},
        "section": {"axis": "EASTING" if bbox.width >= bbox.height else "NORTHING", "half_band_m": half_band},
        "reference_cells": int(len(reference.xyz)),
        "methods": {
            method: {
                "operation_unit_id": methods[method].operation_unit_id,
                "component_id": methods[method].component_id,
                "displayed_points": int(len(displayed[method].xyz)),
                "empty_reason": methods[method].empty_reason,
            }
            for method in METHODS
        },
    }


def stream_eligibility_cells(
    path: Path,
    specs: Mapping[str, tuple[BBox, set[str]]],
    *,
    expected_bytes: int,
    expected_sha256: str,
    expected_rows: int,
) -> tuple[dict[str, PointSet], dict[str, Any]]:
    """One process-and-digest stream of the already-bound compact R1 CSV."""
    _require_regular_file(path, "bound compact reference cells")
    selected: dict[str, list[tuple[float, float, float]]] = {key: [] for key in specs}
    digest = hashlib.sha256()
    total_bytes = 0
    total_rows = 0
    header: list[str] | None = None
    with path.open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            total_bytes += len(raw)
            parsed = next(csv.reader([raw.decode("utf-8")]))
            if header is None:
                header = parsed
                required = {"patch_id", "cell_x", "cell_y", "top_z"}
                if not required.issubset(header):
                    raise RuntimeError("bound compact reference-cell schema mismatch")
                continue
            if len(parsed) != len(header):
                raise RuntimeError("bound compact reference-cell row width mismatch")
            total_rows += 1
            row = dict(zip(header, parsed))
            x, y, z = float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])
            for stable_id, (bbox, patches) in specs.items():
                if row["patch_id"] in patches and bbox.min_x <= x <= bbox.max_x and bbox.min_y <= y <= bbox.max_y:
                    selected[stable_id].append((x, y, z))
    observed_sha = digest.hexdigest()
    if (total_bytes, observed_sha, total_rows) != (expected_bytes, expected_sha256, expected_rows):
        raise RuntimeError(
            "bound compact reference-cell identity mismatch: "
            f"observed bytes/sha/rows={total_bytes}/{observed_sha}/{total_rows}"
        )
    point_sets = {
        key: PointSet(np.asarray(values, dtype=np.float64).reshape((-1, 3)), None) if values else PointSet.empty()
        for key, values in selected.items()
    }
    return point_sets, {"bytes": total_bytes, "sha256": observed_sha, "rows": total_rows, "full_read_and_digest_passes": 1}


def _render_eligibility(
    *,
    output_path: Path,
    examples: Sequence[Mapping[str, str]],
    ledgers: Mapping[str, Mapping[str, str]],
    cells: Mapping[str, PointSet],
    style: Mapping[str, Any],
) -> list[dict[str, Any]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for example in examples:
        observed = len(cells[example["stable_id"]].xyz)
        expected = int(example["reference_cells"])
        if observed != expected:
            raise RuntimeError(
                f"eligibility compact-cell count mismatch for {example['label']}/{example['stable_id']}: "
                f"expected {expected}, observed {observed}"
            )
    fig, axes = plt.subplots(2, 4, figsize=tuple(style["eligibility_figure_inches"]), dpi=int(style["dpi"]), constrained_layout=True)
    axes_flat = list(axes.ravel())
    records: list[dict[str, Any]] = []
    for index, example in enumerate(examples):
        ax = axes_flat[index]
        stable_id = example["stable_id"]
        ledger = ledgers[stable_id]
        bbox = _bbox_from_row(ledger)
        viewport = bbox.padded(float(style["viewport_margin_ratio"]), float(style["viewport_minimum_margin_m"]))
        point_set = cells[stable_id]
        if len(point_set.xyz):
            ax.scatter(point_set.xyz[:, 0], point_set.xyz[:, 1], c=point_set.xyz[:, 2], s=float(style["eligibility_point_size"]), cmap=str(style["colormap"]), linewidths=0, rasterized=True)
        rectangle_x = [bbox.min_x, bbox.max_x, bbox.max_x, bbox.min_x, bbox.min_x]
        rectangle_y = [bbox.min_y, bbox.min_y, bbox.max_y, bbox.max_y, bbox.min_y]
        ax.plot(rectangle_x, rectangle_y, color="#111111", linewidth=float(style["line_width"]))
        candidate = str(example["candidate"]).lower() == "true"
        recorded = int(example["reference_cells"])
        ax.set(xlim=(viewport.min_x, viewport.max_x), ylim=(viewport.min_y, viewport.max_y), aspect="equal", title=f"{example['label']} — {stable_id}\n{'ELIGIBLE' if candidate else 'EXCLUDED'}", xlabel="Easting (m)", ylabel="Northing (m)")
        ax.text(
            0.01,
            0.01,
            f"actual compact rows={len(point_set.xyz)}; recorded reference cells={recorded}\n"
            f"views/MVS/C4={example['image_views']}/{example['mvs_cells']}/{example['c4_cells']}\n"
            f"reason={example['exclusion_reason']}",
            transform=ax.transAxes,
            fontsize=7,
            va="bottom",
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
        )
        records.append({
            "label": example["label"],
            "stable_id": stable_id,
            "candidate": candidate,
            "actual_compact_rows": int(len(point_set.xyz)),
            "recorded_reference_cells": recorded,
            "current_image_views": int(example["image_views"]),
            "mvs_support_cells": int(example["mvs_cells"]),
            "c4_support_cells": int(example["c4_cells"]),
            "bbox": [bbox.min_x, bbox.min_y, bbox.max_x, bbox.max_y],
            "reason": example["exclusion_reason"],
        })
    for ax in axes_flat[len(examples):]:
        ax.axis("off")
    fig.suptitle("199→72 eligibility — bounded descriptive supplement (no eligibility derivation)", fontsize=12)
    fig.savefig(output_path, metadata={"Software": "JointBuildGS fixed-view renderer"})
    plt.close(fig)
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_output_cap(output_dir: Path, cap_bytes: int) -> None:
    observed = sum(path.stat().st_size for path in output_dir.iterdir() if path.is_file() and not path.is_symlink())
    if observed > cap_bytes:
        raise RuntimeError(f"new-output storage cap exceeded: observed {observed}, cap {cap_bytes}")


def _truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1"}


def _write_stage_and_correction_funnel(
    path: Path,
    metric_rows: Sequence[Mapping[str, str]],
    correction: Mapping[str, Any],
) -> dict[str, Any]:
    """Write exact R4 stage counts plus the declared 46/4/1 coverage correction."""
    by_method = {method: [row for row in metric_rows if row.get("method_id") == method] for method in METHODS}
    all_ids = {row["building_id"] for row in by_method["C1_L_upper"]}
    if len(by_method["C1_L_upper"]) != 51 or len(by_method["C2_MVS"]) != 51 or len(all_ids) != 51:
        raise RuntimeError("R4 stage funnel requires exact 51x2 building-method rows")
    if {row["building_id"] for row in by_method["C2_MVS"]} != all_ids:
        raise RuntimeError("R4 C1/C2 building identities disagree")
    absent_id = str(correction["absent_building_id"])
    partial_ids = [str(value) for value in correction["partial_building_ids"]]
    if len(partial_ids) != 4 or len(set(partial_ids)) != 4 or absent_id in partial_ids:
        raise RuntimeError("coverage correction requires four unique partial IDs and one distinct absent ID")
    if set(partial_ids) | {absent_id} > all_ids:
        raise RuntimeError("coverage correction names a building outside the exact R4 roster")
    full_ids = sorted(all_ids - set(partial_ids) - {absent_id})
    if len(full_ids) != 46:
        raise RuntimeError("coverage correction must resolve to exact 46 full / 4 partial / 1 absent")
    c1_generated = [row for row in by_method["C1_L_upper"] if _truth(row.get("G0_generated"))]
    c2_generated = [row for row in by_method["C2_MVS"] if _truth(row.get("G0_generated"))]
    c1_g1 = [row for row in by_method["C1_L_upper"] if _truth(row.get("G1_schema_semantic"))]
    c2_g1 = [row for row in by_method["C2_MVS"] if _truth(row.get("G1_schema_semantic"))]
    c2_absent = [row["building_id"] for row in by_method["C2_MVS"] if not _truth(row.get("G0_generated"))]
    if len(c1_generated) != 51 or len(c2_generated) != 50 or len(c1_g1) != 51 or len(c2_g1) != 50 or c2_absent != [absent_id]:
        raise RuntimeError("R4 G0/G1 funnel does not match exact C1 51/51 and C2 50/51 plus declared absent ID")
    c2_by_id = {row["building_id"]: row for row in by_method["C2_MVS"]}
    for stable_id in full_ids:
        if float(c2_by_id[stable_id].get("reference_vertical_coverage") or "nan") != 1.0:
            raise RuntimeError(f"declared full-coverage C2 building is not exactly 1.0: {stable_id}")
    for stable_id in partial_ids:
        coverage = float(c2_by_id[stable_id].get("reference_vertical_coverage") or "nan")
        if not 0.0 < coverage < 1.0:
            raise RuntimeError(f"declared partial-coverage C2 building is not strictly between 0 and 1: {stable_id}")
    absent_row = c2_by_id[absent_id]
    if (absent_row.get("reference_vertical_coverage") or "").strip() or int(absent_row.get("vertically_scored_cell_count") or 0) != 0:
        raise RuntimeError("declared absent C2 building unexpectedly has a scored coverage value")

    rows: list[dict[str, Any]] = [
        {"section": "STAGE", "method_id": "C1_L_upper", "stage": "G0_GENERATED", "status": "COMPLETE", "numerator": 51, "denominator": 51, "reason": "EXACT_R4_METRIC_ROWS", "building_ids": ""},
        {"section": "STAGE", "method_id": "C1_L_upper", "stage": "G1_SCHEMA_SEMANTIC", "status": "COMPLETE", "numerator": 51, "denominator": 51, "reason": "EXACT_R4_METRIC_ROWS", "building_ids": ""},
        {"section": "STAGE", "method_id": "C2_MVS", "stage": "G0_GENERATED", "status": "COMPLETE", "numerator": 50, "denominator": 51, "reason": f"ONE_UNASSOCIATED_{absent_id}", "building_ids": absent_id},
        {"section": "STAGE", "method_id": "C2_MVS", "stage": "G1_SCHEMA_SEMANTIC", "status": "COMPLETE", "numerator": 50, "denominator": 51, "reason": f"ONE_UNASSOCIATED_{absent_id}", "building_ids": absent_id},
    ]
    pending_reasons = {
        "G2_GEOMETRY_TOPOLOGY_VALID": "CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE",
        "G3_ROOF_STRUCTURE_ACCEPTABLE": "CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE",
        "G4_GEOMETRIC_ACCURACY_ACCEPTABLE": "CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE",
        "PASS_USABLE": "CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE",
    }
    for method in METHODS:
        for stage, reason in pending_reasons.items():
            rows.append({"section": "STAGE", "method_id": method, "stage": stage, "status": "PENDING", "numerator": "", "denominator": 51, "reason": reason, "building_ids": ""})
    rows.extend(
        [
            {"section": "COVERAGE_CORRECTION", "method_id": "C2_MVS", "stage": "FULL", "status": "DESCRIPTIVE", "numerator": 46, "denominator": 50, "reason": "R4_VALUE_ASSERTED_ADDITIVE_CORRECTION_OF_RETURN_47_OF_50", "building_ids": ";".join(full_ids)},
            {"section": "COVERAGE_CORRECTION", "method_id": "C2_MVS", "stage": "PARTIAL", "status": "DESCRIPTIVE", "numerator": 4, "denominator": 50, "reason": "R4_VALUE_ASSERTED_ADDITIVE_CORRECTION_OF_RETURN_47_OF_50", "building_ids": ";".join(partial_ids)},
            {"section": "COVERAGE_CORRECTION", "method_id": "C2_MVS", "stage": "ABSENT", "status": "DESCRIPTIVE", "numerator": 1, "denominator": 51, "reason": "UNASSOCIATED_CONDITION_COMPONENT", "building_ids": absent_id},
        ]
    )
    fields = ["section", "method_id", "stage", "status", "numerator", "denominator", "reason", "building_ids"]
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return {
        "file": path.name,
        "r4_rows_consumed": len(metric_rows),
        "g0": {"C1_L_upper": {"numerator": 51, "denominator": 51}, "C2_MVS": {"numerator": 50, "denominator": 51}},
        "g1": {"C1_L_upper": {"numerator": 51, "denominator": 51}, "C2_MVS": {"numerator": 50, "denominator": 51}},
        "pending": {
            stage: {
                method: {"status": "PENDING", "value": None, "denominator": 51, "reason": reason}
                for method in METHODS
            }
            for stage, reason in pending_reasons.items()
        },
        "coverage_correction": {
            "full": {"numerator": 46, "denominator": 50},
            "partial": {"numerator": 4, "denominator": 50},
            "absent": {"numerator": 1, "denominator": 51},
            "partial_building_ids": partial_ids,
            "absent_building_id": absent_id,
            "supersedes_return_arithmetic": "47/50",
        },
    }


def render_from_config(
    *,
    config_path: Path,
    repository_root: Path,
    artifact_root: Path,
    r3_root: Path,
    output_dir: Path,
    compact_reference_cells_path: Path | None = None,
) -> dict[str, Any]:
    """Render all configured case sheets and the bounded eligibility explainer."""
    config = _read_json(config_path)
    if config.get("schema") != "jointbuildgs.c1_c2_qualitative_evaluator_backfill_config.v1":
        raise RuntimeError("render config schema mismatch")
    if output_dir.is_symlink():
        raise RuntimeError(f"output directory must not be a symlink: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be absent or empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_cap_bytes = int(config.get("execution", {}).get("new_output_bytes_hard", 2_000_000_000))

    inputs = config["inputs"]
    configured_execution_units = int(config.get("expected_execution_units", 7))
    configured_allowlist_records = 3 + 3 * configured_execution_units + 1
    allowlist = _read_json(_safe_relative(repository_root, inputs["artifact_allowlist_git_path"]))
    if (
        allowlist.get("schema") != "jointbuildgs.c1_c2_qualitative_evaluator_backfill_artifact_allowlist.v1"
        or allowlist.get("task_id") != config["task_id"] or allowlist.get("record_count") != configured_allowlist_records
        or len(allowlist.get("records", [])) != configured_allowlist_records or allowlist.get("scientific_verdict") is not None
    ):
        raise RuntimeError("exact 25-record artifact allowlist contract mismatch")
    allow_records = {(str(row["source"]), str(row["path"]).replace("\\", "/")): row for row in allowlist["records"]}
    canonical_allow_records = json.dumps(allowlist["records"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    if (
        int(allowlist.get("total_bytes", -1)) != sum(int(row["bytes"]) for row in allowlist["records"])
        or str(allowlist.get("record_identity_sha256", "")) != hashlib.sha256(canonical_allow_records).hexdigest()
    ):
        raise RuntimeError("artifact allowlist total/record identity mismatch")
    if len(allow_records) != configured_allowlist_records or Counter(row["role"] for row in allowlist["records"]) != Counter({
        "SEALED_ASSOCIATION_CONTROL": 1, "SEALED_DEVELOPMENT_REFERENCE_CONTROL": 1,
        "SEALED_EXECUTION_UNIT_CONTROL": 1, "DERIVED_OPERATION_LAS": configured_execution_units,
        "DERIVED_R_DERIVED": configured_execution_units, "DERIVED_CITYJSONSEQ": configured_execution_units, "BOUND_COMPACT_REFERENCE_CELLS": 1,
    }):
        raise RuntimeError("artifact allowlist role/identity count mismatch")

    control_specs = (
        ("r3_associations_path", "SEALED_ASSOCIATION_CONTROL"),
        ("r3_execution_units_path", "SEALED_EXECUTION_UNIT_CONTROL"),
        ("r3_score_cells_path", "SEALED_DEVELOPMENT_REFERENCE_CONTROL"),
    )
    control_rows: dict[str, list[dict[str, Any]]] = {}
    control_reads: dict[str, dict[str, Any]] = {}
    for config_key, role in control_specs:
        relative = str(inputs[config_key])
        record = allow_records.get(("R3", relative))
        if record is None or record.get("role") != role:
            raise RuntimeError(f"exact allowlist control record is absent: {relative}")
        data, read = _verified_record_bytes(r3_root, record, relative, role)
        control_rows[config_key] = _parse_jsonl_bytes(data, role)
        control_reads[config_key] = read
    associations = control_rows["r3_associations_path"]
    execution_units = control_rows["r3_execution_units_path"]
    score_rows = control_rows["r3_score_cells_path"]
    bboxes = {row["stable_id"]: row for row in _read_csv(_safe_relative(repository_root, inputs["development_bboxes_git_path"]))}
    metric_rows = _read_csv(_safe_relative(repository_root, inputs["r4_metrics_git_path"]))
    metrics = {(row["building_id"], row["method_id"]): row for row in metric_rows}
    accepted_source_manifest = _read_json(_safe_relative(repository_root, inputs["r4_accepted_r3_source_manifest_git_path"]))
    if accepted_source_manifest.get("schema") != "jointbuildgs.p2_c1_c2_r3_finalize_source_manifest.v1":
        raise RuntimeError("accepted R4 source-manifest schema mismatch")
    accepted_city_records = {
        str(row["path"]).replace("\\", "/"): row
        for row in accepted_source_manifest.get("records", [])
        if str(row.get("path", "")).endswith(".city.jsonl")
    }
    allow_city_records = {path: row for (source, path), row in allow_records.items() if source == "R3" and row["role"] == "DERIVED_CITYJSONSEQ"}
    accepted_city_identities = {path: (int(row["bytes"]), str(row["sha256"])) for path, row in accepted_city_records.items()}
    allow_city_identities = {path: (int(row["bytes"]), str(row["sha256"])) for path, row in allow_city_records.items()}
    if accepted_city_identities != allow_city_identities:
        raise RuntimeError("allowlisted CityJSONSeq records do not exactly match accepted R4 source manifest")
    association_map = {(row["building_id"], row["method_id"]): row for row in associations}
    unit_map = {row["operation_unit_id"]: row for row in execution_units}
    expected_association_rows = int(config.get("expected_association_rows", len(associations)))
    expected_execution_units = int(config.get("expected_execution_units", len(execution_units)))
    if len(associations) != expected_association_rows or len(association_map) != expected_association_rows:
        raise RuntimeError(f"sealed association contract mismatch: expected {expected_association_rows} unique rows")
    if len(execution_units) != expected_execution_units or len(unit_map) != expected_execution_units:
        raise RuntimeError(f"sealed execution-unit contract mismatch: expected {expected_execution_units} unique rows")
    if len(accepted_city_records) != expected_execution_units:
        raise RuntimeError(f"accepted CityJSONSeq source-record contract mismatch: expected {expected_execution_units} unique rows")
    score_map: dict[str, list[tuple[float, float, float]]] = {}
    for row in score_rows:
        score_map.setdefault(row["stable_id"], []).append((float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])))

    configured_roles = {str(row["building_id"]): str(row["selection_role"]) for row in config["cases"]}
    if len(configured_roles) != len(config["cases"]):
        raise RuntimeError("render config has duplicate case IDs")
    if config.get("render_all_development_cases"):
        cases = [
            {"building_id": stable_id, "selection_role": configured_roles.get(stable_id, "FULL_DEVELOPMENT_ROSTER_DESCRIPTIVE")}
            for stable_id in sorted(bboxes)
        ]
    else:
        cases = list(config["cases"])
    expected_sheets = int(config.get("expected_case_sheets", len(cases)))
    if len(cases) != expected_sheets:
        raise RuntimeError(f"case-sheet roster count mismatch: observed {len(cases)}, expected {expected_sheets}")
    if "expected_selection_role_counts" in config:
        observed_roles = Counter(str(row["selection_role"]) for row in cases)
        expected_roles = Counter({str(key): int(value) for key, value in config["expected_selection_role_counts"].items()})
        if observed_roles != expected_roles:
            raise RuntimeError(f"case selection-role count mismatch: observed {dict(observed_roles)}, expected {dict(expected_roles)}")

    # Validate the exact 51/50 stage and 46/4/1 coverage contract before the
    # comparatively expensive 51-sheet rendering loop.
    funnel = _write_stage_and_correction_funnel(output_dir / "stage_and_coverage_correction_v1.csv", metric_rows, config["coverage_correction"])
    _assert_output_cap(output_dir, output_cap_bytes)

    # Stream and validate the already-bound compact eligibility evidence before
    # rendering any case sheets, so a lineage/count mismatch fails cheaply.
    eligibility = config["eligibility"]
    examples = _read_csv(_safe_relative(repository_root, eligibility["examples_git_path"]))
    wanted_labels = list(eligibility["example_labels"])
    example_map = {row["label"]: row for row in examples}
    if set(wanted_labels) - set(example_map):
        raise RuntimeError("configured eligibility example label is absent")
    selected_examples = [example_map[label] for label in wanted_labels]
    ledger_rows = _read_csv(_safe_relative(repository_root, eligibility["bbox_ledger_git_path"]))
    ledger_map = {row["stable_id"]: row for row in ledger_rows}
    specs: dict[str, tuple[BBox, set[str]]] = {}
    for example in selected_examples:
        stable_id = example["stable_id"]
        ledger = ledger_map.get(stable_id)
        if ledger is None:
            raise RuntimeError(f"eligibility bbox ledger row is absent: {stable_id}")
        patches = {value for value in ledger["reference_candidate_patch_ids"].split(";") if value}
        specs[stable_id] = (_bbox_from_row(ledger), patches)
    compact_spec = eligibility["compact_reference_cells"]
    compact_allow = allow_records.get(("COMPACT_REFERENCE", str(compact_spec["artifact_relative_path"])))
    if compact_allow is None or compact_allow.get("role") != "BOUND_COMPACT_REFERENCE_CELLS" or (
        int(compact_allow["bytes"]), str(compact_allow["sha256"])
    ) != (int(compact_spec["bytes"]), str(compact_spec["sha256"])):
        raise RuntimeError("compact reference-cell config differs from exact allowlist")
    compact_path = compact_reference_cells_path or _safe_relative(artifact_root, compact_spec["artifact_relative_path"])
    eligibility_cells, compact_read = stream_eligibility_cells(
        compact_path,
        specs,
        expected_bytes=int(compact_spec["bytes"]),
        expected_sha256=str(compact_spec["sha256"]),
        expected_rows=int(compact_spec["expected_rows"]),
    )
    for example in selected_examples:
        actual = len(eligibility_cells[example["stable_id"]].xyz)
        recorded = int(example["reference_cells"])
        if actual != recorded:
            raise RuntimeError(f"eligibility compact-cell count mismatch for {example['label']}: expected {recorded}, observed {actual}")

    las_cache: dict[str, PointSet] = {}
    surface_cache: dict[str, list[Surface]] = {}
    roofprint_cache: dict[str, list[np.ndarray]] = {}
    unit_read_records: dict[str, dict[str, Any]] = {}
    for unit_id in sorted(unit_map):
        unit = unit_map[unit_id]
        work_dir = _safe_relative(r3_root, str(unit["work_directory"]))
        input_relative = f"{str(unit['work_directory']).rstrip('/')}/input.las"
        roofprint_relative = f"{str(unit['work_directory']).rstrip('/')}/r_derived.geojson"
        input_allow = allow_records.get(("R3", input_relative))
        roofprint_allow = allow_records.get(("R3", roofprint_relative))
        if input_allow is None or input_allow.get("role") != "DERIVED_OPERATION_LAS" or roofprint_allow is None or roofprint_allow.get("role") != "DERIVED_R_DERIVED":
            raise RuntimeError(f"operation unit is outside the exact allowlist: {unit_id}")
        for observed, allowed, label in ((unit["input"], input_allow, "input LAS"), (unit["r_derived"], roofprint_allow, "R_derived")):
            if (str(observed.get("path")), int(observed.get("bytes", -1)), str(observed.get("sha256", ""))) != (str(allowed["path"]), int(allowed["bytes"]), str(allowed["sha256"])):
                raise RuntimeError(f"runtime execution-unit {label} record differs from exact allowlist: {unit_id}")
        las_bytes, las_read = _verified_record_bytes(r3_root, input_allow, input_relative, "sealed operation LAS")
        roofprint_bytes, roofprint_read = _verified_record_bytes(r3_root, roofprint_allow, roofprint_relative, "sealed R_derived")
        city_path = _find_city_output(work_dir / "out")
        city_relative = city_path.resolve().relative_to(r3_root.resolve()).as_posix()
        city_record = accepted_city_records.get(city_relative)
        city_allow = allow_records.get(("R3", city_relative))
        if city_record is None or city_allow is None:
            raise RuntimeError(f"exact CityJSONSeq output lacks accepted R4 source attestation: {city_relative}")
        city_bytes, city_read = _verified_record_bytes(r3_root, city_allow, city_relative, "accepted sealed CityJSONSeq")
        las_cache[unit_id] = load_las_points(work_dir / "input.las", las_bytes)
        roofprint_cache[unit_id] = load_roofprint(work_dir / "r_derived.geojson", roofprint_bytes)
        surface_cache[unit_id] = load_cityjsonseq(city_path, city_bytes)
        unit_read_records[unit_id] = {"input_las": las_read, "r_derived": roofprint_read, "cityjsonseq": city_read}
    expected_unique = int(config["expected_unique_execution_units"])
    if len(unit_read_records) != expected_unique:
        raise RuntimeError(f"render preflight verified {len(unit_read_records)} unique execution units, expected {expected_unique}")

    sheets: list[dict[str, Any]] = []
    associated_render_uses = 0
    for case in cases:
        stable_id = str(case["building_id"])
        if stable_id not in bboxes:
            raise RuntimeError(f"case bbox is absent: {stable_id}")
        bbox = _bbox_from_row(bboxes[stable_id])
        reference_values = score_map.get(stable_id, [])
        reference = PointSet(np.asarray(reference_values, dtype=np.float64).reshape((-1, 3)), None) if reference_values else PointSet.empty()
        methods: dict[str, MethodGeometry] = {}
        for method in METHODS:
            association = association_map.get((stable_id, method))
            if association is None:
                raise RuntimeError(f"sealed association row is absent: {stable_id}/{method}")
            unit_id = association.get("operation_unit_id")
            if not unit_id:
                reason = association.get("pre_roofer_failure") or "UNASSOCIATED_CONDITION_COMPONENT"
                methods[method] = MethodGeometry(PointSet.empty(), [], [], None, association.get("component_id"), reason)
                continue
            associated_render_uses += 1
            if unit_id not in unit_map:
                raise RuntimeError(f"associated sealed execution unit is absent: {stable_id}/{method}/{unit_id}")
            methods[method] = MethodGeometry(las_cache[unit_id], surface_cache[unit_id], roofprint_cache[unit_id], unit_id, association.get("component_id"))
        filename = f"{stable_id}_fixed_views_v1.png"
        sheets.append(_render_case(output_path=output_dir / filename, case=case, bbox=bbox, reference=reference, methods=methods, metrics=metrics, style=config["style"]))
        _assert_output_cap(output_dir, output_cap_bytes)

    duplicate_renders_prevented = associated_render_uses - len(unit_read_records)
    if duplicate_renders_prevented < 0:
        raise RuntimeError("duplicate-render accounting underflow")
    expected_associated_uses = int(config.get("expected_associated_render_uses", associated_render_uses))
    if associated_render_uses != expected_associated_uses:
        raise RuntimeError(f"associated render-use count mismatch: observed {associated_render_uses}, expected {expected_associated_uses}")
    expected_duplicates = int(config.get("expected_duplicate_payload_reads_prevented", duplicate_renders_prevented))
    if duplicate_renders_prevented != expected_duplicates:
        raise RuntimeError(f"duplicate payload-read prevention mismatch: observed {duplicate_renders_prevented}, expected {expected_duplicates}")

    eligibility_file = output_dir / "eligibility_199_to_72_fixed_cells_v1.png"
    eligibility_records = _render_eligibility(output_path=eligibility_file, examples=selected_examples, ledgers=ledger_map, cells=eligibility_cells, style=config["style"])
    _assert_output_cap(output_dir, output_cap_bytes)

    output_files = sorted(path for path in output_dir.iterdir() if path.is_file())
    file_records = [{"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)} for path in output_files]
    manifest = {
        "schema": SCHEMA,
        "task_id": config["task_id"],
        "status": SUPPLEMENT_STATUS,
        "scientific_verdict": None,
        "scope": {
            "sealed_r3_geometry_only": True,
            "r4_metrics_annotation_only": True,
            "metric_recomputation_count": 0,
            "roofer_invocation_count": 0,
            "reconstruction_invocation_count": 0,
            "building_bbox_role": "POST_HOC_VIEWPORT_ONLY_NO_GEOMETRY_MODIFICATION",
            "c1_reference_label": "SELF_REFERENCE_UPPER_BASELINE",
            "sealed_input_hash_policy": "ONE_NATURAL_READ_AND_DIGEST_PER_UNIQUE_OPERATION_PAYLOAD",
            "new_output_hash_policy": "ONE_POST_WRITE_OUTPUT_DIGEST_PASS",
            "original_scientific_source_reads_or_hashes": 0,
            "validation_payload_accesses": 0,
            "held_out_payload_accesses": 0,
        },
        "style": config["style"],
        "case_sheets": sheets,
        "eligibility": {
            "role": "BOUNDED_DESCRIPTIVE_SUPPLEMENT_NO_ELIGIBILITY_DERIVATION",
            "compact_source_read": compact_read,
            "examples": eligibility_records,
            "file": eligibility_file.name,
        },
        "stage_and_coverage_correction": funnel,
        "input_reads": {
            "artifact_allowlist_record_count": len(allowlist["records"]),
            "artifact_allowlist_records": allowlist["records"],
            "sealed_control_reads": control_reads,
            "sealed_association_rows": len(associations),
            "sealed_execution_unit_rows": len(execution_units),
            "unique_execution_units": len(unit_read_records),
            "expected_unique_execution_units": expected_unique,
            "associated_render_uses": associated_render_uses,
            "duplicate_payload_reads_prevented": duplicate_renders_prevented,
            "units": unit_read_records,
        },
        "output_digest_passes": {"policy": "POST_WRITE_NEW_OUTPUT_ONLY", "passes_per_file": 1},
        "outputs": file_records,
    }
    manifest_path = output_dir / "fixed_view_manifest_v1.json"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return manifest
