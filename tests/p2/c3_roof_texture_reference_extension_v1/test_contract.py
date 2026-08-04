from __future__ import annotations
import unittest
from scripts.p2.c3_roof_texture_reference_extension_v1.compose import load_config,validate_config


class ReferenceExtensionTest(unittest.TestCase):
    def test_config(self) -> None:
        config=load_config(); validate_config(config)
        self.assertEqual(config["presentation"]["row_count"],7)
        self.assertEqual(sum(config["execution_counters"].values()),0)


if __name__=="__main__": unittest.main()
