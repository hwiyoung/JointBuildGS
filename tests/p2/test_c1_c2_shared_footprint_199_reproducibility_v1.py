from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.p2.c1_c2_shared_footprint_199_v1 import reproducibility_audit as audit


class SharedFootprint199ReproducibilityV1Tests(unittest.TestCase):
    def test_cityjson_digest_ignores_metadata_and_attributes(self) -> None:
        def payload(date: str, runtime: int) -> str:
            return "\n".join([
                json.dumps({
                    "type": "CityJSON", "version": "2.0", "CityObjects": {}, "vertices": [],
                    "metadata": {"referenceDate": date},
                    "transform": {"scale": [0.1, 0.1, 0.1], "translate": [1, 2, 3]},
                }),
                json.dumps({
                    "type": "CityJSONFeature", "id": "B1", "vertices": [[0, 0, 0]],
                    "CityObjects": {"B1": {"type": "Building", "attributes": {"rf_t_run": runtime}, "geometry": []}},
                }),
            ]) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.city.jsonl"
            second = Path(directory) / "second.city.jsonl"
            first.write_text(payload("2026-08-05", 1), encoding="utf-8")
            second.write_text(payload("2026-08-06", 99), encoding="utf-8")
            self.assertEqual(
                audit.canonical_cityjson_geometry(first)["canonical_geometry_sha256"],
                audit.canonical_cityjson_geometry(second)["canonical_geometry_sha256"],
            )

    def test_cityjson_digest_changes_with_vertices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, vertex in enumerate(([0, 0, 0], [1, 0, 0])):
                path = Path(directory) / f"{index}.city.jsonl"
                path.write_text(
                    json.dumps({"type": "CityJSON", "CityObjects": {}, "vertices": [], "transform": {"scale": [1, 1, 1], "translate": [0, 0, 0]}}) + "\n" +
                    json.dumps({"type": "CityJSONFeature", "id": "B1", "vertices": [vertex], "CityObjects": {}}) + "\n",
                    encoding="utf-8",
                )
                paths.append(path)
            self.assertNotEqual(
                audit.canonical_cityjson_geometry(paths[0])["canonical_geometry_sha256"],
                audit.canonical_cityjson_geometry(paths[1])["canonical_geometry_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
