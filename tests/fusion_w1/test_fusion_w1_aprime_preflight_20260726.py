#!/usr/bin/env python3
"""Unit and contract tests for the A-prime five-pin preflight."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_preflight_20260726.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_aprime_preflight_20260726", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)

CONFIG_PATH = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/"
      "fusion_w1_aprime_preflight_20260726.json"
)
WRAPPER = SCRIPT.parent / (
    "run_fusion_w1_aprime_preflight_20260726.sh"
)


def completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fixture"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def completed_bytes(
    stdout: bytes = b"", returncode: int = 0, stderr: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=["fixture"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class AprimeFivePinPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_config_is_receipt_only_and_has_null_verdict(self) -> None:
        preflight.validate_config(self.config)
        self.assertEqual(
            self.config["purpose"],
            "five_pin_measurement_receipt_not_a_training_launch_gate",
        )
        self.assertIsNone(self.config["verdict"])
        self.assertFalse(
            self.config["git"]["dirty_state_policy"][
                "training_launch_gate_evaluated"
            ]
        )

    def test_non_null_verdict_is_rejected(self) -> None:
        drift = copy.deepcopy(self.config)
        drift["verdict"] = "PASS"
        with self.assertRaisesRegex(preflight.PreflightError, "verdict null"):
            preflight.validate_config(drift)

    def test_dirty_state_is_classified_without_becoming_a_launch_gate(
        self,
    ) -> None:
        policy = self.config["git"]["dirty_state_policy"]
        result = preflight.classify_dirty_rows(
            [
                " M src/stage2/train.py",
                (
                    "?? phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/"
                    "training.log"
                ),
                (
                    "?? phases/p2-gsjso/scripts/fusion_w1/"
                    "fusion_w1_aprime_preflight_20260726.py"
                ),
                (
                    "?? phases/p2-gsjso/configs/fusion_w1/"
                    "fusion_w1_aprime_preprocess_20260726.json"
                ),
                "?? unrelated.txt",
            ],
            policy,
        )
        self.assertEqual(
            [row["category"] for row in result["rows"]],
            [
                "shared_T1_code_diff",
                "preexisting_user_run_artifact",
                "current_preflight_implementation_or_output",
                "concurrent_aprime_worktree_change",
                "unclassified_dirty_path",
            ],
        )

    def test_git_pin_allows_classified_dirty_state_but_requires_prereg_blob(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="aprime_preflight_git."
        ) as temporary:
            fixture = Path(temporary)
            lock = self.config["git"]
            contents: dict[str, bytes] = {}
            for spec in lock["locked_documents"]:
                path = fixture / spec["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                source = REPO / spec["path"]
                value = source.read_bytes()
                path.write_bytes(value)
                contents[spec["path"]] = value

            def fake_git(*args: str, check: bool = True):
                if args == ("branch", "--show-current"):
                    return completed(lock["expected_branch"] + "\n")
                if args == ("rev-parse", "HEAD"):
                    return completed("f" * 40 + "\n")
                if args[:2] == ("cat-file", "-t"):
                    return completed("commit\n")
                if args[:2] == ("merge-base", "--is-ancestor"):
                    return completed()
                if args[:2] == ("ls-files", "--error-unmatch"):
                    return completed(args[2] + "\n")
                if args[:2] == ("status", "--porcelain=v1"):
                    return completed(" M src/stage2/train.py\n")
                raise AssertionError(f"unexpected git call: {args}")

            def fake_git_bytes(*args: str, check: bool = True):
                self.assertEqual(args[0], "show")
                path = args[1].split(":", 1)[1]
                return completed_bytes(contents[path])

            with (
                mock.patch.object(preflight, "REPO", fixture),
                mock.patch.object(preflight, "git", side_effect=fake_git),
                mock.patch.object(
                    preflight, "git_bytes", side_effect=fake_git_bytes
                ),
            ):
                result = preflight.check_git_prereg(self.config)
            self.assertEqual(result["status"], "passed")
            dirty = result["evidence"]["dirty_worktree"]
            self.assertFalse(dirty["training_launch_gate_evaluated"])
            self.assertFalse(dirty["training_launch_authorized"])

    def test_image_inventory_uses_logical_sha256sum_stream(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="aprime_preflight_images."
        ) as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir()
            (images / "b.jpg").write_bytes(b"B")
            (images / "a.jpg").write_bytes(b"A")
            expected_stream = b""
            for name, value in (("a.jpg", b"A"), ("b.jpg", b"B")):
                digest = hashlib.sha256(value).hexdigest()
                expected_stream += (
                    f"{digest}  images/{name}\n".encode("utf-8")
                )
            with mock.patch.object(preflight, "REPO", root):
                observed, count, total = (
                    preflight.image_inventory_aggregate(images)
                )
            self.assertEqual(
                observed, hashlib.sha256(expected_stream).hexdigest()
            )
            self.assertEqual((count, total), (2, 2))

    def test_mount_pin_requires_hash_size_and_nanosecond_mtime(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="aprime_preflight_mount_a."
        ) as container_temporary, tempfile.TemporaryDirectory(
            prefix="aprime_preflight_mount_b."
        ) as host_temporary:
            container_root = Path(container_temporary)
            host_root = Path(host_temporary)
            logical = "locked/doc.md"
            value = b"locked\n"
            stamp = 1_700_000_000_123_456_789
            for root in (container_root, host_root):
                path = root / logical
                path.parent.mkdir(parents=True)
                path.write_bytes(value)
                os.utime(path, ns=(stamp, stamp))
            config = {
                "mount_freshness": {
                    "documents": [
                        {
                            "role": "fixture",
                            "path": logical,
                            "sha256": hashlib.sha256(value).hexdigest(),
                        }
                    ]
                }
            }
            with mock.patch.object(preflight, "REPO", container_root):
                result = preflight.check_mount_freshness(
                    config, host_root
                )
            self.assertEqual(result["status"], "passed")
            os.utime(host_root / logical, ns=(stamp + 1, stamp + 1))
            with mock.patch.object(preflight, "REPO", container_root):
                result = preflight.check_mount_freshness(
                    config, host_root
                )
            self.assertEqual(result["status"], "failed")

    def test_atomic_write_replaces_complete_json(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="aprime_preflight_atomic."
        ) as temporary:
            path = Path(temporary) / "receipt.json"
            preflight.atomic_write_json(path, {"verdict": None, "n": 1})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"verdict": None, "n": 1},
            )
            self.assertFalse(list(path.parent.glob(".*.tmp")))

    def test_wrapper_is_one_off_docker_with_read_only_control_bind(self) -> None:
        body = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("docker run --rm", body)
        self.assertIn("--network none", body)
        self.assertIn("--gpus", body)
        self.assertIn(
            ":/host-control/JointBuildGS:ro", body
        )
        self.assertIn("jointbuildgs:dev", body)
        self.assertNotIn("src/stage2/train.py", body)


if __name__ == "__main__":
    unittest.main()
