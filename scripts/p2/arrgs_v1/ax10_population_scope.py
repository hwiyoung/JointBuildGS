"""AX-10 — target-population stratification (pre-registered measurement).

Pre-registration: docs/experiments/p2/arrgs_design_v1/AX10_POPULATION_SCOPE_ko_v1.md
(2026-08-22 revision note: N sets the scope of real-data claims, not the axis
life-or-death; mechanism proof proceeds via controlled injection regardless of N).

Measurement only — no training, CPU only, re-aggregation of sealed artifacts.
Population = frozen 93-building selection mask (never performance-derived).

Axis 1 (change) is reported in two registered variants:
  preregistered : A_STRONG_MISMATCH ∪ B_MODERATE_MISMATCH
  user_adjusted : A-tier + user readout overrides (2026-08-12 session record:
                  all 19 B-tier buildings declared non-change; A-tier vegetation/
                  partial-cover/abstraction overrides below). The browser label
                  export was never frozen, so the override map is reconstructed
                  from the recorded session readout and is listed explicitly in
                  the receipt — nothing silent.
Axis 2 (current-image sufficiency): E2 completeness@0.25 (gt=e1) < 0.9.

scientific_verdict: null (technical measurement; human verdict separate).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
from collections import defaultdict
from pathlib import Path

ARTIFACT_ROOT = Path(os.environ.get("JBGS_ARTIFACT_ROOT", "/artifacts/JointBuildGS"))
PHASE_A = ARTIFACT_ROOT / "phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1"
SELECTION = PHASE_A / "labels/selection_confirm_v1.json"
TIER_CSV = PHASE_A / "labels/change_label_candidates_v1.csv"
MERGED_ROWS = PHASE_A / "a2/evaluation_merged/rows.csv"
FOOTPRINTS = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/c1_c2_shared_footprint_199_v3"
    / "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a"
    / "freeze/shared_footprints_199.geojson"
)
ROOFER_ARMS = {arm: PHASE_A / "a2/assets_roofer_input" / arm for arm in ("E7", "E8")}
OUT_DIR = ARTIFACT_ROOT / "phase-payloads/p2/arrgs_v1/P2-ARRGS-AX10-v1"

COMP_KEY = "completeness@0.25"
INSUFFICIENT_THRESHOLD = 0.9
DEGENERATE_ROOF_RATIO = 0.2

# 2026-08-12 user viewer readout (session record; localStorage export not frozen).
USER_B_TIER_ALL_NONCHANGE = True
USER_A_TIER_OVERRIDES = {
    "DEBY_LOD2_4959326": "CHANGE_CONFIRMED",          # B173 flat roof vs LoD2 gable
    "DEBY_LOD2_4908354": "UNDECIDABLE_VEGETATION",    # B166 canopy suspicion
    "DEBY_LOD2_108250120": "UNDECIDABLE_VEGETATION",  # B011 canopy occlusion
    "DEBY_LOD2_4907207": "UNDECIDABLE_PARTIAL_COVER", # B112 half coverage
    "DEBY_LOD2_4906989": "ABSTRACTION_UPLIFT",        # B043 +1.6 m uplift/abstraction
    "DEBY_LOD2_104586480": "CHANGE_CONFIRMED",        # B003 demolition suspicion
}
NON_CHANGE_OVERRIDE_STATES = {
    "UNDECIDABLE_VEGETATION",
    "UNDECIDABLE_PARTIAL_COVER",
    "ABSTRACTION_UPLIFT",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quartiles(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    v = sorted(values)

    def q(p: float) -> float:
        i = p * (len(v) - 1)
        lo, hi = int(math.floor(i)), int(math.ceil(i))
        return v[lo] + (v[hi] - v[lo]) * (i - lo)

    return {"n": len(v), "q25": round(q(0.25), 4), "median": round(q(0.5), 4),
            "q75": round(q(0.75), 4)}


def ring_area(ring: list[list[float]]) -> float:
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def load_footprint_areas() -> dict[str, float]:
    gj = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    areas: dict[str, float] = {}
    for feat in gj["features"]:
        props = feat.get("properties", {})
        sid = props.get("stable_id") or props.get("gml_id") or props.get("id")
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        area = 0.0
        for poly in polys:
            area += ring_area([c[:2] for c in poly[0]])
            for hole in poly[1:]:
                area -= ring_area([c[:2] for c in hole])
        areas[sid] = area
    return areas


def roofer_obj_stats(path: Path) -> dict:
    verts: list[tuple[float, float, float]] = []
    n_faces = 0
    roof_proj_area = 0.0
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("v "):
            p = line.split()
            verts.append((float(p[1]), float(p[2]), float(p[3])))
        elif line.startswith("f "):
            n_faces += 1
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            for a, b in zip(idx[1:-1], idx[2:]):
                p0, p1, p2 = verts[idx[0]], verts[a], verts[b]
                u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
                w = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
                nz = u[0] * w[1] - u[1] * w[0]
                if nz > 0:  # upward-facing → XY-projected roof plan area
                    roof_proj_area += nz / 2.0
    return {"n_vertices": len(verts), "n_faces": n_faces,
            "roof_projected_area_m2": round(roof_proj_area, 3)}


def main() -> None:
    sel = json.loads(SELECTION.read_text(encoding="utf-8"))
    ids: list[str] = sel["effective_selected_ids"]
    assert len(ids) == 93, "frozen population mask must stay 93"
    id_set = set(ids)

    tiers = {r["stable_id"]: r["tier"] for r in csv.DictReader(open(TIER_CSV, encoding="utf-8"))}

    e2 = {}
    n_roof = defaultdict(dict)
    for r in csv.DictReader(open(MERGED_ROWS, encoding="utf-8")):
        if r["stable_id"] not in id_set:
            continue
        if r["gt"] == "e1" and r["arm"] == "E2":
            e2[r["stable_id"]] = {
                "comp025": float(r[COMP_KEY]) if r[COMP_KEY] else None,
                "coverage": float(r["coverage"]) if r["coverage"] else None,
            }
        if r["gt"] == "e1" and r["arm"] in ("E7", "E8") and r["n_roof"]:
            n_roof[r["stable_id"]][r["arm"]] = float(r["n_roof"])

    areas = load_footprint_areas()

    missing_comp = [sid for sid in ids if e2.get(sid, {}).get("comp025") is None]

    def axis2(sid: str) -> str:
        c = e2.get(sid, {}).get("comp025")
        if c is None:
            return "missing"
        return "insufficient" if c < INSUFFICIENT_THRESHOLD else "sufficient"

    def axis1(sid: str, variant: str) -> str:
        tier = tiers.get(sid, "NA_E1_INSUFFICIENT")
        if variant == "preregistered":
            if tier in ("A_STRONG_MISMATCH", "B_MODERATE_MISMATCH"):
                return "change"
            if tier == "C_CONSISTENT":
                return "nonchange"
            return "na"
        # user_adjusted
        override = USER_A_TIER_OVERRIDES.get(sid)
        if tier == "A_STRONG_MISMATCH":
            if override in NON_CHANGE_OVERRIDE_STATES:
                return "undecidable_user"
            return "change"
        if tier == "B_MODERATE_MISMATCH":
            return "nonchange" if USER_B_TIER_ALL_NONCHANGE else "change"
        if tier == "C_CONSISTENT":
            return "nonchange"
        return "na"

    variants = {}
    for variant in ("preregistered", "user_adjusted"):
        cells: dict[str, list[str]] = defaultdict(list)
        for sid in ids:
            cells[f"{axis1(sid, variant)}|{axis2(sid)}"].append(sid)
        table = {}
        for key, members in sorted(cells.items()):
            comp = [e2[s]["comp025"] for s in members if e2.get(s, {}).get("comp025") is not None]
            cov = [e2[s]["coverage"] for s in members if e2.get(s, {}).get("coverage") is not None]
            dens = [
                (n_roof[s]["E8"] - n_roof[s]["E7"]) / areas[s]
                for s in members
                if "E8" in n_roof.get(s, {}) and "E7" in n_roof.get(s, {}) and areas.get(s)
            ]
            table[key] = {
                "count": len(members),
                "stable_ids": sorted(members),
                "e2_comp025": quartiles(comp),
                "e2_coverage": quartiles(cov),
                "mvs_roof_density_pts_m2": quartiles(dens),
            }
        n_key = "change|insufficient"
        variants[variant] = {
            "cells": table,
            "N_change_and_insufficient": table.get(n_key, {}).get("count", 0),
            "N_stable_ids": table.get(n_key, {}).get("stable_ids", []),
        }

    census = {}
    degenerate_overlap = {"E7": [], "E8": []}
    for arm, arm_dir in ROOFER_ARMS.items():
        rows = {}
        for obj in sorted(arm_dir.glob("B*_*.roofer.obj")):
            sid = obj.name.split("_", 1)[1].removesuffix(".roofer.obj")
            if sid not in id_set:
                continue
            st = roofer_obj_stats(obj)
            fp = areas.get(sid)
            st["footprint_area_m2"] = round(fp, 3) if fp else None
            st["empty"] = st["n_vertices"] == 0 or st["n_faces"] == 0
            st["degenerate"] = bool(
                fp and st["roof_projected_area_m2"] < DEGENERATE_ROOF_RATIO * fp
            )
            rows[sid] = st
        missing = sorted(id_set - set(rows))
        census[arm] = {
            "n_obj_found": len(rows),
            "missing_obj_stable_ids": missing,
            "n_empty": sum(1 for s in rows.values() if s["empty"]),
            "n_degenerate": sum(1 for s in rows.values() if s["degenerate"]),
            "empty_or_degenerate_ids": sorted(
                [s for s, v in rows.items() if v["empty"] or v["degenerate"]] + missing
            ),
            "per_building": rows,
        }
        degenerate_overlap[arm] = census[arm]["empty_or_degenerate_ids"]

    n_ids = set(variants["user_adjusted"]["N_stable_ids"])
    overlap_b = {
        arm: sorted(n_ids & set(ids_)) for arm, ids_ in degenerate_overlap.items()
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pop = {
        "schema": "arrgs_ax10_population_2x2_v1",
        "pre_registration": "docs/experiments/p2/arrgs_design_v1/AX10_POPULATION_SCOPE_ko_v1.md",
        "rule_revision_2026_08_22": (
            "N sets real-data claim scope (full ROC / case study / literature+second-scene); "
            "mechanism proof via controlled injection regardless of N. "
            "Former N<=2 axis-abolition line superseded."
        ),
        "population": {"count": len(ids), "mask": str(SELECTION.relative_to(ARTIFACT_ROOT))},
        "axis2": {"metric": f"E2 {COMP_KEY} (gt=e1)", "insufficient": f"< {INSUFFICIENT_THRESHOLD}",
                  "missing_ids": missing_comp},
        "axis1_variants": {
            "preregistered": "change = A_STRONG_MISMATCH ∪ B_MODERATE_MISMATCH",
            "user_adjusted": {
                "definition": "change = A-tier + user 2026-08-12 readout overrides; "
                              "B-tier all declared non-change by user",
                "a_tier_overrides": USER_A_TIER_OVERRIDES,
                "provenance": "session record 2026-08-12 (browser label export not frozen; "
                              "override map reconstructed and listed here explicitly)",
            },
        },
        "tables": variants,
        "aux_measurement_B_overlap": {
            "definition": "user_adjusted change∧insufficient ∩ roofer empty/degenerate/missing",
            "overlap": overlap_b,
        },
        "scientific_verdict": None,
    }
    (OUT_DIR / "population_2x2.json").write_text(
        json.dumps(pop, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "roofer_failure_census.json").write_text(
        json.dumps({"schema": "arrgs_ax10_roofer_failure_census_v1",
                    "degenerate_rule": f"roof_projected_area < {DEGENERATE_ROOF_RATIO} × footprint",
                    "arms": census, "scientific_verdict": None},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, cwd=Path(__file__).resolve().parents[3]).stdout.strip()
    except Exception:
        commit = None
    receipt = {
        "schema": "arrgs_ax10_receipt_v1",
        "task": "P2-ARRGS-AX10-v1",
        "git_commit": commit,
        "inputs": {
            str(p.relative_to(ARTIFACT_ROOT)): sha256(p)
            for p in (SELECTION, TIER_CSV, MERGED_ROWS, FOOTPRINTS)
        },
        "parameters": {
            "comp_key": COMP_KEY,
            "insufficient_threshold": INSUFFICIENT_THRESHOLD,
            "degenerate_roof_ratio": DEGENERATE_ROOF_RATIO,
            "user_a_tier_overrides": USER_A_TIER_OVERRIDES,
            "user_b_tier_all_nonchange": USER_B_TIER_ALL_NONCHANGE,
        },
        "notes": [
            "P-AX10-1/2 paired tests vs ARRGS_ORACLE not computable population-wide: "
            "ARRGS arms exist only for the 3-building legacy test bed, not the 93.",
        ],
        "scientific_verdict": None,
    }
    (OUT_DIR / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "N_preregistered_AuB": variants["preregistered"]["N_change_and_insufficient"],
        "N_user_adjusted": variants["user_adjusted"]["N_change_and_insufficient"],
        "N_ids_user_adjusted": variants["user_adjusted"]["N_stable_ids"],
        "cells_user_adjusted": {
            k: v["count"] for k, v in variants["user_adjusted"]["cells"].items()
        },
        "cells_preregistered": {
            k: v["count"] for k, v in variants["preregistered"]["cells"].items()
        },
        "roofer_failure": {a: {"empty": c["n_empty"], "degenerate": c["n_degenerate"],
                               "missing": len(c["missing_obj_stable_ids"])}
                           for a, c in census.items()},
        "overlap_B": overlap_b,
        "out_dir": str(OUT_DIR),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
