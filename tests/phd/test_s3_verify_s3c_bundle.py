"""Reference-integrity tests for the S3c verify-page bundle contract.

Contract: ``phd_s3_verify_s3c_v1`` (S3 redesign verification pages, third
stage, internal step 3c "delta unfreeze": injected-shift restoration check).
S3c files are appended to an existing S1+S2+S3a+S3b bundle in the same
``runs/<name>/`` directory. Basis: plan document revision note 2026-08-27
"3c 착수 등록" (commit e826fcc4), stacked on the 3b contract/implementation
(build_s3b_bundle.py; render_state.py is the reuse base).

Bundle root resolution follows tests.phd.test_s3_verify_s1_bundle exactly
(env ``JBGS_S3_VERIFY_ROOT`` -> ``JBGS_ARTIFACT_ROOT`` -> container default
-> host default).

Skip policy (mirrors the S3b module):
- no bundle root / no runs at all -> every test skips (bundle not generated);
- a run with NONE of the S3c markers is an S1..S3b-only bundle -> skipped;
- a run with SOME S3c markers but an incomplete S3c set is a corrupt
  partial bundle -> failure.

Training definition (the single truth — violations are contract failures):
- Trained variables are EXACTLY delta (ONE global translation vector,
  methodology §1.3 — no rotation) and colors (warm-started from the 3b
  ``s3b_colors.f16.bin`` artifact). Planes P, occupancy o and the seed
  geometry stay frozen (checksum-verified by the writer:
  ``s3c_def.frozen_checksum_ok: true``); no free learned alpha, no
  densification/pruning ever -> every 3c row asserts
  ``invariants.planes_frozen/alpha_binary: true`` and
  ``invariants.n_seeds == manifest counts.seeds`` and
  ``param_step_norms.planes == 0``.
- The OPTIMIZATION OBJECTIVE is the photo channel ONLY
  (``s3c_def.objective: "photo"``). anchor/area/anchor_plane are recorded
  as diagnostics but are NOT backpropagation targets in 3c: delta itself
  has no anchor (§2.2), and the plane-anchor target is P0 (+) delta, so
  with planes frozen an anchor term in the objective would become a
  |delta_hat|-proportional penalty that unfairly suppresses the injected-
  shift restoration (it works normally from 3d on, when planes follow).
  The writer states this rationale in ``s3c_def.objective_note``.
- delta moves only where delta-source planes give it scope:
  ``s3c_def.delta_scope_planes`` (int >= 0). These tests branch on the
  RECORDED scope, never on run names: scope-0 runs (e.g. B036; per config
  ``delta_sources`` SYNTH_GABLE currently carries synthetic-source scope 4,
  not 0) are NEGATIVE controls where delta must not move at all.
- Injection runs (names like ``B022_DZ050``) rebuilt the WHOLE pipeline
  S1->S2->3a->3b->3c from ALS bytes shifted via
  ``scripts/p2/arrgs_v1/xreal_run.py scene_for(bkey, dz=0.5)`` — the honest
  route where the injection flows into the plane statements and o_init
  together. Their manifests carry an ``injection`` block:
  ``delta_applied`` (3-vector, e.g. [0, 0, 0.5]), ``route``,
  ``expected_delta_hat`` (WITH the sign convention — the direction that
  cancels the injection).

Weak-wiring check only: an injected scope>0 run whose final |delta_hat| is
not > 0.05 did not move at all -> wiring defect. Restoration QUALITY
(closeness to the injected truth) is deliberately NOT asserted — that is
the human reading's job, as is the residual drift of the no-change
controls (B022/B173 without injection: delta_hat ~ 0 expected but not
asserted).

Appended/updated files in ``runs/<name>/``:
- ``s3_steps.jsonl``: 3c rows APPENDED — the 3a row and ALL 3b rows are
  preserved; every 3c row carries losses(photo/anchor/area/anchor_plane/
  total_recorded), grad_norms (3 groups), delta_hat [3],
  param_step_norms {delta, planes, colors}, invariants; checkpoint rows
  additionally carry ``views_psnr`` and ``color_stats``.
- ``s3_tiles/s3c_s<step>/<view_id>/{render.png, residual.png}``:
  checkpoint steps only, in dedicated ``s3c_s<step>`` directories so they
  never collide with the 3b ``s<step>`` snapshots (photo.png stays the 3a
  per-view tile).
- ``s3_face_residual_s3c_final.json``: same approximation and null
  convention as the 3a/3b face residuals (null = no visible samples).
- ``manifest.json``: stage advances to ``"s1+s2+s3a+s3b+s3c"`` and gains
  the ``s3c_def`` block (plus ``injection`` for the injected runs).

``scientific_verdict`` stays null and ``not_official`` stays true.
"""

from __future__ import annotations

import math
import re
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
        S3_DEF_STAGE,
        TILE_MIN_BYTES,
        _positive_int,
        effective_tile_max_px,
        is_finite_number,
        load_s3_config,
        read_png_meta,
        vector_ok,
    )
    from tests.phd.test_s3_verify_s3b_bundle import (
        CHECKPOINT_ONLY_KEYS,
        COLOR_STATS_REQUIRED_KEYS,
        FR_CKPT_NAME,
        LR_RTOL,
        S3B_STAGE,
        STEP_TILE_FILE_NAMES,
        _plain_int,
        check_face_residual_ckpt_stage,
        get_s3b_def,
        load_s3b_bundle,
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
        S3_DEF_STAGE,
        TILE_MIN_BYTES,
        _positive_int,
        effective_tile_max_px,
        is_finite_number,
        load_s3_config,
        read_png_meta,
        vector_ok,
    )
    from tests.phd.test_s3_verify_s3b_bundle import (
        CHECKPOINT_ONLY_KEYS,
        COLOR_STATS_REQUIRED_KEYS,
        FR_CKPT_NAME,
        LR_RTOL,
        S3B_STAGE,
        STEP_TILE_FILE_NAMES,
        _plain_int,
        check_face_residual_ckpt_stage,
        get_s3b_def,
        load_s3b_bundle,
    )

S3C_SCHEMA = "phd_s3_verify_s3c_v1"
STAGE_S1S2S3AS3BS3C = "s1+s2+s3a+s3b+s3c"
S3C_STAGE = "3c"

FINAL_RESIDUAL_S3C_NAME = "s3_face_residual_s3c_final.json"
S3C_TILES_DIRNAME = "s3_tiles"
# Dedicated snapshot directories — never colliding with the 3b s<step> ones.
S3C_STEP_DIR_RE = re.compile(r"^s3c_s(\d+)$")

S3C_DEF_REQUIRED_KEYS = (
    "steps",
    "lr_delta",
    "lr_rgb",
    "trained",
    "objective",
    "objective_note",
    "delta_scope_planes",
    "checkpoints",
    "frozen_checksum_ok",
)
S3C_TRAINED = ["delta", "colors"]
S3C_OBJECTIVE = "photo"

STEP3C_REQUIRED_KEYS = (
    "step",
    "stage",
    "losses",
    "grad_norms",
    "delta_hat",
    "param_step_norms",
    "invariants",
)
# 3c records the photo objective plus the diagnostic-only channels.
LOSS_3C_REQUIRED_KEYS = ("photo", "anchor", "area", "anchor_plane",
                         "total_recorded")
PARAM_STEP_NORM_KEYS = GRAD_NORM_KEYS  # ("delta", "planes", "colors")
INVARIANTS_3C_REQUIRED_KEYS = ("n_seeds", "alpha_binary", "planes_frozen")

# Injection runs are named <base>_DZ<mm-of-shift> (e.g. B022_DZ050) and must
# carry the manifest injection block.
INJECTION_NAME_RE = re.compile(r"_DZ\d+")
INJECTION_REQUIRED_KEYS = ("delta_applied", "route", "expected_delta_hat")

# Weak wiring bound: an injected run whose final |delta_hat| stays at or
# below this norm did not move at all (wiring defect). Restoration quality
# is NOT asserted.
MIN_INJECTED_FINAL_DELTA_NORM = 0.05

# Writer-owned config s3.c block (steps default 300, NEW lr_delta
# registration, lr_rgb = the 3b value), when present, must agree with the
# manifest s3c_def. Same conventions as the 3b module.
CONFIG_C_EXACT_KEYS = ("steps", "checkpoints")


def load_s3c_config() -> dict:
    """Return the writer-owned ``s3.c`` block of the bundle config, or {}."""
    block = load_s3_config().get("c")
    return block if isinstance(block, dict) else {}


def run_has_any_s3c(run_dir: Path) -> bool:
    """True once ANY S3c marker exists (partial sets then fail loudly)."""
    if (run_dir / FINAL_RESIDUAL_S3C_NAME).is_file():
        return True
    tiles_dir = run_dir / S3C_TILES_DIRNAME
    if tiles_dir.is_dir() and any(
        p.is_dir() and S3C_STEP_DIR_RE.match(p.name) for p in tiles_dir.iterdir()
    ):
        return True
    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
        except (OSError, ValueError):
            return False
        if isinstance(manifest, dict) and (
            manifest.get("stage") == STAGE_S1S2S3AS3BS3C
            or "s3c_def" in manifest
        ):
            return True
    return False


_BUNDLE_CACHE: dict[Path, dict] = {}


def load_s3c_bundle(run_dir: Path) -> dict:
    """Load and cache one run's S3c view of the bundle.

    An S3c run is a superset of an S3b run (the 3a/3b files are preserved),
    so the S3b loader is reused and only the S3c-specific final face
    residual is added. Missing files raise AssertionError (corrupt partial
    bundle).
    """
    cached = _BUNDLE_CACHE.get(run_dir)
    if cached is not None:
        return cached
    bundle = dict(load_s3b_bundle(run_dir))
    final_path = run_dir / FINAL_RESIDUAL_S3C_NAME
    assert final_path.is_file(), (
        f"{run_dir.name}: incomplete S3c bundle, missing "
        f"{FINAL_RESIDUAL_S3C_NAME}"
    )
    bundle["face_residual_s3c_final"] = load_json(final_path)
    bundle["rows_3c"] = [
        row for row in bundle["steps"] if row.get("stage") == S3C_STAGE
    ]
    _BUNDLE_CACHE[run_dir] = bundle
    return bundle


def get_s3c_def(name: str, bundle: dict) -> dict:
    """The manifest s3c_def with the minimum shape other checks depend on."""
    s3c_def = bundle["manifest"].get("s3c_def")
    assert isinstance(s3c_def, dict), (
        f"{name}: manifest missing s3c_def object (corrupt partial S3c bundle)"
    )
    assert _positive_int(s3c_def.get("steps")), (
        f"{name}: s3c_def.steps must be a positive integer, "
        f"got {s3c_def.get('steps')!r}"
    )
    checkpoints = s3c_def.get("checkpoints")
    assert (
        isinstance(checkpoints, list)
        and checkpoints
        and all(_plain_int(c) for c in checkpoints)
    ), (
        f"{name}: s3c_def.checkpoints must be a non-empty list of integers, "
        f"got {checkpoints!r}"
    )
    scope = s3c_def.get("delta_scope_planes")
    assert _plain_int(scope) and scope >= 0, (
        f"{name}: s3c_def.delta_scope_planes must be an integer >= 0, "
        f"got {scope!r}"
    )
    return s3c_def


def delta_norm(vec) -> float:
    return math.sqrt(sum(float(v) ** 2 for v in vec))


def is_injection_run(name: str, manifest: dict) -> bool:
    return bool(INJECTION_NAME_RE.search(name)) or "injection" in manifest


class S3cBundleReferenceIntegrityTest(unittest.TestCase):
    """Strict reference-integrity validation for every discovered S3c run."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle_root = resolve_bundle_root()
        cls.run_dirs = discover_run_dirs(cls.bundle_root)
        # A run participates once ANY S3c marker exists; partial S3c sets
        # then fail inside load_s3c_bundle / the checks. Runs with no S3c
        # marker are S1/S2/S3a/S3b-only and are skipped.
        cls.s3c_run_dirs = [d for d in cls.run_dirs if run_has_any_s3c(d)]
        cls.s3c_config = load_s3c_config()
        cls.tile_max_px = effective_tile_max_px(load_s3_config())

    def setUp(self) -> None:
        if not self.run_dirs:
            self.skipTest(
                "S1 verify bundle not generated yet: no runs/<name>/ found under "
                f"env {BUNDLE_ENV}, {ARTIFACT_ROOT_ENV}/{BUNDLE_RELPATH}, or defaults "
                f"{[str(p) for p in DEFAULT_BUNDLE_ROOTS]}"
            )
        if not self.s3c_run_dirs:
            self.skipTest(
                "S3c bundle files not generated yet in any run (S1..S3b-only "
                f"bundles are allowed): looked for {FINAL_RESIDUAL_S3C_NAME}, "
                f"{S3C_TILES_DIRNAME}/s3c_s<step>/, or a manifest stage/"
                f"s3c_def marker in {[d.name for d in self.run_dirs]}"
            )

    def for_each_s3c_run(self, check) -> None:
        """Run one check per discovered S3c run inside a subTest scope."""
        for run_dir in self.s3c_run_dirs:
            with self.subTest(run=run_dir.name):
                check(run_dir.name, load_s3c_bundle(run_dir))

    # ----------------------------------------------------- 1. manifest s3c_def

    def test_manifest_s3c_contract_fields(self) -> None:
        self.for_each_s3c_run(self._check_manifest_s3c_contract_fields)

    def _check_manifest_s3c_contract_fields(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        self.assertEqual(
            manifest.get("stage"), STAGE_S1S2S3AS3BS3C,
            f"{name}: manifest stage must be {STAGE_S1S2S3AS3BS3C!r} once S3c "
            "files exist (the 3a/3b guarantees stay in force)",
        )
        self.assertIsNone(
            manifest.get("scientific_verdict"),
            f"{name}: scientific_verdict must stay null",
        )
        self.assertIs(
            manifest.get("not_official"), True,
            f"{name}: not_official must stay true",
        )
        if "s3c_schema" in manifest:
            self.assertEqual(
                manifest["s3c_schema"], S3C_SCHEMA,
                f"{name}: s3c_schema, when present, must be {S3C_SCHEMA!r}",
            )

        s3c_def = manifest.get("s3c_def")
        self.assertIsInstance(
            s3c_def, dict, f"{name}: manifest missing s3c_def object"
        )
        for key in S3C_DEF_REQUIRED_KEYS:
            self.assertIn(key, s3c_def, f"{name}: s3c_def missing key {key!r}")

        steps = s3c_def["steps"]
        self.assertTrue(
            _positive_int(steps),
            f"{name}: s3c_def.steps must be a positive integer, got {steps!r}",
        )
        for key in ("lr_delta", "lr_rgb"):
            self.assertTrue(
                is_finite_number(s3c_def[key]) and float(s3c_def[key]) > 0.0,
                f"{name}: s3c_def.{key} must be a positive finite number, "
                f"got {s3c_def[key]!r}",
            )
        self.assertEqual(
            s3c_def["trained"], S3C_TRAINED,
            f"{name}: s3c_def.trained must be exactly {S3C_TRAINED!r} — 3c "
            "trains the ONE global-translation delta (no rotation, §1.3) "
            "plus colors (3b warm-start); planes/occupancy/seed geometry "
            f"stay frozen, got {s3c_def['trained']!r}",
        )
        self.assertEqual(
            s3c_def["objective"], S3C_OBJECTIVE,
            f"{name}: s3c_def.objective must be {S3C_OBJECTIVE!r} — anchor/"
            "area are DIAGNOSTIC records, not backprop targets in 3c (delta "
            "has no anchor; a plane-anchor term with frozen planes would "
            "penalize |delta_hat| and suppress the injected-shift "
            f"restoration), got {s3c_def['objective']!r}",
        )
        objective_note = s3c_def["objective_note"]
        self.assertTrue(
            isinstance(objective_note, str) and objective_note.strip(),
            f"{name}: s3c_def.objective_note must be a non-empty string "
            "stating WHY anchor/area are excluded from the 3c objective "
            "(delta has no anchor, §2.2; plane-anchor target P0(+)delta "
            "degenerates to a |delta_hat| penalty while planes are frozen; "
            f"normal from 3d on), got {objective_note!r}",
        )
        self.assertIs(
            s3c_def["frozen_checksum_ok"], True,
            f"{name}: s3c_def.frozen_checksum_ok must be true — the writer "
            "must assert byte-level invariance of the frozen groups (planes/"
            "occupancy/seed geometry) across the whole run",
        )
        scope = s3c_def["delta_scope_planes"]
        self.assertTrue(
            _plain_int(scope) and scope >= 0,
            f"{name}: s3c_def.delta_scope_planes must be an integer >= 0 "
            f"(number of prior-source planes delta acts on), got {scope!r}",
        )

        checkpoints = s3c_def["checkpoints"]
        self.assertTrue(
            isinstance(checkpoints, list) and checkpoints,
            f"{name}: s3c_def.checkpoints must be a non-empty list, "
            f"got {checkpoints!r}",
        )
        self.assertTrue(
            all(_plain_int(c) for c in checkpoints),
            f"{name}: s3c_def.checkpoints entries must be integers, "
            f"got {checkpoints!r}",
        )
        self.assertEqual(
            checkpoints, sorted(set(checkpoints)),
            f"{name}: s3c_def.checkpoints must be strictly increasing without "
            f"duplicates, got {checkpoints!r}",
        )
        self.assertTrue(
            all(0 <= c <= steps for c in checkpoints),
            f"{name}: s3c_def.checkpoints must lie within [0, steps={steps}], "
            f"got {checkpoints!r}",
        )
        self.assertIn(
            0, checkpoints,
            f"{name}: s3c_def.checkpoints must include 0 (pre-training state)",
        )
        self.assertIn(
            steps, checkpoints,
            f"{name}: s3c_def.checkpoints must include the final step "
            f"{steps}, got {checkpoints!r}",
        )

        # Writer-owned config s3.c block, when registered, is the constant
        # source; the manifest must not silently diverge from it.
        for key in CONFIG_C_EXACT_KEYS:
            if key in self.s3c_config:
                self.assertEqual(
                    s3c_def[key], self.s3c_config[key],
                    f"{name}: s3c_def.{key}={s3c_def[key]!r} diverges from "
                    f"config s3.c.{key}={self.s3c_config[key]!r}",
                )
        for key in ("lr_delta", "lr_rgb"):
            config_lr = self.s3c_config.get(key)
            if is_number(config_lr):
                self.assertTrue(
                    math.isclose(float(s3c_def[key]), float(config_lr),
                                 rel_tol=LR_RTOL),
                    f"{name}: s3c_def.{key}={s3c_def[key]!r} diverges from "
                    f"config s3.c.{key}={config_lr!r}",
                )
        config_opt = self.s3c_config.get("optimizer")
        s3c_opt = s3c_def.get("optimizer")
        if (isinstance(config_opt, str) and config_opt.strip()
                and isinstance(s3c_opt, str)):
            self.assertTrue(
                s3c_opt.startswith(config_opt),
                f"{name}: s3c_def.optimizer={s3c_opt!r} must start with the "
                f"config s3.c.optimizer constant {config_opt!r}",
            )
        # lr_rgb is the 3b value (colors warm-start keeps the 3b color lr):
        # cross-check against the same run's s3b_def.lr.
        s3b_lr = get_s3b_def(name, bundle).get("lr")
        if is_number(s3b_lr):
            self.assertTrue(
                math.isclose(float(s3c_def["lr_rgb"]), float(s3b_lr),
                             rel_tol=LR_RTOL),
                f"{name}: s3c_def.lr_rgb={s3c_def['lr_rgb']!r} must equal the "
                f"3b color lr s3b_def.lr={s3b_lr!r} (3b warm-start)",
            )

        # Injection block: required for injected runs (<base>_DZ<mm>),
        # validated whenever present.
        if INJECTION_NAME_RE.search(name):
            self.assertIn(
                "injection", manifest,
                f"{name}: injected run (name matches _DZ<mm>) must carry the "
                "manifest injection block (delta_applied/route/"
                "expected_delta_hat)",
            )
        injection = manifest.get("injection")
        if injection is not None:
            self.assertIsInstance(
                injection, dict, f"{name}: injection must be an object"
            )
            for key in INJECTION_REQUIRED_KEYS:
                self.assertIn(
                    key, injection, f"{name}: injection missing key {key!r}"
                )
            delta_applied = injection["delta_applied"]
            self.assertTrue(
                vector_ok(delta_applied, 3)
                and all(is_finite_number(v) for v in delta_applied),
                f"{name}: injection.delta_applied must be a finite numeric "
                f"3-vector (e.g. [0, 0, 0.5]), got {delta_applied!r}",
            )
            self.assertGreater(
                delta_norm(delta_applied), 0.0,
                f"{name}: injection.delta_applied must be non-zero, "
                f"got {delta_applied!r}",
            )
            route = injection["route"]
            self.assertTrue(
                isinstance(route, str) and route.strip(),
                f"{name}: injection.route must be a non-empty string naming "
                "the honest injection path (ALS bytes via xreal_run.py "
                f"scene_for dz), got {route!r}",
            )
            expected = injection["expected_delta_hat"]
            expected_ok = (
                isinstance(expected, str) and bool(expected.strip())
            ) or (
                vector_ok(expected, 3)
                and all(is_finite_number(v) for v in expected)
                and delta_norm(expected) > 0.0
            )
            self.assertTrue(
                expected_ok,
                f"{name}: injection.expected_delta_hat must state the "
                "expectation WITH the sign convention (non-empty string or "
                "non-zero numeric 3-vector — the direction that cancels the "
                f"injection), got {expected!r}",
            )
            self.assertGreater(
                s3c_def["delta_scope_planes"], 0,
                f"{name}: injected run must have s3c_def.delta_scope_planes "
                "> 0 — the ALS-byte injection flows through prior-source "
                "plane statements, so a zero delta scope means the honest "
                "injection route is broken",
            )

    # ------------------------------------------------------------ 2. s3_steps

    def test_steps_3c_rows(self) -> None:
        self.for_each_s3c_run(self._check_steps_3c_rows)

    def _check_steps_3c_rows(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        s3c_def = get_s3c_def(name, bundle)
        total_steps = s3c_def["steps"]
        checkpoints = set(s3c_def["checkpoints"])
        scope = s3c_def["delta_scope_planes"]
        id_set = set(bundle["view_ids"])

        # The 3a wiring row and ALL 3b rows must be PRESERVED — 3c appends
        # rows, never rewrites the earlier records. (Their full validation
        # stays with the S3a/S3b modules, which also run on this bundle.)
        rows_3a = [
            row for row in bundle["steps"] if row.get("stage") == S3_DEF_STAGE
        ]
        self.assertEqual(
            len(rows_3a), 1,
            f"{name}: exactly one preserved stage-'3a' row expected in "
            f"s3_steps.jsonl (3c appends rows), got {len(rows_3a)}",
        )
        self.assertEqual(
            rows_3a[0].get("step"), 0,
            f"{name}: the preserved 3a row must have step 0, "
            f"got {rows_3a[0].get('step')!r}",
        )
        rows_3b = [
            row for row in bundle["steps"] if row.get("stage") == S3B_STAGE
        ]
        self.assertTrue(
            rows_3b,
            f"{name}: the stage-'3b' rows must be preserved in "
            "s3_steps.jsonl (3c appends rows)",
        )
        s3b_steps = get_s3b_def(name, bundle)["steps"]
        self.assertEqual(
            rows_3b[-1].get("step"), s3b_steps,
            f"{name}: the last preserved 3b row must still reach "
            f"s3b_def.steps={s3b_steps}, got {rows_3b[-1].get('step')!r} "
            "(3c must not truncate the 3b record)",
        )

        rows_3c = bundle["rows_3c"]
        self.assertTrue(
            rows_3c, f"{name}: s3_steps.jsonl carries no stage-'3c' rows"
        )

        counts = manifest.get("counts", {})
        expected_seeds = counts.get("seeds") if isinstance(counts, dict) else None

        step_values: list[int] = []
        rows_with_delta_movement = 0
        for row in rows_3c:
            step = row.get("step")
            label = f"{name}/3c step {step!r}"
            for key in STEP3C_REQUIRED_KEYS:
                self.assertIn(key, row, f"{label}: row missing key {key!r}")
            self.assertTrue(
                _plain_int(step) and 0 <= step <= total_steps,
                f"{label}: step must be an integer within "
                f"[0, s3c_def.steps={total_steps}]",
            )
            step_values.append(step)

            losses = row["losses"]
            self.assertIsInstance(
                losses, dict, f"{label}: losses must be an object"
            )
            for key in LOSS_3C_REQUIRED_KEYS:
                self.assertIn(
                    key, losses,
                    f"{label}: losses missing key {key!r} (3c records photo "
                    "— the ONLY objective channel — plus anchor/area/"
                    "anchor_plane/total_recorded as diagnostics)",
                )
            for key, value in losses.items():
                self.assertTrue(
                    is_finite_number(value),
                    f"{label}: losses.{key} must be a finite number, "
                    f"got {value!r}",
                )
            self.assertGreaterEqual(
                float(losses["photo"]), 0.0,
                f"{label}: losses.photo must be >= 0",
            )
            self.assertGreaterEqual(
                float(losses["total_recorded"]), 0.0,
                f"{label}: losses.total_recorded must be >= 0",
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
                    "norms are recorded too",
                )
                value = grads[key]
                self.assertTrue(
                    is_finite_number(value) and float(value) >= 0.0,
                    f"{label}: grad_norms.{key} must be a finite non-negative "
                    f"number, got {value!r}",
                )

            delta_hat = row["delta_hat"]
            self.assertTrue(
                vector_ok(delta_hat, 3)
                and all(is_finite_number(v) for v in delta_hat),
                f"{label}: delta_hat must be a finite numeric 3-vector "
                f"(ONE global translation, no rotation), got {delta_hat!r}",
            )

            norms = row["param_step_norms"]
            self.assertIsInstance(
                norms, dict, f"{label}: param_step_norms must be an object"
            )
            for key in PARAM_STEP_NORM_KEYS:
                self.assertIn(
                    key, norms, f"{label}: param_step_norms missing {key!r}"
                )
            planes_norm = norms["planes"]
            self.assertTrue(
                is_number(planes_norm) and float(planes_norm) == 0.0,
                f"{label}: param_step_norms.planes must be exactly 0 — "
                "planes are FROZEN in 3c (delta + colors only), "
                f"got {planes_norm!r}",
            )
            for key in ("delta", "colors"):
                value = norms[key]
                self.assertTrue(
                    is_finite_number(value) and float(value) >= 0.0,
                    f"{label}: param_step_norms.{key} must be a finite "
                    f"non-negative number, got {value!r}",
                )
            if scope == 0:
                self.assertEqual(
                    float(norms["delta"]), 0.0,
                    f"{label}: param_step_norms.delta must be exactly 0 in a "
                    f"delta-scope-0 run (negative control: no prior-source "
                    f"planes for delta to act on), got {norms['delta']!r}",
                )
            elif float(norms["delta"]) > 0.0:
                rows_with_delta_movement += 1

            invariants = row["invariants"]
            self.assertIsInstance(
                invariants, dict, f"{label}: invariants must be an object"
            )
            for key in INVARIANTS_3C_REQUIRED_KEYS:
                self.assertIn(
                    key, invariants, f"{label}: invariants missing {key!r}"
                )
            for key in ("planes_frozen", "alpha_binary"):
                self.assertIs(
                    invariants[key], True,
                    f"{label}: invariants.{key} must be true (planes/occupancy"
                    "/seed geometry frozen; alpha stays derived binary, never "
                    "a free learned alpha; no densify/prune)",
                )
            self.assertIsNot(
                invariants.get("delta_frozen"), True,
                f"{label}: invariants.delta_frozen must NOT be true in 3c — "
                "delta is a TRAINED variable here (omit the key or record "
                "false)",
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
                        "the step is not in s3c_def.checkpoints",
                    )
            if is_checkpoint:
                views_psnr = row["views_psnr"]
                self.assertIsInstance(
                    views_psnr, dict, f"{label}: views_psnr must be an object"
                )
                unknown = sorted(set(views_psnr) - id_set)
                self.assertFalse(
                    unknown,
                    f"{label}: views_psnr keys must be a subset of the "
                    f"s3_views view_id set; unknown keys {unknown}",
                )
                for vid, value in views_psnr.items():
                    self.assertTrue(
                        is_number(value) and not math.isnan(float(value)),
                        f"{label}: views_psnr[{vid!r}] must be a numeric "
                        f"PSNR, got {value!r}",
                    )
                color_stats = row["color_stats"]
                self.assertIsInstance(
                    color_stats, dict,
                    f"{label}: color_stats must be an object",
                )
                for key in COLOR_STATS_REQUIRED_KEYS:
                    self.assertIn(
                        key, color_stats,
                        f"{label}: color_stats missing {key!r}",
                    )
                    value = color_stats[key]
                    self.assertTrue(
                        is_finite_number(value) and float(value) >= 0.0,
                        f"{label}: color_stats.{key} must be a finite "
                        f"non-negative number, got {value!r}",
                    )

        self.assertEqual(
            step_values, sorted(set(step_values)),
            f"{name}: 3c row steps must be strictly increasing, "
            f"got {step_values[:20]}...",
        )
        self.assertEqual(
            step_values[-1], total_steps,
            f"{name}: last 3c row step {step_values[-1]} != s3c_def.steps="
            f"{total_steps} (the run must reach its declared step count)",
        )
        missing_checkpoints = sorted(checkpoints - set(step_values))
        self.assertFalse(
            missing_checkpoints,
            f"{name}: s3c_def.checkpoints without a 3c step row: "
            f"{missing_checkpoints}",
        )
        if scope > 0:
            self.assertGreaterEqual(
                rows_with_delta_movement, 1,
                f"{name}: param_step_norms.delta must be > 0 in at least one "
                "3c row of a delta-scope>0 run (the optimizer must actually "
                "move delta)",
            )

    # ---------------------------------------- 3. delta wiring (weak monotonic)

    def test_delta_wiring_final_delta_hat(self) -> None:
        self.for_each_s3c_run(self._check_delta_wiring_final_delta_hat)

    def _check_delta_wiring_final_delta_hat(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        s3c_def = get_s3c_def(name, bundle)
        total_steps = s3c_def["steps"]
        scope = s3c_def["delta_scope_planes"]

        final_rows = [
            row for row in bundle["rows_3c"] if row.get("step") == total_steps
        ]
        self.assertEqual(
            len(final_rows), 1,
            f"{name}: exactly one 3c row at the final step {total_steps} "
            f"expected, got {len(final_rows)}",
        )
        delta_hat = final_rows[0].get("delta_hat")
        self.assertTrue(
            vector_ok(delta_hat, 3)
            and all(is_finite_number(v) for v in delta_hat),
            f"{name}: final 3c delta_hat must be a finite numeric 3-vector, "
            f"got {delta_hat!r}",
        )

        if scope == 0:
            self.assertTrue(
                all(float(v) == 0.0 for v in delta_hat),
                f"{name}: final |delta_hat| must be exactly 0 in a "
                "delta-scope-0 run (negative control: with no prior-source "
                "planes, a moving delta is a wiring defect), "
                f"got {delta_hat!r}",
            )
        elif is_injection_run(name, manifest):
            self.assertGreater(
                delta_norm(delta_hat), MIN_INJECTED_FINAL_DELTA_NORM,
                f"{name}: injected scope>0 run must move — final |delta_hat| "
                f"= {delta_norm(delta_hat):.6g} <= "
                f"{MIN_INJECTED_FINAL_DELTA_NORM} means the injection never "
                "reached the optimizer (wiring defect). Restoration QUALITY "
                "(closeness to injection.delta_applied) is deliberately not "
                "asserted — that is the human reading's job.",
            )
        # Non-injected scope>0 controls (B022/B173): delta_hat ~ 0 is the
        # expectation but the residual drift is READING material — no
        # magnitude assertion here.

    # --------------------------------------------- 4. s3_tiles/s3c_s<step>/

    def test_checkpoint_step_tiles(self) -> None:
        self.for_each_s3c_run(self._check_checkpoint_step_tiles)

    def _check_checkpoint_step_tiles(self, name: str, bundle: dict) -> None:
        s3c_def = get_s3c_def(name, bundle)
        checkpoints = s3c_def["checkpoints"]
        tiles_dir = bundle["tiles_dir"]
        id_set = set(bundle["view_ids"])

        # s3c_s<step> directories must be exactly the 3c checkpoint set; the
        # 3a per-view and 3b s<step> directories live alongside them and are
        # owned by the S3a/S3b modules.
        step_dirs = {
            int(match.group(1))
            for p in tiles_dir.iterdir()
            if p.is_dir() and (match := S3C_STEP_DIR_RE.match(p.name))
        }
        missing_steps = sorted(set(checkpoints) - step_dirs)
        extra_steps = sorted(step_dirs - set(checkpoints))
        self.assertFalse(
            missing_steps,
            f"{name}: s3_tiles/ missing 3c checkpoint step directories "
            f"{[f's3c_s{c}' for c in missing_steps]}",
        )
        self.assertFalse(
            extra_steps,
            f"{name}: s3_tiles/ has s3c step directories not in "
            f"s3c_def.checkpoints: {[f's3c_s{c}' for c in extra_steps]}",
        )

        for checkpoint in checkpoints:
            step_dir = tiles_dir / f"s3c_s{checkpoint}"
            dir_set = {p.name for p in step_dir.iterdir() if p.is_dir()}
            missing = sorted(v for v in id_set if v not in dir_set)
            extra = sorted(dir_set - id_set)
            self.assertFalse(
                missing,
                f"{name}/s3c_s{checkpoint}: missing view directories "
                f"{missing} (every view gets a render/residual snapshot per "
                "checkpoint; photo.png is reused from the 3a tiles)",
            )
            self.assertFalse(
                extra,
                f"{name}/s3c_s{checkpoint}: directories for unknown view_ids "
                f"{extra}",
            )
            for vid in sorted(v for v in id_set if isinstance(v, str)):
                view_dir = step_dir / vid
                for tile_name in STEP_TILE_FILE_NAMES:
                    tile_path = view_dir / tile_name
                    self.assertTrue(
                        tile_path.is_file(),
                        f"{name}/s3c_s{checkpoint}/{vid}: missing tile "
                        f"{tile_name}",
                    )
                    width, height, size = read_png_meta(tile_path)
                    self.assertGreater(
                        size, TILE_MIN_BYTES,
                        f"{name}/s3c_s{checkpoint}/{vid}/{tile_name}: tile "
                        f"must be non-empty (> {TILE_MIN_BYTES} bytes), "
                        f"got {size}",
                    )
                    self.assertTrue(
                        width >= 1 and height >= 1,
                        f"{name}/s3c_s{checkpoint}/{vid}/{tile_name}: "
                        f"degenerate PNG size {width}x{height}",
                    )
                    self.assertLessEqual(
                        max(width, height), self.tile_max_px,
                        f"{name}/s3c_s{checkpoint}/{vid}/{tile_name}: long "
                        f"side {max(width, height)} exceeds tile_max_px "
                        f"{self.tile_max_px}",
                    )

    # ------------------------------------ 5. s3_face_residual_s3c_final

    def test_face_residual_s3c_final_reference_integrity(self) -> None:
        self.for_each_s3c_run(self._check_face_residual_s3c_final)

    def _check_face_residual_s3c_final(self, name: str, bundle: dict) -> None:
        s3c_def = get_s3c_def(name, bundle)
        doc = bundle["face_residual_s3c_final"]
        self.assertEqual(
            doc.get("step"), s3c_def["steps"],
            f"{name}: {FINAL_RESIDUAL_S3C_NAME} step={doc.get('step')!r} must "
            f"equal the final step s3c_def.steps={s3c_def['steps']}",
        )
        if "stage" in doc:
            self.assertEqual(
                doc["stage"], S3C_STAGE,
                f"{name}: {FINAL_RESIDUAL_S3C_NAME} stage, when present, "
                f"must be {S3C_STAGE!r}",
            )
        method = doc.get("method")
        self.assertTrue(
            isinstance(method, str) and method.strip(),
            f"{name}: {FINAL_RESIDUAL_S3C_NAME} method must be a non-empty "
            "string naming the same approximation as the 3a "
            f"s3_face_residual.json, got {method!r}",
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
        # Same null convention as 3a/3b: null = "no visible samples" — an
        # honest gap, not a defect. Numbers must be finite and non-negative;
        # at least one face must carry a number.
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
            numeric, 0,
            f"{name}: per_face must contain at least one sampled value",
        )

    # ------------------------------- 6. s3_face_residual_ckpt.json (optional)

    def test_face_residual_ckpt_entries(self) -> None:
        """3c entries of the per-checkpoint face residual file.

        Skips when no run carries the file (pre-checkpoint bundles allowed).
        The shared stage checker also asserts the final 3c entry equals
        s3_face_residual_s3c_final.json; the preserved 3b entries, when
        present, must still match the 3b checkpoint list (merge must not
        corrupt the other stage).
        """
        runs = [d for d in self.s3c_run_dirs if (d / FR_CKPT_NAME).is_file()]
        if not runs:
            self.skipTest(
                f"{FR_CKPT_NAME} not generated in any S3c run (pre-checkpoint "
                "bundles allowed — the amended 3b/3c writers create it)"
            )
        for run_dir in runs:
            with self.subTest(run=run_dir.name):
                bundle = load_s3c_bundle(run_dir)
                doc = load_json(run_dir / FR_CKPT_NAME)
                s3c_def = get_s3c_def(run_dir.name, bundle)
                check_face_residual_ckpt_stage(
                    self, run_dir.name, bundle, doc, S3C_STAGE,
                    s3c_def["checkpoints"],
                    bundle["face_residual_s3c_final"].get("per_face"),
                )
                # 3b entries preserved by the 3c merge must stay coherent.
                entries = doc.get("entries", [])
                steps_3b = [e.get("step") for e in entries
                            if isinstance(e, dict) and e.get("stage") == S3B_STAGE]
                if steps_3b:
                    self.assertEqual(
                        steps_3b, get_s3b_def(run_dir.name, bundle)["checkpoints"],
                        f"{run_dir.name}: preserved 3b entries' steps must "
                        "still be the 3b checkpoint list (the 3c merge "
                        "replaces only its own stage)",
                    )


if __name__ == "__main__":
    unittest.main()
