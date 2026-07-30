#!/usr/bin/env python3
"""Static policy tests for P2 panel/qualitative projection consumers.

The historical P0 diagnostic remains readable for provenance, but an active
P2 panel or qualitative publisher must not import it, dynamically load it, or
copy its local ``project_points`` implementation.  Panel v4 is one explicit
temporary exception because the currently running hash-frozen queue still
invokes it; its flat locator may not spread to another entrypoint and it must
be retired after that queue terminates.  The test parses source text and AST
only; it never imports an active publisher or the historical module.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
P2_SCRIPTS = REPO / "phases/p2-gsjso/scripts/fusion_w1"
P2_CONFIGS = REPO / "phases/p2-gsjso/configs/fusion_w1"
LEGACY_PROJECTOR = REPO / "phases/p0-audit/scripts/07_failure_diagnosis.py"
FORBIDDEN_TEXT = (
    "phases/p0-audit/scripts/07_failure_diagnosis.py",
    "07_failure_diagnosis.py",
    "T7.project_points",
)
RETIRED_V1_IMPLEMENTATION = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v1_20260728.py",
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v1_20260728.json",
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v1_20260728.sh",
    REPO
    / "tests/fusion_w1/test_fusion_w1_dense_baseline_qualitative_v1_20260728.py",
)
RETIRED_V5_IMPLEMENTATION = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v5_backfill_20260728.py",
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_panel_v5_backfill_20260728.json",
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_job_panel_v5_backfill_20260728.sh",
    REPO
    / "tests/fusion_w1/test_fusion_w1_aprime_job_panel_v5_backfill_20260728.py",
)
FROZEN_QUEUE_V4_IMPLEMENTATION = (
    REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py",
    REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.json",
    REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_job_panel_v4_20260727.sh",
    REPO / "tests/fusion_w1/test_fusion_w1_aprime_job_panel_v4_20260727.py",
)
DISTORTION_SYMBOLS = {"k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6"}


def relative(path: Path) -> str:
    return str(path.relative_to(REPO))


def active_entrypoints() -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in ("*panel*.py", "*qualitative*.py"):
        paths.update(
            path
            for path in P2_SCRIPTS.glob(pattern)
            if not path.name.startswith("test_")
        )
    for pattern in ("run_*panel*.sh", "run_*qualitative*.sh"):
        paths.update(P2_SCRIPTS.glob(pattern))
    for pattern in ("*panel*.json", "*qualitative*.json"):
        paths.update(P2_CONFIGS.glob(pattern))
    return tuple(sorted(paths))


def legacy_function_fingerprint() -> str:
    tree = ast.parse(LEGACY_PROJECTOR.read_text(encoding="utf-8"))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "project_points"
    ]
    if len(matches) != 1:
        raise AssertionError("historical P0 project_points definition is not unique")
    function = copy.deepcopy(matches[0])
    function.name = "__normalized_projector__"
    function.decorator_list = []
    return ast.dump(function, include_attributes=False)


def normalized_function_fingerprint(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    normalized = copy.deepcopy(function)
    normalized.name = "__normalized_projector__"
    normalized.decorator_list = []
    return ast.dump(normalized, include_attributes=False)


class ActiveQualitativeProjectionPolicyTests(unittest.TestCase):
    def test_active_inventory_uses_corrected_versions_and_keeps_v1_v5_retired(self) -> None:
        active = {relative(path) for path in active_entrypoints()}
        self.assertIn(
            "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.py",
            active,
        )
        self.assertIn(
            "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.json",
            active,
        )
        self.assertGreaterEqual(len(active), 2)
        for path in RETIRED_V1_IMPLEMENTATION:
            with self.subTest(path=relative(path)):
                self.assertFalse(path.exists())
        for path in RETIRED_V5_IMPLEMENTATION:
            with self.subTest(path=relative(path)):
                self.assertFalse(path.exists())
        for path in FROZEN_QUEUE_V4_IMPLEMENTATION:
            with self.subTest(path=relative(path)):
                self.assertTrue(path.is_file())

    def test_flat_locator_is_confined_to_the_frozen_queue_v4_renderer(self) -> None:
        owners: list[str] = []
        for path in active_entrypoints():
            if path.suffix != ".py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "base_xy_to_canonical_at_z"
                for node in ast.walk(tree)
            ):
                owners.append(relative(path))
        self.assertEqual(
            owners,
            ["phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py"],
        )

    def test_historical_p0_projector_is_preserved_but_not_active(self) -> None:
        self.assertTrue(LEGACY_PROJECTOR.is_file())
        self.assertNotIn(LEGACY_PROJECTOR, active_entrypoints())
        self.assertIn("def project_points", LEGACY_PROJECTOR.read_text(encoding="utf-8"))

    def test_active_entrypoints_do_not_reference_legacy_module(self) -> None:
        violations: dict[str, list[str]] = {}
        for path in active_entrypoints():
            source = path.read_text(encoding="utf-8")
            matches = [token for token in FORBIDDEN_TEXT if token in source]
            if matches:
                violations[relative(path)] = matches
        self.assertEqual(violations, {})

    def test_active_python_does_not_own_legacy_or_equivalent_projector(self) -> None:
        legacy_fingerprint = legacy_function_fingerprint()
        violations: list[str] = []
        for path in active_entrypoints():
            if path.suffix != ".py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                label = f"{relative(path)}:{node.lineno}:{node.name}"
                if node.name == "project_points":
                    violations.append(label + ":forbidden_local_api")
                if normalized_function_fingerprint(node) == legacy_fingerprint:
                    violations.append(label + ":legacy_ast_clone")
                names = {
                    child.id for child in ast.walk(node) if isinstance(child, ast.Name)
                }
                attributes = {
                    child.attr
                    for child in ast.walk(node)
                    if isinstance(child, ast.Attribute)
                }
                if DISTORTION_SYMBOLS <= names and {"rot", "params"} <= attributes:
                    violations.append(label + ":legacy_distortion_math_clone")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
