import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/p2/reference_assessment_funnel_viewer_v1/build.py"
SPEC = importlib.util.spec_from_file_location("reference_funnel_viewer", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReferenceAssessmentFunnelViewerTest(unittest.TestCase):
    def row(self, *, cells=20, temporal="UNCHANGED_CONFIDENT", inside=True, eligible=True):
        return {
            "current_uas_reference_cell_count": cells,
            "temporal_reference_status": temporal,
            "fully_inside_roofer_aoi": inside,
            "current_uas_reference_eligible": eligible,
        }

    def test_exclusive_buckets_are_separate_from_cumulative_stages(self):
        stages, bucket = MODULE.classify(self.row(cells=0, temporal="REFERENCE_ID_ALIGNMENT_UNCERTAIN", eligible=False))
        self.assertEqual(stages, ["ALL_199"])
        self.assertEqual(bucket, "REFERENCE_ABSENT")
        stages, bucket = MODULE.classify(self.row(temporal="TEMPORAL_CHANGE_SUSPECTED", eligible=False))
        self.assertEqual(stages, ["ALL_199", "CURRENT_REFERENCE_PRESENT", "TEMPORAL_STATUS_RESOLVED"])
        self.assertEqual(bucket, "CHANGED_OUTSIDE_UNCHANGED_COHORT")
        stages, bucket = MODULE.classify(self.row(inside=False, eligible=False))
        self.assertIn("UNCHANGED_CONFIDENT", stages)
        self.assertEqual(bucket, "AOI_REPLAY_REQUIRED")
        stages, bucket = MODULE.classify(self.row())
        self.assertEqual(stages[-1], "ASSESSABLE_UNCHANGED")
        self.assertEqual(bucket, "ASSESSABLE_UNCHANGED")

    def test_viewer_exposes_required_labels_and_null_verdict(self):
        self.assertIn("누적 단계", MODULE.INDEX_HTML)
        self.assertIn("제외 사유", MODULE.INDEX_HTML)
        self.assertIn("scientific_verdict=null", MODULE.INDEX_HTML)
        self.assertIn("변화 의심 6동은 정확도 실패가 아니라", MODULE.INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
