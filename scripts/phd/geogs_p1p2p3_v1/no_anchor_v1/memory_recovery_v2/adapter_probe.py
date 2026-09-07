#!/usr/bin/env python3
"""Approved resource probe only: six Adam groups, storage cycles, no optimizer step.

Requires a reviewed GPU resource window. Uses at most 100k synthetic points,
128 MiB PyTorch device-allocator cap, 2 warmups/mode and <=8 sec scheduling
window. CUDA driver/context and torch import host RSS are separate overheads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import time
import traceback

import torch
from pinned_storage import GROUP_WIDTHS, load_v1, make_storage_class

MIB = 1024 ** 2


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--points", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--max-gpu-seconds", type=float, default=8)
    parser.add_argument("--v1-adapter", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--context-note", default="Two existing training processes continue. Shared GPU/PCIe interference is possible.")
    args = parser.parse_args(argv)
    if not (args.device >= 0 and 1 <= args.points <= 100000 and 1 <= args.repeats <= 8
            and 0 < args.max_gpu_seconds <= 8):
        parser.error("Require device >=0, points 1..100000, repeats 1..8, window (0,8] seconds")
    if args.receipt.exists():
        parser.error("Receipt exists; choose a new path")
    return args


def state_hashes(optimizer, base):
    result = {}
    for group in optimizer.param_groups:
        parameter = group["params"][0]
        state = optimizer.state[parameter]
        result[group["name"]] = {key: base.tensor_sha(value) for key, value in
            (("parameter", parameter), ("step", state["step"]),
             ("exp_avg", state["exp_avg"]), ("exp_avg_sq", state["exp_avg_sq"]))}
    return result


def run(args, receipt):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    base = load_v1(args.v1_adapter)
    device = torch.device("cuda", args.device)
    torch.cuda.set_device(device)
    allocator_cap = 128 * MIB
    properties = torch.cuda.get_device_properties(device)
    torch.cuda.set_per_process_memory_fraction(allocator_cap / properties.total_memory, device=device)
    receipt.update(torch_version=torch.__version__, cuda_version=torch.version.cuda,
        gpu_name=properties.name, allocator_cap_bytes=allocator_cap,
        cuda_context_excluded_from_allocator_cap=True,
        host_rss_limit_enforced=False, process_peak_rss_before_buffers_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    groups = []
    for name, width in GROUP_WIDTHS.items():
        parameter = torch.nn.Parameter(torch.full((args.points, width), .5, dtype=torch.float32).to(device))
        groups.append(dict(name=name, params=[parameter], lr=.001))
    optimizer = torch.optim.Adam(groups, eps=1e-15, foreach=True)
    for group in optimizer.param_groups:
        parameter = group["params"][0]
        optimizer.state[parameter] = dict(step=torch.tensor(17., dtype=torch.float32),
            exp_avg=torch.full(parameter.shape, .125, dtype=torch.float32).to(device),
            exp_avg_sq=torch.full(parameter.shape, .25, dtype=torch.float32).to(device))
    storage = {"v1_pageable": base.MomentStorage(),
               "v2_pinned_reuse": make_storage_class(base)()}
    step_ids = [id(optimizer.state[group["params"][0]]["step"]) for group in groups]
    parameter_pointers = [group["params"][0].data_ptr() for group in groups]
    before = state_hashes(optimizer, base)
    receipt["effective_parameter_bytes"] = args.points * 58 * 4
    receipt["effective_moment_bytes_one_direction"] = args.points * 58 * 4 * 2
    receipt["traffic_bytes_per_cycle"] = args.points * 58 * 4 * 4
    receipt["initial_state_sha256"] = before
    stream = torch.cuda.current_stream(device)
    rows = receipt["cycles"] = []
    iteration = 0
    begin_window = time.monotonic()
    deadline = begin_window + args.max_gpu_seconds
    for repeat in range(-2, args.repeats):
        modes = ("v1_pageable", "v2_pinned_reuse") if repeat % 2 == 0 else ("v2_pinned_reuse", "v1_pageable")
        for mode in modes:
            if time.monotonic() >= deadline:
                break
            iteration += 1
            instance = storage[mode]
            stream.synchronize()
            begin = time.perf_counter()
            amount = instance.offload(optimizer, iteration)
            stream.synchronize()
            offload_end = time.perf_counter()
            allocated_offloaded = torch.cuda.memory_allocated(device)
            restored = instance.restore(optimizer, iteration)
            stream.synchronize()
            restore_end = time.perf_counter()
            if amount != restored:
                raise RuntimeError("Moment byte count changed")
            rows.append(dict(repeat=repeat, warmup=repeat < 0, mode=mode,
                offload_seconds=offload_end - begin, restore_seconds=restore_end - offload_end,
                total_seconds=restore_end - begin, allocated_after_offload_bytes=allocated_offloaded,
                allocated_after_restore_bytes=torch.cuda.memory_allocated(device)))
        else:
            continue
        break
    receipt["measurement_window_seconds_including_warmups"] = time.monotonic() - begin_window
    after = state_hashes(optimizer, base)
    if before != after:
        raise RuntimeError("Synthetic parameter/moment/counter bytes changed")
    for index, group in enumerate(groups):
        parameter = group["params"][0]
        if (parameter.data_ptr() != parameter_pointers[index]
                or id(optimizer.state[parameter]["step"]) != step_ids[index] or parameter.grad is not None):
            raise RuntimeError("Parameter pointer, counter object or gradient changed")
    measured = {mode: {row["repeat"]: row for row in rows if row["mode"] == mode and not row["warmup"]}
                for mode in storage}
    common = sorted(set(measured["v1_pageable"]) & set(measured["v2_pinned_reuse"]))
    summary = {"paired_repeats": len(common)}
    if common:
        for field in ("offload_seconds", "restore_seconds", "total_seconds"):
            summary[field] = {mode: statistics.median(measured[mode][repeat][field] for repeat in common) for mode in storage}
            summary[field]["paired_v1_over_v2_median"] = statistics.median(
                measured["v1_pageable"][repeat][field] / measured["v2_pinned_reuse"][repeat][field] for repeat in common)
    receipt["summary"] = summary
    receipt["v2_cache"] = storage["v2_pinned_reuse"].cache_summary()
    receipt["peak_allocated_cuda_bytes"] = torch.cuda.max_memory_allocated(device)
    receipt["peak_reserved_cuda_bytes"] = torch.cuda.max_memory_reserved(device)
    receipt["process_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    receipt["state_bytes_equal"] = True
    receipt["first_roundtrip_checked"] = {name: instance.first_populated_cycle_checked for name, instance in storage.items()}
    receipt["status"] = ("PASS_BOUNDED_ADAPTER_MEASUREMENT" if common
        and receipt["measurement_window_seconds_including_warmups"] <= 10
        and receipt["peak_allocated_cuda_bytes"] <= allocator_cap else "FAIL_BUDGET_OR_NO_PAIRED_MEASUREMENT")


def main():
    args = arguments()
    receipt = dict(schema="jointbuildgs.geogs.pinned_adapter_probe.v1", status="FAIL", scientific_verdict=None,
        arguments={key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        sources_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                       (Path(__file__), Path(__file__).with_name("pinned_storage.py"), args.v1_adapter)},
        pid=os.getpid(), cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
        interpretation="Synthetic fixed-size storage cycles only. No optimizer step, backward, rendering, geometry, or training process changes. Pinned first allocation/hash checks are warmup-only. Not a total-training speed estimate.",
        timing_limit="Schedule cycles for at most 8 seconds; actual window must be <=10 seconds. Blocking CUDA calls cannot be forcibly preempted here.",
        interference=args.context_note)
    started = time.monotonic()
    try:
        run(args, receipt)
    except Exception:
        receipt.update(status="FAIL_ADAPTER_PROBE", error=traceback.format_exc())
    receipt["total_work_seconds_excluding_torch_import"] = time.monotonic() - started
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt), "summary": receipt.get("summary")}))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
