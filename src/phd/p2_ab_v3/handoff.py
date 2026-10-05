"""Consume region-specific A geometry without replacing it with a global source.

This validates provenance and permissions, not the scientific validity of A.
Explicit fixtures may exercise wiring, but cannot claim calibrated decisions.
"""
from dataclasses import dataclass
import hashlib
import json

import numpy as np


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    action: str
    xyz: np.ndarray
    normals: np.ndarray
    native_rows: np.ndarray
    parent_hashes: tuple[str, ...]
    registration_version: str

    def fingerprint(self):
        digest = hashlib.sha256()
        digest.update(json.dumps({"id": self.candidate_id, "action": self.action,
            "parents": self.parent_hashes, "registration": self.registration_version},
            sort_keys=True).encode())
        for value in (self.xyz, self.normals, self.native_rows):
            value = np.ascontiguousarray(value)
            digest.update(str(value.dtype).encode())
            digest.update(str(value.shape).encode())
            digest.update(value.tobytes())
        return digest.hexdigest()

    def validate(self):
        if self.action not in {"IMAGE", "PRIOR", "FUSION"}:
            raise ValueError("unsupported candidate action")
        if self.xyz.ndim != 2 or self.xyz.shape[1] != 3 or not len(self.xyz):
            raise ValueError("candidate must contain XYZ points")
        if self.normals.shape != self.xyz.shape or len(self.native_rows) != len(self.xyz):
            raise ValueError("geometry and native membership disagree")
        if not np.isfinite(self.xyz).all() or not np.isfinite(self.normals).all():
            raise ValueError("nonfinite geometry")
        if not self.parent_hashes or not self.registration_version:
            raise ValueError("source lineage and registration version are required")
        if self.action == "FUSION" and len(set(self.parent_hashes)) < 2:
            raise ValueError("fusion must retain two distinct parent candidates")


def assemble_selected_geometry(candidates, decisions, *, fixture=False):
    """Return explicit seeds and permissions; ABSTAIN contributes no geometry.

    Candidates already contain the exact region-specific corrected/fused geometry.
    The function performs no registration, fusion, interpolation or downsampling.
    Component bounds remain records: a scalar normal error is never interpreted
    as a three-dimensional displacement permission.
    """
    parts = {key: [] for key in ("xyz", "normals", "native_rows", "region_index",
                                "appearance_allowed", "detail_allowed")}
    regions, seen = [], set()
    for index, decision in enumerate(decisions):
        region_id = decision["region_id"]
        if region_id in seen:
            raise ValueError("duplicate region decision")
        seen.add(region_id)
        action = decision["action"]
        if action == "ABSTAIN":
            if decision.get("candidate_id") is not None:
                raise ValueError("ABSTAIN cannot silently seed a candidate")
            regions.append(dict(decision, point_count=0))
            continue
        if action not in {"IMAGE", "PRIOR", "FUSION"}:
            raise ValueError("unknown action")
        candidate = candidates[decision["candidate_id"]]
        candidate.validate()
        if candidate.action != action or candidate.fingerprint() != decision["geometry_sha256"]:
            raise ValueError("selected action/geometry differs from A handoff")
        if not fixture and (decision.get("eligibility") != "ELIGIBLE"
                            or decision.get("calibration_status") != "CALIBRATED"):
            raise ValueError("uncalibrated/unknown decisions require explicit fixture mode")
        components = decision.get("components", [])
        if not components:
            raise ValueError("component-specific bounds and units are required")
        for component in components:
            upper = component["candidate_error_upper"]
            tolerance = component["required_error"]
            if not np.isfinite([upper, tolerance]).all() or not 0 <= upper <= tolerance:
                raise ValueError("invalid component error budget")
            if not component.get("component") or not component.get("unit"):
                raise ValueError("component identity and unit are required")
        n = len(candidate.xyz)
        appearance = np.asarray(decision["appearance_allowed"], dtype=bool)
        detail = np.asarray(decision["detail_allowed"], dtype=bool)
        if appearance.shape != (n,) or detail.shape != (n,):
            raise ValueError("permissions must explicitly match selected geometry")
        if detail.any() and not decision.get("detail_evidence_version"):
            raise ValueError("detail motion requires its own evidence version")
        for key in ("xyz", "normals", "native_rows"):
            parts[key].append(getattr(candidate, key).copy())
        parts["region_index"].append(np.full(n, index, dtype=np.int32))
        parts["appearance_allowed"].append(appearance.copy())
        parts["detail_allowed"].append(detail.copy())
        record = {key: value for key, value in decision.items()
                  if key not in {"appearance_allowed", "detail_allowed"}}
        regions.append(dict(record, point_count=n, parent_hashes=candidate.parent_hashes,
                            registration_version=candidate.registration_version))
    arrays = {}
    for key, values in parts.items():
        if values:
            arrays[key] = np.concatenate(values)
        else:
            dtype = bool if key.endswith("allowed") else (np.float64 if key in {"xyz", "normals"} else np.int64)
            arrays[key] = np.empty((0, 3) if key in {"xyz", "normals"} else (0,), dtype=dtype)
    return arrays, {"status": "WIRING_FIXTURE_ONLY" if fixture else "VALIDATED_HANDOFF_BYTES",
                    "scientific_verdict": None, "regions": regions,
                    "new_seed_addition_allowed": False,
                    "component_budgets_are_not_global_xyz_permissions": True}
