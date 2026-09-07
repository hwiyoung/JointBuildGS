#!/usr/bin/env python3
"""Prepare a fresh hash-bound v2 source copy; never launch/resume training."""
import argparse
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

V1_PREPARER_SHA256 = "5be6b12931b3a4a4a2d5e0868267e9d71f8b79b377008550de195aa8985e8eaf"
V1_ADAPTER_SHA256 = "de4ba2a8c6a50efd670b195479b07962052c9cec10efd35d594c3ba9dc69c114"
EXPECTED_PATCHED_TRAIN_SHA256 = "1680d6e357877a03811c912804d211fe7c4b77562ecf24999d573fb4897450cb"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_preparer(v1_directory):
    file = v1_directory / "prepare_runtime.py"
    if sha(file) != V1_PREPARER_SHA256 or sha(v1_directory / "memory_adapter.py") != V1_ADAPTER_SHA256:
        raise ValueError("Frozen v1 preparer/adapter identity differs")
    spec = importlib.util.spec_from_file_location("jbgs_v1_preparer", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(source, destination, v1_directory=None):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    folder = Path(__file__).parent
    v1_directory = (v1_directory or folder.parent / "memory_recovery_v1").resolve(strict=True)
    v1 = load_preparer(v1_directory)
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if (destination.exists() or destination.is_symlink() or destination.resolve() == source
            or source in destination.resolve().parents):
        raise ValueError("Require a new destination outside the immutable source")
    parent_path = source / "jbgs_no_anchor_runtime_receipt.json"
    if sha(parent_path) != v1.PARENT_RECEIPT_SHA256 or sha(source / "train.py") != v1.TRAIN_SHA256:
        raise ValueError("Exact original no-anchor source differs")
    parent = json.loads(parent_path.read_text())
    before = v1.hashes(source)
    if parent["status"] != "PASS_RUNTIME_PREPARED_NO_TRAINING" or before != parent["destination_python_sha256"]:
        raise ValueError("Original Python hashes differ from the preserved parent receipt")
    text = (source / "train.py").read_text()
    patched = v1.patch_train(text)
    if hashlib.sha256(patched.encode()).hexdigest() != EXPECTED_PATCHED_TRAIN_SHA256:
        raise ValueError("v2 must retain exactly the already-validated v1 train.py bytes")
    files = {"jbgs_memory_recovery_v1_base.py": v1_directory / "memory_adapter.py",
             "jbgs_pinned_storage.py": folder / "pinned_storage.py",
             "jbgs_memory_recovery.py": folder / "runtime_adapter.py"}
    for file in files.values():
        ast.parse(file.read_text())
    receipt = dict(schema="jointbuildgs.geogs.memory_recovery_runtime.v1", storage_version=2,
        status="PREPARING", scientific_verdict=None, source=str(source), destination=str(destination),
        parent_runtime_receipt_sha256=v1.PARENT_RECEIPT_SHA256,
        original_source_python_sha256=before, science_config_unchanged=True,
        script_sha256=sha(__file__), v1_preparer_sha256=V1_PREPARER_SHA256,
        adapter_source_sha256=sha(folder / "runtime_adapter.py"),
        added_module_source_sha256={name: sha(path) for name, path in files.items()},
        training_launched=False, checkpoint_resume_supported=False, eligible_regions=["P1", "P2", "P3"],
        train_py_identical_to_memory_recovery_v1=True,
        changes=["Exact existing v1 train.py patch: CPU depth cache and selected-map CUDA copies; original resize and dtype",
                 "Byte-identical frozen v1 moment/lifecycle adapter retained as jbgs_memory_recovery_v1_base.py",
                 "Only D2H moment destination changes to stable pinned CPU buffers with power-of-two capacity",
                 "Original v1 blocking restore, pointer/counter guards, optimizer math and stage/snapshot boundaries retained",
                 "Growth/prune reuse twelve named slots; no persistent old parameter or gradient references",
                 "Before growth enforce existing cgroup RAM budget capped at32GiB with complete-snapshot reserve and1GiB margin",
                 "Add cache policy, periodic cache-capacity telemetry and final lifecycle cache receipt"],
        limits=["Storage throughput measurements do not establish whole-training speed or trajectory bitwise equality",
                "Retired allocations may remain in PyTorch host cache; requested history is bounded but total future process peaks are not guaranteed",
                "Resource guard failure changes no Gaussian count, densification, scientific parameter or host limit",
                "No checkpoint resume or interrupted-state reinterpretation is added"])
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, symlinks=False, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        (destination / "train.py").write_text(patched)
        for name, file in files.items():
            shutil.copyfile(file, destination / name)
        patch = "".join(difflib.unified_diff(text.splitlines(True), patched.splitlines(True),
            fromfile="parent/train.py", tofile="memory_recovery_v2/train.py"))
        (destination / "jbgs_memory_recovery.patch").write_text(patch)
        after = v1.hashes(destination)
        changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        if changed != sorted([*files, "train.py"]):
            raise RuntimeError("Unexpected Python source mutation")
        if v1.hashes(source) != before or sha(parent_path) != v1.PARENT_RECEIPT_SHA256:
            raise RuntimeError("Original source changed during preparation")
        if sha(destination / parent_path.name) != v1.PARENT_RECEIPT_SHA256:
            raise RuntimeError("Parent receipt bytes changed")
        receipt.update(status="PASS_MEMORY_RECOVERY_RUNTIME_PREPARED", destination_python_sha256=after,
            modified_or_added_python=changed, original_source_unchanged=True,
            parent_runtime_receipt_bytes_preserved=True,
            patch_sha256=sha(destination / "jbgs_memory_recovery.patch"))
    except Exception as error:
        receipt.update(status="FAIL_MEMORY_RECOVERY_RUNTIME_PREPARATION", error_type=type(error).__name__, error=str(error))
        if destination.is_dir():
            with (destination / "jbgs_memory_recovery_receipt.json").open("x") as stream:
                json.dump(receipt, stream, indent=2)
        raise
    with (destination / "jbgs_memory_recovery_receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--v1-directory", type=Path)
    args = parser.parse_args()
    result = prepare(args.source, args.destination, args.v1_directory)
    print(json.dumps({key: result[key] for key in ("status", "destination", "science_config_unchanged", "storage_version")}, indent=2))
