#!/usr/bin/env python3
"""E5 pilot B-stage read-out and Roofer gate material tools.

Host-side orchestrator.  It keeps the existing P2 GS-semantic pointcloud
read-out and the P0 Roofer/status rules intact, but expands them to the fixed
C001 pilot block and the {sparse,dense,acmp} x {r1,r2} runs.

Observation only: this script writes tables and logs; it does not change the
recipe or choose a gate outcome.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from e5_baseline_tools import (
    classify_buildings,
    combine_cityjsonseq,
    parse_roofer_features,
    write_status_csv,
)


REPO = Path(__file__).resolve().parents[3]
P0 = REPO / "phases/p0-audit"
P0_RUNS = P0 / "runs"
P2_RUNS = REPO / "phases/p2-gsjso/runs"
FOOTPRINTS_GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
FOOTPRINTS_GPKG_CT = "/workspace/data/work/w2/footprints_scene_aoi.gpkg"
P0_COMPOSE = ["docker", "compose", "-f", str(P0 / "env/docker-compose.p0.yml")]
TOOLS_RUN = [
    "docker",
    "run",
    "--rm",
    "-i",
    "--user",
    f"{os.getuid()}:{os.getgid()}",
    "-v",
    f"{REPO}:/workspace/JointBuildGS",
    "-w",
    "/workspace/JointBuildGS",
    "jointbuildgs-p0-tools:t0",
]
DEV_IMAGE = "jointbuildgs:dev"
TRAIN_RUN_ID = "e5p_train_20260707_C001"
GATE_RUN_ID = "e5p_gate_20260707_C001"
READOUT_STRING = "readout(gssem; semantic-TSDF[minobs3, voxel0.05]; Roofer eps0.3/minpts15/complexity0.888)"
Z_DATUM_HISTORY = "E5 pilot GS: C001 cropped scene uses zeta -558.3 linked constants; output P_utm in EPSG:25832 ellipsoidal frame"
C001_SHORT_IDS = [
    "108247349",
    "108247350",
    "108247351",
    "4907184",
    "4907185",
    "4907186",
    "4907188",
    "4907194",
    "4907195",
    "4907198",
    "4907199",
    "4907202",
    "4908168",
    "4908178",
    "4908179",
    "60098",
    "8568391",
    "8568392",
]
C001_IDS = [f"DEBY_LOD2_{bid}" for bid in C001_SHORT_IDS]
ARMS = ("sparse", "dense", "acmp")
REPS = ("r1", "r2")


def run_names() -> list[str]:
    return [f"gs_e5_C001_{arm}_{rep}" for arm in ARMS for rep in REPS]


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def run(cmd: list[str], log_path: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    print("+ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log_path:
        log_path.write_text("+ " + " ".join(cmd) + "\n" + (proc.stdout or ""), encoding="utf-8")
    if proc.stdout:
        print(proc.stdout, end="", flush=True)
    if check:
        proc.check_returncode()
    return proc


def footprint_bboxes() -> dict[str, list[float]]:
    payload = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    out: dict[str, list[float]] = {}
    for feat in payload["features"]:
        bid = feat.get("properties", {}).get("building_id")
        if bid not in C001_IDS:
            continue
        coords = feat["geometry"]["coordinates"]
        if feat["geometry"]["type"] == "Polygon":
            rings = [coords[0]]
        else:
            rings = [poly[0] for poly in coords]
        xs = [float(pt[0]) for ring in rings for pt in ring]
        ys = [float(pt[1]) for ring in rings for pt in ring]
        out[bid] = [min(xs), min(ys), max(xs), max(ys)]
    missing = sorted(set(C001_IDS) - set(out))
    if missing:
        raise RuntimeError(f"C001 footprints missing from {FOOTPRINTS_GEOJSON}: {missing}")
    return out


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def parse_train_log(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    for key in ("START_UTC", "END_UTC"):
        m = re.search(rf"{key}=([0-9TZ:\-]+)", text)
        if m:
            out[key.lower()] = m.group(1)
    m = re.search(r"\[done\]\s+(\d+) iter in ([0-9.]+) min\.\s+final N=(\d+)", text)
    if m:
        out.update({"max_iter": m.group(1), "elapsed_min": m.group(2), "final_n": m.group(3)})
    return out


def fingerprint_train(args: argparse.Namespace) -> None:
    run_dir = P2_RUNS / args.train_run_id
    rows = []
    for name in run_names():
        cfg = REPO / "configs/tum_mob/e5_pilot" / f"{name}.yaml"
        ckpt = REPO / "results/tum_transfer/e5_pilot/C001/runs" / name / "ckpt/final.pt"
        log = REPO / "results/tum_transfer/e5_pilot/C001/train_logs" / f"{name}.log"
        item = {
            "run_name": name,
            "arm": name.split("_")[-2],
            "replicate": name.split("_")[-1],
            "config": rel(cfg),
            "config_sha256": sha256_file(cfg) if cfg.exists() else "missing",
            "versions": rel(run_dir / "versions.txt"),
            "ckpt": rel(ckpt),
            "ckpt_sha256": sha256_file(ckpt) if ckpt.exists() else "missing",
            "pointcloudification": "GS training checkpoint only; pointcloudification in B2 readout",
            "readout": READOUT_STRING,
            "geoid_flag": Z_DATUM_HISTORY,
            "log": rel(log),
        }
        item.update(parse_train_log(log))
        rows.append(item)
    out = run_dir / "train_fingerprints.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_name",
        "arm",
        "replicate",
        "config",
        "config_sha256",
        "versions",
        "ckpt",
        "ckpt_sha256",
        "pointcloudification",
        "readout",
        "geoid_flag",
        "log",
        "start_utc",
        "end_utc",
        "max_iter",
        "elapsed_min",
        "final_n",
    ]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"out": rel(out), "rows": len(rows)}, ensure_ascii=False))


def dev_docker_base(args: argparse.Namespace) -> list[str]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--gpus",
        "all",
        "-e",
        "HOME=/tmp",
        "-e",
        f"TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/{args.torch_extensions}",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
    ]
    if args.gpu:
        cmd.extend(["-e", f"CUDA_VISIBLE_DEVICES={args.gpu}"])
    cmd.append(DEV_IMAGE)
    return cmd


def readout(args: argparse.Namespace) -> None:
    out_rows = []
    for name in run_names():
        ckpt = f"results/tum_transfer/e5_pilot/C001/runs/{name}/ckpt/final.pt"
        out_npz = f"results/tum_transfer/e5_pilot/C001/readout/{name}/tsdf_gssem.npz"
        log = REPO / "results/tum_transfer/e5_pilot/C001/readout" / name / "readout.log"
        cmd = dev_docker_base(args) + [
            "python",
            "phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py",
            "--ckpt",
            ckpt,
            "--out",
            out_npz,
            "--data-root",
            args.data_root,
            "--geojson",
            "results/tum_transfer/analysis/footprints_aoi.geojson",
            "--buffer",
            str(args.buffer_m),
            "--min-obs",
            str(args.min_obs),
            "--voxel",
            str(args.voxel),
            "--targets",
            *C001_SHORT_IDS,
        ]
        run(cmd, log_path=log)
        path = REPO / out_npz
        out_rows.append(
            {
                "run_name": name,
                "tsdf_npz": out_npz,
                "tsdf_sha256": sha256_file(path) if path.exists() else "missing",
                "readout": READOUT_STRING,
                "z_datum_history": Z_DATUM_HISTORY,
                "log": rel(log),
            }
        )
    run_dir = P2_RUNS / args.train_run_id
    out_csv = run_dir / "readout_fingerprints.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)
    print(json.dumps({"out": rel(out_csv), "rows": len(out_rows)}, ensure_ascii=False))


def patch_prep_no_las(row: dict[str, str], metrics: dict[str, Any] | None) -> None:
    if not metrics or metrics.get("classified_las"):
        return
    row.update(
        {
            "status": "failure",
            "reason": "pointcloud_unusable_no_points",
            "rf_success": "True",
            "rf_extrusion_mode": "skip",
            "rf_pointcloud_unusable": "True",
            "rf_roof_type": "no points",
            "rf_pt_density": "0.000000",
            "rf_nodata_frac": "1.000000",
            "rf_rmse_lod22": "",
            "rf_roof_planes": "0",
            "has_lod22": "False",
            "val3dity_valid": "",
            "val3dity_errors": "",
        }
    )


def target_id_from_roofer_dir(path: Path) -> str:
    match = re.match(r"roofer_(DEBY_LOD2_\d+)_run_\d+$", path.parent.name)
    if not match:
        raise RuntimeError(f"Cannot infer target building id from Roofer output path: {path}")
    return match.group(1)


def filter_cityjsonseq_to_target(source: Path, target_id: str, output: Path) -> bool:
    """Keep only the target feature from a per-building Roofer bbox run.

    C001 has close footprints, so one bbox run can emit neighbouring buildings.
    Filtering avoids duplicate CityObject ids when per-building runs are merged.
    """
    kept = False
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8") as src, output.open("w", encoding="utf-8") as dst:
        header = src.readline()
        dst.write(header)
        for line in src:
            if not line.strip():
                continue
            feature = json.loads(line)
            cityobjects = feature.get("CityObjects", {})
            if feature.get("id") == target_id or target_id in cityobjects:
                dst.write(json.dumps(feature, ensure_ascii=False, separators=(",", ":")) + "\n")
                kept = True
                break
    return kept


def filtered_cityjsonseq_files(jsonl_files: list[Path], gate_dir: Path, name: str, rep_name: str) -> list[Path]:
    out: list[Path] = []
    for source in jsonl_files:
        target_id = target_id_from_roofer_dir(source)
        filtered = gate_dir / "filtered_cityjsonseq" / name / rep_name / source.parent.name / source.name
        if filter_cityjsonseq_to_target(source, target_id, filtered):
            out.append(filtered)
    return out


def assemble(args: argparse.Namespace) -> None:
    gate_dir = P0_RUNS / args.gate_run_id
    bboxes = footprint_bboxes()
    all_status_rows: list[dict[str, str]] = []
    metric_rows: list[dict[str, Any]] = []
    for name in run_names():
        npz = REPO / "results/tum_transfer/e5_pilot/C001/readout" / name / "tsdf_gssem.npz"
        if not npz.exists():
            raise FileNotFoundError(npz)
        for repeat in range(1, args.repeats + 1):
            rep_name = f"run_{repeat}"
            label = f"GS-{name.split('_')[-2]}-{name.split('_')[-1]}"
            outdir_host = gate_dir / "roofer" / name / rep_name
            outdir_ct = f"/workspace/JointBuildGS/{rel(outdir_host)}"
            outdir_roofer = f"/workspace/runs/{gate_dir.name}/roofer/{name}/{rep_name}"
            outdir_host.mkdir(parents=True, exist_ok=True)
            logs = gate_dir / "logs" / name / rep_name
            prep_metrics_by_bid: dict[str, dict[str, Any] | None] = {}
            for bid in C001_IDS:
                prep_log = logs / f"{bid}_prep.log"
                prep_cmd = TOOLS_RUN + [
                    "python3",
                    "phases/p2-gsjso/scripts/_mob_prep_las_gssem.py",
                    "--tsdf",
                    f"/workspace/JointBuildGS/{rel(npz)}",
                    "--bid",
                    bid,
                    "--geojson",
                    "/workspace/JointBuildGS/results/tum_transfer/analysis/footprints_aoi.geojson",
                    "--buffer",
                    str(args.buffer_m),
                    "--target-density",
                    "0.0",
                    "--outdir",
                    outdir_ct,
                    "--tag",
                    rep_name,
                ]
                prep_proc = run(prep_cmd, log_path=prep_log, check=False)
                metrics_path = outdir_host / f"{bid}_{rep_name}_metrics.json"
                metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
                prep_metrics_by_bid[bid] = metrics
                metric_rows.append(
                    {
                        "run_name": name,
                        "roofer_repeat": rep_name,
                        "building_id": bid,
                        "prep_returncode": prep_proc.returncode,
                        "n_clip": "" if metrics is None else metrics.get("n_clip", ""),
                        "n_used": "" if metrics is None else metrics.get("n_used", ""),
                        "n_building": "" if metrics is None else metrics.get("n_building", ""),
                        "n_building_in_fp": "" if metrics is None else metrics.get("n_building_in_fp", ""),
                        "classified_las": "" if metrics is None else metrics.get("classified_las", ""),
                    }
                )
                clf = None if metrics is None else metrics.get("classified_las")
                if not clf:
                    continue
                clf_roofer = str(clf).replace("/workspace/JointBuildGS/phases/p0-audit/runs", "/workspace/runs")
                x0, y0, x1, y1 = bboxes[bid]
                roof_out_ct = f"{outdir_roofer}/roofer_{bid}_{rep_name}"
                roofer_cmd = P0_COMPOSE + [
                    "run",
                    "-T",
                    "--rm",
                    "roofer",
                    "--id-attribute",
                    "building_id",
                    "--box",
                    f"{x0:.3f}",
                    f"{y0:.3f}",
                    f"{x1:.3f}",
                    f"{y1:.3f}",
                    clf_roofer,
                    FOOTPRINTS_GPKG_CT,
                    roof_out_ct,
                ]
                run(roofer_cmd, log_path=logs / f"{bid}_roofer.log", check=False)

            jsonl_files = filtered_cityjsonseq_files(sorted(outdir_host.glob("roofer_*/*.city.jsonl")), gate_dir, name, rep_name)
            cityjson = gate_dir / "cityjson" / f"{name}_{rep_name}.city.json"
            val_report = gate_dir / "val3dity" / f"{name}_{rep_name}_val3dity.json"
            val_by_id: dict[str, dict[str, Any]] = {}
            roofer_by_id: dict[str, dict[str, Any]] = {}
            if jsonl_files:
                combine_cityjsonseq(jsonl_files, cityjson)
                cj_ct = f"/workspace/runs/{gate_dir.name}/cityjson/{cityjson.name}"
                rep_ct = f"/workspace/runs/{gate_dir.name}/val3dity/{val_report.name}"
                val_report.parent.mkdir(parents=True, exist_ok=True)
                run(
                    P0_COMPOSE + ["run", "-T", "--rm", "tools", "val3dity", cj_ct, "--report", rep_ct],
                    log_path=logs / "val3dity.log",
                    check=False,
                )
                roofer_by_id = parse_roofer_features(jsonl_files)
                if val_report.exists():
                    val_payload = json.loads(val_report.read_text(encoding="utf-8"))
                    val_by_id = {
                        str(feature.get("id")): feature
                        for feature in val_payload.get("features", [])
                        if feature.get("id") is not None
                    }
            rows = classify_buildings(label, C001_IDS, roofer_by_id, val_by_id)
            for row in rows:
                patch_prep_no_las(row, prep_metrics_by_bid.get(row["building_id"]))
            status_csv = gate_dir / "status" / f"{name}_{rep_name}.csv"
            write_status_csv(status_csv, rows)
            for row in rows:
                with_extra = {
                    "run_name": name,
                    "arm": name.split("_")[-2],
                    "replicate": name.split("_")[-1],
                    "roofer_repeat": rep_name,
                    **row,
                }
                all_status_rows.append(with_extra)
            print(
                json.dumps(
                    {
                        "run_name": name,
                        "repeat": rep_name,
                        "has_lod22": sum(r["has_lod22"] == "True" for r in rows),
                        "valid": sum(r["val3dity_valid"] == "True" for r in rows),
                        "status_csv": rel(status_csv),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    combined = gate_dir / "building_reconstruction_status.csv"
    combined.parent.mkdir(parents=True, exist_ok=True)
    with combined.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(all_status_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_status_rows)
    metrics_csv = gate_dir / "prep_metrics.csv"
    with metrics_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(metric_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(metric_rows)
    write_gate_versions(gate_dir, args)
    print(json.dumps({"status_csv": rel(combined), "prep_metrics": rel(metrics_csv)}, ensure_ascii=False))


def write_gate_versions(gate_dir: Path, args: argparse.Namespace) -> None:
    lines = [
        f"run_id: {gate_dir.name}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5-B3 GS pilot Roofer assembly repeats",
        "mode: observation only; no recipe change; no gate verdict",
        "crs: EPSG:25832",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'], cwd=REPO)}",
        f"git_branch: {capture(['git', 'branch', '--show-current'], cwd=REPO)}",
        "docker_images:",
        "  gs_readout: jointbuildgs:dev",
        "  roofer_tools: jointbuildgs-p0-tools:t0 and P0 roofer compose service",
        f"readout: {READOUT_STRING}",
        f"z_datum_history: {Z_DATUM_HISTORY}",
        "roofer_defaults: eps0.3/minpts15/complexity0.888 default family; no input-kind tuning",
        f"repeats_per_training_run: {args.repeats}",
        f"buffer_m: {args.buffer_m}",
        "outputs:",
        f"  status: {rel(gate_dir / 'building_reconstruction_status.csv')}",
        f"  prep_metrics: {rel(gate_dir / 'prep_metrics.csv')}",
    ]
    (gate_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_repeats(args: argparse.Namespace) -> None:
    status_path = P0_RUNS / args.gate_run_id / "building_reconstruction_status.csv"
    with status_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out_rows = []
    for name in run_names():
        for bid in C001_IDS:
            sub = [r for r in rows if r["run_name"] == name and r["building_id"] == bid]
            by_rep = {r["roofer_repeat"]: r for r in sub}
            vals = [by_rep.get(f"run_{i}", {}).get("has_lod22", "") for i in range(1, args.repeats + 1)]
            out_rows.append(
                {
                    "run_name": name,
                    "arm": name.split("_")[-2],
                    "replicate": name.split("_")[-1],
                    "building_id": bid,
                    "run_1_has_lod22": vals[0] if vals else "",
                    "repeat_has_lod22_values": ";".join(vals),
                    "repeat_flip": str(len(set(vals)) > 1),
                    "run_1_status": by_rep.get("run_1", {}).get("status", ""),
                    "run_1_reason": by_rep.get("run_1", {}).get("reason", ""),
                    "run_1_rf_rmse_lod22": by_rep.get("run_1", {}).get("rf_rmse_lod22", ""),
                    "run_1_rf_roof_planes": by_rep.get("run_1", {}).get("rf_roof_planes", ""),
                }
            )
    out = P2_RUNS / args.train_run_id / "repeat_flip_table.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)
    summary = Counter(r["repeat_flip"] for r in out_rows)
    print(json.dumps({"out": rel(out), "repeat_flip_counts": dict(summary)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    fp = sub.add_parser("fingerprint-train")
    fp.add_argument("--train-run-id", default=TRAIN_RUN_ID)

    ro = sub.add_parser("readout")
    ro.add_argument("--train-run-id", default=TRAIN_RUN_ID)
    ro.add_argument("--data-root", default="results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20")
    ro.add_argument("--torch-extensions", default="results/tum_transfer/e5_pilot/C001/torch_extensions")
    ro.add_argument("--gpu", default="0")
    ro.add_argument("--buffer-m", type=float, default=20.0)
    ro.add_argument("--min-obs", type=int, default=3)
    ro.add_argument("--voxel", type=float, default=0.05)

    asm = sub.add_parser("assemble")
    asm.add_argument("--gate-run-id", default=GATE_RUN_ID)
    asm.add_argument("--buffer-m", type=float, default=20.0)
    asm.add_argument("--repeats", type=int, default=3)

    sr = sub.add_parser("summarize-repeats")
    sr.add_argument("--train-run-id", default=TRAIN_RUN_ID)
    sr.add_argument("--gate-run-id", default=GATE_RUN_ID)
    sr.add_argument("--repeats", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "fingerprint-train":
        fingerprint_train(args)
    elif args.cmd == "readout":
        readout(args)
    elif args.cmd == "assemble":
        assemble(args)
    elif args.cmd == "summarize-repeats":
        summarize_repeats(args)
    else:
        raise AssertionError(args.cmd)


if __name__ == "__main__":
    main()
