#!/usr/bin/env python3
"""Build the measured comparison and portable-report source artifact."""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


REPO = Path("/workspace/JointBuildGS")
ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1")
ARMS = ("MVS_SURFACE_METRIC", "FUSED_VIS_CONF")
STEPS = (7000, 12000, 15000, 20000)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def num(row: dict[str, str], key: str) -> float:
    return float(row[key])


def image_html(path: Path, caption: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        '<figure style="margin:1rem 0"><img style="width:100%;height:auto" '
        f'src="data:image/png;base64,{encoded}" alt="{caption}">'
        f'<figcaption>{caption}</figcaption></figure>'
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    checkpoint_rows = read_csv(ROOT / "checkpoint_metrics.csv")
    by_key = {(r["arm"], int(r["completed_updates"])): r for r in checkpoint_rows}
    surface = json.loads((ROOT / "mvs_surface_audit.json").read_text())
    surface_by_key = {(r["arm"], int(r["completed_updates"])): r for r in surface["rows"]}
    support = json.loads((ROOT / "fusion_support_definition.json").read_text())
    lineage = json.loads((ROOT / "e4_e6_depth_lineage.json").read_text())

    base = by_key[(ARMS[0], 20000)]
    masked = by_key[(ARMS[1], 20000)]
    base_s = surface_by_key[(ARMS[0], 20000)]
    masked_s = surface_by_key[(ARMS[1], 20000)]

    highz_chart = []
    surface_chart = []
    for step in STEPS:
        highz_chart.append({
            "checkpoint": f"{step // 1000}k",
            ARMS[0]: int(float(by_key[(ARMS[0], step)]["z_gt_650"])),
            ARMS[1]: int(float(by_key[(ARMS[1], step)]["z_gt_650"])),
        })
        surface_chart.append({
            "checkpoint": f"{step // 1000}k",
            ARMS[0]: float(surface_by_key[(ARMS[0], step)]["ordinary_point_to_plane_m_median"]),
            ARMS[1]: float(surface_by_key[(ARMS[1], step)]["ordinary_point_to_plane_m_median"]),
        })

    final_rows = []
    for arm in ARMS:
        c = by_key[(arm, 20000)]
        s = surface_by_key[(arm, 20000)]
        final_rows.append({
            "arm": arm,
            "z_gt_650": int(float(c["z_gt_650"])),
            "z_max_m": num(c, "z_max"),
            "eval_psnr_db": num(c, "eval_psnr"),
            "fusion_ge2": int(float(c["fusion_ge2"])),
            "fusion_ge3_ratio": num(c, "fusion_ge3_ratio"),
            "roofer_rmse_lod2_m": num(c, "roofer_rmse_lod22"),
            "ordinary_p2plane_median_m": float(s["ordinary_point_to_plane_m_median"]),
            "ordinary_p2plane_p95_m": float(s["ordinary_point_to_plane_m_p95"]),
            "ordinary_normal_median_deg": float(s["ordinary_normal_angle_deg_median"]),
            "ordinary_coverage": float(s["ordinary_grid_coverage_of_mvs"]),
        })

    support_train = support["groups"]["train"]
    delta_highz = int(float(masked["z_gt_650"])) - int(float(base["z_gt_650"]))
    delta_psnr = num(masked, "eval_psnr") - num(base, "eval_psnr")
    delta_roofer = num(masked, "roofer_rmse_lod22") - num(base, "roofer_rmse_lod22")
    delta_p2p = float(masked_s["ordinary_point_to_plane_m_median"]) - float(base_s["ordinary_point_to_plane_m_median"])
    delta_normal = float(masked_s["ordinary_normal_angle_deg_median"]) - float(base_s["ordinary_normal_angle_deg_median"])

    comparison = f"""# FUSED_VIS_CONF comparison

## Measured setup

- Control: `MVS_SURFACE_METRIC/R1` — every positive-finite fused mesh ray hit is supervised.
- Intervention: `FUSED_VIS_CONF/R1` — the same fused target is supervised only where native OpenMVS filtered depth/confidence supports the view and agrees within 1%.
- Exact-equal state through 7k; one new training arm; 20k maximum; same 55 views, seed, GPU, depth loss/weight/schedule, MVC/NC and densification.
- Training support: {support_train['supported']:,} pixels, {support_train['supported_fraction_fused']:.2%} of fused-valid pixels, with support in {support_train['views_with_support']}/{support_train['views']} train views.

## 20k high-Z and downstream geometry

| metric | unconditioned fused | view-supported fused | delta |
|---|---:|---:|---:|
| Gaussian Z>650 m | {int(float(base['z_gt_650'])):,} | {int(float(masked['z_gt_650'])):,} | {delta_highz:,} |
| Gaussian Z max (m) | {num(base, 'z_max'):.2f} | {num(masked, 'z_max'):.2f} | {num(masked, 'z_max')-num(base, 'z_max'):.2f} |
| Held-out PSNR (dB) | {num(base, 'eval_psnr'):.3f} | {num(masked, 'eval_psnr'):.3f} | {delta_psnr:+.3f} |
| Fusion support >=2 views | {int(float(base['fusion_ge2'])):,} | {int(float(masked['fusion_ge2'])):,} | {int(float(masked['fusion_ge2']))-int(float(base['fusion_ge2'])):,} |
| Fusion support >=3 ratio | {num(base, 'fusion_ge3_ratio'):.3%} | {num(masked, 'fusion_ge3_ratio'):.3%} | {num(masked, 'fusion_ge3_ratio')-num(base, 'fusion_ge3_ratio'):+.3%} |
| Roofer success | {base['roofer_success']} | {masked['roofer_success']} | — |
| Roofer LoD2 RMSE, evaluation-only (m) | {num(base, 'roofer_rmse_lod22'):.3f} | {num(masked, 'roofer_rmse_lod22'):.3f} | {delta_roofer:+.3f} |

## 20k ordinary surface versus filtered MVS

| metric | unconditioned fused | view-supported fused | delta |
|---|---:|---:|---:|
| point-to-plane median (m) | {float(base_s['ordinary_point_to_plane_m_median']):.4f} | {float(masked_s['ordinary_point_to_plane_m_median']):.4f} | {delta_p2p:+.4f} |
| point-to-plane p95 (m) | {float(base_s['ordinary_point_to_plane_m_p95']):.4f} | {float(masked_s['ordinary_point_to_plane_m_p95']):.4f} | {float(masked_s['ordinary_point_to_plane_m_p95'])-float(base_s['ordinary_point_to_plane_m_p95']):+.4f} |
| normal angle median (deg) | {float(base_s['ordinary_normal_angle_deg_median']):.3f} | {float(masked_s['ordinary_normal_angle_deg_median']):.3f} | {delta_normal:+.3f} |
| 1 m grid coverage | {float(base_s['ordinary_grid_coverage_of_mvs']):.3%} | {float(masked_s['ordinary_grid_coverage_of_mvs']):.3%} | {float(masked_s['ordinary_grid_coverage_of_mvs'])-float(base_s['ordinary_grid_coverage_of_mvs']):+.3%} |

## Observation and next recommendation

View-conditioned selection of the same fused metric target strongly reduced high-Z, improved ordinary positional residuals and improved the Roofer evaluation-only error, while normal median error did not improve. The measured effect therefore concerns per-view support selection, not evidence that a fused target alone is sufficient or that normals are solved. Replicate this LoD2-blind OpenMVS visibility/confidence gate on another building before adding normal supervision; do not combine it with a new loss or multiview densification in that replication.

E4/E5 were not trained with ground-truth depth: both retained the common image-derived evidence and added an existing ALS 3D prior. E6 used reference-derived LoD2 planes and is diagnostic-only. Their 937-view setup is also not directly comparable to this 55-view run.

scientific_verdict: null
"""
    (ROOT / "comparison.md").write_text(comparison)

    now = datetime.now(timezone.utc).isoformat()
    summary_dataset = [{
        "z_gt_650_reduction": -delta_highz,
        "psnr_delta_db": delta_psnr,
        "roofer_rmse_reduction_m": -delta_roofer,
        "ordinary_p2plane_reduction_m": -delta_p2p,
    }]
    image_block = image_html(
        ROOT / "representative_images/support/DJI_20241217095023_0038_D.png",
        "Raw COLMAP, globally fused target, native OpenMVS view evidence, and support-state map",
    ) + image_html(
        ROOT / "representative_images/paired/step_020000__DJI_20241217101359_0032_D.png",
        "20k held-out qualitative pair: unconditioned fused target (left) and view-supported fused target (right)",
    )
    source_prefix = "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
    sources = [
        {"id": "checkpoint", "label": "Checkpoint metrics", "path": f"{source_prefix}/checkpoint_metrics.csv", "query": {"description": "Exact 7k, 12k, 15k, and 20k checkpoint measurements", "engine": "artifact-csv", "sql": "SELECT * FROM checkpoint_metrics WHERE replica = 'R1' AND completed_updates IN (7000,12000,15000,20000)", "language": "sql", "filters": ["building=DEBY_LOD2_4906982", "replica=R1"], "metric_definitions": ["high-Z: EPSG:25832 Z > 650 m", "fusion_ge2: point supported by at least two views"], "tables_used": ["checkpoint_metrics.csv"]}},
        {"id": "surface", "label": "Filtered MVS surface audit", "path": f"{source_prefix}/mvs_surface_audit.json", "query": {"description": "Ordinary surface point/normal/coverage audit against the verified filtered OpenMVS seed", "engine": "artifact-json", "sql": "SELECT * FROM mvs_surface_audit_rows WHERE replica = 'R1' AND completed_updates IN (7000,12000,15000,20000)", "language": "sql", "filters": ["inside shared footprint", "Z <= MVS max Z + 5 m"], "metric_definitions": ["point-to-plane uses local PCA reference normal", "normal angle is sign-invariant"], "tables_used": ["mvs_surface_audit.json"]}},
        {"id": "support", "label": "Native OpenMVS support definition", "path": f"{source_prefix}/fusion_support_definition.json", "query": {"description": "Frozen pre-training visibility/confidence support gate", "engine": "artifact-json", "sql": "SELECT * FROM fusion_support_definition", "language": "sql", "filters": ["native confidence > 0", "relative depth difference < 1%"], "metric_definitions": ["support is diagnostic lineage, not independent GT"], "tables_used": ["fusion_support_definition.json", "fusion_support_metrics.csv"]}},
    ]
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "DEBY_LOD2_4906982 fused depth view-support diagnostic",
            "description": "Single-variable comparison of an unconditioned globally fused depth target and the same target gated by native OpenMVS per-view support.",
            "generatedAt": now,
            "cards": [{"id": "headline", "dataset": "summary", "sourceId": "checkpoint", "metrics": [
                {"label": "High-Z removed", "field": "z_gt_650_reduction", "format": "number"},
                {"label": "Held-out PSNR delta", "field": "psnr_delta_db", "format": "number", "signed": True},
                {"label": "Roofer RMSE reduction (m)", "field": "roofer_rmse_reduction_m", "format": "number"},
                {"label": "P2plane median reduction (m)", "field": "ordinary_p2plane_reduction_m", "format": "number"},
            ]}],
            "charts": [
                {"id": "highz", "title": "High-Z count by checkpoint", "subtitle": "EPSG:25832 Z > 650 m; lower is better", "intent": "comparison", "question": "Does view support prevent the late high-Z explosion?", "rationale": "Grouped bars preserve the discrete checkpoint comparison.", "type": "bar", "dataset": "highz", "sourceId": "checkpoint", "encodings": {"x": {"field": "checkpoint", "type": "ordinal", "label": "Completed updates"}, "y": {"fields": ["MVS_SURFACE_METRIC", "FUSED_VIS_CONF"], "type": "quantitative", "label": "Gaussian count", "format": "number"}}, "valueFormat": "number", "layout": "full"},
                {"id": "surface", "title": "Ordinary-surface point-to-plane median", "subtitle": "Against filtered OpenMVS seed; lower is better", "intent": "comparison", "question": "Did support gating improve ordinary surface position, not only outliers?", "rationale": "The same checkpoint grain is shown for both arms.", "type": "bar", "dataset": "surface", "sourceId": "surface", "encodings": {"x": {"field": "checkpoint", "type": "ordinal", "label": "Completed updates"}, "y": {"fields": ["MVS_SURFACE_METRIC", "FUSED_VIS_CONF"], "type": "quantitative", "label": "Median residual", "unit": "m", "format": "number"}}, "valueFormat": "number", "unit": "m", "layout": "full"},
            ],
            "tables": [{"id": "final", "title": "20k high-Z and ordinary-surface measurements", "dataset": "final", "sourceId": "checkpoint", "layout": "full", "density": "dense", "columns": [
                {"field": "arm", "label": "Arm", "type": "text"}, {"field": "z_gt_650", "label": "Z>650", "format": "number"}, {"field": "eval_psnr_db", "label": "PSNR dB", "format": "number"}, {"field": "fusion_ge2", "label": "Fusion >=2", "format": "number"}, {"field": "roofer_rmse_lod2_m", "label": "Roofer RMSE m", "format": "number"}, {"field": "ordinary_p2plane_median_m", "label": "P2plane med m", "format": "number"}, {"field": "ordinary_normal_median_deg", "label": "Normal med deg", "format": "number"}, {"field": "ordinary_coverage", "label": "Coverage", "format": "percent"},
            ]}],
            "sources": sources,
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# Fused depth view-support diagnostic\n\nDEBY_LOD2_4906982, 55 fixed views, one new training arm. `scientific_verdict: null`"},
                {"id": "summary", "type": "markdown", "body": "## Technical summary\n\nThe same fused metric target behaved very differently when limited to native per-view OpenMVS support. High-Z and ordinary positional residuals improved, while normal median error did not."},
                {"id": "metrics", "type": "metric-strip", "cardIds": ["headline"]},
                {"id": "highz-chart", "type": "chart", "chartId": "highz"},
                {"id": "surface-chart", "type": "chart", "chartId": "surface"},
                {"id": "visuals", "type": "html", "body": image_block},
                {"id": "scope", "type": "markdown", "body": f"## Scope, data, and definitions\n\nThe control supervises every positive-finite fused mesh ray hit. The intervention keeps the target unchanged but requires native filtered depth/confidence and <1% native/fused relative disagreement. Train support was {support_train['supported_fraction_fused']:.2%} of fused-valid pixels in {support_train['views_with_support']}/{support_train['views']} views. Support is lineage evidence, not independent ground truth."},
                {"id": "table", "type": "table", "tableId": "final"},
                {"id": "method", "type": "markdown", "body": "## Methodology and experimental design\n\nBoth arms share the exact 7k full state, sparse initialization, expected-depth L1, weight and schedule, MVC/NC, densification, 47/8 view roles, seed and GPU. Only the pre-frozen depth-valid mask changes. LoD2 Z and roof geometry are evaluation-only."},
                {"id": "limitations", "type": "markdown", "body": "## Limitations and robustness\n\nThis is one building and one replica. The filtered MVS seed is a process-relative reference, not independent GT. Roofer LoD2 error is evaluation-only. One training view had no support and therefore received RGB/MVC but no depth loss."},
                {"id": "next", "type": "markdown", "body": "## Recommended next step\n\nReplicate the same frozen, LoD2-blind native visibility/confidence gate on another building. Keep the target, loss and densification fixed. Because position improved but normal median did not, defer any normal-supervision experiment until the support-gate replication is measured."},
                {"id": "questions", "type": "markdown", "body": f"## Further questions\n\n- Does the support-mask effect reproduce outside DEBY_LOD2_4906982?\n- Is the slight normal-median regression ({delta_normal:+.3f} deg at 20k) stable across views and buildings?\n- Can the no-support train view be replaced without regenerating the frozen 55-view crop?"},
            ],
        },
        "snapshot": {"version": 1, "generatedAt": now, "status": "ready", "datasets": {"summary": summary_dataset, "highz": highz_chart, "surface": surface_chart, "final": final_rows}},
        "sources": sources,
        "scientific_verdict": None,
    }
    (ROOT / "artifact.json").write_text(json.dumps(artifact, indent=2) + "\n")
    (ROOT / "chart_map.json").write_text(json.dumps({"highz": {"dataset": "checkpoint_metrics.csv", "fields": ["completed_updates", "z_gt_650"]}, "surface": {"dataset": "mvs_surface_audit.json", "fields": ["completed_updates", "ordinary_point_to_plane_m_median"]}, "scientific_verdict": None}, indent=2) + "\n")

    contract_path = ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED", "training_experiments_started": 1, "scientific_verdict": None})
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    refreshed = {}
    for relative in provenance.get("source_config_sha256", {}):
        path = REPO / relative
        refreshed[relative] = sha256(path) if path.is_file() else None
    for relative in (
        "scripts/p2/e3_local_4906982_fused_vis_conf_v1/audit_e4_e6_lineage.py",
        "scripts/p2/e3_local_4906982_fused_vis_conf_v1/build_report.py",
    ):
        refreshed[relative] = sha256(REPO / relative)
    provenance["source_config_sha256"] = refreshed
    provenance["ended_utc"] = now
    provenance.setdefault("commands", []).append("python scripts/p2/e3_local_4906982_fused_vis_conf_v1/build_report.py")
    provenance.setdefault("return_codes", []).append(0)
    provenance["scientific_verdict"] = None
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    (ROOT / "NOTES.md").write_text(f"# P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1\n\nSupport gate: `GATE_PASSED`. One new training arm completed through 20k. Checkpoint, Stage 3, Roofer, ordinary-surface and qualitative measurements completed.\n\n20k Z>650: {int(float(base['z_gt_650'])):,} -> {int(float(masked['z_gt_650'])):,}. Roofer evaluation-only RMSE: {num(base, 'roofer_rmse_lod22'):.3f} -> {num(masked, 'roofer_rmse_lod22'):.3f} m. Ordinary point-to-plane median: {float(base_s['ordinary_point_to_plane_m_median']):.4f} -> {float(masked_s['ordinary_point_to_plane_m_median']):.4f} m. Ordinary normal median: {float(base_s['ordinary_normal_angle_deg_median']):.3f} -> {float(masked_s['ordinary_normal_angle_deg_median']):.3f} deg.\n\nE4/E5 used image-derived evidence plus existing ALS, not GT depth. E6 was reference-derived diagnostic.\n\nscientific_verdict: null\n")
    print(comparison)


if __name__ == "__main__":
    main()
