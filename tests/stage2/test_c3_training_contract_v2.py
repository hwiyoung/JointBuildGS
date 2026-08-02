from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import yaml

from src.stage2.train import _load_exact_view_manifest
from src.text_identity import canonical_lf_bytes


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/c3_first_wave_v2/c3_gs_image_seed0.yaml"
CROSSWALK = REPO / "artifacts/manifests/gate_s0/common_base_r2b/exact_937_member_crosswalk_v1.json"


class C3TrainingContractV2Tests(unittest.TestCase):
    def test_single_recipe_enables_image_derived_support(self):
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(cfg["seed"], 0)
        self.assertEqual(cfg["exact_view_count"], 937)
        self.assertEqual(cfg["downscale"], 1.0)
        self.assertTrue(cfg["load_depth"])
        self.assertEqual(cfg["w_depth"], 0.03)
        self.assertTrue(cfg["load_semantic"])
        self.assertEqual(cfg["w_sem"], 0.1)
        self.assertFalse(cfg["load_normal"])
        self.assertEqual(cfg["w_normal"], 0.0)
        self.assertEqual(cfg["w_nc"], 0.05)
        self.assertEqual(cfg["w_distort"], 100.0)
        self.assertEqual(cfg["distort_normalization"], "scene_scale_sq")
        self.assertEqual(cfg["structure_grouping"], "g2")
        self.assertEqual(cfg["max_gaussians"], 4_000_000)
        self.assertIsNone(cfg["scientific_verdict"])

    def test_exact_auxiliary_inventory_requires_every_view(self):
        from src.stage2.train import _validate_exact_auxiliary_inventory

        with tempfile.TemporaryDirectory() as temporary:
            semantic_dir = Path(temporary)
            (semantic_dir / "a.png").write_bytes(b"x")
            frames = [
                SimpleNamespace(name="a.jpg", depth_path=Path("a.bin")),
                SimpleNamespace(name="b.jpg", depth_path=None),
            ]
            with self.assertRaisesRegex(RuntimeError, "depth inventory is incomplete"):
                _validate_exact_auxiliary_inventory(
                    frames,
                    expected_count=2,
                    require_depth=True,
                    require_semantic=True,
                    semantic_dir=semantic_dir,
                )

            frames[1].depth_path = Path("b.bin")
            with self.assertRaisesRegex(RuntimeError, "semantic inventory is incomplete"):
                _validate_exact_auxiliary_inventory(
                    frames,
                    expected_count=2,
                    require_depth=True,
                    require_semantic=True,
                    semantic_dir=semantic_dir,
                )

            (semantic_dir / "b.png").write_bytes(b"x")
            audit = _validate_exact_auxiliary_inventory(
                frames,
                expected_count=2,
                require_depth=True,
                require_semantic=True,
                semantic_dir=semantic_dir,
            )
            self.assertEqual(audit, {"views": 2, "depth_maps": 2, "semantic_masks": 2})

    def test_exact_manifest_forces_all_937_into_training_role(self):
        digest = hashlib.sha256(canonical_lf_bytes(CROSSWALK.read_bytes())).hexdigest()
        names = _load_exact_view_manifest(
            {
                "exact_view_manifest": str(CROSSWALK),
                "exact_view_manifest_sha256": digest,
                "exact_view_count": 937,
            }
        )
        self.assertEqual(len(names or []), 937)
        self.assertEqual(len(set(names or [])), 937)

    def test_exact_manifest_uses_git_lf_identity_for_crlf_checkout(self):
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        lf = canonical_lf_bytes(CROSSWALK.read_bytes())
        digest = hashlib.sha256(lf).hexdigest()
        self.assertEqual(cfg["exact_view_manifest_sha256"], digest)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "views.json"
            path.write_bytes(lf.replace(b"\n", b"\r\n"))
            names = _load_exact_view_manifest(
                {
                    "exact_view_manifest": str(path),
                    "exact_view_manifest_sha256": digest,
                    "exact_view_count": 937,
                }
            )
            self.assertEqual(len(names or []), 937)
            path.write_bytes(lf.replace(b"\n", b"\r", 1))
            with self.assertRaisesRegex(RuntimeError, "lone carriage return"):
                _load_exact_view_manifest(
                    {
                        "exact_view_manifest": str(path),
                        "exact_view_manifest_sha256": digest,
                        "exact_view_count": 937,
                    }
                )

    def test_manifest_hash_or_count_drift_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            _load_exact_view_manifest(
                {
                    "exact_view_manifest": str(CROSSWALK),
                    "exact_view_manifest_sha256": "0" * 64,
                    "exact_view_count": 937,
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "views.json"
            path.write_text(
                json.dumps({"member_count": 2, "rows": [{"basename": "a"}, {"basename": "a"}]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "membership/count"):
                _load_exact_view_manifest(
                    {"exact_view_manifest": str(path), "exact_view_count": 2}
                )


if __name__ == "__main__":
    unittest.main()
