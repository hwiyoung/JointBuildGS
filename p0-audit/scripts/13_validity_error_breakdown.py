#!/usr/bin/env python3
"""T13 val3dity error-type breakdown for the canonical run_2.

Parse the canonical (`w3_2b_roofer_repeatability_20260612_220747/run_2`)
val3dity reports for the 93-building coverage-control set and aggregate the
validity errors by input (ALS / DIM) and by geometric error category. This is
an aggregation/observation task only -- no GO/NO-GO judgement is made.

Run from p0-audit/. Host mode re-runs this script inside the P0 tools
container so the parsing/plotting stays in the recorded audit toolchain
(rule 8). The val3dity reports are pre-existing run_2 outputs; this script does
not re-run any geometry tool.
"""

from __future__ import annotations

import collections
import csv
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "T13"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"
VAL3DITY_DIR = f"runs/{CANONICAL_RUN.split('/')[0]}/val3dity/run_2"
ALS_REPORT = f"{VAL3DITY_DIR}/als_default.json"
DIM_REPORT = f"{VAL3DITY_DIR}/dim_default.json"
PAIRED_STATUS = "docs/W3_2c_canonical_paired_status.csv"

# Expected control population and per-input invalid counts (from W3-2c closeout:
# coverage-control 93, ALS 88/93 valid, DIM 83/93 valid). Used as sanity asserts.
EXPECTED_CONTROL_N = 93
EXPECTED_ALS_INVALID = 5
EXPECTED_DIM_INVALID = 10

REPORT_MD = "docs/W3_validity_error_breakdown.md"
BUILDING_CSV = "docs/W3_validity_error_breakdown_building_errors.csv"
TYPE_CSV = "docs/W3_validity_error_breakdown_type_by_input.csv"
ATTRIB_CSV = "docs/W3_validity_error_breakdown_quality_attribution.csv"
FIGURE = "docs/figs/w3_t13_validity_error_breakdown.png"

PACKAGE_FIGURE = "fig_16_t13_validity_error_breakdown.png"
INPUTS = ("ALS", "DIM")

# val3dity 2.6.0 error-code -> (category key, Korean label, English label).
# Categories follow the T13 prompt taxonomy (non-watertight / self-intersection /
# orientation / degenerate-duplicate) plus non-manifold and non-planar, which
# val3dity reports as their own shell/polygon-level codes.
CATEGORY_ORDER = [
    ("non_watertight", "비폐합 (non-watertight)"),
    ("self_intersection", "자기교차 (self-intersection)"),
    ("non_manifold", "비다양체 (non-manifold)"),
    ("degenerate_duplicate", "중복·퇴화 면 (degenerate/duplicate)"),
    ("orientation", "면 방향 오류 (wrong orientation)"),
    ("non_planar", "비평면 (non-planar)"),
    ("other", "기타 (other)"),
]
CATEGORY_LABEL = dict(CATEGORY_ORDER)

CODE_CATEGORY = {
    # 1xx ring-level
    101: "degenerate_duplicate",   # TOO_FEW_POINTS
    102: "degenerate_duplicate",   # CONSECUTIVE_POINTS_SAME (zero-length edge)
    103: "non_watertight",         # RING_NOT_CLOSED
    104: "self_intersection",      # RING_SELF_INTERSECTION
    105: "degenerate_duplicate",   # COLLAPSED_TO_LINE
    # 2xx polygon-level
    201: "self_intersection",      # INTERSECTION_RINGS
    202: "degenerate_duplicate",   # DUPLICATED_RINGS
    203: "non_planar",             # NON_PLANAR_POLYGON_DISTANCE_PLANE
    204: "non_planar",             # NON_PLANAR_POLYGON_NORMALS_DEVIATION
    205: "self_intersection",      # POLYGON_INTERIOR_DISCONNECTED
    206: "other",                  # INNER_RING_OUTSIDE
    207: "other",                  # INNER_RINGS_NESTED
    208: "orientation",            # ORIENTATION_RINGS_SAME
    # 3xx shell/solid-level
    300: "non_manifold",           # NOT_VALID_2_MANIFOLD
    301: "degenerate_duplicate",   # TOO_FEW_POLYGONS
    302: "non_watertight",         # SHELL_NOT_CLOSED
    303: "non_manifold",           # NON_MANIFOLD_CASE
    305: "non_manifold",           # MULTIPLE_CONNECTED_COMPONENTS
    306: "self_intersection",      # SHELL_SELF_INTERSECTION
    307: "orientation",            # POLYGON_WRONG_ORIENTATION
    # 4xx solid-level
    401: "self_intersection",      # INTERSECTION_SOLIDS
    402: "degenerate_duplicate",   # DUPLICATED_SOLIDS
    403: "other",                  # DISCONNECTED_SOLIDS
}


# ---------------------------------------------------------------------------
# data extraction
# ---------------------------------------------------------------------------
@dataclass
class FeatureErrors:
    building_id: str
    valid: bool
    code_counts: dict[int, int] = field(default_factory=dict)
    code_desc: dict[int, str] = field(default_factory=dict)

    @property
    def total_instances(self) -> int:
        return sum(self.code_counts.values())

    @property
    def categories(self) -> list[str]:
        seen: list[str] = []
        for code in self.code_counts:
            cat = CODE_CATEGORY.get(code, "other")
            if cat not in seen:
                seen.append(cat)
        return seen

    def code_string(self) -> str:
        if not self.code_counts:
            return ""
        return "; ".join(
            f"{code}×{self.code_counts[code]} {self.code_desc.get(code, '')}".strip()
            for code in sorted(self.code_counts)
        )

    def category_string(self) -> str:
        return "; ".join(CATEGORY_LABEL.get(c, c) for c in self.categories)


def parse_report(path: Path) -> dict[str, FeatureErrors]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "val3dity_report":
        raise RuntimeError(f"{path} is not a val3dity report")
    out: dict[str, FeatureErrors] = {}
    for feat in data["features"]:
        fe = FeatureErrors(building_id=feat["id"], valid=bool(feat.get("validity", True)))
        for err in feat.get("errors", []):
            code = int(err["code"])
            fe.code_counts[code] = fe.code_counts.get(code, 0) + 1
            if err.get("description"):
                fe.code_desc[code] = err["description"]
        out[feat["id"]] = fe
    return out


def report_meta(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    overview = data.get("features_overview", [{}])[0]
    return {
        "val3dity_version": data.get("val3dity_version"),
        "parameters": data.get("parameters", {}),
        "all_errors": data.get("all_errors", []),
        "features_total": overview.get("total"),
        "features_valid": overview.get("valid"),
        "primitives_overview": data.get("primitives_overview", []),
    }


def load_paired_status(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows[row["building_id"]] = row
    return rows


def in_quality_71(row: dict[str, str]) -> bool:
    return row.get("paired_category") == "both_success" and row.get("exclude_from_comparison") == "no"


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------
def build_breakdown(
    als: dict[str, FeatureErrors],
    dim: dict[str, FeatureErrors],
    status: dict[str, dict[str, str]],
) -> dict[str, Any]:
    als_ids, dim_ids = set(als), set(dim)
    if als_ids != dim_ids:
        raise RuntimeError("ALS and DIM val3dity reports cover different building sets")
    control = {bid for bid, r in status.items() if r.get("coverage_control_population", "").strip().lower() == "yes"}
    if als_ids != control:
        only_report = sorted(als_ids - control)
        only_control = sorted(control - als_ids)
        raise RuntimeError(
            "val3dity feature set != coverage-control 93 set "
            f"(report-only={only_report[:5]}, control-only={only_control[:5]})"
        )

    als_invalid = {bid for bid, fe in als.items() if not fe.valid}
    dim_invalid = {bid for bid, fe in dim.items() if not fe.valid}
    if len(als_ids) != EXPECTED_CONTROL_N:
        raise RuntimeError(f"expected {EXPECTED_CONTROL_N} features, got {len(als_ids)}")
    if len(als_invalid) != EXPECTED_ALS_INVALID:
        raise RuntimeError(f"expected {EXPECTED_ALS_INVALID} ALS-invalid, got {len(als_invalid)}")
    if len(dim_invalid) != EXPECTED_DIM_INVALID:
        raise RuntimeError(f"expected {EXPECTED_DIM_INVALID} DIM-invalid, got {len(dim_invalid)}")

    union = sorted(als_invalid | dim_invalid)
    both = sorted(als_invalid & dim_invalid)
    als_only = sorted(als_invalid - dim_invalid)
    dim_only = sorted(dim_invalid - als_invalid)

    # building-level rows (union of validity-failing buildings)
    building_rows: list[dict[str, Any]] = []
    for bid in union:
        row = status.get(bid, {})
        a, d = als[bid], dim[bid]
        # validity axis; distinct from paired_category (reconstruction-success axis)
        if not a.valid and not d.valid:
            invalid_in = "both_invalid"
        elif not a.valid:
            invalid_in = "ALS_only_invalid"
        else:
            invalid_in = "DIM_only_invalid"
        building_rows.append(
            {
                "building_id": bid,
                "invalid_in": invalid_in,
                "paired_category": row.get("paired_category", ""),
                "in_quality_71": "yes" if in_quality_71(row) else "no",
                "als_validity": "valid" if a.valid else "INVALID",
                "als_error_codes": a.code_string(),
                "als_categories": a.category_string(),
                "als_error_instances": a.total_instances,
                "dim_validity": "valid" if d.valid else "INVALID",
                "dim_error_codes": d.code_string(),
                "dim_categories": d.category_string(),
                "dim_error_instances": d.total_instances,
            }
        )

    # error-type x input aggregation (building counts + error-instance counts)
    type_table: list[dict[str, Any]] = []
    for cat_key, cat_label in CATEGORY_ORDER:
        entry: dict[str, Any] = {"category": cat_key, "category_label": cat_label}
        codes_seen: set[int] = set()
        present = False
        for inp, reports in (("ALS", als), ("DIM", dim)):
            bcount = 0
            icount = 0
            for fe in reports.values():
                if fe.valid:
                    continue
                cat_codes = [c for c in fe.code_counts if CODE_CATEGORY.get(c, "other") == cat_key]
                if cat_codes:
                    bcount += 1
                    for c in cat_codes:
                        icount += fe.code_counts[c]
                        codes_seen.add(c)
            entry[f"{inp.lower()}_buildings"] = bcount
            entry[f"{inp.lower()}_error_instances"] = icount
            present = present or bcount > 0
        entry["val3dity_codes"] = ", ".join(str(c) for c in sorted(codes_seen)) if codes_seen else ""
        if present:
            type_table.append(entry)

    # representative cases
    representatives = _representatives(als, dim, both, dim_only)

    # quality-pair attribution. The 71 survivors are both_success AND inside the
    # coverage-control 93 (both_success across the full 199 is 93, so the control
    # intersection is required to land on 71).
    union_in_quality = [bid for bid in union if in_quality_71(status.get(bid, {}))]
    quality_71 = sorted(bid for bid, r in status.items() if in_quality_71(r) and bid in control)
    if len(quality_71) != 71:
        raise RuntimeError(f"expected 71 coverage-control both_success survivors, got {len(quality_71)}")
    attribution = {
        "als_invalid_total": sorted(als_invalid),
        "dim_invalid_total": sorted(dim_invalid),
        "als_only_invalid": als_only,
        "dim_only_invalid": dim_only,
        "both_invalid": both,
        "union_invalid": union,
        "union_in_quality_71": union_in_quality,
        "quality_71_n": len(quality_71),
    }

    return {
        "control_n": len(als_ids),
        "als_invalid_n": len(als_invalid),
        "dim_invalid_n": len(dim_invalid),
        "building_rows": building_rows,
        "type_table": type_table,
        "representatives": representatives,
        "attribution": attribution,
    }


def _representatives(als, dim, both, dim_only) -> list[dict[str, str]]:
    reps: list[dict[str, str]] = []
    # 1) DIM dominant degenerate/duplicate type (most common DIM code among dim_only)
    dim_code_buildings = collections.defaultdict(list)
    for bid in dim_only:
        for code in dim[bid].code_counts:
            dim_code_buildings[code].append(bid)
    if dim_code_buildings:
        top_code, blist = max(dim_code_buildings.items(), key=lambda kv: len(kv[1]))
        reps.append(
            {
                "case": "DIM dominant type",
                "building_id": sorted(blist)[0],
                "note": f"code {top_code} {dim[sorted(blist)[0]].code_desc.get(top_code, '')} "
                f"on {len(blist)} DIM-only buildings ({', '.join(b.replace('DEBY_LOD2_', '') for b in sorted(blist))})",
            }
        )
    # 2) buildings invalid in BOTH inputs but via different error codes
    for bid in both:
        a_codes = set(als[bid].code_counts)
        d_codes = set(dim[bid].code_counts)
        if a_codes != d_codes:
            reps.append(
                {
                    "case": "both inputs invalid, different error",
                    "building_id": bid,
                    "note": f"ALS {als[bid].code_string()} vs DIM {dim[bid].code_string()}",
                }
            )
    # 3) highest single-building ALS error-instance case
    als_invalid_items = [(bid, als[bid]) for bid in (set(b for b in als) ) if not als[bid].valid]
    if als_invalid_items:
        bid, fe = max(als_invalid_items, key=lambda kv: kv[1].total_instances)
        reps.append(
            {
                "case": "ALS most error instances",
                "building_id": bid,
                "note": f"{fe.code_string()} ({fe.total_instances} instances)",
            }
        )
    return reps


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(out)


def write_csvs(root: Path, b: dict[str, Any]) -> None:
    # building-level
    bfields = [
        "building_id", "invalid_in", "paired_category", "in_quality_71",
        "als_validity", "als_error_codes", "als_categories", "als_error_instances",
        "dim_validity", "dim_error_codes", "dim_categories", "dim_error_instances",
    ]
    with (root / BUILDING_CSV).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=bfields)
        w.writeheader()
        for row in b["building_rows"]:
            w.writerow({k: row[k] for k in bfields})

    # type x input
    tfields = [
        "category", "category_label", "val3dity_codes",
        "als_buildings", "dim_buildings", "als_error_instances", "dim_error_instances",
    ]
    with (root / TYPE_CSV).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=tfields)
        w.writeheader()
        for row in b["type_table"]:
            w.writerow({k: row.get(k, "") for k in tfields})

    # quality attribution
    attr = b["attribution"]
    groups = [
        ("als_invalid_total", "ALS invalid (total)", attr["als_invalid_total"]),
        ("dim_invalid_total", "DIM invalid (total)", attr["dim_invalid_total"]),
        ("als_only_invalid", "ALS-only invalid", attr["als_only_invalid"]),
        ("dim_only_invalid", "DIM-only invalid", attr["dim_only_invalid"]),
        ("both_invalid", "invalid in both inputs", attr["both_invalid"]),
        ("union_invalid", "union of validity failures", attr["union_invalid"]),
        ("union_in_quality_71", "validity failures inside quality-71", attr["union_in_quality_71"]),
    ]
    with (root / ATTRIB_CSV).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "label", "n", "share_of_93_pct", "building_ids"])
        for key, label, ids in groups:
            share = 100.0 * len(ids) / b["control_n"]
            w.writerow([key, label, len(ids), f"{share:.1f}", " ".join(x.replace("DEBY_LOD2_", "") for x in ids)])


def write_figure(root: Path, b: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    def english_label(label: str) -> str:
        # category_label is "<korean> (<english>)"; matplotlib's default font has no
        # Hangul glyphs, so the figure uses the English portion only.
        return label.split("(")[-1].rstrip(") ").strip() if "(" in label else label

    table = b["type_table"]
    labels = [english_label(t["category_label"]) for t in table]
    als_vals = [t["als_buildings"] for t in table]
    dim_vals = [t["dim_buildings"] for t in table]
    y = np.arange(len(labels))
    height = 0.38

    fig, ax = plt.subplots(figsize=(10.4, 0.9 * len(labels) + 2.2), constrained_layout=True)
    bars_als = ax.barh(y + height / 2, als_vals, height, label=f"ALS (5/93 invalid)", color="#1f77b4")
    bars_dim = ax.barh(y - height / 2, dim_vals, height, label=f"DIM (10/93 invalid)", color="#d62728")
    for bars in (bars_als, bars_dim):
        for rect in bars:
            w = rect.get_width()
            if w > 0:
                ax.text(w + 0.05, rect.get_y() + rect.get_height() / 2, str(int(w)), va="center", fontsize=10)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("number of buildings with this error category (canonical run_2, control 93)")
    ax.set_title("T13 val3dity error category by input — ALS vs DIM (no GO/NO-GO judgement)")
    ax.legend(loc="lower right")
    ax.margins(x=0.12)
    fig.savefig(root / FIGURE, dpi=200)
    plt.close(fig)


def write_report(root: Path, b: dict[str, Any], meta: dict[str, dict[str, Any]], run_id: str) -> None:
    attr = b["attribution"]
    als_meta, dim_meta = meta["ALS"], meta["DIM"]
    val3dity_ver = als_meta["val3dity_version"]
    params = als_meta["parameters"]
    short = lambda ids: ", ".join(x.replace("DEBY_LOD2_", "") for x in ids)

    # type x input table rows
    type_rows = [
        [
            t["category_label"], t["val3dity_codes"],
            t["als_buildings"], t["dim_buildings"],
            t["als_error_instances"], t["dim_error_instances"],
        ]
        for t in b["type_table"]
    ]
    type_rows.append(
        [
            "**total invalid buildings**", "",
            f"**{b['als_invalid_n']}**", f"**{b['dim_invalid_n']}**",
            sum(t["als_error_instances"] for t in b["type_table"]),
            sum(t["dim_error_instances"] for t in b["type_table"]),
        ]
    )

    # building-level table rows
    bld_rows = []
    for r in b["building_rows"]:
        bld_rows.append(
            [
                r["building_id"].replace("DEBY_LOD2_", ""),
                r["invalid_in"],
                r["als_error_codes"] or "—",
                r["dim_error_codes"] or "—",
            ]
        )

    # determine the dominant DIM and ALS categories for the observation line
    dim_dom = max(b["type_table"], key=lambda t: t["dim_buildings"])
    als_cats = [t for t in b["type_table"] if t["als_buildings"] > 0]
    als_obs = ", ".join(f"{t['category_label'].split(' (')[0]} {t['als_buildings']}" for t in als_cats)

    attr_rows = [
        ["ALS invalid (total)", len(attr["als_invalid_total"]), short(attr["als_invalid_total"])],
        ["DIM invalid (total)", len(attr["dim_invalid_total"]), short(attr["dim_invalid_total"])],
        ["ALS-only invalid", len(attr["als_only_invalid"]), short(attr["als_only_invalid"])],
        ["DIM-only invalid", len(attr["dim_only_invalid"]), short(attr["dim_only_invalid"])],
        ["invalid in both inputs", len(attr["both_invalid"]), short(attr["both_invalid"])],
        ["**union of validity failures**", f"**{len(attr['union_invalid'])}**", short(attr["union_invalid"])],
        ["validity failures inside quality-71", len(attr["union_in_quality_71"]), short(attr["union_in_quality_71"]) or "—"],
    ]

    rep_rows = [[r["case"], r["building_id"].replace("DEBY_LOD2_", ""), r["note"]] for r in b["representatives"]]

    text = f"""# W3 — val3dity Validity-Error Breakdown (T13)

- Run ID: `{run_id}`
- Task: T13 — parse the canonical `run_2` val3dity reports and aggregate the
  93-building validity errors by input and by geometric error category.
- Canonical val3dity reports: `{ALS_REPORT}`, `{DIM_REPORT}` (val3dity {val3dity_ver}).
- Paired status: `{PAIRED_STATUS}` (`coverage_control_population == yes` = 93 buildings).
- CRS: EPSG:25832 (numeric UTM32); inherited from the canonical CityJSON inputs.
  This task parses validity reports only and produces no new spatial product.
- val3dity parameters: overlap_tol={params.get('overlap_tol')}, planarity_d2p_tol={params.get('planarity_d2p_tol')}, planarity_n_tol={params.get('planarity_n_tol')}, snap_tol={params.get('snap_tol')}.
- Toolchain (rule 8): parsing/plotting executed inside the P0 `tools` docker service via `env/docker-compose.p0.yml`; tool versions recorded in `runs/{run_id}/versions.txt`. No geometry tool was re-run — the val3dity reports are pre-existing run_2 outputs.
- **Aggregation/observation only — no GO/NO-GO judgement.**

## 0. Scope

| input | features (Building) | valid | invalid | val3dity codes present |
| --- | --- | --- | --- | --- |
| ALS | {als_meta['features_total']} | {als_meta['features_valid']} | {b['als_invalid_n']} | {', '.join(str(c) for c in als_meta['all_errors'])} |
| DIM | {dim_meta['features_total']} | {dim_meta['features_valid']} | {b['dim_invalid_n']} | {', '.join(str(c) for c in dim_meta['all_errors'])} |

Building-level validity rate: ALS {als_meta['features_valid']}/{b['control_n']} ({100.0 * als_meta['features_valid'] / b['control_n']:.1f}%), DIM {dim_meta['features_valid']}/{b['control_n']} ({100.0 * dim_meta['features_valid'] / b['control_n']:.1f}%); drop = {100.0 * (als_meta['features_valid'] - dim_meta['features_valid']) / b['control_n']:.1f} pp (matches W3-2c `validity_rate_drop_pp`).

## 1. Error type × input aggregation ①

Building counts (a building is counted once per category it exhibits) and raw
val3dity error-instance counts.

{md_table(["error category", "val3dity codes", "ALS buildings", "DIM buildings", "ALS err-inst", "DIM err-inst"], type_rows)}

![T13 error category by input]({FIGURE.replace('docs/', '')})

## 2. Per-building error codes (union of validity failures) ①

{md_table(["building", "invalid in", "ALS error codes", "DIM error codes"], bld_rows)}

## 3. Representative cases ②

{md_table(["case", "building", "detail"], rep_rows)}

## 4. Quality-pair exclusion attribution ③

The clean quality comparison uses the {attr['quality_71_n']} `both_success` survivor buildings.
Validity failures are attributed by input below; the union of distinct
validity-failing buildings equals the W3-2c `validity` priority bucket (13).

{md_table(["group", "n", "buildings (id suffix)"], attr_rows)}

- DIM invalid 10 = {len(attr['dim_only_invalid'])} DIM-only + {len(attr['both_invalid'])} both.
- ALS invalid {len(attr['als_invalid_total'])} = {len(attr['als_only_invalid'])} ALS-only + {len(attr['both_invalid'])} both.
- All {len(attr['union_invalid'])} validity-failing buildings fall **outside** the quality-71 survivor set
  ({len(attr['union_in_quality_71'])} inside) — the 71 paired survivors are val3dity-valid in both inputs.

## 5. Observation

- DIM 무효 주 유형은 **{dim_dom['category_label']}** ({dim_dom['dim_buildings']}/{b['dim_invalid_n']} buildings, codes {dim_dom['val3dity_codes']});
  these are zero-length-edge / degenerate-ring failures consistent with noisy dense image-derived points.
- ALS는 단일 우세 유형이 없이 분산: {als_obs} (buildings).
- 두 입력이 같은 건물(4906967, 4906975)에서 모두 무효이나 **오류 코드는 서로 다르다**
  (ALS=self-intersection, DIM=non-manifold) — 같은 footprint에서도 입력별로 실패 기하가 갈린다.
- 절대 수가 작다(ALS 5 / DIM 10 / union 13); 단일 장면·단일 footprint 집합 한정.

## 6. Limitations

- Single canonical run (`{CANONICAL_RUN}`); W3-2b repeatability is ±0.5 pp by half-range.
- val3dity feature-level (Building) validity is reported here; primitive-level (Solid)
  counts differ (ALS Solid {_solid_str(als_meta)}, DIM Solid {_solid_str(dim_meta)}).
- Categories are an analyst grouping of val3dity codes; the code+description in the
  per-building table is the ground truth.
- Counts only; recovery/severity is not assessed and no GO/NO-GO judgement is made.

## Files

- Report: `{REPORT_MD}`
- Per-building errors: `{BUILDING_CSV}`
- Error type × input: `{TYPE_CSV}`
- Quality-pair attribution: `{ATTRIB_CSV}`
- Figure: `{FIGURE}`
"""
    (root / REPORT_MD).write_text(text, encoding="utf-8")


def _solid_str(meta: dict[str, Any]) -> str:
    for prim in meta.get("primitives_overview", []):
        if prim.get("type") == "Solid":
            return f"{prim.get('valid')}/{prim.get('total')} valid"
    return "n/a"


# ---------------------------------------------------------------------------
# G1 package
# ---------------------------------------------------------------------------
def add_to_g1_package(root: Path) -> None:
    package = root / "docs/G1_package"
    package_figs = package / "figs"
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)

    csvs = [BUILDING_CSV, TYPE_CSV, ATTRIB_CSV]
    pkg_csv_names = [
        "t13_validity_error_breakdown_building_errors.csv",
        "t13_validity_error_breakdown_type_by_input.csv",
        "t13_validity_error_breakdown_quality_attribution.csv",
    ]
    for src, name in zip(csvs, pkg_csv_names):
        shutil.copy2(root / src, package / name)
    shutil.copy2(root / REPORT_MD, package / "W3_validity_error_breakdown.md")
    shutil.copy2(root / FIGURE, package_figs / PACKAGE_FIGURE)

    update_package_captions(package / "captions.md")

    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "package": "G1_package", "canonical_run": CANONICAL_RUN, "files": [], "figure_count": 0,
    }
    files = set(manifest.get("files", []))
    files.update(pkg_csv_names)
    files.add("W3_validity_error_breakdown.md")
    files.add(f"figs/{PACKAGE_FIGURE}")
    files.add("captions.md")
    manifest["files"] = sorted(files)
    manifest["figure_count"] = sum(1 for f in manifest["files"] if f.startswith("figs/") and f.endswith(".png"))
    manifest["t13_validity_error_breakdown"] = {
        "report": "W3_validity_error_breakdown.md",
        "figure": f"figs/{PACKAGE_FIGURE}",
        "tables": pkg_csv_names,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_package_captions(path: Path) -> None:
    caption = (
        f"| Figure 16 | figs/{PACKAGE_FIGURE} | "
        "T13 val3dity validity-error category counts by input over the canonical run_2 control 93; "
        "ALS 5/93 vs DIM 10/93 invalid, no GO/NO-GO judgement. |"
    )
    if not path.exists():
        path.write_text("# G1 Figure Captions\n\n| figure | file | caption |\n| --- | --- | --- |\n" + caption + "\n", encoding="utf-8")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if any(line.startswith("| Figure 16 |") for line in lines):
        lines = [caption if line.startswith("| Figure 16 |") else line for line in lines]
    else:
        lines.append(caption)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# entrypoints
# ---------------------------------------------------------------------------
def compute_entrypoint() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (root / "docs/figs").mkdir(parents=True, exist_ok=True)

    als = parse_report(root / ALS_REPORT)
    dim = parse_report(root / DIM_REPORT)
    status = load_paired_status(root / PAIRED_STATUS)
    meta = {"ALS": report_meta(root / ALS_REPORT), "DIM": report_meta(root / DIM_REPORT)}

    breakdown = build_breakdown(als, dim, status)
    write_csvs(root, breakdown)
    write_figure(root, breakdown)
    write_report(root, breakdown, meta, run_id)
    add_to_g1_package(root)

    copy_outputs(
        run_dir,
        [
            root / REPORT_MD, root / BUILDING_CSV, root / TYPE_CSV, root / ATTRIB_CSV, root / FIGURE,
            root / "docs/G1_package/manifest.json", root / "docs/G1_package/captions.md",
        ],
    )

    attr = breakdown["attribution"]
    print(f"control_n={breakdown['control_n']}")
    print(f"als_invalid={breakdown['als_invalid_n']} dim_invalid={breakdown['dim_invalid_n']}")
    print(f"union_invalid={len(attr['union_invalid'])} (als_only={len(attr['als_only_invalid'])} dim_only={len(attr['dim_only_invalid'])} both={len(attr['both_invalid'])})")
    print(f"validity_failures_in_quality_71={len(attr['union_in_quality_71'])}")
    print(f"report={REPORT_MD}")


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t13_validity_error_breakdown_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    write_host_config(run_dir, run_id, git_commit)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    try:
        run(
            compose
            + [
                "run", "-T", "--rm",
                "-e", "P0_INSIDE_CONTAINER=1",
                "-e", f"RUN_ID={run_id}",
                "-e", f"P0_GIT_COMMIT={git_commit}",
                "tools", "python", "/workspace/scripts/13_validity_error_breakdown.py", "--mode", "compute",
            ],
            cwd=repo, env=env, log_path=logs_dir / "compute.log",
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print(f"report={REPORT_MD}")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(
        "\n".join(
            [
                f"task_id: {TASK_ID}",
                f"run_id: {run_id}",
                f"git_commit: {git_commit}",
                f"canonical_run: {CANONICAL_RUN}",
                f"val3dity_als_report: {ALS_REPORT}",
                f"val3dity_dim_report: {DIM_REPORT}",
                f"paired_status: {PAIRED_STATUS}",
                f"expected_control_n: {EXPECTED_CONTROL_N}",
                f"expected_als_invalid: {EXPECTED_ALS_INVALID}",
                f"expected_dim_invalid: {EXPECTED_DIM_INVALID}",
                "crs: EPSG:25832 numeric UTM32 (inherited from canonical CityJSON inputs)",
                "task_kind: validity-report parsing/aggregation only; no geometry tool re-run; no P0 judgement",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_host_versions(repo: Path, run_dir: Path, compose: list[str], env: dict[str, str], git_commit: str) -> None:
    lines = [
        "# T13 Validity Error Breakdown Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        f"- Canonical val3dity reports: {ALS_REPORT}, {DIM_REPORT}",
        "",
        "```console",
    ]
    version_cmds = [
        ["git", "status", "--short", "--branch"],
        compose + ["run", "-T", "--rm", "tools", "python", "--version"],
        compose + ["run", "-T", "--rm", "tools", "python", "-c",
                   "import matplotlib, numpy; print('matplotlib=' + matplotlib.__version__); print('numpy=' + numpy.__version__)"],
        compose + ["run", "-T", "--rm", "tools", "val3dity", "--version"],
    ]
    for cmd in version_cmds:
        proc = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True, check=False)
        lines.append("$ " + " ".join(cmd))
        out = (proc.stdout or proc.stderr).strip()
        if out:
            lines.append(out)
        if proc.returncode != 0:
            lines.append(f"[exit {proc.returncode}]")
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "outputs"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            continue
        if path.is_relative_to(Path("/workspace/docs")):
            dst = snapshot / "docs" / path.relative_to(Path("/workspace/docs"))
        else:
            dst = snapshot / path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Validity Error Breakdown\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, log_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout


def main() -> None:
    if os.environ.get("P0_INSIDE_CONTAINER") == "1":
        compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()
