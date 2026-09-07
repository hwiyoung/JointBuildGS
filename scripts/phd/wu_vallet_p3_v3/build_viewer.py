"""Forensic photo and point viewer of preserved and corrected Wu--Vallet updates.

Counts and downloads retain every native point. The browser uses an explicitly
declared deterministic DISPLAY_ONLY subset, always indexed into the exact input.
This script never changes labels, performs fusion, or infers a scientific verdict.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

import numpy as np


LABELS = ["consistent", "changed", "single", "unassessed", "filtered"]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    with Path(path).open("x") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def build_forensics(cfg, run, output, xyz, common, copy, binary):
    """Copy only declared evidence and bind each photo pixel to its native point."""
    root = Path(cfg["forensics_root"])
    receipt = read(root / "receipt.json")
    if receipt.get("scientific_verdict", "missing") is not None:
        raise ValueError("Forensic evidence requires a null scientific verdict")
    for relative, expected_hash in receipt.get("output_hashes", {}).items():
        if sha(root / relative) != expected_hash:
            raise ValueError(f"Forensic receipt hash mismatch: {relative}")
    evidence_path = root / receipt["evidence_npz"]
    evidence = np.load(evidence_path, allow_pickle=False)
    n = len(xyz["new"])
    pixels = np.asarray(evidence["pixel_xy"], dtype=np.float64)
    distance = np.asarray(evidence["new_reference_distance_m"], dtype=np.float64)
    if pixels.shape != (n, 2) or distance.shape != (n,) or not np.isfinite(pixels).all() or not np.isfinite(distance).all():
        raise ValueError("Photo evidence must preserve full native new point order")
    photo = dict(receipt["photo"])
    if np.any(pixels < 0) or np.any(pixels[:, 0] >= photo["width"]) or np.any(pixels[:, 1] >= photo["height"]):
        raise ValueError("Projected master pixels are outside the actual image")
    depth_shape = receipt.get("depth_shape", [741, 1024])
    pixel_id = np.asarray(common["new_pixel_id"], dtype=np.int64)
    expected_pixels = np.c_[pixel_id % depth_shape[1], pixel_id // depth_shape[1]] * np.array([photo["width"] / depth_shape[1], photo["height"] / depth_shape[0]])
    if not np.allclose(pixels, expected_pixels, rtol=0, atol=1e-4):
        raise ValueError("Photo pixels do not match native depth pixel provenance")
    if "new_xyz" in evidence and not np.allclose(evidence["new_xyz"], xyz["new"], rtol=0, atol=1e-7):
        raise ValueError("Forensic XYZ and update native input differ")
    baseline = np.load(run / cfg["baseline_arm"] / "updated_points.npz", allow_pickle=False)
    original_keep = np.asarray(evidence["original_keep"], dtype=bool)
    if not np.array_equal(original_keep, baseline["new_keep_mask"]):
        raise ValueError("Forensic original membership must match the named v2 comparator")
    copy(root / "receipt.json", "receipts/forensics.json")
    copy(evidence_path, "downloads/forensic_evidence.npz")
    photo["path"] = copy(root / photo["path"], "photos/master_133.jpg")
    points = read(root / receipt["points_json"])
    if isinstance(points, dict):
        points = points.get("points", points.get("records", []))
    copy(root / receipt["points_json"], "receipts/representative_points.json")
    rois = receipt.get("rois", [])
    for roi in rois:
        box = np.asarray(roi["bbox_xyxy"], dtype=float)
        if box.shape != (4,) or not (0 <= box[0] < box[2] <= photo["width"] and 0 <= box[1] < box[3] <= photo["height"]):
            raise ValueError("Invalid native image ROI")
        index = int(roi["representative_new_index"])
        if index < 0 or index >= n:
            raise ValueError("Invalid representative native point index")
    figures = []
    for figure in receipt.get("figures", []):
        entry = dict(figure)
        entry["path"] = copy(root / figure["path"], "figures/forensic_" + Path(figure["path"]).name)
        figures.append(entry)
    result = {"photo": photo, "rois": rois, "points": points, "figures": figures,
            "baseline_arm": cfg["baseline_arm"], "default_arm": cfg["default_arm"],
            "distance_threshold_m": float(cfg["large_reference_distance_m"]),
            "native_count": n, "depth_shape": depth_shape,
            "pixels": binary(pixels, "forensics/pixels.bin", "<f4"),
            "xyz": binary(xyz["new"], "forensics/xyz.bin", "<f4"),
            "distance": binary(distance, "forensics/reference_distance.bin", "<f4"),
            "baseline_keep": binary(original_keep, "forensics/baseline_keep.bin", "u1"),
            "pixel_ids": binary(pixel_id, "forensics/native_pixel_ids.bin", "<i8"),
            "diagnosis_role": "EVALUATION_ONLY_not_used_to_select_or_filter_points",
            "validation": "PASS_native_depth_pixel_to_master_photo_and_baseline_membership"}
    for key, dtype in (("sor_survives", "u1"), ("component_id", "<i4"), ("component_area_m2", "<f4")):
        if key in evidence:
            value = np.asarray(evidence[key])
            if value.shape != (n,) or not np.isfinite(value).all():
                raise ValueError(f"Invalid native-order diagnostic: {key}")
            result[key] = binary(value, f"forensics/{key}.bin", dtype)
    return result


FORENSIC_CARD = r'''<section class="card" id="photo-card"><h2>실제 현재 사진에서 갱신점 확인</h2><p class="muted">촬영 영상 133의 보정된 원본 사진입니다. 색점은 해당 깊이 픽셀에서 생성한 영상점의 위치이며, 깊이의 정확성을 사진 한 장으로 입증하지 않습니다. 아래 점을 누르면 같은 원점의 좌표·선택 상태를 읽을 수 있습니다.</p><div class="controls"><label class="control"><span>비교 조건</span><select id="photo-arm-select"></select></label><label class="control"><span>사진 범위</span><select id="roi-select"><option value="full">전체 사진</option></select></label><label class="control"><span>사진에 표시</span><select id="photo-mode"><option value="admitted">현재 조건에서 추가한 영상점</option><option value="removed">v2에서 추가했으나 현재 조건에서 제외한 점</option><option value="large">추가점 중 UAS 거리 차이 2 m 초과 · 평가 전용</option><option value="all">모든 영상 원점</option><option value="none">사진만</option></select></label></div><div class="photo-layout"><div class="photo-stage"><canvas id="photo-canvas" aria-label="현재 실제 사진과 원점 픽셀 오버레이"></canvas></div><aside><p class="small" id="photo-caption"></p><p class="small muted">청록색: 현재 추가점 · 자홍색: v2 대비 제외점 · 주황색: 추가점 중 UAS와 2 m 초과 차이(평가 전용). 오버레이는 전체 원점에서 선택하며 표시용 3D 샘플링을 사용하지 않습니다.</p><div id="point-detail" class="mono">ROI 또는 사진의 점을 선택하세요.</div><p class="small muted" id="photo-count"></p><p class="small muted">UAS 헤더 EPSG:32632 / 작업 표기 EPSG:25832. 재투영·정합 없이 수치 좌표를 비교한 거리입니다. 실제 변화·가림·센서 차이도 거리 차이를 만들 수 있습니다.</p><a href="photos/master_133.jpg">실제 원본 사진</a> · <a href="receipts/forensics.json">사진·픽셀 출처 기록</a></aside></div></section><section class="card" id="forensic-figures" hidden><h2>같은 원점의 사진·지도·단면</h2><div class="controls"><label class="control"><span>진단 그림</span><select id="figure-select"></select></label></div><img id="forensic-figure" alt="현재 선택한 진단 그림" style="width:100%;height:auto;display:block"><p id="figure-caption" class="small muted"></p></section><style>.photo-layout{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:18px}.photo-stage{background:#16222c;border:1px solid var(--border);border-radius:8px;overflow:hidden;min-width:0;height:590px}.photo-stage canvas{width:100%;height:100%;display:block;cursor:crosshair}#point-detail{background:#f1f5f7;padding:12px;border-radius:8px;min-height:150px}@media(max-width:900px){.photo-layout{grid-template-columns:1fr}.photo-stage{height:390px}}</style>'''


FORENSIC_JS = r'''
function imageLoaded(path){return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(Error('Photo failed: '+path));img.src=path;});}
async function loadForensics(){const f=d.forensics;forensic={pixels:await binary(f.pixels,Float32Array),xyz:await binary(f.xyz,Float32Array),distance:await binary(f.distance,Float32Array),baselineKeep:await binary(f.baseline_keep,Uint8Array),pixelIds:await binary(f.pixel_ids,BigInt64Array),oldDisplayIds:await binary(d.sources.old.display_indices,BigInt64Array),newDisplayIds:await binary(d.sources.new.display_indices,BigInt64Array),sectionIds:{old:{},new:{}}};for(const side of ['old','new'])for(const s of ['x','y'])forensic.sectionIds[side][s]=await binary(d.sources[side].sections[s].indices,BigInt64Array);if(f.sor_survives)forensic.sor=await binary(f.sor_survives,Uint8Array);if(f.component_id)forensic.component=await binary(f.component_id,Int32Array);if(f.component_area_m2)forensic.area=await binary(f.component_area_m2,Float32Array);photoImage=await imageLoaded(f.photo.path);if(photoImage.naturalWidth!==f.photo.width||photoImage.naturalHeight!==f.photo.height)throw Error('Native photo dimensions differ from receipt');for(const roi of f.rois){const opt=document.createElement('option');opt.value=roi.id;opt.textContent=roi.label;$('roi-select').append(opt);}$('roi-select').onchange=()=>{photoROI=$('roi-select').value;const roi=f.rois.find(r=>r.id===photoROI);selectedPoint=roi?roi.representative_new_index:null;drawPhoto();showSelectedPoint();};$('photo-mode').onchange=()=>{photoMode=$('photo-mode').value;drawPhoto();};$('photo-canvas').onclick=selectPhotoPoint;if(f.figures.length){$('forensic-figures').hidden=false;for(const fig of f.figures){const opt=document.createElement('option');opt.value=fig.id;opt.textContent=fig.label;$('figure-select').append(opt);}const updateFigure=()=>{const fig=f.figures.find(x=>x.id===$('figure-select').value);$('forensic-figure').src=fig.path;$('figure-caption').textContent=fig.caption??fig.label;};$('figure-select').onchange=updateFigure;updateFigure();}window.__WV_QA.photoLoaded=true;window.__WV_QA.nativePhoto={width:photoImage.naturalWidth,height:photoImage.naturalHeight,imageId:f.photo.image_id};}
function photoIncluded(i){if(photoMode==='none')return false;if(photoMode==='all')return true;if(photoMode==='removed')return forensic.baselineKeep[i]===1&&active.fullNewKeep[i]===0;if(photoMode==='large')return active.fullNewKeep[i]===1&&forensic.distance[i]>d.forensics.distance_threshold_m;return active.fullNewKeep[i]===1;}
function drawPhoto(){if(!photoImage||!active)return;const canvas=$('photo-canvas'),w=canvas.parentElement.clientWidth,h=canvas.parentElement.clientHeight,ratio=Math.min(devicePixelRatio,2);canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#16222c';ctx.fillRect(0,0,w,h);const roi=d.forensics.rois.find(r=>r.id===photoROI),box=roi?.bbox_xyxy??[0,0,d.forensics.photo.width,d.forensics.photo.height],bw=box[2]-box[0],bh=box[3]-box[1],scale=Math.min(w/bw,h/bh),ox=(w-bw*scale)/2,oy=(h-bh*scale)/2;photoTransform={box,scale,ox,oy,w,h};ctx.drawImage(photoImage,box[0],box[1],bw,bh,ox,oy,bw*scale,bh*scale);ctx.save();ctx.beginPath();ctx.rect(ox,oy,bw*scale,bh*scale);ctx.clip();let n=0,large=0;ctx.globalAlpha=.8;for(let i=0;i<d.forensics.native_count;i++){if(!photoIncluded(i))continue;const x=forensic.pixels[i*2],y=forensic.pixels[i*2+1];if(x<box[0]||x>=box[2]||y<box[1]||y>=box[3])continue;const removed=forensic.baselineKeep[i]===1&&active.fullNewKeep[i]===0,far=forensic.distance[i]>d.forensics.distance_threshold_m;ctx.fillStyle=removed?'#ed62cb':far?'#ff9c42':'#42dec5';const r=photoROI==='full'?.8:1.45;ctx.fillRect(ox+(x-box[0])*scale-r,oy+(y-box[1])*scale-r,r*2,r*2);n++;if(far)large++;}ctx.globalAlpha=1;if(selectedPoint!==null){const x=ox+(forensic.pixels[selectedPoint*2]-box[0])*scale,y=oy+(forensic.pixels[selectedPoint*2+1]-box[1])*scale;ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,8,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#172d3d';ctx.fillRect(x+10,y-11,106,21);ctx.fillStyle='#fff';ctx.font='12px system-ui';ctx.fillText('원점 '+selectedPoint,x+14,y+4);}ctx.restore();$('photo-caption').textContent=(roi?.caption??'전체 원본 사진. ROI는 사후 진단 사례를 찾기 위한 범위이며 처리나 매개변수 선택에 사용하지 않았습니다.')+' · 실행 조건: '+current.name;$('photo-count').textContent=`현재 범위 표시 ${count(n)}점 / 그중 UAS와 2 m 초과 차이 ${count(large)}점. 픽셀은 원래 깊이 격자에서 사진 크기로 정확하게 대응합니다.`;window.__WV_QA.photo={roi:photoROI,mode:photoMode,points:n,largeDistancePoints:large,box,selectedPoint,arm:current.name};showSelectedPoint();}
function showSelectedPoint(){if(selectedPoint===null||!active)return;const i=selectedPoint,record={new_native_index:i,depth_pixel_id:Number(forensic.pixelIds[i]),master_pixel_xy:[forensic.pixels[2*i],forensic.pixels[2*i+1]].map(x=>Number(x.toFixed(3))),xyz_scene_local_m:Array.from(forensic.xyz.slice(i*3,i*3+3)).map(x=>Number(x.toFixed(4))),v2_added:forensic.baselineKeep[i]===1,selected_arm_added:active.fullNewKeep[i]===1,selected_arm_label:labelNames[d.labels[active.fullNewLabels[i]]],reference_distance_m:Number(forensic.distance[i].toFixed(4)),reference_role:'평가 전용; 변화 또는 오류의 확정 라벨 아님'};const note=d.forensics.points.find(x=>x.new_native_index===i);if(note?.reason)record.case_note=note.reason;if(note?.nearest_reference_xyz)record.nearest_reference_xyz=note.nearest_reference_xyz;if(forensic.component){record.largest_incident_changed_component_id=forensic.component[i];record.largest_incident_changed_component_area_m2=Number(forensic.area[i].toFixed(4));}if(forensic.sor)record.spatial_outlier_diagnostic_survives=forensic.sor[i]===1;$('point-detail').textContent=JSON.stringify(record,null,2);window.__WV_QA.selectedPoint=record;if(scene&&renderer){if(pointMarker){scene.remove(pointMarker);pointMarker.geometry.dispose();pointMarker.material.dispose();}const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(forensic.xyz.slice(i*3,i*3+3),3));pointMarker=new THREE.Points(geo,new THREE.PointsMaterial({size:12,sizeAttenuation:false,color:'#a8177b',depthTest:false}));pointMarker.renderOrder=10;scene.add(pointMarker);draw();}}
function selectPhotoPoint(event){if(!active||!photoTransform||photoMode==='none')return;const rect=$('photo-canvas').getBoundingClientRect(),{box,scale,ox,oy}=photoTransform,x=(event.clientX-rect.left-ox)/scale+box[0],y=(event.clientY-rect.top-oy)/scale+box[1];let best=null,bestDist=(12/scale)**2;for(let i=0;i<d.forensics.native_count;i++){if(!photoIncluded(i))continue;const dx=forensic.pixels[i*2]-x,dy=forensic.pixels[i*2+1]-y,dist=dx*dx+dy*dy;if(dist<bestDist){bestDist=dist;best=i;}}if(best!==null){selectedPoint=best;drawPhoto();}}
'''


HTML = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>P3 · Wu–Vallet 갱신점 검토</title><link rel="icon" href="data:,"><style>
:root{--ink:#172d3d;--muted:#587080;--border:#dce4e9;--blue:#1876a0;--old:#b88742;--new:#268dc0;--changed:#d44952;--same:#26a68b;--single:#92a0aa;--unassessed:#5e5279}*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f0f4f6;font:15px/1.6 system-ui,-apple-system,"Noto Sans KR",sans-serif}main{max-width:1640px;padding:28px 24px 60px;margin:auto}h1{font-size:31px;letter-spacing:-1px;line-height:1.3;margin:9px 0 13px}h2{font-size:21px;margin:0 0 6px}h3{font-size:16px;margin:0}p{margin:8px 0}.eyebrow{font-size:12px;color:var(--blue);font-weight:750;letter-spacing:1px}.lead,.muted{color:var(--muted)}.notice{border-left:4px solid #c2933e;background:#fff7e5;padding:14px 18px;margin:20px 0}.notice p{margin:5px 0}.tag{display:inline-block;background:#e0ebf1;border-radius:20px;padding:3px 10px;font-size:12px;margin:4px 6px 0 0}.card{background:white;border:1px solid var(--border);border-radius:12px;padding:21px;margin:22px 0}.controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:15px 0}.control{display:flex;gap:8px;align-items:center;min-width:0;max-width:100%}.control span{font-size:13px;font-weight:650;flex-shrink:0}button,select{font:inherit;border:1px solid #c6d3dd;background:#fff;color:var(--ink);border-radius:7px;padding:7px 10px;max-width:100%;min-width:0}button{cursor:pointer}button:hover{background:#eef5f8}a{color:var(--blue)}button:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #dba331;outline-offset:2px}.view-grid{display:grid;grid-template-columns:minmax(0,1fr) 270px;gap:18px}.viewport{position:relative;background:#eef3f6;border:1px solid var(--border);border-radius:9px;overflow:hidden;min-width:0;height:560px}.viewport canvas{display:block;width:100%;height:100%;touch-action:none}.viewport .corner{position:absolute;left:13px;top:10px;font-size:12px;pointer-events:none;color:#3c5768;background:#ffffffcf;border-radius:5px;padding:4px 7px}.stats{display:grid;grid-template-columns:1fr;gap:9px}.stat{background:#f4f7f9;border-radius:8px;padding:11px 14px}.stat b{font-size:21px;font-variant-numeric:tabular-nums;display:block;line-height:1.4}.stat span{font-size:12px;color:var(--muted)}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;margin:12px 0}.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}.small{font-size:12px}.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}.plot{height:370px;min-width:0;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:#fbfcfd}.plot canvas{display:block;width:100%;height:100%}.table-wrap{overflow:auto;max-width:100%;border:1px solid var(--border);border-radius:8px;margin-top:14px}table{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap;font-variant-numeric:tabular-nums;text-align:right}th,td{padding:10px 12px;border-bottom:1px solid var(--border)}th{background:#edf4f7;font-size:12px}th:first-child,td:first-child{text-align:left}tr.selected td{background:#e7f2f7}tr[data-arm]{cursor:pointer}tbody tr:last-child td{border:0}.mono{font:12px/1.55 ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}details{padding:12px 0;border-bottom:1px solid var(--border)}summary{cursor:pointer;font-weight:650}.links{display:flex;flex-wrap:wrap;gap:15px;margin:13px 0}.error{background:#ffe2e2;color:#921c26;padding:15px;border-radius:9px}footer{font-size:12px;color:var(--muted)}#loading{font-size:13px;color:var(--muted)}
@media(max-width:900px){main{padding:18px 12px 45px}.card{padding:16px}.view-grid{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.two{grid-template-columns:1fr}.viewport{height:420px}.plot{height:340px}h1{font-size:26px}.stat b{font-size:19px}.control{width:100%}.control select{flex:1}.controls button{flex:1} .mono{font-size:11px}}
</style></head><body><main><header><div class="eyebrow">JOINTBUILDGS · P3 · POINT CLOUD UPDATE</div><h1>갱신점은 사진의 어디에서 왔는가</h1><p class="lead">실제 현재 사진과 동일한 원점 인덱스를 연결하여 갱신점을 확인합니다. 기존 v2 결과와 소영역 제외를 수정한 v3 결과를 함께 비교합니다.</p><span class="tag">원래 산출물: 갱신 점군</span><span class="tag">비확증 개발 실행</span><span class="tag">scientific_verdict: null</span></header>
<div class="notice"><strong>논문 기반 구현이며 저자 코드의 동일 재현은 아닙니다.</strong><p>과거 ALS 센서 위치를 추정한 조건과 현재 영상 광선만 사용한 조건을 구분합니다. 현재 영상 점군은 COLMAP 깊이를 사용하므로 논문의 PSMNet 입력 생성과도 다릅니다. 추정 위치의 오차와 입력 대체의 영향을 포함한 결과입니다.</p><p id="scope-detail" class="small"></p></div>
<div class="notice"><strong>현재 확인한 문제는 구현 누락입니다. 논문의 맹점으로 결론내리지 않습니다.</strong><p>작은 영역의 면을 제외한 뒤 그 점을 단독 관측으로 다시 추가하는 경로를 수정했습니다. 남은 큰 영역의 영상 기하 오차와 입력·센서 위치 근사의 영향은 별도로 확인해야 합니다. 참조와 큰 거리 차이가 있다는 표시만으로 오류나 실제 변화를 확정하지 않습니다.</p></div>
__FORENSIC_CARD__
<div id="loading">점군과 실행 기록을 불러오는 중입니다.</div><div id="error" class="error" hidden></div>
<section class="card"><h2>원점과 갱신 결과</h2><p class="muted">드래그로 회전하고 휠로 확대합니다. 아래 3D와 지도는 같은 표시 점을 사용하며, 점의 색은 출처·판정입니다. 사진이나 Gaussian 렌더가 아닙니다.</p><div class="controls"><label class="control"><span>실행 조건</span><select id="arm-select" aria-label="실행 조건"></select></label><label class="control"><span>표시할 점</span><select id="mode-select" aria-label="표시할 점"><option value="updated">갱신 점군 · 출처 색</option><option value="inputs">두 입력 · 출처 색</option><option value="old">과거 ALS 원점</option><option value="new">현재 영상 원점</option><option value="region_removed">v2에서 추가했으나 현재 조건에서 제외한 영상점</option><option value="discrepancy">추가 영상점 중 UAS 거리 차이가 큰 점 · 평가 전용</option><option value="labels">두 입력 · 구현 판정 색</option><option value="removed">삭제된 과거 ALS</option><option value="added">추가된 현재 영상 점</option></select></label><button id="reset-view">3D 초기 시점</button><button id="top-view">위에서 보기</button></div><div class="view-grid"><div class="viewport" id="viewport"><div class="corner" id="view-caption"></div></div><aside><div class="stats" id="stats"></div><div class="legend" id="legend"></div><p class="small muted" id="display-count"></p><p class="small muted" id="direction-note"></p></aside></div></section>
<section class="card"><h2>같은 위치의 지도와 단면</h2><p class="muted">위에서 선택한 점을 XY 지도와 고정 단면에서 함께 봅니다. 단면 표본은 전체 원점에서 직접 선택하므로 3D 표시용 샘플링에 의해 사라지지 않습니다.</p><div class="controls"><label class="control"><span>단면 위치</span><select id="section-select"><option value="x">X = −40 m · Y–Z 단면</option><option value="y">Y = −15 m · X–Z 단면</option></select></label></div><div class="two"><div><h3>XY 출처·판정 지도</h3><div class="plot"><canvas id="map-canvas" aria-label="XY 지도"></canvas></div></div><div><h3 id="section-title">고정 단면</h3><div class="plot"><canvas id="section-canvas" aria-label="고정 단면"></canvas></div></div></div><p class="small muted" id="section-count"></p></section>
<section class="card"><h2>실행 조건별 유지·삭제·추가</h2><p class="muted">모든 수는 P3의 원래 점 전체에서 계산합니다. 기본 비교는 같은 소영역 문턱의 v2_a1 → corrected_area1입니다. changed_only_area1은 교차 미검출점을 모두 제외하는 별도 민감도 조건입니다. 점 수의 증가·감소 자체가 정확도나 개선을 뜻하지 않습니다. 행을 누르면 해당 조건으로 이동합니다.</p><div class="table-wrap"><table><thead><tr><th>실행 조건</th><th>광선 방향</th><th>허용 거리</th><th>소영역 문턱</th><th>유지 ALS</th><th>삭제 ALS</th><th>추가 영상 점</th><th>갱신 전체</th></tr></thead><tbody id="arm-table"></tbody></table></div><div id="evaluation-panel" hidden><h3 style="margin-top:20px">평가 기록</h3><p class="small muted">평가 전용 참조와의 비교입니다. 판정이나 매개변수 선택에 이 참조를 사용하지 않았으며, 좌표계·시점·밀도 차이의 제한을 함께 읽어야 합니다.</p><p class="small muted" id="evaluation-summary"></p><div class="table-wrap"><table><thead><tr><th>입력 / 갱신 조건</th><th>갱신 전체</th><th>추가 영상점</th><th>추가 중 UAS 차이 > 2 m</th><th>제외 중 UAS 차이 > 2 m</th><th>갱신 → UAS p90</th><th>UAS → 갱신 p90</th></tr></thead><tbody id="evaluation-table"></tbody></table></div><div class="links" id="evaluation-links"><a href="receipts/evaluation.json">전체 평가 JSON</a></div></div></section>
<section class="card"><h2>확인 범위와 원본 산출물</h2><p>일치한 점은 과거 ALS를 유지하고 현재 영상의 중복 점을 제외합니다. 변경으로 판정한 과거 점은 삭제하고 현재 점을 추가합니다. 교차 미검출(single)은 가림·메시 범위 부족 등을 포함하며 실제 단독 관측을 보증하지 않습니다. 여기에 남은 과거 점의 현재 적합성은 별도로 검증해야 합니다.</p><details open><summary>GPS time과 과거 센서 위치가 하는 일</summary><p class="muted">GPS time은 점의 취득 순서와 스캔 구조 복원에 쓰입니다. 센서 위치가 있으면 각 점까지 비어 있어야 하는 광선 구간을 검사할 수 있습니다. 현재 영상 광선만 사용하면 현재 관측 앞에 있는 낡은 ALS를 제거할 수 있지만, 신축 구조 뒤에 있는 과거 면은 같은 방식으로 배제할 수 없습니다. 추정 ALS 광선의 결과는 이 누락을 줄일 가능성과 추정 오차의 영향을 함께 포함합니다.</p></details><details><summary>표시와 원자료 출처</summary><pre class="mono" id="provenance"></pre></details><div class="links"><a href="viewer_manifest.json">뷰어 출처·해시</a><a href="receipts/update_receipt.json">전체 실행 기록</a><a href="downloads/common.npz">P3 두 입력 NPZ</a><a id="arm-json" href="#">선택 조건 실행 JSON</a><a id="arm-npz" href="#">선택 조건 갱신 NPZ</a><a id="arm-ply" href="#">선택 조건 갱신 PLY</a></div></section><footer>원점·분류·갱신 산출물은 보존됩니다. 이 화면은 Wu–Vallet 기반 점군 갱신의 개발 결과이며 방법 우위나 과학적 판정을 대신하지 않습니다.</footer>
<script id="evidence-data" type="application/json">__DATA__</script><script type="module">
import * as THREE from './three.module.min.js';
const d=JSON.parse(document.getElementById('evidence-data').textContent),$=id=>document.getElementById(id),count=x=>Number(x).toLocaleString('ko-KR'),colors={old:'#b88742',new:'#268dc0',consistent:'#26a68b',changed:'#d44952',single:'#92a0aa',unassessed:'#5e5279',filtered:'#b0509a',region_removed:'#bd4b9e',discrepancy:'#e98424'},labelNames={old:'과거 ALS',new:'현재 영상',consistent:'일치',changed:'변경',single:'교차 미검출 · 원인 미확정',unassessed:'미판정',filtered:'소영역 제외',region_removed:'v2 대비 제외 영상점',discrepancy:'UAS 차이 > 2 m · 평가 전용'};
window.__WV_QA={ready:false,arm:null,mode:null,frames:0,errors:[],assets:[]};
async function binary(path,Type){const r=await fetch(path);if(!r.ok)throw Error(path+' HTTP '+r.status);const b=await r.arrayBuffer();window.__WV_QA.assets.push(path);return new Type(b);}
let current=d.arms.find(a=>a.name===d.default_arm)??d.arms[0],mode='updated',section='x',oldXYZ,newXYZ,forensic=null,photoImage=null,photoTransform=null,photoMode='admitted',photoROI='full',selectedPoint=null,pointMarker=null,oldSections={},newSections={},armCache=new Map(),active,selected={old:[],new:[]},scene,camera,renderer,group,azimuth=-.65,elevation=.72,zoom=1;
const center=d.bounds.min.map((v,i)=>(v+d.bounds.max[i])/2),span=Math.max(...d.bounds.max.map((v,i)=>v-d.bounds.min[i]));
function colorFor(side,label){if(mode==='discrepancy')return '#e98424';if(mode==='region_removed')return '#bd4b9e';return mode==='labels'?colors[d.labels[label]]:mode==='removed'?colors.changed:colors[side];}
function included(side,label,keep,nativeIndex=null){if(mode==='old')return side==='old';if(mode==='new')return side==='new';if(mode==='region_removed')return side==='new'&&nativeIndex!==null&&forensic&&forensic.baselineKeep[nativeIndex]===1&&keep===0;if(mode==='discrepancy')return side==='new'&&nativeIndex!==null&&forensic&&keep===1&&forensic.distance[nativeIndex]>d.forensics.distance_threshold_m;if(mode==='inputs'||mode==='labels')return true;if(mode==='updated')return keep===1;if(mode==='removed')return side==='old'&&keep===0;return side==='new'&&keep===1;}
function setCamera(){const w=$('viewport').clientWidth,h=$('viewport').clientHeight,scale=span*.74/zoom*Math.max(1,h/w);camera.left=-scale*w/h;camera.right=scale*w/h;camera.top=scale;camera.bottom=-scale;camera.position.set(center[0]+span*3*Math.cos(azimuth)*Math.cos(elevation),center[1]+span*3*Math.sin(azimuth)*Math.cos(elevation),center[2]+span*3*Math.sin(elevation));camera.up.set(0,0,1);camera.lookAt(...center);camera.updateProjectionMatrix();renderer.setSize(w,h,false);draw();}
function draw(){renderer.render(scene,camera);window.__WV_QA.frames++;}
function rebuildCloud(){if(!active)return;for(const obj of [...group.children]){group.remove(obj);obj.geometry.dispose();obj.material.dispose();}selected={old:[],new:[]};for(const side of ['old','new']){const xyz=side==='old'?oldXYZ:newXYZ,pos=[],col=[],labels=active[side+'Labels'],keep=active[side+'Keep'];for(let i=0;i<labels.length;i++){if(!included(side,labels[i],keep[i],Number((side==='old'?forensic?.oldDisplayIds:forensic?.newDisplayIds)?.[i]??i)))continue;selected[side].push(i);pos.push(xyz[3*i],xyz[3*i+1],xyz[3*i+2]);const c=new THREE.Color(colorFor(side,labels[i]));col.push(c.r,c.g,c.b);}const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geo.setAttribute('color',new THREE.Float32BufferAttribute(col,3));const material=new THREE.PointsMaterial({size:1.7,sizeAttenuation:false,vertexColors:true,transparent:false});group.add(new THREE.Points(geo,material));}draw();drawPlots();$('view-caption').textContent=current.name+' · '+$('mode-select').selectedOptions[0].textContent;$('display-count').textContent=`표시 ${count(selected.old.length+selected.new.length)}점. 입력 전체 ALS ${count(d.sources.old.native_count)}점 / 영상 ${count(d.sources.new.native_count)}점. 3D·지도만 소스당 최대 ${count(d.display_cap)}점을 결정적 순서로 표시합니다.`;window.__WV_QA.arm=current.name;window.__WV_QA.mode=mode;window.__WV_QA.visiblePoints={old:selected.old.length,new:selected.new.length};window.__WV_QA.ready=true;}
function setupCanvas(canvas){const rect=canvas.parentElement.getBoundingClientRect(),ratio=Math.min(devicePixelRatio,2);canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#fbfcfd';ctx.fillRect(0,0,rect.width,rect.height);return {ctx,w:rect.width,h:rect.height};}
function axes(canvas,xb,yb,xlabel,ylabel){const {ctx,w,h}=setupCanvas(canvas),pad={l:54,r:17,t:20,b:43},sx=(w-pad.l-pad.r)/(xb[1]-xb[0]),sy=(h-pad.t-pad.b)/(yb[1]-yb[0]),fx=x=>pad.l+(x-xb[0])*sx,fy=y=>h-pad.b-(y-yb[0])*sy;ctx.font='11px system-ui';ctx.lineWidth=1;for(let i=0;i<=4;i++){const x=xb[0]+(xb[1]-xb[0])*i/4,y=yb[0]+(yb[1]-yb[0])*i/4;ctx.strokeStyle='#e5ebef';ctx.beginPath();ctx.moveTo(fx(x),pad.t);ctx.lineTo(fx(x),h-pad.b);ctx.moveTo(pad.l,fy(y));ctx.lineTo(w-pad.r,fy(y));ctx.stroke();ctx.fillStyle='#627684';ctx.textAlign='center';ctx.fillText(x.toFixed(1),fx(x),h-pad.b+17);ctx.textAlign='right';ctx.fillText(y.toFixed(1),pad.l-7,fy(y)+4);}ctx.fillStyle='#405c6c';ctx.textAlign='center';ctx.fillText(xlabel,w/2,h-6);ctx.save();ctx.translate(13,h/2);ctx.rotate(-Math.PI/2);ctx.fillText(ylabel,0,0);ctx.restore();return {ctx,fx,fy};}
function drawPlots(){if(!active)return;const map=axes($('map-canvas'),[d.bounds.min[0],d.bounds.max[0]],[d.bounds.min[1],d.bounds.max[1]],'X · scene-local m','Y · scene-local m');for(const side of ['old','new']){const xyz=side==='old'?oldXYZ:newXYZ;for(const i of selected[side]){map.ctx.fillStyle=colorFor(side,active[side+'Labels'][i]);map.ctx.fillRect(map.fx(xyz[3*i])-0.6,map.fy(xyz[3*i+1])-0.6,1.2,1.2);}}const axis=section==='x'?1:0,at=section==='x'?d.sections.x:d.sections.y;map.ctx.strokeStyle='#162f3f';map.ctx.lineWidth=1.6;map.ctx.setLineDash([5,4]);map.ctx.beginPath();if(section==='x'){map.ctx.moveTo(map.fx(at),map.fy(d.bounds.min[1]));map.ctx.lineTo(map.fx(at),map.fy(d.bounds.max[1]));}else{map.ctx.moveTo(map.fx(d.bounds.min[0]),map.fy(at));map.ctx.lineTo(map.fx(d.bounds.max[0]),map.fy(at));}map.ctx.stroke();const plot=axes($('section-canvas'),[d.bounds.min[axis],d.bounds.max[axis]],[d.bounds.min[2],d.bounds.max[2]],(axis===0?'X':'Y')+' · scene-local m','Z · scene-local m');let n=0;for(const side of ['old','new']){const xyz=(side==='old'?oldSections:newSections)[section],labels=active[side+'SectionLabels'][section],keep=active[side+'SectionKeep'][section];for(let i=0;i<labels.length;i++){if(!included(side,labels[i],keep[i],Number(forensic?.sectionIds?.[side]?.[section]?.[i]??i)))continue;plot.ctx.fillStyle=colorFor(side,labels[i]);plot.ctx.fillRect(plot.fx(xyz[3*i+axis])-1,plot.fy(xyz[3*i+2])-1,2,2);n++;}}$('section-title').textContent=`${section.toUpperCase()} = ${at} m · 폭 ${d.sections.width} m`;$('section-count').textContent=`단면 표시 ${count(n)}점 · 전체 원점에서 |${section.toUpperCase()} − ${at}| ≤ ${d.sections.width/2} m로 선택. 좌표는 작업 원점 이동 후 미터 단위입니다.`;window.__WV_QA.section=section;window.__WV_QA.sectionPoints=n;}
function updateText(){const c=current.counts;$('stats').replaceChildren();for(const [name,value] of [['유지한 과거 ALS',c.retained_old],['삭제한 과거 ALS',c.removed_old],['추가한 현재 영상 점',c.admitted_new],['최종 갱신 점',c.updated]]){const el=document.createElement('div');el.className='stat';el.innerHTML='<span></span><b></b>';el.children[0].textContent=name;el.children[1].textContent=count(value);$('stats').append(el);}$('legend').replaceChildren();for(const key of (mode==='labels'?d.labels:mode==='removed'?['changed']:mode==='region_removed'||mode==='discrepancy'?[mode]:mode==='old'?['old']:mode==='new'||mode==='added'?['new']:['old','new'])){const el=document.createElement('span'),swatch=document.createElement('i');swatch.className='swatch';swatch.style.background=colors[key];el.append(swatch,document.createTextNode(labelNames[key]));$('legend').append(el);}$('direction-note').textContent=current.direction_mode==='ONLY_CURRENT_IMAGE_RAYS'?'현재 영상 → ALS만 실행했습니다. 현재 관측 뒤쪽의 과거 면은 과거 광선 없이 배제할 수 없습니다.':'추정한 ALS 센서 위치와 현재 영상 위치에서 양방향 광선을 실행했습니다. ALS 광선의 근사는 별도 불확실성입니다.';$('direction-note').textContent+=` ALS ${count(c.old_labels.unassessed)}점은 메시 미지원으로 미판정 상태에서 보존했습니다.`;for(const row of $('arm-table').children)row.classList.toggle('selected',row.dataset.arm===current.name);for(const ext of ['json','npz','ply'])$('arm-'+ext).href=current.downloads[ext];}
async function switchArm(name){window.__WV_QA.ready=false;current=d.arms.find(a=>a.name===name);$('arm-select').value=name;$('photo-arm-select').value=name;if(!armCache.has(name)){const b=current.display,entry={};for(const side of ['old','new']){entry[side+'Labels']=await binary(b[side].labels,Uint8Array);entry[side+'Keep']=await binary(b[side].keep,Uint8Array);if(side==='new'){entry.fullNewKeep=await binary(b.new.full_keep,Uint8Array);entry.fullNewLabels=await binary(b.new.full_labels,Uint8Array);}entry[side+'SectionLabels']={};entry[side+'SectionKeep']={};for(const s of ['x','y']){entry[side+'SectionLabels'][s]=await binary(b[side].sections[s].labels,Uint8Array);entry[side+'SectionKeep'][s]=await binary(b[side].sections[s].keep,Uint8Array);}}armCache.set(name,entry);}active=armCache.get(name);updateText();rebuildCloud();drawPhoto();}
__FORENSIC_JS__
try{await loadForensics();oldXYZ=await binary(d.sources.old.display_xyz,Float32Array);newXYZ=await binary(d.sources.new.display_xyz,Float32Array);for(const s of ['x','y']){oldSections[s]=await binary(d.sources.old.sections[s].xyz,Float32Array);newSections[s]=await binary(d.sources.new.sections[s].xyz,Float32Array);}scene=new THREE.Scene();scene.background=new THREE.Color('#eef3f6');camera=new THREE.OrthographicCamera(-1,1,1,-1,.01,span*100);renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));$('viewport').append(renderer.domElement);group=new THREE.Group();scene.add(group);const axesHelper=new THREE.AxesHelper(span*.2);axesHelper.position.set(d.bounds.min[0],d.bounds.min[1],d.bounds.min[2]);scene.add(axesHelper);const grid=new THREE.GridHelper(span,10,'#c5d2db','#dbe4ea');grid.rotation.x=Math.PI/2;grid.position.set(center[0],center[1],d.bounds.min[2]);scene.add(grid);let drag=null;renderer.domElement.onpointerdown=e=>{drag=[e.clientX,e.clientY];renderer.domElement.setPointerCapture(e.pointerId);};renderer.domElement.onpointerup=()=>drag=null;renderer.domElement.onpointermove=e=>{if(!drag)return;azimuth-=(e.clientX-drag[0])*.006;elevation=Math.max(.02,Math.min(1.56,elevation+(e.clientY-drag[1])*.006));drag=[e.clientX,e.clientY];setCamera();};renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.3,Math.min(8,zoom*Math.exp(-e.deltaY*.001)));setCamera();},{passive:false});for(const arm of d.arms){const option=document.createElement('option');option.value=arm.name;option.textContent=arm.name;$('arm-select').append(option);$('photo-arm-select').append(option.cloneNode(true));const row=document.createElement('tr');row.dataset.arm=arm.name;for(const value of [arm.name,arm.direction_mode==='ONLY_CURRENT_IMAGE_RAYS'?'현재 영상 → ALS':'추정 ALS ↔ 현재 영상',arm.tolerance_m+' m',arm.small_region_area_m2+' m²',...['retained_old','removed_old','admitted_new','updated'].map(k=>count(arm.counts[k]))]){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}row.onclick=()=>switchArm(arm.name).catch(fail);$('arm-table').append(row);} $('photo-arm-select').onchange=()=>switchArm($('photo-arm-select').value).catch(fail);$('arm-select').onchange=()=>switchArm($('arm-select').value).catch(fail);$('mode-select').onchange=()=>{mode=$('mode-select').value;updateText();rebuildCloud();drawPhoto();};$('section-select').options[0].textContent=`X = ${d.sections.x} m · Y–Z 단면`;$('section-select').options[1].textContent=`Y = ${d.sections.y} m · X–Z 단면`;$('section-select').onchange=()=>{section=$('section-select').value;drawPlots();};$('reset-view').onclick=()=>{azimuth=-.65;elevation=.72;zoom=1;setCamera();};$('top-view').onclick=()=>{azimuth=-Math.PI/2;elevation=1.56;setCamera();};new ResizeObserver(()=>{setCamera();drawPlots();}).observe($('viewport'));window.addEventListener('resize',()=>{drawPlots();drawPhoto();});$('scope-detail').textContent=`${d.arms.length}개 실행 조건 · 현재 영상 ${d.image_id??'133'} · 원문 미기재 판정 문턱과 샘플링 규칙은 실행 JSON에 명시했습니다.`;$('provenance').textContent=JSON.stringify({source_paths:d.source_paths,display_rule:d.display_rule,coordinates:d.coordinates,scientific_verdict:null},null,2);if(d.evaluation){$('evaluation-panel').hidden=false;$('evaluation-summary').textContent='참조 헤더 EPSG:32632 / 작업 표기 EPSG:25832. 이번 평가는 재투영·정합 없이 기존 수치 좌표의 원점 이동만 사용했습니다. 거리값은 이에 조건부이며 절대 정확도 인증이 아닙니다.';for(const [name,value] of Object.entries(d.evaluation.methods??{})){const row=document.createElement('tr');const items=[name,count(value.updated_to_reference.n),count(value.new.retained.n),count(value.new.large_discrepancy_retained),count(value.new.large_discrepancy_excluded),value.updated_to_reference.p90_m.toFixed(3)+' m',value.reference_to_updated.p90_m.toFixed(3)+' m'];for(const item of items){const cell=document.createElement('td');cell.textContent=item;row.append(cell);}$('evaluation-table').append(row);}for(const [name,path] of Object.entries(d.evaluation_figures??{})){const link=document.createElement('a');link.href=path;link.textContent=name==='height_comparison.png'?'전체 점 높이 비교 그림':'전체 점 공통 단면 그림';$('evaluation-links').append(link);}}setCamera();await switchArm(current.name);$('loading').hidden=true;}
catch(error){fail(error);}function fail(error){window.__WV_QA.errors.push(String(error));$('error').hidden=false;$('error').textContent='표시 실패: '+String(error);console.error(error);}
</script></main></body></html>'''


def main(config, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Build this project artifact in Docker")
    started = time.monotonic()
    cfg = read(config)
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must be null")
    run = Path(cfg["update_root"])
    receipt = read(run / "receipt.json")
    if receipt.get("scientific_verdict", "missing") is not None or not receipt.get("arms"):
        raise ValueError("Completed update receipt with arms and null verdict required")
    if output.exists():
        raise FileExistsError("New viewer output required")
    output.mkdir(parents=True, exist_ok=False)
    copied, derivatives, inputs = {}, {}, {}

    def copy(source, relative):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = sha(source)
        shutil.copy2(source, destination)
        if sha(destination) != digest:
            raise ValueError("Copied artifact hash mismatch")
        copied[relative] = {"source": str(source), "sha256": digest, "bytes": destination.stat().st_size}
        inputs[str(source)] = digest
        return relative

    def binary(array, relative, dtype):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            np.asarray(array, dtype=dtype).tofile(handle)
        derivatives[relative] = {"sha256": sha(destination), "bytes": destination.stat().st_size,
                                 "dtype": np.dtype(dtype).str, "shape": list(np.asarray(array).shape),
                                 "role": "DISPLAY_ONLY_never_used_for_classification_or_metrics"}
        return relative

    copy(run / "receipt.json", "receipts/update_receipt.json")
    copy(run / "common.npz", "downloads/common.npz")
    repo = Path(__file__).resolve().parents[3]
    copy(repo / "src/apps/gs3d_4way_viewer/build/three.module.min.js", "three.module.min.js")
    copy(config, "receipts/viewer_config.json")
    common = np.load(run / "common.npz", allow_pickle=False)
    xyz = {side: np.asarray(common[f"{side}_xyz"], dtype=np.float64) for side in ("old", "new")}
    for side, points in xyz.items():
        if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
            raise ValueError(f"Invalid native {side} geometry")
    cap = int(cfg["maximum_display_points_per_source"])
    if cap < 1:
        raise ValueError("Positive display cap required")
    indices = {side: np.arange(len(points), dtype=np.int64)[::max(1, int(np.ceil(len(points) / cap)))] for side, points in xyz.items()}
    sections = {"x": float(cfg["section_x_m"]), "y": float(cfg["section_y_m"]), "width": float(cfg["section_full_width_m"])}
    sec_indices = {side: {key: np.flatnonzero(np.abs(points[:, axis] - sections[key]) <= sections["width"] / 2)
                          for key, axis in (("x", 0), ("y", 1))} for side, points in xyz.items()}
    sources = {}
    for side in ("old", "new"):
        sources[side] = {
            "native_count": len(xyz[side]), "display_count": len(indices[side]),
            "display_xyz": binary(xyz[side][indices[side]], f"display/{side}_xyz.bin", "<f4"),
            "display_indices": binary(indices[side], f"display/{side}_indices.bin", "<i8"),
            "sections": {key: {"native_count": len(ids),
                                "xyz": binary(xyz[side][ids], f"display/{side}_section_{key}_xyz.bin", "<f4"),
                                "indices": binary(ids, f"display/{side}_section_{key}_indices.bin", "<i8")}
                         for key, ids in sec_indices[side].items()},
        }
    arms = []
    for entry in receipt["arms"]:
        name = entry["name"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Unsafe arm name")
        root = run / name
        result = read(root / "result.json")
        payload = np.load(root / "updated_points.npz", allow_pickle=False)
        counts, display = {}, {}
        expected_parts = []
        for side in ("old", "new"):
            labels, keep = payload[f"{side}_labels"], np.asarray(payload[f"{side}_keep_mask"], dtype=bool)
            if labels.shape != (len(xyz[side]),) or keep.shape != labels.shape or not np.isin(labels, LABELS).all():
                raise ValueError(f"Native label/membership mismatch: {name}/{side}")
            label_ids = np.array([LABELS.index(label) for label in labels], dtype=np.uint8)
            display[side] = {
                "labels": binary(label_ids[indices[side]], f"display/{name}/{side}_labels.bin", "u1"),
                "keep": binary(keep[indices[side]], f"display/{name}/{side}_keep.bin", "u1"),
                "full_keep": binary(keep, f"display/{name}/{side}_full_keep.bin", "u1"),
                "full_labels": binary(label_ids, f"display/{name}/{side}_full_labels.bin", "u1"),
                "sections": {key: {"labels": binary(label_ids[ids], f"display/{name}/{side}_section_{key}_labels.bin", "u1"),
                                    "keep": binary(keep[ids], f"display/{name}/{side}_section_{key}_keep.bin", "u1")}
                             for key, ids in sec_indices[side].items()},
            }
            counts[f"{side}_labels"] = {label: int(np.count_nonzero(labels == label)) for label in LABELS}
            counts["retained_old" if side == "old" else "admitted_new"] = int(keep.sum())
            if side == "old":
                counts["removed_old"] = int((~keep).sum())
            expected_parts.append(xyz[side][keep])
        expected = np.concatenate(expected_parts)
        actual = payload["updated_points"]
        if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0, atol=1e-7):
            raise ValueError(f"Updated XYZ does not match native-source membership: {name}")
        expected_source = np.r_[np.zeros(len(expected_parts[0]), dtype=np.int8), np.ones(len(expected_parts[1]), dtype=np.int8)]
        if not np.array_equal(payload["updated_source"], expected_source):
            raise ValueError(f"Updated source ordering mismatch: {name}")
        counts["updated"] = len(actual)
        downloads = {"json": copy(root / "result.json", f"receipts/{name}.json"),
                     "npz": copy(root / "updated_points.npz", f"downloads/{name}.npz"),
                     "ply": copy(root / "updated_points.ply", f"downloads/{name}.ply")}
        arms.append({"name": name, "direction_mode": entry.get("direction_mode", result.get("direction_mode")),
                     "tolerance_m": entry.get("tolerance_m", result.get("tolerance_m")),
                     "small_region_area_m2": entry.get("small_region_area_m2", result.get("small_region_area_m2", 0)),
                     "counts": counts, "display": display, "downloads": downloads})
    if len({arm["name"] for arm in arms}) != len(arms):
        raise ValueError("Duplicate arm names")
    merged = np.concatenate(list(xyz.values()))
    if not len(merged):
        raise ValueError("No native points")
    evaluation, evaluation_figures = None, {}
    epath = Path(cfg["evaluation_root"]) / "evaluation.json"
    if epath.is_file():
        evaluation = read(epath)
        if evaluation.get("scientific_verdict", "missing") is not None:
            raise ValueError("Evaluation scientific_verdict must be null")
        copy(epath, "receipts/evaluation.json")
        for name in ("height_comparison.png", "cross_sections.png"):
            source = epath.parent / name
            if source.is_file():
                if evaluation.get("outputs", {}).get(name) != sha(source):
                    raise ValueError(f"Evaluation figure hash differs: {name}")
                evaluation_figures[name] = copy(source, f"figures/{name}")
    data = {"schema": cfg["schema"], "task_id": cfg["task_id"], "generated_utc": datetime.now(timezone.utc).isoformat(),
            "scientific_verdict": None, "native_2026_reproduction": False, "arms": arms, "sources": sources,
            "labels": LABELS, "display_cap": cap, "sections": sections,
            "display_rule": "DISPLAY_ONLY_native_input_order_stride_ceil_N_over_cap_no_spatial_aggregation_no_scoring",
            "bounds": {"min": merged.min(axis=0).tolist(), "max": merged.max(axis=0).tolist()},
            "source_paths": {"update": str(run), "evaluation": str(epath) if evaluation else None},
            "coordinates": receipt.get("coordinates", {"working_crs": "EPSG:25832", "display": "scene_local_meters"}),
            "image_id": receipt.get("image_id", 133), "evaluation": evaluation,
            "evaluation_figures": evaluation_figures}
    data["forensics"] = build_forensics(cfg, run, output, xyz, common, copy, binary)
    data["default_arm"] = cfg.get("default_arm") if cfg.get("default_arm") in {arm["name"] for arm in arms} else arms[0]["name"]
    data["default_arm_policy"] = "configured_nominal_tolerance_and_no_region_filter_not_selected_from_performance"
    json_text = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    (output / "index.html").write_text(HTML.replace("__FORENSIC_CARD__", FORENSIC_CARD).replace("__FORENSIC_JS__", FORENSIC_JS).replace("__DATA__", json_text))
    manifest = {"status": "WU_VALLET_PHOTO_POINT_FORENSIC_VIEWER_COMPLETE", "task_id": cfg["task_id"],
                "scientific_verdict": None, "native_2026_reproduction": False,
                "source_receipt": str(run / "receipt.json"), "input_hashes": inputs,
                "copied_assets": copied, "display_derivatives": derivatives,
                "index_sha256": sha(output / "index.html"), "arm_count": len(arms),
                "forensics_native_pixel_and_xyz_validation": "PASS",
                "native_source_counts": {side: len(points) for side, points in xyz.items()},
                "display_source_counts": {side: len(ids) for side, ids in indices.items()},
                "all_arm_native_membership_xyz_and_source_validation": "PASS",
                "evaluation_included": evaluation is not None,
                "runtime_seconds": time.monotonic() - started}
    write(output / "viewer_manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "arms": len(arms), "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        main(args.config, args.output)
    except Exception as exc:
        if args.output.exists() and not (args.output / "FAILED.json").exists():
            write(args.output / "FAILED.json", {"error": repr(exc), "scientific_verdict": None})
        raise
