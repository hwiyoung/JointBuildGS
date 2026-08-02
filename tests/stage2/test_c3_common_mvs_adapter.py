from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import src.stage2.c3_common_mvs_adapter as adapter
from src.stage2.c3_common_mvs_adapter import (
    C3CommonMvsAdapterError,
    CommonMvsAdapterConfig,
)


def _ascii_ply(rows: list[tuple[float, float, float, int]]) -> bytes:
    header = adapter._ascii_header(len(rows))
    body = b"".join(
        f"{x:.8f} {y:.8f} {z:.8f} {class_id}\n".encode("ascii")
        for x, y, z, class_id in rows
    )
    return header + body


def _read_binary_xyz(path: Path) -> np.ndarray:
    data = path.read_bytes()
    marker = b"end_header\n"
    body = data[data.index(marker) + len(marker) :]
    return np.frombuffer(body, dtype="<f4").reshape(-1, 3)


def _fixture_config(
    root: Path,
    rows: list[tuple[float, float, float, int]],
    *,
    expected_classes: tuple[tuple[int, int], ...] = ((2, 2), (6, 1)),
    shift: tuple[float, float, float] = (100.0, 200.0, 300.0),
) -> CommonMvsAdapterConfig:
    source = root / "mvs_class26_v1.ply"
    payload = _ascii_ply(rows)
    source.write_bytes(payload)
    return CommonMvsAdapterConfig(
        source_path=source,
        output_path=root / "mvs_class26_gs_local_xyz.ply",
        receipt_path=root / "mvs_class26_gs_local_xyz.receipt.json",
        expected_input_bytes=len(payload),
        expected_input_sha256=hashlib.sha256(payload).hexdigest(),
        expected_input_points=len(rows),
        expected_class_counts=expected_classes,
        shift_xyz=shift,
        chunk_rows=2,
    )


def _adapt(config: CommonMvsAdapterConfig):
    return adapter._adapt_common_mvs_to_gs_local_for_test(config)


class C3CommonMvsAdapterTests(unittest.TestCase):
    def test_one_read_coordinate_bounds_xyz_only_and_concat_contract(self):
        rows = [
            (101.25, 202.50, 303.75, 2),
            (99.50, 200.00, 300.00, 6),
            (100.00, 199.00, 298.00, 2),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _fixture_config(root, rows)
            with patch.object(adapter, "_open_source", wraps=adapter._open_source) as opened:
                receipt = _adapt(config)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(receipt["input"]["class_counts"], {"2": 2, "6": 1})
            self.assertEqual(
                receipt["input"]["bounds_epsg25832_float64"],
                {"min_xyz": [99.5, 199.0, 298.0], "max_xyz": [101.25, 202.5, 303.75]},
            )
            self.assertEqual(
                receipt["output"]["bounds_gs_local_float64_before_serialization"],
                {"min_xyz": [-0.5, -1.0, -2.0], "max_xyz": [1.25, 2.5, 3.75]},
            )
            np.testing.assert_array_equal(
                _read_binary_xyz(config.output_path),
                np.asarray(
                    [[1.25, 2.5, 3.75], [-0.5, 0.0, 0.0], [0.0, -1.0, -2.0]],
                    dtype=np.float32,
                ),
            )
            self.assertFalse(receipt["transform"]["classification_written_to_output"])
            self.assertFalse(receipt["transform"]["classification_exposed_to_loss"])
            self.assertEqual(receipt["output"]["vertex_count"], 3)
            self.assertEqual(
                receipt["output"]["sha256"],
                hashlib.sha256(config.output_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(receipt["pass_accounting"]["input_standalone_rehash_passes"], 0)
            self.assertEqual(receipt["pass_accounting"]["output_standalone_rehash_passes"], 0)
            concat = receipt["training_side_concat_contract"]
            self.assertEqual(concat["exact_final_initial_gaussians"], 371_811)
            self.assertEqual(concat["production_exact_final_initial_gaussians"], 593_852)
            self.assertEqual(concat["mvs_rgb_initialization"], "SCENE_MEAN_RGB_FALLBACK")
            persisted = json.loads(config.receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted, receipt)
            self.assertIsNone(receipt["scientific_verdict"])
            self.assertEqual(receipt["performance_runs_started"], 0)

    def test_nonfinite_input_fails_closed_without_publication(self):
        rows = [(101.0, 202.0, float("nan"), 2), (99.0, 200.0, 300.0, 6)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _fixture_config(root, rows, expected_classes=((2, 1), (6, 1)))
            with self.assertRaisesRegex(C3CommonMvsAdapterError, "non-finite"):
                _adapt(config)
            self.assertFalse(config.output_path.exists())
            self.assertFalse(config.receipt_path.exists())

    def test_class_count_identity_mismatch_fails_after_one_read(self):
        rows = [(101.0, 202.0, 303.0, 2), (99.0, 200.0, 300.0, 6)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _fixture_config(root, rows, expected_classes=((2, 2),))
            with patch.object(adapter, "_open_source", wraps=adapter._open_source) as opened:
                with self.assertRaisesRegex(C3CommonMvsAdapterError, "outside exact"):
                    _adapt(config)
            self.assertEqual(opened.call_count, 1)
            self.assertFalse(config.output_path.exists())
            self.assertFalse(config.receipt_path.exists())

    def test_sha_identity_mismatch_fails_without_publication_or_rehash(self):
        rows = [(101.0, 202.0, 303.0, 2), (99.0, 200.0, 300.0, 6)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _fixture_config(root, rows, expected_classes=((2, 1), (6, 1)))
            config = CommonMvsAdapterConfig(
                **{**config.__dict__, "expected_input_sha256": "f" * 64}
            )
            with patch.object(adapter, "_open_source", wraps=adapter._open_source) as opened:
                with self.assertRaisesRegex(C3CommonMvsAdapterError, "SHA-256"):
                    _adapt(config)
            self.assertEqual(opened.call_count, 1)
            self.assertFalse(config.output_path.exists())
            self.assertFalse(config.receipt_path.exists())

    def test_add_once_rejects_before_second_source_open(self):
        rows = [(101.0, 202.0, 303.0, 2), (99.0, 200.0, 300.0, 6)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _fixture_config(root, rows, expected_classes=((2, 1), (6, 1)))
            _adapt(config)
            with patch.object(adapter, "_open_source") as opened:
                with self.assertRaisesRegex(C3CommonMvsAdapterError, "add-once"):
                    _adapt(config)
            opened.assert_not_called()

    def test_production_entry_rejects_nonexact_identity_before_git_or_source(self):
        rows = [(101.0, 202.0, 303.0, 2), (99.0, 200.0, 300.0, 6)]
        with tempfile.TemporaryDirectory() as directory:
            config = _fixture_config(
                Path(directory), rows, expected_classes=((2, 1), (6, 1))
            )
            with patch.object(adapter, "_actual_clean_repository_head") as git_head, patch.object(
                adapter, "_open_source"
            ) as opened:
                with self.assertRaisesRegex(C3CommonMvsAdapterError, "production adapter"):
                    adapter.adapt_common_mvs_to_gs_local(config)
            git_head.assert_not_called()
            opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
