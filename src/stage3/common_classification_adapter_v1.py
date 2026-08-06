"""Frozen C2/C3 scene-classification adapter for the direct comparison.

Only the source reader differs by condition.  The crop, SMRF, shared-footprint
overlay, class values, CRS, and LAS writer are emitted from one parameter block.
Semantic dimensions carried by a C3 source are forwarded as audit attributes;
they never participate in the class-2/class-6 decision.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence


def context_bounds(scene: Mapping[str, Any]) -> str:
    x0, y0, x1, y1 = map(float, scene["roofer_aoi_bbox"])
    buffer_m = float(scene["classification_context_buffer_m"])
    return f"([{x0-buffer_m:.3f},{x1+buffer_m:.3f}],[{y0-buffer_m:.3f},{y1+buffer_m:.3f}])"


def common_stages(
    *,
    scene: Mapping[str, Any],
    classification: Mapping[str, Any],
    footprint_path: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    """Return the byte-stable scientific classification stage sequence."""
    return [
        {"type": "filters.crop", "bounds": context_bounds(scene)},
        {
            "type": "filters.smrf",
            **classification["smrf"],
            "ground_class": int(classification["ground_class"]),
            "other_class": int(classification["unclassified_class"]),
        },
        {
            "type": "filters.overlay",
            "dimension": "Classification",
            "datasource": footprint_path.as_posix(),
            "column": "class",
            "where": f"Classification != {int(classification['ground_class'])}",
            "threads": 1,
        },
        {
            "type": "writers.las",
            "filename": output_path.as_posix(),
            "a_srs": scene["crs"],
            "minor_version": 4,
            "dataformat_id": 3,
            "compression": "lazperf",
            "extra_dims": "all",
            "forward": "all",
        },
    ]


def pipeline(
    *,
    source_stages: Sequence[Mapping[str, Any]],
    scene: Mapping[str, Any],
    classification: Mapping[str, Any],
    footprint_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    return {
        "pipeline": [
            *[dict(stage) for stage in source_stages],
            *common_stages(
                scene=scene,
                classification=classification,
                footprint_path=footprint_path,
                output_path=output_path,
            ),
        ]
    }
