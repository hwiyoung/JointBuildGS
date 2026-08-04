from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_tsdf_roof_diagnostic_v1/run_v1.json"
PROJECT_IMAGE_ID = "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if config.get("schema") != "jointbuildgs.p2.c3_tsdf_roof_diagnostic.v1":
        raise RuntimeError("unexpected C3 TSDF diagnostic schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXPERIMENT_HOST_EXECUTION":
        raise RuntimeError("C3 TSDF diagnostic is not activated")
    authority = config.get("execution_authority") or {}
    if authority.get("mode") != "DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST":
        raise RuntimeError("unexpected execution authority")
    if authority.get("write_ownership_transfer_performed") is not False:
        raise RuntimeError("this local task must not claim a write-ownership transfer")
    if authority.get("two_host_receipt_required") is not False:
        raise RuntimeError("this local task must not manufacture two-host receipts")
    scope = config.get("scope") or {}
    expected_buildings = {
        "DEBY_LOD2_4907177", "DEBY_LOD2_4906975", "DEBY_LOD2_108580336"
    }
    if set(scope.get("building_ids") or ()) != expected_buildings:
        raise RuntimeError("building membership drifted")
    if list(scope.get("condition_ids") or ()) != ["C3_1_SEM", "C3_2_SEM_DEPTH"]:
        raise RuntimeError("condition order drifted")
    if scope.get("c4_c5_access_allowed") is not False:
        raise RuntimeError("C4/C5 access must remain disabled")
    counters = config.get("execution_counters") or {}
    expected_zero = (
        "expected_gs_training_invocations", "expected_roofer_invocations",
        "expected_g2_invocations", "expected_metric_recomputations",
        "expected_c4_c5_accesses",
    )
    if any(int(counters.get(key, -1)) != 0 for key in expected_zero):
        raise RuntimeError("prohibited execution counter is nonzero")
    if int(counters.get("expected_checkpoint_render_extractions", -1)) != 2:
        raise RuntimeError("expected exactly two checkpoint render extractions")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None:
        raise RuntimeError("official G3/G4/PASS must remain null")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific verdict must remain null")
    surface = config.get("surface") or {}
    if float(surface.get("tsdf_truncation_m", 0)) < 2 * float(surface.get("tsdf_voxel_m", 1)):
        raise RuntimeError("TSDF truncation must span at least two voxels")
    return {
        "status": "PASS",
        "building_count": 3,
        "condition_count": 2,
        "scientific_verdict": None,
    }


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def require_regular(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} missing/non-regular: {path}")
    return path


def resolve_artifact(artifact_root: Path, relative: str, label: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise RuntimeError(f"unsafe {label} path: {relative}")
    root = artifact_root.resolve()
    path = (root / value).resolve()
    if root not in path.parents:
        raise RuntimeError(f"{label} escaped artifact root")
    return path
