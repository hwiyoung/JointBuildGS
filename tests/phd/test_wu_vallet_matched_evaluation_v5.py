"""Regression checks for equivalence gates before any UAS access."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.phd.wu_vallet_matched_v5.evaluate_regions import matched_gate, POLICY_KEYS
from scripts.phd.wu_vallet_regions_v4.evaluate_regions import sha


class MatchedProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = json.loads(Path("configs/phd/wu_vallet_matched_v5/regions_v5.json").read_text())
        self.policy_path = self.root / "policy.json"
        self.write(self.policy_path, self.policy)
        self.code = self.root / "implementation.py"
        self.code.write_text("# shared implementation\n")
        self.cfg = json.loads(Path("configs/phd/wu_vallet_matched_v5/evaluation_v5.json").read_text())
        self.cfg["matched_protocol_config"] = str(self.policy_path)
        self.cfg["core_audit_receipt"] = str(self.root / "core_audit.json")
        self.write(Path(self.cfg["core_audit_receipt"]), {"status": "PASS", "source_unchanged": True,
                   "reference_accessed": False, "tests_run": 59, "input_hashes": {str(self.code): sha(self.code)}})
        self.config = self.root / "config.json"
        shared = {key: self.policy[key] for key in POLICY_KEYS}
        for row in self.cfg["regions"]:
            rid = row["id"]
            input_root, update_root = self.root / rid / "input", self.root / rid / "update"
            input_root.mkdir(parents=True); update_root.mkdir()
            count = self.policy["regions"][rid]["frozen_view_count"]
            self.write(input_root / "selected.json", {"image_id": 1, "selection": dict(shared["view_selection"], decision_count=count)})
            (input_root / "native.npz").write_bytes(b"source")
            (update_root / "common.npz").write_bytes(b"common")
            self.write(input_root / "receipt.json", {"reference_accessed": False, "outputs": {}, "view_count": count, "decision_view_count": count})
            self.write(input_root / "protocol_receipt.json", {"shared_policy": shared, "reference_accessed": False,
                       "common_config_sha256": sha(self.policy_path), "source_hashes": {str(self.code): sha(self.code)}})
            self.write(update_root / "config.json", self.policy)
            self.write(update_root / "receipt.json", {"reference_accessed": False, "image_id": 1,
                       "domain": self.policy["regions"][rid]["domain"], "matched_core_policy": "shared",
                       "implementation_hashes": {str(self.code): sha(self.code)}, "arms": [{"name": "corrected_area1",
                       "direction_mode": "BIDIRECTIONAL", "tolerance_m": .3, "small_region_area_m2": 1., "raw_single_retained": True}]})
            row.update(input_root=str(input_root), update_root=str(update_root), view_json=str(input_root / "selected.json"),
                       native_npz=str(input_root / "native.npz"), common_npz=str(update_root / "common.npz"),
                       frozen_reference_npz=str(self.root / "MUST_NOT_BE_OPENED_UAS.npz"))
        self.write(self.config, self.cfg)

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data))

    def change(self, path, fn):
        data = json.loads(path.read_text()); fn(data); self.write(path, data)

    def test_complete_gate_does_not_open_reference(self):
        receipt = matched_gate(self.config)
        self.assertEqual(receipt["status"], "PASS_MATCHED_THREE_REGION_PROTOCOL_BEFORE_REFERENCE")
        self.assertFalse(receipt["reference_accessed"])
        self.assertEqual([r["frozen_views"] for r in receipt["regions"]], [113, 66, 157])

    def test_region_specific_arm_tolerance_is_rejected(self):
        self.change(self.root / "P3/update/receipt.json", lambda d: d["arms"][0].update(tolerance_m=.5))
        with self.assertRaisesRegex(ValueError, "Region-specific"):
            matched_gate(self.config)

    def test_partial_view_audit_is_rejected(self):
        self.change(self.root / "P3/input/receipt.json", lambda d: d.update(decision_view_count=40))
        with self.assertRaisesRegex(ValueError, "subset"):
            matched_gate(self.config)

    def test_source_changed_after_candidate_is_rejected(self):
        self.code.write_text("# modified after candidate\n")
        with self.assertRaisesRegex(ValueError, "implementation differs"):
            matched_gate(self.config)

    def test_region_specific_mesh_setting_is_rejected(self):
        self.change(self.root / "P2/update/config.json", lambda d: d["image_mesh"].update(max_edge_length_m=4.))
        with self.assertRaisesRegex(ValueError, "Update policy differs"):
            matched_gate(self.config)

    def test_raw_reference_fallback_is_rejected(self):
        self.cfg["raw_reference"] = {"path": "unused.laz"}; self.write(self.config, self.cfg)
        with self.assertRaisesRegex(ValueError, "exact frozen"):
            matched_gate(self.config)

    def test_candidate_source_must_equal_tested_source(self):
        self.change(Path(self.cfg["core_audit_receipt"]), lambda d: d["input_hashes"].update({str(self.code): "0" * 64}))
        with self.assertRaisesRegex(ValueError, "tested core source"):
            matched_gate(self.config)


if __name__ == "__main__":
    unittest.main()
