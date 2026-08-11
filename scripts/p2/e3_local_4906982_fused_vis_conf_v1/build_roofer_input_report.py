#!/usr/bin/env python3
"""Build the canonical portable-report payload for the Roofer input audit."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


AUDIT_ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_roofer_input_audit_v1/"
    "P2-E3-LOCAL-4906982-ROOFER-INPUT-AUDIT-v1"
)
ROOFER_VIS_ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_roofer_vis_v1/"
    "P2-E3-LOCAL-4906982-ROOFER-VIS-v1"
)
OUTPUT = AUDIT_ROOT / "report"


def main() -> None:
    audit = json.loads((AUDIT_ROOT / "metrics.json").read_text())
    roofer = json.loads((ROOFER_VIS_ROOT / "receipt.json").read_text())
    labels = {
        "MVS_SURFACE_METRIC": "All fused-mesh ray hits",
        "FUSED_VIS_CONF": "View-supported fused target",
    }
    coverage_rows = []
    detail_rows = []
    for arm, label in labels.items():
        metrics = audit["metrics"][arm]
        c2 = metrics["class_inside_footprint"]["2"]
        c6 = metrics["class_inside_footprint"]["6"]
        coverage_rows.extend(
            [
                {"arm": label, "stage": "Fused input", "xy_coverage_pct": metrics["raw_xy_coverage_pct"]},
                {"arm": label, "stage": "Class 6 after SMRF", "xy_coverage_pct": c6["xy_coverage_pct"]},
            ]
        )
        detail_rows.append(
            {
                "arm": label,
                "raw_inside_points": metrics["raw_inside_footprint_points"],
                "raw_xy_coverage_pct": metrics["raw_xy_coverage_pct"],
                "class2_points": c2["count"],
                "class2_point_fraction_pct": 100.0 * c2["inside_footprint_fraction"],
                "class6_points": c6["count"],
                "class6_xy_coverage_pct": c6["xy_coverage_pct"],
                "roofer_roof_coverage_pct": roofer["metrics"][arm]["roof_projection_coverage_pct"],
            }
        )
    generated_at = datetime.now(timezone.utc).isoformat()
    source_audit = {
        "id": "roofer_input_audit",
        "label": "20k fused and classified point-cloud audit",
        "path": "artifact://JointBuildGS/phase-payloads/p2/e3_local_4906982_roofer_input_audit_v1/P2-E3-LOCAL-4906982-ROOFER-INPUT-AUDIT-v1/metrics.json",
        "query": {
            "engine": "DuckDB over the Docker-audit derived table",
            "language": "sql",
            "sql": "SELECT arm, stage, xy_coverage_pct FROM roofer_input_coverage ORDER BY arm, stage",
            "description": "Count points inside the frozen shared footprint and compare 0.5 m XY-cell coverage before and after frozen SMRF classification.",
            "executed_at": audit["ended_at"],
            "filters": ["DEBY_LOD2_4906982", "step 20000", "shared footprint XY only", "0.5 m grid"],
            "metric_definitions": [
                "XY coverage = eligible 0.5 m cells with at least one point / cells whose center is covered by the shared footprint XY.",
                "Class fractions use all classified points whose XY lies inside the shared footprint.",
            ],
            "tables_used": ["fused_surface.laz", "classified_surface.laz", "shared_standard_footprint_4906982.geojson"],
        },
    }
    source_roofer = {
        "id": "roofer_output_audit",
        "label": "20k Roofer CityJSON area audit",
        "path": "artifact://JointBuildGS/phase-payloads/p2/e3_local_4906982_roofer_vis_v1/P2-E3-LOCAL-4906982-ROOFER-VIS-v1/receipt.json",
        "query": {
            "engine": "Docker Python CityJSON and Shapely",
            "language": "python",
            "description": "Project the actual Roofer RoofSurface faces to XY and divide their union area by the shared footprint area.",
            "executed_at": roofer["ended_at"],
            "filters": ["DEBY_LOD2_4906982", "step 20000", "actual Roofer CityJSON outputs"],
            "metric_definitions": ["Roofer roof coverage = XY union area of generated RoofSurface faces / shared footprint XY area."],
            "tables_used": ["690897_5336168.city.jsonl", "shared_standard_footprint_4906982.geojson"],
        },
    }
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "4906982 Roofer input-loss diagnosis",
            "description": "Read-only separation of fused point-cloud coverage, frozen classification, and Roofer output.",
            "generatedAt": generated_at,
            "blocks": [
                {"id": "title", "type": "markdown", "layout": "full", "body": "# 4906982 Roofer input-loss diagnosis"},
                {
                    "id": "technical_summary",
                    "type": "markdown",
                    "layout": "full",
                    "body": "## The point cloud is present; the frozen classifier removes most roof support\n\nBoth 20k fused inputs cover essentially the full footprint. After SMRF, however, 84–87% of footprint-internal points are class 2 and class-6 XY coverage falls to 18.6–22.3%. The fragmented Roofer solids therefore cannot be attributed to missing XY point-cloud coverage alone.",
                    "sourceId": "roofer_input_audit",
                },
                {"id": "coverage_chart_block", "type": "chart", "layout": "full", "chartId": "coverage_chart"},
                {
                    "id": "evidence_interpretation",
                    "type": "markdown",
                    "layout": "full",
                    "body": "## Classification loss matches the partial Roofer geometry\n\nThe raw fused clouds contain about 50k points inside the footprint and occupy almost every eligible 0.5 m cell. The class-6 subset is concentrated at edges and isolated patches, while the generated roof covers only 1.45% or 5.56% of the footprint. This is a downstream classification/readout failure layered on top of remaining GS height and outlier issues; it is not evidence that the entire GS point cloud is absent.",
                },
                {"id": "detail_table_block", "type": "table", "layout": "full", "tableId": "detail_table"},
                {
                    "id": "scope_definitions",
                    "type": "markdown",
                    "layout": "full",
                    "body": "## Scope and definitions\n\nThe cohort is one building, two current 55-view GS arms, replica R1, checkpoint 20k. Coverage uses the shared GroundSurface footprint XY only. LoD2 Z and RoofSurface geometry were not used. `fused_surface.laz` is the Roofer pre-classification input; `classified_surface.laz` is the frozen SMRF plus footprint-overlay output.",
                },
                {
                    "id": "methodology",
                    "type": "markdown",
                    "layout": "full",
                    "body": "## Methodology\n\nThe audit reads the hash-bound LAZ files in Docker, selects points whose XY lies inside the frozen footprint, and measures occupancy on a preregistered 0.5 m grid. It then decomposes the same footprint-internal classified cloud into classes 1, 2, and 6. Roofer coverage comes from the XY union of the actual generated RoofSurface faces.",
                },
                {
                    "id": "limitations",
                    "type": "markdown",
                    "layout": "full",
                    "body": "## Limitations and robustness\n\nFull XY occupancy does not prove correct roof height, normal, opacity, or surface concentration. Both fused clouds retain high-Z outliers, and most ordinary points lie in a narrow Z band. The audit identifies a concrete downstream loss mechanism but does not establish that classification is the only remaining failure. No alternative SMRF setting or Roofer rerun was executed.",
                },
                {
                    "id": "next_step",
                    "type": "markdown",
                    "layout": "full",
                    "body": "## Recommended next step\n\nRun one 55-view C4/E4-style prior-only arm: retain the current view-supported MVS depth base and identical initialization, then add the validated Existing ALS depth/normal prior. Evaluate the GS checkpoint before classification and Roofer, and keep a separate read-only classification sensitivity diagnostic. Do not change ALS initialization in the same arm.",
                },
                {
                    "id": "questions",
                    "type": "markdown",
                    "layout": "full",
                    "body": "## Further questions\n\nWould the same checkpoint yield a complete model under a LoD2-blind classification rule that preserves footprint-internal surface points? Does ALS supervision improve ordinary-surface Z and normals before readout, independent of that classification rule? These should remain separate measurements.",
                },
            ],
            "charts": [
                {
                    "id": "coverage_chart",
                    "title": "Footprint XY coverage before and after classification",
                    "subtitle": "0.5 m eligible cells; same 20k fused inputs and frozen shared footprint",
                    "type": "bar",
                    "dataset": "coverage_rows",
                    "source": source_audit,
                    "encodings": {
                        "x": {"field": "arm", "type": "nominal", "label": "55-view arm"},
                        "y": {"field": "xy_coverage_pct", "type": "quantitative", "format": "number", "label": "XY coverage", "unit": "%"},
                        "color": {"field": "stage", "type": "nominal", "label": "Pipeline stage"},
                    },
                    "yAxisTitle": "Footprint XY coverage (%)",
                    "layout": "full",
                    "maxRows": 10,
                }
            ],
            "tables": [
                {
                    "id": "detail_table",
                    "title": "Point-cloud and Roofer readout metrics",
                    "subtitle": "One row per 55-view arm at 20k; coverage denominators are the same shared footprint",
                    "dataset": "detail_rows",
                    "defaultSort": {"field": "raw_xy_coverage_pct", "direction": "desc"},
                    "density": "spacious",
                    "source": {
                        "id": "combined_pointcloud_roofer_audit",
                        "label": "Combined point-cloud and Roofer receipts",
                        "query": {
                            "engine": "DuckDB over the two Docker-audit derived tables",
                            "language": "sql",
                            "sql": "SELECT p.arm, p.raw_inside_points, p.raw_xy_coverage_pct, p.class2_point_fraction_pct, p.class6_points, p.class6_xy_coverage_pct, r.roofer_roof_coverage_pct FROM pointcloud_metrics p JOIN roofer_metrics r USING (arm) ORDER BY p.raw_xy_coverage_pct DESC",
                            "description": "Join the two arm-level point-cloud audit rows with the corresponding Roofer output coverage rows by arm.",
                            "executed_at": generated_at,
                            "filters": ["DEBY_LOD2_4906982", "step 20000", "two 55-view arms"],
                            "metric_definitions": ["Point fractions and XY coverage follow the two canonical source receipts."],
                            "tables_used": ["metrics.json", "roofer visualization receipt.json"],
                        },
                    },
                    "columns": [
                        {"field": "arm", "label": "Arm", "type": "text"},
                        {"field": "raw_inside_points", "label": "Raw points", "format": "number"},
                        {"field": "raw_xy_coverage_pct", "label": "Raw XY %", "format": "number"},
                        {"field": "class2_point_fraction_pct", "label": "Class 2 points %", "format": "number"},
                        {"field": "class6_points", "label": "Class 6 points", "format": "number"},
                        {"field": "class6_xy_coverage_pct", "label": "Class 6 XY %", "format": "number"},
                        {"field": "roofer_roof_coverage_pct", "label": "Roofer roof %", "format": "number"},
                    ],
                    "layout": "full",
                }
            ],
            "sources": [source_audit, source_roofer],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {"coverage_rows": coverage_rows, "detail_rows": detail_rows},
            "accessIssues": [],
        },
        "sources": [source_audit, source_roofer],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(OUTPUT / "artifact.json")


if __name__ == "__main__":
    main()
