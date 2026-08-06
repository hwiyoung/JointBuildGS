#!/usr/bin/env python3
"""Prefer pose diversity, then deterministically fill from validated cameras."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

from scripts.p2.qualitative_row1_current_raw_v3.preview import (
    canonical_json_bytes,
    stable_seed,
    verify_file,
)
from scripts.p2.qualitative_row1_current_raw_v4.preview10 import public_candidate, separated
from scripts.p2.qualitative_row1_current_raw_v6 import preview10 as delegate


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v2.json"


def choose_views(
    building_id: str,
    candidates: Sequence[dict[str, Any]],
    selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str, int, str]:
    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    roles = [str(value) for value in selection["roles"]]
    seed = stable_seed(str(selection["random_seed_namespace"]), building_id)
    pool = [public_candidate(row) for row in sorted(eligible, key=lambda row: row["camera_name"])]
    pool_hash = hashlib.sha256(canonical_json_bytes(pool)).hexdigest()
    if not eligible:
        return [
            {"role": role, "status": "REPRESENTATIVE_ROOF_CAMERA_MISSING", "camera": None}
            for role in roles
        ], "REPRESENTATIVE_ROOF_CAMERA_MISSING", seed, pool_hash

    top = min(
        eligible,
        key=lambda row: (
            row["nadir_deg"],
            -row["representative_projected_bbox_area_px2"],
            -row["valid_actual_observation_count"],
            row["camera_name"],
        ),
    )
    top_status = (
        "NEAR_NADIR"
        if top["nadir_deg"] <= float(selection["near_nadir_max_deg"])
        else "BEST_AVAILABLE_NO_NEAR_NADIR"
    )
    remaining = [row for row in eligible if row is not top]
    random.Random(seed).shuffle(remaining)

    wanted = len(roles) - 1
    diverse: list[dict[str, Any]] = []
    chosen = [top]
    for candidate in remaining:
        if separated(
            candidate,
            chosen,
            float(selection["minimum_view_direction_separation_deg"]),
            float(selection["minimum_camera_center_separation_m"]),
        ):
            diverse.append(candidate)
            chosen.append(candidate)
            if len(diverse) == wanted:
                break

    diverse_ids = {id(row) for row in diverse}
    fallback = [row for row in remaining if id(row) not in diverse_ids][
        : max(0, wanted - len(diverse))
    ]
    selected_random = [
        (row, "DETERMINISTIC_POSE_DIVERSE_RANDOM_REPRESENTATIVE_COMPONENT")
        for row in diverse
    ] + [
        (row, "DETERMINISTIC_VALIDATED_RANDOM_FALLBACK") for row in fallback
    ]

    views = [
        {"role": roles[0], "status": "SELECTED", "source": top_status, "camera": public_candidate(top)}
    ]
    for role, (candidate, source) in zip(roles[1:], selected_random):
        views.append(
            {"role": role, "status": "SELECTED", "source": source, "camera": public_candidate(candidate)}
        )
    for role in roles[len(views) :]:
        views.append({"role": role, "status": "REPRESENTATIVE_ROOF_CAMERA_MISSING", "camera": None})
    return views, top_status, seed, pool_hash


def run(
    config_path: Path,
    repo_root: Path,
    artifact_root: Path,
    output_root: Path,
    source_commit: str,
    image_id: str,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    fallback = config.get("selection_fallback", {})
    if not (
        fallback.get("pose_diversity_has_priority")
        and fallback.get("fallback_uses_only_fully_validated_candidates")
        and fallback.get("fallback_is_deterministic")
        and fallback.get("fallback_may_not_replace_a_missing_candidate_pool")
    ):
        raise RuntimeError("v6-v2 validated-camera fallback contract is not frozen")
    dependency = config["v6_delegate_dependency"]
    verify_file(
        repo_root / dependency["git_path"],
        dependency["sha256"],
        "v6 delegate dependency",
        int(dependency["bytes"]),
    )

    original_choose_views = delegate.choose_views
    original_file = delegate.__file__
    delegate.choose_views = choose_views
    delegate.__file__ = str(Path(__file__).resolve())
    try:
        return delegate.run(
            config_path,
            repo_root,
            artifact_root,
            output_root,
            source_commit,
            image_id,
        )
    finally:
        delegate.choose_views = original_choose_views
        delegate.__file__ = original_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.config,
                args.repo_root,
                args.artifact_root,
                args.output_root,
                args.source_commit,
                args.image_id,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
