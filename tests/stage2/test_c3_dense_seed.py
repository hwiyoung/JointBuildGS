from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import src.stage2.c3_dense_seed as dense_seed
from src.stage2.c3_dense_seed import (
    C3DenseSeedError,
    DenseSeedConfig,
    REPRESENTATIVE_RULE,
    UTARGET199_NEUTRAL_CONTRACT,
    UTARGET199_NEUTRAL_MAX_DENSE_SEED_POINTS,
    UTARGET199_NEUTRAL_VOXEL_SPACINGS_M,
)


def _produce(config: DenseSeedConfig):
    return dense_seed._produce_dense_seed_for_test(config)


def _ply_bytes(points: list[tuple[float, float, float]]) -> bytes:
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment synthetic fixture\n"
        f"element vertex {len(points)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    ).encode("ascii")
    body = b"".join(struct.pack("<fff", *point) for point in points)
    return header + body


def _read_xyz(path: Path) -> np.ndarray:
    data = path.read_bytes()
    marker = b"end_header\n"
    body = data[data.index(marker) + len(marker) :]
    return np.frombuffer(body, dtype="<f4").reshape(-1, 3)


def _config(
    root: Path,
    points: list[tuple[float, float, float]],
    cap: int = 2,
    chunk_points: int = 2,
):
    source = root / "dim_dense.ply"
    payload = _ply_bytes(points)
    source.write_bytes(payload)
    return DenseSeedConfig(
        source_path=source,
        output_path=root / "selected_dense.ply",
        receipt_path=root / "selected_dense.receipt.json",
        expected_input_bytes=len(payload),
        expected_input_points=len(points),
        expected_input_sha256=hashlib.sha256(payload).hexdigest(),
        aoi_xy=(0.0, 0.0, 1.0, 1.0),
        local_offset_xyz=(0.0, 0.0, 0.0),
        local_z_range=(0.0, 1.0),
        max_dense_points=cap,
        chunk_points=chunk_points,
        temp_parent=root / "scratch",
    )


class C3DenseSeedTests(unittest.TestCase):
    def test_utarget199_neutral_contract_is_unclassified_and_memory_bounded(self):
        self.assertEqual(UTARGET199_NEUTRAL_VOXEL_SPACINGS_M, (0.5, 1.0, 2.0, 4.0))
        self.assertEqual(UTARGET199_NEUTRAL_MAX_DENSE_SEED_POINTS, 220_000)
        self.assertIn("NEUTRAL", UTARGET199_NEUTRAL_CONTRACT)

    def test_production_entry_rejects_nonexact_contract_before_git_or_source(self):
        points = [(0.01, 0.01, 0.01)]
        with tempfile.TemporaryDirectory() as directory:
            config = _config(Path(directory), points, cap=1)
            with patch.object(dense_seed, "_actual_clean_repository_head") as git_head, patch.object(
                dense_seed, "_open_source"
            ) as source_open:
                with self.assertRaisesRegex(C3DenseSeedError, "production C3 entry"):
                    dense_seed.produce_dense_seed(config)
            git_head.assert_not_called()
            source_open.assert_not_called()

    def test_repository_commit_is_actual_clean_head_not_a_caller_value(self):
        head = "c" * 40
        completed = [
            subprocess.CompletedProcess([], 0, stdout=head + "\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ]
        with patch.object(dense_seed.subprocess, "run", side_effect=completed) as run:
            self.assertEqual(dense_seed._actual_clean_repository_head(), head)
        self.assertEqual(run.call_count, 2)
        exact_repo = str(dense_seed.REPO.resolve())
        for call in run.call_args_list:
            command = call.args[0]
            self.assertEqual(
                command[:7],
                [
                    "git",
                    "-c",
                    "safe.directory=",
                    "-c",
                    f"safe.directory={exact_repo}",
                    "-C",
                    exact_repo,
                ],
            )
        dirty = [
            subprocess.CompletedProcess([], 0, stdout=head + "\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=" M src/stage2/c3_dense_seed.py\n", stderr=""),
        ]
        with patch.object(dense_seed.subprocess, "run", side_effect=dirty):
            with self.assertRaisesRegex(C3DenseSeedError, "clean repository"):
                dense_seed._actual_clean_repository_head()

    @unittest.skipUnless(os.name == "posix" and os.geteuid() == 0, "requires root in Docker")
    def test_dubious_ownership_repo_is_trusted_only_by_exact_safe_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "dubious"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "tracked.txt").write_text("exact\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=JointBuildGS test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "fixture",
                ],
                check=True,
            )
            head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            os.chown(repo, 65534, 65534)
            untrusted = subprocess.run(
                [
                    "git",
                    "-c",
                    "safe.directory=",
                    "-C",
                    str(repo),
                    "rev-parse",
                    "HEAD",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(untrusted.returncode, 0)
            self.assertIn("dubious ownership", untrusted.stderr)
            self.assertEqual(
                dense_seed._actual_clean_repository_head_for_repo(repo), head
            )

    def test_one_read_counts_selects_fine_candidate_and_records_same_pass_digests(self):
        points = [
            (0.01, 0.01, 0.01),
            (0.11, 0.01, 0.01),
            (0.41, 0.01, 0.01),
            (0.51, 0.01, 0.01),
            (2.00, 0.01, 0.01),
            (float("nan"), 0.01, 0.01),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, points)
            with patch.object(
                dense_seed, "_open_source", wraps=dense_seed._open_source
            ) as source_open:
                receipt = _produce(config)
            self.assertEqual(source_open.call_count, 1)
            self.assertEqual(
                receipt["voxel_preflight"]["candidate_dense_point_counts"],
                {"0.10": 4, "0.20": 2, "0.40": 2},
            )
            self.assertEqual(receipt["voxel_preflight"]["selected_voxel_m"], 0.20)
            self.assertEqual(receipt["input"]["natural_stream_reads"], 1)
            self.assertEqual(receipt["input"]["standalone_rehash_passes"], 0)
            self.assertEqual(receipt["output"]["standalone_rehash_passes"], 0)
            self.assertEqual(receipt["scientific_verdict"], None)
            self.assertEqual(receipt["performance_runs_started"], 0)
            self.assertEqual(
                receipt["output"]["sha256"],
                hashlib.sha256(config.output_path.read_bytes()).hexdigest(),
            )
            persisted = json.loads(config.receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted, receipt)
            np.testing.assert_allclose(
                _read_xyz(config.output_path),
                np.asarray([[0.11, 0.01, 0.01], [0.51, 0.01, 0.01]], dtype=np.float32),
            )

    def test_center_tie_uses_world_xyz_lexicographic_then_source_row(self):
        # Both points are float32-exact axis permutations and therefore have
        # exactly equal squared distance to the (0.05,0.05,0.05) voxel center.
        # Put the lexicographically larger point in the earlier source chunk.
        points = [(0.0625, 0.03125, 0.03125), (0.03125, 0.0625, 0.03125)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, points, cap=1, chunk_points=1)
            receipt = _produce(config)
            self.assertEqual(REPRESENTATIVE_RULE, receipt["voxel_preflight"]["representative_rule"])
            self.assertEqual(receipt["voxel_preflight"]["selected_voxel_m"], 0.10)
            np.testing.assert_allclose(
                _read_xyz(config.output_path),
                np.asarray([[0.03125, 0.0625, 0.03125]], dtype=np.float32),
            )

    def test_external_merge_replaces_earlier_chunk_with_nearer_representative(self):
        points = [(0.001, 0.001, 0.001), (0.049, 0.049, 0.049)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, points, cap=1, chunk_points=1)
            receipt = _produce(config)
            self.assertEqual(receipt["voxel_preflight"]["selected_voxel_m"], 0.10)
            np.testing.assert_allclose(
                _read_xyz(config.output_path),
                np.asarray([[0.049, 0.049, 0.049]], dtype=np.float32),
            )

    def test_voxel_grid_is_world_origin_then_output_is_local_xyz(self):
        points = [(0.39, 0.10, 9.50), (0.41, 0.10, 9.50)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dim_dense.ply"
            payload = _ply_bytes(points)
            source.write_bytes(payload)
            config = DenseSeedConfig(
                source_path=source,
                output_path=root / "selected_dense.ply",
                receipt_path=root / "selected_dense.receipt.json",
                expected_input_bytes=len(payload),
                expected_input_points=len(points),
                expected_input_sha256=hashlib.sha256(payload).hexdigest(),
                aoi_xy=(0.30, 0.00, 0.50, 0.20),
                local_offset_xyz=(0.15, 0.00, 10.00),
                local_z_range=(-1.0, 1.0),
                max_dense_points=2,
                chunk_points=1,
                temp_parent=root / "scratch",
            )
            receipt = _produce(config)
            # At 0.40 m the fixed world-origin grid separates x=0.39 and x=0.41.
            # Voxelizing after the 0.15 m local shift would incorrectly merge them.
            self.assertEqual(
                receipt["voxel_preflight"]["candidate_dense_point_counts"]["0.40"],
                2,
            )
            np.testing.assert_allclose(
                _read_xyz(config.output_path),
                np.asarray([[0.24, 0.10, -0.50], [0.26, 0.10, -0.50]], dtype=np.float32),
                atol=1e-6,
            )

    def test_add_once_fails_before_source_is_open(self):
        points = [(0.01, 0.01, 0.01)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, points, cap=1)
            _produce(config)
            with patch.object(dense_seed, "_open_source") as source_open:
                with self.assertRaisesRegex(C3DenseSeedError, "add-once"):
                    _produce(config)
            source_open.assert_not_called()

    def test_no_candidate_under_cap_fails_without_public_output(self):
        points = [(0.01, 0.01, 0.01), (0.81, 0.01, 0.01)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, points, cap=1)
            with self.assertRaisesRegex(C3DenseSeedError, "no frozen voxel candidate"):
                _produce(config)
            self.assertFalse(config.output_path.exists())
            self.assertFalse(config.receipt_path.exists())

    def test_truncated_or_size_mismatched_source_fails_closed(self):
        points = [(0.01, 0.01, 0.01)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, points, cap=1)
            config.source_path.write_bytes(config.source_path.read_bytes()[:-1])
            with self.assertRaisesRegex(C3DenseSeedError, "byte size differs"):
                _produce(config)
            self.assertFalse(config.output_path.exists())
            self.assertFalse(config.receipt_path.exists())


if __name__ == "__main__":
    unittest.main()
