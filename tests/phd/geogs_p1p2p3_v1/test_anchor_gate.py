import copy
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/seal_anchor_gate.py'
spec = importlib.util.spec_from_file_location('geogs_anchor_gate', MODULE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class AnchorGateTests(unittest.TestCase):
    def setUp(self):
        self.restore = {'status': 'EXACT_PRESTEP_RESTORE_AND_HOOK_PARITY', 'checkpoint_sha256': 'anchor'}
        self.step = {'status': 'PASS_ONE_NATIVE_STEP'}
        self.anchor = {'checkpoint_sha256': 'anchor'}
        self.rows = [{'path': path, 'equal': True, 'kind': 'scalar'} for path in (
            'rng/python/0', 'rng/numpy/0', 'rng/torch_cpu', 'iteration', 'train_order/0',
            'test_order/0', 'viewpoint_stack/0', 'optimization/iterations', 'implementation_hashes/train.py')]
        self.rows.append({'path': 'rng/torch_cuda/0', 'equal': True, 'kind': 'tensor',
                          'shape': [5056], 'dtype': 'torch.uint8', 'max_abs': 0})

    def validate(self, rows=None):
        return gate.validate_evidence(self.restore, self.step,
                                      {'entries': self.rows if rows is None else rows}, self.anchor)

    def test_later_cuda_value_and_model_differences_are_reported_without_cause_claim(self):
        self.rows[-1].update(equal=False, max_abs=32)
        self.rows.append({'path': 'model_optimizer/1', 'equal': False, 'kind': 'tensor',
                          'shape_or_dtype_mismatch': True})
        diagnostic = self.validate()
        self.assertEqual(diagnostic['status'], 'UNRESOLVED_BRANCH_DYNAMICS')
        self.assertFalse(diagnostic['all_equal'])
        self.assertFalse(diagnostic['cause_established'])
        self.assertEqual(diagnostic['nonmatching_entries'], [self.rows[-2]])

    def test_cpu_rng_cameras_iteration_optimization_and_source_remain_strict(self):
        for index in range(len(self.rows) - 1):
            with self.subTest(path=self.rows[index]['path']):
                rows = copy.deepcopy(self.rows)
                rows[index]['equal'] = False
                rows[-1]['equal'] = False
                with self.assertRaises(ValueError):
                    self.validate(rows)

    def test_cuda_rng_structure_changes_are_not_counter_evolution(self):
        invalid = (
            {'path': 'rng/torch_cuda', 'kind': 'length_mismatch'},
            {'path': 'rng/torch_cuda', 'kind': 'missing_key'},
            {'path': 'rng/torch_cuda/0', 'kind': 'tensor', 'shape_or_dtype_mismatch': True},
        )
        for row in invalid:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    self.validate(self.rows[:-1] + [dict(row, equal=False)])

    def test_initial_restore_failure_is_never_waived(self):
        self.restore['status'] = 'RESTORE_DIFFERENCES_REQUIRE_REVIEW'
        self.rows[-1]['equal'] = False
        with self.assertRaises(ValueError):
            self.validate()

    def test_one_step_failure_is_never_waived(self):
        self.step['status'] = 'FAIL_ONE_NATIVE_STEP'
        with self.assertRaises(ValueError):
            self.validate()

    def test_wrong_anchor_is_rejected(self):
        self.anchor['checkpoint_sha256'] = 'another-anchor'
        with self.assertRaises(ValueError):
            self.validate()

    def test_equal_rng_does_not_establish_model_parity(self):
        self.rows.append({'path': 'model_optimizer/1', 'equal': False, 'kind': 'tensor'})
        diagnostic = self.validate()
        self.assertEqual(diagnostic['status'], 'EXACT')
        self.assertIn('does not establish exact model trajectory parity', diagnostic['interpretation'])

    def test_optional_leading_slash_cannot_hide_a_strict_failure(self):
        rows = [{'path': '/rng/python/0', 'equal': False, 'kind': 'scalar'}]
        with self.assertRaises(ValueError):
            self.validate(rows)


if __name__ == '__main__':
    unittest.main()
