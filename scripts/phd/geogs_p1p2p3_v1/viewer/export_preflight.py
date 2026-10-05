"""Reference-free browser display preflight from actual sealed ALS surface vertices.

Mount only three surface PLY files, config and new output. No UAS or evaluations.
This is not a GeoGS result, geometric evaluation or surface quality assessment.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False)


cfg_path = Path("/config.json")
cfg = json.loads(cfg_path.read_text())
out = Path("/out")
if (out / "manifest.json").exists():
    raise FileExistsError("Preserve prior preflight exports")
manifest = {"schema": "geogs_p1p2p3_viewer_v1", "scientific_verdict": None,
            "status": "PREFLIGHT_INPUT_DISPLAY_ONLY", "regions": [], "default_region": "P1",
            "downloads": [{"label": "참조 없는 표시 점검 기록", "url": "receipt.json"}]}
receipt = {"status": "PREFLIGHT_INPUT_DISPLAY_ONLY", "scientific_verdict": None,
           "config_sha256": sha(cfg_path), "source_script_sha256": sha(__file__),
           "inputs": {}, "no_reference_mounted": True,
           "sampling": "All actual input ALS mesh vertices incident to a triangle and in frozen core prism; deterministic evenly spaced original vertex order only above 50000; no Gaussian points",
           "libraries": {"numpy": np.__version__, "trimesh": trimesh.__version__}}
for region, value in cfg["regions"].items():
    path = Path("/surfaces") / f"{region}.ply"
    mesh = trimesh.load(path, process=False, force="mesh")
    vertices = np.asarray(mesh.vertices)
    used = np.unique(np.asarray(mesh.faces).reshape(-1))
    points = vertices[used]
    lower = np.asarray([value["domain"][axis][0] for axis in "xyz"])
    upper = np.asarray([value["domain"][axis][1] for axis in "xyz"])
    points = points[np.all((points >= lower) & (points < upper), axis=1)]
    full_count = len(points)
    if not full_count:
        raise ValueError(f"No actual core mesh vertices: {region}")
    if len(points) > 50000:
        points = points[np.linspace(0, len(points) - 1, 50000, dtype=np.int64)]
    point_name = f"{region}_als_surface_display.json"
    write(out / point_name, {"display_only": True, "xyz": points.astype(np.float32).reshape(-1).tolist(),
                             "source": "Actual ALS-derived triangle mesh incident vertices; not Gaussian centers"})
    file_receipt = {"source": f"inputs/{region}/surface/als_surface.ply", "sha256": sha(path),
                    "incident_core_vertices": full_count, "display_count": len(points),
                    "display_sha256": sha(out / point_name)}
    receipt["inputs"][region] = file_receipt
    candidates = [{"id": "prior", "label": "실제 ALS 표면 입력", "role": "prior", "status": "available",
                   "surface_kind": "ALS-derived input mesh incident vertices",
                   "source_count": full_count, "provenance": file_receipt,
                   "data": {"format": "json", "url": point_name},
                   "downloads": [{"label": "입력 표면 전체 PLY", "url": f"../inputs/{region}/surface/als_surface.ply"},
                                 {"label": "표면 변환 기록", "url": f"../inputs/{region}/surface/surface_receipt.json"}]}]
    for role in ["mvs", "anchor", "vanilla", "changed", "reference"]:
        candidates.append({"id": role, "label": "사전 표시 점검 제외", "role": role, "status": "pending",
                           "reason": "PREFLIGHT_INPUT_DISPLAY_ONLY: 참조 없는 입력 표시 점검입니다. 이 화면은 GeoGS 결과 분석이 아닙니다."})
    manifest["regions"].append({"id": region, "label": region + " · 사전 입력 표시 점검",
                               "bounds": {"min": lower.tolist(), "max": upper.tolist()},
                               "frame": {"working_crs": cfg["crs"]["working"], "world_shift": cfg["crs"]["world_shift"]},
                               "notes": ["PREFLIGHT_INPUT_DISPLAY_ONLY — 실제 ALS 표면 입력만 표시. GeoGS/UAS/MVS 결과 대기. 정량·정성 실험 결과가 아닙니다."],
                               "candidates": candidates,
                               "panel_candidates": {key: key for key in ["prior", "mvs", "anchor", "vanilla", "reference"]},
                               "conditions": [{"id": "preflight", "label": "결과 없는 표시 점검", "candidate_id": "changed"}],
                               "sections": [], "renders": [],
                               "case_selection_note": "고정 P1/P2/P3 prism의 실제 prior 입력을 모두 표시했습니다. 참조와 실험 결과는 이 점검에 접근하지 않습니다."})
write(out / "manifest.json", manifest)
receipt["manifest_sha256"] = sha(out / "manifest.json")
write(out / "receipt.json", receipt)
(out / "config_snapshot.json").write_bytes(cfg_path.read_bytes())
print(json.dumps(receipt, ensure_ascii=False))
