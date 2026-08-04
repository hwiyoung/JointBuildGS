from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_mesh_attribute_hybrid_v1/render_v1.json"
PROJECT_IMAGE_ID = "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if config.get("schema") != "jointbuildgs.p2.c3_mesh_attribute_hybrid.v1":
        raise RuntimeError("unexpected mesh attribute hybrid schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXPERIMENT_HOST_EXECUTION":
        raise RuntimeError("mesh attribute hybrid task is not activated")
    authority = config.get("execution_authority") or {}
    if authority.get("mode") != "DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST":
        raise RuntimeError("unexpected execution authority")
    if authority.get("write_ownership_transfer_performed") is not False:
        raise RuntimeError("must not claim two-host ownership transfer")
    scope = config.get("scope") or {}
    if list(scope.get("condition_ids") or ()) != ["C3_1_SEM", "C3_2_SEM_DEPTH"]:
        raise RuntimeError("condition order drifted")
    if set(scope.get("building_ids") or ()) != {
        "DEBY_LOD2_4907177", "DEBY_LOD2_4906975", "DEBY_LOD2_108580336"
    }:
        raise RuntimeError("building scope drifted")
    if list(scope.get("mesh_methods") or ()) != ["POISSON", "TSDF"]:
        raise RuntimeError("mesh method order drifted")
    if list(scope.get("display_modes") or ()) != ["RGB", "SEMANTIC", "VIRTUAL_DEPTH", "ABS_NORMAL"]:
        raise RuntimeError("display mode order drifted")
    if scope.get("c4_c5_access_allowed") is not False:
        raise RuntimeError("C4/C5 access must remain disabled")
    hybrid = config.get("hybrid") or {}
    if hybrid.get("role") != "GT_FOOTPRINT_ORACLE_HYBRID_VISUALIZATION_NOT_HONEST_STAGE3":
        raise RuntimeError("hybrid oracle boundary drifted")
    if float(hybrid.get("boundary_sample_spacing_m", 0)) <= 0:
        raise RuntimeError("invalid boundary sample spacing")
    counters = config.get("execution_counters") or {}
    zero_keys = (
        "expected_gs_training_invocations", "expected_checkpoint_render_extractions",
        "expected_poisson_reconstructions", "expected_tsdf_reconstructions",
        "expected_roofer_invocations", "expected_g2_invocations",
        "expected_metric_recomputations", "expected_c4_c5_accesses",
    )
    if any(int(counters.get(key, -1)) != 0 for key in zero_keys):
        raise RuntimeError("a prohibited execution counter is nonzero")
    if int(counters.get("expected_hybrid_wall_assemblies", -1)) != 12:
        raise RuntimeError("expected exactly 12 display-only hybrid assemblies")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None:
        raise RuntimeError("official G3/G4/PASS must remain null")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific verdict must remain null")
    return {"status": "PASS", "case_count": 3, "hybrid_count": 12, "scientific_verdict": None}
