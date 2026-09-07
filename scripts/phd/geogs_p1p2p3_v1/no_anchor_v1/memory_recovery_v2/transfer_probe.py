#!/usr/bin/env python3
"""Bounded CUDA transfer measurement. No torch import, kernels, or training.

The explicit GPU buffer cap excludes the CUDA driver/context. Wall-time checks
cannot preempt a stalled CUDA call: an overrun is reported as FAIL_BUDGET, never
presented as an enforced driver-level deadline. Run only with resource approval.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import time
import traceback

MIB = 1024 ** 2
PATTERN = 0x5A


class Cuda:
    def __init__(self, library):
        self.lib = C.CDLL(str(library))
        signatures = {
            "cudaSetDevice": [C.c_int],
            "cudaRuntimeGetVersion": [C.POINTER(C.c_int)],
            "cudaDriverGetVersion": [C.POINTER(C.c_int)],
            "cudaMalloc": [C.POINTER(C.c_void_p), C.c_size_t],
            "cudaFree": [C.c_void_p],
            "cudaHostAlloc": [C.POINTER(C.c_void_p), C.c_size_t, C.c_uint],
            "cudaFreeHost": [C.c_void_p],
            "cudaStreamCreateWithFlags": [C.POINTER(C.c_void_p), C.c_uint],
            "cudaStreamSynchronize": [C.c_void_p],
            "cudaStreamDestroy": [C.c_void_p],
            "cudaMemcpyAsync": [C.c_void_p, C.c_void_p, C.c_size_t, C.c_int, C.c_void_p],
            "cudaMemGetInfo": [C.POINTER(C.c_size_t), C.POINTER(C.c_size_t)],
        }
        for name, arguments in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, C.c_int
        self.lib.cudaGetErrorString.argtypes = [C.c_int]
        self.lib.cudaGetErrorString.restype = C.c_char_p

    def call(self, name, *args):
        code = getattr(self.lib, name)(*args)
        if code:
            message = self.lib.cudaGetErrorString(code).decode(errors="replace")
            raise RuntimeError(f"{name}: CUDA {code}: {message}")

    def version(self, name):
        value = C.c_int()
        self.call(name, C.byref(value))
        return value.value

    def memory(self):
        free, total = C.c_size_t(), C.c_size_t()
        self.call("cudaMemGetInfo", C.byref(free), C.byref(total))
        return {"free_bytes": free.value, "total_bytes": total.value}


def peak_rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def transfer_plan(sizes, repeats):
    # Rotate mode and direction order; timing always includes own-stream sync.
    for repeat in range(repeats):
        for size in sizes:
            for direction in (("H2D", "D2H") if repeat % 2 == 0 else ("D2H", "H2D")):
                for mode in (("pageable", "pinned") if repeat % 2 == 0 else ("pinned", "pageable")):
                    yield repeat, size, direction, mode


def summarize(rows):
    result = []
    for size in sorted({row["size_mib"] for row in rows}):
        for direction in ("H2D", "D2H"):
            groups = {mode: {row["repeat"]: row["seconds"] for row in rows
                             if row["size_mib"] == size and row["direction"] == direction
                             and row["mode"] == mode} for mode in ("pageable", "pinned")}
            paired = sorted(set(groups["pageable"]) & set(groups["pinned"]))
            if not paired:
                continue
            item = {"size_mib": size, "direction": direction, "paired_repeats": len(paired)}
            for mode in groups:
                median = statistics.median(groups[mode][r] for r in paired)
                item[mode + "_median_seconds"] = median
                item[mode + "_decimal_GB_per_second"] = size * MIB / median / 1e9
            item["paired_pageable_over_pinned_median"] = statistics.median(
                groups["pageable"][r] / groups["pinned"][r] for r in paired)
            result.append(item)
    return result


def run(args, receipt):
    cuda, stream, pinned = None, C.c_void_p(), C.c_void_p()
    devices, cleanup_errors = [], []
    rows = receipt["transfers"] = []
    started = time.monotonic()
    amount = max(args.sizes_mib) * MIB
    receipt["explicit_buffers"] = {"gpu_count": 2, "gpu_bytes": 2 * amount,
        "gpu_cap_bytes": 128 * MIB, "host_pageable_bytes": amount,
        "host_pinned_bytes": amount, "host_buffer_bytes": 2 * amount,
        "process_peak_rss_limit_bytes": 256 * MIB,
        "driver_context_gpu_memory_excluded": True}
    try:
        library = Path(args.cudart).resolve(strict=True)
        receipt["cudart"] = {"path": str(library),
            "sha256": hashlib.sha256(library.read_bytes()).hexdigest()}
        cuda = Cuda(library)
        cuda.call("cudaSetDevice", args.device)
        receipt["cuda_runtime_version"] = cuda.version("cudaRuntimeGetVersion")
        receipt["cuda_driver_version"] = cuda.version("cudaDriverGetVersion")
        receipt["memory_before_own_buffers"] = cuda.memory()
        cuda.call("cudaStreamCreateWithFlags", C.byref(stream), 1)
        for _ in range(2):
            pointer = C.c_void_p()
            cuda.call("cudaMalloc", C.byref(pointer), amount)
            devices.append(pointer)
        pageable = C.create_string_buffer(amount)
        page_pointer = C.cast(pageable, C.c_void_p)
        begin = time.perf_counter()
        cuda.call("cudaHostAlloc", C.byref(pinned), amount, 0)
        receipt["pinned_allocation_seconds"] = time.perf_counter() - begin
        C.memset(page_pointer, PATTERN, amount)
        C.memset(pinned, PATTERN, amount)
        cuda.call("cudaMemcpyAsync", devices[0], page_pointer, amount, 1, stream)
        cuda.call("cudaStreamSynchronize", stream)
        receipt["setup_seconds"] = time.monotonic() - started
        receipt["memory_with_own_buffers"] = cuda.memory()
        if peak_rss() > 256 * MIB:
            raise RuntimeError("Host peak RSS exceeded 256 MiB before measurement")
        begin_window = time.monotonic()
        deadline = begin_window + args.max_gpu_seconds
        for repeat, size, direction, mode in transfer_plan(args.sizes_mib, args.repeats):
            if time.monotonic() >= deadline:
                break
            host = page_pointer if mode == "pageable" else pinned
            destination, source, kind = ((devices[1], host, 1) if direction == "H2D"
                                          else (host, devices[0], 2))
            begin = time.perf_counter()
            cuda.call("cudaMemcpyAsync", destination, source, size * MIB, kind, stream)
            cuda.call("cudaStreamSynchronize", stream)
            duration = time.perf_counter() - begin
            rows.append({"repeat": repeat, "size_mib": size, "direction": direction,
                         "mode": mode, "seconds": duration})
            if peak_rss() > 256 * MIB:
                raise RuntimeError("Host peak RSS exceeded 256 MiB during measurement")
        receipt["measurement_window_seconds"] = time.monotonic() - begin_window
        # CPU checks only; both initialized and copied host buffers must retain
        # the same pattern. Hashing views does not allocate another full buffer.
        hashes = []
        for pointer in (page_pointer, pinned):
            view = memoryview((C.c_ubyte * amount).from_address(pointer.value))
            hashes.append(hashlib.sha256(view).hexdigest())
        receipt["host_buffer_sha256"] = hashes
        if hashes[0] != hashes[1]:
            raise RuntimeError("Pageable and pinned host buffers differ after copies")
        receipt["summary"] = summarize(rows)
        receipt["budget_pass"] = receipt["measurement_window_seconds"] <= 10 and peak_rss() <= 256 * MIB
        receipt["completed_plan"] = len(rows) == len(list(transfer_plan(args.sizes_mib, args.repeats)))
        receipt["status"] = "PASS_BOUNDED_TRANSFER_MEASUREMENT" if rows and receipt["budget_pass"] else "FAIL_BUDGET"
    finally:
        if cuda is not None:
            calls = [("cudaFree", pointer) for pointer in reversed(devices)]
            if pinned.value:
                calls.append(("cudaFreeHost", pinned))
            if stream.value:
                calls.append(("cudaStreamDestroy", stream))
            for name, pointer in calls:
                try:
                    cuda.call(name, pointer)
                except Exception as error:
                    cleanup_errors.append(str(error))
        receipt["cleanup_errors"] = cleanup_errors
        receipt["process_peak_rss_bytes"] = peak_rss()
        receipt["total_process_work_seconds"] = time.monotonic() - started
        if cleanup_errors:
            receipt["status"] = "FAIL_CLEANUP"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, default=0, help="CUDA_VISIBLE_DEVICES local index")
    parser.add_argument("--sizes-mib", type=int, nargs="+", default=[2, 8, 32])
    parser.add_argument("--repeats", type=int, default=6)
    parser.add_argument("--max-gpu-seconds", type=float, default=8)
    parser.add_argument("--cudart", default="/usr/local/cuda/lib64/libcudart.so")
    parser.add_argument("--context-note", default="Two existing training processes continue; shared GPU/PCIe timings may be affected.")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.device < 0 or not 1 <= args.repeats <= 8 or not 0 < args.max_gpu_seconds <= 8
            or any(size not in (2, 8, 32) for size in args.sizes_mib)
            or len(set(args.sizes_mib)) != len(args.sizes_mib)):
        parser.error("Require device >=0, repeats 1..8, window (0,8] sec, unique sizes from 2,8,32 MiB")
    if args.receipt.exists():
        parser.error("Receipt already exists; choose a new path")
    return args


def main():
    args = parse_args()
    payload = {"schema": "jointbuildgs.geogs.pinned_transfer_probe.v1", "status": "FAIL",
        "scientific_verdict": None, "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "pid": os.getpid(), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "interference": args.context_note,
        "scope": "Storage transfers only; no torch import, arithmetic kernels, optimizer, render, geometry, or process stop.",
        "timing_limits": "Own nonblocking stream synchronized after each copy; 8-second scheduling deadline and observed <=10-second measurement check. Driver-call stalls cannot be preempted here.",
        "interpretation": "Tests pageable versus pinned CUDA staging only. Does not measure total training speed or PyTorch host allocation/lifetime."}
    try:
        run(args, payload)
    except Exception:
        payload.update(status="FAIL_TRANSFER_PROBE", error=traceback.format_exc())
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as output:
        json.dump(payload, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": payload["status"], "receipt": str(args.receipt), "summary": payload.get("summary", [])}))
    return 0 if payload["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
