from __future__ import annotations

import unittest

from scripts.p2.utarget199_c1_c4_matrix_v1.render import load_config, verify_config


class UTarget199C1C4MatrixTest(unittest.TestCase):
    def test_contract_is_exact_199_and_keeps_null_boundary(self) -> None:
        config = load_config()
        verify_config(config)
        self.assertEqual(config["scope"]["building_count"], 199)
        self.assertEqual(config["presentation"]["separate_principal_section_pages"], 0)
        self.assertEqual(config["presentation"]["c5_state"], "NOT_RUN")
        self.assertIsNone(config["official_G3_G4_PASS_usable"])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()
