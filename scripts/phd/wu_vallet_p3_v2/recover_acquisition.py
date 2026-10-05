"""Read immutable ALS, recover P3 acquisition fields and recorded scan order."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import time
import traceback

import laspy
import numpy as np

from src.phd.wu_vallet_p3_v2.acquisition import group_pulses, recover_scan_coordinates


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def record(path, expected=None):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    value = dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())
    if expected and value["sha256"] != expected:
        raise ValueError(f"Hash mismatch {path}")
    return value


def statistics(a):
    a = np.asarray(a)
    v, n = np.unique(a, return_counts=True)
    return dict(count=len(a), finite_count=int(np.isfinite(a).sum()),
                minimum=float(v[0]), maximum=float(v[-1]), unique_count=len(v),
                value_counts={str(x): int(y) for x, y in zip(v, n)} if len(v) <= 100 else None)


def raw_arrays(points):
    return {"gps_time": np.asarray(points.gps_time).copy(),
            "strip": np.asarray(points.point_source_id).copy(),
            "return_number": np.asarray(points.return_number).copy(),
            "number_of_returns": np.asarray(points.number_of_returns).copy(),
            "scan_angle_rank": np.asarray(points.scan_angle_rank).copy(),
            "scan_direction_flag": np.asarray(points.scan_direction_flag).copy(),
            "edge_of_flight_line": np.asarray(points.edge_of_flight_line).copy(),
            "xyz_raw": np.column_stack([points.x, points.y, points.z])}


def main(config_path, output_override=None):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Project processing must run in pinned Docker")
    cfg = json.loads(Path(config_path).read_text())
    root = Path(cfg["artifact_root"])
    output = Path(output_override) if output_override else root / cfg["output_relative_path"]
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write(output / "STARTED.json", dict(utc=datetime.now(timezone.utc).isoformat(), task_id=cfg["task_id"], scientific_verdict=None))
    try:
        source = json.loads(Path(cfg["source_config"]).read_text())
        spec = source["inputs"]["existing_als"]
        shift = np.asarray(source["frame"]["world_shift_xyz_m"])
        native_path = root / cfg["native_relative_path"]
        records = [record(native_path, cfg["native_sha256"]), record(config_path), record(cfg["source_config"]),
                   record(__file__), record("src/phd/wu_vallet_p3_v2/acquisition.py")]
        native = np.load(native_path, allow_pickle=False)
        n = len(native["als_xyz"])
        if n != cfg["expected_p3_points"]:
            raise ValueError("Frozen P3 count differs")
        names = sorted(spec["files"])
        p3 = {}
        for fi in np.unique(native["als_original_file_index"]):
            take = np.flatnonzero(native["als_original_file_index"] == fi)
            rows = native["als_original_row"][take]
            with laspy.open(root / spec["relative_root"] / names[int(fi)]) as handle:
                if "gps_time" not in handle.header.point_format.dimension_names:
                    raise ValueError("GPS time absent; scan recovery is unavailable")
                handle.seek(int(rows.min()))
                points = handle.read_points(int(rows.max() - rows.min() + 1))[rows - rows.min()]
                for key, arr in raw_arrays(points).items():
                    if key not in p3:
                        p3[key] = np.empty((n,) + arr.shape[1:], dtype=arr.dtype)
                    p3[key][take] = arr
        p3_xyz = p3.pop("xyz_raw") + np.array([0, 0, spec["z_shift_m"]]) - shift
        if not np.array_equal(p3_xyz.astype(np.float32), native["als_xyz"]):
            raise ValueError("Every-row P3 raw XYZ replay failed")
        if not np.isfinite(p3["gps_time"]).all():
            raise ValueError("P3 has non-finite GPS time")
        windows = {int(s): [float(p3["gps_time"][p3["strip"] == s].min() - cfg["context_time_padding_seconds"]),
                            float(p3["gps_time"][p3["strip"] == s].max() + cfg["context_time_padding_seconds"])]
                   for s in np.unique(p3["strip"])}
        buffers, header_records = {}, []
        for fi, name in enumerate(names):
            path = root / spec["relative_root"] / name
            records.append(record(path, spec["files"][name]))
            offset = 0
            with laspy.open(path) as handle:
                header_records.append(dict(file=name, point_count=handle.header.point_count,
                                           point_format=handle.header.point_format.id,
                                           global_encoding=handle.header.global_encoding.value,
                                           gps_time_type=str(handle.header.global_encoding.gps_time_type),
                                           scales=handle.header.scales.tolist(), offsets=handle.header.offsets.tolist(),
                                           dimensions=list(handle.header.point_format.dimension_names)))
                for chunk in handle.chunk_iterator(2_000_000):
                    t, s = np.asarray(chunk.gps_time), np.asarray(chunk.point_source_id)
                    keep = np.zeros(len(t), dtype=bool)
                    for strip, (lo, hi) in windows.items():
                        keep |= (s == strip) & (t >= lo) & (t <= hi)
                    if keep.any():
                        values = raw_arrays(chunk[keep])
                        values["original_row"] = np.flatnonzero(keep).astype(np.int64) + offset
                        values["original_file_index"] = np.full(int(keep.sum()), fi, dtype=np.int16)
                        for key, arr in values.items():
                            buffers.setdefault(key, []).append(arr)
                    offset += len(chunk)
            print(f"Read and hash verified {name}", flush=True)
        context = {k: np.concatenate(v) for k, v in buffers.items()}
        context["xyz"] = context.pop("xyz_raw") + np.array([0, 0, spec["z_shift_m"]]) - shift
        keys = context["original_file_index"].astype(np.uint64) * (1 << 32) + context["original_row"].astype(np.uint64)
        p3keys = native["als_original_file_index"].astype(np.uint64) * (1 << 32) + native["als_original_row"].astype(np.uint64)
        if len(np.unique(keys)) != len(keys):
            raise ValueError("Duplicate raw rows in temporal context")
        order = np.argsort(keys)
        positions = np.searchsorted(keys[order], p3keys)
        if (positions >= len(keys)).any() or not np.array_equal(keys[order[positions]], p3keys):
            raise ValueError("P3 membership missing from context")
        p3_context_row = order[positions]
        if not np.array_equal(context["xyz"][p3_context_row], p3_xyz):
            raise ValueError("P3 context XYZ replay mismatch")
        for key, values in p3.items():
            if not np.array_equal(context[key][p3_context_row], values):
                raise ValueError(f"P3 field mismatch: {key}")
        pulse = group_pulses(context["gps_time"], context["strip"], context["return_number"],
                             context["number_of_returns"], context["xyz"])
        pulse_count = len(pulse["pulse_gps_time"])
        for name, dtype in [("scan_id", np.int32), ("beam_order", np.int64), ("beam_coordinate", np.float64), ("complete_scan", bool)]:
            pulse["pulse_" + name] = np.empty(pulse_count, dtype=dtype)
        scans = []
        for strip in sorted(windows):
            idx = np.flatnonzero(pulse["pulse_strip"] == strip)
            t = pulse["pulse_gps_time"][idx]
            angle = context["scan_angle_rank"][pulse["pulse_first_context_row"][idx]]
            primary = recover_scan_coordinates(t, angle, cfg["scan_reset_degrees"], cfg["minimum_scan_boundaries"])
            sensitivity = []
            for threshold in cfg["scan_reset_sensitivity_degrees"]:
                alt = recover_scan_coordinates(t, angle, threshold, cfg["minimum_scan_boundaries"])
                sensitivity.append(dict(reset_degrees=threshold,
                                        identical_scan_assignments=bool(np.array_equal(primary["scan_id"], alt["scan_id"])),
                                        boundary_count=len(alt["boundary_rows"])))
            for name in ["scan_id", "beam_order", "beam_coordinate", "complete_scan"]:
                pulse["pulse_" + name][idx] = primary[name]
            scans.append(dict(strip=strip, pulse_count=len(idx), report=primary["report"], reset_sensitivity=sensitivity))
        arrays = {"context_" + k: v for k, v in context.items()}
        arrays.update(pulse)
        arrays.update({"p3_" + k: v for k, v in p3.items()})
        arrays.update(p3_xyz=p3_xyz, p3_context_row=p3_context_row,
                      p3_original_row=native["als_original_row"], p3_original_file_index=native["als_original_file_index"])
        p3_pid = pulse["context_pulse_id"][p3_context_row]
        arrays["p3_pulse_id"] = p3_pid
        for name in ["scan_id", "beam_order", "beam_coordinate", "complete_scan"]:
            arrays["p3_" + name] = pulse["pulse_" + name][p3_pid]
        np.savez_compressed(output / "acquisition.npz", **arrays)
        for path, target in [(config_path, "config.json"), (__file__, "recover_acquisition.py"),
                             ("src/phd/wu_vallet_p3_v2/acquisition.py", "acquisition.py")]:
            shutil.copyfile(path, output / target)
        report = dict(task_id=cfg["task_id"], status="RECORDED_GPS_PULSE_AND_SCAN_COORDINATES_RECOVERED",
                      scientific_verdict=None, input_records=records, headers=header_records,
                      frame=source["frame"], transform="Raw XYZ + [0,0,45.7] - frozen world shift; no registration fitting",
                      p3_every_original_row_verified=True, p3_native_count=n,
                      p3_field_statistics={k: statistics(v) for k, v in p3.items()},
                      context_field_statistics={k: statistics(v) for k, v in context.items() if k not in ["xyz", "original_row"]},
                      temporal_windows_by_strip=windows, scan_recovery=scans,
                      pulses=dict(count=pulse_count, complete=int(pulse["pulse_complete"].sum()),
                                  ambiguous=int(pulse["pulse_ambiguous"].sum()),
                                  multi_return=int((pulse["pulse_return_count"] > 1).sum()),
                                  complete_multi_return=int((pulse["pulse_complete"] & (pulse["pulse_return_count"] > 1)).sum()),
                                  p3_complete_scan_rows=int(arrays["p3_complete_scan"].sum())),
                      limitations=["GPS time + angle reset recovers observed scan order; it does not provide the ALS optical centre.",
                                   "Exact equal GPS time groups returns within each strip; duplicate return indices are flagged ambiguous.",
                                   "All original returns are preserved. Selecting one return per pulse for a mesh is a downstream explicit choice.",
                                   "First and last context scans may be truncated. P3 complete_scan exposes that condition.",
                                   "Continuous beam coordinates use elapsed GPS time so missing pulses do not compress acquisition gaps.",
                                   "Reset thresholds 2, 5, 10 and 20 degrees are engineering sensitivity settings, not unpublished author parameters.",
                                   "Four available spatial raw tiles limit temporal context; no missing return is invented."],
                      runtime=dict(python=platform.python_version(), numpy=np.__version__, laspy=laspy.__version__,
                                   docker_image=os.environ.get("JBGS_IMAGE_ID"), git_head=os.environ.get("JBGS_GIT_HEAD")),
                      elapsed_seconds=time.monotonic() - started,
                      outputs={p.name: record(p) for p in sorted(output.iterdir()) if p.is_file()})
        write(output / "receipt.json", report)
        print(json.dumps({k: report[k] for k in ["status", "p3_native_count", "pulses", "scan_recovery", "elapsed_seconds"]}), flush=True)
    except Exception:
        write(output / "FAILED.json", dict(traceback=traceback.format_exc(), scientific_verdict=None))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    main(args.config, args.output)
