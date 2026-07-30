import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "repository"
    / "validate_work_readiness.py"
)
SPEC = importlib.util.spec_from_file_location("validate_work_readiness", MODULE_PATH)
assert SPEC and SPEC.loader
work_readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = work_readiness
SPEC.loader.exec_module(work_readiness)


class WorkReadinessTests(unittest.TestCase):
    def test_canonical_paths_include_only_reviewed_canonical_documents(self):
        config = {
            "canonical_documents": [{"path": "docs/current.md"}],
            "reviewed_family_maps": [
                {
                    "documents": [
                        {"path": "docs/family/current.md", "status": "canonical"},
                        {"path": "docs/family/old.md", "status": "superseded"},
                        {"path": "docs/family/table.csv", "status": "supporting"},
                    ]
                }
            ],
        }
        self.assertEqual(
            work_readiness.canonical_paths(config),
            {"docs/current.md", "docs/family/current.md"},
        )

    def test_expected_resolution_partition_is_complete(self):
        self.assertEqual(
            sum(work_readiness.EXPECTED_RESOLUTION_COUNTS.values()), 227
        )

    def test_work_entrypoint_markers_match_completed_fusion_handoff(self):
        self.assertIn("source-lock v4", work_readiness.WORK_REQUIRED_MARKERS)
        self.assertIn(
            "integrity_verified_external_unpromoted",
            work_readiness.WORK_REQUIRED_MARKERS,
        )
        self.assertNotIn(
            "does not exist on remote `main`",
            work_readiness.WORK_REQUIRED_MARKERS,
        )
        self.assertEqual(
            set(work_readiness.EXPECTED_RESOLUTION_COUNTS),
            {
                "deterministic_current_path",
                "external_artifact",
                "historical_migration",
                "missing_evidence",
            },
        )


if __name__ == "__main__":
    unittest.main()
