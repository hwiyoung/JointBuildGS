from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image as PILImage

from src.stage2.c3_image_semantic import (
    BOX_THRESHOLD,
    CROSSWALK_BYTES,
    CROSSWALK_SHA256,
    C3SemanticError,
    NMS_IOU,
    IMAGE_INVENTORY_BYTES,
    IMAGE_INVENTORY_SHA256,
    PROMPTS,
    SemanticCandidate,
    SemanticResult,
    TEXT_THRESHOLD,
    build_input_manifest,
    canonical_image_names,
    load_input_manifest,
    produce,
    resolve_semantic_pixels,
    sha256_bytes,
    _completion_name,
    _publish_directory_noreplace,
)


def _image_bytes(value: int) -> bytes:
    stream = BytesIO()
    PILImage.fromarray(np.full((3, 4, 3), value, dtype=np.uint8), mode="RGB").save(
        stream, format="PNG"
    )
    return stream.getvalue()


class _FakeInference:
    def __init__(self):
        self.calls = 0

    def __call__(self, rgb):
        self.calls += 1
        labels = np.zeros(rgb.shape[:2], dtype=np.uint8)
        labels[:, :2] = 1
        return SemanticResult(labels, ())


class C3ImageSemanticTests(unittest.TestCase):
    def test_crosswalk_and_inventory_constants_equal_committed_lf_blobs(self):
        from src.stage2 import c3_image_semantic as semantic

        repo = semantic.REPO.resolve()
        expected = (
            (semantic.CANONICAL_CROSSWALK, CROSSWALK_BYTES, CROSSWALK_SHA256),
            (
                semantic.CANONICAL_IMAGE_INVENTORY,
                IMAGE_INVENTORY_BYTES,
                IMAGE_INVENTORY_SHA256,
            ),
        )
        for path, size, digest in expected:
            relative = path.relative_to(repo).as_posix()
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
            self.assertEqual((len(blob), sha256_bytes(blob)), (size, digest))

    def test_compact_git_inventory_builds_exact_manifest_without_raw_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "input.json"
            receipt = build_input_manifest(output)
            rows, _digest = load_input_manifest(output)
            self.assertEqual(len(rows), 937)
            self.assertEqual(receipt["raw_image_reads"], 0)
            self.assertEqual(receipt["images_zip_reads_or_hashes"], 0)

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

    def test_manifest_rejects_non_image_fields_and_wrong_exact_set(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            row = {"name": "a.png", "relative_path": "a.png", "bytes": 1, "sha256": "0" * 64}
            path.write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.c3_image_semantic_input_manifest.v1",
                        "images": [{**row, "pose": [1, 2, 3]}],
                        "scientific_verdict": None,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(C3SemanticError):
                load_input_manifest(path, ["a.png"])
            path.write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.c3_image_semantic_input_manifest.v1",
                        "images": [row],
                        "scientific_verdict": None,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(C3SemanticError):
                load_input_manifest(path, ["a.png", "b.png"])

    def test_add_once_publication_and_resume_without_reinference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_root = root / "images"
            image_root.mkdir()
            asset_root = root / "assets"
            asset_root.mkdir()
            names = ["a.png", "b.png"]
            rows = []
            for index, name in enumerate(names):
                data = _image_bytes(40 + index)
                (image_root / name).write_bytes(data)
                rows.append(
                    {
                        "name": name,
                        "relative_path": name,
                        "bytes": len(data),
                        "sha256": sha256_bytes(data),
                    }
                )
            manifest = root / "input.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.c3_image_semantic_input_manifest.v1",
                        "images": rows,
                        "scientific_verdict": None,
                    }
                ),
                encoding="utf-8",
            )
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
                            "groundingdino_source": {"kind": "source_tree", "size_bytes": 1, "sha256": "0" * 64},
                            "segment_anything_source": {"kind": "source_tree", "size_bytes": 2, "sha256": "1" * 64},
                            "groundingdino_swint_ogc": {"kind": "file", "size_bytes": 10, "sha256": "2" * 64},
                            "sam_vit_h": {"kind": "file", "size_bytes": 20, "sha256": "3" * 64},
                            "bert_base_uncased": {"kind": "huggingface_snapshot", "size_bytes": 30, "sha256": "4" * 64},
                        }
                    }
                ),
                encoding="utf-8",
            )
            fake_lock = {
                "runtime_environment": {"docker_image_id": "sha256:" + "3" * 64},
                "runtime_assets": {
                    "groundingdino_source": {"revision": "dino"},
                    "segment_anything_source": {"revision": "sam"},
                    "bert_base_uncased": {"revision": "bert"},
                },
            }
            infer = _FakeInference()
            factory = lambda _lock, _assets, _device: infer
            verifier = lambda _lock, _lock_path, _asset_root, _receipt: {}
            common = dict(
                image_root=image_root,
                input_manifest=manifest,
                lock_path=lock_path,
                asset_root=asset_root,
                asset_receipt=receipt_path,
                work_dir=root / "work",
                device="cpu",
                expected_names=names,
                asset_verifier=verifier,
                runtime_verifier=lambda _lock: {},
                inference_factory=factory,
            )
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                first = produce(output_dir=root / "final1", **common)
                self.assertEqual(infer.calls, 2)
                self.assertEqual(first["resumption"]["new_inference_images"], 2)
                second = produce(output_dir=root / "final2", **common)
            self.assertEqual(infer.calls, 2)
            self.assertEqual(second["resumption"]["reused_exact_completed_images"], 2)
            self.assertEqual(len(list((root / "final1/masks").glob("*.png"))), 2)
            with PILImage.open(root / "final1/masks/a.png") as image:
                self.assertEqual(np.asarray(image).dtype, np.uint8)
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                with self.assertRaises(C3SemanticError):
                    produce(output_dir=root / "final1", **common)

            completion_receipt = (
                root / "work/completed" / _completion_name(0, "a.png") / "receipt.json"
            )
            tampered = json.loads(completion_receipt.read_text(encoding="utf-8"))
            tampered["index"] = 99
            completion_receipt.write_text(json.dumps(tampered), encoding="utf-8")
            with patch("src.stage2.c3_image_semantic.load_c3_contract", return_value=fake_lock):
                with self.assertRaises(C3SemanticError):
                    produce(output_dir=root / "tampered", **common)

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
