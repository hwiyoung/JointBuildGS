from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image as PILImage

from src.stage2.c3_image_semantic import (
    BOX_THRESHOLD,
    COMPLETION_SCHEMA,
    CROSSWALK_BYTES,
    CROSSWALK_SHA256,
    C3SemanticError,
    INPUT_SCHEMA,
    NMS_IOU,
    PROMPTS,
    SEMANTIC_CONTRACT,
    SEMANTIC_CONTRACT_BYTES,
    SEMANTIC_CONTRACT_SHA256,
    SOURCE_ROLE,
    SemanticCandidate,
    SemanticResult,
    TEXT_THRESHOLD,
    _completion_name,
    _bind_work_namespace,
    _publish_directory_noreplace,
    build_input_manifest,
    canonical_image_names,
    load_input_manifest,
    produce,
    resolve_semantic_pixels,
    sha256_bytes,
)
from src.text_identity import canonical_lf_bytes


def _image_bytes(value: int, width: int = 4, height: int = 3) -> bytes:
    stream = BytesIO()
    PILImage.fromarray(
        np.full((height, width, 3), value, dtype=np.uint8), mode="RGB"
    ).save(stream, format="PNG")
    return stream.getvalue()


def _membership(name: str, image_id: int) -> dict[str, object]:
    return {
        "name": name,
        "relative_path": name,
        "colmap_image_id": image_id,
        "colmap_camera_model_id": 1,
        "geometric_depth_relative_path": f"{name}.geometric.bin",
    }


def _write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": INPUT_SCHEMA,
                "source_role": SOURCE_ROLE,
                "images": rows,
                "scientific_verdict": None,
            }
        ),
        encoding="utf-8",
    )


def _write_colmap(
    root: Path,
    names: list[str],
    *,
    width: int = 4,
    height: int = 3,
    depth_width: int | None = None,
    depth_height: int | None = None,
) -> tuple[Path, Path, Path]:
    sparse = root / "sparse"
    sparse.mkdir()
    cameras_bin = sparse / "cameras.bin"
    camera = (
        struct.pack("<Q", 1)
        + struct.pack("<iiQQ", 1, 1, width, height)
        + struct.pack("<dddd", 100.0, 100.0, width / 2, height / 2)
    )
    cameras_bin.write_bytes(camera)
    images = bytearray(struct.pack("<Q", len(names)))
    for image_id, name in enumerate(names, start=1):
        images.extend(struct.pack("<I", image_id))
        images.extend(struct.pack("<dddd", 1.0, 0.0, 0.0, 0.0))
        images.extend(struct.pack("<ddd", 0.0, 0.0, 0.0))
        images.extend(struct.pack("<I", 1))
        images.extend(name.encode("utf-8") + b"\x00")
        images.extend(struct.pack("<Q", 0))
    images_bin = sparse / "images.bin"
    images_bin.write_bytes(images)
    depth_root = root / "depth"
    depth_root.mkdir()
    dw = width if depth_width is None else depth_width
    dh = height if depth_height is None else depth_height
    for name in names:
        (depth_root / f"{name}.geometric.bin").write_bytes(
            f"{dw}&{dh}&1&".encode("ascii") + np.zeros((dh, dw), dtype=np.float32).tobytes()
        )
    return cameras_bin, images_bin, depth_root


def _asset_contract(root: Path) -> tuple[Path, Path, dict[str, object]]:
    lock_path = root / "lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    receipt_path = root / "asset_receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "jointbuildgs.c3_image_semantic_asset_receipt.v1",
                "contract_sha256": sha256_bytes(lock_path.read_bytes()),
                "scientific_verdict": None,
                "artifacts": {
                    "groundingdino_source": {
                        "kind": "source_tree",
                        "size_bytes": 1,
                        "sha256": "0" * 64,
                    },
                    "segment_anything_source": {
                        "kind": "source_tree",
                        "size_bytes": 2,
                        "sha256": "1" * 64,
                    },
                    "groundingdino_swint_ogc": {
                        "kind": "file",
                        "size_bytes": 10,
                        "sha256": "2" * 64,
                    },
                    "sam_vit_h": {
                        "kind": "file",
                        "size_bytes": 20,
                        "sha256": "3" * 64,
                    },
                    "bert_base_uncased": {
                        "kind": "huggingface_snapshot",
                        "size_bytes": 30,
                        "sha256": "4" * 64,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    fake_lock: dict[str, object] = {
        "runtime_environment": {"docker_image_id": "sha256:" + "3" * 64},
        "runtime_assets": {
            "groundingdino_source": {"revision": "dino"},
            "segment_anything_source": {"revision": "sam"},
            "bert_base_uncased": {"revision": "bert"},
        },
    }
    return lock_path, receipt_path, fake_lock


class _FakeInference:
    def __init__(self):
        self.calls = 0

    def __call__(self, rgb: np.ndarray) -> SemanticResult:
        self.calls += 1
        labels = np.zeros(rgb.shape[:2], dtype=np.uint8)
        labels[:, :2] = 1
        return SemanticResult(labels, ())


class C3ImageSemanticTests(unittest.TestCase):
    def test_crosswalk_constant_equals_committed_lf_blob(self):
        from src.stage2 import c3_image_semantic as semantic

        repo = semantic.REPO.resolve()
        relative = semantic.CANONICAL_CROSSWALK.relative_to(repo).as_posix()
        blob = subprocess.run(
            [
                "git",
                "-c",
                "safe.directory=",
                "-c",
                f"safe.directory={repo}",
                "-C",
                str(repo),
                "cat-file",
                "blob",
                f"HEAD:{relative}",
            ],
            check=True,
            capture_output=True,
        ).stdout
        self.assertNotIn(b"\r", blob)
        self.assertEqual((len(blob), sha256_bytes(blob)), (CROSSWALK_BYTES, CROSSWALK_SHA256))

    def test_semantic_producer_contract_canonical_identity_is_pinned(self):
        payload = canonical_lf_bytes(SEMANTIC_CONTRACT.read_bytes())
        self.assertEqual(
            (len(payload), sha256_bytes(payload)),
            (SEMANTIC_CONTRACT_BYTES, SEMANTIC_CONTRACT_SHA256),
        )

    def test_crosswalk_builds_membership_without_rgb_or_depth_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "membership.json"
            receipt = build_input_manifest(output)
            rows, _digest = load_input_manifest(output)
            self.assertEqual(len(rows), 937)
            self.assertEqual(receipt["rgb_pre_reads"], 0)
            self.assertEqual(receipt["depth_pre_reads"], 0)
            self.assertEqual(receipt["colmap_binary_pre_reads"], 0)
            self.assertTrue(all("bytes" not in row and "sha256" not in row for row in rows))

    def test_exact_prompts_thresholds_and_crosswalk(self):
        self.assertEqual(
            PROMPTS,
            {1: ("roof",), 2: ("facade", "wall"), 3: ("ground", "road", "pavement")},
        )
        self.assertEqual((BOX_THRESHOLD, TEXT_THRESHOLD, NMS_IOU), (0.30, 0.25, 0.80))
        self.assertEqual(len(canonical_image_names()), 937)

    def test_overlap_highest_score_and_exact_tie_lower_class(self):
        full = np.ones((2, 2), dtype=bool)
        one = np.array([[True, False], [False, False]], dtype=bool)
        candidates = (
            SemanticCandidate(2, "wall", "wall", 0.7, (0, 0, 2, 2), full),
            SemanticCandidate(1, "roof", "roof", 0.7, (0, 0, 2, 2), full),
            SemanticCandidate(3, "ground", "ground", 0.8, (0, 0, 1, 1), one),
        )
        labels = resolve_semantic_pixels((2, 2), candidates)
        np.testing.assert_array_equal(labels, np.array([[3, 1], [1, 1]], dtype=np.uint8))

    def test_manifest_rejects_pre_read_rgb_identity_and_wrong_exact_set(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            row = _membership("a.png", 1)
            _write_manifest(path, [{**row, "bytes": 1, "sha256": "0" * 64}])
            with self.assertRaises(C3SemanticError):
                load_input_manifest(path, ["a.png"])
            _write_manifest(path, [row])
            with self.assertRaises(C3SemanticError):
                load_input_manifest(path, ["a.png", "b.png"])

    def _common_run(
        self,
        root: Path,
        names: list[str],
        *,
        image_width: int = 4,
        camera_width: int = 4,
        depth_width: int | None = None,
    ) -> tuple[dict[str, object], _FakeInference, dict[str, object]]:
        image_root = root / "images"
        image_root.mkdir()
        rows = [_membership(name, index) for index, name in enumerate(names, start=1)]
        for index, name in enumerate(names):
            (image_root / name).write_bytes(_image_bytes(40 + index, width=image_width))
        manifest = root / "input.json"
        _write_manifest(manifest, rows)
        cameras_bin, images_bin, depth_root = _write_colmap(
            root,
            names,
            width=camera_width,
            depth_width=depth_width,
        )
        asset_root = root / "assets"
        asset_root.mkdir()
        lock_path, receipt_path, fake_lock = _asset_contract(root)
        infer = _FakeInference()
        common: dict[str, object] = {
            "image_root": image_root,
            "cameras_bin": cameras_bin,
            "images_bin": images_bin,
            "geometric_depth_root": depth_root,
            "input_manifest": manifest,
            "lock_path": lock_path,
            "asset_root": asset_root,
            "asset_receipt": receipt_path,
            "work_dir": root / "semantic_937_colmap_undistorted_r2_work",
            "device": "cpu",
            "expected_names": names,
            "test_only_allow_unbound_paths": True,
            "asset_verifier": lambda *_args: {},
            "runtime_verifier": lambda _lock: {},
            "inference_factory": lambda *_args: infer,
        }
        return common, infer, fake_lock

    def test_arbitrary_or_raw_runtime_paths_are_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common, infer, fake_lock = self._common_run(root, ["a.png"])
            common["test_only_allow_unbound_paths"] = False
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                with self.assertRaisesRegex(C3SemanticError, "runtime paths differ"):
                    produce(output_dir=root / "final", **common)
            self.assertEqual(infer.calls, 0)
            self.assertFalse(Path(common["work_dir"]).exists())

    def test_add_once_resume_and_final_undistorted_rgb_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common, infer, fake_lock = self._common_run(root, ["a.png", "b.png"])
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                first = produce(output_dir=root / "final1", **common)
            self.assertEqual(infer.calls, 2)
            self.assertEqual(first["resumption"]["new_inference_images"], 2)
            self.assertEqual(first["source_role"], SOURCE_ROLE)
            self.assertEqual(len(first["records"]), 2)
            for record in first["records"]:
                source = record["undistorted_rgb"]
                image_bytes = (Path(common["image_root"]) / record["name"]).read_bytes()
                self.assertEqual(source["sha256"], sha256_bytes(image_bytes))
                self.assertEqual(source["bytes"], len(image_bytes))
                self.assertEqual((source["width"], source["height"]), (4, 3))
                self.assertEqual(source["resize_count"], 0)
                self.assertEqual(record["geometric_depth"]["shape_matches_rgb"], True)
            with (
                patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock),
                patch(
                    "src.stage2.c3_image_semantic._read_undistorted_rgb_once",
                    side_effect=AssertionError("completed RGB must not be reopened"),
                ),
                patch(
                    "src.stage2.c3_image_semantic._read_colmap_depth_shape",
                    side_effect=AssertionError("completed depth must not be reopened"),
                ),
            ):
                second = produce(output_dir=root / "final2", **common)
            self.assertEqual(infer.calls, 2)
            self.assertEqual(second["resumption"]["reused_exact_completed_images"], 2)

            completion_receipt = (
                Path(common["work_dir"])
                / "completed"
                / _completion_name(0, "a.png")
                / "receipt.json"
            )
            tampered = json.loads(completion_receipt.read_text(encoding="utf-8"))
            tampered["schema"] = "jointbuildgs.c3_image_semantic_completion.v1"
            completion_receipt.write_text(json.dumps(tampered), encoding="utf-8")
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                with self.assertRaises(C3SemanticError):
                    produce(output_dir=root / "legacy_receipt", **common)

    def test_rgb_camera_mismatch_fails_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common, infer, fake_lock = self._common_run(
                root, ["a.png"], image_width=5, camera_width=4
            )
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                with self.assertRaisesRegex(C3SemanticError, "dimensions differ"):
                    produce(output_dir=root / "final", **common)
            self.assertEqual(infer.calls, 0)

    def test_depth_shape_mismatch_fails_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common, infer, fake_lock = self._common_run(
                root, ["a.png"], depth_width=5
            )
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                with self.assertRaisesRegex(C3SemanticError, "depth shape differs"):
                    produce(output_dir=root / "final", **common)
            self.assertEqual(infer.calls, 0)

    def test_legacy_work_namespace_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common, infer, fake_lock = self._common_run(root, ["a.png"])
            old_completed = Path(common["work_dir"]) / "completed"
            old_completed.mkdir(parents=True)
            (old_completed / "old_raw_completion").mkdir()
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                with self.assertRaisesRegex(C3SemanticError, "legacy or unbound"):
                    produce(output_dir=root / "final", **common)
            self.assertEqual(infer.calls, 0)
            self.assertFalse((Path(common["work_dir"]) / "namespace.json").exists())

    def test_completed_root_symlink_or_regular_file_fails_before_inference(self):
        for kind in ("symlink", "regular_file"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                common, infer, fake_lock = self._common_run(root, ["a.png"])
                work_dir = Path(common["work_dir"])
                _bind_work_namespace(work_dir)
                completed_root = work_dir / "completed"
                if kind == "symlink":
                    target = root / "external_completed"
                    target.mkdir()
                    completed_root.symlink_to(target, target_is_directory=True)
                else:
                    completed_root.write_text("not a directory", encoding="utf-8")
                with patch(
                    "src.stage2.c3_image_semantic.load_c3_contract",
                    return_value=fake_lock,
                ):
                    with self.assertRaisesRegex(C3SemanticError, "completed root"):
                        produce(output_dir=root / "final", **common)
                self.assertEqual(infer.calls, 0)

    def test_all_existing_expected_completions_are_prevalidated_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common, infer, fake_lock = self._common_run(root, ["a.png", "b.png"])
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                produce(output_dir=root / "final1", **common)
            completed_root = Path(common["work_dir"]) / "completed"
            shutil.rmtree(completed_root / _completion_name(0, "a.png"))
            late_receipt = completed_root / _completion_name(1, "b.png") / "receipt.json"
            value = json.loads(late_receipt.read_text(encoding="utf-8"))
            value["index"] = 99
            late_receipt.write_text(json.dumps(value), encoding="utf-8")
            with (
                patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock),
                patch(
                    "src.stage2.c3_image_semantic._read_undistorted_rgb_once",
                    side_effect=AssertionError("missing earlier RGB must not be inferred"),
                ),
            ):
                with self.assertRaisesRegex(C3SemanticError, "receipt differs"):
                    produce(output_dir=root / "final2", **common)
            self.assertEqual(infer.calls, 2)

    def test_dangling_expected_completion_symlink_fails_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common, infer, fake_lock = self._common_run(root, ["a.png"])
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                produce(output_dir=root / "final1", **common)
            completion = (
                Path(common["work_dir"]) / "completed" / _completion_name(0, "a.png")
            )
            shutil.rmtree(completion)
            completion.symlink_to(root / "missing_completion", target_is_directory=True)
            with (
                patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock),
                patch(
                    "src.stage2.c3_image_semantic._read_undistorted_rgb_once",
                    side_effect=AssertionError("dangling completion must not trigger inference"),
                ),
            ):
                with self.assertRaisesRegex(C3SemanticError, "incomplete or symlinked"):
                    produce(output_dir=root / "final2", **common)
            self.assertEqual(infer.calls, 1)

    def test_directory_publication_never_replaces_existing_empty_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "staging"
            target = root / "target"
            staging.mkdir()
            target.mkdir()
            (staging / "payload").write_text("new", encoding="utf-8")
            with self.assertRaises(C3SemanticError):
                _publish_directory_noreplace(staging, target)
            self.assertTrue(target.is_dir())
            self.assertEqual(list(target.iterdir()), [])
            self.assertTrue((staging / "payload").is_file())


if __name__ == "__main__":
    unittest.main()
