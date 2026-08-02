"""Read-only C1/C2 development gate-closure candidate evaluator."""

from .evaluator import (
    RoofSurface,
    evaluate_g3,
    evaluate_g4,
    evaluate_row,
    load_config,
    parse_cityjsonseq_roof_surfaces,
)

__all__ = [
    "RoofSurface",
    "evaluate_g3",
    "evaluate_g4",
    "evaluate_row",
    "load_config",
    "parse_cityjsonseq_roof_surfaces",
]
