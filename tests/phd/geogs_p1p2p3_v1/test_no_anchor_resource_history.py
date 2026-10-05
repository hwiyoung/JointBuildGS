"""Account for previous stopped attempts without inventing OOM or quality results."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "resource_summary", ROOT / "scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/summarize_resources.py")
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


class PriorResourceHistory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        self.original, self.v1, self.v2 = [self.task / p for p in ("original", "v1", "v2")]
        self.config = {"regions": ["P1", "P2"], "condition_id": "C"}
        self.config_sha = self.write(self.original / "config.json", self.config)
        for root in (self.v1, self.v2):
            self.write(root / "config.json", self.config)
        self.old_p1 = self.receipt(self.original, "P1", 1, 10)
        (self.old_p1.parent / "native.log").write_text("torch.cuda.OutOfMemoryError: fixture\n")
        self.stopped = self.receipt(self.v1, "P1", -15, 20)
        (self.stopped.parent / "native.log").write_text("Native child terminated by requested signal\n")
        self.receipt(self.original, "P2", 1, 11)
        self.stop = self.stopped.parent / "stop_intent.json"
        self.write(self.stop, {"region": "P1", "cause": "RESOURCE_TRANSFER_OPTIMIZATION"})
        self.link = {"receipt": self.reference(self.stopped), "stop_intent": self.reference(self.stop)}
        self.amendment = {"region": "P1", "arithmetic_or_scientific_controls_changed": False,
                          "scientific_verdict": None, "prior_resource_attempts": [self.link, self.link]}
        self.save_amendment()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return SUMMARY.sha_bytes(path.read_bytes())

    def reference(self, path):
        return {"path": str(path.relative_to(self.task)), "sha256": SUMMARY.sha_bytes(path.read_bytes())}

    def save_amendment(self):
        self.write(self.v2 / "amendment.json", self.amendment)

    def receipt(self, root, region, code, wall):
        path = root / "runs" / region / "C/receipt.json"
        self.write(path, {"status": "FAIL", "region": region, "condition_id": "C", "phase": "train",
                          "config_sha256": self.config_sha, "native_exit_code": code,
                          "validated_exit_code": 1, "wall_seconds": wall, "child_peak_rss_bytes": 100})
        trace = path.parent / "model/jbgs_trace.jsonl"
        trace.parent.mkdir()
        trace.write_text(json.dumps({"iteration": 100, "elapsed_seconds": 8, "gaussians": 12,
                                     "protected": 1, "peak_cuda_allocated_bytes": 22,
                                     "peak_cuda_reserved_bytes": 24}) + "\n")
        return path

    def collect(self):
        evidence = SUMMARY.Evidence()
        evidence.json(self.original / "config.json")
        return SUMMARY.closed_training_attempt_records(
            evidence, self.task, self.original, self.config, {"P1": self.v2})

    def test_intentional_stop_cost_is_separate_and_not_oom(self):
        rows = self.collect()
        self.assertEqual(len(rows), 3)  # duplicate history link does not duplicate work
        self.assertEqual(sum(r["wall_seconds"] for r in rows), 41)
        self.assertEqual({r["termination_reason"] for r in rows}, {
            "CUDA_OUT_OF_MEMORY", "INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT",
            "UNCLASSIFIED_NONPASS_TERMINATION"})
        previous = [r for r in rows if r["history_amendment_path"]]
        self.assertEqual(len(previous), 1)
        self.assertEqual(previous[0]["wall_seconds"], 20)
        self.assertFalse(previous[0]["cuda_oom_observed_in_log"])
        self.assertEqual([r["attempt_experiment"] for r in rows if r["region"] == "P2"], [str(self.original)])
        for row in rows:
            self.assertFalse(row["memory_peaks_additive"])
            self.assertFalse(row["quality_evidence"])
            self.assertIsNone(row["actual_optimizer_updates"])
            self.assertEqual(row["minimum_completed_optimizer_updates"], 100)

    def test_changed_receipt_hash_rejected(self):
        self.link["receipt"]["sha256"] = "wrong"
        self.save_amendment()
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.collect()

    def test_stop_intent_from_another_region_rejected(self):
        self.write(self.stop, {"region": "P2", "cause": "RESOURCE_TRANSFER_OPTIMIZATION"})
        self.link["stop_intent"] = self.reference(self.stop)
        self.save_amendment()
        with self.assertRaisesRegex(ValueError, "region differs"):
            self.collect()

    def test_intent_alone_does_not_override_different_actual_exit(self):
        value = json.loads(self.stopped.read_text())
        value["native_exit_code"] = 1
        self.write(self.stopped, value)
        self.link["receipt"] = self.reference(self.stopped)
        self.save_amendment()
        previous = [r for r in self.collect() if r["history_amendment_path"]][0]
        self.assertFalse(previous["intentional_resource_replacement"])
        self.assertEqual(previous["termination_reason"], "UNCLASSIFIED_NONPASS_TERMINATION")

    def initialization_link(self):
        value = json.loads(self.stopped.read_text())
        value['native_exit_code'] = 1
        self.write(self.stopped, value)
        self.stop.unlink()
        (self.stopped.parent / 'model/jbgs_trace.jsonl').unlink()
        log = self.stopped.parent / 'native.log'
        log.write_text('Camera initialization\nRuntimeError: CUDA error: out of memory\n')
        self.amendment['prior_resource_attempts'] = []
        self.amendment['prior_initialization_failure'] = {
            'receipt': self.reference(self.stopped), 'log': self.reference(log),
            'cause': 'RESOURCE_SCHEDULING_ERROR'}
        self.save_amendment()

    def test_pre_first_step_scheduling_failure_preserves_cost_without_training_oom_count(self):
        self.initialization_link()
        previous = [r for r in self.collect() if r['history_amendment_path']][0]
        self.assertEqual(previous['termination_reason'], 'RESOURCE_SCHEDULING_ERROR')
        self.assertTrue(previous['cuda_oom_observed_in_log'])
        self.assertFalse(previous['counted_as_training_cuda_oom'])
        self.assertIsNone(previous['minimum_completed_optimizer_updates'])
        self.assertEqual(previous['wall_seconds'], 20)
        self.assertFalse(previous['quality_evidence'])

    def test_initialization_failure_with_first_step_record_is_rejected(self):
        self.initialization_link()
        self.write(self.stopped.parent / 'model/jbgs_no_anchor/first_step.json', {'status': 'PASS'})
        with self.assertRaisesRegex(ValueError, 'scheduling incident'):
            self.collect()


if __name__ == "__main__":
    unittest.main()
