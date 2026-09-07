#!/usr/bin/env python3
"""Fresh no-anchor v3 source generator; v2 train.py and original runtime preserved."""
import argparse
import ast
import difflib
import importlib.util
import json
from pathlib import Path
import shutil

V2_HASHES = {"prepare_runtime.py": "3517b2815a9d5a0a24b446627fc6994921c1013f2ecf2fce91183f99192bd28f",
             "runtime_adapter.py": "9a925bfdafd14ef2aabe6a372615dfc4c0aeced362c064d7f0c0ef0d5182f450",
             "pinned_storage.py": "6b95cdf3fb42d7351853e4be6045be46c46975601295aa39cf8d1a7fdead66db"}
TRAIN_SHA = "1680d6e357877a03811c912804d211fe7c4b77562ecf24999d573fb4897450cb"
GAUSSIAN_SHA = "4be070008683ba1943de9e22d1f4d1a9c194aef56010c0b3186d0bd7f6aadb9a"


def sha(path):
    import hashlib
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): value.update(block)
    return value.hexdigest()


def load_v2(directory):
    for name, expected in V2_HASHES.items():
        if sha(directory / name) != expected: raise ValueError("Frozen v2 file changed: " + name)
    spec = importlib.util.spec_from_file_location("jbgs_v2_preparer", directory / "prepare_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(source, destination, v1_directory, v2_directory):
    if not Path("/.dockerenv").is_file(): raise RuntimeError("Docker required")
    v2 = load_v2(v2_directory)
    if sha(source / "scene/gaussian_model.py") != GAUSSIAN_SHA: raise ValueError("Frozen native save_ply source changed")
    folder = Path(__file__).parent
    for name in ("runtime_adapter.py", "stream_ply.py"): ast.parse((folder / name).read_text())
    inherited = v2.prepare(source, destination, v1_directory)
    v1 = v2.load_preparer(v1_directory)
    destination = destination.absolute()
    parent_receipt = destination / "jbgs_memory_recovery_receipt.json"
    parent_sha = sha(parent_receipt)
    parent_receipt.rename(destination / "jbgs_memory_recovery_v2_receipt.json")
    receipt = dict(inherited, resource_recovery_version=3, status="PREPARING",
        script_sha256=sha(__file__), v2_implementation_source_sha256=V2_HASHES,
        v2_runtime_receipt_sha256=parent_sha, checkpoint_resume_supported=False,
        v2_destination_python_sha256=inherited["destination_python_sha256"],
        train_py_identical_to_memory_recovery_v2=True, native_gaussian_model_sha256=GAUSSIAN_SHA,
        early_parameter_gradient_release=True, stream_ply=True,
        changes=inherited["changes"] + [
            "Release previous parameter gradients via zero_grad(set_to_none=True) before next forward; original before-backward clear retained",
            "Bind only live Gaussian instance save_ply to bounded65536-row serializer; same native binary61-float32 field/vertex order",
            "Preserve v2 wrapper and its generated receipt bytes as separate provenance modules/records"],
        limits=inherited["limits"] + [
            "Previous-gradient release helps next forward only; does not reduce current backward tensor requirements",
            "PLY streaming bounds serialization staging, not checkpoint torch.save or total future process peak",
            "Only fresh SfM retries supported; no full-state resume or scientific parameter changes"])
    try:
        shutil.copyfile(destination / "jbgs_memory_recovery.py", destination / "jbgs_memory_recovery_v2_base.py")
        shutil.copyfile(folder / "runtime_adapter.py", destination / "jbgs_memory_recovery.py")
        shutil.copyfile(folder / "stream_ply.py", destination / "jbgs_stream_ply.py")
        after = v1.hashes(destination)
        before = inherited["destination_python_sha256"]
        changed_v2 = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        if changed_v2 != ["jbgs_memory_recovery.py", "jbgs_memory_recovery_v2_base.py", "jbgs_stream_ply.py"]:
            raise RuntimeError("Unexpected v2 source modification")
        if sha(destination / "train.py") != TRAIN_SHA or sha(destination / "scene/gaussian_model.py") != GAUSSIAN_SHA:
            raise RuntimeError("Frozen arithmetic/save-source files changed")
        if v1.hashes(source) != inherited["original_source_python_sha256"]: raise RuntimeError("Original source changed")
        if sha(destination / "jbgs_memory_recovery_v2_base.py") != V2_HASHES["runtime_adapter.py"]:
            raise RuntimeError("Original v2 runtime wrapper bytes changed")
        patch = "".join(difflib.unified_diff((v2_directory / "runtime_adapter.py").read_text().splitlines(True),
            (folder / "runtime_adapter.py").read_text().splitlines(True), fromfile="v2/jbgs_memory_recovery.py", tofile="v3/jbgs_memory_recovery.py"))
        (destination / "jbgs_memory_recovery_v3.patch").write_text(patch)
        receipt.update(status="PASS_MEMORY_RECOVERY_RUNTIME_PREPARED", destination_python_sha256=after,
            adapter_source_sha256=sha(folder / "runtime_adapter.py"),
            added_module_source_sha256={name: after[name] for name in ("jbgs_memory_recovery_v1_base.py", "jbgs_pinned_storage.py",
                "jbgs_memory_recovery_v2_base.py", "jbgs_memory_recovery.py", "jbgs_stream_ply.py")},
            modified_or_added_python=sorted(k for k in set(after) | set(inherited["original_source_python_sha256"])
                if after.get(k) != inherited["original_source_python_sha256"].get(k)),
            changed_from_memory_recovery_v2=changed_v2, v3_patch_sha256=sha(destination / "jbgs_memory_recovery_v3.patch"))
    except Exception as error:
        receipt.update(status="FAIL_MEMORY_RECOVERY_RUNTIME_PREPARATION", error_type=type(error).__name__, error=str(error))
        with parent_receipt.open("x") as stream: json.dump(receipt, stream, indent=2)
        raise
    with parent_receipt.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--v1-directory", type=Path, required=True)
    parser.add_argument("--v2-directory", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source, args.destination, args.v1_directory, args.v2_directory)
    print(json.dumps({key: result[key] for key in ("status", "destination", "resource_recovery_version", "storage_version")}))
