#!/usr/bin/env python3
"""Build the A2 all-199 multi-condition comparison viewer payload.

Links every configured arm's sealed per-building roofer-input crop
(E1/E2/E7/E8 primary + E3/E4_V2/E5_V2 secondary), inlines the existing
CityGML LoD2 RoofSurface exterior rings in the viewer-local frame (sealed
+45.7 m datum bridge), and embeds per-building A2 metrics (f1@0.5 against
both GT suites, change-candidate tier, O50 auto-OX development labels) so
the browser list can sort by where each method wins or loses.

Visual inspection support only — no metric, gate, or verdict is computed
here; `scientific_verdict` stays null. Run inside the project container.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.p2.e4_e6_redesign_s3_v1.build_viewer_assets import write_ply
from scripts.p2.journal1_phase_b_v1.build_label_review_viewer import viewer_local_rings

REPO = Path(__file__).resolve().parents[3]
CHUNK = 2_000_000


def _voxel_partial(xyz, rgb, cls, voxel):
    """Per-chunk voxel aggregation: (keys, xyz sums, rgb sums, counts, cls max)."""
    keys = np.floor(xyz / voxel).astype(np.int64)
    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    keys, xyz, rgb, cls = keys[order], xyz[order], rgb[order], cls[order]
    starts = np.r_[0, np.flatnonzero(np.any(np.diff(keys, axis=0) != 0, axis=1)) + 1]
    counts = np.diff(np.r_[starts, len(keys)]).astype(np.float64)
    return (
        keys[starts],
        np.add.reduceat(xyz, starts, axis=0),
        np.add.reduceat(rgb.astype(np.float64), starts, axis=0),
        counts,
        np.maximum.reduceat(cls, starts),
    )


def build_scene_asset(source: Path, destination: Path, voxel: float, origin) -> int:
    """Full-scene classified LAZ → voxel-centroid PLY in the viewer-local frame."""
    import laspy

    keys_p, xyz_p, rgb_p, count_p, cls_p = [], [], [], [], []
    with laspy.open(source) as reader:
        for chunk in reader.chunk_iterator(CHUNK):
            xyz = np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)))
            try:
                rgb = np.column_stack((
                    np.asarray(chunk.red), np.asarray(chunk.green), np.asarray(chunk.blue),
                )).astype(np.float64)
            except Exception:
                rgb = np.full((len(xyz), 3), 32768.0)
            cls = np.asarray(chunk.classification).astype(np.uint8)
            k, x, r, c, m = _voxel_partial(xyz, rgb, cls, voxel)
            keys_p.append(k); xyz_p.append(x); rgb_p.append(r); count_p.append(c); cls_p.append(m)
    keys = np.concatenate(keys_p)
    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    keys = keys[order]
    xyz_s = np.concatenate(xyz_p)[order]
    rgb_s = np.concatenate(rgb_p)[order]
    count_s = np.concatenate(count_p)[order]
    cls_m = np.concatenate(cls_p)[order]
    starts = np.r_[0, np.flatnonzero(np.any(np.diff(keys, axis=0) != 0, axis=1)) + 1]
    counts = np.add.reduceat(count_s, starts)
    centroid = np.add.reduceat(xyz_s, starts, axis=0) / counts[:, None]
    rgb_mean = np.add.reduceat(rgb_s, starts, axis=0) / counts[:, None]
    rgb8 = (rgb_mean / 257.0).clip(0, 255).astype(np.uint8)
    cls_out = np.maximum.reduceat(cls_m, starts)
    write_ply(destination, centroid - np.asarray(origin, dtype=np.float64), rgb8, cls_out)
    return int(len(centroid))


def build_scene_assets(cfg: dict, out_dir: Path) -> dict:
    spec = cfg["scene"]
    voxel = float(spec["voxel_m"])
    scene_dir = out_dir / "assets_scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    entries = {}
    for arm in cfg["arms"]:
        arm_id = arm["id"]
        source = Path(spec["sources"][arm_id])
        destination = scene_dir / f"{arm_id}.points.ply"
        if destination.exists():
            with open(destination, "rb") as handle:
                head = handle.read(4096).decode("ascii", "replace")
            count = int(next(l for l in head.split("\n") if l.startswith("element vertex")).split()[2])
        else:
            print(f"[scene] {arm_id} <- {source.name} ...", flush=True)
            count = build_scene_asset(source, destination, voxel, cfg["origin"])
        entries[arm_id] = {"path": f"assets_scene/{arm_id}.points.ply", "points": count,
                           "source": str(source)}
        print(f"[scene] {arm_id}: {count:,} voxel points", flush=True)
    return {"voxel_m": voxel, "assets": entries,
            "note": spec["note"]}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def link_asset(src: Path, dst: Path) -> None:
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(os.path.relpath(src, dst.parent))


def load_metrics(rows_path: Path) -> dict[tuple[str, str, str], dict]:
    out = {}
    for line in open(rows_path, encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        out[(row["stable_id"], row["arm"], row["gt"])] = row
    return out


def load_ox(config: dict) -> dict[tuple[str, str], str]:
    """(arm, stable_id) -> O50 noG2 development verdict."""
    spec = config["auto_ox"]
    verdicts: dict[tuple[str, str], str] = {}

    def no_g2(row: dict) -> str:
        if row["verdict"] == "NA":
            return "NA"
        gates = (row["G0_status"], row["G1_status"], row["G3_status"], row["G4_status"])
        return "O" if all(value == "O" for value in gates) else "X"

    for row in csv.DictReader(open(spec["v22_csv"], encoding="utf-8")):
        if row["criterion"] == "O50" and row["condition_id"] in ("E1", "E2", "E3"):
            verdicts[(row["condition_id"], row["stable_id"])] = no_g2(row)
    rename = {"E4_V2_STATIC": "E4_V2", "E5_V2_F1": "E5_V2"}
    for row in csv.DictReader(open(spec["s3b_csv"], encoding="utf-8")):
        if row["criterion"] == "O50" and row["condition_id"] in rename:
            verdicts[(rename[row["condition_id"]], row["stable_id"])] = row["verdict_noG2"]
    for row in csv.DictReader(open(spec["a2_csv"], encoding="utf-8")):
        if row["criterion"] == "O50":
            verdicts[(row["condition_id"], row["stable_id"])] = row["verdict_noG2"]
    return verdicts


def _rings_center(rings) -> list | None:
    if not rings:
        return None
    pts = [p for ring in rings for p in ring]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; zs = [p[2] for p in pts]
    return [round((min(xs) + max(xs)) / 2, 2), round((min(ys) + max(ys)) / 2, 2),
            round((min(zs) + max(zs)) / 2, 2)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/p2/journal1_phase_a_v1/conditions_viewer_v1.json")
    args = parser.parse_args()
    cfg = json.load(open(args.config))
    assert cfg.get("scientific_verdict") is None
    script_dir = Path(__file__).resolve().parent

    selection_rows = {}
    selection_meta = None
    selection_dir = cfg.get("selection_dir")
    if selection_dir and (Path(selection_dir) / "selection_v1.json").is_file():
        payload = json.loads((Path(selection_dir) / "selection_v1.json").read_text(encoding="utf-8"))
        selection_rows = {row["stable_id"]: row for row in payload["buildings"]}
        boundary = json.loads((Path(selection_dir) / "boundary_viewer.json").read_text(encoding="utf-8"))
        selection_meta = {
            "status": payload["status"],
            "rule": payload["rule"],
            "counts": payload["counts"],
            "coverage_rings": boundary["coverage_rings"],
            "interior_rings": boundary["interior_rings"],
        }

    footprints = json.load(open(cfg["footprints_geojson"]))
    ordered = sorted(
        (int(f["properties"]["population_index"]), str(f["properties"]["stable_id"]))
        for f in footprints["features"]
    )
    targets = {sid for _, sid in ordered}
    tiers = {r["stable_id"]: r["tier"] for r in csv.DictReader(open(cfg["labels_csv"]))}
    metrics = load_metrics(Path(cfg["merged_rows"]))
    ox = load_ox(cfg)
    lod2 = viewer_local_rings(cfg["gml_tiles"], targets, cfg["origin"], cfg["lod2_z_shift_to_viewer_m"])

    arm_maps = {}
    for arm in cfg["arms"]:
        arm_maps[arm["id"]] = {
            p.name.split("_", 1)[1].removesuffix(".points.ply"): p
            for p in sorted(Path(arm["dir"]).glob("B*_*.points.ply"))
        }

    out_dir = Path(cfg["out_dir"])
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)

    def metric_cell(sid: str, arm: str) -> dict:
        cell = {}
        for gt, key in (("lod2", "f1_lod2"), ("e1", "f1_e1")):
            row = metrics.get((sid, arm, gt))
            value = row.get("f1@0.5") if row else None
            cell[key] = round(value, 3) if value is not None else None
        verdict = ox.get((arm, sid))
        if verdict is not None:
            cell["ox"] = verdict
        return cell

    buildings = []
    missing = {arm["id"]: [] for arm in cfg["arms"]}
    for population_index, sid in ordered:
        entry = {
            "stable_id": sid,
            "bkey": f"B{population_index:03d}",
            "tier": tiers.get(sid, "?"),
            "assets": {},
            "metrics": {},
        }
        for arm in cfg["arms"]:
            arm_id = arm["id"]
            src = arm_maps[arm_id].get(sid)
            if src is None:
                missing[arm_id].append(sid)
            else:
                arm_dir = out_dir / "assets" / arm_id
                arm_dir.mkdir(parents=True, exist_ok=True)
                link_asset(src, arm_dir / src.name)
                entry["assets"][arm_id] = f"assets/{arm_id}/{src.name}"
            entry["metrics"][arm_id] = metric_cell(sid, arm_id)
        got = lod2.get(sid)
        entry["lod2_rings"] = got["rings"] if got else []
        entry["center"] = _rings_center(entry["lod2_rings"])
        sel = selection_rows.get(sid)
        if sel:
            entry["sel"] = {"zone": sel["zone"], "cover": sel["e1_any_cover"],
                            "selected": sel["selected_rule"]}

        def f1(arm_id: str, key: str):
            return entry["metrics"].get(arm_id, {}).get(key)

        deltas = {}
        pairs = {
            "gs_vs_e2_e1": ("E4_V2", "E2", "f1_e1"),
            "e8_vs_e2_lod2": ("E8", "E2", "f1_lod2"),
            "e8_vs_e4v2_e1": ("E8", "E4_V2", "f1_e1"),
            "e7_vs_e2_e1": ("E7", "E2", "f1_e1"),
        }
        for name, (a, b, key) in pairs.items():
            va, vb = f1(a, key), f1(b, key)
            deltas[name] = round(va - vb, 3) if va is not None and vb is not None else None
        entry["deltas"] = deltas
        buildings.append(entry)

    generated_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {
        "task_id": cfg["task_id"],
        "stage": cfg["stage"],
        "status": cfg["status"],
        "scientific_verdict": None,
        "generated_utc": generated_utc,
        "frame": {
            "origin": cfg["origin"],
            "lod2_z_shift_to_viewer_m": cfg["lod2_z_shift_to_viewer_m"],
            "note": "viewer-local = world - origin; LoD2 additionally z + 45.7 (datum bridge)",
        },
        "crs": "EPSG:25832 (world frame; viewer frame is a pure translation)",
        "arms": [{"id": a["id"], "primary": a["primary"], "lineage": a["lineage"]} for a in cfg["arms"]],
        "ox_note": "O50 noG2 development labels (NOT_OFFICIAL); NA = evaluation reference absent",
        "scene": build_scene_assets(cfg, out_dir),
        "selection": selection_meta,
        "buildings": buildings,
    }
    (out_dir / "conditions_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))

    for name in ("index.html", "app.js"):
        shutil.copy2(script_dir / "conditions_viewer" / name, out_dir / name)
    shutil.copy2(cfg["three_module"], out_dir / "three.module.min.js")

    receipt = {
        "task_id": cfg["task_id"],
        "stage": cfg["stage"],
        "status": cfg["status"],
        "scientific_verdict": None,
        "generated_utc": generated_utc,
        "tool": "scripts/p2/journal1_phase_a_v1/a2_build_conditions_viewer.py",
        "config": str(args.config),
        "inputs": {
            "footprints_geojson": cfg["footprints_geojson"],
            "labels_csv": cfg["labels_csv"],
            "merged_rows": cfg["merged_rows"],
            "merged_rows_sha256": sha256_file(Path(cfg["merged_rows"])),
            "auto_ox": cfg["auto_ox"],
            "arm_dirs": {a["id"]: a["dir"] for a in cfg["arms"]},
        },
        "counts": {
            "buildings": len(buildings),
            "assets_linked": {a["id"]: len(arm_maps[a["id"]]) for a in cfg["arms"]},
            "missing_assets": {k: len(v) for k, v in missing.items()},
            "lod2_rings_total": sum(len(b["lod2_rings"]) for b in buildings),
            "buildings_without_lod2": sum(1 for b in buildings if not b["lod2_rings"]),
            "scene_voxel_points": {k: v["points"] for k, v in manifest["scene"]["assets"].items()},
        },
        "serve_note": cfg["serve_note"],
    }
    (out_dir / "web_receipt_v1.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps({"buildings": len(buildings),
                      "missing": {k: len(v) for k, v in missing.items()},
                      "out_dir": str(out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
