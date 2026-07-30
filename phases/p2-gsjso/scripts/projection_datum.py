#!/usr/bin/env python3
"""Shared vertical-datum handling for image projection.

COLMAP/OPF camera poses live in the ellipsoidal local frame:
    canonical_z = h_ellipsoidal - 604

GML, ALS and footprint-derived points are orthometric in EPSG:25832. Before
projecting them into camera space, add the configured geoid undulation:
    h_ellipsoidal = H_orthometric + zeta

Callers can pass input_datum="ellipsoidal" to keep the historical -604 path.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np


def _repo_root() -> Path:
    env = os.environ.get("JOINTBUILDGS_REPO")
    if env:
        return Path(env)
    workspace = Path("/workspace/JointBuildGS")
    if workspace.exists():
        return workspace
    return Path(__file__).resolve().parents[3]


REPO = _repo_root()
DEFAULT_CONFIG = REPO / "configs/input_and_alignment/projection_datum.json"
CONFIG_ENV = "JOINTBUILDGS_PROJECTION_CONFIG"
ORTHOMETRIC = "orthometric"
ELLIPSOIDAL = "ellipsoidal"


def _config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        return Path(config_path)
    return Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))


@lru_cache(maxsize=8)
def _load_config_cached(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    with open(path) as f:
        return json.load(f)


def load_projection_config(config_path: str | Path | None = None) -> dict[str, Any]:
    return dict(_load_config_cached(str(_config_path(config_path))))


def projection_geoid_m(geoid_m: float | None = None, config_path: str | Path | None = None) -> float:
    if geoid_m is not None:
        return float(geoid_m)
    cfg = load_projection_config(config_path)
    return float(cfg["orthometric_geoid_m"])


def scene_transform(scene_ref: Mapping[str, Any]) -> Mapping[str, Any]:
    return scene_ref.get("base_to_canonical", scene_ref)


def apply_vertical_datum(
    points: np.ndarray,
    input_datum: str = ORTHOMETRIC,
    geoid_m: float | None = None,
    config_path: str | Path | None = None,
) -> np.ndarray:
    a = np.asarray(points, float).copy()
    if a.ndim == 1:
        a = a[None]
    datum = input_datum.lower()
    if datum in {"ortho", "orthometric", "dhhn", "dhhn2016"}:
        a[:, 2] += projection_geoid_m(geoid_m, config_path)
    elif datum in {"ellip", "ellipsoid", "ellipsoidal", "wgs84"}:
        pass
    else:
        raise ValueError(f"unknown input_datum={input_datum!r}")
    return a


def base_to_canonical_points(
    points_base: np.ndarray,
    scene_ref: Mapping[str, Any],
    input_datum: str = ORTHOMETRIC,
    geoid_m: float | None = None,
    config_path: str | Path | None = None,
) -> np.ndarray:
    a = apply_vertical_datum(points_base, input_datum, geoid_m, config_path)
    t = scene_transform(scene_ref)
    if t.get("swap_xy", False):
        a[:, [0, 1]] = a[:, [1, 0]]
    return (a + np.array(t.get("shift", [0, 0, 0]), float)) * np.array(t.get("scale", [1, 1, 1]), float)


def canonical_to_base_points(points_canonical: np.ndarray, scene_ref: Mapping[str, Any]) -> np.ndarray:
    t = scene_transform(scene_ref)
    a = np.asarray(points_canonical, float).copy()
    if a.ndim == 1:
        a = a[None]
    a = a / np.array(t.get("scale", [1, 1, 1]), float) - np.array(t.get("shift", [0, 0, 0]), float)
    if t.get("swap_xy", False):
        a[:, [0, 1]] = a[:, [1, 0]]
    return a


def as_ellipsoidal_points(
    points_base: np.ndarray,
    input_datum: str = ORTHOMETRIC,
    geoid_m: float | None = None,
    config_path: str | Path | None = None,
) -> np.ndarray:
    return apply_vertical_datum(points_base, input_datum, geoid_m, config_path)


def describe_projection_config(config_path: str | Path | None = None) -> str:
    cfg = load_projection_config(config_path)
    return (
        f"geo={cfg.get('geo_crs', 'EPSG:25832')} opf={cfg.get('opf_crs', 'EPSG:32632')} "
        f"input_default={cfg.get('input_vertical_datum_default', ORTHOMETRIC)} "
        f"orthometric_geoid_m={projection_geoid_m(config_path=config_path):.6f}"
    )
