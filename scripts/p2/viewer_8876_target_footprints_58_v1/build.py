#!/usr/bin/env python3
"""Show only the 58 sparse-present/MVS-raw-support target footprints in viewer 8876."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/viewer_8876_target_footprints_58_v1/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_target_footprints_58_v1/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_target_footprints_58_v1/P2-VIEWER-8876-TARGET-FOOTPRINTS-58-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing input: {path}")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"sha256 drift: {path}: {actual} != {expected}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}


def atomic_text(path: Path, body: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body)
    os.replace(temporary, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    if TASK.exists():
        raise RuntimeError(f"add-once task exists: {TASK}")
    viewer = AR / cfg["viewer_root"]
    before = {name: verify(viewer / name, expected) for name, expected in cfg["expected_before"].items()}
    candidate_path = AR / cfg["candidate_csv"]
    footprint_path = AR / cfg["shared_footprints"]
    building_path = AR / cfg["building_manifest"]
    bindings = {
        "candidate_csv": verify(candidate_path, cfg["candidate_csv_sha256"]),
        "shared_footprints": verify(footprint_path, cfg["shared_footprints_sha256"]),
        "building_manifest": verify(building_path, cfg["building_manifest_sha256"]),
    }

    with candidate_path.open(newline="") as stream:
        candidates = [row for row in csv.DictReader(stream) if int(row["sparse_building_prism_point_count"]) > 0]
    if len(candidates) != int(cfg["expected_target_count"]):
        raise RuntimeError(f"target count drifted: {len(candidates)}")
    candidate_by_id = {row["stable_id"]: row for row in candidates}
    footprints = json.loads(footprint_path.read_text())
    footprint_by_id = {feature["properties"]["stable_id"]: feature for feature in footprints["features"]}
    buildings = [json.loads(line) for line in building_path.read_text().splitlines() if line]
    building_by_id = {row["building_id"]: row for row in buildings}
    shift_x, shift_y, shift_z = map(float, cfg["world_shift_xyz"])
    target_footprints = []
    for stable_id, candidate in sorted(candidate_by_id.items(), key=lambda item: int(item[1]["population_index"])):
        feature = footprint_by_id[stable_id]
        building = building_by_id[stable_id]
        geometry = feature["geometry"]
        if geometry["type"] != "Polygon":
            raise RuntimeError(f"unsupported footprint geometry: {stable_id}: {geometry['type']}")
        rings = [
            [[float(x) - shift_x, float(y) - shift_y] for x, y in ring]
            for ring in geometry["coordinates"]
        ]
        z_min, z_max = map(float, building["z_range_ellipsoidal_m"])
        status = candidate["sparse_seed_status"]
        strong = status == "SPARSE_SEED_PRESENT_STRONG_MULTI_VIEW_TRACK_PROXY"
        target_footprints.append({
            "stable_id": stable_id,
            "population_index": int(candidate["population_index"]),
            "rings_local_xy": rings,
            "z_local": (z_min + z_max) / 2.0 - shift_z + float(cfg["display_z_offset_m"]),
            "z_source": "EVALUATION_BUILDING_Z_RANGE_DISPLAY_ALIGNMENT_ONLY_NOT_MODEL_INPUT",
            "sparse_seed_status": status,
            "sparse_building_prism_point_count": int(candidate["sparse_building_prism_point_count"]),
            "dense_mvs_all_point_coverage_0p5m": float(candidate["dense_mvs_all_point_coverage_0p5m"]),
            "strength": "strong" if strong else "weak",
            "color": cfg["strong_color"] if strong else cfg["weak_color"],
        })
    strong_count = sum(row["strength"] == "strong" for row in target_footprints)
    weak_count = len(target_footprints) - strong_count
    if strong_count != int(cfg["expected_strong_count"]) or weak_count != int(cfg["expected_weak_count"]):
        raise RuntimeError(f"strength count drifted: {strong_count}/{weak_count}")

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["target_building_footprints"] = target_footprints
    manifest["target_building_footprint_contract"] = {
        "target_rule": cfg["target_rule"],
        "target_count": len(target_footprints),
        "strong_count": strong_count,
        "weak_count": weak_count,
        "default_visible": bool(cfg["default_visible"]),
        "all_199_building_index_role": cfg["all_199_role"],
        "only_target_footprints_are_rendered": True,
        "outline_width_m": float(cfg["outline_width_m"]),
        "evaluation_z_used_for_display_alignment_only": True,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    manifest["roofer_inputs_modified"] = False
    manifest["scientific_verdict"] = None
    atomic_json(manifest_path, manifest)

    app_path = viewer / "app.js"
    app = app_path.read_text()
    app = app.replace(
        "let syntheticRegionsVisible = false;",
        "let syntheticRegionsVisible = false;\nlet targetFootprintsVisible = true;",
    )
    marker = "function surfaceMesh(spec) {"
    helper = r'''function targetFootprintOverlay(rows) {
  const group = new THREE.Group();
  group.name = 'target-building-footprints-58-only';
  const width = Number(manifest.target_building_footprint_contract?.outline_width_m || 0.38);
  for (const row of rows || []) {
    const positions = [];
    for (const ring of row.rings_local_xy) {
      for (let index = 0; index + 1 < ring.length; index++) {
        const [x0, y0] = ring[index];
        const [x1, y1] = ring[index + 1];
        const dx = x1 - x0;
        const dy = y1 - y0;
        const length = Math.hypot(dx, dy);
        if (length <= 1e-9) continue;
        const nx = -dy / length * width / 2;
        const ny = dx / length * width / 2;
        const z = row.z_local;
        positions.push(
          x0 + nx, y0 + ny, z, x0 - nx, y0 - ny, z, x1 - nx, y1 - ny, z,
          x0 + nx, y0 + ny, z, x1 - nx, y1 - ny, z, x1 + nx, y1 + ny, z,
        );
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
      color: row.color,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: row.strength === 'strong' ? 0.98 : 0.90,
      depthTest: false,
      depthWrite: false,
    }));
    mesh.renderOrder = 30;
    mesh.userData.targetBuilding = row;
    group.add(mesh);
  }
  return group;
}

'''
    if "function targetFootprintOverlay" not in app:
        app = app.replace(marker, helper + marker)
    app = app.replace(
        "  const realCandidates = regionOverlay(manifest.real_change_candidates, 'real-change-candidates', 0.98);",
        "  const targetFootprints = targetFootprintOverlay(manifest.target_building_footprints);\n"
        "  targetFootprints.visible = targetFootprintsVisible;\n"
        "  scene.add(targetFootprints);\n"
        "  const realCandidates = regionOverlay(manifest.real_change_candidates, 'real-change-candidates', 0.98);",
    )
    app = app.replace(
        "  const viewer = {root, renderer, scene, camera, object, evidence, surface, realCandidates, syntheticRegions, spec};",
        "  const viewer = {root, renderer, scene, camera, object, evidence, surface, targetFootprints, realCandidates, syntheticRegions, spec};",
    )
    toggle_marker = "document.getElementById('toggleRealChanges').addEventListener('click', event => {"
    toggle_handler = r'''document.getElementById('toggleTargetFootprints').addEventListener('click', event => {
  targetFootprintsVisible = !targetFootprintsVisible;
  for (const viewer of viewers) viewer.targetFootprints.visible = targetFootprintsVisible;
  event.currentTarget.textContent = `대상58 footprint ${targetFootprintsVisible ? 'ON' : 'OFF'}`;
  info.textContent = targetFootprintsVisible
    ? 'MVS raw support 부족 + sparse seed 존재 58동만 표시 · strong 51 cyan / weak 7 amber'
    : '대상 58동 footprint 숨김';
});
'''
    if "toggleTargetFootprints').addEventListener" not in app:
        app = app.replace(toggle_marker, toggle_handler + toggle_marker)
    app = app.replace(
        "document.getElementById('toggleRealChanges').textContent = `시점차 후보 ${realCandidatesVisible ? 'ON' : 'OFF'}`;",
        "document.getElementById('toggleTargetFootprints').textContent = `대상58 footprint ${targetFootprintsVisible ? 'ON' : 'OFF'}`;\n"
        "document.getElementById('toggleRealChanges').textContent = `시점차 후보 ${realCandidatesVisible ? 'ON' : 'OFF'}`;",
    )
    app = app.replace(
        "? 'E1 UAS LiDAR + E2 OpenMVS + E3-E6 TSDF 표면 mesh 로드 완료'",
        "? '표면 mesh 로드 완료 · 대상 footprint 58동만 ON (strong 51 / weak 7)'",
    ).replace(
        ": '8개 패널 로드 완료 · Roofer + E1-E6 입력 점군 표시 · 시점차 후보 기본 OFF';",
        ": '8개 패널 로드 완료 · 대상 footprint 58동만 ON (strong 51 / weak 7)';",
    )
    atomic_text(app_path, app)

    index_path = viewer / "index.html"
    index = index_path.read_text()
    index = index.replace(
        '<button id="toggleSurfaceMeshes" type="button">표면mesh OFF</button>',
        '<button id="toggleSurfaceMeshes" type="button">표면mesh OFF</button><button id="toggleTargetFootprints" type="button">대상58 footprint ON</button>',
    )
    index = index.replace(
        '<span class="legend"><span><i style="background:#fb7185"></i>현재증가</span>',
        '<span class="legend"><span><i style="background:#00e5ff"></i>대상 strong 51</span><span><i style="background:#ffb020"></i>대상 weak 7</span><span><i style="background:#fb7185"></i>현재증가</span>',
    )
    index = index.replace(
        "app.js?v=e1e6-20260810-e1-lidar-surface-v1",
        "app.js?v=e1e6-20260810-target-footprints-58-v1",
    )
    atomic_text(index_path, index)

    after = {name: {"bytes": (viewer / name).stat().st_size, "sha256": sha256(viewer / name)} for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_target_footprints_58.receipt.v1",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {"path": str(CONFIG), "sha256": sha256(CONFIG)},
        "script": {"path": str(SOURCE), "sha256": sha256(SOURCE)},
        "bindings": bindings,
        "counts": {"target": len(target_footprints), "strong": strong_count, "weak": weak_count},
        "viewer_before": before,
        "viewer_after": after,
        "only_target_footprints_rendered": True,
        "all_199_index_preserved_for_non_visible_camera_lookup": True,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
