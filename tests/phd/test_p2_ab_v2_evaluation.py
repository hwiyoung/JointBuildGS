import unittest
import numpy as np
from src.phd.p2_ab_v2.evaluation import detail_residual, paired_detail_metrics, common_detail_fields
from src.phd.p2_ab_v2.geometry_evaluation import GeometryEvaluator
from src.phd.p2_ab_v1.evaluation import geometry_metrics


class DetailEvaluationTests(unittest.TestCase):
    def test_parallel_reference_cache_preserves_exact_geometry_definitions(self):
        rng = np.random.default_rng(19)
        reference = rng.normal(size=(200, 3))
        reference[100:] = reference[:100]
        predicted = rng.normal(size=(91, 3)) + [0., 0., 4.]
        for p, r in [(predicted, reference), (predicted[:0], reference), (predicted, reference[:0])]:
            expected, _ = geometry_metrics(p, r)
            measured = GeometryEvaluator(r, workers=4).measure(p)
            self.assertEqual(measured, expected)

    def test_disjoint_arm_support_cannot_produce_a_cross_arm_error_ranking(self):
        values = np.zeros((2, 2))
        first = np.array([[True, False], [True, False]])
        second = ~first
        arms = {name: {phase: (values, mask) for phase in ['initial', 'final']}
                for name, mask in [('a', first), ('b', second)]}
        result = common_detail_fields(arms, (values, np.ones_like(first)))
        self.assertEqual(result['common_stencils'], 0)
        self.assertEqual(result['reference_stencils'], 4)
        for arm in result['arms'].values():
            self.assertIsNone(arm['final']['error_common']['rmse_m'])
            self.assertEqual(arm['final']['missing_reference_stencils'], 2)

    def test_affine_plane_is_not_counted_as_detail(self):
        y, x = np.mgrid[:7, :7]
        d, mask = detail_residual(2*x-3*y+11.)
        self.assertTrue(mask.all())
        np.testing.assert_allclose(d, 0., atol=1e-12)

    def test_supported_local_feature_improvement_and_missing_are_separate(self):
        y, x = np.mgrid[:7, :7]
        before = np.c_[x.ravel()+.5, y.ravel()+.5, np.zeros(x.size)]
        ref = before.copy()
        ref[24, 2] = .3
        after = ref.copy()
        # Removing a remote raster cell must remain visible in the fixed
        # reference stencil denominator while the supported feature improves.
        after = after[~((after[:, 0] == 1.5) & (after[:, 1] == 1.5))]
        r = paired_detail_metrics(before, after, ref, [[0, 0], [7, 7]], (1.,))['scales'][0]
        self.assertEqual(r['initial_missing_reference_stencils'], 0)
        self.assertGreater(r['final_missing_reference_stencils'], 0)
        self.assertGreater(r['initial_error_common']['rmse_m'], 0)
        self.assertEqual(r['final_error_common']['rmse_m'], 0)


if __name__ == '__main__':
    unittest.main()
