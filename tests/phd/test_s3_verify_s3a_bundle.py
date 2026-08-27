"""Reference-integrity tests for the S3a verify-page bundle contract.

Contract: ``phd_s3_verify_s3a_v1`` (S3 redesign verification pages, third
stage, internal step 3a "render-only": 0 optimizer steps, the run exists to
prove the differentiable-rendering wiring itself). S3a files are appended to
an existing S1+S2 bundle in the same ``runs/<name>/`` directory. Basis: plan
document revision note 2026-08-27 (commit 64664b98).

Bundle root resolution follows tests.phd.test_s3_verify_s1_bundle exactly
(env ``JBGS_S3_VERIFY_ROOT`` -> ``JBGS_ARTIFACT_ROOT`` -> container default
-> host default).

Skip policy (mirrors the S2 module):
- no bundle root / no runs at all -> every test skips (bundle not generated);
- a run with NONE of the S3a files is an S1/S2-only bundle and is skipped;
- a run with SOME but not all S3a files is a corrupt partial bundle -> failure.

Methodology fixed values (r16 render-state definition — the single truth):
- Gaussians derive from the FULL s2_seeds set; opacity alpha_g =
  |o_state_a - o_state_b| in {0,1} is a DERIVED quantity (s2_faces
  ``initial_real``), never a free learned alpha -> the step row must assert
  ``invariants.alpha_binary: true``.
- delta is wired as a render argument from the very start (P0 + delta flows
  differentiably into Gaussian position/orientation) but stays frozen at 0
  in 3a -> ``s3_def.delta_wired: true``, ``delta_value: [0, 0, 0]``,
  ``delta_hat: [0, 0, 0]``, ``invariants.delta_frozen: true``.
- No densification/pruning ever (lifetime rule (1)) ->
  ``invariants.n_seeds == manifest counts.seeds``.
- Renderer is gsplat (repo invariant 6: never the official 2DGS fork); the
  canonical term is "differentiable rendering". Color is a neutral-gray
  constant in 3a; the optimizer is "none" (0 steps).
- One backward pass IS executed (no weight update: ``param_step_norm == 0``)
  so ``grad_norms`` for the three groups delta/planes/colors are the wiring
  evidence: each must exist and be finite and non-negative.

View selection: real buildings pick the per-building top views from the
sealed base cameras/images (legacy selection machinery), count set by config
within [8, 24]; SYNTH reuses the existing x0 path (GT Gaussian renders serve
as photos), so only >= 1 view is required there. The writer-owned ``s3``
block of ``configs/phd/s3_verify_v1/s1_bundle_v1.json`` (keys ``n_views``,
``tile_max_px``) refines the bounds when present; contract hard bounds
(8..24 real views, tile long side <= 640 px) always apply.

``scientific_verdict`` stays null and ``not_official`` stays true.
"""

from __future__ import annotations

import json
import math
import re
import struct
import unittest
from pathlib import Path

try:
    from tests.phd.test_s3_verify_s1_bundle import (
        ARTIFACT_ROOT_ENV,
        BUNDLE_ENV,
        BUNDLE_RELPATH,
        DEFAULT_BUNDLE_ROOTS,
        discover_run_dirs,
        is_number,
        load_json,
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
        discover_run_dirs,
        is_number,
        load_json,
        resolve_bundle_root,
    )

S3A_SCHEMA = "phd_s3_verify_s3a_v1"
STAGE_S1S2S3A = "s1+s2+s3a"
# Stages 3b (color-only training) and 3c (delta unfreeze) append files to
# the same bundle and advance the manifest stage without invalidating any
# S3a guarantee.
S3A_ALLOWED_STAGES = (STAGE_S1S2S3A, "s1+s2+s3a+s3b", "s1+s2+s3a+s3b+s3c")
# Checkpoint snapshot directories s3_tiles/s<step>/ (S3b) and
# s3_tiles/s3c_s<step>/ (S3c) live alongside the 3a per-view tile
# directories; they are owned by the S3b/S3c modules respectively.
STEP_SNAPSHOT_DIR_RE = re.compile(r"^(?:s|s3c_s)\d+$")

S3A_FILE_NAMES = ("s3_views.json", "s3_steps.jsonl", "s3_face_residual.json")
S3A_TILES_DIRNAME = "s3_tiles"
TILE_FILE_NAMES = ("photo.png", "render.png", "residual.png")

# Contract hard values.
TILE_MIN_BYTES = 1024        # tiles must be non-empty (> 1 KB)
TILE_MAX_PX_CONTRACT = 640   # downscaled tiles: long side <= 640 px
REAL_N_VIEWS_MIN = 8         # real buildings: config picks a count in [8, 24]
REAL_N_VIEWS_MAX = 24

S3_DEF_REQUIRED_KEYS = (
    "stage",
    "delta_wired",
    "delta_value",
    "color",
    "optimizer",
    "renderer",
    "n_views",
)
S3_DEF_STAGE = "3a"
S3_DEF_COLOR = "neutral-gray"
S3_DEF_OPTIMIZER = "none"
S3_DEF_RENDERER = "gsplat"

VIEW_REQUIRED_KEYS = ("view_id", "image_ref", "width", "height")
STEP_REQUIRED_KEYS = (
    "step",
    "stage",
    "losses",
    "grad_norms",
    "delta_hat",
    "invariants",
    "param_step_norm",
    "views_psnr",
)
LOSS_REQUIRED_KEYS = ("photo", "anchor", "area", "total")
GRAD_NORM_KEYS = ("delta", "planes", "colors")
INVARIANTS_REQUIRED_KEYS = ("n_seeds", "alpha_binary", "delta_frozen")

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "phd" / "s3_verify_v1" / "s1_bundle_v1.json"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def load_s3_config() -> dict:
    """Return the writer-owned ``s3`` block of the bundle config, or {}."""
    if not CONFIG_PATH.is_file():
        return {}
    try:
        config = load_json(CONFIG_PATH)
    except (OSError, ValueError):
        return {}
    s3 = config.get("s3") if isinstance(config, dict) else None
    return s3 if isinstance(s3, dict) else {}


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def effective_tile_max_px(s3_config: dict) -> int:
    """Config tile_max_px capped by the contract hard bound (640)."""
    value = s3_config.get("tile_max_px")
    if _positive_int(value):
        return min(value, TILE_MAX_PX_CONTRACT)
    return TILE_MAX_PX_CONTRACT


def real_view_bounds(s3_config: dict) -> tuple[int, int]:
    """(lo, hi) allowed view count for REAL runs.

    A valid config ``n_views`` int inside [8, 24] pins the count exactly;
    a valid ``[lo, hi]`` pair is intersected with [8, 24]; anything else
    falls back to the contract bounds.
    """
    value = s3_config.get("n_views")
    if _positive_int(value) and REAL_N_VIEWS_MIN <= value <= REAL_N_VIEWS_MAX:
        return value, value
    if (
        isinstance(value, list)
        and len(value) == 2
        and all(_positive_int(v) for v in value)
    ):
        lo = max(int(value[0]), REAL_N_VIEWS_MIN)
        hi = min(int(value[1]), REAL_N_VIEWS_MAX)
        if lo <= hi:
            return lo, hi
    return REAL_N_VIEWS_MIN, REAL_N_VIEWS_MAX


def is_finite_number(value) -> bool:
    return is_number(value) and math.isfinite(float(value))


def matrix_ok(value, rows: int, cols: int) -> bool:
    """True when value is a numeric nested list of shape [rows][cols]."""
    return (
        isinstance(value, list)
        and len(value) == rows
        and all(
            isinstance(row, list)
            and len(row) == cols
            and all(is_number(v) for v in row)
            for row in value
        )
    )


def vector_ok(value, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == length
        and all(is_number(v) for v in value)
    )


def read_png_meta(path: Path) -> tuple[int, int, int]:
    """(width, height, byte size) after PNG signature/IHDR validation."""
    raw = path.read_bytes()
    assert len(raw) >= 33, f"{path}: file too small to be a PNG ({len(raw)} bytes)"
    assert raw[:8] == PNG_SIGNATURE, f"{path}: missing PNG signature"
    assert raw[12:16] == b"IHDR", f"{path}: first PNG chunk must be IHDR"
    width, height = struct.unpack(">II", raw[16:24])
    return int(width), int(height), len(raw)


def run_has_any_s3a(run_dir: Path) -> bool:
    if (run_dir / S3A_TILES_DIRNAME).is_dir():
        return True
    return any((run_dir / name).is_file() for name in S3A_FILE_NAMES)


_BUNDLE_CACHE: dict[Path, dict] = {}


def load_s3a_bundle(run_dir: Path) -> dict:
    """Load and cache one run's S3a files; missing files raise AssertionError.

    Only what S3a checks read is required here (manifest, s2_faces, the S3a
    files); full S1/S2 completeness is already enforced by the S1/S2 modules
    on every discovered run.
    """
    cached = _BUNDLE_CACHE.get(run_dir)
    if cached is not None:
        return cached
    required_json = {
        "manifest": run_dir / "manifest.json",
        "faces": run_dir / "s2_faces.json",
        "views": run_dir / "s3_views.json",
        "face_residual": run_dir / "s3_face_residual.json",
    }
    steps_path = run_dir / "s3_steps.jsonl"
    tiles_dir = run_dir / S3A_TILES_DIRNAME
    missing = [
        str(p) for p in [*required_json.values(), steps_path] if not p.is_file()
    ]
    if not tiles_dir.is_dir():
        missing.append(str(tiles_dir))
    assert not missing, (
        f"{run_dir.name}: incomplete S3a bundle, missing files: {missing}"
    )

    bundle = {name: load_json(path) for name, path in required_json.items()}

    step_rows: list[dict] = []
    with steps_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"{run_dir.name}: s3_steps.jsonl line {line_no} is not "
                    f"valid JSON: {exc}"
                ) from exc
            assert isinstance(row, dict), (
                f"{run_dir.name}: s3_steps.jsonl line {line_no} must be an object"
            )
            step_rows.append(row)
    bundle["steps"] = step_rows
    bundle["tiles_dir"] = tiles_dir
    bundle["run_dir"] = run_dir

    views = bundle["views"].get("views")
    assert isinstance(views, list), (
        f"{run_dir.name}: s3_views.json 'views' must be a list"
    )
    assert all(isinstance(v, dict) for v in views), (
        f"{run_dir.name}: s3_views.json views entries must be objects"
    )
    bundle["view_ids"] = [v.get("view_id") for v in views]

    faces = bundle["faces"].get("faces")
    assert isinstance(faces, list), (
        f"{run_dir.name}: s2_faces.json 'faces' must be a list"
    )
    bundle["face_ids"] = {
        f.get("face_id") for f in faces if isinstance(f, dict)
    }
    _BUNDLE_CACHE[run_dir] = bundle
    return bundle


class S3aBundleReferenceIntegrityTest(unittest.TestCase):
    """Strict reference-integrity validation for every discovered S3a run."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle_root = resolve_bundle_root()
        cls.run_dirs = discover_run_dirs(cls.bundle_root)
        # A run participates once ANY S3a file exists; partial S3a sets then
        # fail inside load_s3a_bundle. Runs with no S3a file are S1/S2-only.
        cls.s3a_run_dirs = [d for d in cls.run_dirs if run_has_any_s3a(d)]
        cls.s3_config = load_s3_config()
        cls.tile_max_px = effective_tile_max_px(cls.s3_config)
        cls.real_view_lo, cls.real_view_hi = real_view_bounds(cls.s3_config)

    def setUp(self) -> None:
        if not self.run_dirs:
            self.skipTest(
                "S1 verify bundle not generated yet: no runs/<name>/ found under "
                f"env {BUNDLE_ENV}, {ARTIFACT_ROOT_ENV}/{BUNDLE_RELPATH}, or defaults "
                f"{[str(p) for p in DEFAULT_BUNDLE_ROOTS]}"
            )
        if not self.s3a_run_dirs:
            self.skipTest(
                "S3a bundle files not generated yet in any run (S1/S2-only "
                f"bundles are allowed): looked for {list(S3A_FILE_NAMES)} and "
                f"{S3A_TILES_DIRNAME}/ in {[d.name for d in self.run_dirs]}"
            )

    def for_each_s3a_run(self, check) -> None:
        """Run one check per discovered S3a run inside a subTest scope."""
        for run_dir in self.s3a_run_dirs:
            with self.subTest(run=run_dir.name):
                check(run_dir.name, load_s3a_bundle(run_dir))

    # ------------------------------------------------------ 1. manifest s3_def

    def test_manifest_s3a_contract_fields(self) -> None:
        self.for_each_s3a_run(self._check_manifest_s3a_contract_fields)

    def _check_manifest_s3a_contract_fields(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        self.assertIn(
            manifest.get("stage"), S3A_ALLOWED_STAGES,
            f"{name}: manifest stage must be one of {S3A_ALLOWED_STAGES} "
            "once S3a files exist",
        )
        self.assertIsNone(
            manifest.get("scientific_verdict"),
            f"{name}: scientific_verdict must stay null",
        )
        self.assertIs(
            manifest.get("not_official"), True,
            f"{name}: not_official must stay true",
        )
        if "s3_schema" in manifest:
            self.assertEqual(
                manifest["s3_schema"], S3A_SCHEMA,
                f"{name}: s3_schema, when present, must be {S3A_SCHEMA!r}",
            )

        s3_def = manifest.get("s3_def")
        self.assertIsInstance(
            s3_def, dict, f"{name}: manifest missing s3_def object"
        )
        for key in S3_DEF_REQUIRED_KEYS:
            self.assertIn(key, s3_def, f"{name}: s3_def missing key {key!r}")
        self.assertEqual(
            s3_def["stage"], S3_DEF_STAGE,
            f"{name}: s3_def.stage must be {S3_DEF_STAGE!r} (render-only)",
        )
        self.assertIs(
            s3_def["delta_wired"], True,
            f"{name}: s3_def.delta_wired must be true — delta is a render "
            "argument from the start (P0+delta flows into Gaussian "
            "position/orientation), merely frozen at 0 in 3a",
        )
        delta_value = s3_def["delta_value"]
        self.assertTrue(
            vector_ok(delta_value, 3)
            and all(float(v) == 0.0 for v in delta_value),
            f"{name}: s3_def.delta_value must be [0, 0, 0] (delta frozen in "
            f"3a), got {delta_value!r}",
        )
        self.assertEqual(
            s3_def["color"], S3_DEF_COLOR,
            f"{name}: s3_def.color must be {S3_DEF_COLOR!r} (constant color "
            "in 3a)",
        )
        self.assertEqual(
            s3_def["optimizer"], S3_DEF_OPTIMIZER,
            f"{name}: s3_def.optimizer must be {S3_DEF_OPTIMIZER!r} "
            "(0 optimization steps in 3a)",
        )
        self.assertEqual(
            s3_def["renderer"], S3_DEF_RENDERER,
            f"{name}: s3_def.renderer must be {S3_DEF_RENDERER!r} "
            "(repo invariant 6: gsplat, never the official 2DGS fork)",
        )
        n_views = s3_def["n_views"]
        self.assertTrue(
            _positive_int(n_views),
            f"{name}: s3_def.n_views must be a positive integer, got {n_views!r}",
        )
        self.assertEqual(
            n_views, len(bundle["views"]["views"]),
            f"{name}: s3_def.n_views={n_views} != len(s3_views.json views)="
            f"{len(bundle['views']['views'])}",
        )

    # ---------------------------------------------------------- 2. s3_views

    def test_views_reference_integrity(self) -> None:
        self.for_each_s3a_run(self._check_views_reference_integrity)

    def _check_views_reference_integrity(self, name: str, bundle: dict) -> None:
        views_doc = bundle["views"]
        views = views_doc["views"]
        view_ids = bundle["view_ids"]

        selection_rule = views_doc.get("selection_rule")
        self.assertTrue(
            isinstance(selection_rule, str) and selection_rule.strip(),
            f"{name}: selection_rule must be a non-empty string naming its "
            f"source (legacy top-view selection / SYNTH x0 path), got "
            f"{selection_rule!r}",
        )

        self.assertEqual(
            len(view_ids), len(set(view_ids)),
            f"{name}: duplicate view_id values: "
            f"{sorted({v for v in view_ids if view_ids.count(v) > 1})}",
        )

        for view in views:
            vid = view.get("view_id")
            for key in VIEW_REQUIRED_KEYS:
                self.assertIn(key, view, f"{name}/{vid}: view missing key {key!r}")
            self.assertTrue(
                isinstance(vid, str) and vid.strip(),
                f"{name}: view_id must be a non-empty string, got {vid!r}",
            )
            image_ref = view["image_ref"]
            self.assertTrue(
                isinstance(image_ref, str) and image_ref.strip(),
                f"{name}/{vid}: image_ref must be a non-empty original "
                f"path/identifier, got {image_ref!r}",
            )
            for key in ("width", "height"):
                self.assertTrue(
                    _positive_int(view[key]),
                    f"{name}/{vid}: {key} must be a positive integer, "
                    f"got {view[key]!r}",
                )
            if "px_per_m" in view and view["px_per_m"] is not None:
                self.assertTrue(
                    is_finite_number(view["px_per_m"]) and view["px_per_m"] > 0,
                    f"{name}/{vid}: px_per_m, when present, must be a positive "
                    f"finite number, got {view['px_per_m']!r}",
                )

            # Pose: full K/R/t OR an explicit colmap reference.
            has_any_krt = any(key in view for key in ("K", "R", "t"))
            colmap_ref = view.get("colmap")
            has_colmap = (
                isinstance(colmap_ref, str) and bool(colmap_ref.strip())
            ) or (isinstance(colmap_ref, dict) and bool(colmap_ref))
            self.assertTrue(
                has_any_krt or has_colmap,
                f"{name}/{vid}: view needs K/R/t or a non-empty 'colmap' "
                "reference",
            )
            if has_any_krt:
                self.assertTrue(
                    matrix_ok(view.get("K"), 3, 3),
                    f"{name}/{vid}: K must be a numeric 3x3 nested list",
                )
                self.assertTrue(
                    matrix_ok(view.get("R"), 3, 3),
                    f"{name}/{vid}: R must be a numeric 3x3 nested list",
                )
                self.assertTrue(
                    vector_ok(view.get("t"), 3),
                    f"{name}/{vid}: t must be a numeric length-3 list",
                )

        # View-count bounds: config s3.n_views is a CAP, not an exact count —
        # the selection rule may qualify fewer views (e.g. B173 -> 10). Real
        # runs must stay within the contract floor [8, ...] and the cap;
        # SYNTH reuses the x0 path and only needs >= 1 view.
        dataset = bundle["manifest"].get("dataset")
        kind = dataset.get("kind") if isinstance(dataset, dict) else None
        if kind == "real":
            self.assertTrue(
                REAL_N_VIEWS_MIN <= len(views) <= self.real_view_hi,
                f"{name}: real run must carry between {REAL_N_VIEWS_MIN} and "
                f"{self.real_view_hi} views (contract floor {REAL_N_VIEWS_MIN}, "
                f"cap = config s3.n_views within [{REAL_N_VIEWS_MIN}, "
                f"{REAL_N_VIEWS_MAX}]), got {len(views)}",
            )
        else:
            self.assertGreaterEqual(
                len(views), 1, f"{name}: at least one view is required"
            )

    # ---------------------------------------------------------- 3. s3_steps

    def test_steps_step0_wiring_row(self) -> None:
        self.for_each_s3a_run(self._check_steps_step0_wiring_row)

    def _check_steps_step0_wiring_row(self, name: str, bundle: dict) -> None:
        steps = bundle["steps"]
        manifest = bundle["manifest"]
        self.assertTrue(steps, f"{name}: s3_steps.jsonl carries no rows")

        rows_3a = [row for row in steps if row.get("stage") == S3_DEF_STAGE]
        self.assertEqual(
            len(rows_3a), 1,
            f"{name}: exactly one stage-'3a' row expected (render-only, "
            f"step 0), got {len(rows_3a)}",
        )
        row = rows_3a[0]
        for key in STEP_REQUIRED_KEYS:
            self.assertIn(key, row, f"{name}: 3a step row missing key {key!r}")
        self.assertTrue(
            isinstance(row["step"], int)
            and not isinstance(row["step"], bool)
            and row["step"] == 0,
            f"{name}: 3a row must have step: 0, got {row['step']!r}",
        )

        losses = row["losses"]
        self.assertIsInstance(losses, dict, f"{name}: losses must be an object")
        for key in LOSS_REQUIRED_KEYS:
            self.assertIn(key, losses, f"{name}: losses missing key {key!r}")
        for key, value in losses.items():
            self.assertTrue(
                is_finite_number(value),
                f"{name}: losses.{key} must be a finite number, got {value!r}",
            )
        self.assertGreaterEqual(
            float(losses["total"]), 0.0,
            f"{name}: losses.total must be >= 0",
        )

        grads = row["grad_norms"]
        self.assertIsInstance(grads, dict, f"{name}: grad_norms must be an object")
        for key in GRAD_NORM_KEYS:
            self.assertIn(
                key, grads,
                f"{name}: grad_norms missing group {key!r} (the single "
                "backward pass must prove the photometric residual reaches "
                "delta, planes and colors)",
            )
            value = grads[key]
            self.assertTrue(
                is_finite_number(value) and float(value) >= 0.0,
                f"{name}: grad_norms.{key} must be a finite non-negative "
                f"number, got {value!r}",
            )

        delta_hat = row["delta_hat"]
        self.assertTrue(
            vector_ok(delta_hat, 3) and all(float(v) == 0.0 for v in delta_hat),
            f"{name}: delta_hat must be [0, 0, 0] (delta frozen at 0 in 3a), "
            f"got {delta_hat!r}",
        )

        invariants = row["invariants"]
        self.assertIsInstance(
            invariants, dict, f"{name}: invariants must be an object"
        )
        for key in INVARIANTS_REQUIRED_KEYS:
            self.assertIn(key, invariants, f"{name}: invariants missing {key!r}")
        n_seeds = invariants["n_seeds"]
        counts = manifest.get("counts", {})
        expected_seeds = counts.get("seeds") if isinstance(counts, dict) else None
        self.assertTrue(
            isinstance(n_seeds, int) and not isinstance(n_seeds, bool),
            f"{name}: invariants.n_seeds must be an integer, got {n_seeds!r}",
        )
        self.assertEqual(
            n_seeds, expected_seeds,
            f"{name}: invariants.n_seeds={n_seeds!r} != manifest counts.seeds="
            f"{expected_seeds!r} (lifetime rule (1): no densification/pruning)",
        )
        self.assertIs(
            invariants["alpha_binary"], True,
            f"{name}: invariants.alpha_binary must be true (alpha_g = "
            "|o_state_a - o_state_b| is a derived quantity, never a free "
            "learned alpha)",
        )
        self.assertIs(
            invariants["delta_frozen"], True,
            f"{name}: invariants.delta_frozen must be true in 3a",
        )

        param_step_norm = row["param_step_norm"]
        self.assertTrue(
            is_number(param_step_norm) and float(param_step_norm) == 0.0,
            f"{name}: param_step_norm must be 0 (backward pass only, no "
            f"weight update), got {param_step_norm!r}",
        )

        views_psnr = row["views_psnr"]
        self.assertIsInstance(
            views_psnr, dict, f"{name}: views_psnr must be an object"
        )
        id_set = set(bundle["view_ids"])
        unknown = sorted(set(views_psnr) - id_set)
        self.assertFalse(
            unknown,
            f"{name}: views_psnr keys must be a subset of the s3_views "
            f"view_id set; unknown keys {unknown}",
        )
        for vid, value in views_psnr.items():
            self.assertTrue(
                is_number(value) and not math.isnan(float(value)),
                f"{name}: views_psnr[{vid!r}] must be a numeric PSNR, "
                f"got {value!r}",
            )

    # ---------------------------------------------------------- 4. s3_tiles

    def test_tiles_triplets(self) -> None:
        self.for_each_s3a_run(self._check_tiles_triplets)

    def _check_tiles_triplets(self, name: str, bundle: dict) -> None:
        tiles_dir = bundle["tiles_dir"]
        id_set = set(bundle["view_ids"])
        dir_set = {
            p.name
            for p in tiles_dir.iterdir()
            if p.is_dir() and not STEP_SNAPSHOT_DIR_RE.match(p.name)
        }
        missing = sorted(v for v in id_set if v not in dir_set)
        extra = sorted(dir_set - id_set)
        self.assertFalse(
            missing, f"{name}: s3_tiles/ missing view directories {missing}"
        )
        self.assertFalse(
            extra,
            f"{name}: s3_tiles/ has directories for unknown view_ids {extra}",
        )
        for vid in sorted(v for v in id_set if isinstance(v, str)):
            view_dir = tiles_dir / vid
            for tile_name in TILE_FILE_NAMES:
                tile_path = view_dir / tile_name
                self.assertTrue(
                    tile_path.is_file(),
                    f"{name}/{vid}: missing tile {tile_name}",
                )
                width, height, size = read_png_meta(tile_path)
                self.assertGreater(
                    size, TILE_MIN_BYTES,
                    f"{name}/{vid}/{tile_name}: tile must be non-empty "
                    f"(> {TILE_MIN_BYTES} bytes), got {size}",
                )
                self.assertTrue(
                    width >= 1 and height >= 1,
                    f"{name}/{vid}/{tile_name}: degenerate PNG size "
                    f"{width}x{height}",
                )
                self.assertLessEqual(
                    max(width, height), self.tile_max_px,
                    f"{name}/{vid}/{tile_name}: long side {max(width, height)} "
                    f"exceeds tile_max_px {self.tile_max_px} (contract hard "
                    f"bound {TILE_MAX_PX_CONTRACT})",
                )

    # -------------------------------------------------- 5. s3_face_residual

    def test_face_residual_reference_integrity(self) -> None:
        self.for_each_s3a_run(self._check_face_residual_reference_integrity)

    def _check_face_residual_reference_integrity(
        self, name: str, bundle: dict
    ) -> None:
        doc = bundle["face_residual"]
        method = doc.get("method")
        self.assertTrue(
            isinstance(method, str) and method.strip(),
            f"{name}: s3_face_residual.json method must be a non-empty string "
            "naming the approximation (e.g. face-polygon projection mean, "
            f"occlusion handling yes/no), got {method!r}",
        )
        per_face = doc.get("per_face")
        self.assertIsInstance(
            per_face, dict, f"{name}: per_face must be an object"
        )
        face_ids = bundle["face_ids"]
        unknown = sorted(set(per_face) - face_ids)
        self.assertFalse(
            unknown,
            f"{name}: per_face keys must all exist in s2_faces; unknown "
            f"face_ids {unknown[:20]}"
            + (" (truncated)" if len(unknown) > 20 else ""),
        )
        # null = "no visible samples" (writer's stated approximation limit for
        # some gate-0 faces) — an honest gap, not a defect. Numbers must be
        # finite and non-negative; at least one face must carry a number.
        numeric = 0
        for fid, value in per_face.items():
            if value is None:
                continue
            numeric += 1
            self.assertTrue(
                is_finite_number(value) and float(value) >= 0.0,
                f"{name}/{fid}: per_face residual must be a finite "
                f"non-negative number or null (no samples), got {value!r}",
            )
        self.assertGreater(
            numeric, 0, f"{name}: per_face must contain at least one sampled value"
        )


if __name__ == "__main__":
    unittest.main()
