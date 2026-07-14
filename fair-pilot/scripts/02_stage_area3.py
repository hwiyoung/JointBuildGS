#!/usr/bin/env python3
"""Selectively stage the bounded Vaihingen Area 3 pilot subset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def append_log(path: Path, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{message}\n")
        f.flush()
        os.fsync(f.fileno())


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    fields = list(rows[0]) if rows else ["member", "status"]
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def allowed_members(zf: zipfile.ZipFile, images: list[str]) -> list[str]:
    exact = {
        "Vaihingen/Images/daporo.dat",
        "Vaihingen/Images/daporp.dat",
        "Vaihingen/Images/Vaihingen_Date_UTC.txt",
        "Vaihingen/Overview_Vaihingen_DMC.pdf",
        "Vaihingen/DSM/DSM_09cm_matching.tif",
        "Vaihingen/DSM/DSM_09cm_matching.tfw",
        "Vaihingen/DSM/DSM_25cm_ALS.tif",
        "Vaihingen/DSM/DSM_25cm_ALS.tfw",
        "Vaihingen/Ortho/TOP_Mosaic_09cm.tif",
        "Vaihingen/Ortho/TOP_Mosaic_09cm.tfw",
        "Vaihingen/ALS/Vaihingen_Strip_03.LAS",
        "Vaihingen/ALS/Vaihingen_Strip_05.LAS",
    }
    exact.update(f"Vaihingen/Images/{stem}.tif" for stem in images)
    prefixes = (
        "Vaihingen/Reference_3d_reconstruction/Reference_Area/borderline_area_3",
        "Vaihingen/Reference_3d_reconstruction/Reference_Buildings/building_outline_area_3",
        "Vaihingen/Reference_3d_reconstruction/Reference_Roofs/gebaeude_area_3_3D_dachflaechen.dxf",
    )
    names = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        if info.filename in exact or info.filename.startswith(prefixes):
            names.append(info.filename)
    missing = sorted(exact.difference(names))
    if missing:
        raise RuntimeError(f"archive is missing locked members: {missing}")
    return sorted(names)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="fair-pilot/config/vaihingen_area3.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    archive = ROOT / cfg["archive"]["path"]
    run_dir = ROOT / "fair-pilot" / "runs" / cfg["run_id"]
    log = run_dir / "run.log"
    stage_root = ROOT / "fair-pilot" / "staging"
    extracted = stage_root / "area3_source_epsg32632"
    raw_link = stage_root / "raw" / "Vaihingen.zip"
    rows: list[dict] = []
    append_log(log, "stage=selective_staging status=started")

    raw_link.parent.mkdir(parents=True, exist_ok=True)
    target = os.path.relpath(archive, raw_link.parent)
    if raw_link.is_symlink() or raw_link.exists():
        if not raw_link.is_symlink() or os.readlink(raw_link) != target:
            raise RuntimeError(f"refusing to replace unexpected staging path: {raw_link}")
    else:
        raw_link.symlink_to(target)
    append_log(log, f"raw_symlink={raw_link.relative_to(ROOT)} target={target}")

    with zipfile.ZipFile(archive) as zf:
        members = allowed_members(zf, cfg["pilot"]["images"])
        for index, name in enumerate(members, 1):
            info = zf.getinfo(name)
            relative = Path(*Path(name).parts[1:])
            destination = extracted / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_file() and destination.stat().st_size == info.file_size:
                digest = sha256_file(destination)
                status = "reused"
            else:
                tmp = destination.with_suffix(destination.suffix + ".part")
                digest_obj = hashlib.sha256()
                copied = 0
                next_mark = 256 << 20
                with zf.open(info, "r") as source, tmp.open("wb") as sink:
                    while chunk := source.read(16 << 20):
                        sink.write(chunk)
                        digest_obj.update(chunk)
                        copied += len(chunk)
                        if copied >= next_mark:
                            append_log(log, f"extract_progress member={name} bytes={copied}/{info.file_size}")
                            next_mark += 256 << 20
                    sink.flush()
                    os.fsync(sink.fileno())
                if copied != info.file_size:
                    raise RuntimeError(f"short extraction for {name}: {copied} != {info.file_size}")
                os.replace(tmp, destination)
                digest = digest_obj.hexdigest()
                status = "extracted"
            row = {
                "member": name,
                "staged_path": str(destination.relative_to(ROOT)),
                "status": status,
                "size_bytes": info.file_size,
                "sha256": digest,
                "archive_crc32_hex": f"{info.CRC:08x}",
            }
            rows.append(row)
            write_csv(run_dir / "stage_manifest.csv", rows)
            append_log(log, f"stage=selective_staging item={index}/{len(members)} status={status} member={name}")

    summary = {
        "task_id": cfg["task_id"],
        "run_id": cfg["run_id"],
        "stage": "selective_staging",
        "status": "complete",
        "source_archive": cfg["archive"]["path"],
        "source_archive_sha256": cfg["archive"]["expected_sha256"],
        "raw_staging": "relative_symlink",
        "pilot_area": cfg["pilot"]["area"],
        "source_crs": cfg["pilot"]["source_crs"],
        "output_crs": cfg["pilot"]["output_crs"],
        "members": len(rows),
        "staged_bytes": sum(int(r["size_bytes"]) for r in rows),
        "images": cfg["pilot"]["images"],
    }
    manifest = run_dir / "stage_summary.json"
    tmp = manifest.with_suffix(".json.part")
    tmp.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, manifest)
    append_log(log, f"stage=selective_staging status=complete members={len(rows)} bytes={summary['staged_bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
