import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repo_inventory.py"
SPEC = importlib.util.spec_from_file_location("repo_inventory", MODULE_PATH)
assert SPEC and SPEC.loader
repo_inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = repo_inventory
SPEC.loader.exec_module(repo_inventory)


class RepoInventoryUnitTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "family_rules": [
                {"pattern": "(?i)boundary[_-]map", "family_id": "boundary_map"}
            ],
            "implicit_version_rules": [
                {
                    "family_id": "boundary_map",
                    "pattern": "(?i)^docs/(?:W_)?boundary_map_(?!v[0-9])",
                    "version": "v1",
                }
            ],
        }

    def test_family_rule_groups_report_table_and_manifest(self):
        paths = [
            "docs/W_boundary_map_v3_summary_20260719.md",
            "docs/boundary_map_v4_manifest.json",
            "docs/figs/boundary_map_v2/panel.png",
        ]
        self.assertEqual(
            [repo_inventory.family_id_for(path, self.config) for path in paths],
            ["boundary_map", "boundary_map", "boundary_map"],
        )

    def test_version_parser_handles_implicit_v1_and_minor_versions(self):
        self.assertEqual(
            repo_inventory.version_label_for("docs/boundary_map_metrics.csv", "boundary_map", self.config),
            "v1",
        )
        self.assertEqual(
            repo_inventory.version_label_for("docs/boundary_map_v4_1_ladder.csv", "boundary_map", self.config),
            "v4_1",
        )
        self.assertEqual(repo_inventory.version_tuple("v4_1"), (4, 1))

    def test_relative_markdown_link_resolves_from_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "figs").mkdir(parents=True)
            (root / "docs" / "figs" / "panel.png").write_bytes(b"png")
            self.assertEqual(
                repo_inventory.resolve_reference("docs/report.md", "figs/panel.png#view", root),
                ("docs/figs/panel.png", "yes"),
            )

    def test_external_and_anchor_links_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(repo_inventory.resolve_reference("docs/report.md", "https://example.com/a", root))
            self.assertIsNone(repo_inventory.resolve_reference("docs/report.md", "#section", root))

    def test_csv_path_mention_stops_at_delimiter(self):
        mentions = list(
            repo_inventory.path_mentions(
                "results/run/ckpt/step_005000.pt,23282ebc56b4cfaa,0.125"
            )
        )
        self.assertEqual(mentions, [("results/run/ckpt/step_005000.pt", 1)])

    def test_front_matter_preserves_explicit_lineage(self):
        metadata = repo_inventory.parse_front_matter(
            "---\nfamily_id: boundary_map\nstatus: canonical\nsupersedes:\n  - docs/old.md\n---\n# Report\n"
        )
        self.assertEqual(metadata["family_id"], "boundary_map")
        self.assertEqual(metadata["status"], "canonical")
        self.assertEqual(metadata["supersedes"], ["docs/old.md"])

    def test_inventory_control_paths_do_not_inventory_themselves(self):
        config = {
            "generated_paths": ["docs/catalog/DOCUMENT_CATALOG.csv"],
            "inventory_control_paths": ["docs/README.md"],
            "document_roots": ["docs"],
            "phase_document_globs": [],
        }
        self.assertFalse(repo_inventory.is_document_scope("docs/README.md", config))
        self.assertFalse(
            repo_inventory.is_document_scope("docs/catalog/DOCUMENT_CATALOG.csv", config)
        )
        self.assertTrue(repo_inventory.is_document_scope("docs/RESEARCH_CONTEXT.md", config))

    def test_filename_candidate_lineage_is_not_an_approval(self):
        rows = []
        for version, path in (
            ("v2", "docs/boundary_map_v2_metrics.csv"),
            ("v3", "docs/boundary_map_v3_metrics.csv"),
        ):
            rows.append(
                {
                    "path": path,
                    "family_id": "boundary_map",
                    "lineage_key": "boundary_map_metrics",
                    "extension": ".csv",
                    "artifact_kind": "table",
                    "version": version,
                    "proposed_status": "supporting",
                    "status_source": "default_inventory",
                    "status_note": "",
                }
            )
        relations = []
        repo_inventory.add_version_candidates(rows, relations)
        self.assertEqual(rows[0]["proposed_status"], "superseded_candidate")
        self.assertEqual(rows[1]["proposed_status"], "canonical_candidate")
        self.assertEqual(relations[0].relation, "candidate_supersedes")
        self.assertEqual(relations[0].confidence, "filename_candidate")


if __name__ == "__main__":
    unittest.main()
