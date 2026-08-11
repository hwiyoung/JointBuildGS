#!/usr/bin/env python3
"""Build an add-only interactive 3D comparison of classified evidence and Roofer."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import shape
import yaml


REPO = Path("/workspace/JointBuildGS")
ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E4-LOCAL-4906982-55V-ALS-NORMAL-ABLATION-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_normal_ablation_v1" / TASK_ID
FULL_E4_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
CONFIG = REPO / "configs/p2/e4_local_4906982_55v_als_normal_ablation_v1/viewer.yaml"
STEPS = (7000, 12000, 15000, 20000)
ARM_SOURCES = {
    "FUSED_VIS_CONF": (TASK_ROOT, "FUSED_VIS_CONF", "Control: image MVS depth + MVC/NC, no ALS prior"),
    "ALS_DEPTH_ONLY": (TASK_ROOT, "ALS_DEPTH_ONLY", "ALS metric depth, no ALS normal"),
    "E4_ALS_PRIOR_ONLY": (FULL_E4_ROOT, "E4_ALS_PRIOR_ONLY", "Full E4: ALS depth + normal"),
}
REFERENCE_GML = ARTIFACT_ROOT / "phase-payloads/p0-audit/data/raw/lod2/690_5336.gml"
PREDICTION_Z_SHIFT_TO_REFERENCE_M = -45.7


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict]:
    return json.loads(path.read_text()).get("rows", [])


def select_row(rows: list[dict], arm: str, step: int) -> dict:
    return next(row for row in rows if row.get("arm") == arm and row.get("completed_updates") == step)


def sample(points: np.ndarray, maximum: int) -> np.ndarray:
    if len(points) <= maximum:
        return points
    return points[np.linspace(0, len(points) - 1, maximum, dtype=np.int64)]


def city_surfaces(path: Path, center: np.ndarray) -> tuple[list[dict], dict]:
    documents = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    transform = documents[0]["transform"]
    scale = np.asarray(transform["scale"], dtype=np.float64)
    translate = np.asarray(transform["translate"], dtype=np.float64)
    feature = documents[1]
    vertices = np.asarray(feature["vertices"], dtype=np.float64) * scale + translate
    mapped = np.column_stack((vertices[:, 0] - center[0], vertices[:, 2] - center[2], -(vertices[:, 1] - center[1])))
    output: list[dict] = []
    attributes = feature["CityObjects"]["DEBY_LOD2_4906982"].get("attributes", {})
    for obj in feature["CityObjects"].values():
        for geometry in obj.get("geometry", []):
            if geometry.get("type") != "Solid":
                continue
            semantics = geometry.get("semantics", {})
            definitions = semantics.get("surfaces", [])
            values = semantics.get("values", [])
            for shell_index, shell in enumerate(geometry["boundaries"]):
                shell_values = values[shell_index] if shell_index < len(values) else [None] * len(shell)
                for surface_index, rings in enumerate(shell):
                    if not rings or len(rings[0]) < 3:
                        continue
                    semantic_index = shell_values[surface_index] if surface_index < len(shell_values) else None
                    semantic = definitions[semantic_index] if isinstance(semantic_index, int) and semantic_index < len(definitions) else {"type": "Unknown"}
                    output.append({
                        "type": semantic.get("type", "Unknown"),
                        "vertices": np.round(mapped[np.asarray(rings[0], dtype=np.int64)], 4).tolist(),
                        "on_footprint_edge": semantic.get("on_footprint_edge"),
                    })
    return output, attributes


def reference_surfaces(center: np.ndarray) -> tuple[list[dict], list[Any]]:
    library_path = REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py"
    spec = importlib.util.spec_from_file_location("jbgs_viewer_reference_library", library_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(library_path)
    library = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = library
    spec.loader.exec_module(library)
    from lxml import etree

    surfaces = []
    document = etree.parse(str(REFERENCE_GML))
    building = next((element for element in document.iter() if library.local_name(element.tag) == "Building" and library.gml_id(element) == "DEBY_LOD2_4906982"), None)
    if building is None:
        raise RuntimeError("evaluation-only LoD2 building not found")
    type_map = {"RoofSurface": "ReferenceRoof", "WallSurface": "ReferenceWall", "GroundSurface": "ReferenceGround"}
    for semantic in building.iter():
        local = library.local_name(semantic.tag)
        if local not in type_map:
            continue
        polygon_index = 0
        for polygon in semantic.iter():
            if library.local_name(polygon.tag) != "Polygon":
                continue
            polygon_index += 1
            ring = library.first_poslist(polygon)
            if ring is None or len(ring) < 3:
                continue
            vertices = np.asarray(ring, dtype=np.float64).copy()
            vertices[:, 2] -= PREDICTION_Z_SHIFT_TO_REFERENCE_M
            mapped = np.column_stack((vertices[:, 0] - center[0], vertices[:, 2] - center[2], -(vertices[:, 1] - center[1])))
            surfaces.append({"type": type_map[local], "vertices": np.round(mapped, 4).tolist(), "surface_id": f"{local}_{polygon_index}"})
    return surfaces, library.parse_reference_roofs(REFERENCE_GML, "DEBY_LOD2_4906982")


def sampled_normal_axes(mapped: np.ndarray, normals: np.ndarray, xyz: np.ndarray, mask: np.ndarray, reference_roofs: list[Any], *, cell_m: float = 2.0, maximum: int = 700, length_m: float = 1.5) -> list[dict]:
    index = np.flatnonzero(mask)
    if not len(index):
        return []
    cells = np.floor(xyz[index, :2] / cell_m).astype(np.int64)
    _, first = np.unique(cells, axis=0, return_index=True)
    index = index[np.sort(first)]
    if len(index) > maximum:
        index = index[np.linspace(0, len(index) - 1, maximum, dtype=np.int64)]
    vectors = np.column_stack((normals[index, 0], normals[index, 2], -normals[index, 1]))
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True).clip(1e-12)
    half = length_m / 2.0
    axes = np.stack((mapped[index] - half * vectors, mapped[index] + half * vectors), axis=1)
    from shapely.geometry import Point

    output = []
    for source_index, segment in zip(index, axes):
        point = Point(float(xyz[source_index, 0]), float(xyz[source_index, 1]))
        reference = min(reference_roofs, key=lambda item: item.polygon.distance(point))
        source_normal = normals[source_index] / max(float(np.linalg.norm(normals[source_index])), 1e-12)
        cosine = float(np.clip(abs(np.dot(source_normal, reference.normal())), 0.0, 1.0))
        output.append({"vertices": np.round(segment, 3).tolist(), "reference_angle_deg": round(float(np.degrees(np.arccos(cosine))), 3)})
    return output


def page_html() -> str:
    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>55-view E4 ALS normal ablation Roofer</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,sans-serif}*{box-sizing:border-box}body{margin:0;background:#071018;color:#e8f0f4;overflow:hidden}
#bar{position:fixed;z-index:2;top:0;left:0;right:0;display:flex;gap:14px;align-items:center;padding:12px 16px;background:#0b1822ee;border-bottom:1px solid #29404f}h1{font-size:16px;margin:0 10px 0 0}label{font-size:12px;color:#a9bdc8}select,button{background:#152936;color:#fff;border:1px solid #365365;border-radius:6px;padding:7px 9px}button{cursor:pointer}
#view{position:fixed;inset:58px 340px 0 0}.panel{position:fixed;z-index:2;right:0;top:58px;bottom:0;width:340px;padding:16px;overflow:auto;background:#0b1822e8;border-left:1px solid #29404f}.card{background:#112431;border:1px solid #29404f;border-radius:8px;padding:10px;margin-bottom:9px}.k{font-size:11px;color:#91a8b6}.v{font-size:18px;margin-top:3px}.note{font-size:12px;line-height:1.5;color:#b8c8d0}.legend span{display:block;margin:7px 0}.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px}.swatch{display:inline-block;width:14px;height:9px;margin-right:7px}
</style></head><body>
<div id="bar"><h1>DEBY_LOD2_4906982 · Roofer LoD2</h1><label>조건 <select id="arm"></select></label><label>checkpoint <select id="step"></select></label><label><input id="reference" type="checkbox" checked> reference LoD2</label><label><input id="solid" type="checkbox" checked> 예측 wall+ground</label><label><input id="evidence" type="checkbox"> 입력 points</label><label><input id="normals" type="checkbox"> 입력 normal 축</label><button id="reset">시점 초기화</button></div>
<div id="view"></div><aside class="panel"><div id="label" class="card"></div><div id="metrics"></div>
<div class="card legend"><div class="k">표시</div><span><i class="swatch" style="background:#7c8cff"></i>evaluation-only reference LoD2 solid</span><span><i class="swatch" style="background:#ffbd45"></i>Roofer 예측 roof</span><span><i class="swatch" style="background:#53c8e8"></i>Roofer 예측 wall</span><span><i class="swatch" style="background:#6d657d"></i>Roofer 예측 ground</span><span><i class="dot" style="background:#ff4fa3"></i>입력 class 6</span><span><i class="swatch" style="background:#78ff9a"></i>입력 normal 축(부호 무관)</span></div>
<p class="note">기본 화면은 reference LoD2와 Roofer가 생성한 전체 LoD2 solid를 동일하게 roof·wall·ground로 겹쳐 보여줍니다. 왼쪽 드래그는 회전, 오른쪽 또는 Shift+왼쪽 드래그는 위치 이동입니다. normal 축은 roof-like class-6에서 2m 격자당 최대 하나이며 부호를 해석하지 않습니다. LoD2 reference는 evaluation-only입니다. scientific_verdict=null.</p></aside>
<script type="module" src="./app.js"></script></body></html>"""


def app_js() -> str:
    return """import * as THREE from '../three.module.min.js';
const manifest=await (await fetch('./manifest.json')).json();
const armSel=document.querySelector('#arm'),stepSel=document.querySelector('#step');
for(const a of manifest.arms){const o=document.createElement('option');o.value=a.id;o.textContent=a.label;armSel.append(o)}
for(const s of manifest.steps){const o=document.createElement('option');o.value=s;o.textContent=s.toLocaleString();stepSel.append(o)}stepSel.value='20000';
const host=document.querySelector('#view'),scene=new THREE.Scene();scene.background=new THREE.Color(0x071018);
const camera=new THREE.PerspectiveCamera(44,1,.1,1000),renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.append(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xdff5ff,0x14202b,1.8));const sun=new THREE.DirectionalLight(0xffffff,2.1);sun.position.set(30,50,25);scene.add(sun);
const grid=new THREE.GridHelper(90,18,0x35566a,0x1a3241);scene.add(grid);let group=null,az=-.65,el=.35,dist=80,target=new THREE.Vector3(0,3,0),drag=false,pan=false,px=0,py=0;
function cam(){camera.position.set(target.x+dist*Math.cos(el)*Math.sin(az),target.y+dist*Math.sin(el),target.z+dist*Math.cos(el)*Math.cos(az));camera.lookAt(target)}
function resize(){const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}addEventListener('resize',resize);resize();cam();
renderer.domElement.oncontextmenu=e=>e.preventDefault();renderer.domElement.onpointerdown=e=>{drag=true;pan=e.button===1||e.button===2||e.shiftKey;px=e.clientX;py=e.clientY;renderer.domElement.setPointerCapture(e.pointerId)};renderer.domElement.onpointerup=()=>{drag=false;pan=false};renderer.domElement.onpointermove=e=>{if(!drag)return;const dx=e.clientX-px,dy=e.clientY-py;if(pan){const forward=target.clone().sub(camera.position).normalize(),right=new THREE.Vector3().crossVectors(forward,camera.up).normalize(),up=new THREE.Vector3().crossVectors(right,forward).normalize(),scale=dist*.0015;target.addScaledVector(right,-dx*scale).addScaledVector(up,dy*scale)}else{az-=dx*.008;el=Math.max(.08,Math.min(1.45,el+dy*.008))}px=e.clientX;py=e.clientY;cam()};renderer.domElement.onwheel=e=>{e.preventDefault();dist=Math.max(12,Math.min(180,dist*Math.exp(e.deltaY*.001)));cam()};
function dispose(){if(!group)return;scene.remove(group);group.traverse(o=>{o.geometry?.dispose();if(o.material){(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose())}})}
function points(values,color,size){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(values.flat(),3));return new THREE.Points(g,new THREE.PointsMaterial({color,size,sizeAttenuation:true,transparent:true,opacity:.82}))}
function normalAxes(values){const positions=[],colors=[];for(const axis of values){positions.push(...axis.vertices[0],...axis.vertices[1]);const a=axis.reference_angle_deg,c=a<=5?[.25,1,.45]:a<=15?[1,.82,.2]:[1,.25,.25];colors.push(...c,...c)}const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));return new THREE.LineSegments(g,new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.92}))}
function surface(face){const v=face.vertices;if(v.length<3)return null;const pos=[];for(let i=1;i<v.length-1;i++)pos.push(...v[0],...v[i],...v[i+1]);const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));g.computeVertexNormals();const ref=face.type.startsWith('Reference'),roof=face.type==='RoofSurface',wall=face.type==='WallSurface',ground=face.type==='GroundSurface';const root=new THREE.Group(),color=ref?0x7c8cff:roof?0xffbd45:wall?0x42d8ff:ground?0x76698d:0x65727a,m=ref?new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide,wireframe:true,transparent:true,opacity:.58,depthWrite:false}):new THREE.MeshStandardMaterial({color,side:THREE.DoubleSide,transparent:false,roughness:.72,metalness:.04});root.add(new THREE.Mesh(g,m));const outline=[...v,v[0]].flat(),lg=new THREE.BufferGeometry();lg.setAttribute('position',new THREE.Float32BufferAttribute(outline,3));root.add(new THREE.Line(lg,new THREE.LineBasicMaterial({color:ref?0xa8b0ff:roof?0xff7d16:wall?0x20b9e6:0xa395b8,transparent:true,opacity:ref?.9:1})));return root}
const fmt=(v,d=3)=>v==null?'—':Number(v).toFixed(d);function card(k,v){return `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`}
async function load(){dispose();const arm=armSel.value,step=Number(stepSel.value),data=await (await fetch(`./data/${arm}_${String(step).padStart(6,'0')}.json`)).json();group=new THREE.Group();group.name='case';if(document.querySelector('#reference').checked)for(const face of data.reference.surfaces){const mesh=surface(face);if(mesh)group.add(mesh)}if(document.querySelector('#evidence').checked){group.add(points(data.points.class6,0xff4fa3,.16));group.add(points(data.points.class2,0x9a744b,.11))}if(document.querySelector('#normals').checked)group.add(normalAxes(data.points.normal_axes));for(const face of data.roofer.surfaces){if(!document.querySelector('#solid').checked&&(face.type==='WallSurface'||face.type==='GroundSurface'))continue;const mesh=surface(face);if(mesh)group.add(mesh)}scene.add(group);document.querySelector('#label').innerHTML=`<div class="k">선택 조건</div><div class="v">${data.label}</div><div class="note">${step.toLocaleString()} updates · class6 ${data.counts.class6.toLocaleString()} · normal axes ${data.points.normal_axes.length} · predicted R/W/G ${data.counts.predicted_roof_faces}/${data.counts.predicted_wall_faces}/${data.counts.predicted_ground_faces}</div>`;
const m=data.metrics;document.querySelector('#metrics').innerHTML=card('Roofer output roof coverage',fmt(100*m.roofer_coverage,2)+'%')+card('Ground Z error vs reference',fmt(m.roofer_ground_z_error,2)+' m')+card('Exterior wall height',fmt(m.roofer_exterior_wall_height_median,2)+' m (reference '+fmt(m.reference_building_height,2)+' m)')+card('Roofer output/reference normal',fmt(m.roofer_reference_normal_median,2)+'°')+card('Input class6/reference normal',fmt(m.classified_normal_median,2)+'° (p95 '+fmt(m.classified_normal_p95,2)+'°)')+card('Input center roof coverage',fmt(100*m.classified_center_coverage,2)+'%');}
armSel.onchange=load;stepSel.onchange=load;document.querySelector('#reference').onchange=load;document.querySelector('#solid').onchange=load;document.querySelector('#evidence').onchange=load;document.querySelector('#normals').onchange=load;document.querySelector('#reset').onclick=()=>{az=-.65;el=.35;dist=80;target.set(0,3,0);cam()};
armSel.value='E4_ALS_PRIOR_ONLY';await load();renderer.setAnimationLoop(()=>renderer.render(scene,camera));
"""


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output")
    args = parser.parse_args()
    cfg = yaml.safe_load(CONFIG.read_text())
    viewer_root = Path(cfg["viewer_root"])
    output = Path(args.output) if args.output else viewer_root / cfg["slot_dir"]
    precondition = json.loads((TASK_ROOT / "control/viewer_root_precondition.json").read_text())
    for name, expected in precondition["fixed_file_sha256"].items():
        if sha256(viewer_root / name) != expected:
            raise RuntimeError(f"viewer root changed before add-only build: {name}")
    if output.exists() and any(output.iterdir()):
        existing = json.loads((output / "manifest.json").read_text())
        if existing.get("task_id") != TASK_ID:
            raise RuntimeError(f"viewer slot is owned by another task: {output}")
    (output / "data").mkdir(parents=True, exist_ok=True)
    footprint = shape(json.loads((TASK_ROOT / "control/shared_standard_footprint_4906982.geojson").read_text())["features"][0]["geometry"])
    center = np.asarray([footprint.centroid.x, footprint.centroid.y, 584.0])
    references, reference_roofs = reference_surfaces(center)
    reference_ground_z = float(np.median(np.concatenate([np.asarray(face["vertices"], dtype=np.float64)[:, 1] + center[2] for face in references if face["type"] == "ReferenceGround"])))
    reference_roof_z = float(np.median(np.concatenate([np.asarray(face["vertices"], dtype=np.float64)[:, 1] + center[2] for face in references if face["type"] == "ReferenceRoof"])))
    reference_building_height = reference_roof_z - reference_ground_z
    manifest_arms = []
    panels = []
    for visible_arm, (root, source_arm, label) in ARM_SOURCES.items():
        manifest_arms.append({"id": visible_arm, "label": label})
        metrics_doc = json.loads((root / "metrics.json").read_text())
        mvs_rows = load_rows(root / "mvs_surface_audit.json")
        lod2_rows = load_rows(root / "lod2_fused_evaluation.json")
        roofer_rows_path = root / ("lod2_evaluation_als_depth_only.json" if source_arm == "ALS_DEPTH_ONLY" else f"lod2_evaluation_{source_arm.lower()}.json")
        if source_arm == "FUSED_VIS_CONF" and root == TASK_ROOT:
            roofer_rows_path = FULL_E4_ROOT / "lod2_evaluation_fused_vis_conf.json"
        roofer_rows = load_rows(roofer_rows_path)
        for step in STEPS:
            work = root / f"arms/{source_arm}/R1/evaluation/step_{step:06d}/fusion"
            cloud = laspy.read(work / "classified_surface.laz")
            xyz = np.column_stack((cloud.x, cloud.y, cloud.z)).astype(np.float64)
            mapped = np.column_stack((xyz[:, 0] - center[0], xyz[:, 2] - center[2], -(xyz[:, 1] - center[1])))
            classes = np.asarray(cloud.classification)
            normals = np.column_stack((cloud["NormalX"], cloud["NormalY"], cloud["NormalZ"])).astype(np.float64)
            normal_z = normals[:, 2]
            rooflike_class6 = (classes == 6) & (np.abs(normal_z) >= 0.7)
            class6 = sample(mapped[classes == 6], 22000)
            class2 = sample(mapped[classes == 2], 7000)
            normal_axes = sampled_normal_axes(mapped, normals, xyz, rooflike_class6, reference_roofs)
            city_path = next((work / "roofer/output").glob("*.city.jsonl"))
            surfaces, attributes = city_surfaces(city_path, center)
            exterior_walls = [np.asarray(face["vertices"], dtype=np.float64) for face in surfaces if face["type"] == "WallSurface" and face.get("on_footprint_edge") is True]
            exterior_wall_heights = [float(np.ptp(vertices[:, 1])) for vertices in exterior_walls]
            mvs = select_row(mvs_rows, source_arm, step)
            lod2 = select_row(lod2_rows, source_arm, step)
            roofer = select_row(roofer_rows, source_arm, step)
            aggregate = metrics_doc["aggregates"][str(step)][source_arm]
            body = {
                "schema": "jointbuildgs.viewer.e4_normal_ablation_case.v1", "arm": visible_arm, "source_arm": source_arm,
                "label": label, "completed_updates": step, "center_epsg25832": center.tolist(),
                "points": {"class6": np.round(class6, 3).tolist(), "class2": np.round(class2, 3).tolist(), "normal_axes": normal_axes},
                "counts": {"all": int(len(xyz)), "class6": int((classes == 6).sum()), "rooflike_class6": int(rooflike_class6.sum()), "class2": int((classes == 2).sum()),
                           "predicted_roof_faces": sum(face["type"] == "RoofSurface" for face in surfaces), "predicted_wall_faces": sum(face["type"] == "WallSurface" for face in surfaces), "predicted_ground_faces": sum(face["type"] == "GroundSurface" for face in surfaces)},
                "reference": {"surfaces": references, "path": str(REFERENCE_GML), "evaluation_only": True, "z_shift_to_prediction_space_m": 45.7},
                "roofer": {"surfaces": surfaces, "attributes": attributes},
                "metrics": {
                    "roofer_coverage": roofer.get("roofer_roof_xy_coverage_fraction"), "roofer_fscore_0p5": roofer.get("roofer_surface_fscore_0p5m"),
                    "roofer_internal_rmse": roofer.get("roofer_internal_rmse"), "roofer_reference_normal_median": roofer.get("roofer_surface_normal_angle_deg_median"),
                    "roofer_surface_count": roofer.get("roofer_roof_surface_count"), "classified_grid_coverage": roofer.get("classified_grid_coverage_fraction"),
                    "classified_center_coverage": roofer.get("classified_center_grid_coverage_fraction"), "classified_normal_median": roofer.get("classified_normal_angle_deg_median"),
                    "classified_normal_p95": roofer.get("classified_normal_angle_deg_p95"),
                    "reference_ground_z": reference_ground_z, "reference_building_height": reference_building_height,
                    "roofer_ground_z": attributes.get("rf_h_ground"), "roofer_ground_z_error": None if attributes.get("rf_h_ground") is None else float(attributes["rf_h_ground"] - reference_ground_z),
                    "roofer_exterior_wall_height_median": None if not exterior_wall_heights else float(np.median(exterior_wall_heights)),
                    "roofer_exterior_wall_height_max": None if not exterior_wall_heights else float(np.max(exterior_wall_heights)),
                    "lod2_abs_dz_median": lod2.get("abs_dz_m_median"),
                    "lod2_normal_median": lod2.get("normal_angle_deg_median"), "mvs_p2plane_median": mvs.get("ordinary_point_to_plane_m_median"),
                    "gaussian_z_gt_650": int(aggregate["z_gt_650"]["mean"]),
                },
                "sources": {"classified_laz": str(work / "classified_surface.laz"), "cityjsonseq": str(city_path)}, "scientific_verdict": None,
            }
            target = output / "data" / f"{visible_arm}_{step:06d}.json"
            target.write_text(json.dumps(body, separators=(",", ":")) + "\n")
            if step == 20000:
                panels.append((visible_arm, label, xyz[classes == 6], surfaces, body["metrics"]))
    manifest = {"schema": "jointbuildgs.viewer.e4_normal_ablation.v1", "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982", "arms": manifest_arms, "steps": list(STEPS), "default": {"arm": "E4_ALS_PRIOR_ONLY", "step": 20000}, "scientific_verdict": None}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output / "index.html").write_text(page_html())
    (output / "app.js").write_text(app_js())

    figure, axes = plt.subplots(1, 3, figsize=(18, 6), constrained_layout=True)
    for axis, (_, label, points, surfaces, metrics) in zip(axes, panels):
        for face in references:
            vertices = np.asarray(face["vertices"]); axis.fill(vertices[:, 0] + center[0], -vertices[:, 2] + center[1], color="#7c8cff", alpha=.16); axis.plot(vertices[:, 0] + center[0], -vertices[:, 2] + center[1], color="#5967d8", linewidth=.8)
        subset = sample(points, 25000); axis.scatter(subset[:, 0], subset[:, 1], c=subset[:, 2], s=.25, cmap="viridis", alpha=.25, rasterized=True)
        for face in surfaces:
            if face["type"] != "RoofSurface": continue
            vertices = np.asarray(face["vertices"]); axis.plot(vertices[:, 0] + center[0], -vertices[:, 2] + center[1], color="#ff8c24", linewidth=1.2)
        axis.set_aspect("equal"); axis.set_title(f"{label}\ncoverage={100*metrics['roofer_coverage']:.2f}% · RMSE={metrics['roofer_internal_rmse']:.2f}m"); axis.set_xlabel("EPSG:25832 X"); axis.set_ylabel("Y")
    image = TASK_ROOT / "representative_images/roofer_3arm_20k_top.png"; image.parent.mkdir(parents=True, exist_ok=True); figure.savefig(image, dpi=160); plt.close(figure)
    fixed_after = {name: sha256(viewer_root / name) for name in precondition["fixed_file_sha256"]}
    if fixed_after != precondition["fixed_file_sha256"]:
        raise RuntimeError("viewer root state changed during slot build")
    receipt = {"schema": "jointbuildgs.viewer.add_only_slot_receipt.v1", "slot_id": cfg["slot_dir"], "slot_path": str(output), "relative_url": f"{cfg['slot_dir']}/index.html", "root_fixed_sha256_before_after_equal": True, "source_artifacts_modified": False, "files": {str(path.relative_to(output)): sha256(path) for path in sorted(output.rglob("*")) if path.is_file()}, "scientific_verdict": None}
    (TASK_ROOT / "viewer_slot.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"slot": str(output), "cases": len(ARM_SOURCES) * len(STEPS), "root_preserved": True}, indent=2))


if __name__ == "__main__":
    main()
