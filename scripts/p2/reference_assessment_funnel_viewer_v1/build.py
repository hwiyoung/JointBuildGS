#!/usr/bin/env python3
"""Build a read-only viewer for the current-reference assessment funnel."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_REPO = Path("/workspace/JointBuildGS")
DEFAULT_ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")
CONFIG_RELATIVE = Path("configs/p2/reference_assessment_funnel_viewer_v1/viewer.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(root: Path, spec: Mapping[str, Any]) -> Path:
    path = root / str(spec["path"])
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or invalid input: {path}")
    if path.stat().st_size != int(spec["bytes"]) or sha256(path) != spec["sha256"]:
        raise RuntimeError(f"bound input differs: {path}")
    return path


def parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def number(value: str) -> float | None:
    return float(value) if value.strip() else None


def classify(row: Mapping[str, Any]) -> tuple[list[str], str]:
    reference_count = int(row["current_uas_reference_cell_count"])
    temporal_status = str(row["temporal_reference_status"])
    stages = ["ALL_199"]
    if reference_count > 0:
        stages.append("CURRENT_REFERENCE_PRESENT")
    if temporal_status in {"UNCHANGED_CONFIDENT", "TEMPORAL_CHANGE_SUSPECTED"}:
        stages.append("TEMPORAL_STATUS_RESOLVED")
    if temporal_status == "UNCHANGED_CONFIDENT":
        stages.append("UNCHANGED_CONFIDENT")
    if bool(row["current_uas_reference_eligible"]):
        stages.append("ASSESSABLE_UNCHANGED")

    if reference_count == 0:
        bucket = "REFERENCE_ABSENT"
    elif temporal_status == "REFERENCE_ID_ALIGNMENT_UNCERTAIN":
        bucket = "REFERENCE_ALIGNMENT_UNRESOLVED"
    elif temporal_status == "TEMPORAL_CHANGE_SUSPECTED":
        bucket = "CHANGED_OUTSIDE_UNCHANGED_COHORT"
    elif not bool(row["fully_inside_roofer_aoi"]):
        bucket = "AOI_REPLAY_REQUIRED"
    elif bool(row["current_uas_reference_eligible"]):
        bucket = "ASSESSABLE_UNCHANGED"
    else:
        bucket = "OTHER_CONTRACT_GAP"
    return stages, bucket


def polygon_rings(geometry: Mapping[str, Any]) -> Iterable[list[list[float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "Polygon":
        yield from coordinates
    elif kind == "MultiPolygon":
        for polygon in coordinates:
            yield from polygon
    else:
        raise RuntimeError(f"unsupported footprint geometry: {kind}")


def svg_path(geometry: Mapping[str, Any], bounds: tuple[float, float, float, float]) -> str:
    min_x, min_y, max_x, max_y = bounds
    pad = 18.0
    width, height = 1000.0 - 2 * pad, 700.0 - 2 * pad
    scale = min(width / (max_x - min_x), height / (max_y - min_y))
    used_w, used_h = (max_x - min_x) * scale, (max_y - min_y) * scale
    offset_x, offset_y = (1000.0 - used_w) / 2, (700.0 - used_h) / 2
    parts: list[str] = []
    for ring in polygon_rings(geometry):
        points = [
            (offset_x + (float(x) - min_x) * scale, offset_y + (max_y - float(y)) * scale)
            for x, y, *_ in ring
        ]
        if not points:
            continue
        parts.append("M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points) + " Z")
    return " ".join(parts)


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_data(config: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    census_path = verify(artifact_root, config["inputs"]["census"])
    temporal_path = verify(artifact_root, config["inputs"]["temporal_diagnostics"])
    footprints_path = verify(artifact_root, config["inputs"]["shared_footprints"])
    with census_path.open(encoding="utf-8", newline="") as stream:
        census = list(csv.DictReader(stream))
    temporal = {row["building_id"]: row for row in jsonl(temporal_path)}
    footprint_collection = json.loads(footprints_path.read_text(encoding="utf-8"))
    footprints = {feature["properties"]["stable_id"]: feature for feature in footprint_collection["features"]}
    ids = {row["stable_id"] for row in census}
    if len(census) != 199 or ids != set(temporal) or ids != set(footprints):
        raise RuntimeError("census, temporal diagnostics, and footprints do not bind to the same 199 IDs")

    all_points = [point for feature in footprints.values() for ring in polygon_rings(feature["geometry"]) for point in ring]
    xs, ys = [float(point[0]) for point in all_points], [float(point[1]) for point in all_points]
    bounds = (min(xs), min(ys), max(xs), max(ys))
    output_rows: list[dict[str, Any]] = []
    for raw in census:
        stable_id = raw["stable_id"]
        row = {
            "population_index": int(raw["population_index"]),
            "stable_id": stable_id,
            "fully_inside_roofer_aoi": parse_bool(raw["fully_inside_roofer_aoi"]),
            "current_uas_reference_cell_count": int(raw["current_uas_reference_cell_count"]),
            "current_uas_reference_eligible": parse_bool(raw["current_uas_reference_eligible"]),
            "temporal_reference_status": raw["temporal_reference_status"],
            "no_clip_reason": raw["no_clip_reason"],
            "current_uas_accuracy_candidate": None if not raw["current_uas_accuracy_candidate"] else parse_bool(raw["current_uas_accuracy_candidate"]),
            "current_uas_vertical_coverage": number(raw["current_uas_vertical_coverage"]),
            "current_uas_height_mae_m": number(raw["current_uas_height_mae_m"]),
            "current_uas_rmsz_m": number(raw["current_uas_rmsz_m"]),
            "current_uas_rmsxy_m": number(raw["current_uas_rmsxy_m"]),
            "current_uas_surface_rmse_m": number(raw["current_uas_surface_rmse_m"]),
            "current_uas_surface_p95_m": number(raw["current_uas_surface_p95_m"]),
            "improvement_flags": raw["improvement_flags"].split(";") if raw["improvement_flags"] else [],
            "current_rgb": temporal[stable_id]["current_rgb"],
            "lod2_interpolated_cell_count": int(temporal[stable_id]["lod2_interpolated_cell_count"]),
            "temporal_median_abs_z_m": temporal[stable_id]["median_abs_z_m"],
            "temporal_p95_abs_z_m": temporal[stable_id]["p95_abs_z_m"],
            "svg_path": svg_path(footprints[stable_id]["geometry"], bounds),
        }
        row["stages"], row["exclusive_bucket"] = classify(row)
        output_rows.append(row)
    output_rows.sort(key=lambda row: row["population_index"])

    stage_counts = Counter(stage for row in output_rows for stage in row["stages"])
    bucket_counts = Counter(row["exclusive_bucket"] for row in output_rows)
    if dict(stage_counts) != config["expected_counts"]["stages"]:
        raise RuntimeError(f"stage counts differ: {dict(stage_counts)}")
    if dict(bucket_counts) != config["expected_counts"]["exclusive_buckets"]:
        raise RuntimeError(f"exclusive bucket counts differ: {dict(bucket_counts)}")
    return {
        "schema": "jointbuildgs.p2.reference_assessment_funnel_viewer.data.v1",
        "task_id": config["task_id"],
        "stages": [
            {"id": "ALL_199", "label": "전체 대상", "count": 199, "note": "U_target 전체"},
            {"id": "CURRENT_REFERENCE_PRESENT", "label": "current-UAS cell 존재", "count": 79, "note": "1개 이상 배정"},
            {"id": "TEMPORAL_STATUS_RESOLVED", "label": "시간 상태 판별", "count": 53, "note": "unchanged 또는 change suspected"},
            {"id": "UNCHANGED_CONFIDENT", "label": "변화 없음 후보", "count": 47, "note": "임시 temporal threshold"},
            {"id": "ASSESSABLE_UNCHANGED", "label": "G4 계산 가능", "count": 40, "note": "AOI·cell·RoofSurface 계약 충족"},
        ],
        "exclusive_buckets": [
            {"id": "REFERENCE_ABSENT", "label": "current reference 없음", "count": 120},
            {"id": "REFERENCE_ALIGNMENT_UNRESOLVED", "label": "reference/ID 정합 미해결", "count": 26},
            {"id": "CHANGED_OUTSIDE_UNCHANGED_COHORT", "label": "변화 의심", "count": 6},
            {"id": "AOI_REPLAY_REQUIRED", "label": "AOI 재처리 필요", "count": 7},
            {"id": "ASSESSABLE_UNCHANGED", "label": "평가 가능·변화 없음", "count": 40},
        ],
        "buildings": output_rows,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }


INDEX_HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Current-reference assessment funnel</title>
<style>
:root{color-scheme:dark;--bg:#071018;--panel:#0d1823;--line:#294052;--text:#e8f0f6;--muted:#9db0bf;--active:#51a9ff;--absent:#667482;--uncertain:#e6a23c;--changed:#e96788;--aoi:#6d8ef2;--ok:#42b983}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px system-ui,sans-serif}button,input{font:inherit}header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap}h1{font-size:18px;margin:0;font-weight:600}header span{color:var(--muted)}main{padding:14px;display:grid;gap:12px}.mode,.steps,.buckets{display:flex;gap:8px;flex-wrap:wrap}.mode button,.steps button,.buckets button,.building{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:7px;padding:8px 10px;cursor:pointer}.mode button.active,.steps button.active,.buckets button.active{outline:2px solid var(--active);outline-offset:1px}.steps button{min-width:150px;text-align:left}.steps small,.buckets small{display:block;color:var(--muted);margin-top:3px}.arrow{align-self:center;color:var(--muted)}.workspace{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(290px,.8fr);gap:12px;min-height:560px}.mapwrap,.side{border:1px solid var(--line);background:var(--panel);border-radius:9px;overflow:hidden}.maphead{padding:10px 12px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px}.maphead strong{font-weight:600}.maphead span{color:var(--muted)}svg{display:block;width:100%;height:auto;min-height:520px;background:#09131d}.footprint{stroke:#dbe8f2;stroke-width:.7;vector-effect:non-scaling-stroke;cursor:pointer;transition:opacity .12s}.footprint.dim{opacity:.08}.footprint.selected{stroke:#fff;stroke-width:3}.side{display:grid;grid-template-rows:auto auto minmax(180px,1fr);min-height:0}.detail{padding:12px;border-bottom:1px solid var(--line);min-height:195px}.detail h2{font-size:16px;margin:0 0 9px}.detail dl{display:grid;grid-template-columns:125px 1fr;gap:5px 9px;margin:0}.detail dt{color:var(--muted)}.detail dd{margin:0;overflow-wrap:anywhere}.search{padding:10px;border-bottom:1px solid var(--line)}.search input{width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;background:#071018;color:var(--text)}.list{overflow:auto;padding:8px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;gap:6px}.building{text-align:left;padding:7px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.building.active{outline:2px solid var(--active)}footer{color:var(--muted);padding:2px 4px}.legend{display:flex;gap:12px;flex-wrap:wrap}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}@media(max-width:900px){.workspace{grid-template-columns:1fr}.side{min-height:620px}.steps .arrow{display:none}}@media(max-width:520px){.steps button,.buckets button{width:100%}.list{grid-template-columns:1fr}.detail dl{grid-template-columns:105px 1fr}}
</style></head><body>
<header><h1>Current-reference assessment funnel</h1><span>동결 artifact 진단 · official_PASS_usable=null · scientific_verdict=null</span></header>
<main>
  <nav class="mode"><button id="mode-stage" class="active">누적 단계</button><button id="mode-bucket">제외 사유</button></nav>
  <section id="controls" class="steps"></section>
  <section class="workspace">
    <div class="mapwrap"><div class="maphead"><strong id="filter-title"></strong><span id="filter-count"></span></div><svg id="map" viewBox="0 0 1000 700" role="img" aria-label="199개 건물 footprint 분포"></svg></div>
    <aside class="side"><div id="detail" class="detail"></div><div class="search"><input id="search" type="search" placeholder="건물 ID 검색"></div><div id="list" class="list"></div></aside>
  </section>
  <div class="legend"><span><i style="background:var(--absent)"></i>reference 없음</span><span><i style="background:var(--uncertain)"></i>정합 미해결</span><span><i style="background:var(--changed)"></i>변화 의심</span><span><i style="background:var(--aoi)"></i>AOI 재처리</span><span><i style="background:var(--ok)"></i>평가 가능</span></div>
  <footer>변화 의심 6동은 정확도 실패가 아니라 unchanged-only cohort 밖의 건물이다.</footer>
</main>
<script type="module">
const data=await (await fetch('viewer_data.json',{cache:'no-store'})).json();
const colors={REFERENCE_ABSENT:'var(--absent)',REFERENCE_ALIGNMENT_UNRESOLVED:'var(--uncertain)',CHANGED_OUTSIDE_UNCHANGED_COHORT:'var(--changed)',AOI_REPLAY_REQUIRED:'var(--aoi)',ASSESSABLE_UNCHANGED:'var(--ok)'};
let mode='stage',filter='ALL_199',selected=null,query='';
const controls=document.getElementById('controls'),map=document.getElementById('map'),list=document.getElementById('list'),detail=document.getElementById('detail');
const match=row=>mode==='stage'?row.stages.includes(filter):row.exclusive_bucket===filter;
const fmt=value=>value===null||value===undefined?'—':typeof value==='number'?value.toFixed(3):String(value);
function select(id){selected=id;render();}
function renderControls(){const defs=mode==='stage'?data.stages:data.exclusive_buckets;controls.className=mode==='stage'?'steps':'buckets';controls.innerHTML='';defs.forEach((def,index)=>{if(mode==='stage'&&index)controls.insertAdjacentHTML('beforeend','<span class="arrow">→</span>');const b=document.createElement('button');b.className=def.id===filter?'active':'';b.innerHTML=`<strong>${def.count}동 · ${def.label}</strong><small>${def.note||def.id}</small>`;b.onclick=()=>{filter=def.id;selected=null;render()};controls.appendChild(b)});}
function renderMap(){map.innerHTML='';for(const row of data.buildings){const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',row.svg_path);p.setAttribute('fill',colors[row.exclusive_bucket]||'var(--absent)');p.setAttribute('fill-rule','evenodd');p.setAttribute('class','footprint'+(match(row)?'':' dim')+(selected===row.stable_id?' selected':''));p.setAttribute('aria-label',row.stable_id);p.onclick=()=>select(row.stable_id);map.appendChild(p)}}
function renderList(){const rows=data.buildings.filter(row=>match(row)&&row.stable_id.toLowerCase().includes(query.toLowerCase()));list.innerHTML='';for(const row of rows){const b=document.createElement('button');b.className='building'+(selected===row.stable_id?' active':'');b.textContent=row.stable_id.replace('DEBY_LOD2_','');b.title=row.stable_id;b.onclick=()=>select(row.stable_id);list.appendChild(b)}}
function renderDetail(){const row=data.buildings.find(item=>item.stable_id===selected);if(!row){detail.innerHTML='<h2>건물을 선택하세요</h2><p>지도 또는 오른쪽 ID 목록을 클릭하면 단계 판정 근거와 현재 진단값을 확인할 수 있습니다.</p>';return}detail.innerHTML=`<h2>${row.stable_id}</h2><dl><dt>제외/평가 상태</dt><dd>${row.exclusive_bucket}</dd><dt>current-UAS cells</dt><dd>${row.current_uas_reference_cell_count}</dd><dt>LoD2 대응 cells</dt><dd>${row.lod2_interpolated_cell_count}</dd><dt>temporal 상태</dt><dd>${row.temporal_reference_status}</dd><dt>temporal median/p95</dt><dd>${fmt(row.temporal_median_abs_z_m)} / ${fmt(row.temporal_p95_abs_z_m)} m</dd><dt>AOI 내부</dt><dd>${row.fully_inside_roofer_aoi?'yes':'no'}</dd><dt>Roofer no-clip</dt><dd>${row.no_clip_reason}</dd><dt>G4 candidate</dt><dd>${fmt(row.current_uas_accuracy_candidate)}</dd><dt>surface RMSE / p95</dt><dd>${fmt(row.current_uas_surface_rmse_m)} / ${fmt(row.current_uas_surface_p95_m)} m</dd></dl>`}
function render(){renderControls();renderMap();renderList();renderDetail();const def=(mode==='stage'?data.stages:data.exclusive_buckets).find(x=>x.id===filter);document.getElementById('filter-title').textContent=def.label;document.getElementById('filter-count').textContent=`${data.buildings.filter(match).length}동`;document.getElementById('mode-stage').classList.toggle('active',mode==='stage');document.getElementById('mode-bucket').classList.toggle('active',mode==='bucket')}
document.getElementById('mode-stage').onclick=()=>{mode='stage';filter='ALL_199';selected=null;render()};document.getElementById('mode-bucket').onclick=()=>{mode='bucket';filter='REFERENCE_ABSENT';selected=null;render()};document.getElementById('search').oninput=event=>{query=event.target.value;renderList()};render();
</script></body></html>
'''


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config_path = args.repo_root / CONFIG_RELATIVE
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_root = args.output or args.artifact_root / config["output_relative_root"]
    if output_root.exists():
        raise RuntimeError(f"add-once output already exists: {output_root}")
    viewer = output_root / "viewer"
    data = build_data(config, args.artifact_root)
    atomic_write(viewer / "viewer_data.json", (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
    atomic_write(viewer / "index.html", INDEX_HTML.encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.reference_assessment_funnel_viewer.receipt.v1",
        "task_id": config["task_id"],
        "inputs": config["inputs"],
        "outputs": {
            name: {"path": f"viewer/{name}", "bytes": (viewer / name).stat().st_size, "sha256": sha256(viewer / name)}
            for name in ("index.html", "viewer_data.json")
        },
        "stage_counts": config["expected_counts"]["stages"],
        "exclusive_bucket_counts": config["expected_counts"]["exclusive_buckets"],
        "source_role": config["source_role"],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_write(output_root / "receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"output": str(output_root), "viewer": str(viewer), "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
