#!/usr/bin/env python3
"""Build the journal1 Phase-B change-label review viewer payload.

Reads the Phase-A candidate CSV, keeps the A/B mismatch tiers, extracts the
existing CityGML LoD2 RoofSurface exterior rings for those buildings in the
viewer-local frame (world - origin, plus the sealed +45.7 m LoD2 z bridge),
links the sealed E1/E2 roofer-input crops, and emits a static browser viewer
(index.html + app.js + three.module.min.js + review_manifest.json).

The viewer records human 3-way labels (CHANGE / NO_CHANGE /
ABSTRACTION_MISMATCH) plus notes in browser localStorage and exports them as
JSON. No metric, gate, or scientific verdict is computed here.

Run inside the project container, e.g.:
  docker run --rm --network none \
    -v <repo>:/workspace/JointBuildGS -v <artifacts-root>:/artifacts/JointBuildGS \
    -w /workspace/JointBuildGS jointbuildgs:dev \
    python scripts/p2/journal1_phase_b_v1/build_label_review_viewer.py \
      --config configs/p2/journal1_phase_b_v1/run_v1.json
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

GML = "{http://www.opengis.net/gml}"
BLDG = "{http://www.opengis.net/citygml/building/1.0}"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_candidates(csv_path, tiers):
    """CSV rows for the requested tiers, in file order (A block then B block)."""
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["tier"] in tiers:
                rows.append(row)
    return rows


def viewer_local_rings(tiles, targets, origin, z_shift):
    """{stable_id: {"rings": [[[x,y,z],...],...], "interior_skipped": n}}.

    Exterior ring per gml:Polygon under bldg:RoofSurface, shifted into the
    viewer-local frame: xyz - origin, then z + z_shift (LoD2 datum bridge).
    """
    shift = [origin[0], origin[1], origin[2] - z_shift]
    out = {}
    for tile in tiles:
        for _, el in ET.iterparse(str(tile), events=("end",)):
            if el.tag != BLDG + "Building":
                continue
            bid = el.get(GML + "id")
            if bid in targets:
                rings, interior = [], 0
                for rs in el.iter(BLDG + "RoofSurface"):
                    for poly in rs.iter(GML + "Polygon"):
                        interior += len(poly.findall(f"{GML}interior"))
                        ext = poly.find(f"{GML}exterior")
                        if ext is None:
                            continue
                        pl = ext.find(f".//{GML}posList")
                        if pl is None or not pl.text:
                            continue
                        vals = [float(x) for x in pl.text.split()]
                        if len(vals) < 12 or len(vals) % 3:
                            continue
                        ring = [[round(vals[i] - shift[0], 3),
                                 round(vals[i + 1] - shift[1], 3),
                                 round(vals[i + 2] - shift[2], 3)]
                                for i in range(0, len(vals), 3)]
                        rings.append(ring)
                if rings:
                    out[bid] = {"rings": rings, "interior_skipped": interior}
            el.clear()
    return out


def link_asset(src, dst):
    """Relative symlink dst -> src (idempotent)."""
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(os.path.relpath(src, dst.parent))


def git_commit(repo_dir):
    try:
        return subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/p2/journal1_phase_b_v1/run_v1.json")
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    script_dir = Path(__file__).resolve().parent
    repo_dir = script_dir.parents[2]

    rows = read_candidates(cfg["candidates_csv"], set(cfg["tiers"]))
    if not rows:
        sys.exit("no candidate rows matched the requested tiers")
    targets = {r["stable_id"] for r in rows}

    # Optional per-building E1/E2 coverage diagnostic (coverage_diagnostic.py runs
    # after the first build; rebuilding then embeds its rows into the manifest).
    coverage_map = {}
    cov_meta = None
    cov_path = cfg.get("coverage_json")
    if cov_path and Path(cov_path).exists():
        cov = json.load(open(cov_path))
        coverage_map = {r["stable_id"]: r for r in cov.get("buildings", [])
                        if "error" not in r}
        cov_meta = {"schema": cov.get("schema"), "generated_utc": cov.get("generated_utc"),
                    "params": cov.get("params")}

    lod2 = viewer_local_rings(cfg["gml_tiles"], targets, cfg["origin"],
                              cfg["lod2_z_shift_to_viewer_m"])

    asset_maps = {}
    for arm, d in cfg["asset_dirs"].items():
        arm_map = {}
        for p in sorted(Path(d).glob("B*_*.points.ply")):
            arm_map[p.name.split("_", 1)[1].removesuffix(".points.ply")] = p
        asset_maps[arm] = arm_map

    out_dir = Path(cfg["out_dir"])
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)

    buildings, missing = [], {"lod2": [], "E1": []}
    for row in rows:
        sid = row["stable_id"]
        entry = {
            "stable_id": sid,
            "tier": row["tier"],
            "metrics": {
                "e1_lod2_completeness_0p5": float(row["e1_lod2_completeness@0.5"]),
                "e1_lod2_acc_median_m": float(row["e1_lod2_acc_median_m"]),
                "e1_lod2_f1_0p5": float(row["e1_lod2_f1@0.5"]),
                "n_e1_roof_pts": int(row["n_e1_roof_pts"]),
                "flag": row.get("flag", ""),
            },
            "assets": {},
        }
        for arm, arm_map in asset_maps.items():
            src = arm_map.get(sid)
            if src is None:
                if arm == "E1":
                    missing["E1"].append(sid)
                continue
            arm_dir = out_dir / "assets" / arm
            arm_dir.mkdir(parents=True, exist_ok=True)
            link_asset(src, arm_dir / src.name)
            entry["assets"][arm] = f"assets/{arm}/{src.name}"
            if arm == "E1":
                entry["bkey"] = src.name.split("_", 1)[0]
        got = lod2.get(sid)
        if got is None:
            missing["lod2"].append(sid)
            entry["lod2_rings"] = []
        else:
            entry["lod2_rings"] = got["rings"]
            entry["lod2_interior_skipped"] = got["interior_skipped"]
        c = coverage_map.get(sid)
        if c:
            entry["coverage"] = {"E1": c.get("E1"), "E2": c.get("E2"),
                                 "gate_any_070": c.get("gate_any_070"),
                                 "gate_cls6_070": c.get("gate_cls6_070")}
        buildings.append(entry)

    generated_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {
        "task_id": cfg["task_id"],
        "status": cfg["status"],
        "scientific_verdict": None,
        "generated_utc": generated_utc,
        "source_csv": cfg["candidates_csv"],
        "source_csv_sha256": sha256_file(cfg["candidates_csv"]),
        "tiers": cfg["tiers"],
        "excluded_tiers_note": cfg["excluded_tiers_note"],
        "frame": {
            "origin": cfg["origin"],
            "lod2_z_shift_to_viewer_m": cfg["lod2_z_shift_to_viewer_m"],
            "note": "viewer-local = world - origin; LoD2 additionally z + 45.7 (datum bridge)",
        },
        "asset_lineage": cfg["asset_lineage"],
        "crs": "EPSG:25832 (world frame; viewer frame is a pure translation)",
        "label_values": ["CHANGE", "NO_CHANGE", "ABSTRACTION_MISMATCH", "UNDECIDABLE"],
        "coverage_source": cov_meta,
        "buildings": buildings,
    }
    (out_dir / "review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))

    for name in ("index.html", "app.js"):
        shutil.copy2(script_dir / "viewer" / name, out_dir / name)
    shutil.copy2(cfg["three_module"], out_dir / "three.module.min.js")

    receipt = {
        "task_id": cfg["task_id"],
        "status": cfg["status"],
        "scientific_verdict": None,
        "generated_utc": generated_utc,
        "tool": "scripts/p2/journal1_phase_b_v1/build_label_review_viewer.py",
        "config": str(args.config),
        "git_commit": git_commit(repo_dir),
        "python": platform.python_version(),
        "inputs": {
            "candidates_csv": cfg["candidates_csv"],
            "candidates_csv_sha256": manifest["source_csv_sha256"],
            "gml_tiles": cfg["gml_tiles"],
            "asset_dirs": cfg["asset_dirs"],
            "three_module": cfg["three_module"],
        },
        "counts": {
            "buildings": len(buildings),
            "by_tier": {t: sum(1 for b in buildings if b["tier"] == t)
                        for t in cfg["tiers"]},
            "with_e2_asset": sum(1 for b in buildings if "E2" in b["assets"]),
            "with_coverage_diag": sum(1 for b in buildings if "coverage" in b),
            "lod2_rings_total": sum(len(b["lod2_rings"]) for b in buildings),
            "lod2_interior_rings_skipped": sum(b.get("lod2_interior_skipped", 0)
                                               for b in buildings),
        },
        "missing": missing,
        "outputs": {
            "out_dir": str(out_dir),
            "files": ["index.html", "app.js", "three.module.min.js",
                      "review_manifest.json", "assets/E1/*.ply (symlink)",
                      "assets/E2/*.ply (symlink)"],
        },
        "labels_note": ("Labels live in browser localStorage "
                        "(key jbgs-journal1-phase-b-change-labels-v1) until exported "
                        "as JSON by the reviewer; the build writes no label data."),
        "serve_note": cfg["serve_note"],
    }
    (out_dir / "web_receipt_v1.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2))

    print(json.dumps({"buildings": len(buildings), "missing": missing,
                      "lod2_rings": receipt["counts"]["lod2_rings_total"],
                      "out_dir": str(out_dir)}, ensure_ascii=False))
    if missing["E1"] or missing["lod2"]:
        sys.exit("missing required inputs — see receipt")


if __name__ == "__main__":
    main()
