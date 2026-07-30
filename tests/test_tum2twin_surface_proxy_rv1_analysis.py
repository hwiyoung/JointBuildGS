"""Regression checks for the 20260728_2327 TUM2TWIN post-analysis."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.input_and_alignment.tum2twin_rv1.analyze_tum2twin_surface_proxy_rv1 import classify_surface_proxy, percentile_rank


OUTPUT = REPO / "docs/experiments/evaluation/tum2twin_surface_proxy_rv1"


def test_percentile_rank_uses_average_ties_and_inverse_order() -> None:
    values = pd.Series([1.0, 2.0, 2.0, 4.0, np.nan])
    expected = np.asarray([0.0, 0.5, 0.5, 1.0, np.nan])
    assert np.allclose(percentile_rank(values).to_numpy(), expected, equal_nan=True)
    assert np.allclose(
        percentile_rank(values, inverse=True).to_numpy(),
        1.0 - expected,
        equal_nan=True,
    )


def test_classification_population_and_stability_counts() -> None:
    frame = pd.read_csv(OUTPUT / "tables/surface_proxy_R_v1.csv", low_memory=False)
    assert len(frame) == 178
    assert frame["building_id"].nunique() == 178
    assert int(frame["surface_proxy_metric_valid"].sum()) == 135
    assert frame["surface_proxy_R_v1"].value_counts().to_dict() == {
        "RX": 93,
        "R0": 33,
        "R3": 25,
        "R1": 14,
        "R2": 13,
    }
    stable = frame["surface_proxy_R_v1"].ne("RX")
    assert (
        frame.loc[stable, "surface_proxy_R_q40"]
        == frame.loc[stable, "surface_proxy_R_q50"]
    ).all()
    assert (
        frame.loc[stable, "surface_proxy_R_q50"]
        == frame.loc[stable, "surface_proxy_R_q60"]
    ).all()
    assert not frame["surface_thickness_used_in_reliability"].any()


def test_saved_classification_matches_fresh_metric_only_recompute() -> None:
    source = pd.read_csv(
        REPO / "reports/nightly_rv1_20260728_2327/building_metrics.csv",
        low_memory=False,
    )
    expected, _ = classify_surface_proxy(source)
    actual = pd.read_csv(OUTPUT / "tables/surface_proxy_R_v1.csv", low_memory=False)
    assert expected["building_id"].tolist() == actual["building_id"].tolist()
    for field in ("completeness_score", "reliability_score", "surface_proxy_score"):
        assert np.allclose(expected[field], actual[field], equal_nan=True)
    for field in (
        "surface_proxy_R_q40",
        "surface_proxy_R_q50",
        "surface_proxy_R_q60",
        "surface_proxy_R_v1",
    ):
        assert expected[field].tolist() == actual[field].tolist()


def test_oracle_candidates_are_complete_and_group_balanced() -> None:
    payload = json.loads((OUTPUT / "tables/oracle_candidates.yaml").read_text(encoding="utf-8"))
    candidates = payload["candidates"]
    assert [item["surface_proxy_R_v1"] for item in candidates] == [
        "R0",
        "R1",
        "R1",
        "R2",
        "R2",
    ]
    assert len({item["building_id"] for item in candidates}) == 5
    assert all(item["essential_inputs_complete"] for item in candidates)
    assert all(item["missing_image_count"] == 0 for item in candidates)
    assert all(item["view_count"] >= 10 for item in candidates)


def test_manifest_records_unchanged_sources_and_nonempty_figures() -> None:
    manifest = json.loads((OUTPUT / "manifests/analysis_manifest.json").read_text(encoding="utf-8"))
    source_rows = manifest["source_snapshot_audit"]
    assert len(source_rows) == 8
    assert all(row["exists"] and row["size_match"] and row["mtime_match"] for row in source_rows)
    for name in (
        "completeness_vs_reliability.png",
        "recall_vs_precision.png",
        "surface_vs_lod2.png",
    ):
        assert (REPO / "docs/figs/tum2twin_surface_proxy_rv1" / name).stat().st_size > 50_000


if __name__ == "__main__":
    checks = [
        test_percentile_rank_uses_average_ties_and_inverse_order,
        test_classification_population_and_stability_counts,
        test_saved_classification_matches_fresh_metric_only_recompute,
        test_oracle_candidates_are_complete_and_group_balanced,
        test_manifest_records_unchanged_sources_and_nonempty_figures,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
