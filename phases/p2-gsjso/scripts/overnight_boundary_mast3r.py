#!/usr/bin/env python3
"""Run the C-wave MASt3R correspondence queue with resumable atomic outputs.

Only reciprocal descriptor matches inside both projected roof masks are
counted.  No point reconstruction, GS optimization, checkpoint update, or
training operation is performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import cv2
import numpy as np
import torch
from PIL import Image as PILImage

import mast3r.utils.path_to_dust3r  # noqa: F401,E402
from dust3r.inference import inference  # noqa: E402
from dust3r.utils.image import ImgNorm  # noqa: E402
from mast3r.fast_nn import fast_reciprocal_NNs  # noqa: E402
from mast3r.model import AsymmetricMASt3R  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
RUN_DIR = REPO / "phases/p2-gsjso/runs/20260716_boundary_map"
JOBS_JSON = RUN_DIR / "mast3r_jobs.json"
RESULT_CSV = RUN_DIR / "mast3r_correspondence.csv"
PROGRESS_JSON = RUN_DIR / "mast3r_progress.json"
MANIFEST = RUN_DIR / "mast3r_manifest.json"
LOG = RUN_DIR / "mast3r.log"
SUPPORT_CSV = RUN_DIR / "boundary_map_support_metrics.csv"
METRICS_CSV = REPO / "docs/archive/boundary_map/v1/tables/boundary_map_metrics.csv"

MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256 = "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_BYTES = 2_754_661_648
LOAD_WIDTH = 512
LOAD_HEIGHT = 384
MATCH_SUBSAMPLE = 8
MATCH_BORDER_PX = 3

RESULT_FIELDS = [
    "building_id",
    "evaluation_scope",
    "priority_group",
    "priority_rank",
    "status",
    "failure_reason",
    "view_a",
    "view_b",
    "crop_a_xyxy",
    "crop_b_xyxy",
    "reciprocal_raw_count",
    "border_match_count",
    "roof_correspondence_count",
    "roof_correspondence_fraction_of_border",
    "model_revision",
    "model_sha256",
    "model_bytes",
    "match_rule",
    "projection_reference_height_used",
    "projection_reference_source",
    "elapsed_seconds",
    "completed_utc",
    "learning_runs_started",
    "new_inference_type",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}" if math.isfinite(value) else ""
    return value


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows([{key: fmt(row.get(key)) for key in fields} for row in rows])
    temporary.replace(path)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def log(message: str) -> None:
    line = f"{now()} {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def prepare_image(
    path: Path,
    box: Sequence[int],
    index: int,
) -> tuple[dict[str, Any], np.ndarray]:
    with PILImage.open(path) as source:
        crop = source.convert("RGB").crop(tuple(box)).resize(
            (LOAD_WIDTH, LOAD_HEIGHT),
            PILImage.Resampling.LANCZOS,
        )
    image = {
        "img": ImgNorm(crop)[None],
        "true_shape": np.int32([[LOAD_HEIGHT, LOAD_WIDTH]]),
        "idx": index,
        "instance": str(index),
    }
    return image, np.asarray(crop, dtype=np.uint8)


def projected_mask(
    rings: Sequence[Sequence[Sequence[float]]],
    box: Sequence[int],
) -> np.ndarray:
    x0, y0, x1, y1 = [float(value) for value in box]
    scale_x = LOAD_WIDTH / max(x1 - x0, 1.0)
    scale_y = LOAD_HEIGHT / max(y1 - y0, 1.0)
    mask = np.zeros((LOAD_HEIGHT, LOAD_WIDTH), dtype=np.uint8)
    polygons = []
    for ring in rings:
        array = np.asarray(ring, dtype=np.float64)
        if len(array) < 3:
            continue
        array[:, 0] = (array[:, 0] - x0) * scale_x
        array[:, 1] = (array[:, 1] - y0) * scale_y
        polygons.append(np.rint(array).astype(np.int32))
    if polygons:
        cv2.fillPoly(mask, polygons, 1)
    return mask.astype(bool)


def measure_job(
    model: Any,
    job: dict[str, Any],
    device: str,
) -> dict[str, Any]:
    started = time.monotonic()
    path_a = REPO / job["image_a"]
    path_b = REPO / job["image_b"]
    image_a, _rgb_a = prepare_image(path_a, job["crop_a_xyxy"], 0)
    image_b, _rgb_b = prepare_image(path_b, job["crop_b_xyxy"], 1)
    mask_a = projected_mask(job["projected_rings_a"], job["crop_a_xyxy"])
    mask_b = projected_mask(job["projected_rings_b"], job["crop_b_xyxy"])
    if not np.any(mask_a) or not np.any(mask_b):
        raise RuntimeError("projected roof mask empty after crop resize")
    with torch.inference_mode():
        output = inference(
            [(image_a, image_b)],
            model,
            device,
            batch_size=1,
            verbose=False,
        )
    descriptor_a = output["pred1"]["desc"].squeeze(0).detach()
    descriptor_b = output["pred2"]["desc"].squeeze(0).detach()
    matches_a, matches_b = fast_reciprocal_NNs(
        descriptor_a,
        descriptor_b,
        subsample_or_initxy1=MATCH_SUBSAMPLE,
        device=device,
        dist="dot",
        block_size=2**13,
    )
    raw_count = int(len(matches_a))
    border = (
        (matches_a[:, 0] >= MATCH_BORDER_PX)
        & (matches_a[:, 0] < LOAD_WIDTH - MATCH_BORDER_PX)
        & (matches_a[:, 1] >= MATCH_BORDER_PX)
        & (matches_a[:, 1] < LOAD_HEIGHT - MATCH_BORDER_PX)
        & (matches_b[:, 0] >= MATCH_BORDER_PX)
        & (matches_b[:, 0] < LOAD_WIDTH - MATCH_BORDER_PX)
        & (matches_b[:, 1] >= MATCH_BORDER_PX)
        & (matches_b[:, 1] < LOAD_HEIGHT - MATCH_BORDER_PX)
    )
    matches_a = matches_a[border]
    matches_b = matches_b[border]
    border_count = int(len(matches_a))
    inside = (
        mask_a[matches_a[:, 1], matches_a[:, 0]]
        & mask_b[matches_b[:, 1], matches_b[:, 0]]
    )
    roof_count = int(np.count_nonzero(inside))
    return {
        "building_id": job["building_id"],
        "evaluation_scope": job["evaluation_scope"],
        "priority_group": job["priority_group"],
        "priority_rank": job["priority_rank"],
        "status": "complete",
        "failure_reason": "",
        "view_a": job["view_a"],
        "view_b": job["view_b"],
        "crop_a_xyxy": ";".join(str(value) for value in job["crop_a_xyxy"]),
        "crop_b_xyxy": ";".join(str(value) for value in job["crop_b_xyxy"]),
        "reciprocal_raw_count": raw_count,
        "border_match_count": border_count,
        "roof_correspondence_count": roof_count,
        "roof_correspondence_fraction_of_border": (
            roof_count / border_count if border_count else 0.0
        ),
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "model_bytes": MODEL_BYTES,
        "match_rule": "reciprocal descriptor NN stride8; 3px border; both projected roof masks",
        "projection_reference_height_used": True,
        "projection_reference_source": job["projection_reference_source"],
        "elapsed_seconds": time.monotonic() - started,
        "completed_utc": now(),
        "learning_runs_started": 0,
        "new_inference_type": "MASt3R correspondence only",
    }


def failed_row(job: dict[str, Any], error: Exception, elapsed: float) -> dict[str, Any]:
    return {
        "building_id": job["building_id"],
        "evaluation_scope": job["evaluation_scope"],
        "priority_group": job["priority_group"],
        "priority_rank": job["priority_rank"],
        "status": "failed",
        "failure_reason": f"{type(error).__name__}: {error}",
        "view_a": job["view_a"],
        "view_b": job["view_b"],
        "crop_a_xyxy": ";".join(str(value) for value in job["crop_a_xyxy"]),
        "crop_b_xyxy": ";".join(str(value) for value in job["crop_b_xyxy"]),
        "reciprocal_raw_count": None,
        "border_match_count": None,
        "roof_correspondence_count": None,
        "roof_correspondence_fraction_of_border": None,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "model_bytes": MODEL_BYTES,
        "match_rule": "reciprocal descriptor NN stride8; 3px border; both projected roof masks",
        "projection_reference_height_used": True,
        "projection_reference_source": job["projection_reference_source"],
        "elapsed_seconds": elapsed,
        "completed_utc": now(),
        "learning_runs_started": 0,
        "new_inference_type": "MASt3R correspondence only",
    }


def update_public_metrics(results: Sequence[dict[str, Any]]) -> None:
    result_by_id = {row["building_id"]: row for row in results}
    support_rows = read_csv(SUPPORT_CSV)
    if not support_rows:
        return
    fields = list(support_rows[0])
    merged: list[dict[str, Any]] = []
    for row in support_rows:
        output: dict[str, Any] = dict(row)
        result = result_by_id.get(row["building_id"])
        if result:
            output.update(
                {
                    "mast3r_correspondence_count": result.get("roof_correspondence_count"),
                    "mast3r_reciprocal_raw_count": result.get("reciprocal_raw_count"),
                    "mast3r_border_count": result.get("border_match_count"),
                    "mast3r_status": result.get("status"),
                    "mast3r_view_a": result.get("view_a"),
                    "mast3r_view_b": result.get("view_b"),
                    "mast3r_crop_a_xyxy": result.get("crop_a_xyxy"),
                    "mast3r_crop_b_xyxy": result.get("crop_b_xyxy"),
                }
            )
        merged.append(output)
    atomic_csv(SUPPORT_CSV, merged, fields)
    atomic_csv(
        METRICS_CSV,
        [row for row in merged if row["evaluation_scope"] == "evaluation_178"],
        fields,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--max-seconds", type=float, default=43_100.0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    start = time.monotonic()
    weights = args.model_dir / "model.safetensors"
    if args.model_dir.name != MODEL_REVISION:
        raise RuntimeError(f"model revision mismatch: {args.model_dir.name}")
    if not weights.is_file() or weights.stat().st_size != MODEL_BYTES:
        raise RuntimeError("MASt3R model byte lock mismatch")
    if sha256_file(weights) != MODEL_SHA256:
        raise RuntimeError("MASt3R model SHA256 lock mismatch")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    jobs_payload = json.loads(JOBS_JSON.read_text(encoding="utf-8"))
    jobs = jobs_payload["jobs"]
    if args.limit > 0:
        jobs = jobs[: args.limit]
    existing = read_csv(RESULT_CSV)
    completed_ids = {row["building_id"] for row in existing}
    results: list[dict[str, Any]] = list(existing)
    atomic_json(
        PROGRESS_JSON,
        {
            "status": "loading_model",
            "created_utc": now(),
            "job_count": len(jobs),
            "existing_result_count": len(existing),
            "learning_runs_started": 0,
        },
    )
    log(
        f"start jobs={len(jobs)} resume={len(existing)} device={args.device} "
        "learning_runs_started=0"
    )
    model = AsymmetricMASt3R.from_pretrained(str(args.model_dir)).to(args.device)
    model.eval()
    log(f"model loaded elapsed_seconds={time.monotonic() - start:.1f}")

    timed_out = False
    for index, job in enumerate(jobs, start=1):
        if job["building_id"] in completed_ids:
            continue
        if time.monotonic() - start >= args.max_seconds:
            timed_out = True
            log(f"internal time budget reached before {job['building_id']}")
            break
        row_started = time.monotonic()
        try:
            row = measure_job(model, job, args.device)
        except Exception as error:  # keep the queue moving and preserve the failed row
            row = failed_row(job, error, time.monotonic() - row_started)
            log(f"failed {job['building_id']} {row['failure_reason']}")
        results.append(row)
        completed_ids.add(job["building_id"])
        results.sort(key=lambda item: int(item["priority_rank"]))
        atomic_csv(RESULT_CSV, results, RESULT_FIELDS)
        update_public_metrics(results)
        pending = [
            item["building_id"]
            for item in jobs
            if item["building_id"] not in completed_ids
        ]
        atomic_json(
            PROGRESS_JSON,
            {
                "status": "running",
                "updated_utc": now(),
                "completed_count": len(completed_ids),
                "queue_count": len(jobs),
                "pending_count": len(pending),
                "pending_buildings": pending,
                "last_building": job["building_id"],
                "elapsed_seconds": time.monotonic() - start,
                "learning_runs_started": 0,
            },
        )
        log(
            f"progress {index}/{len(jobs)} building={job['building_id']} "
            f"status={row['status']} roof_correspondence={row.get('roof_correspondence_count', '')} "
            f"elapsed_seconds={time.monotonic() - start:.1f}"
        )

    pending = [
        item["building_id"]
        for item in jobs
        if item["building_id"] not in completed_ids
    ]
    status = "time_budget_reached" if timed_out or pending else "complete"
    atomic_json(
        PROGRESS_JSON,
        {
            "status": status,
            "updated_utc": now(),
            "completed_count": len(completed_ids),
            "queue_count": len(jobs),
            "pending_count": len(pending),
            "pending_buildings": pending,
            "elapsed_seconds": time.monotonic() - start,
            "learning_runs_started": 0,
        },
    )
    manifest = {
        "schema": "jointbuildgs.boundary_map.mast3r.v1",
        "created_utc": now(),
        "status": status,
        "device": args.device,
        "cuda_device_name": (
            torch.cuda.get_device_name(torch.cuda.current_device())
            if args.device.startswith("cuda") and torch.cuda.is_available()
            else ""
        ),
        "max_seconds": args.max_seconds,
        "elapsed_seconds": time.monotonic() - start,
        "job_count": len(jobs),
        "result_count": len(results),
        "pending_buildings": pending,
        "model": {
            "revision": MODEL_REVISION,
            "weights_sha256": MODEL_SHA256,
            "weights_bytes": MODEL_BYTES,
        },
        "jobs_sha256": sha256_file(JOBS_JSON),
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in [RESULT_CSV, PROGRESS_JSON, LOG, SUPPORT_CSV, METRICS_CSV]
            if path.is_file()
        },
        "learning_runs_started": 0,
        "new_inference_type": "MASt3R correspondence only",
        "interpretation_or_verdict": None,
    }
    atomic_json(MANIFEST, manifest)
    log(
        f"finish status={status} results={len(results)} pending={len(pending)} "
        f"elapsed_seconds={time.monotonic() - start:.1f} learning_runs_started=0"
    )


if __name__ == "__main__":
    main()
