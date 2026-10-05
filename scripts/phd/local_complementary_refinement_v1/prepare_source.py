"""Copy the exact parent GeoGS snapshot and patch only declared stage-2 paths."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


RAW_BLOCK = '''        lod_depth_loss = compute_depth_loss(
            render_pkg["surf_depth"], lod_depth,
            use_scale_invariant=args.use_scale_invariant
        )
        da_depth_loss = compute_depth_loss(
            render_pkg["surf_depth"],
            da_depth,
            conf_map=da_conf_weight if use_confidence else None,
            use_scale_invariant=args.use_scale_invariant
        )'''
STAGE2_BLOCK = '''            total_loss = rgb_loss + dist_loss + normal_loss
            if lod_depth is not None:
                total_loss += lambda_lod_anchor * lod_depth_loss
            if da_depth is not None:
                total_loss += (da_weight if dynamic_da else lambda_da_depth) * da_depth_loss'''
STAGE2_REPLACEMENT = '''            local_lod_loss, local_da_loss = local_depth_control.stage2_losses(
                render_pkg["surf_depth"], lod_depth, da_depth, lod_depth_loss, da_depth_loss,
                iteration=iteration, camera=cam_name, lambda_prior=lambda_lod_anchor,
                lambda_visual=(da_weight if dynamic_da else lambda_da_depth),
                visual_confidence=da_conf_weight if use_confidence else None,
            )
            total_loss = rgb_loss + dist_loss + normal_loss
            if lod_depth is not None:
                total_loss += lambda_lod_anchor * local_lod_loss
            if da_depth is not None:
                total_loss += (da_weight if dynamic_da else lambda_da_depth) * local_da_loss'''
RESTORE_BLOCK = '''    if state['source_sha256'] != digest(Path(__file__).with_name('train.py')):
        raise ValueError('Instrumented training source changed')
    if state['implementation_hashes'] != implementation_hashes():
        raise ValueError('An instrumented implementation file changed')'''
RESTORE_REPLACEMENT = '''    from jbgs_local_depth import verify_resume_source
    verify_resume_source(state, Path(__file__).parent, implementation_hashes())'''


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def implementation_hashes(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*.py"))
            if "submodules" not in p.parts and "__pycache__" not in p.parts}


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one {label} block; found {text.count(old)}")
    return text.replace(old, new, 1)


def prepare_source(parent, destination):
    parent = Path(parent).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")
    if destination.resolve().is_relative_to(parent):
        raise ValueError("Destination must not be inside the immutable source")
    for name in ("train.py", "jbgs_state.py"):
        if (parent / name).is_symlink():
            raise ValueError(f"Refuse to patch copied symlink: {name}")
    if (parent / "jbgs_local_depth.py").exists() or (parent / "local_source_provenance.json").exists():
        raise ValueError("Parent must be the original unpatched source snapshot")
    helper = Path(__file__).with_name("local_depth_loss.py")
    parent_hashes = implementation_hashes(parent)
    train = (parent / "train.py").read_text(encoding="utf-8")
    state = (parent / "jbgs_state.py").read_text(encoding="utf-8")
    train = replace_once(train, "import jbgs_state\n", "import jbgs_state\nimport jbgs_local_depth\n", "local import")
    train = replace_once(train, "    tb_writer = prepare_output_and_logger(dataset)\n",
                         "    tb_writer = prepare_output_and_logger(dataset)\n"
                         "    local_depth_control = jbgs_local_depth.LocalDepthController.from_environment(\n"
                         "        dataset.model_path, args.use_scale_invariant)\n", "controller initialization")
    raw_replacement = "        with local_depth_control.raw_loss_context(iteration > stage_switch_iter):\n" + "\n".join("    " + line for line in RAW_BLOCK.splitlines())
    train = replace_once(train, RAW_BLOCK, raw_replacement, "raw depth context")
    train = replace_once(train, STAGE2_BLOCK, STAGE2_REPLACEMENT, "stage2 objective")
    state = replace_once(state, RESTORE_BLOCK, RESTORE_REPLACEMENT, "anchor provenance")
    # Assert all patterns before creating anything; never patch parent files.
    compile(train, str(destination / "train.py"), "exec")
    compile(state, str(destination / "jbgs_state.py"), "exec")
    shutil.copytree(parent, destination, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (destination / "train.py").write_text(train, encoding="utf-8")
    (destination / "jbgs_state.py").write_text(state, encoding="utf-8")
    shutil.copy2(helper, destination / "jbgs_local_depth.py")
    if implementation_hashes(parent) != parent_hashes:
        raise RuntimeError("Parent source changed while preparing the isolated copy")
    receipt = {
        "schema": "JBGS_LOCAL_COMPLEMENTARY_SOURCE_v1", "scientific_verdict": None,
        "parent_path": str(parent), "prepared_path": str(destination),
        "parent_implementation_hashes": parent_hashes,
        "prepared_implementation_hashes": implementation_hashes(destination),
        "local_depth_module_sha256": digest(helper),
        "preparer_sha256": digest(Path(__file__)),
        "patch_scope": ["local_depth_module_import", "local_controller_environment",
                        "raw_stage2_loss_no_grad_only", "stage2_depth_objective_only",
                        "exact_parent_anchor_and_prepared_runtime_hash_verification"],
        "environment": {"JBGS_LOCAL_DEPTH_MODE": "disabled|complementary",
                        "JBGS_LOCAL_TAU0": "explicit common meters",
                        "JBGS_LOCAL_TAU1": "explicit common meters"},
    }
    with (destination / "local_source_provenance.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    receipt = prepare_source(args.parent, args.destination)
    print(json.dumps({"prepared_path": receipt["prepared_path"],
                      "train_sha256": receipt["prepared_implementation_hashes"]["train.py"],
                      "scientific_verdict": None}))


if __name__ == "__main__":
    main()
