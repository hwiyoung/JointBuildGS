#!/usr/bin/env python3
"""Build the redesign O50-O80 cut for the 8880 judgment dashboard.

Self-contained HTML embedded into the existing dashboard page: same-lineage
O table that recomputes per threshold (O50..O80), a footprint transition map,
and a per-building detail panel that shows WHICH gate metrics caused X
(value vs frozen development threshold). O_noG2 basis; development read-out;
`scientific_verdict: null`.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ART = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
S3 = ART / "phase-payloads/p2/e4_e6_redesign_s3_v1/P2-E4-E6-REDESIGN-S3-v1"
V22 = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-AUTO-OX-v22-ROBUST-PLANE-MATCH"
DASH = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-GATE5-DASHBOARD-v1"
OUT = DASH / "redesign_v1/index.html"
CONDS = ("E1", "E2", "E3", "E4v2", "E5v2")
CRITS = ("O50", "O60", "O70", "O80")
METRIC_KEYS = (
    ("g3_plane_area_recall", "G3 recall", ">="),
    ("g3_plane_area_precision", "G3 precision", ">="),
    ("g4_coverage", "G4 coverage", ">="),
    ("g4_rmse_z_m", "G4 RMSE[m]", "<="),
    ("g4_p95_abs_z_m", "G4 p95[m]", "<="),
    ("g4_median_bias_z_m", "G4 bias[m]", "<=abs"),
)


def no_g2(row: dict) -> str:
    if row["verdict"] == "NA":
        return "NA"
    return "O" if all(row[g] == "O" for g in ("G0_status", "G1_status", "G3_status", "G4_status")) else "X"


def metrics_of(row: dict) -> dict:
    out = {}
    for key, _, _ in METRIC_KEYS:
        value = row.get(key)
        if value not in (None, "", "None"):
            out[key] = round(float(value), 3)
    return out


def main() -> None:
    config = json.loads((REPO / "configs/p2/e1_e6_roofer_ox_review_v1/reference_auto_ox_v1.json").read_text())
    thresholds = config["acceptance_thresholds"]
    verdicts: dict[str, dict[str, dict[str, str]]] = {}
    detail: dict[str, dict[str, dict]] = {}
    for r in csv.DictReader((V22 / "reference_auto_ox_building_condition_v1.csv").open()):
        cond = r["condition_id"]
        if cond in ("E4", "E5", "E6"):
            continue
        sid = r["stable_id"]
        verdicts.setdefault(sid, {}).setdefault(r["criterion"], {})[cond] = no_g2(r)
        if r["criterion"] == "O50":
            detail.setdefault(sid, {})[cond] = {"fr": r["failure_reasons"], "m": metrics_of(r)}
    label = {"E4_V2_STATIC": "E4v2", "E5_V2_F1": "E5v2"}
    for r in csv.DictReader((S3 / "evaluation/s3_building_condition_v1.csv").open()):
        sid = r["stable_id"]
        cond = label[r["condition_id"]]
        row = dict(r)
        row["verdict"] = r["verdict_noG2"]
        row.setdefault("G2_status", "O")
        verdicts.setdefault(sid, {}).setdefault(r["criterion"], {})[cond] = no_g2(row)
        if r["criterion"] == "O50":
            detail.setdefault(sid, {})[cond] = {"fr": r["failure_reasons"], "m": metrics_of(r)}

    geo = json.loads((S3 / "freeze/shared_footprints.geojson").read_text())
    xs, ys, features = [], [], []
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
        features.append({"sid": sid, "rings": rings, "v": verdicts.get(sid, {}), "d": detail.get(sid, {})})

    data = json.dumps({
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "features": features,
        "thresholds": thresholds,
        "generated": datetime.now(timezone.utc).isoformat(),
    }, separators=(",", ":"))

    html = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>재설계 O-컷 (개발 판독)</title>
<style>
body{font-family:system-ui,sans-serif;margin:12px;background:#F6F7F8;color:#1B2026}
h2{font-size:16px;margin:4px 0} h2 small{color:#8B95A0;font-weight:400;font-size:11px}
table.o{border-collapse:collapse;margin:8px 0} .o td,.o th{border:1px solid #E2E6EA;padding:4px 14px;text-align:center;background:#fff}
.controls{margin:8px 0;font-size:13px} select{border:1px solid #ccc;padding:3px 6px;margin-right:10px}
#map{background:#fff;border:1px solid #E2E6EA} .fp{stroke:#666;stroke-width:.5;cursor:pointer}
.rescue{fill:#2E9E5B}.regress{fill:#C2453A}.bothO{fill:#2E6BA8}.bothX{fill:#D5DAе0}
.bothX{fill:#D5DAE0}
.legend span{margin-right:12px;font-size:12px}.legend i{display:inline-block;width:11px;height:11px;margin-right:3px;vertical-align:-1px}
#detail{background:#fff;border:1px solid #E2E6EA;padding:8px 12px;font-size:12px;margin-top:8px}
#detail table{border-collapse:collapse;margin-top:6px} #detail td,#detail th{border:1px solid #EDF0F3;padding:2px 8px;font-size:12px;text-align:center}
.bad{color:#C2453A;font-weight:600}.ok{color:#2E9E5B}
.caveat{color:#8B95A0;font-size:11px;margin-top:8px}
</style></head><body>
<h2>재설계 O-컷: 같은 계보, 임계 연동 <small>O_noG2 · 비확증 개발 판독 · scientific_verdict: null</small></h2>
<div class="controls">
판정 임계 <select id="crit"><option>O50</option><option>O60</option><option>O70</option><option>O80</option></select>
기준선 <select id="base"><option value="E2">E2 (product)</option><option value="E3">E3 (메커니즘)</option></select>
비교 arm <select id="arm"><option value="E5v2">E5 (재설계)</option><option value="E4v2">E4 (재설계)</option></select>
<span class="legend"><span><i class="rescue"></i>rescue X→O</span><span><i class="regress"></i>역전 O→X</span><span><i class="bothO"></i>둘 다 O</span><span><i class="bothX"></i>둘 다 X</span></span>
</div>
<table class="o" id="otab"></table>
<svg id="map" width="960" height="600"></svg>
<div id="detail">건물을 클릭하면 조건별 판정과 <b>X의 원인 지표</b>(값 vs 임계)가 표시됩니다.</div>
<p class="caveat">G0∧G1∧G3∧G4 (val3dity 부재로 G2 제외). E1/E2/E3 = 봉인 v22 판정 · E4/E5 = 재설계 S3 판정. 지표 상세는 O50 기준 값. EPSG:25832.</p>
<script>
const D=__DATA__, CONDS=['E1','E2','E3','E4v2','E5v2'];
const NAMES={E1:'E1',E2:'E2',E3:'E3',E4v2:'E4(재설계)',E5v2:'E5(재설계)'};
const TH=D.thresholds;
const LIMS={g3_plane_area_recall:['≥',TH.g3.plane_area_recall_min],g3_plane_area_precision:['≥',TH.g3.plane_area_precision_min],
 g4_coverage:['≥',TH.g4.coverage_min],g4_rmse_z_m:['≤',TH.g4.rmse_z_m_max],g4_p95_abs_z_m:['≤',TH.g4.p95_abs_z_m_max],g4_median_bias_z_m:['|x|≤',TH.g4.abs_median_bias_z_m_max]};
const MLABEL={g3_plane_area_recall:'G3 recall',g3_plane_area_precision:'G3 precision',g4_coverage:'G4 coverage',g4_rmse_z_m:'G4 RMSE[m]',g4_p95_abs_z_m:'G4 p95[m]',g4_median_bias_z_m:'G4 bias[m]'};
const svg=document.getElementById('map');
const W=960,H=600,[x0,y0,x1,y1]=D.bbox,pad=12;
const s=Math.min((W-2*pad)/(x1-x0),(H-2*pad)/(y1-y0));
const px=x=>pad+(x-x0)*s, py=y=>H-pad-(y-y0)*s;
function counts(crit){const c={};for(const k of CONDS)c[k]=0;
 for(const f of D.features){const v=f.v[crit]||{};for(const k of CONDS)if(v[k]==='O')c[k]++;}return c;}
function otab(){const crit=document.getElementById('crit').value;const c=counts(crit);
 document.getElementById('otab').innerHTML='<tr>'+CONDS.map(k=>'<th>'+NAMES[k]+'</th>').join('')+'</tr>'+
 '<tr>'+CONDS.map(k=>'<td'+(k.endsWith('v2')?' style="font-weight:700"':'')+'>'+c[k]+' / 199</td>').join('')+'</tr>';}
function cat(f,crit,b,a){const v=f.v[crit]||{},vb=v[b],va=v[a];
 if(vb==='X'&&va==='O')return 'rescue'; if(vb==='O'&&va==='X')return 'regress';
 if(vb==='O'&&va==='O')return 'bothO'; return 'bothX';}
function pass(key,val){const[op,lim]=LIMS[key];if(val==null)return null;
 return op==='≥'?val>=lim:(op==='≤'?val<=lim:Math.abs(val)<=lim);}
function detail(f){const crit=document.getElementById('crit').value;const v=f.v[crit]||{};
 let h='<b>'+f.sid+'</b> — 판정('+crit+'): '+CONDS.map(k=>NAMES[k]+'=<b class="'+((v[k]==='O')?'ok':'bad')+'">'+(v[k]||'?')+'</b>').join(' · ');
 h+='<table><tr><th>지표 (O50 값)</th><th>임계</th>'+['E2','E3','E4v2','E5v2'].map(k=>'<th>'+NAMES[k]+'</th>').join('')+'</tr>';
 for(const key of Object.keys(MLABEL)){const[op,lim]=LIMS[key];
  h+='<tr><td style="text-align:left">'+MLABEL[key]+'</td><td>'+op+' '+lim+'</td>';
  for(const k of ['E2','E3','E4v2','E5v2']){const d=(f.d||{})[k];const val=d&&d.m?d.m[key]:null;
   const p=pass(key,val);h+='<td class="'+(p===false?'bad':(p===true?'ok':''))+'">'+(val==null?'—':val)+'</td>';}
  h+='</tr>';}
 h+='</table>';
 for(const k of ['E2','E3','E4v2','E5v2']){const d=(f.d||{})[k];
  if(d&&d.fr)h+='<div style="margin-top:3px"><span style="color:#8B95A0">'+NAMES[k]+' 실패사유:</span> <span class="bad">'+d.fr.split('|').join(', ')+'</span></div>';}
 document.getElementById('detail').innerHTML=h;}
function render(){const crit=document.getElementById('crit').value,b=document.getElementById('base').value,a=document.getElementById('arm').value;
 otab();svg.innerHTML='';
 for(const f of D.features){
  const d=f.rings.map(r=>'M'+r.map(p=>px(p[0]).toFixed(1)+','+py(p[1]).toFixed(1)).join('L')+'Z').join(' ');
  const el=document.createElementNS('http://www.w3.org/2000/svg','path');
  el.setAttribute('d',d);el.setAttribute('class','fp '+cat(f,crit,b,a));
  el.addEventListener('click',()=>detail(f));svg.appendChild(el);}}
for(const id of ['crit','base','arm'])document.getElementById(id).onchange=render;
render();
</script></body></html>"""
    html = html.replace("__DATA__", data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(json.dumps({"written": str(OUT), "bytes": OUT.stat().st_size}))


if __name__ == "__main__":
    main()
