"""Create a hash-bound P1 intervention copy; never modify the parent MVS source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


PROVENANCE_NAME = "p1_single_view_weight_source_provenance.json"
SCHEMA = "JBGS_P1_SINGLE_VIEW_WEIGHT_SOURCE_v2"
EXPECTED_PARENT = {
    "train.py": "b032b84ee63788b821915784bfc1de12fa4e5aa40862ef59f3ae38973e56b262",
    "jbgs_state.py": "dbf1f370bdaee9a243f6986e56e865583d7aec483a5ec07d67cef66e50a9b400",
    "gaussian_renderer/__init__.py": "6a7710f9a52aaf419705fbb983d6cdaeb8c6986e33a07446267ce2d407448492",
}
INIT_BLOCK = "    mvs_pgsr_control = jbgs_mvs_pgsr.from_environment(dataset, opt, pipe, args)\n"
INIT_REPLACEMENT = INIT_BLOCK + "    p1_weight_control = jbgs_p1_weight.Controller(dataset.model_path, args, mvs_pgsr_control)\n"
RAW_BLOCK = '''        da_depth_loss = compute_depth_loss(
            render_pkg["surf_depth"],
            da_depth,
            conf_map=da_conf_weight if use_confidence else None,
            use_scale_invariant=args.use_scale_invariant
        )'''
RAW_REPLACEMENT = RAW_BLOCK + '''
        da_depth_loss = p1_weight_control.apply(
            render_pkg["surf_depth"], da_depth, da_depth_loss,
            camera=cam_name, iteration=iteration)'''
RESUME_IMPORT = "    from jbgs_mvs_pgsr_source import verify_resume_source\n"
RESUME_REPLACEMENT = "    from jbgs_p1_weight import verify_resume_source\n"
ALLOWED_BLOCK = "    allowed = NON_METHOD_ARGS | {'lambda_lod_anchor', 'lod2_building_xyz_lr_scale', 'protect_bldg_lr_scale'}"
ALLOWED_REPLACEMENT = ALLOWED_BLOCK + " | {'dynamic_depth_weight'}"


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def implementation_hashes(root):
    root = Path(root)
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*.py"))
            if "submodules" not in p.parts and "__pycache__" not in p.parts}


def payload_hashes(root):
    root = Path(root)
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
            and p.name != PROVENANCE_NAME}


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one {label} block, found {text.count(old)}")
    return text.replace(old, new, 1)


def prepare_source(parent, destination, helper=None):
    parent = Path(parent).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(destination)
    if destination.resolve().is_relative_to(parent):
        raise ValueError("Destination must be outside the immutable parent")
    if any(path.is_symlink() for path in parent.rglob("*")):
        raise ValueError("Parent snapshot must have no symlinks")
    if (parent / PROVENANCE_NAME).exists() or (parent / "jbgs_p1_weight.py").exists():
        raise ValueError("Parent already contains a P1 intervention")
    original_provenance = parent / "mvs_pgsr_source_provenance.json"
    mvs_receipt = json.loads(original_provenance.read_text())
    if mvs_receipt.get("schema") != "JBGS_GEOGS_MVS_PGSR_SOURCE_v1" or mvs_receipt.get("scientific_verdict") is not None:
        raise ValueError("Parent is not the frozen MVS source")
    parent_implementation = implementation_hashes(parent)
    if parent_implementation != mvs_receipt["prepared_implementation_hashes"]:
        raise ValueError("Parent implementation differs from its frozen MVS receipt")
    for name, expected in EXPECTED_PARENT.items():
        if parent_implementation.get(name) != expected:
            raise ValueError("Pinned MVS parent differs: " + name)
    parent_payload = payload_hashes(parent)
    helper = (Path(__file__).resolve().parents[3] / "src/phd/p1_single_view_weight_v1/loss.py"
              if helper is None else Path(helper).resolve(strict=True))
    helper_bytes = helper.read_bytes()
    train = (parent / "train.py").read_text()
    train = replace_once(train, "import jbgs_mvs_pgsr\n", "import jbgs_mvs_pgsr\nimport jbgs_p1_weight\n", "P1 import")
    train = replace_once(train, INIT_BLOCK, INIT_REPLACEMENT, "P1 controller initialization")
    train = replace_once(train, RAW_BLOCK, RAW_REPLACEMENT, "P1 MVS objective")
    state = (parent / "jbgs_state.py").read_text()
    state = replace_once(state, RESUME_IMPORT, RESUME_REPLACEMENT, "P1 source lineage validation")
    state = replace_once(state, ALLOWED_BLOCK, ALLOWED_REPLACEMENT, "declared fixed-controller change")
    receipt_line = "    receipt['restore_equivalence'] = restore_equivalence\n"
    state = replace_once(state, receipt_line, receipt_line +
                         "    receipt['declared_dynamic_depth_weight_change'] = [state['args']['dynamic_depth_weight'], args.dynamic_depth_weight]\n",
                         "controller change receipt")
    for name, value in {"train.py": train, "jbgs_state.py": state, "jbgs_p1_weight.py": helper_bytes}.items():
        compile(value, str(destination / name), "exec")
    shutil.copytree(parent, destination, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (destination / "train.py").write_text(train)
    (destination / "jbgs_state.py").write_text(state)
    (destination / "jbgs_p1_weight.py").write_bytes(helper_bytes)
    if payload_hashes(parent) != parent_payload:
        raise RuntimeError("Immutable parent source changed during preparation")
    prepared_payload = payload_hashes(destination)
    changed = sorted(name for name in parent_payload if prepared_payload.get(name) != parent_payload[name])
    added = sorted(set(prepared_payload) - set(parent_payload))
    if changed != ["jbgs_state.py", "train.py"] or added != ["jbgs_p1_weight.py"]:
        raise RuntimeError("Prepared source exceeded the declared patch scope")
    receipt = {
        "schema": SCHEMA, "scientific_verdict": None,
        "parent_path": str(parent), "prepared_path": str(destination),
        "parent_source_provenance_sha256": sha(original_provenance),
        "ancestor_anchor_implementation_hashes": mvs_receipt["parent_implementation_hashes"],
        "parent_implementation_hashes": parent_implementation,
        "prepared_implementation_hashes": implementation_hashes(destination),
        "parent_payload_hashes": parent_payload, "prepared_payload_hashes": prepared_payload,
        "changed_parent_files": changed, "added_files": added,
        "helper_sha256": {"jbgs_p1_weight.py": sha(destination / "jbgs_p1_weight.py")},
        "helper_source_path": str(helper), "preparer_sha256": sha(__file__),
        "policy": "annotated_support_v2",
        "patch_scope": ["target camera frozen R1/R2/R3 support; R1 alpha and zero outside use_mask", "original per-view valid-count denominator",
                        "all camera draws and every target forward logged", "exact complete Anchor8k lineage retained",
                        "only dynamic_depth_weight becomes False; fixed visual .05 and prior .005"],
        "preserved_controls": ["98 RGB and MVS cameras", "other 97 cameras retain all native valid pixels", "native camera and RNG schedule",
                               "optimizer", "native protection", "renderer", "densification", "MVS source provenance"],
    }
    with (destination / PROVENANCE_NAME).open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--helper", type=Path)
    args = parser.parse_args()
    receipt = prepare_source(args.parent, args.destination, args.helper)
    print(json.dumps({"schema": SCHEMA, "prepared_path": receipt["prepared_path"],
                      "train_sha256": receipt["prepared_implementation_hashes"]["train.py"], "scientific_verdict": None}))


if __name__ == "__main__":
    main()
