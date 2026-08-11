#!/usr/bin/env python3
"""Rerun Roofer with an exterior-ring terrain height, without changing GS outputs."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


REPO_HOST = Path(__file__).resolve().parents[3]
ARTIFACT_HOST = REPO_HOST.parent / "JointBuildGS-artifacts"
REPO = Path("/workspace/JointBuildGS")
ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")
CONFIG_REL = Path("configs/p2/e3_local_4906982_ring_ground_roofer_v1/experiment.yaml")
SCRIPT_REL = Path("scripts/p2/e3_local_4906982_ring_ground_roofer_v1/run.py")
TASK_REL = Path("phase-payloads/p2/e3_local_4906982_ring_ground_roofer_v1/P2-E3-LOCAL-4906982-RING-GROUND-ROOFER-v1")
TASK_HOST = ARTIFACT_HOST / TASK_REL
TASK_ROOT = ARTIFACT_ROOT / TASK_REL
TOOLS_IMAGE = "jointbuildgs:dev"
GROUND_ATTRIBUTE = "jbgs_ground_z"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(body, indent=2, sort_keys=True) + "\n"
    if path.is_file():
        if path.read_text() != encoded:
            raise RuntimeError(f"immutable output drift: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded)
    os.replace(temporary, path)


def load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text())


def docker_python(command: str) -> list[str]:
    uid, gid = os.getuid(), os.getgid()
    return [
        "docker", "run", "--rm", "--network", "none", "--user", f"{uid}:{gid}",
        "-v", f"{REPO_HOST}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_HOST}:/artifacts/JointBuildGS:rw",
        "-w", "/workspace/JointBuildGS", TOOLS_IMAGE,
        "python", str(SCRIPT_REL), command,
    ]


def run_capture(argv: list[str], log: Path | None = None) -> subprocess.CompletedProcess[str]:
    if log is None:
        return subprocess.run(argv, text=True, capture_output=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        return subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)


def record_runtime_context_host() -> None:
    provenance_path = TASK_HOST / "provenance.json"
    if not provenance_path.is_file():
        return
    provenance = json.loads(provenance_path.read_text())
    images = {}
    for key, image in (("analysis", TOOLS_IMAGE), ("roofer", json.loads((TASK_HOST / "control/run_plan.json").read_text())["roofer_image"])):
        result = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True, capture_output=True)
        images[key] = {"reference": image, "local_id": result.stdout.strip(), "inspect_return_code": result.returncode}
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True, capture_output=True)
    operations = []
    for path in sorted((TASK_HOST / "cases").glob("*/roofer/operation.json")):
        operations.append(json.loads(path.read_text()))
    provenance["docker_images"] = images
    provenance["gpu"] = {"used": False, "model": None if gpu.returncode else gpu.stdout.splitlines()[0].strip(), "query_return_code": gpu.returncode}
    provenance["commands"] = [row["command"] for row in operations]
    provenance["return_codes"] = [{"case": row["case"], "return_code": row["return_code"], "started_utc": row["started_utc"], "ended_utc": row["ended_utc"]} for row in operations]
    provenance["source_sha256"] = {str(CONFIG_REL): sha256(REPO_HOST / CONFIG_REL), str(SCRIPT_REL): sha256(REPO_HOST / SCRIPT_REL)}
    provenance["scientific_verdict"] = None
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")


def host_all() -> None:
    complete = TASK_HOST / "metrics.json"
    if complete.is_file() and json.loads(complete.read_text()).get("status") == "COMPLETE":
        record_runtime_context_host()
        print(complete.read_text())
        return
    prep = run_capture(docker_python("prepare"))
    if prep.returncode:
        raise RuntimeError(prep.stdout + prep.stderr)
    plan = json.loads((TASK_HOST / "control/run_plan.json").read_text())
    operations = []
    for case in plan["cases"]:
        case_root = TASK_HOST / "cases" / case["id"]
        output = case_root / "roofer/output"
        receipt = case_root / "roofer/operation.json"
        if receipt.is_file() and json.loads(receipt.read_text()).get("return_code") == 0 and list(output.glob("*.city.jsonl")):
            operations.append(json.loads(receipt.read_text()))
            continue
        if output.exists() and any(output.iterdir()):
            raise RuntimeError(f"unsealed Roofer output: {output}")
        output.mkdir(parents=True, exist_ok=True)
        uid, gid = os.getuid(), os.getgid()
        argv = [
            "docker", "run", "--rm", "--network", "none", "--cpus", "12", "--memory", "64g",
            "--pids-limit", "4096", "--user", f"{uid}:{gid}",
            "-v", f"{ARTIFACT_HOST}:/artifacts/JointBuildGS:ro",
            "-v", f"{TASK_HOST}:/task:rw", "-w", "/task", plan["roofer_image"],
            "--id-attribute", "stable_id", "--jobs", "1", "--box", *[str(value) for value in plan["roofer_box"]],
            "--h-terrain-strategy", "user", "--h-terrain-attribute", GROUND_ATTRIBUTE,
            f"/artifacts/JointBuildGS/{case['source_classified_laz']}",
            f"cases/{case['id']}/footprint_ring_ground.geojson",
            f"cases/{case['id']}/roofer/output",
        ]
        started_utc, started = now(), time.monotonic()
        proc = run_capture(argv, case_root / "roofer/roofer.log")
        body = {
            "schema": "jointbuildgs.p2.e3_local_4906982_ring_ground_roofer_v1.operation.v1",
            "case": case["id"], "command": argv, "started_utc": started_utc, "ended_utc": now(),
            "wall_seconds": time.monotonic() - started, "return_code": proc.returncode,
            "scientific_verdict": None,
        }
        atomic_json(receipt, body)
        operations.append(body)
        if proc.returncode:
            (TASK_HOST / "issues.md").write_text(f"# Issues\n\n- Roofer failed for `{case['id']}`; see `{case_root / 'roofer/roofer.log'}`.\n")
            raise RuntimeError(f"Roofer failed: {case['id']}")
    final = run_capture(docker_python("finalize"), TASK_HOST / "logs/finalize.log")
    if final.returncode:
        raise RuntimeError(f"finalize failed; inspect {TASK_HOST / 'logs/finalize.log'}")
    record_runtime_context_host()
    print((TASK_HOST / "metrics.json").read_text())


def load_footprint() -> tuple[dict, object, Path]:
    source = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1/control/shared_standard_footprint_4906982.geojson"
    document = json.loads(source.read_text())
    from shapely.geometry import shape
    return document, shape(document["features"][0]["geometry"]), source


def cloud_ground_metrics(path: Path, footprint, outer_m: float, ground_class: int, quantile: float) -> tuple[dict, float]:
    import laspy
    import numpy as np
    from shapely import contains_xy
    cloud = laspy.read(path)
    xyz = np.column_stack((np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z)))
    classes = np.asarray(cloud.classification, dtype=np.uint8)
    inside = contains_xy(footprint, xyz[:, 0], xyz[:, 1])
    ring_geometry = footprint.buffer(outer_m)
    in_buffer = contains_xy(ring_geometry, xyz[:, 0], xyz[:, 1])
    ring = (classes == ground_class) & (~inside) & in_buffer
    inclusive = (classes == ground_class) & in_buffer
    interior = (classes == ground_class) & inside
    def stats(mask) -> dict:
        z = xyz[mask, 2]
        return {
            "count": int(len(z)), "min_z": None if not len(z) else float(z.min()),
            "q05_z": None if not len(z) else float(np.quantile(z, 0.05)),
            "median_z": None if not len(z) else float(np.median(z)),
            "p95_z": None if not len(z) else float(np.quantile(z, 0.95)),
            "max_z": None if not len(z) else float(z.max()),
        }
    ring_stats = stats(ring)
    if ring_stats["count"] == 0:
        raise RuntimeError(f"no exterior-ring ground points: {path}")
    ground_z = float(np.quantile(xyz[ring, 2], quantile))
    return {"interior": stats(interior), "inclusive_buffer": stats(inclusive), "exterior_ring": ring_stats}, ground_z


def prepare() -> None:
    import yaml
    cfg_path = REPO / CONFIG_REL
    cfg = load_yaml(cfg_path)
    document, footprint, footprint_source = load_footprint()
    root = TASK_ROOT
    for name in ("control", "cases", "logs", "representative_images"):
        (root / name).mkdir(parents=True, exist_ok=True)
    outer = float(cfg["ground_height"]["exterior_ring_outer_m"])
    ground_class = int(cfg["ground_height"]["source_class"])
    quantile = float(cfg["ground_height"]["quantile"])
    minimum = int(cfg["ground_height"]["minimum_point_count"])
    rows, hashes, cases = [], {"config": sha256(cfg_path), "footprint": sha256(footprint_source)}, []
    bounds = footprint.bounds
    pad = float(cfg["roofer"]["aoi_buffer_m"])
    for item in cfg["cases"]:
        source = ARTIFACT_ROOT / item["source_fusion"]
        classified = source / "classified_surface.laz"
        old_city = next((source / "roofer/output").glob("*.city.jsonl"))
        if not classified.is_file() or not old_city.is_file():
            raise FileNotFoundError(source)
        metrics, ground_z = cloud_ground_metrics(classified, footprint, outer, ground_class, quantile)
        if metrics["exterior_ring"]["count"] < minimum:
            raise RuntimeError(f"insufficient ring ground: {item['id']}")
        case_root = root / "cases" / item["id"]
        case_root.mkdir(parents=True, exist_ok=True)
        feature = {
            "type": "Feature", "geometry": document["features"][0]["geometry"],
            "properties": {
                "stable_id": cfg["building_id"], "class": 6, GROUND_ATTRIBUTE: ground_z,
                "ground_height_source": "CLASS2_EXTERIOR_RING_Q05",
                "ground_ring_outer_m": outer, "lod2_z_used": False, "roofsurface_used": False,
            },
        }
        derived = {"type": "FeatureCollection", "name": f"{cfg['building_id']}_{item['id']}_ring_ground", "crs": document.get("crs"), "features": [feature]}
        atomic_json(case_root / "footprint_ring_ground.geojson", derived)
        row = {
            "case": item["id"], "label": item["label"], "ground_z_exterior_ring_q05": ground_z,
            "interior_class2_count": metrics["interior"]["count"], "interior_class2_q05_z": metrics["interior"]["q05_z"],
            "inclusive_4m_count": metrics["inclusive_buffer"]["count"], "inclusive_4m_q05_z": metrics["inclusive_buffer"]["q05_z"],
            "exterior_ring_4m_count": metrics["exterior_ring"]["count"], "exterior_ring_4m_q05_z": metrics["exterior_ring"]["q05_z"],
        }
        rows.append(row)
        rel_classified = classified.relative_to(ARTIFACT_ROOT).as_posix()
        rel_old = old_city.relative_to(ARTIFACT_ROOT).as_posix()
        cases.append({"id": item["id"], "label": item["label"], "source_classified_laz": rel_classified, "source_old_cityjson": rel_old, "ground_z": ground_z})
        hashes[f"{item['id']}.classified_surface.laz"] = sha256(classified)
        hashes[f"{item['id']}.old_cityjson"] = sha256(old_city)
        atomic_json(case_root / "ground_height.json", {"schema": "jointbuildgs.ring_ground_height.v1", "case": item["id"], "definition": {"ground_class": ground_class, "inside_footprint_excluded": True, "ring_outer_m": outer, "quantile": quantile}, "metrics": metrics, "selected_ground_z": ground_z, "lod2_z_used": False, "scientific_verdict": None})
    atomic_json(root / "control/run_plan.json", {"schema": cfg["schema"], "task_id": cfg["task_id"], "roofer_image": cfg["roofer"]["image"], "roofer_box": [bounds[0]-pad, bounds[1]-pad, bounds[2]+pad, bounds[3]+pad], "cases": cases, "scientific_verdict": None})
    atomic_json(root / "input_hashes.json", hashes)
    with (root / "ground_height_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    atomic_json(root / "ground_height_metrics.json", {"rows": rows, "scientific_verdict": None})
    if not (root / "config_diff.txt").is_file():
        (root / "config_diff.txt").write_text("Roofer h-terrain-strategy: buffer_tile -> user\nRoofer h-terrain-attribute: unset -> jbgs_ground_z\nTerrain candidates: class2 in footprint.buffer(4m) -> class2 in footprint.buffer(4m) minus footprint interior\nTerrain statistic: q05 -> q05 (unchanged)\nPoint cloud, footprint XY, Roofer quality parameters: unchanged\nLoD2 Z/RoofSurface/roof type: unused before reconstruction\nscientific_verdict: null\n")
    if not (root / "NOTES.md").is_file():
        (root / "NOTES.md").write_text("# Ring-ground Roofer readout\n\nThis task reruns Roofer only. It reuses immutable 20k classified fusion clouds and exact shared footprint XY. Ground height is frozen per case as the 5th Z percentile of class-2 points in the exterior 0-4 m ring. Training, fusion, and classification are not rerun. LoD2 Z and surfaces are evaluation-only after reconstruction. `scientific_verdict` is `null`.\n")
    atomic_json(root / "experiment_contract.json", {"task_id": cfg["task_id"], "status": "PREPARED", "single_variable": "Roofer terrain-height candidate region", "training_reruns": 0, "fusion_reruns": 0, "classification_reruns": 0, "roofer_reruns_planned": len(cases), "scientific_verdict": None})
    if not (root / "provenance.json").is_file():
        git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, text=True, capture_output=True, check=True).stdout.strip()
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=REPO, text=True, capture_output=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, text=True, capture_output=True, check=True).stdout.splitlines()
        atomic_json(root / "provenance.json", {"schema": "jointbuildgs.provenance.v1", "task_id": cfg["task_id"], "started_utc": now(), "ended_utc": None, "git": {"commit": git_head, "branch": branch, "dirty": bool(dirty), "dirty_entries": dirty}, "docker": {"analysis_image": TOOLS_IMAGE, "roofer_image": cfg["roofer"]["image"]}, "inputs": hashes, "commands": [], "return_codes": [], "scientific_verdict": None})
    print(json.dumps({"status": "PREPARED", "cases": len(cases), "scientific_verdict": None}))


def import_helper():
    path = REPO / "scripts/p2/e4_local_4906982_55v_als_normal_ablation_v1/build_viewer.py"
    spec = importlib.util.spec_from_file_location("ring_ground_viewer_helper", path)
    if spec is None or spec.loader is None: raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def roof_z_and_height(surfaces: list[dict], attributes: dict) -> tuple[float | None, float | None]:
    import numpy as np
    roof_z = [float(vertex[1] + 570.0) for face in surfaces if face["type"] == "RoofSurface" for vertex in face["vertices"]]
    median = None if not roof_z else float(np.median(roof_z))
    ground = attributes.get("rf_h_ground")
    return median, None if median is None or ground is None else median - float(ground)


def roof_xy_coverage(surfaces: list[dict], footprint, center) -> float:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polygons = []
    for face in surfaces:
        if face["type"] != "RoofSurface":
            continue
        world_xy = [(float(v[0] + center[0]), float(-v[2] + center[1])) for v in face["vertices"]]
        polygon = Polygon(world_xy)
        if polygon.is_valid and polygon.area > 0:
            polygons.append(polygon)
    if not polygons:
        return 0.0
    return float(unary_union(polygons).intersection(footprint).area / footprint.area)


def render_figures(records: list[dict], helper, references: list[dict], footprint) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import numpy as np
    output = TASK_ROOT / "representative_images"
    output.mkdir(parents=True, exist_ok=True)
    colors = {"RoofSurface": "#f3a712", "WallSurface": "#4ea5d9", "GroundSurface": "#7568a6", "ReferenceRoof": "#65d6c4", "ReferenceWall": "#65d6c4", "ReferenceGround": "#65d6c4"}
    zlim = (555.0, 594.0)
    def draw3d(ax, surfaces, title, reference=False):
        for face in surfaces:
            vertices = np.asarray(face["vertices"], dtype=float)
            xyz = np.column_stack((vertices[:, 0], -vertices[:, 2], vertices[:, 1] + 570.0))
            ax.add_collection3d(Poly3DCollection([xyz], facecolor=colors.get(face["type"], "#aaa"), edgecolor="#222", linewidth=.35, alpha=.72 if not reference else .35))
        ax.set_xlim(-30, 30); ax.set_ylim(-30, 30); ax.set_zlim(*zlim); ax.set_box_aspect((60,60,32)); ax.view_init(elev=25, azim=-55); ax.set_title(title, fontsize=9); ax.set_xlabel("local E", fontsize=7); ax.set_ylabel("local N", fontsize=7); ax.set_zlabel("Z", fontsize=7); ax.tick_params(labelsize=6)
    fig = plt.figure(figsize=(15, 25), dpi=150, constrained_layout=True)
    for row, record in enumerate(records):
        draw3d(fig.add_subplot(len(records),3,row*3+1,projection="3d",proj_type="ortho"), record["old_surfaces"], f"{record['label']}\nold buffer ground {record['old_ground_z']:.3f} m")
        draw3d(fig.add_subplot(len(records),3,row*3+2,projection="3d",proj_type="ortho"), record["new_surfaces"], f"exterior-ring ground {record['new_ground_z']:.3f} m")
        draw3d(fig.add_subplot(len(records),3,row*3+3,projection="3d",proj_type="ortho"), references, "evaluation-only LoD2 reference", True)
    oblique = output / "roofer_old_vs_exterior_ring_oblique_20k.png"; fig.savefig(oblique); plt.close(fig)
    fig, axes = plt.subplots(len(records), 3, figsize=(15, 20), dpi=150, constrained_layout=True)
    for row, record in enumerate(records):
        for col, (surfaces, title) in enumerate(((record["old_surfaces"], "old"), (record["new_surfaces"], "exterior ring"), (references, "reference"))):
            ax=axes[row,col]
            for face in surfaces:
                vertices=np.asarray(face["vertices"],dtype=float); x=vertices[:,0]; z=vertices[:,1]+570.0
                ax.fill(x,z,facecolor=colors.get(face["type"],"#aaa"),edgecolor="#222",alpha=.55,linewidth=.45)
            ax.set_xlim(-30,30);ax.set_ylim(*zlim);ax.grid(alpha=.2);ax.set_title(f"{record['label']} · {title}" if col==0 else title,fontsize=9);ax.set_xlabel("local E");ax.set_ylabel("Z")
    side=output/"roofer_old_vs_exterior_ring_side_20k.png";fig.savefig(side);plt.close(fig)
    labels=[r["id"] for r in records]; old=[r["old_ground_z"] for r in records]; new=[r["new_ground_z"] for r in records]
    ref_ground=min(v[1]+570.0 for f in references if f["type"]=="ReferenceGround" for v in f["vertices"])
    fig,ax=plt.subplots(figsize=(14,6),dpi=160,constrained_layout=True);x=np.arange(len(labels));w=.34
    ax.bar(x-w/2,old,w,label="old inclusive buffer",color="#d95f02");ax.bar(x+w/2,new,w,label="exterior ring",color="#1b9e77");ax.axhline(ref_ground,color="#7570b3",linestyle="--",label=f"eval-only reference {ref_ground:.3f} m")
    ax.set_xticks(x,labels,rotation=18,ha="right");ax.set_ylabel("Roofer ground Z (m)");ax.set_ylim(555,585);ax.grid(axis="y",alpha=.25);ax.legend()
    for i,(a,b) in enumerate(zip(old,new)):ax.text(i-w/2,a+.25,f"{a:.2f}",ha="center",fontsize=8);ax.text(i+w/2,b+.25,f"{b:.2f}",ha="center",fontsize=8)
    diagnostic=output/"ground_z_old_vs_exterior_ring.png";fig.savefig(diagnostic);plt.close(fig)
    return [oblique,side,diagnostic]


def build_gallery(records: list[dict], images: list[Path]) -> Path:
    cfg = load_yaml(REPO / CONFIG_REL)
    viewer_root = ARTIFACT_ROOT / cfg["viewer"]["root"]
    slot = viewer_root / cfg["viewer"]["slot"]
    fixed = [viewer_root/name for name in ("index.html","app.js","viewer_manifest.json","mvs_depth_viewer_receipt.json")]
    before = {path.name: sha256(path) for path in fixed}
    if slot.exists() and any(slot.iterdir()):
        manifest = slot / "manifest.json"
        if not manifest.is_file() or json.loads(manifest.read_text()).get("task_id") != cfg["task_id"]: raise RuntimeError(f"viewer slot collision: {slot}")
    slot.mkdir(parents=True,exist_ok=True)
    for image in images: shutil.copy2(image,slot/image.name)
    rows="".join(f"<tr><td>{r['label']}</td><td>{r['old_ground_z']:.3f}</td><td>{r['new_ground_z']:.3f}</td><td>{r['old_height_m']:.3f}</td><td>{r['new_height_m']:.3f}</td><td>{100*r['new_roof_xy_coverage_fraction']:.1f}%</td><td>{r['new_attributes'].get('rf_roof_planes')}</td><td>{r['new_attributes'].get('rf_volume_lod22'):.1f}</td></tr>" for r in records)
    page=f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Exterior-ring Roofer ground</title><style>body{{font-family:system-ui;background:#071018;color:#e8f0f4;margin:24px}}a{{color:#7fd3ff}}img{{display:block;width:100%;max-width:1800px;margin:16px 0;border:1px solid #456}}table{{border-collapse:collapse;width:100%;max-width:1400px}}th,td{{border:1px solid #456;padding:7px;text-align:right}}th:first-child,td:first-child{{text-align:left}}</style></head><body><h1>DEBY_LOD2_4906982 · exterior-ring ground Roofer</h1><p>동일 20k classified point cloud와 동일 footprint XY. Roofer ground만 내부 포함 buffer q05에서 외부 0–4 m ring class-2 q05로 변경. Reference는 evaluation-only. scientific_verdict=null.</p><table><thead><tr><th>case</th><th>old ground Z</th><th>ring ground Z</th><th>old height</th><th>ring height</th><th>ring roof XY</th><th>roof planes</th><th>ring volume m³</th></tr></thead><tbody>{rows}</tbody></table>"""
    for image in images: page+=f"<h2>{image.stem}</h2><img src='{image.name}' alt='{image.stem}'>"
    page+="</body></html>";(slot/"index.html").write_text(page)
    atomic_json(slot/"manifest.json",{"task_id":cfg["task_id"],"slot":cfg["viewer"]["slot"],"scientific_verdict":None})
    after={path.name:sha256(path) for path in fixed}
    if before!=after:raise RuntimeError("protected viewer root files changed")
    atomic_json(TASK_ROOT/"viewer_slot.json",{"slot":cfg["viewer"]["slot"],"relative_url":f"{cfg['viewer']['slot']}/index.html","protected_root_hashes_unchanged":True,"scientific_verdict":None})
    return slot


def finalize() -> None:
    import numpy as np
    cfg=load_yaml(REPO/CONFIG_REL);plan=json.loads((TASK_ROOT/"control/run_plan.json").read_text());helper=import_helper();document,footprint,_=load_footprint();center=np.asarray([footprint.centroid.x,footprint.centroid.y,570.0]);references,_=helper.reference_surfaces(center)
    records=[]
    for case in plan["cases"]:
        case_root=TASK_ROOT/"cases"/case["id"];new_city=next((case_root/"roofer/output").glob("*.city.jsonl"));old_city=ARTIFACT_ROOT/case["source_old_cityjson"]
        old_surfaces,old_attrs=helper.city_surfaces(old_city,center);new_surfaces,new_attrs=helper.city_surfaces(new_city,center)
        if abs(float(new_attrs["rf_h_ground"])-float(case["ground_z"]))>0.002:raise RuntimeError(f"Roofer did not use frozen ring ground: {case['id']}")
        old_roof,old_height=roof_z_and_height(old_surfaces,old_attrs);new_roof,new_height=roof_z_and_height(new_surfaces,new_attrs)
        record={"id":case["id"],"label":case["label"],"source_classified_laz":case["source_classified_laz"],"old_cityjson":case["source_old_cityjson"],"new_cityjson":new_city.relative_to(ARTIFACT_ROOT).as_posix(),"old_ground_z":float(old_attrs["rf_h_ground"]),"new_ground_z":float(new_attrs["rf_h_ground"]),"old_roof_z_median":old_roof,"new_roof_z_median":new_roof,"old_height_m":old_height,"new_height_m":new_height,"old_roof_xy_coverage_fraction":roof_xy_coverage(old_surfaces,footprint,center),"new_roof_xy_coverage_fraction":roof_xy_coverage(new_surfaces,footprint,center),"old_attributes":old_attrs,"new_attributes":new_attrs,"old_surfaces":old_surfaces,"new_surfaces":new_surfaces,"scientific_verdict":None};records.append(record)
        atomic_json(case_root/"roofer/terminal.json",{"schema":"jointbuildgs.ring_ground_roofer_terminal.v1","case":case["id"],"output_cityjson_sha256":sha256(new_city),"target_attributes":new_attrs,"ground_height_gate":"PASS","scientific_verdict":None})
    images=render_figures(records,helper,references,footprint);slot=build_gallery(records,images)
    slim=[]
    for r in records:slim.append({k:v for k,v in r.items() if k not in ("old_surfaces","new_surfaces","old_attributes")})
    (TASK_ROOT/"metrics.json").write_text(json.dumps({"schema":"jointbuildgs.p2.e3_local_4906982_ring_ground_roofer_v1.metrics.v1","status":"COMPLETE","training_reruns":0,"fusion_reruns":0,"classification_reruns":0,"roofer_reruns":len(records),"rows":slim,"scientific_verdict":None},indent=2,sort_keys=True)+"\n")
    with (TASK_ROOT/"roofer_metrics.csv").open("w",newline="") as stream:
        fields=["id","label","old_ground_z","new_ground_z","old_roof_z_median","new_roof_z_median","old_height_m","new_height_m","old_roof_xy_coverage_fraction","new_roof_xy_coverage_fraction"]
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows([{k:r[k] for k in fields} for r in records])
    lines=["# Exterior-ring ground Roofer comparison","","Only Roofer terrain-height selection changed; training, fusion, classification, point clouds, footprint XY, and other Roofer parameters are unchanged.","","| case | old ground Z | ring ground Z | old height | ring height | old roof XY | ring roof XY | roof planes | ring volume |","|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in records:lines.append(f"| {r['label']} | {r['old_ground_z']:.3f} | {r['new_ground_z']:.3f} | {r['old_height_m']:.3f} | {r['new_height_m']:.3f} | {100*r['old_roof_xy_coverage_fraction']:.1f}% | {100*r['new_roof_xy_coverage_fraction']:.1f}% | {r['new_attributes'].get('rf_roof_planes')} | {r['new_attributes'].get('rf_volume_lod22'):.1f} |")
    lines.extend(["","Reference LoD2 geometry is used only in the post-Roofer figures. `scientific_verdict` remains `null`."])
    (TASK_ROOT/"comparison.md").write_text("\n".join(lines)+"\n")
    contract=json.loads((TASK_ROOT/"experiment_contract.json").read_text());contract.update({"status":"COMPLETE","roofer_reruns_actual":len(records),"viewer_slot":cfg["viewer"]["slot"],"scientific_verdict":None});(TASK_ROOT/"experiment_contract.json").write_text(json.dumps(contract,indent=2,sort_keys=True)+"\n")
    provenance=json.loads((TASK_ROOT/"provenance.json").read_text());provenance.update({"ended_utc":now(),"source_sha256":{str(CONFIG_REL):sha256(REPO/CONFIG_REL),str(SCRIPT_REL):sha256(REPO/SCRIPT_REL)},"outputs":{path.relative_to(TASK_ROOT).as_posix():sha256(path) for path in images+[TASK_ROOT/"metrics.json",TASK_ROOT/"comparison.md"]},"viewer_slot":str(slot),"scientific_verdict":None});(TASK_ROOT/"provenance.json").write_text(json.dumps(provenance,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":"COMPLETE","cases":len(records),"images":[str(p) for p in images],"viewer":str(slot),"scientific_verdict":None},indent=2))


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("command",choices=("all","prepare","finalize"));command=parser.parse_args().command
    {"all":host_all,"prepare":prepare,"finalize":finalize}[command]()


if __name__ == "__main__":
    main()
