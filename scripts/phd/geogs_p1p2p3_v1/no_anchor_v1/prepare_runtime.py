"""Prepare an isolated, hash-bound GeoGS runtime for fresh SfM refinement.

This copies source and adds instrumentation only; it never launches training.
The original runtime is immutable. An existing destination is always rejected.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil


PINS = {
    "train.py": "08cfab996b144488b1a583bf722b991c627d90136a9031f85f7d33b1cae0c44b",
    "jbgs_state.py": "7114f78e6f429c9186ce44e81a0c40d18e5087994f99a52d81eeee18ab7fa570",
    "scene/gaussian_model.py": "4be070008683ba1943de9e22d1f4d1a9c194aef56010c0b3186d0bd7f6aadb9a",
    "arguments/__init__.py": "059113ea23d1905b750b9849f95aafb1f7ea3f644f8a261a656535454ec0c71c",
}
PATCHES = (
    ("import jbgs_state\n", "import jbgs_state\nimport jbgs_no_anchor\n"),
    (
        '    progress_bar = tqdm(range(first_iter, opt.iterations), desc="Training progress")\n',
        "    # Fresh SfM: reuse the native protection helpers before any optimizer step.\n"
        "    building_freeze_mask = jbgs_no_anchor.initialize_protection(locals(), globals())\n"
        "    freeze_done = False\n"
        "    jbgs_no_anchor.capture_initial_state(locals(), globals())\n\n"
        '    progress_bar = tqdm(range(first_iter, opt.iterations), desc="Training progress")\n',
    ),
    (
        "        if jbgs_state.after_step(locals()):\n",
        "        jbgs_no_anchor.audit_first_step(locals())\n"
        "        if jbgs_state.after_step(locals()):\n",
    ),
    (
        "    jbgs_state.register_args(parser)\n",
        "    jbgs_state.register_args(parser)\n    jbgs_no_anchor.register_args(parser)\n",
    ),
    (
        "    jbgs_state.validate_args(args)\n",
        "    jbgs_state.validate_args(args)\n    jbgs_no_anchor.validate_args(args)\n",
    ),
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def python_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob("*.py"))
        if not {".git", "__pycache__"}.intersection(path.relative_to(root).parts)
    }


def patch_train(source: str) -> str:
    if "jbgs_no_anchor" in source:
        raise ValueError("Runtime already contains the no-anchor adapter")
    patched = source
    for old, new in PATCHES:
        if patched.count(old) != 1:
            raise ValueError(f"Expected exactly one frozen patch target: {old!r}")
        patched = patched.replace(old, new, 1)
    ast.parse(patched)
    return patched


def prepare(source: Path, destination: Path) -> dict:
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    source = source.resolve(strict=True)
    destination = destination.absolute()
    # A missing descendant may resolve through existing parent symlinks.
    resolved_destination = destination.resolve()
    if resolved_destination == source or source in resolved_destination.parents:
        raise ValueError("Destination must be outside the immutable source tree")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    for relative, expected in PINS.items():
        path = source / relative
        if path.is_symlink() or digest(path) != expected:
            raise ValueError(f"Frozen runtime hash mismatch: {relative}")
    sidecar = Path(__file__).with_name("no_anchor_adapter.py")
    if not sidecar.is_file():
        raise FileNotFoundError(sidecar)
    sidecar_text = sidecar.read_text()
    ast.parse(sidecar_text)
    original_text = (source / "train.py").read_text()
    patched_text = patch_train(original_text)
    before = python_hashes(source)
    receipt = {
        "schema": "jointbuildgs.geogs.no_anchor_runtime.v1",
        "status": "PREPARING",
        "scientific_verdict": None,
        "source": str(source),
        "destination": str(destination),
        "source_python_sha256": before,
        "required_source_sha256": PINS,
        "preparer_sha256": digest(Path(__file__)),
        "sidecar_source_sha256": digest(sidecar),
        "training_launched": False,
        "new_initialization": "nonempty image-SfM PLY, checked against separate manifest",
        "pretrained_model_or_optimizer_loaded": False,
        "als_gaussians_inserted": False,
        "protection": "native proximity helpers applied once to fresh SfM before step1; native hook re-registration after densification unchanged",
        "stage2_from_iteration": 1,
        "schedule": "fresh absolute-iteration schedule; not the old 8001-30000 schedule",
        "continued_resume_supported": False,
    }
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, symlinks=False,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        (destination / "train.py").write_text(patched_text)
        (destination / "jbgs_no_anchor.py").write_text(sidecar_text)
        patch = "".join(difflib.unified_diff(
            original_text.splitlines(keepends=True), patched_text.splitlines(keepends=True),
            fromfile="frozen/train.py", tofile="no_anchor/train.py"))
        (destination / "jbgs_no_anchor_train.patch").write_text(patch)
        after_source = python_hashes(source)
        if after_source != before:
            raise RuntimeError("Original source changed during runtime preparation")
        after = python_hashes(destination)
        changed = sorted(name for name in set(before) | set(after)
                         if before.get(name) != after.get(name))
        if changed != ["jbgs_no_anchor.py", "train.py"]:
            raise RuntimeError(f"Unexpected source modifications: {changed}")
        receipt.update(status="PASS_RUNTIME_PREPARED_NO_TRAINING",
                       destination_python_sha256=after,
                       modified_or_added_python=changed,
                       patch_sha256=digest(destination / "jbgs_no_anchor_train.patch"),
                       original_source_unchanged=True)
    except Exception as error:
        receipt.update(status="FAILED_RUNTIME_PREPARATION",
                       error_type=type(error).__name__, error=str(error))
        if destination.is_dir():
            with (destination / "jbgs_no_anchor_runtime_receipt.json").open("x") as stream:
                json.dump(receipt, stream, indent=2)
        raise
    with (destination / "jbgs_no_anchor_runtime_receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source, args.destination)
    print(json.dumps({key: result[key] for key in (
        "status", "destination", "modified_or_added_python", "patch_sha256",
        "training_launched", "scientific_verdict")}, indent=2))


if __name__ == "__main__":
    main()
