#!/usr/bin/env python3
"""Build an additive E2-baseline Roofer O/X adjudication viewer."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from typing import Any

from scripts.p2.c1_c2_shared_footprint_199_v1.run import (
    canonical_json_bytes,
    exact_file,
    file_record,
    write_new,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/adjudication_e2_baseline_v1.json"


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.e1_e6_roofer_adjudication.e2_baseline.v1":
        raise RuntimeError("adjudication config schema drifted")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("adjudication viewer build is not approved")
    if config.get("product_baseline") != "E2_MVS":
        raise RuntimeError("E2 must remain the product baseline")
    if config.get("mechanism_ablation") != "E3_GS_image":
        raise RuntimeError("E3 must remain the mechanism ablation")
    if config.get("primary_product_contrast") != "E5-vs-E2":
        raise RuntimeError("primary product contrast drifted")
    if config.get("official_PASS_usable", "missing") is not None:
        raise RuntimeError("official_PASS_usable must remain null")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    return config


def patch_index(source: str) -> str:
    text = source.replace(
        "<title>JointBuildGS E1-E6 Roofer O/X Review</title>",
        "<title>JointBuildGS E2-baseline Roofer O/X Adjudication</title>",
    )
    marker = "</style>\n</head>"
    if marker not in text:
        raise RuntimeError("parent index style marker drifted")
    text = text.replace(
        marker,
        '</style>\n<link rel="stylesheet" href="./adjudication.css?v=e2-baseline-v1">\n</head>',
        1,
    )
    body_marker = "</body>"
    if body_marker not in text:
        raise RuntimeError("parent index body marker drifted")
    text = text.replace(
        body_marker,
        '<script type="module" src="./adjudication.js?v=e2-baseline-v1"></script>\n</body>',
        1,
    )
    return text


def patch_app(source: str, config: dict[str, Any]) -> str:
    if not config.get("reviewer_profiles"):
        return source
    old = "const STORAGE_KEY = 'jointbuildgs-e1-e6-roofer-ox-v4';"
    new = "const REVIEWER_ID = new URLSearchParams(window.location.search).get('reviewer') || 'R1';\nconst STORAGE_KEY = `jointbuildgs-e1-e6-roofer-ox-v4-${REVIEWER_ID}`;"
    if old not in source:
        raise RuntimeError("parent app storage marker drifted")
    text = source.replace(old, new, 1)
    text = text.replace("mvsMesh: 0xe62dd2,", "mvsMesh: 0x8b5cf6,")
    text = text.replace("mvsPointRgb: [1, 145 / 255, 35 / 255],", "mvsPointRgb: [139 / 255, 92 / 255, 246 / 255],")
    return text


def build(config_path: Path, repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    parent_spec = config["parent_viewer"]
    parent = artifact_root / parent_spec["relative_root"]
    for prefix, field in (("viewer_manifest", "viewer_manifest_path"), ("receipt", "receipt_path"), ("index", "index_path"), ("app", "app_path")):
        exact_file(parent / parent_spec[field], {
            "bytes": parent_spec[f"{prefix}_bytes"],
            "sha256": parent_spec[f"{prefix}_sha256"],
        })
    for spec in config["application_sources"].values():
        exact_file(repo_root / spec["path"], spec)

    output = artifact_root / config["output_relative_root"]
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise RuntimeError("fresh add-once adjudication namespace required")
    partial.mkdir(parents=True)
    replaced = {"viewer_manifest.json", "web_receipt_v1.json", "index.html", "README.md"}
    for source in parent.iterdir():
        if source.name in replaced:
            continue
        target = partial / source.name
        if source.name == "app.js":
            write_new(target, patch_app(source.read_text(encoding="utf-8"), config).encode("utf-8"))
            continue
        relative = os.path.relpath(source, start=partial)
        os.symlink(relative, target, target_is_directory=source.is_dir())

    viewer = json.loads((parent / parent_spec["viewer_manifest_path"]).read_text(encoding="utf-8"))
    if len(viewer.get("buildings", [])) != 199:
        raise RuntimeError("parent viewer population drifted")
    viewer.update({
        "task_id": config["task_id"],
        "status": "READY_FOR_E2_BASELINE_HUMAN_ROOFER_OX_ADJUDICATION",
        "adjudication_contract": {
            "product_baseline": config["product_baseline"],
            "mechanism_ablation": config["mechanism_ablation"],
            "product_arms": config["product_arms"],
            "primary_product_contrast": config["primary_product_contrast"],
            "human_review_storage_key": config["local_storage_key"],
            "reviewer_profiles": config.get("reviewer_profiles", ["R1"]),
            "blind_permutation_seed": config.get("blind_permutation_seed"),
            "calibration_sample_status": config.get("calibration_sample_status"),
            "default_mode": config.get("default_mode", "TRANSITION"),
            "automatic_candidates": "DEVELOPMENT_ONLY_NOT_OFFICIAL",
        },
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    write_new(partial / "viewer_manifest.json", canonical_json_bytes(viewer))

    patched_index = patch_index((parent / parent_spec["index_path"]).read_text(encoding="utf-8"))
    write_new(partial / "index.html", patched_index.encode("utf-8"))
    for target, key in (("adjudication.css", "css"), ("adjudication.js", "js")):
        shutil.copyfile(repo_root / config["application_sources"][key]["path"], partial / target)
    write_new(
        partial / "README.md",
        (
            "# E2-baseline Roofer adjudication v17\n\n"
            "E2 is the existing current-image MVS to Roofer product baseline. "
            "E3 is the no-prior GS mechanism ablation; E4/E5 are prior-guided product arms. "
            "The viewer reuses v16 assets exactly, preserves the existing local O/X review key, "
            "and adds only an adjudication UI. Automatic G3/G4 candidates remain nonofficial. "
            "No training, extraction, Roofer, or metric recomputation was run. "
            "official_PASS_usable and scientific_verdict remain null.\n"
        ).encode("utf-8"),
    )

    parent_receipt = json.loads((parent / parent_spec["receipt_path"]).read_text(encoding="utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6_roofer_adjudication.receipt.v1",
        "task_id": config["task_id"],
        "status": "READY_FOR_E2_BASELINE_HUMAN_ROOFER_OX_ADJUDICATION",
        "parent_task_id": parent_receipt.get("task_id"),
        "parent_viewer_manifest": file_record(parent / parent_spec["viewer_manifest_path"], artifact_root),
        "parent_receipt": file_record(parent / parent_spec["receipt_path"], artifact_root),
        "reuse_method": "PARENT_BOUND_RELATIVE_SYMLINK_V16_ASSETS_UI_ONLY",
        "application_sources": {
            key: file_record(repo_root / spec["path"], repo_root)
            for key, spec in config["application_sources"].items()
        },
        "application": {
            name: file_record(partial / name, partial)
            for name in ("index.html", "app.js", "adjudication.css", "adjudication.js")
        },
        "viewer_manifest": file_record(partial / "viewer_manifest.json", partial),
        "execution_counts": {"training": 0, "extraction": 0, "roofer": 0, "metric_recompute": 0},
        "product_baseline": config["product_baseline"],
        "mechanism_ablation": config["mechanism_ablation"],
        "primary_product_contrast": config["primary_product_contrast"],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(partial / "web_receipt_v1.json", canonical_json_bytes(receipt))
    os.rename(partial, output)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, default=REPO.parent / "JointBuildGS-artifacts")
    args = parser.parse_args()
    print(json.dumps(build(args.config.resolve(), args.repo_root.resolve(), args.artifact_root.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
