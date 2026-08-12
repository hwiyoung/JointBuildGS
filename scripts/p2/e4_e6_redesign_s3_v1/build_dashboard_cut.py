#!/usr/bin/env python3
"""Build the redesign O50 cut for the 8880 judgment dashboard.

Self-contained HTML: same-lineage O50 table + a footprint map of all 199
buildings coloured by paired transition (rescue / regress / both-O / both-X)
against a selectable baseline (E2 or E3) for a selectable arm (E4-v2 / E5-v2),
with per-building gate details on click. Development read-out only; O_noG2
basis; `scientific_verdict: null`.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ART = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
S3 = ART / "phase-payloads/p2/e4_e6_redesign_s3_v1/P2-E4-E6-REDESIGN-S3-v1"
V22 = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-AUTO-OX-v22-ROBUST-PLANE-MATCH"
DASH = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-GATE5-DASHBOARD-v1"
OUT = DASH / "redesign_v1/index.html"


def no_g2(row: dict) -> str:
    if row["verdict"] == "NA":
        return "NA"
    return "O" if all(row[g] == "O" for g in ("G0_status", "G1_status", "G3_status", "G4_status")) else "X"


def main() -> None:
    sealed = [r for r in csv.DictReader((V22 / "reference_auto_ox_building_condition_v1.csv").open()) if r["criterion"] == "O50"]
    mine = [r for r in csv.DictReader((S3 / "evaluation/s3_building_condition_v1.csv").open()) if r["criterion"] == "O50"]
    verdicts: dict[str, dict[str, str]] = {}
    reasons: dict[str, dict[str, str]] = {}
    for r in sealed:
        verdicts.setdefault(r["stable_id"], {})[r["condition_id"]] = no_g2(r)
        if r["condition_id"] in ("E2", "E3"):
            reasons.setdefault(r["stable_id"], {})[r["condition_id"]] = r["failure_reasons"]
    label = {"E4_V2_STATIC": "E4v2", "E5_V2_F1": "E5v2"}
    for r in mine:
        verdicts.setdefault(r["stable_id"], {})[label[r["condition_id"]]] = r["verdict_noG2"]
        reasons.setdefault(r["stable_id"], {})[label[r["condition_id"]]] = r["failure_reasons"]

    geo = json.loads((S3 / "freeze/shared_footprints.geojson").read_text())
    xs, ys = [], []
    features = []
    for f in geo["features"]:
        sid = str(f["properties"]["stable_id"])
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = []
        for poly in polys:
            for ring in poly[:1]:
                pts = [(round(x, 2), round(y, 2)) for x, y, *_ in ring]
                rings.append(pts)
                xs += [p[0] for p in pts]
                ys += [p[1] for p in pts]
        features.append({"sid": sid, "rings": rings, "v": verdicts.get(sid, {}), "fr": reasons.get(sid, {})})
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    counts = {c: sum(1 for f in features if f["v"].get(c) == "O") for c in ("E1", "E2", "E3", "E4v2", "E5v2")}
    generated = datetime.now(timezone.utc).isoformat()
    data = json.dumps({"bbox": [x0, y0, x1, y1], "features": features}, separators=(",", ":"))

    html = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>E1-E6 redesign O50 cut (development)</title>
<style>
body{font-family:system-ui,sans-serif;margin:14px;background:#111;color:#eee}
h1{font-size:18px} h1 small{color:#999;font-weight:400;font-size:12px}
table{border-collapse:collapse;margin:8px 0} td,th{border:1px solid #444;padding:4px 12px;text-align:center}
.controls{margin:10px 0} select,button{background:#222;color:#eee;border:1px solid #555;padding:4px 8px;margin-right:8px}
#map{background:#181818;border:1px solid #333} .fp{stroke:#000;stroke-width:.6;cursor:pointer}
.rescue{fill:#2ecc71}.regress{fill:#e74c3c}.bothO{fill:#3498db}.bothX{fill:#555}
.legend span{display:inline-block;margin-right:14px;font-size:12px}
.legend i{display:inline-block;width:12px;height:12px;margin-right:4px;vertical-align:-1px}
#detail{background:#1c1c1c;border:1px solid #333;padding:8px 12px;font-size:13px;min-height:70px;white-space:pre-wrap}
.caveat{color:#888;font-size:11px;margin-top:10px}
a{color:#7fb3ff}
</style></head><body>
<h1>재설계 O50 컷 <small>같은 계보 · O_noG2 · 비확증 개발 판독 · scientific_verdict: null · __GEN__</small></h1>
<p><a href="../index.html">← 기존 Gate5 대시보드(레거시 컷)</a></p>
<table><tr><th>E1</th><th>E2</th><th>E3</th><th>E4 (재설계)</th><th>E5 (재설계)</th></tr>
<tr><td>__E1__</td><td>__E2__</td><td>__E3__</td><td><b>__E4v2__</b></td><td><b>__E5v2__</b></td></tr></table>
<div class="controls">
기준선 <select id="base"><option value="E2">E2 (product)</option><option value="E3">E3 (메커니즘)</option></select>
비교 arm <select id="arm"><option value="E5v2">E5 (재설계)</option><option value="E4v2">E4 (재설계)</option></select>
<span class="legend"><span><i class="rescue"></i>rescue X→O</span><span><i class="regress"></i>역전 O→X</span><span><i class="bothO"></i>둘 다 O</span><span><i class="bothX"></i>둘 다 X</span></span>
</div>
<svg id="map" width="980" height="640"></svg>
<div id="detail">건물을 클릭하면 조건별 판정과 실패 사유가 표시됩니다.</div>
<p class="caveat">판정: v22 기준(G0∧G1∧G3∧G4; val3dity 부재로 G2 제외). E1/E2/E3는 봉인된 v22 판정, E4/E5는 재설계 S3 판정. 좌표 EPSG:25832.</p>
<script>
const D=__DATA__;
const svg=document.getElementById('map');
const W=980,H=640,[x0,y0,x1,y1]=D.bbox,pad=12;
const sx=(W-2*pad)/(x1-x0),sy=(H-2*pad)/(y1-y0),s=Math.min(sx,sy);
const px=x=>pad+(x-x0)*s, py=y=>H-pad-(y-y0)*s;
function cat(f,b,a){const vb=f.v[b],va=f.v[a];
 if(vb==='X'&&va==='O')return 'rescue'; if(vb==='O'&&va==='X')return 'regress';
 if(vb==='O'&&va==='O')return 'bothO'; return 'bothX';}
function render(){
 const b=document.getElementById('base').value,a=document.getElementById('arm').value;
 svg.innerHTML='';
 for(const f of D.features){
  const d=f.rings.map(r=>'M'+r.map(p=>px(p[0]).toFixed(1)+','+py(p[1]).toFixed(1)).join('L')+'Z').join(' ');
  const el=document.createElementNS('http://www.w3.org/2000/svg','path');
  el.setAttribute('d',d); el.setAttribute('class','fp '+cat(f,b,a));
  el.addEventListener('click',()=>{
   const v=f.v, fr=f.fr||{};
   document.getElementById('detail').textContent=
    f.sid+'\\n판정(O50,noG2): E1='+(v.E1||'?')+' E2='+(v.E2||'?')+' E3='+(v.E3||'?')+' | E4v2='+(v.E4v2||'?')+' E5v2='+(v.E5v2||'?')+
    '\\nE2 실패사유: '+(fr.E2||'-')+'\\nE3 실패사유: '+(fr.E3||'-')+'\\nE4v2 실패사유: '+(fr.E4v2||'-')+'\\nE5v2 실패사유: '+(fr.E5v2||'-');
  });
  svg.appendChild(el);
 }}
document.getElementById('base').onchange=render;
document.getElementById('arm').onchange=render;
render();
</script></body></html>"""
    html = (html.replace("__GEN__", generated).replace("__DATA__", data)
            .replace("__E1__", str(counts["E1"])).replace("__E2__", str(counts["E2"]))
            .replace("__E3__", str(counts["E3"])).replace("__E4v2__", str(counts["E4v2"]))
            .replace("__E5v2__", str(counts["E5v2"])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(json.dumps({"written": str(OUT), "bytes": OUT.stat().st_size, "counts": counts}))


if __name__ == "__main__":
    main()
