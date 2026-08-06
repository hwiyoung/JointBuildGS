from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


CONFIG_ROOT = Path("/workspace/JointBuildGS/configs/p2/e1_e6_techdev_v1")
TASK_RELATIVE_ROOT = Path(
    "phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1"
)
CONDITIONS = {
    "E3": "e3.json",
    "E4": "e4.json",
    "E5": "e5.json",
    "E6": "e6.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def materialize_config(
    condition: str,
    *,
    repository_root: Path,
    artifact_root: Path,
    max_iter: int | None = None,
    als_depth_weight: float | None = None,
) -> dict[str, Any]:
    key = condition.upper()
    if key not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    config_root = repository_root / "configs/p2/e1_e6_techdev_v1"
    common = yaml.safe_load((config_root / "common_gs.yaml").read_text(encoding="utf-8"))
    overlay = _read_json(config_root / CONDITIONS[key])
    merged = {**common, **overlay}
    task_root = artifact_root / TASK_RELATIVE_ROOT
    prep_root = task_root / "prep"
    runs_root = task_root / "runs"
    merged["view_roles_manifest"] = str(prep_root / "view_roles.json")
    merged["view_roles_manifest_sha256"] = sha256(prep_root / "view_roles.json")
    merged["init_pointcloud"] = str(task_root / merged["init_pointcloud"])
    merged["out_dir"] = str(task_root / merged["out_dir"])
    merged["init_pointcloud_mode"] = "concat"
    merged["seed_protect"] = True
    merged["seed_protect_until_iter"] = 5000
    merged["mvs_seed_init_opacity"] = 0.10
    merged["depth_huber_delta_m"] = float(
        _read_json(prep_root / "w_b.json")["sigma0_m"]
    )
    if max_iter is not None:
        merged["max_iter"] = int(max_iter)
    if key in {"E4", "E5"}:
        selection = prep_root / "lambda_selection.json"
        selected = (
            float(_read_json(selection)["selected_lambda_L"])
            if selection.is_file()
            else 0.5
        )
        merged.update(
            {
                "external_als_prior_dir": str(prep_root / "als_prior/views"),
                "w_external_als_depth": float(
                    selected if als_depth_weight is None else als_depth_weight
                ),
                "w_external_als_normal": 0.1,
                "external_als_huber_delta_m": float(
                    _read_json(prep_root / "w_b.json")["sigma0_m"]
                ),
                "external_als_warmup": 2000,
                "external_als_schedule": "ramp",
                "external_als_ramp_steps": 2000,
            }
        )
    if key == "E6":
        merged["external_lod_prior_dir"] = str(prep_root / "lod_prior/views")
    merged["scientific_verdict"] = None
    merged["official_PASS_usable"] = None
    runs_root.mkdir(parents=True, exist_ok=True)
    return merged


def e4_e5_scientific_diff(e4: dict[str, Any], e5: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    plumbing = {"condition_id", "out_dir", "external_als_apply_building_weight"}
    keys = set(e4) | set(e5)
    return {key: (e4.get(key), e5.get(key)) for key in sorted(keys - plumbing) if e4.get(key) != e5.get(key)}


def write_runtime_config(config: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=True), encoding="utf-8")
