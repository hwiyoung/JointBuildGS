#!/usr/bin/env python3
"""Injection bench v1 — generate perturbed copies of the frozen tile partitions with known truth (design DESIGN_ko_v1.md).

Each variant gets its own directory holding: partition/{mvs,als}/<tile>.xyz_f32le.bin (perturbed copies), partition_receipt.json and
relation_map.npy (verbatim copies so the frozen downstream drivers resolve their inputs), truth_{mvs,als}_u8.npy (per point: 0 = untouched,
1 = modified / deleted-marker kept for deleted points in the original order), truth_cells.npy (per baseline top-layer cell: injected kind),
injection_manifest.json (patches, parameters, hashes).  The originals are never written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/injection_bench_v1/bench_v1.json"
SCHEMA = "jointbuildgs.phd.injection_bench.run.v1"
PROHIBITED_TOKENS = ("uas", "lod2", "footprint", "stable_id", "journal1", "roster")
CELL_KIND = {"none": 0, "delta_all": 1, "mvs_missing": 2, "mvs_noisy": 3, "mvs_biased": 4, "als_stale": 5}
CELL_DTYPE = np.dtype([("ix", "<i4"), ("iy", "<i4"), ("kind", "u1"), ("patch_id", "<i4")])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_bytes(value); os.replace(tmp, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_npy(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    os.replace(tmp, path)


def git_head() -> str:
    env = os.environ.get("JBGS_SOURCE_GIT_HEAD")
    if env:
        return env
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema") != SCHEMA:
        raise ValueError("injection bench config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("run is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    serialized = json.dumps({"inputs": cfg["inputs"], "output": cfg["output_relative_root"]}).lower()
    for token in PROHIBITED_TOKENS:
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    ids = [v["id"] for v in cfg["variants"]]
    if len(set(ids)) != len(ids):
        raise ValueError("variant ids must be unique")
    for v in cfg["variants"]:
        if v["kind"] not in ("als_shift_all", "mvs_delete_patches", "mvs_noise_patches", "mvs_shift_patches", "als_shift_patches"):
            raise ValueError(f"unknown variant kind: {v['kind']}")
    rule = cfg["patch_rule"]
    if not (0 < float(rule["select_fraction"]) <= 1) or float(rule["grid_m"]) <= 0:
        raise ValueError("invalid patch rule")
    return cfg


# ----------------------------------------------------------------------------
# patches
# ----------------------------------------------------------------------------

def candidate_patches(top: np.ndarray, domain: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    """3 m grid squares over the prism whose 0.5 m top-layer cells are >= min fraction COMPATIBLE and planar (baseline pairing)."""
    cell = float(rule["cell_size_m"]); grid = float(rule["grid_m"])
    x0, y0 = float(domain["x"][0]), float(domain["y"][0]); x1, y1 = float(domain["x"][1]), float(domain["y"][1])
    per_side = int(round(grid / cell))
    nx = int(np.floor((x1 - x0) / grid)); ny = int(np.floor((y1 - y0) / grid))
    compat = (top["state"] == 1) & (top["rough"] == 0)
    lookup = {(int(ix), int(iy)): bool(c) for ix, iy, c in zip(top["ix"], top["iy"], compat)}
    out = []
    for gy in range(ny):
        for gx in range(nx):
            cells = [(gx * per_side + dx, gy * per_side + dy) for dx in range(per_side) for dy in range(per_side)]
            present = [lookup.get(c, False) for c in cells]
            frac = sum(present) / len(cells)
            if frac >= float(rule["min_compatible_planar_fraction"]):
                out.append({"gx": gx, "gy": gy, "bbox": [x0 + gx * grid, y0 + gy * grid, x0 + (gx + 1) * grid, y0 + (gy + 1) * grid],
                            "cells": [list(c) for c in cells], "compatible_fraction": float(frac)})
    return out


def select_patches(candidates: list[dict[str, Any]], rule: dict[str, Any]) -> list[dict[str, Any]]:
    rng = np.random.default_rng(int(rule["seed"]))
    n = len(candidates)
    k = int(round(n * float(rule["select_fraction"])))
    order = rng.permutation(n)[:k]
    chosen = [dict(candidates[i], patch_id=int(j + 1)) for j, i in enumerate(sorted(order.tolist()))]
    return chosen


def in_patches(xy: np.ndarray, patches: list[dict[str, Any]]) -> np.ndarray:
    """Patch id (1-based) per point, 0 outside every patch."""
    ids = np.zeros(len(xy), dtype=np.int32)
    for p in patches:
        bx0, by0, bx1, by1 = p["bbox"]
        m = (xy[:, 0] >= bx0) & (xy[:, 0] < bx1) & (xy[:, 1] >= by0) & (xy[:, 1] < by1)
        ids[m] = p["patch_id"]
    return ids


# ----------------------------------------------------------------------------
# variants
# ----------------------------------------------------------------------------

def apply_variant(variant: dict[str, Any], mvs: np.ndarray, als: np.ndarray, patches: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, str]:
    """Return (mvs_out, als_out, truth_mvs, truth_als, cell_kind_name).  truth arrays are aligned to the ORIGINAL point order
    (1 = modified or deleted); deleted points are removed from mvs_out."""
    kind = variant["kind"]
    tm = np.zeros(len(mvs), dtype=np.uint8); ta = np.zeros(len(als), dtype=np.uint8)
    if kind == "als_shift_all":
        shift = np.asarray(variant["shift_xyz_m"], dtype=np.float32)
        ta[:] = 1
        return mvs, (als + shift).astype("<f4"), tm, ta, "delta_all"
    pid_m = in_patches(mvs[:, :2], patches); pid_a = in_patches(als[:, :2], patches)
    if kind == "mvs_delete_patches":
        tm[pid_m > 0] = 1
        return mvs[pid_m == 0], als, tm, ta, "mvs_missing"
    if kind == "mvs_noise_patches":
        rng = np.random.default_rng(int(variant["noise_seed"]))
        out = mvs.copy(); sel = pid_m > 0
        out[sel, 2] += rng.normal(0.0, float(variant["sigma_m"]), size=int(sel.sum())).astype(np.float32)
        tm[sel] = 1
        return out.astype("<f4"), als, tm, ta, "mvs_noisy"
    if kind == "mvs_shift_patches":
        out = mvs.copy(); sel = pid_m > 0; out[sel, 2] += np.float32(variant["shift_z_m"]); tm[sel] = 1
        return out.astype("<f4"), als, tm, ta, "mvs_biased"
    if kind == "als_shift_patches":
        out = als.copy(); sel = pid_a > 0; out[sel, 2] += np.float32(variant["shift_z_m"]); ta[sel] = 1
        return mvs, out.astype("<f4"), tm, ta, "als_stale"
    raise ValueError(kind)


def truth_cells(top: np.ndarray, kind_name: str, patches: list[dict[str, Any]]) -> np.ndarray:
    cells = np.zeros(len(top), dtype=CELL_DTYPE)
    cells["ix"], cells["iy"] = top["ix"], top["iy"]
    if kind_name == "delta_all":
        cells["kind"] = CELL_KIND["delta_all"]; cells["patch_id"] = 0
        return cells
    lookup = {}
    for p in patches:
        for c in p["cells"]:
            lookup[(int(c[0]), int(c[1]))] = p["patch_id"]
    for i, (ix, iy) in enumerate(zip(top["ix"], top["iy"])):
        pid = lookup.get((int(ix), int(iy)), 0)
        cells["patch_id"][i] = pid
        cells["kind"][i] = CELL_KIND[kind_name] if pid else CELL_KIND["none"]
    return cells


# ----------------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------------

def verify(path: Path, expected_sha: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected_sha:
        raise RuntimeError(f"input drift: {label}")


def resolve_inputs(cfg: dict[str, Any]) -> dict[str, Path]:
    root = Path(cfg["artifact_root"]); inp = cfg["inputs"]
    rel = root / inp["source_relation_relative_root"]
    verify(rel / inp["partition_receipt"]["relative_path"], inp["partition_receipt"]["sha256"], "partition receipt")
    verify(rel / inp["relation_map"]["relative_path"], inp["relation_map"]["sha256"], "relation map")
    for s, item in inp["partitions"].items():
        verify(rel / item["relative_path"], item["sha256"], f"partition {s}")
    pair = root / inp["baseline_pairing_relative_root"]
    verify(pair / "artifact_manifest.json", inp["baseline_pairing_artifact_manifest_sha256"], "baseline pairing manifest")
    verify(pair / "validation_receipt.json", inp["baseline_pairing_validation_receipt_sha256"], "baseline pairing receipt")
    receipt = json.loads((pair / "validation_receipt.json").read_text(encoding="utf-8"))
    if receipt.get("artifact_manifest_sha256") != sha256(pair / "artifact_manifest.json") or any(v != "PASS" for v in receipt["checks"].values()):
        raise RuntimeError("baseline pairing receipt not bound or not PASS")
    return {"relation_root": rel, "pairing_root": pair}


def read_xyz(path: Path) -> np.ndarray:
    if path.stat().st_size % 12:
        raise ValueError(f"{path}: invalid xyz byte count")
    return np.fromfile(path, dtype="<f4").reshape(-1, 3)


def write_variant(out: Path, cfg: dict[str, Any], variant: dict[str, Any], roots: dict[str, Path], mvs: np.ndarray, als: np.ndarray,
                  top: np.ndarray, patches: list[dict[str, Any]], receipt_doc: dict[str, Any]) -> dict[str, Any]:
    tile = cfg["inputs"]["tile_id"]
    mvs_out, als_out, tm, ta, kind_name = apply_variant(variant, mvs, als, patches)
    vdir = out / variant["id"]
    atomic_bytes(vdir / f"partition/mvs/{tile}.xyz_f32le.bin", np.ascontiguousarray(mvs_out, dtype="<f4").tobytes())
    atomic_bytes(vdir / f"partition/als/{tile}.xyz_f32le.bin", np.ascontiguousarray(als_out, dtype="<f4").tobytes())
    shutil.copyfile(roots["relation_root"] / cfg["inputs"]["relation_map"]["relative_path"], vdir / "relation_map.npy")
    receipt = dict(receipt_doc)
    receipt["injection_bench"] = {"task_id": cfg["task_id"], "variant": variant["id"], "kind": variant["kind"],
                                  "note": "partition copies perturbed by the injection bench; the relation map is the frozen original (3D-a cores predate the injection)"}
    atomic_json(vdir / "partition_receipt.json", receipt)
    atomic_npy(vdir / "truth_mvs_u8.npy", tm); atomic_npy(vdir / "truth_als_u8.npy", ta)
    cells = truth_cells(top, kind_name, patches if kind_name != "delta_all" else [])
    atomic_npy(vdir / "truth_cells.npy", cells)
    files = {}
    for name in (f"partition/mvs/{tile}.xyz_f32le.bin", f"partition/als/{tile}.xyz_f32le.bin", "partition_receipt.json", "relation_map.npy",
                 "truth_mvs_u8.npy", "truth_als_u8.npy", "truth_cells.npy"):
        p = vdir / name; files[name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
    manifest = {"schema": "jointbuildgs.phd.injection_bench.variant.v1", "task_id": cfg["task_id"], "variant": variant, "cell_kind_name": kind_name,
                "cell_kind_code": CELL_KIND[kind_name], "patches": patches if kind_name != "delta_all" else [],
                "points": {"mvs_in": int(len(mvs)), "mvs_out": int(len(mvs_out)), "mvs_modified": int(tm.sum()), "als_in": int(len(als)), "als_out": int(len(als_out)), "als_modified": int(ta.sum())},
                "cells_injected": int(np.count_nonzero(cells["kind"])), "files": files, "generated_utc": utc_now(), "scientific_verdict": None}
    atomic_json(vdir / "injection_manifest.json", manifest)
    return manifest


def run(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]; out.mkdir(parents=True, exist_ok=True)
    roots = resolve_inputs(cfg)
    inp = cfg["inputs"]
    mvs = read_xyz(roots["relation_root"] / inp["partitions"]["mvs"]["relative_path"])
    als = read_xyz(roots["relation_root"] / inp["partitions"]["als"]["relative_path"])
    receipt_doc = json.loads((roots["relation_root"] / inp["partition_receipt"]["relative_path"]).read_text(encoding="utf-8"))
    pair_cells = np.load(roots["pairing_root"] / "pair_cells.npy", allow_pickle=False); top = pair_cells[pair_cells["layer"] == 0]
    candidates = candidate_patches(top, cfg["domain"], cfg["patch_rule"])
    patches = select_patches(candidates, cfg["patch_rule"])
    variants = {}
    for variant in cfg["variants"]:
        variants[variant["id"]] = write_variant(out, cfg, variant, roots, mvs, als, top, patches, receipt_doc)
    technical = {
        "schema": "jointbuildgs.phd.injection_bench.technical_return.v1", "task_id": cfg["task_id"], "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "generated_utc": utc_now(), "git_commit": git_head(), "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "driver": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))}, "domain": cfg["domain"], "patch_rule": cfg["patch_rule"],
        "candidate_patches": len(candidates), "selected_patches": len(patches), "patch_area_m2": float(len(patches) * cfg["patch_rule"]["grid_m"] ** 2),
        "compatible_planar_cells": int(np.count_nonzero((top["state"] == 1) & (top["rough"] == 0))),
        "variants": {k: {"kind": v["variant"]["kind"], "points": v["points"], "cells_injected": v["cells_injected"], "files": v["files"]} for k, v in variants.items()},
        "expectations_before_run": cfg["expectations_before_run"], "not_decided_here": cfg["not_decided_here"],
        "elapsed_seconds": time.perf_counter() - started, "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "technical_return.json", technical)
    atomic_json(out / "artifact_manifest.json", {"schema": "jointbuildgs.phd.injection_bench.artifact_manifest.v1", "task_id": cfg["task_id"],
                                                  "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY", "generated_utc": utc_now(), "git_commit": technical["git_commit"],
                                                  "config": technical["config"], "driver": technical["driver"], "inputs": {k: str(v) for k, v in roots.items()},
                                                  "variants": {k: v["files"] for k, v in variants.items()}, "patches": patches,
                                                  "prohibited_inputs_accessed": [], "scientific_verdict": None})
    return technical


def validate(cfg: dict[str, Any]) -> dict[str, Any]:
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    manifest = json.loads((out / "artifact_manifest.json").read_text(encoding="utf-8"))
    checks = {}
    for vid, files in manifest["variants"].items():
        for name, item in files.items():
            p = out / vid / name
            if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
                raise AssertionError(f"variant output drift: {vid}/{name}")
    checks["variant_hashes"] = "PASS"
    roots = resolve_inputs(cfg); checks["input_hashes_and_baseline_binding"] = "PASS"
    inp = cfg["inputs"]; tile = inp["tile_id"]
    mvs = read_xyz(roots["relation_root"] / inp["partitions"]["mvs"]["relative_path"]); als = read_xyz(roots["relation_root"] / inp["partitions"]["als"]["relative_path"])
    for variant in cfg["variants"]:
        vdir = out / variant["id"]
        vm = json.loads((vdir / "injection_manifest.json").read_text(encoding="utf-8"))
        tm = np.load(vdir / "truth_mvs_u8.npy", allow_pickle=False); ta = np.load(vdir / "truth_als_u8.npy", allow_pickle=False)
        m_out = read_xyz(vdir / f"partition/mvs/{tile}.xyz_f32le.bin"); a_out = read_xyz(vdir / f"partition/als/{tile}.xyz_f32le.bin")
        if len(tm) != len(mvs) or len(ta) != len(als):
            raise AssertionError(f"{variant['id']}: truth length drift")
        if variant["kind"] == "mvs_delete_patches":
            if len(m_out) != int((tm == 0).sum()) or not np.array_equal(m_out, mvs[tm == 0]):
                raise AssertionError(f"{variant['id']}: deleted points inconsistent")
        else:
            if len(m_out) != len(mvs) or np.any(m_out[tm == 0] != mvs[tm == 0]):
                raise AssertionError(f"{variant['id']}: untouched MVS points changed")
        if np.any(a_out[ta == 0] != als[ta == 0]):
            raise AssertionError(f"{variant['id']}: untouched ALS points changed")
        if variant["kind"] == "als_shift_all":
            if not np.allclose(a_out - als, np.asarray(variant["shift_xyz_m"], dtype=np.float32), atol=1e-4):
                raise AssertionError(f"{variant['id']}: ALS shift drift")
        if int(tm.sum()) != vm["points"]["mvs_modified"] or int(ta.sum()) != vm["points"]["als_modified"]:
            raise AssertionError(f"{variant['id']}: truth counts drift")
    checks["truth_consistency"] = "PASS"
    technical = json.loads((out / "technical_return.json").read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None or technical.get("prohibited_inputs_accessed") != []:
        raise AssertionError("technical return contract drift")
    checks["prohibited_inputs"] = "PASS"; checks["scientific_verdict_null"] = "PASS"
    receipt = {"schema": "jointbuildgs.phd.injection_bench.validation.v1", "task_id": cfg["task_id"], "generated_utc": utc_now(), "checks": checks,
               "artifact_manifest_sha256": sha256(out / "artifact_manifest.json"), "prohibited_inputs_accessed": [], "scientific_verdict": None}
    atomic_json(out / "validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("command", choices=("run", "validate", "run-and-validate"))
    args = parser.parse_args()
    cfg = load_config(args.config.resolve())
    if args.command in {"run", "run-and-validate"}:
        technical = run(cfg, args.config.resolve())
        print(json.dumps({k: technical[k] for k in ("candidate_patches", "selected_patches", "patch_area_m2", "compatible_planar_cells", "elapsed_seconds")}, indent=1))
        print(json.dumps({k: v["points"] for k, v in technical["variants"].items()}, indent=1))
    if args.command in {"validate", "run-and-validate"}:
        print(json.dumps(validate(cfg)["checks"], indent=1))


if __name__ == "__main__":
    main()
