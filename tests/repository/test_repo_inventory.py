import importlib.util
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "repository" / "repo_inventory.py"
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
            repo_inventory.version_label_for("docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv", "boundary_map", self.config),
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

    def test_known_root_prefix_prefers_existing_source_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_report = root / "docs" / "experiments" / "demo" / "reports" / "report.md"
            local_report.parent.mkdir(parents=True)
            local_report.write_text("report", encoding="utf-8")
            self.assertEqual(
                repo_inventory.resolve_reference(
                    "docs/experiments/demo/README.md", "reports/report.md", root
                ),
                ("docs/experiments/demo/reports/report.md", "yes"),
            )

    def test_parenthesized_numeric_prose_is_not_a_markdown_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs" / "report.md"
            source.parent.mkdir(parents=True)
            source.write_text("bbox x[0,1](0.5 x 0.5 km)", encoding="utf-8")
            relations, _, _, _ = repo_inventory.scan_relations(
                root, "docs/report.md", {".md"}, 1000
            )
            self.assertEqual(relations, [])

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
            "generated_paths": ["docs/research/repository/DOCUMENT_CATALOG.csv"],
            "inventory_control_paths": ["docs/README.md"],
            "document_roots": ["docs"],
            "phase_document_globs": [],
        }
        self.assertFalse(repo_inventory.is_document_scope("docs/README.md", config))
        self.assertFalse(
            repo_inventory.is_document_scope("docs/research/repository/DOCUMENT_CATALOG.csv", config)
        )
        self.assertTrue(repo_inventory.is_document_scope("docs/research/RESEARCH_CONTEXT.md", config))

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

    def test_reviewed_family_map_is_validated_and_flattened(self):
        config = {
            "reviewed_family_maps": [
                {
                    "family_id": "boundary_map",
                    "decision_record": "docs/research/repository/families/BOUNDARY_MAP.md",
                    "reviewed_on": "2026-07-29",
                    "documents": [
                        {
                            "path": "docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv",
                            "status": "canonical",
                            "canonical_for": "current_ladder",
                            "reason": "reviewed",
                        }
                    ],
                }
            ]
        }
        reviewed = repo_inventory.reviewed_document_map(config)
        item = reviewed["docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv"]
        self.assertEqual(item["reviewed_family_id"], "boundary_map")
        self.assertEqual(item["decision_record"], "docs/research/repository/families/BOUNDARY_MAP.md")

    def test_reviewed_status_is_not_replaced_by_filename_candidate(self):
        rows = [
            {
                "path": "docs/boundary_map_v3_metrics.csv",
                "family_id": "boundary_map",
                "lineage_key": "boundary_map_metrics",
                "extension": ".csv",
                "artifact_kind": "table",
                "version": "v3",
                "proposed_status": "supporting",
                "status_source": "reviewed_family_map",
                "status_note": "reviewed",
            },
            {
                "path": "docs/boundary_map_v4_metrics.csv",
                "family_id": "boundary_map",
                "lineage_key": "boundary_map_metrics",
                "extension": ".csv",
                "artifact_kind": "table",
                "version": "v4",
                "proposed_status": "canonical",
                "status_source": "reviewed_family_map",
                "status_note": "reviewed",
            },
        ]
        repo_inventory.add_version_candidates(rows, [])
        self.assertEqual(rows[0]["proposed_status"], "supporting")
        self.assertEqual(rows[1]["proposed_status"], "canonical")

    def test_path_migration_resolves_old_reference_and_preserves_historical_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            new_path = root / "docs" / "experiments" / "input-and-alignment" / "boundary_map" / "tables" / "ladder.csv"
            new_path.parent.mkdir(parents=True)
            new_path.write_bytes(b"building_id,cell\nA,1\n")
            digest = hashlib.sha256(new_path.read_bytes()).hexdigest()
            manifest = root / "docs" / "research" / "repository" / "migrations" / "paths.csv"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                "migration_id,old_path,new_path,lifecycle_status,old_path_retained,sha256\n"
                f"T,docs/old.csv,docs/experiments/input-and-alignment/boundary_map/tables/ladder.csv,canonical,false,{digest}\n",
                encoding="utf-8",
            )
            migrations = repo_inventory.load_path_migrations(
                root,
                {"path_migration_manifests": ["docs/research/repository/migrations/paths.csv"]},
            )
            self.assertEqual(migrations["docs/old.csv"]["sha256"], digest)
            relation = repo_inventory.Relation(
                "docs/report.md",
                "mentions_path",
                "docs/old.csv",
                "no",
                "docs/old.csv",
                "text",
                4,
            )
            resolved = repo_inventory.apply_path_migrations(root, [relation], migrations)
            self.assertEqual(
                resolved[0].target_path,
                "docs/experiments/input-and-alignment/boundary_map/tables/ladder.csv",
            )
            self.assertEqual(resolved[0].target_exists, "yes")
            self.assertEqual(resolved[0].confidence, "text+path_migration")

    def test_current_layout_resolves_semantic_experiment_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = (
                root
                / "docs"
                / "experiments"
                / "evaluation"
                / "demo"
                / "reports"
                / "report.md"
            )
            current.parent.mkdir(parents=True)
            current.write_text("report", encoding="utf-8")
            self.assertEqual(
                repo_inventory.resolve_current_layout_path(
                    root, "docs/experiments/demo/reports/report.md"
                ),
                "docs/experiments/evaluation/demo/reports/report.md",
            )

    def test_existing_final_path_is_not_hijacked_by_historical_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "docs" / "experiments" / "family" / "table.csv"
            current.parent.mkdir(parents=True)
            current.write_text("current", encoding="utf-8")
            migrations = {
                "docs/experiments/family/table.csv": {
                    "old_path": "docs/experiments/family/table.csv",
                    "new_path": "docs/evidence/archive/family/table.csv",
                    "sha256": "0" * 64,
                }
            }
            relation = repo_inventory.Relation(
                "docs/report.md",
                "mentions_path",
                "docs/experiments/family/table.csv",
                "yes",
                "docs/experiments/family/table.csv",
                "text",
                1,
            )
            self.assertEqual(
                repo_inventory.apply_path_migrations(root, [relation], migrations),
                [relation],
            )

    def test_completed_p0_document_resolves_to_evidence_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = (
                root
                / "docs"
                / "evidence"
                / "p0-audit"
                / "w2-roofer"
                / "reports"
                / "W2_report.md"
            )
            current.parent.mkdir(parents=True)
            current.write_text("report", encoding="utf-8")
            self.assertEqual(
                repo_inventory.resolve_current_layout_path(
                    root, "phases/p0-audit/docs/W2_report.md"
                ),
                "docs/evidence/p0-audit/w2-roofer/reports/W2_report.md",
            )
            self.assertEqual(
                repo_inventory.phase_for(
                    "docs/evidence/p0-audit/w2-roofer/reports/W2_report.md"
                ),
                "P0",
            )
            self.assertEqual(
                repo_inventory.target_bucket(
                    "w2_report",
                    [{"phase": "P0", "path": current.as_posix()}],
                ),
                "docs/evidence/p0-audit/",
            )

    def test_path_migration_resolves_relative_link_from_historical_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            table = root / "docs" / "experiments" / "family" / "tables" / "table.csv"
            table.parent.mkdir(parents=True)
            table.write_bytes(b"id,value\nA,1\n")
            report = root / "docs" / "experiments" / "family" / "reports" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("[table](table.csv)\n", encoding="utf-8")
            table_digest = hashlib.sha256(table.read_bytes()).hexdigest()
            report_digest = hashlib.sha256(report.read_bytes()).hexdigest()
            migrations = {
                "docs/report.md": {
                    "old_path": "docs/report.md",
                    "new_path": "docs/experiments/family/reports/report.md",
                    "sha256": report_digest,
                },
                "docs/table.csv": {
                    "old_path": "docs/table.csv",
                    "new_path": "docs/experiments/family/tables/table.csv",
                    "sha256": table_digest,
                },
            }
            relation = repo_inventory.Relation(
                "docs/experiments/family/reports/report.md",
                "references",
                "docs/experiments/family/reports/table.csv",
                "no",
                "table.csv",
                "explicit",
                1,
            )
            resolved = repo_inventory.apply_path_migrations(root, [relation], migrations)
            self.assertEqual(resolved[0].target_path, "docs/experiments/family/tables/table.csv")
            self.assertEqual(resolved[0].target_exists, "yes")
            self.assertEqual(
                resolved[0].confidence,
                "explicit+historical_source_path+path_migration",
            )

    def test_reference_resolution_manifest_requires_exact_reviewed_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs" / "report.md"
            source.parent.mkdir(parents=True)
            source.write_text("[payload](payload.json)\n", encoding="utf-8")
            manifest = root / "docs" / "resolutions.csv"
            manifest.write_text(
                "source_path,relation,raw_target,line,class,resolved_target,verification\n"
                "docs/report.md,references,payload.json,1,missing_evidence,"
                "results/run/payload.json,absent_from_repo_and_artifact;no_safe_equivalent\n",
                encoding="utf-8",
            )
            resolved = repo_inventory.load_reference_resolutions(
                root, {"reference_resolution_manifest": "docs/resolutions.csv"}
            )
            self.assertEqual(
                resolved[("docs/report.md", "references", "payload.json")]["class"],
                "missing_evidence",
            )

    def test_reference_resolutions_keep_external_and_missing_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relations = [
                repo_inventory.Relation(
                    "docs/report.md", "references", "docs/payload.json", "no",
                    "payload.json", "explicit", 1,
                ),
                repo_inventory.Relation(
                    "docs/report.md", "references", "docs/lost.json", "no",
                    "lost.json", "explicit", 2,
                ),
            ]
            resolutions = {
                ("docs/report.md", "references", "payload.json"): {
                    "class": "external_artifact",
                    "resolved_target": "results/run/payload.json",
                    "verification": "artifact_exists",
                },
                ("docs/report.md", "references", "lost.json"): {
                    "class": "missing_evidence",
                    "resolved_target": "results/run/lost.json",
                    "verification": "absent_from_repo_and_artifact;no_safe_equivalent",
                },
            }
            resolved = repo_inventory.apply_reference_resolutions(
                root, relations, resolutions
            )
            self.assertEqual(resolved[0].target_exists, "external")
            self.assertEqual(
                resolved[0].target_path,
                "artifact://JointBuildGS/results/run/payload.json",
            )
            self.assertEqual(resolved[1].target_exists, "missing")
            self.assertEqual(
                resolved[1].target_path,
                "missing://JointBuildGS/results/run/lost.json",
            )


if __name__ == "__main__":
    unittest.main()
