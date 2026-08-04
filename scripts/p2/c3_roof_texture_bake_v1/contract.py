from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_roof_texture_bake_v1/bake_v1.json"
PROJECT_IMAGE_ID = "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if config.get("schema") != "jointbuildgs.p2.c3_roof_texture_bake.v1":
        raise RuntimeError("unexpected roof texture bake schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXPERIMENT_HOST_EXECUTION":
        raise RuntimeError("roof texture bake is not activated")
    scope = config.get("scope") or {}
    if scope.get("roof_only") is not True or scope.get("c4_c5_access_allowed") is not False:
        raise RuntimeError("roof-only/C4-C5 boundary drifted")
    if list(scope.get("condition_ids") or ()) != ["C3_1_SEM", "C3_2_SEM_DEPTH"]:
        raise RuntimeError("condition order drifted")
    if list(scope.get("mesh_methods") or ()) != ["POISSON", "TSDF"]:
        raise RuntimeError("mesh method order drifted")
    if set(scope.get("building_ids") or ()) != {"DEBY_LOD2_4907177", "DEBY_LOD2_4906975", "DEBY_LOD2_108580336"}:
        raise RuntimeError("building scope drifted")
    texture = config.get("texture") or {}
    if int(texture.get("atlas_resolution_px", 0)) < 256:
        raise RuntimeError("texture atlas resolution is too small")
    if texture.get("uv_policy") != "GT_FOOTPRINT_XY_PLANAR_DISPLAY_ATLAS":
        raise RuntimeError("unexpected UV policy")
    hybrid = config.get("hybrid") or {}
    if hybrid.get("role") != "GT_FOOTPRINT_DISPLAY_WALL_NOT_HONEST_STAGE3":
        raise RuntimeError("unexpected display-wall role")
    if hybrid.get("wall_texture_created") is not False or hybrid.get("ground_cap_created") is not False:
        raise RuntimeError("display wall must remain untextured and ground-cap free")
    if hybrid.get("honest_stage3_output") is not False or hybrid.get("official_metric_input") is not False:
        raise RuntimeError("display wall provenance boundary drifted")
    counters = config.get("execution_counters") or {}
    zero = (
        "expected_gs_training_invocations", "expected_checkpoint_render_extractions",
        "expected_poisson_reconstructions", "expected_tsdf_reconstructions",
        "expected_roofer_invocations", "expected_g2_invocations",
        "expected_metric_recomputations", "expected_c4_c5_accesses",
    )
    if any(int(counters.get(key, -1)) != 0 for key in zero):
        raise RuntimeError("prohibited execution counter is nonzero")
    if int(counters.get("expected_roof_texture_bakes", -1)) != 12:
        raise RuntimeError("expected exactly 12 roof texture bakes")
    if int(counters.get("expected_display_only_gt_footprint_wall_assemblies", -1)) != 12:
        raise RuntimeError("expected exactly 12 display-only wall assemblies")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific/official verdict fields must remain null")
    return {"status": "PASS", "texture_bake_count": 12, "scientific_verdict": None}
