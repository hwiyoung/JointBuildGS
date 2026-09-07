"""Copy the exact no-anchor runtime and amend memory placement only. No training."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil


PARENT_RECEIPT_SHA256 = "3f2347bc4728c3c1026aef52fda8d6860baf1302996424871a0d791c75a6ae1c"
TRAIN_SHA256 = "3a7124bd9a2cb01fd7004bd5dbd9e35151a1ee3045187c0b77b01303561788ab"
PATCHES = (
    ("import jbgs_no_anchor\n", "import jbgs_no_anchor\nimport jbgs_memory_recovery\n"),
    ("load_depth_set(args.lod_depth_path, all_cameras, target_size)",
     "load_depth_set(args.lod_depth_path, all_cameras, target_size, device=\"cpu\")"),
    ("load_depth_set(args.da_depth_path, all_cameras, target_size)",
     "load_depth_set(args.da_depth_path, all_cameras, target_size, device=\"cpu\")"),
    ("    jbgs_no_anchor.capture_initial_state(locals(), globals())\n",
     "    jbgs_no_anchor.capture_initial_state(locals(), globals())\n"
     "    memory_recovery = jbgs_memory_recovery.initialize(locals())\n"),
    ("        iter_start.record()\n",
     "        iter_start.record()\n"
     "        memory_recovery.before_forward(gaussians.optimizer, iteration)\n"),
    ("        da_depth = da_depth_maps.get(cam_name, None)\n",
     "        da_depth = da_depth_maps.get(cam_name, None)\n"
     "        lod_depth, da_depth = memory_recovery.depths_to_device(\n"
     "            lod_depth, da_depth, gaussians.get_xyz.device, iteration)\n"),
    ("        total_loss.backward()\n        gaussians.optimizer.step()\n",
     "        total_loss.backward()\n"
     "        memory_recovery.before_optimizer_step(gaussians.optimizer, iteration)\n"
     "        gaussians.optimizer.step()\n"
     "        memory_recovery.after_optimizer_step(gaussians.optimizer, iteration)\n"),
    ("        jbgs_no_anchor.audit_first_step(locals())\n",
     "        memory_recovery.after_step_boundary(gaussians.optimizer, iteration)\n"
     "        jbgs_no_anchor.audit_first_step(locals())\n"),
)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def hashes(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*.py"))
            if not {".git", "__pycache__"}.intersection(p.relative_to(root).parts)}


def patch_train(source):
    if "jbgs_memory_recovery" in source:
        raise ValueError("Memory recovery is already present")
    for old, new in PATCHES:
        if source.count(old) != 1:
            raise ValueError(f"Expected one frozen target: {old!r}")
        source = source.replace(old, new, 1)
    ast.parse(source)
    return source


def prepare(source, destination):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    source = source.resolve(strict=True)
    destination = destination.absolute()
    resolved = destination.resolve()
    if resolved == source or source in resolved.parents or destination.exists() or destination.is_symlink():
        raise ValueError("A fresh destination outside the immutable source is required")
    parent_path = source / "jbgs_no_anchor_runtime_receipt.json"
    if sha(parent_path) != PARENT_RECEIPT_SHA256 or sha(source / "train.py") != TRAIN_SHA256:
        raise ValueError("Exact no-anchor runtime identity differs")
    parent = json.loads(parent_path.read_text())
    before = hashes(source)
    if parent["status"] != "PASS_RUNTIME_PREPARED_NO_TRAINING" or before != parent["destination_python_sha256"]:
        raise ValueError("Original runtime implementation differs from its receipt")
    adapter = Path(__file__).with_name("memory_adapter.py")
    adapter_text = adapter.read_text()
    ast.parse(adapter_text)
    original = (source / "train.py").read_text()
    patched = patch_train(original)
    receipt = dict(schema="jointbuildgs.geogs.memory_recovery_runtime.v1", status="PREPARING",
        scientific_verdict=None, source=str(source), destination=str(destination),
        parent_runtime_receipt_sha256=PARENT_RECEIPT_SHA256,
        original_source_python_sha256=before, science_config_unchanged=True,
        script_sha256=sha(__file__), adapter_source_sha256=sha(adapter),
        training_launched=False, checkpoint_resume_supported=False, eligible_regions=["P1", "P2", "P3"],
        changes=["Native cv2 INTER_LINEAR depth resize and float32 values retained; only depth cache device becomes CPU",
                 "Only selected LoD/DA3 depth maps copied to CUDA, blocking, unchanged dtype",
                 "Only Adam exp_avg and exp_avg_sq moved to CPU before forward/backward",
                 "Moments restored to each current parameter device before the original CUDA optimizer.step",
                 "Step counters, parameters, gradients, optimizer arithmetic, zero_grad timing, camera/RNG order and all scientific settings unchanged",
                 "Moments remain on GPU for native densification, protection registration and every snapshot/trace boundary"],
        limits=["Transfer overhead changes timing; compute configuration does not change",
                "Whole-run bitwise equivalence and 30000-step completion are not established by preparation",
                "Incomplete offloaded cycles cannot be represented as complete resumable checkpoints"])
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, symlinks=False,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        (destination / "train.py").write_text(patched)
        (destination / "jbgs_memory_recovery.py").write_text(adapter_text)
        diff = "".join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True),
                                          fromfile="parent/train.py", tofile="memory_recovery/train.py"))
        (destination / "jbgs_memory_recovery.patch").write_text(diff)
        after = hashes(destination)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        if changed != ["jbgs_memory_recovery.py", "train.py"]:
            raise RuntimeError(f"Unexpected Python changes: {changed}")
        if hashes(source) != before or sha(parent_path) != PARENT_RECEIPT_SHA256:
            raise RuntimeError("Original runtime changed during preparation")
        if sha(destination / parent_path.name) != PARENT_RECEIPT_SHA256:
            raise RuntimeError("Copied parent runtime receipt changed")
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
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source, args.destination)
    print(json.dumps({key: result[key] for key in ("status", "destination", "science_config_unchanged", "training_launched")}, indent=2))
