"""Reference-integrity tests for the S3b verify-page bundle contract.

Contract: ``phd_s3_verify_s3b_v1`` (S3 redesign verification pages, third
stage, internal step 3b "color-only training": geometry frozen, warm-up).
S3b files are appended to an existing S1+S2+S3a bundle in the same
``runs/<name>/`` directory. Basis: plan document revision note 2026-08-27
(commit 64664b98 — variable-group staged unfreezing 3a -> 3b -> 3c -> 3d)
plus the 3a implementation (commit f4af886b; render_state.py is the reuse
base).

Bundle root resolution follows tests.phd.test_s3_verify_s1_bundle exactly
(env ``JBGS_S3_VERIFY_ROOT`` -> ``JBGS_ARTIFACT_ROOT`` -> container default
-> host default).

Skip policy (mirrors the S3a module):
- no bundle root / no runs at all -> every test skips (bundle not generated);
- a run with NONE of the S3b markers is an S1/S2/S3a-only bundle -> skipped;
- a run with SOME S3b markers but an incomplete S3b set is a corrupt
  partial bundle -> failure.

Training definition (the single truth — violations are contract failures):
- The ONLY trained variable group is color A_g. Planes P, delta, occupancy o
  and the seed geometry stay frozen at the byte level; the writer asserts and
  records this as ``s3b_def.frozen_checksum_ok: true`` and every 3b step row
  must carry ``param_step_norms.delta == 0`` and ``param_step_norms.planes
  == 0`` (weight updates applied to colors only).
- No densification/pruning ever; alpha_g = |delta o| stays a DERIVED binary
  quantity (never a free learned alpha) -> every 3b row asserts
  ``invariants.alpha_binary/delta_frozen/planes_frozen: true`` and
  ``invariants.n_seeds == manifest counts.seeds``.
- The loss keeps the 3a channels (photo L1 + anchor/area constants recorded).
  backward flows through ALL leaves, so the gradient norms of the frozen
  groups are recorded too (observation: how geometry pressure evolves while
  color converges) -> ``grad_norms`` for delta/planes/colors must exist,
  finite and non-negative in every 3b row, even though only colors update.
- Steps/lr/optimizer come from the legacy arrgs_train color-training
  constants registered in the writer-owned config ``s3.b`` block (steps
  default 300, checkpoints ~6: 0 + log-spaced + final). When that block is
  present, the manifest ``s3b_def`` must agree with it.

Appended/updated files in ``runs/<name>/``:
- ``s3_steps.jsonl``: 3b rows APPENDED — the single 3a row (stage "3a",
  step 0) is preserved; checkpoint rows additionally carry ``views_psnr``
  and ``color_stats``.
- ``s3_tiles/s<step>/<view_id>/{render.png, residual.png}``: checkpoint
  steps only (photo.png is reused from the 3a per-view tiles; the viewer
  references it).
- ``s3_face_residual_final.json``: same approximation and null convention
  as the 3a ``s3_face_residual.json`` (null = no visible samples).
- ``manifest.json``: stage advances to ``"s1+s2+s3a+s3b"`` and gains the
  ``s3b_def`` block.

Weak-monotonicity check: the median PSNR of the FINAL checkpoint row must
exceed the median PSNR of the 3a step-0 row (did color training actually
improve the render?).

``scientific_verdict`` stays null and ``not_official`` stays true.
"""

from __future__ import annotations

import math
import re
import statistics
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
    from tests.phd.test_s3_verify_s3a_bundle import (
        GRAD_NORM_KEYS,
        LOSS_REQUIRED_KEYS,
        S3_DEF_STAGE,
        TILE_MIN_BYTES,
        _positive_int,
        effective_tile_max_px,
        is_finite_number,
        load_s3_config,
        load_s3a_bundle,
        read_png_meta,
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
    from tests.phd.test_s3_verify_s3a_bundle import (
        GRAD_NORM_KEYS,
        LOSS_REQUIRED_KEYS,
        S3_DEF_STAGE,
        TILE_MIN_BYTES,
        _positive_int,
        effective_tile_max_px,
        is_finite_number,
        load_s3_config,
        load_s3a_bundle,
        read_png_meta,
    )

S3B_SCHEMA = "phd_s3_verify_s3b_v1"
STAGE_S1S2S3AS3B = "s1+s2+s3a+s3b"
S3B_STAGE = "3b"

FINAL_RESIDUAL_NAME = "s3_face_residual_final.json"
S3B_TILES_DIRNAME = "s3_tiles"
STEP_DIR_RE = re.compile(r"^s(\d+)$")
STEP_TILE_FILE_NAMES = ("render.png", "residual.png")

S3B_DEF_REQUIRED_KEYS = (
    "steps",
    "lr",
    "optimizer",
    "trained",
    "checkpoints",
    "frozen_checksum_ok",
)
S3B_TRAINED = ["colors"]

STEP3B_REQUIRED_KEYS = (
    "step",
    "stage",
    "losses",
    "grad_norms",
    "param_step_norms",
    "invariants",
)
PARAM_STEP_NORM_KEYS = GRAD_NORM_KEYS  # ("delta", "planes", "colors")
INVARIANTS_3B_REQUIRED_KEYS = (
    "n_seeds",
    "alpha_binary",
    "delta_frozen",
    "planes_frozen",
)
CHECKPOINT_ONLY_KEYS = ("views_psnr", "color_stats")
COLOR_STATS_REQUIRED_KEYS = ("mean_saturation", "color_var")

# Writer-owned config s3.b block (legacy arrgs_train color constants
# registered once in configs/phd/s3_verify_v1/s1_bundle_v1.json), when
# present, must agree with the manifest s3b_def:
# - steps / checkpoints: exact equality;
# - lr: config key "lr" or legacy-named "lr_rgb" (arrgs_train lr.rgb),
#   numeric equality;
# - optimizer: the manifest string may elaborate (e.g. "adam (torch.optim.
#   Adam, ...)"), so it must START WITH the config constant (e.g. "adam").
CONFIG_B_EXACT_KEYS = ("steps", "checkpoints")
LR_RTOL = 1e-9


def _plain_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_s3b_config() -> dict:
    """Return the writer-owned ``s3.b`` block of the bundle config, or {}."""
    block = load_s3_config().get("b")
    return block if isinstance(block, dict) else {}


def run_has_any_s3b(run_dir: Path) -> bool:
    """True once ANY S3b marker exists (partial sets then fail loudly)."""
    if (run_dir / FINAL_RESIDUAL_NAME).is_file():
        return True
    tiles_dir = run_dir / S3B_TILES_DIRNAME
    if tiles_dir.is_dir() and any(
        p.is_dir() and STEP_DIR_RE.match(p.name) for p in tiles_dir.iterdir()
    ):
        return True
    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
        except (OSError, ValueError):
            return False
        if isinstance(manifest, dict) and (
            manifest.get("stage") == STAGE_S1S2S3AS3B or "s3b_def" in manifest
        ):
            return True
    return False


_BUNDLE_CACHE: dict[Path, dict] = {}


def load_s3b_bundle(run_dir: Path) -> dict:
    """Load and cache one run's S3b view of the bundle.

    An S3b run is a superset of an S3a run (the 3a files are preserved), so
    the S3a loader is reused for manifest/faces/views/steps/tiles and only
    the S3b-specific final face residual is added. Missing files raise
    AssertionError (corrupt partial bundle).
    """
    cached = _BUNDLE_CACHE.get(run_dir)
    if cached is not None:
        return cached
    bundle = dict(load_s3a_bundle(run_dir))
    final_path = run_dir / FINAL_RESIDUAL_NAME
    assert final_path.is_file(), (
        f"{run_dir.name}: incomplete S3b bundle, missing {FINAL_RESIDUAL_NAME}"
    )
    bundle["face_residual_final"] = load_json(final_path)
    bundle["rows_3b"] = [
        row for row in bundle["steps"] if row.get("stage") == S3B_STAGE
    ]
    _BUNDLE_CACHE[run_dir] = bundle
    return bundle


def get_s3b_def(name: str, bundle: dict) -> dict:
    """The manifest s3b_def with the minimum shape other checks depend on."""
    s3b_def = bundle["manifest"].get("s3b_def")
    assert isinstance(s3b_def, dict), (
        f"{name}: manifest missing s3b_def object (corrupt partial S3b bundle)"
    )
    assert _positive_int(s3b_def.get("steps")), (
        f"{name}: s3b_def.steps must be a positive integer, "
        f"got {s3b_def.get('steps')!r}"
    )
    checkpoints = s3b_def.get("checkpoints")
    assert (
        isinstance(checkpoints, list)
        and checkpoints
        and all(_plain_int(c) for c in checkpoints)
    ), (
        f"{name}: s3b_def.checkpoints must be a non-empty list of integers, "
        f"got {checkpoints!r}"
    )
    return s3b_def


def psnr_median(values: dict) -> float:
    return float(statistics.median(float(v) for v in values.values()))


class S3bBundleReferenceIntegrityTest(unittest.TestCase):
    """Strict reference-integrity validation for every discovered S3b run."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle_root = resolve_bundle_root()
        cls.run_dirs = discover_run_dirs(cls.bundle_root)
        # A run participates once ANY S3b marker exists; partial S3b sets
        # then fail inside load_s3b_bundle / the checks. Runs with no S3b
        # marker are S1/S2/S3a-only and are skipped.
        cls.s3b_run_dirs = [d for d in cls.run_dirs if run_has_any_s3b(d)]
        cls.s3b_config = load_s3b_config()
        cls.tile_max_px = effective_tile_max_px(load_s3_config())

    def setUp(self) -> None:
        if not self.run_dirs:
            self.skipTest(
                "S1 verify bundle not generated yet: no runs/<name>/ found under "
                f"env {BUNDLE_ENV}, {ARTIFACT_ROOT_ENV}/{BUNDLE_RELPATH}, or defaults "
                f"{[str(p) for p in DEFAULT_BUNDLE_ROOTS]}"
            )
        if not self.s3b_run_dirs:
            self.skipTest(
                "S3b bundle files not generated yet in any run (S1/S2/S3a-only "
                f"bundles are allowed): looked for {FINAL_RESIDUAL_NAME}, "
                f"{S3B_TILES_DIRNAME}/s<step>/, or a manifest stage/"
                f"s3b_def marker in {[d.name for d in self.run_dirs]}"
            )

    def for_each_s3b_run(self, check) -> None:
        """Run one check per discovered S3b run inside a subTest scope."""
        for run_dir in self.s3b_run_dirs:
            with self.subTest(run=run_dir.name):
                check(run_dir.name, load_s3b_bundle(run_dir))

    # ----------------------------------------------------- 1. manifest s3b_def

    def test_manifest_s3b_contract_fields(self) -> None:
        self.for_each_s3b_run(self._check_manifest_s3b_contract_fields)

    def _check_manifest_s3b_contract_fields(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        self.assertEqual(
            manifest.get("stage"), STAGE_S1S2S3AS3B,
            f"{name}: manifest stage must be {STAGE_S1S2S3AS3B!r} once S3b "
            "files exist (not 's1+s2+s3b' — the 3a guarantees stay in force)",
        )
        self.assertIsNone(
            manifest.get("scientific_verdict"),
            f"{name}: scientific_verdict must stay null",
        )
        self.assertIs(
            manifest.get("not_official"), True,
            f"{name}: not_official must stay true",
        )
        if "s3b_schema" in manifest:
            self.assertEqual(
                manifest["s3b_schema"], S3B_SCHEMA,
                f"{name}: s3b_schema, when present, must be {S3B_SCHEMA!r}",
            )

        s3b_def = manifest.get("s3b_def")
        self.assertIsInstance(
            s3b_def, dict, f"{name}: manifest missing s3b_def object"
        )
        for key in S3B_DEF_REQUIRED_KEYS:
            self.assertIn(key, s3b_def, f"{name}: s3b_def missing key {key!r}")

        steps = s3b_def["steps"]
        self.assertTrue(
            _positive_int(steps),
            f"{name}: s3b_def.steps must be a positive integer, got {steps!r}",
        )
        self.assertTrue(
            is_finite_number(s3b_def["lr"]) and float(s3b_def["lr"]) > 0.0,
            f"{name}: s3b_def.lr must be a positive finite number, "
            f"got {s3b_def['lr']!r}",
        )
        optimizer = s3b_def["optimizer"]
        self.assertTrue(
            isinstance(optimizer, str) and optimizer.strip(),
            f"{name}: s3b_def.optimizer must be a non-empty string (legacy "
            f"arrgs_train color optimizer), got {optimizer!r}",
        )
        self.assertEqual(
            s3b_def["trained"], S3B_TRAINED,
            f"{name}: s3b_def.trained must be exactly {S3B_TRAINED!r} — 3b "
            "trains color A_g ONLY; planes/delta/occupancy/seed geometry "
            f"stay frozen, got {s3b_def['trained']!r}",
        )
        self.assertIs(
            s3b_def["frozen_checksum_ok"], True,
            f"{name}: s3b_def.frozen_checksum_ok must be true — the writer "
            "must assert byte-level invariance of the frozen groups across "
            "the whole run",
        )

        checkpoints = s3b_def["checkpoints"]
        self.assertTrue(
            isinstance(checkpoints, list) and checkpoints,
            f"{name}: s3b_def.checkpoints must be a non-empty list, "
            f"got {checkpoints!r}",
        )
        self.assertTrue(
            all(_plain_int(c) for c in checkpoints),
            f"{name}: s3b_def.checkpoints entries must be integers, "
            f"got {checkpoints!r}",
        )
        self.assertEqual(
            checkpoints, sorted(set(checkpoints)),
            f"{name}: s3b_def.checkpoints must be strictly increasing without "
            f"duplicates, got {checkpoints!r}",
        )
        self.assertTrue(
            all(0 <= c <= steps for c in checkpoints),
            f"{name}: s3b_def.checkpoints must lie within [0, steps={steps}], "
            f"got {checkpoints!r}",
        )
        self.assertIn(
            0, checkpoints,
            f"{name}: s3b_def.checkpoints must include 0 (pre-training state)",
        )
        self.assertIn(
            steps, checkpoints,
            f"{name}: s3b_def.checkpoints must include the final step "
            f"{steps}, got {checkpoints!r}",
        )

        # Writer-owned config s3.b block, when registered, is the constant
        # source (legacy arrgs_train color constants); the manifest must not
        # silently diverge from it.
        for key in CONFIG_B_EXACT_KEYS:
            if key in self.s3b_config:
                self.assertEqual(
                    s3b_def[key], self.s3b_config[key],
                    f"{name}: s3b_def.{key}={s3b_def[key]!r} diverges from "
                    f"config s3.b.{key}={self.s3b_config[key]!r}",
                )
        config_lr = self.s3b_config.get("lr", self.s3b_config.get("lr_rgb"))
        if is_number(config_lr):
            self.assertTrue(
                math.isclose(float(s3b_def["lr"]), float(config_lr),
                             rel_tol=LR_RTOL),
                f"{name}: s3b_def.lr={s3b_def['lr']!r} diverges from config "
                f"s3.b lr/lr_rgb={config_lr!r}",
            )
        config_opt = self.s3b_config.get("optimizer")
        if isinstance(config_opt, str) and config_opt.strip():
            self.assertTrue(
                optimizer.startswith(config_opt),
                f"{name}: s3b_def.optimizer={optimizer!r} must start with "
                f"the config s3.b.optimizer constant {config_opt!r}",
            )

    # ------------------------------------------------------------ 2. s3_steps

    def test_steps_3b_rows(self) -> None:
        self.for_each_s3b_run(self._check_steps_3b_rows)

    def _check_steps_3b_rows(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        s3b_def = get_s3b_def(name, bundle)
        total_steps = s3b_def["steps"]
        checkpoints = set(s3b_def["checkpoints"])

        # The 3a wiring row (stage "3a", step 0) must be PRESERVED — 3b rows
        # are appended, never rewritten over the 3a record.
        rows_3a = [
            row for row in bundle["steps"] if row.get("stage") == S3_DEF_STAGE
        ]
        self.assertEqual(
            len(rows_3a), 1,
            f"{name}: exactly one preserved stage-'3a' row expected in "
            f"s3_steps.jsonl (3b appends rows), got {len(rows_3a)}",
        )
        self.assertEqual(
            rows_3a[0].get("step"), 0,
            f"{name}: the preserved 3a row must have step 0, "
            f"got {rows_3a[0].get('step')!r}",
        )

        rows_3b = bundle["rows_3b"]
        self.assertTrue(
            rows_3b, f"{name}: s3_steps.jsonl carries no stage-'3b' rows"
        )

        counts = manifest.get("counts", {})
        expected_seeds = counts.get("seeds") if isinstance(counts, dict) else None

        step_values: list[int] = []
        rows_with_color_movement = 0
        for row in rows_3b:
            step = row.get("step")
            label = f"{name}/3b step {step!r}"
            for key in STEP3B_REQUIRED_KEYS:
                self.assertIn(key, row, f"{label}: row missing key {key!r}")
            self.assertTrue(
                _plain_int(step) and 0 <= step <= total_steps,
                f"{label}: step must be an integer within "
                f"[0, s3b_def.steps={total_steps}]",
            )
            step_values.append(step)

            losses = row["losses"]
            self.assertIsInstance(
                losses, dict, f"{label}: losses must be an object"
            )
            for key in LOSS_REQUIRED_KEYS:
                self.assertIn(
                    key, losses,
                    f"{label}: losses missing key {key!r} (3b keeps the 3a "
                    "loss channels: photo L1 + anchor/area constants)",
                )
            for key, value in losses.items():
                self.assertTrue(
                    is_finite_number(value),
                    f"{label}: losses.{key} must be a finite number, "
                    f"got {value!r}",
                )
            self.assertGreaterEqual(
                float(losses["total"]), 0.0,
                f"{label}: losses.total must be >= 0",
            )

            grads = row["grad_norms"]
            self.assertIsInstance(
                grads, dict, f"{label}: grad_norms must be an object"
            )
            for key in GRAD_NORM_KEYS:
                self.assertIn(
                    key, grads,
                    f"{label}: grad_norms missing group {key!r} — backward "
                    "flows through all leaves so the FROZEN groups' gradient "
                    "norms are recorded too (geometry-pressure observation)",
                )
                value = grads[key]
                self.assertTrue(
                    is_finite_number(value) and float(value) >= 0.0,
                    f"{label}: grad_norms.{key} must be a finite non-negative "
                    f"number, got {value!r}",
                )

            norms = row["param_step_norms"]
            self.assertIsInstance(
                norms, dict, f"{label}: param_step_norms must be an object"
            )
            for key in PARAM_STEP_NORM_KEYS:
                self.assertIn(
                    key, norms, f"{label}: param_step_norms missing {key!r}"
                )
            for key in ("delta", "planes"):
                value = norms[key]
                self.assertTrue(
                    is_number(value) and float(value) == 0.0,
                    f"{label}: param_step_norms.{key} must be exactly 0 — "
                    f"the {key} group is FROZEN in 3b (color-only training), "
                    f"got {value!r}",
                )
            colors_norm = norms["colors"]
            self.assertTrue(
                is_finite_number(colors_norm) and float(colors_norm) >= 0.0,
                f"{label}: param_step_norms.colors must be a finite "
                f"non-negative number, got {colors_norm!r}",
            )
            if float(colors_norm) > 0.0:
                rows_with_color_movement += 1

            invariants = row["invariants"]
            self.assertIsInstance(
                invariants, dict, f"{label}: invariants must be an object"
            )
            for key in INVARIANTS_3B_REQUIRED_KEYS:
                self.assertIn(
                    key, invariants, f"{label}: invariants missing {key!r}"
                )
            for key in ("delta_frozen", "planes_frozen", "alpha_binary"):
                self.assertIs(
                    invariants[key], True,
                    f"{label}: invariants.{key} must be true (geometry "
                    "frozen; alpha_g = |delta o| stays derived, never a free "
                    "learned alpha)",
                )
            self.assertEqual(
                invariants["n_seeds"], expected_seeds,
                f"{label}: invariants.n_seeds={invariants['n_seeds']!r} != "
                f"manifest counts.seeds={expected_seeds!r} (no "
                "densification/pruning ever)",
            )

            # Checkpoint-only payload: views_psnr / color_stats appear on
            # checkpoint rows and only there.
            is_checkpoint = step in checkpoints
            for key in CHECKPOINT_ONLY_KEYS:
                if is_checkpoint:
                    self.assertIn(
                        key, row,
                        f"{label}: checkpoint row missing {key!r}",
                    )
                else:
                    self.assertNotIn(
                        key, row,
                        f"{label}: {key!r} is a checkpoint-only field but "
                        "the step is not in s3b_def.checkpoints",
                    )

        self.assertEqual(
            step_values, sorted(set(step_values)),
            f"{name}: 3b row steps must be strictly increasing, "
            f"got {step_values[:20]}...",
        )
        self.assertEqual(
            step_values[-1], total_steps,
            f"{name}: last 3b row step {step_values[-1]} != s3b_def.steps="
            f"{total_steps} (the run must reach its declared step count)",
        )
        missing_checkpoints = sorted(checkpoints - set(step_values))
        self.assertFalse(
            missing_checkpoints,
            f"{name}: s3b_def.checkpoints without a 3b step row: "
            f"{missing_checkpoints}",
        )
        self.assertGreaterEqual(
            rows_with_color_movement, 1,
            f"{name}: param_step_norms.colors must be > 0 in at least one 3b "
            "row (color training must actually move the color parameters)",
        )

    # ----------------------------------------------- 3. checkpoint rows / PSNR

    def test_checkpoint_rows_psnr_and_color_stats(self) -> None:
        self.for_each_s3b_run(self._check_checkpoint_rows_psnr_and_color_stats)

    def _check_checkpoint_rows_psnr_and_color_stats(
        self, name: str, bundle: dict
    ) -> None:
        s3b_def = get_s3b_def(name, bundle)
        total_steps = s3b_def["steps"]
        checkpoints = set(s3b_def["checkpoints"])
        id_set = set(bundle["view_ids"])

        final_row = None
        for row in bundle["rows_3b"]:
            step = row.get("step")
            if step not in checkpoints:
                continue
            label = f"{name}/3b step {step!r}"

            views_psnr = row.get("views_psnr")
            self.assertIsInstance(
                views_psnr, dict, f"{label}: views_psnr must be an object"
            )
            unknown = sorted(set(views_psnr) - id_set)
            self.assertFalse(
                unknown,
                f"{label}: views_psnr keys must be a subset of the s3_views "
                f"view_id set; unknown keys {unknown}",
            )
            for vid, value in views_psnr.items():
                self.assertTrue(
                    is_number(value) and not math.isnan(float(value)),
                    f"{label}: views_psnr[{vid!r}] must be a numeric PSNR, "
                    f"got {value!r}",
                )

            color_stats = row.get("color_stats")
            self.assertIsInstance(
                color_stats, dict, f"{label}: color_stats must be an object"
            )
            for key in COLOR_STATS_REQUIRED_KEYS:
                self.assertIn(
                    key, color_stats, f"{label}: color_stats missing {key!r}"
                )
                value = color_stats[key]
                self.assertTrue(
                    is_finite_number(value) and float(value) >= 0.0,
                    f"{label}: color_stats.{key} must be a finite "
                    f"non-negative number, got {value!r}",
                )

            if step == total_steps:
                final_row = row

        self.assertIsNotNone(
            final_row,
            f"{name}: no checkpoint row at the final step {total_steps}",
        )

        # Weak monotonicity: color-only training must actually improve the
        # render — median PSNR of the FINAL checkpoint must exceed the 3a
        # (step-0, neutral-gray) median PSNR.
        rows_3a = [
            row for row in bundle["steps"] if row.get("stage") == S3_DEF_STAGE
        ]
        self.assertTrue(
            rows_3a, f"{name}: preserved 3a row required for the PSNR baseline"
        )
        psnr_3a = rows_3a[0].get("views_psnr")
        self.assertTrue(
            isinstance(psnr_3a, dict) and psnr_3a,
            f"{name}: 3a row views_psnr must be a non-empty object to serve "
            "as the PSNR baseline",
        )
        psnr_final = final_row["views_psnr"]
        self.assertTrue(
            psnr_final,
            f"{name}: final checkpoint views_psnr must be non-empty",
        )
        median_3a = psnr_median(psnr_3a)
        median_final = psnr_median(psnr_final)
        self.assertGreater(
            median_final, median_3a,
            f"{name}: final-checkpoint median PSNR {median_final:.3f} must "
            f"exceed the 3a step-0 median PSNR {median_3a:.3f} (weak "
            "monotonicity: did color training actually improve the render?)",
        )

    # ------------------------------------------------- 4. s3_tiles/s<step>/

    def test_checkpoint_step_tiles(self) -> None:
        self.for_each_s3b_run(self._check_checkpoint_step_tiles)

    def _check_checkpoint_step_tiles(self, name: str, bundle: dict) -> None:
        s3b_def = get_s3b_def(name, bundle)
        checkpoints = s3b_def["checkpoints"]
        tiles_dir = bundle["tiles_dir"]
        id_set = set(bundle["view_ids"])

        # Step directories (s<step>) must be exactly the checkpoint set; the
        # 3a per-view tile directories live alongside them and are owned by
        # the S3a module.
        step_dirs = {
            int(match.group(1))
            for p in tiles_dir.iterdir()
            if p.is_dir() and (match := STEP_DIR_RE.match(p.name))
        }
        missing_steps = sorted(set(checkpoints) - step_dirs)
        extra_steps = sorted(step_dirs - set(checkpoints))
        self.assertFalse(
            missing_steps,
            f"{name}: s3_tiles/ missing checkpoint step directories "
            f"{[f's{c}' for c in missing_steps]}",
        )
        self.assertFalse(
            extra_steps,
            f"{name}: s3_tiles/ has step directories not in "
            f"s3b_def.checkpoints: {[f's{c}' for c in extra_steps]}",
        )

        for checkpoint in checkpoints:
            step_dir = tiles_dir / f"s{checkpoint}"
            dir_set = {p.name for p in step_dir.iterdir() if p.is_dir()}
            missing = sorted(v for v in id_set if v not in dir_set)
            extra = sorted(dir_set - id_set)
            self.assertFalse(
                missing,
                f"{name}/s{checkpoint}: missing view directories {missing} "
                "(every view gets a render/residual snapshot per checkpoint; "
                "photo.png is reused from the 3a tiles)",
            )
            self.assertFalse(
                extra,
                f"{name}/s{checkpoint}: directories for unknown view_ids "
                f"{extra}",
            )
            for vid in sorted(v for v in id_set if isinstance(v, str)):
                view_dir = step_dir / vid
                for tile_name in STEP_TILE_FILE_NAMES:
                    tile_path = view_dir / tile_name
                    self.assertTrue(
                        tile_path.is_file(),
                        f"{name}/s{checkpoint}/{vid}: missing tile {tile_name}",
                    )
                    width, height, size = read_png_meta(tile_path)
                    self.assertGreater(
                        size, TILE_MIN_BYTES,
                        f"{name}/s{checkpoint}/{vid}/{tile_name}: tile must "
                        f"be non-empty (> {TILE_MIN_BYTES} bytes), got {size}",
                    )
                    self.assertTrue(
                        width >= 1 and height >= 1,
                        f"{name}/s{checkpoint}/{vid}/{tile_name}: degenerate "
                        f"PNG size {width}x{height}",
                    )
                    self.assertLessEqual(
                        max(width, height), self.tile_max_px,
                        f"{name}/s{checkpoint}/{vid}/{tile_name}: long side "
                        f"{max(width, height)} exceeds tile_max_px "
                        f"{self.tile_max_px}",
                    )

    # ------------------------------------------ 5. s3_face_residual_final

    def test_face_residual_final_reference_integrity(self) -> None:
        self.for_each_s3b_run(self._check_face_residual_final)

    def _check_face_residual_final(self, name: str, bundle: dict) -> None:
        s3b_def = get_s3b_def(name, bundle)
        doc = bundle["face_residual_final"]
        self.assertEqual(
            doc.get("step"), s3b_def["steps"],
            f"{name}: {FINAL_RESIDUAL_NAME} step={doc.get('step')!r} must "
            f"equal the final step s3b_def.steps={s3b_def['steps']}",
        )
        method = doc.get("method")
        self.assertTrue(
            isinstance(method, str) and method.strip(),
            f"{name}: {FINAL_RESIDUAL_NAME} method must be a non-empty string "
            "naming the same approximation as the 3a s3_face_residual.json, "
            f"got {method!r}",
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
        # Same null convention as 3a: null = "no visible samples" — an honest
        # gap, not a defect. Numbers must be finite and non-negative; at
        # least one face must carry a number.
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
