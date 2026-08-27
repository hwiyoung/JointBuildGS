"""Reference-integrity tests for the S2 verify-page bundle contract.

Contract: ``phd_s3_verify_s2_bundle_v1`` (S3 redesign verification pages,
stage 2: cells / faces / seeds on top of an existing S1 bundle in the same
``runs/<name>/`` directory).

Bundle root resolution follows tests.phd.test_s3_verify_s1_bundle exactly
(env ``JBGS_S3_VERIFY_ROOT`` -> ``JBGS_ARTIFACT_ROOT`` -> container default
-> host default).

Skip policy:
- no bundle root / no runs at all -> every test skips (bundle not generated);
- a run with NONE of the S2 files is an S1-only bundle and is skipped;
- a run with SOME but not all S2 files is a corrupt partial bundle -> failure.

Methodology fixed values (r16 — the single source of truth):
- o_init surface-height verdict: single vertical column of radius 0.75 m at
  the CELL CENTROID; z_surf = p90 of ALS-only (source==1) point heights in
  that column. centroid below z_surf -> t=0.75, above -> t=0.15, empty
  column -> t=0.4 (r16 reselection from 0.2), outside footprint -> t=0.0
  fixed. Multi-point averaging is abolished (r16).
- o_state = [t > 0.5]; soft t survives as the anchor target.
- initial real faces F* = { f : |o_state_a - o_state_b| = 1 } with o=0
  outside the domain boundary.
- seeds: one grid pass per face, present on EVERY face including gate-0
  (non-real) faces (lifetime rule (2)); no subsampling.

``scientific_verdict`` stays null and ``not_official`` stays true.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import numpy as np

try:
    from tests.phd.test_s3_verify_s1_bundle import (
        ARTIFACT_ROOT_ENV,
        BUNDLE_ENV,
        BUNDLE_RELPATH,
        DEFAULT_BUNDLE_ROOTS,
        SOURCE_ALS,
        as_index_array,
        discover_run_dirs,
        is_number,
        load_json,
        load_ply_points,
        resolve_bundle_root,
    )
except ImportError:  # direct-file execution fallback
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.phd.test_s3_verify_s1_bundle import (
        ARTIFACT_ROOT_ENV,
        BUNDLE_ENV,
        BUNDLE_RELPATH,
        DEFAULT_BUNDLE_ROOTS,
        SOURCE_ALS,
        as_index_array,
        discover_run_dirs,
        is_number,
        load_json,
        load_ply_points,
        resolve_bundle_root,
    )

S2_FILE_NAMES = ("s2_cells.json", "s2_faces.json", "s2_seeds.json")

STAGE_S1S2 = "s1+s2"
# Stages 3a (render-only wiring check), 3b (color-only training, geometry
# frozen) and 3c (delta unfreeze: global-translation + colors, planes/o
# frozen) append files to the same bundle and advance the manifest stage
# without invalidating any S2 guarantee.
S2_ALLOWED_STAGES = (STAGE_S1S2, "s1+s2+s3a", "s1+s2+s3a+s3b",
                     "s1+s2+s3a+s3b+s3c")

# r16 fixed o_init contract values (the only truth).
O_INIT_RADIUS_M = 0.75
O_INIT_STAT = "p90"
O_INIT_SAMPLE = "cell-centroid"
O_INIT_T = {"below": 0.75, "above": 0.15, "empty": 0.4, "outside": 0.0}
T_VALUES = np.asarray([O_INIT_T[k] for k in ("below", "above", "empty", "outside")])

VERDICTS = frozenset(O_INIT_T)
DOMAINS = frozenset({"wall", "ground", "top"})

CELL_ID_RE = re.compile(r"^c\d{4,}$")
FACE_ID_RE = re.compile(r"^f\d{5,}$")
SEED_ID_RE = re.compile(r"^s\d{6,}$")

CELL_REQUIRED_KEYS = (
    "cell_id",
    "centroid",
    "volume_m3",
    "fixed",
    "t",
    "o_state",
    "surf",
    "cut_plane_ids",
    "face_ids",
)
SURF_REQUIRED_KEYS = ("cx", "cy", "radius_m", "z_surf", "n_col_pts", "col_pt_idx", "verdict")
FACE_REQUIRED_KEYS = (
    "face_id",
    "cell_a",
    "cell_b",
    "s1_plane_ids",
    "domain",
    "n",
    "d",
    "poly3d",
    "area_m2",
    "initial_real",
)
SEED_REQUIRED_KEYS = ("seed_id", "face_id", "uv", "mu")
O_INIT_DEF_REQUIRED_KEYS = ("radius_m", "stat", "t", "sample", "als_only")
S2_COUNT_KEYS = ("cells", "faces", "seeds")
VOLUMES_REQUIRED_KEYS = ("prism_m3", "sum_cells_m3")

T_ATOL = 1e-6            # tolerance for t / o_init constants written by the writer
COORD_TOL_M = 1e-3       # tolerance for rounded JSON coords vs float32 PLY coords
VOLUME_RTOL = 1e-3       # contract: relative 1e-3 on volume conservation
SEED_PLANE_TOL_M = 1e-3  # contract: seed mu point-plane distance < 1e-3


def t_verdict_match(t_value, verdict) -> bool:
    expected = O_INIT_T.get(verdict)
    return expected is not None and abs(float(t_value) - expected) <= T_ATOL


def rel_close(a: float, b: float, rtol: float) -> bool:
    scale = max(abs(a), abs(b), 1e-12)
    return abs(a - b) <= rtol * scale


def polygon_area_2d(xy: np.ndarray) -> float:
    """Shoelace area of an [N,2] polygon (absolute value)."""
    x, y = xy[:, 0], xy[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def best_fit_plane(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(centroid, unit normal) of the best-fit plane through [N,3] points."""
    centroid = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - centroid, full_matrices=False)
    return centroid, vt[-1]


_BUNDLE_CACHE: dict[Path, dict] = {}


def run_has_any_s2(run_dir: Path) -> bool:
    return any((run_dir / name).is_file() for name in S2_FILE_NAMES)


def load_s2_bundle(run_dir: Path) -> dict:
    """Load and cache one run's S1+S2 files; missing files raise AssertionError."""
    cached = _BUNDLE_CACHE.get(run_dir)
    if cached is not None:
        return cached
    required = {
        "manifest": run_dir / "manifest.json",
        "planes": run_dir / "s1_planes.json",
        "view": run_dir / "s1_view.json",
        "cells": run_dir / "s2_cells.json",
        "faces": run_dir / "s2_faces.json",
        "seeds": run_dir / "s2_seeds.json",
    }
    ply_path = run_dir / "s1_points.ply"
    missing = [str(p) for p in [*required.values(), ply_path] if not p.is_file()]
    assert not missing, (
        f"{run_dir.name}: incomplete S1+S2 bundle, missing files: {missing}"
    )
    bundle = {name: load_json(path) for name, path in required.items()}
    bundle["points"] = load_ply_points(ply_path)
    bundle["run_dir"] = run_dir

    cells = bundle["cells"].get("cells")
    faces = bundle["faces"].get("faces")
    seeds = bundle["seeds"].get("seeds")
    assert isinstance(cells, list), f"{run_dir.name}: s2_cells.json cells must be a list"
    assert isinstance(faces, list), f"{run_dir.name}: s2_faces.json faces must be a list"
    assert isinstance(seeds, list), f"{run_dir.name}: s2_seeds.json seeds must be a list"
    bundle["cell_by_id"] = {
        c.get("cell_id"): c for c in cells if isinstance(c, dict)
    }
    bundle["face_by_id"] = {
        f.get("face_id"): f for f in faces if isinstance(f, dict)
    }
    bundle["s1_plane_ids"] = {
        p.get("plane_id") for p in bundle["planes"].get("planes", [])
    }
    _BUNDLE_CACHE[run_dir] = bundle
    return bundle


class S2BundleReferenceIntegrityTest(unittest.TestCase):
    """Strict reference-integrity validation for every discovered S2 run."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle_root = resolve_bundle_root()
        cls.run_dirs = discover_run_dirs(cls.bundle_root)
        # A run participates once ANY S2 file exists; partial S2 sets then
        # fail inside load_s2_bundle. Runs with no S2 file are S1-only.
        cls.s2_run_dirs = [d for d in cls.run_dirs if run_has_any_s2(d)]

    def setUp(self) -> None:
        if not self.run_dirs:
            self.skipTest(
                "S1 verify bundle not generated yet: no runs/<name>/ found under "
                f"env {BUNDLE_ENV}, {ARTIFACT_ROOT_ENV}/{BUNDLE_RELPATH}, or defaults "
                f"{[str(p) for p in DEFAULT_BUNDLE_ROOTS]}"
            )
        if not self.s2_run_dirs:
            self.skipTest(
                "S2 bundle files not generated yet in any run (S1-only bundles "
                f"are allowed): looked for {list(S2_FILE_NAMES)} in "
                f"{[d.name for d in self.run_dirs]}"
            )

    def for_each_s2_run(self, check) -> None:
        """Run one check per discovered S2 run inside a subTest scope."""
        for run_dir in self.s2_run_dirs:
            with self.subTest(run=run_dir.name):
                check(run_dir.name, load_s2_bundle(run_dir))

    # -------------------------------------------------------- 1. manifest s2

    def test_manifest_s2_contract_fields(self) -> None:
        self.for_each_s2_run(self._check_manifest_s2_contract_fields)

    def _check_manifest_s2_contract_fields(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        self.assertIn(
            manifest.get("stage"), S2_ALLOWED_STAGES,
            f"{name}: manifest stage must be one of {S2_ALLOWED_STAGES} "
            "once S2 files exist",
        )
        self.assertIsNone(
            manifest.get("scientific_verdict"),
            f"{name}: scientific_verdict must stay null",
        )
        self.assertIs(
            manifest.get("not_official"), True,
            f"{name}: not_official must stay true",
        )

        o_init = manifest.get("o_init_def")
        self.assertIsInstance(o_init, dict, f"{name}: manifest missing o_init_def object")
        for key in O_INIT_DEF_REQUIRED_KEYS:
            self.assertIn(key, o_init, f"{name}: o_init_def missing key {key!r}")
        self.assertTrue(
            is_number(o_init["radius_m"])
            and abs(o_init["radius_m"] - O_INIT_RADIUS_M) <= T_ATOL,
            f"{name}: o_init_def.radius_m must be {O_INIT_RADIUS_M} (r16), "
            f"got {o_init['radius_m']!r}",
        )
        self.assertEqual(
            o_init["stat"], O_INIT_STAT,
            f"{name}: o_init_def.stat must be {O_INIT_STAT!r}",
        )
        self.assertEqual(
            o_init["sample"], O_INIT_SAMPLE,
            f"{name}: o_init_def.sample must be {O_INIT_SAMPLE!r} "
            "(single centroid column; multi-point averaging abolished in r16)",
        )
        self.assertIs(
            o_init["als_only"], True, f"{name}: o_init_def.als_only must be true"
        )
        t_def = o_init["t"]
        self.assertIsInstance(t_def, dict, f"{name}: o_init_def.t must be an object")
        self.assertEqual(
            set(t_def), set(O_INIT_T),
            f"{name}: o_init_def.t keys must be exactly {sorted(O_INIT_T)}",
        )
        for key, expected in O_INIT_T.items():
            self.assertTrue(
                is_number(t_def[key]) and abs(t_def[key] - expected) <= T_ATOL,
                f"{name}: o_init_def.t.{key} must be {expected} (r16: empty=0.4), "
                f"got {t_def[key]!r}",
            )

        counts = manifest.get("counts", {})
        expected_counts = {
            "cells": len(bundle["cells"]["cells"]),
            "faces": len(bundle["faces"]["faces"]),
            "seeds": len(bundle["seeds"]["seeds"]),
        }
        for key in S2_COUNT_KEYS:
            value = counts.get(key)
            self.assertTrue(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0,
                f"{name}: counts.{key} must be a non-negative integer, got {value!r}",
            )
            self.assertEqual(
                value, expected_counts[key],
                f"{name}: counts.{key}={value} != len(s2 {key} array)="
                f"{expected_counts[key]}",
            )

        volumes = manifest.get("volumes")
        self.assertIsInstance(volumes, dict, f"{name}: manifest missing volumes object")
        for key in VOLUMES_REQUIRED_KEYS:
            self.assertTrue(
                is_number(volumes.get(key)),
                f"{name}: volumes.{key} must be a number, got {volumes.get(key)!r}",
            )

        dataset = manifest.get("dataset", {})
        if isinstance(dataset, dict) and dataset.get("kind") == "synthetic":
            self.assertIs(
                manifest.get("synthetic_als"), True,
                f"{name}: synthetic dataset must declare synthetic_als: true "
                "(pseudo-ALS deterministically sampled from GT faces)",
            )
            self.assertGreater(
                counts.get("points_als", 0), 0,
                f"{name}: synthetic_als run must carry source==1 pseudo-ALS "
                "points in s1_points.ply (S1 regeneration with updated counts)",
            )

    # ----------------------------------------------------------- 2. s2_cells

    def test_cells_reference_integrity(self) -> None:
        self.for_each_s2_run(self._check_cells_reference_integrity)

    def _check_cells_reference_integrity(self, name: str, bundle: dict) -> None:
        cells = bundle["cells"]["cells"]
        points = bundle["points"]
        total = len(points)
        source = points["source"]
        face_ids_all = set(bundle["face_by_id"])
        s1_plane_ids = bundle["s1_plane_ids"]
        cells_path = bundle["run_dir"] / "s2_cells.json"

        cell_ids = [cell.get("cell_id") for cell in cells]
        self.assertEqual(
            len(cell_ids), len(set(cell_ids)),
            f"{name}: duplicate cell_id values: "
            f"{sorted({c for c in cell_ids if cell_ids.count(c) > 1})}",
        )

        t_list: list[float] = []
        o_list: list[int] = []
        fixed_list: list[bool] = []
        verdict_ok: list[bool] = []
        col_idx_parts: list[np.ndarray] = []
        col_center_parts: list[np.ndarray] = []

        for cell in cells:
            cid = cell.get("cell_id")
            for key in CELL_REQUIRED_KEYS:
                self.assertIn(key, cell, f"{name}/{cid}: cell missing key {key!r}")
            self.assertTrue(
                isinstance(cid, str) and CELL_ID_RE.match(cid),
                f"{name}: cell_id must match 'c'+digits (>=4), got {cid!r}",
            )
            centroid = cell["centroid"]
            self.assertTrue(
                isinstance(centroid, list)
                and len(centroid) == 3
                and all(is_number(v) for v in centroid),
                f"{name}/{cid}: centroid must be [x, y, z] numeric",
            )
            self.assertTrue(
                is_number(cell["volume_m3"]) and cell["volume_m3"] >= 0,
                f"{name}/{cid}: volume_m3 must be a non-negative number",
            )
            self.assertIsInstance(
                cell["fixed"], bool, f"{name}/{cid}: fixed must be a bool"
            )
            self.assertTrue(is_number(cell["t"]), f"{name}/{cid}: t must be a number")
            self.assertTrue(
                isinstance(cell["o_state"], int)
                and not isinstance(cell["o_state"], bool)
                and cell["o_state"] in (0, 1),
                f"{name}/{cid}: o_state must be the integer 0 or 1",
            )

            surf = cell["surf"]
            self.assertIsInstance(surf, dict, f"{name}/{cid}: surf must be an object")
            for key in SURF_REQUIRED_KEYS:
                self.assertIn(key, surf, f"{name}/{cid}: surf missing key {key!r}")
            verdict = surf["verdict"]
            self.assertIn(
                verdict, VERDICTS,
                f"{name}/{cid}: surf.verdict {verdict!r} not in {sorted(VERDICTS)}",
            )
            self.assertTrue(
                is_number(surf["radius_m"])
                and abs(surf["radius_m"] - O_INIT_RADIUS_M) <= T_ATOL,
                f"{name}/{cid}: surf.radius_m must be {O_INIT_RADIUS_M}",
            )
            self.assertTrue(
                is_number(surf["cx"]) and is_number(surf["cy"]),
                f"{name}/{cid}: surf.cx/cy must be numeric",
            )
            # sample == cell-centroid: the column sits at the cell centroid.
            self.assertLessEqual(
                max(abs(surf["cx"] - centroid[0]), abs(surf["cy"] - centroid[1])),
                COORD_TOL_M,
                f"{name}/{cid}: surf.(cx,cy) must equal centroid xy "
                "(o_init sample is cell-centroid)",
            )

            col_idx = as_index_array(
                surf["col_pt_idx"], cells_path, f"{cid}.surf.col_pt_idx"
            )
            self.assertTrue(
                isinstance(surf["n_col_pts"], int)
                and not isinstance(surf["n_col_pts"], bool)
                and surf["n_col_pts"] == col_idx.size,
                f"{name}/{cid}: surf.n_col_pts must equal len(col_pt_idx)",
            )
            if col_idx.size:
                self.assertTrue(
                    bool((col_idx >= 0).all()) and bool((col_idx < total).all()),
                    f"{name}/{cid}: col_pt_idx out of [0, {total})",
                )
                self.assertEqual(
                    col_idx.size, np.unique(col_idx).size,
                    f"{name}/{cid}: duplicate indices inside col_pt_idx",
                )
                col_idx_parts.append(col_idx)
                col_center_parts.append(
                    np.repeat(
                        np.asarray([[surf["cx"], surf["cy"]]], dtype=np.float64),
                        col_idx.size,
                        axis=0,
                    )
                )

            if verdict == "empty":
                self.assertIsNone(
                    surf["z_surf"],
                    f"{name}/{cid}: empty column must record z_surf: null",
                )
                self.assertEqual(
                    col_idx.size, 0,
                    f"{name}/{cid}: empty column must record col_pt_idx: []",
                )
            elif verdict in ("below", "above"):
                self.assertTrue(
                    is_number(surf["z_surf"]),
                    f"{name}/{cid}: verdict {verdict!r} requires numeric z_surf (p90)",
                )
                self.assertGreaterEqual(
                    col_idx.size, 1,
                    f"{name}/{cid}: verdict {verdict!r} requires column points",
                )
                col_z = points["z"][col_idx].astype(np.float64)
                self.assertTrue(
                    float(col_z.min()) - COORD_TOL_M
                    <= surf["z_surf"]
                    <= float(col_z.max()) + COORD_TOL_M,
                    f"{name}/{cid}: z_surf (p90) must lie within the column "
                    f"z range [{col_z.min()}, {col_z.max()}]",
                )

            cut_ids = cell["cut_plane_ids"]
            self.assertIsInstance(
                cut_ids, list, f"{name}/{cid}: cut_plane_ids must be a list"
            )
            self.assertEqual(
                len(cut_ids), len(set(cut_ids)),
                f"{name}/{cid}: duplicate entries in cut_plane_ids",
            )
            unknown_cuts = [p for p in cut_ids if p not in s1_plane_ids]
            self.assertFalse(
                unknown_cuts,
                f"{name}/{cid}: cut_plane_ids reference unknown s1 plane_id "
                f"{unknown_cuts}",
            )

            fids = cell["face_ids"]
            self.assertIsInstance(
                fids, list, f"{name}/{cid}: face_ids must be a list"
            )
            self.assertEqual(
                len(fids), len(set(fids)),
                f"{name}/{cid}: duplicate entries in face_ids",
            )
            unknown_faces = [f for f in fids if f not in face_ids_all]
            self.assertFalse(
                unknown_faces,
                f"{name}/{cid}: face_ids reference unknown face_id {unknown_faces}",
            )

            t_list.append(float(cell["t"]))
            o_list.append(int(cell["o_state"]))
            fixed_list.append(bool(cell["fixed"]))
            verdict_ok.append(t_verdict_match(cell["t"], verdict))

        if not cells:
            return
        t_arr = np.asarray(t_list, dtype=np.float64)
        o_arr = np.asarray(o_list, dtype=np.int64)
        fixed_arr = np.asarray(fixed_list, dtype=bool)
        ids_arr = np.asarray(cell_ids, dtype=object)

        # t in {0.75, 0.15, 0.4, 0.0}
        dist = np.abs(t_arr[:, None] - T_VALUES[None, :]).min(axis=1)
        bad_t = ids_arr[dist > T_ATOL]
        self.assertEqual(
            bad_t.size, 0,
            f"{name}: t outside contract set {sorted(set(O_INIT_T.values()))} "
            f"for cells {bad_t.tolist()}",
        )

        # o_state == [t > 0.5]
        expected_o = (t_arr > 0.5).astype(np.int64)
        bad_o = ids_arr[o_arr != expected_o]
        self.assertEqual(
            bad_o.size, 0,
            f"{name}: o_state != [t > 0.5] for cells {bad_o.tolist()}",
        )

        # fixed <=> t == 0.0 (outside footprint)
        expected_fixed = np.abs(t_arr - O_INIT_T["outside"]) <= T_ATOL
        bad_fixed = ids_arr[fixed_arr != expected_fixed]
        self.assertEqual(
            bad_fixed.size, 0,
            f"{name}: fixed flag must hold exactly when t == 0.0 (outside "
            f"footprint); violated by cells {bad_fixed.tolist()}",
        )

        # verdict -> t mapping (below 0.75 / above 0.15 / empty 0.4 / outside 0.0)
        bad_verdict = ids_arr[~np.asarray(verdict_ok, dtype=bool)]
        self.assertEqual(
            bad_verdict.size, 0,
            f"{name}: surf.verdict does not match t (below->0.75, above->0.15, "
            f"empty->0.4, outside->0.0) for cells {bad_verdict.tolist()}",
        )

        # column indices: ALS-only (source==1) and horizontally inside the column
        if col_idx_parts:
            all_idx = np.concatenate(col_idx_parts)
            bad_src = int(np.count_nonzero(source[all_idx] != SOURCE_ALS))
            self.assertEqual(
                bad_src, 0,
                f"{name}: {bad_src} col_pt_idx entries point at non-ALS points "
                "(o_init is ALS-only: source==1)",
            )
            centers = np.concatenate(col_center_parts, axis=0)
            px = points["x"][all_idx].astype(np.float64)
            py = points["y"][all_idx].astype(np.float64)
            r = np.hypot(px - centers[:, 0], py - centers[:, 1])
            n_out = int(np.count_nonzero(r > O_INIT_RADIUS_M + COORD_TOL_M))
            self.assertEqual(
                n_out, 0,
                f"{name}: {n_out} col_pt_idx points lie outside the "
                f"{O_INIT_RADIUS_M} m column radius of their cell centroid",
            )

    # ----------------------------------------------------------- 3. s2_faces

    def test_faces_reference_integrity(self) -> None:
        self.for_each_s2_run(self._check_faces_reference_integrity)

    def _check_faces_reference_integrity(self, name: str, bundle: dict) -> None:
        faces = bundle["faces"]["faces"]
        cell_by_id = bundle["cell_by_id"]
        s1_plane_ids = bundle["s1_plane_ids"]

        face_ids = [face.get("face_id") for face in faces]
        self.assertEqual(
            len(face_ids), len(set(face_ids)),
            f"{name}: duplicate face_id values: "
            f"{sorted({f for f in face_ids if face_ids.count(f) > 1})}",
        )

        for face in faces:
            fid = face.get("face_id")
            for key in FACE_REQUIRED_KEYS:
                self.assertIn(key, face, f"{name}/{fid}: face missing key {key!r}")
            self.assertTrue(
                isinstance(fid, str) and FACE_ID_RE.match(fid),
                f"{name}: face_id must match 'f'+digits (>=5), got {fid!r}",
            )

            cell_a = face["cell_a"]
            cell_b = face["cell_b"]
            domain = face["domain"]
            self.assertIn(
                cell_a, cell_by_id,
                f"{name}/{fid}: cell_a references unknown cell_id {cell_a!r}",
            )
            if domain is None:
                self.assertIn(
                    cell_b, cell_by_id,
                    f"{name}/{fid}: interior face cell_b references unknown "
                    f"cell_id {cell_b!r}",
                )
                self.assertNotEqual(
                    cell_a, cell_b, f"{name}/{fid}: cell_a and cell_b must differ"
                )
            else:
                self.assertIn(
                    domain, DOMAINS,
                    f"{name}/{fid}: domain must be null or one of "
                    f"{sorted(DOMAINS)}, got {domain!r}",
                )
                self.assertIsNone(
                    cell_b,
                    f"{name}/{fid}: domain-boundary face must have cell_b: null",
                )

            plane_refs = face["s1_plane_ids"]
            self.assertIsInstance(
                plane_refs, list, f"{name}/{fid}: s1_plane_ids must be a list"
            )
            if domain is not None:
                self.assertEqual(
                    plane_refs, [],
                    f"{name}/{fid}: domain face must carry an empty s1_plane_ids",
                )
            else:
                self.assertGreaterEqual(
                    len(plane_refs), 1,
                    f"{name}/{fid}: interior (cut) face must reference the full "
                    "ring of s1 plane_ids of its cutting plane",
                )
                self.assertEqual(
                    len(plane_refs), len(set(plane_refs)),
                    f"{name}/{fid}: duplicate entries in s1_plane_ids",
                )
                unknown = [p for p in plane_refs if p not in s1_plane_ids]
                self.assertFalse(
                    unknown,
                    f"{name}/{fid}: s1_plane_ids reference unknown s1 plane_id "
                    f"{unknown}",
                )

            n = face["n"]
            self.assertTrue(
                isinstance(n, list) and len(n) == 3 and all(is_number(v) for v in n),
                f"{name}/{fid}: n must be [nx, ny, nz] numeric",
            )
            self.assertGreater(
                float(np.linalg.norm(np.asarray(n, dtype=np.float64))), 0.0,
                f"{name}/{fid}: n must be non-zero",
            )
            self.assertTrue(is_number(face["d"]), f"{name}/{fid}: d must be numeric")

            poly = face["poly3d"]
            self.assertTrue(
                isinstance(poly, list) and len(poly) >= 3,
                f"{name}/{fid}: poly3d needs at least 3 vertices",
            )
            for vertex in poly:
                self.assertTrue(
                    isinstance(vertex, list)
                    and len(vertex) == 3
                    and all(is_number(v) for v in vertex),
                    f"{name}/{fid}: poly3d vertices must be [x, y, z] numeric",
                )
            self.assertTrue(
                is_number(face["area_m2"]) and face["area_m2"] > 0,
                f"{name}/{fid}: area_m2 must be a positive number",
            )
            self.assertIsInstance(
                face["initial_real"], bool,
                f"{name}/{fid}: initial_real must be a bool",
            )

        # F* recomputation: initial_real == XOR of o_state, o=0 beyond domain.
        o_by_cell = {
            cid: int(cell.get("o_state", 0)) for cid, cell in cell_by_id.items()
        }
        o_a = np.asarray(
            [o_by_cell.get(face["cell_a"], 0) for face in faces], dtype=np.int64
        )
        o_b = np.asarray(
            [
                o_by_cell.get(face["cell_b"], 0) if face["cell_b"] is not None else 0
                for face in faces
            ],
            dtype=np.int64,
        )
        stored = np.asarray([bool(face["initial_real"]) for face in faces], dtype=bool)
        expected = np.abs(o_a - o_b) == 1
        bad = np.asarray(face_ids, dtype=object)[stored != expected]
        self.assertEqual(
            bad.size, 0,
            f"{name}: initial_real disagrees with recomputed F* "
            "(|o_state_a - o_state_b| == 1, domain side o=0) for faces "
            f"{bad.tolist()}",
        )

    # ----------------------------------------------------------- 4. s2_seeds

    def test_seeds_reference_integrity(self) -> None:
        self.for_each_s2_run(self._check_seeds_reference_integrity)

    def _check_seeds_reference_integrity(self, name: str, bundle: dict) -> None:
        seeds_doc = bundle["seeds"]
        seeds = seeds_doc["seeds"]
        face_by_id = bundle["face_by_id"]

        grid = seeds_doc.get("grid")
        self.assertIsInstance(grid, dict, f"{name}: s2_seeds.json missing grid object")
        for key in ("spacing_m", "size_m"):
            self.assertTrue(
                is_number(grid.get(key)) and grid[key] > 0,
                f"{name}: grid.{key} must be a positive number, got {grid.get(key)!r}",
            )

        seed_ids = [seed.get("seed_id") for seed in seeds]
        self.assertEqual(
            len(seed_ids), len(set(seed_ids)),
            f"{name}: duplicate seed_id values",
        )

        for seed in seeds:
            sid = seed.get("seed_id")
            for key in SEED_REQUIRED_KEYS:
                self.assertIn(key, seed, f"{name}/{sid}: seed missing key {key!r}")
            self.assertTrue(
                isinstance(sid, str) and SEED_ID_RE.match(sid),
                f"{name}: seed_id must match 's'+digits (>=6), got {sid!r}",
            )
            self.assertIn(
                seed["face_id"], face_by_id,
                f"{name}/{sid}: face_id references unknown face "
                f"{seed['face_id']!r}",
            )
            uv = seed["uv"]
            self.assertTrue(
                isinstance(uv, list) and len(uv) == 2 and all(is_number(v) for v in uv),
                f"{name}/{sid}: uv must be [u, v] numeric",
            )
            mu = seed["mu"]
            self.assertTrue(
                isinstance(mu, list) and len(mu) == 3 and all(is_number(v) for v in mu),
                f"{name}/{sid}: mu must be [x, y, z] numeric",
            )

        # Every face — including gate-0 (non-real) faces — carries >= 1 seed
        # (lifetime rule (2): seeds exist on non-real faces too).
        seeded_faces = {seed["face_id"] for seed in seeds}
        unseeded = sorted(set(face_by_id) - seeded_faces)
        self.assertFalse(
            unseeded,
            f"{name}: faces without any seed (lifetime rule (2) requires seeds "
            f"on every face, including gate-0 faces): {unseeded}",
        )

        # mu lies on the face's poly3d plane (point-plane distance < 1e-3).
        plane_by_face: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for fid, face in face_by_id.items():
            poly = np.asarray(face["poly3d"], dtype=np.float64)
            if poly.ndim == 2 and poly.shape[0] >= 3 and poly.shape[1] == 3:
                plane_by_face[fid] = best_fit_plane(poly)
        if seeds:
            centroids = np.empty((len(seeds), 3), dtype=np.float64)
            normals = np.empty((len(seeds), 3), dtype=np.float64)
            mus = np.empty((len(seeds), 3), dtype=np.float64)
            for i, seed in enumerate(seeds):
                centroid, normal = plane_by_face[seed["face_id"]]
                centroids[i] = centroid
                normals[i] = normal
                mus[i] = np.asarray(seed["mu"], dtype=np.float64)
            dist = np.abs(np.einsum("ij,ij->i", mus - centroids, normals))
            bad = np.asarray(seed_ids, dtype=object)[dist >= SEED_PLANE_TOL_M]
            self.assertEqual(
                bad.size, 0,
                f"{name}: seed mu off its face poly3d plane by >= "
                f"{SEED_PLANE_TOL_M} m: {bad.tolist()[:20]} "
                f"(max distance {float(dist.max())})",
            )

    # ------------------------------------------------- 5. volume conservation

    def test_volume_conservation(self) -> None:
        self.for_each_s2_run(self._check_volume_conservation)

    def _check_volume_conservation(self, name: str, bundle: dict) -> None:
        cells_doc = bundle["cells"]
        view = bundle["view"]
        manifest = bundle["manifest"]

        for key in ("prism_volume_m3", "sum_cell_volume_m3"):
            self.assertTrue(
                is_number(cells_doc.get(key)),
                f"{name}: s2_cells.json {key} must be a number, "
                f"got {cells_doc.get(key)!r}",
            )
        prism = float(cells_doc["prism_volume_m3"])
        sum_field = float(cells_doc["sum_cell_volume_m3"])
        self.assertGreater(prism, 0.0, f"{name}: prism_volume_m3 must be positive")

        volumes = np.asarray(
            [float(cell["volume_m3"]) for cell in cells_doc["cells"]],
            dtype=np.float64,
        )
        sum_cells = float(volumes.sum()) if volumes.size else 0.0

        self.assertTrue(
            rel_close(sum_cells, prism, VOLUME_RTOL),
            f"{name}: |sum(cell volumes) - prism_volume_m3| exceeds relative "
            f"{VOLUME_RTOL}: sum={sum_cells}, prism={prism}",
        )
        self.assertTrue(
            rel_close(sum_field, sum_cells, VOLUME_RTOL),
            f"{name}: sum_cell_volume_m3={sum_field} != recomputed "
            f"sum {sum_cells} (relative {VOLUME_RTOL})",
        )

        footprint = np.asarray(view["footprint_local"], dtype=np.float64)
        self.assertGreaterEqual(
            footprint.shape[0], 3, f"{name}: footprint_local needs >= 3 vertices"
        )
        height = float(view["top_z"]) - float(view["ground_z"])
        expected_prism = polygon_area_2d(footprint) * height
        self.assertTrue(
            rel_close(prism, expected_prism, VOLUME_RTOL),
            f"{name}: prism_volume_m3={prism} != footprint area x "
            f"(top_z - ground_z) = {expected_prism} (relative {VOLUME_RTOL})",
        )

        manifest_volumes = manifest.get("volumes", {})
        if isinstance(manifest_volumes, dict):
            if is_number(manifest_volumes.get("prism_m3")):
                self.assertTrue(
                    rel_close(float(manifest_volumes["prism_m3"]), prism, VOLUME_RTOL),
                    f"{name}: manifest volumes.prism_m3="
                    f"{manifest_volumes['prism_m3']} != s2_cells prism_volume_m3="
                    f"{prism}",
                )
            if is_number(manifest_volumes.get("sum_cells_m3")):
                self.assertTrue(
                    rel_close(
                        float(manifest_volumes["sum_cells_m3"]), sum_field, VOLUME_RTOL
                    ),
                    f"{name}: manifest volumes.sum_cells_m3="
                    f"{manifest_volumes['sum_cells_m3']} != s2_cells "
                    f"sum_cell_volume_m3={sum_field}",
                )

    # ------------------------------------------- 6. cell-face mutual linkage

    def test_cell_face_mutual_consistency(self) -> None:
        self.for_each_s2_run(self._check_cell_face_mutual_consistency)

    def _check_cell_face_mutual_consistency(self, name: str, bundle: dict) -> None:
        cell_by_id = bundle["cell_by_id"]
        faces = bundle["faces"]["faces"]

        # forward: each face must appear in the face_ids of its cell_a/cell_b.
        for face in faces:
            fid = face["face_id"]
            for role in ("cell_a", "cell_b"):
                cid = face[role]
                if cid is None:
                    continue
                cell = cell_by_id.get(cid)
                if cell is None:
                    continue  # unknown references already fail in test 3
                self.assertIn(
                    fid, cell.get("face_ids", []),
                    f"{name}/{fid}: face missing from face_ids of its "
                    f"{role} {cid!r}",
                )

        # backward: every face listed by a cell must name that cell as a/b.
        face_by_id = bundle["face_by_id"]
        for cid, cell in cell_by_id.items():
            for fid in cell.get("face_ids", []):
                face = face_by_id.get(fid)
                if face is None:
                    continue  # unknown references already fail in test 2
                self.assertIn(
                    cid, (face.get("cell_a"), face.get("cell_b")),
                    f"{name}/{cid}: face_ids lists {fid!r} but that face "
                    f"joins {face.get('cell_a')!r}/{face.get('cell_b')!r}",
                )


if __name__ == "__main__":
    unittest.main()
