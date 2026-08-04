from __future__ import annotations

import unittest

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v5 import load_config, validate_config


class ConsolidatedPresentationV5Test(unittest.TestCase):
    def test_single_section_contract(self) -> None:
        config = load_config()
        validate_config(config)
        self.assertEqual(config["display"]["principal_frame"], "FOOTPRINT_PCA_SINGLE_CANONICAL_SECTION")
        self.assertEqual(config["display"]["separate_principal_section_page_count"], 0)
        self.assertFalse(config["display"]["legacy_blue_red_dual_section_visible"])

    def test_sealed_v4_hashes_are_exact(self) -> None:
        config = load_config()
        self.assertEqual(config["exact_source_hashes"]["sealed_v4_closure"], "16565a646d00afa86f1d629c081058cfa3889186d794b37d705304caac0cbc3f")
        self.assertEqual(config["exact_source_hashes"]["sealed_v4_pdf"], "675e20b076fb79791c7a05342f5e844a7fa2703357b7cc289f059dcd2582097f")

    def test_no_scientific_execution_or_verdict(self) -> None:
        config = load_config()
        prohibited = {key: value for key, value in config["execution_counters"].items() if key != "c2_display_texture_bakes"}
        self.assertTrue(all(value == 0 for value in prohibited.values()))
        self.assertIsNone(config["official_G3_G4_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()
