from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from src.stage2.c3_image_semantic_assets import (
    BASE_IMAGE_ID,
    C3AssetError,
    EXPECTED_ASSETS,
    RECEIPT_SCHEMA,
    TARGET_IMAGE_ID,
    _publish_directory_noreplace,
    _receipt_row,
    audit_c3_runtime,
    load_c3_contract,
    verify_c3_asset_receipt,
)
from src.stage2.pilot_plane_mask_producer import sha256_file


REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "configs/stage2/c3_image_semantic_runtime_v1.json"


def _git(arguments: list[str], root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _source(root: Path, filename: str) -> str:
    root.mkdir(parents=True)
    _git(["init", "-q"], root)
    (root / filename).parent.mkdir(parents=True, exist_ok=True)
    (root / filename).write_text("locked\n", encoding="utf-8")
    _git(["add", filename], root)
    _git(
        [
            "-c",
            "user.name=JointBuildGS test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        root,
    )
    return _git(["rev-parse", "HEAD"], root)


class C3ImageSemanticAssetTests(unittest.TestCase):
    def test_canonical_contract_pins_new_remote_runtime_and_weight_identities(self):
        contract = load_c3_contract(CONTRACT)
        runtime = contract["runtime_environment"]
        self.assertEqual(runtime["base_docker_image_id"], BASE_IMAGE_ID)
        self.assertEqual(runtime["docker_image_id"], TARGET_IMAGE_ID)
        self.assertEqual(
            contract["runtime_assets"]["groundingdino_swint_ogc"]["size_bytes"],
            693_997_677,
        )
        self.assertEqual(
            contract["runtime_assets"]["sam_vit_h"]["sha256"],
            "a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e",
        )
        self.assertIsNone(contract["scientific_verdict"])
        self.assertEqual(
            sha256_file(REPO / "requirements-c3-semantic.txt"),
            runtime["runtime_requirements_sha256"],
        )
        self.assertEqual(
            sha256_file(REPO / "Dockerfile.c3-semantic"),
            "a7b474d3577f66649e6d5c83ad846592e5434b635a65a7bd903c68579dc422e2",
        )

    def test_contract_rejects_historical_runtime_id(self):
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
        value["runtime_environment"]["docker_image_id"] = (
            "sha256:3622911fb15eb2f460637f5c3f7f34f2790f5957b0475d1827d6c0a3e5dc88b1"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(C3AssetError):
                load_c3_contract(path)

    def _synthetic_bundle(self, root: Path):
        cache = root / "assets"
        dino = cache / "sources/DINO"
        sam = cache / "sources/SAM"
        dino_revision = _source(dino, "dino.py")
        sam_revision = _source(sam, "sam.py")
        dino_weight = cache / "weights/dino.pth"
        sam_weight = cache / "weights/sam.pth"
        dino_weight.parent.mkdir(parents=True)
        dino_weight.write_bytes(b"dino-weight")
        sam_weight.write_bytes(b"sam-weight")
        bert = cache / "snapshots/bert"
        bert.mkdir(parents=True)
        for filename in ("config.json", "tokenizer.json", "model.safetensors"):
            (bert / filename).write_text(filename, encoding="utf-8")

        assets = {
            "groundingdino_source": {
                "kind": "source_tree",
                "repository": "https://example.invalid/dino.git",
                "revision": dino_revision,
                "cache_relative_path": "sources/DINO",
            },
            "segment_anything_source": {
                "kind": "source_tree",
                "repository": "https://example.invalid/sam.git",
                "revision": sam_revision,
                "cache_relative_path": "sources/SAM",
            },
            "groundingdino_swint_ogc": {
                "kind": "file",
                "url": "https://example.invalid/dino.pth",
                "cache_relative_path": "weights/dino.pth",
                "size_bytes": dino_weight.stat().st_size,
                "sha256": sha256_file(dino_weight),
            },
            "sam_vit_h": {
                "kind": "file",
                "url": "https://example.invalid/sam.pth",
                "cache_relative_path": "weights/sam.pth",
                "size_bytes": sam_weight.stat().st_size,
                "sha256": sha256_file(sam_weight),
            },
            "bert_base_uncased": {
                "kind": "huggingface_snapshot",
                "repository": "example/bert",
                "revision": "1" * 40,
                "cache_relative_path": "snapshots/bert",
                "required_files": ["config.json", "tokenizer.json"],
                "weight_file": "model.safetensors",
            },
        }
        self.assertEqual(tuple(assets), EXPECTED_ASSETS)
        contract = {
            "runtime_environment": {"docker_image_id": "sha256:" + "1" * 64},
            "runtime_assets": assets,
            "groundingdino_primary_source_evidence": {},
        }
        contract_path = root / "contract.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        rows = {
            artifact_id: _receipt_row(
                assets[artifact_id],
                cache / assets[artifact_id]["cache_relative_path"],
                cache,
            )
            for artifact_id in EXPECTED_ASSETS
        }
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "contract_sha256": sha256_file(contract_path),
            "runtime_environment": contract["runtime_environment"],
            "network_accessed": True,
            "learning_runs_started": 0,
            "inference_runs_started": 0,
            "scientific_verdict": None,
            "artifacts": rows,
        }
        receipt_path = cache / "asset_receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        return contract, contract_path, cache, receipt_path, dino

    def test_live_receipt_verification_and_dirty_source_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self._synthetic_bundle(Path(directory))
            contract, contract_path, cache, receipt_path, dino = bundle
            with patch("src.stage2.c3_image_semantic_assets._source_evidence"):
                resolved = verify_c3_asset_receipt(
                    contract, contract_path, cache, receipt_path
                )
                self.assertEqual(tuple(resolved), EXPECTED_ASSETS)
                (dino / "dino.py").write_text("dirty!\n", encoding="utf-8")
                with self.assertRaisesRegex(Exception, "dirty"):
                    verify_c3_asset_receipt(contract, contract_path, cache, receipt_path)

    def test_legacy_receipt_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, contract_path, cache, receipt_path, _dino = self._synthetic_bundle(
                Path(directory)
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["schema"] = "jointbuildgs.pilot_1wave.mask_producer_asset_receipt.v1"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaises(C3AssetError):
                verify_c3_asset_receipt(contract, contract_path, cache, receipt_path)

    def test_asset_publication_never_replaces_existing_empty_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "staging"
            target = root / "target"
            staging.mkdir()
            target.mkdir()
            (staging / "asset").write_text("new", encoding="utf-8")
            with self.assertRaises(C3AssetError):
                _publish_directory_noreplace(staging, target)
            self.assertEqual(list(target.iterdir()), [])
            self.assertTrue((staging / "asset").is_file())

    def test_runtime_audit_enforces_cuda_arch_and_ignored_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dino = root / "DINO"
            sam = root / "SAM"
            _source(dino, "groundingdino/source.py")
            (dino / ".gitignore").write_text("groundingdino/_C*.so\n", encoding="utf-8")
            _git(["add", ".gitignore"], dino)
            _git(
                [
                    "-c",
                    "user.name=JointBuildGS test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "ignore extension",
                ],
                dino,
            )
            dino_revision = _git(["rev-parse", "HEAD"], dino)
            sam_revision = _source(sam, "sam.py")
            extension = dino / "groundingdino/_Ctest.so"
            extension.write_bytes(b"compiled")
            requirements = root / "requirements.txt"
            requirements.write_text("locked\n", encoding="utf-8")
            contract = {
                "runtime_environment": {
                    "docker_image_id": TARGET_IMAGE_ID,
                    "runtime_requirements_path": str(requirements),
                    "runtime_requirements_sha256": sha256_file(requirements),
                    "groundingdino_source_root": str(dino),
                    "segment_anything_source_root": str(sam),
                },
                "runtime_dependency_gate": {
                    "required_python_version": "3.11.15",
                    "required_distribution_versions": {"fixture": "1.0"},
                    "required_groundingdino_extension_glob": "groundingdino/_C*.so",
                    "compiled_torch_cuda": "12.1",
                    "compiled_cuda_arch": "8.6",
                },
            }
            patches = (
                patch("src.stage2.c3_image_semantic_assets.DINO_REVISION", dino_revision),
                patch("src.stage2.c3_image_semantic_assets.SAM_REVISION", sam_revision),
                patch("src.stage2.c3_image_semantic_assets.platform.python_version", return_value="3.11.15"),
                patch("src.stage2.c3_image_semantic_assets.importlib.metadata.version", return_value="1.0"),
            )
            with patches[0], patches[1], patches[2], patches[3], patch.dict(
                os.environ, {"TORCH_CUDA_ARCH_LIST": "8.6"}
            ):
                result = audit_c3_runtime(contract)
                self.assertEqual(result["groundingdino_extension"]["torch_cuda"], "12.1")
                self.assertTrue(result["groundingdino_extension"]["git_ignored"])
            with patches[0], patches[1], patches[2], patches[3], patch.dict(
                os.environ, {"TORCH_CUDA_ARCH_LIST": "7.5"}
            ):
                with self.assertRaises(C3AssetError):
                    audit_c3_runtime(contract)


if __name__ == "__main__":
    unittest.main()
