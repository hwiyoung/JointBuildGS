#!/usr/bin/env python3
"""Read-only reference-family parity and frozen-input gate."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

import yaml


REPO = Path("/workspace/JointBuildGS")
ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-REFERENCE-FAMILY-DIAG-v1"
TASK_ROOT = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_reference_family_diag_v1"
    / TASK_ID
)
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_reference_family_diag_v1"
SOURCE_ROOT = TASK_ROOT / "control/reference_sources"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(value)
    os.replace(tmp, path)


def artifact_path(raw: str) -> Path:
    marker = "JointBuildGS-artifacts/"
    if marker in raw:
        return ARTIFACT_ROOT / raw.split(marker, 1)[1]
    path = Path(raw)
    return path


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "safe.directory=/workspace/JointBuildGS", *args],
        cwd=REPO,
        text=True,
    ).strip()


def require_text(path: Path, fragments: list[str]) -> list[dict[str, object]]:
    value = path.read_text(errors="replace")
    rows = []
    for fragment in fragments:
        rows.append(
            {
                "path": str(path),
                "fragment": fragment,
                "found": fragment in value,
            }
        )
    return rows


def verify_inputs(source_manifest: Path) -> dict[str, object]:
    body = json.loads(source_manifest.read_text())
    checked: list[dict[str, object]] = []
    failures: list[str] = []

    def check(path: Path, expected: str, role: str) -> None:
        actual = sha256(path) if path.is_file() else None
        row = {
            "role": role,
            "path": str(path),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "passed": actual == expected,
        }
        checked.append(row)
        if not row["passed"]:
            failures.append(str(path))

    crop_root = artifact_path(body["crop_root"])
    for row in body["crop_images"]["files"]:
        check(crop_root / "images" / row["basename"], row["sha256"], "crop_image")
    for basename, row in body["camera_and_sparse_seed"].items():
        check(artifact_path(row["path"]), row["sha256"], basename)
    for key in ("exact_view_manifest", "view_roles_manifest"):
        row = body[key]
        check(artifact_path(row["path"]), row["sha256"], key)
    for basename, expected in body["geometric_depth_maps_sha256"].items():
        check(
            crop_root / "stereo/depth_maps" / f"{basename}.geometric.bin",
            expected,
            "colmap_geometric_depth",
        )
    if failures:
        raise RuntimeError(f"frozen input hash failures: {failures[:5]}")
    return {
        "schema": "jointbuildgs.reference_family_input_hashes.v1",
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": sha256(source_manifest),
        "verified_file_count": len(checked),
        "verified_by_role": {
            role: sum(row["role"] == role for row in checked)
            for role in sorted({str(row["role"]) for row in checked})
        },
        "records": checked,
        "scientific_verdict": None,
    }


def main() -> None:
    started = now()
    common = yaml.safe_load((CONFIG_DIR / "common.yaml").read_text())
    two_cfg = yaml.safe_load((CONFIG_DIR / "two_dgs_ref.yaml").read_text())
    pgsr_cfg = yaml.safe_load((CONFIG_DIR / "pgsr_ref.yaml").read_text())
    receipt_path = Path(common["source_reference_receipt"])
    receipt = json.loads(receipt_path.read_text())
    overlay_manifest_path = Path(common["surface_overlay_manifest"])
    overlay_audit_path = Path(common["surface_overlay_audit"])
    overlay_manifest = json.loads(overlay_manifest_path.read_text())
    overlay_audit = json.loads(overlay_audit_path.read_text())
    overlay_root = overlay_manifest_path.parent / "gsplat"
    overlay_live_hashes = {
        relative: sha256(overlay_root / relative)
        for relative in overlay_manifest["patched_sha256"]
    }
    if (
        overlay_live_hashes != overlay_manifest["patched_sha256"]
        or not overlay_audit.get("passed")
    ):
        raise RuntimeError("surface overlay live-hash or synthetic audit gate failed")

    source_checks: list[dict[str, object]] = []
    for name, row in receipt["sources"].items():
        source_checks.append(
            {
                "source": name,
                "requested_commit": row["requested_commit"],
                "actual_commit": row["actual_commit"],
                "passed": row["requested_commit"] == row["actual_commit"],
                "file_count": row["tree"]["file_count"],
            }
        )

    evidence = []
    evidence += require_text(
        SOURCE_ROOT / "two_dgs/train.py",
        [
            "lambda_normal = opt.lambda_normal if iteration > 7000 else 0.0",
            "normal_error = (1 - (rend_normal * surf_normal).sum(dim=0))[None]",
            "lambda_dist = opt.lambda_dist if iteration > 3000 else 0.0",
        ],
    )
    evidence += require_text(
        SOURCE_ROOT / "two_dgs/gaussian_renderer/__init__.py",
        [
            "render_depth_expected = (render_depth_expected / render_alpha)",
            "surf_normal = surf_normal * (render_alpha).detach()",
        ],
    )
    evidence += require_text(
        SOURCE_ROOT / "diff_surfel_rasterization/cuda_rasterizer/forward.cu",
        [
            "float depth = (s.x * Tw.x + s.y * Tw.y) + Tw.z;",
            "D  += depth * w;",
        ],
    )
    evidence += require_text(
        SOURCE_ROOT / "pgsr/train.py",
        [
            "min_scale_loss = sorted_scale[...,0]",
            "ncc, ncc_mask = lncc(ref_gray_val, sampled_gray_val)",
            "prune_mask = (observe_cnt < observe_the).squeeze()",
        ],
    )
    evidence += require_text(
        SOURCE_ROOT / "pgsr/submodules/diff-plane-rasterization/cuda_rasterizer/forward.cu",
        [
            "out_plane_depth[pix_id] = All_map[4] / -(All_map[0] * ray.x",
        ],
    )
    evidence += require_text(
        REPO / "src/stage2/train.py",
        [
            "normal_consistency_mode == \"official_2dgs\"",
            "lr_means_schedule == \"official_2dgs_exponential\"",
        ],
    )
    evidence += require_text(
        REPO / "src/stage2/renderer.py",
        ["surface_normal_depth_mode == \"surface_intersection_expected\""],
    )
    evidence += require_text(
        REPO / "src/stage2/loss/data_fitting.py",
        ["def l_nc_official_2dgs("],
    )
    if not all(row["found"] for row in evidence):
        missing = [row for row in evidence if not row["found"]]
        raise RuntimeError(f"reference parity source check failed: {missing}")

    input_hashes = verify_inputs(Path(common["source_input_hashes"]))
    atomic_json(TASK_ROOT / "input_hashes.json", input_hashes)

    two_overrides = two_cfg["overrides"]
    forbidden_two = {
        key: two_overrides.get(key)
        for key in (
            "w_depth", "w_normal", "w_mono_depth", "w_mvc", "w_distort",
            "w_external_als_depth", "w_external_als_normal", "w_lod_prior",
            "w_sem", "w_mutual", "w_structure",
        )
        if float(two_overrides.get(key, 0.0) or 0.0) != 0.0
    }
    two_pass = (
        not forbidden_two
        and two_overrides["w_nc"] == 0.05
        and two_overrides["normal_consistency_mode"] == "official_2dgs"
        and two_overrides["surface_normal_depth_mode"] == "surface_intersection_expected"
        and two_overrides["lr_means_schedule"] == "official_2dgs_exponential"
    )

    rows = [
        {
            "arm": "GSPLAT_2DGS_REF",
            "primitive": "intrinsically planar 2D Gaussian",
            "rasterizer": "gsplat 1.4 rasterization_2dgs plus audited exact-hit overlay",
            "single_view_surface": "official ray-surfel expected depth plus official normal reduction",
            "multi_view": "none",
            "external_depth": "none",
            "densification": "gsplat DefaultStrategy mapped to official thresholds",
            "parity_status": "PASS_GSPLAT_ADAPTATION" if two_pass else "FAIL",
            "training_allowed": two_pass,
        },
        {
            "arm": "PGSR_REF",
            "primitive": "reference 3D Gaussian minimum-scale plane is unavailable",
            "rasterizer": "reference diff-plane outputs unavailable in gsplat 2DGS",
            "single_view_surface": "reference image-weighted depth-normal L1 unavailable",
            "multi_view": "reference reprojection plus LNCC plus trim unavailable",
            "external_depth": "none in reference",
            "densification": "reference absgrad/observation trim unavailable",
            "parity_status": "BLOCKED_NOT_REFERENCE_FAITHFUL",
            "training_allowed": False,
        },
    ]
    csv_path = TASK_ROOT / "parity_matrix.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.with_suffix(".csv.tmp").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(csv_path.with_suffix(".csv.tmp"), csv_path)

    audit = {
        "schema": "jointbuildgs.reference_family_parity_audit.v1",
        "task_id": TASK_ID,
        "source_snapshot_checks": source_checks,
        "source_semantic_checks": evidence,
        "surface_overlay": {
            "manifest_path": str(overlay_manifest_path),
            "manifest_sha256": sha256(overlay_manifest_path),
            "audit_path": str(overlay_audit_path),
            "audit_sha256": sha256(overlay_audit_path),
            "live_patched_sha256": overlay_live_hashes,
            "synthetic_gate_passed": True,
        },
        "arms": rows,
        "two_dgs_adaptation_limits": two_cfg["adaptation_limits"],
        "pgsr_blockers": pgsr_cfg["blocking_differences"],
        "gate": {
            "two_dgs_training_allowed": two_pass,
            "pgsr_training_allowed": False,
            "training_arms_allowed": int(two_pass),
        },
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "reference_parity_audit.json", audit)
    contract = {
        "schema": "jointbuildgs.reference_family_experiment_contract.v1",
        "task_id": TASK_ID,
        "question": "Does one coherent reference-family gsplat recipe transfer MVS-quality geometry better than the current external-depth hybrid?",
        "comparison": ["MVS_DIRECT_REUSE", "CURRENT_DEPTH_REUSE", "GSPLAT_2DGS_REF"],
        "blocked_arm": "PGSR_REF",
        "blocked_arm_reason": "No reference-faithful gsplat-native implementation exists in the current repository.",
        "two_dgs_intervention": "RGB plus official 2DGS intrinsic normal consistency; no COLMAP depth, MVC, ALS, LoD, or semantic prior.",
        "evaluation_only": ["LoD2 Z", "RoofSurface", "roof type", "reference normals"],
        "shared_control": "exact LoD2 GroundSurface XY footprint and stable building ID",
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    issues = """# Issues\n\n- Reference fetch attempt 1 failed because the no-checkout worktree appeared deleted; attempt 2 forced a detached checkout and passed with pinned commits.\n- `PGSR_REF` is stopped before training: its 3D Gaussian plane rasterizer, plane-depth/distance outputs, patch LNCC reprojection, abs-gradient densification, and observation trim are not present in the current gsplat 2DGS stack.\n- `GSPLAT_2DGS_REF` is explicitly an adaptation, not a byte-identical official-fork reproduction; gsplat DefaultStrategy replaces the official densifier and the common budget stops at 20k rather than 30k.\n- Smoke attempt 1 stopped before the first optimizer update because the pinned PyTorch build rejects replicate padding on an unbatched HxWxC tensor. The equivalent explicit last-row/last-column replication is unit-tested; retry uses `smoke/attempt_2`.\n- scientific_verdict remains null.\n"""
    atomic_text(TASK_ROOT / "issues.md", issues)
    notes = """# NOTES\n\nThis task does not add external depth, MVC, semantic, ALS, or LoD supervision. It first binds exact official source snapshots, then permits only the reference-faithful portion that can be expressed with repository-required gsplat. PGSR is not approximated by stacking existing losses.\n\n`GSPLAT_2DGS_REF` uses the official large-scene/default expected ray-surfel depth for pseudo-normal construction, the official unnormalized normal-consistency reduction after update 7000, the official camera-radius-scaled exponential position learning rate, and reference densification thresholds mapped onto gsplat DefaultStrategy. Distortion stays zero as in the pinned default/large-scene recipe.\n\nscientific_verdict: null\n"""
    atomic_text(TASK_ROOT / "NOTES.md", notes)

    config_files = sorted(CONFIG_DIR.glob("*.yaml"))
    source_files = [
        REPO / "src/stage2/renderer.py",
        REPO / "src/stage2/train.py",
        REPO / "src/stage2/loss/data_fitting.py",
        REPO / "scripts/p2/e3_local_4906982_reference_family_diag_v1/audit_reference_parity.py",
        REPO / "scripts/p2/e3_local_4906982_reference_family_diag_v1/fetch_reference_sources.py",
    ]
    provenance = {
        "schema": "jointbuildgs.reference_family_provenance.v1",
        "task_id": TASK_ID,
        "git_commit": git("rev-parse", "HEAD"),
        "git_branch": git("branch", "--show-current"),
        "git_dirty": bool(git("status", "--porcelain")),
        "git_status_porcelain": git("status", "--porcelain").splitlines(),
        "docker_image": common["docker_image"],
        "docker_image_id": os.environ.get("JBGS_DOCKER_IMAGE_ID"),
        "gpu_model": os.environ.get("JBGS_GPU_MODEL"),
        "source_sha256": {str(p.relative_to(REPO)): sha256(p) for p in source_files},
        "config_sha256": {str(p.relative_to(REPO)): sha256(p) for p in config_files},
        "reference_receipt_sha256": sha256(receipt_path),
        "surface_overlay_manifest_sha256": sha256(overlay_manifest_path),
        "surface_overlay_audit_sha256": sha256(overlay_audit_path),
        "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"),
        "random_seed": common["random_seed"],
        "start_time": started,
        "end_time": now(),
        "command_line": " ".join(os.sys.argv),
        "return_code": 0,
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "provenance.json", provenance)
    print(json.dumps(audit["gate"], sort_keys=True))


if __name__ == "__main__":
    main()
