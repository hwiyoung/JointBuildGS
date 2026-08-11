#!/usr/bin/env python3
"""Build the thread-scoped interactive Roofer comparison fragment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


DATA = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1/representative_images/roofer_qualitative/roofer_qualitative.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    encoded = json.dumps(json.loads(DATA.read_text()), separators=(",", ":")).replace("</", "<\\/")
    fragment = r'''<div id="jbgs-roofer-qualitative-v1">
  <style>
    #jbgs-roofer-qualitative-v1 { width: 100%; color: var(--foreground); }
    #jbgs-roofer-qualitative-v1 .plots { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    #jbgs-roofer-qualitative-v1 canvas { display: block; width: 100%; height: 430px; cursor: grab; touch-action: none; }
    #jbgs-roofer-qualitative-v1 canvas:active { cursor: grabbing; }
    #jbgs-roofer-qualitative-v1 .panel-label { font-weight: 500; margin-bottom: 4px; }
    #jbgs-roofer-qualitative-v1 .legend { color: var(--muted-foreground); margin-top: 8px; }
    #jbgs-roofer-qualitative-v1 .swatch { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin: 0 4px 0 12px; background: var(--muted-foreground); }
    @media (max-width: 700px) { #jbgs-roofer-qualitative-v1 .plots { grid-template-columns: 1fr; } #jbgs-roofer-qualitative-v1 canvas { height: 390px; } }
  </style>
  <div class="viz-controls">
    <label class="form-label" for="jbgs-roofer-view">View</label>
    <select class="form-select" id="jbgs-roofer-view">
      <option value="context">Full footprint and evidence</option>
      <option value="closeup">Each Roofer output close-up</option>
    </select>
  </div>
  <div class="plots">
    <div><div class="panel-label">RAW_DEPTH</div><canvas id="jbgs-roofer-raw" aria-label="Rotatable RAW Roofer evidence and output"></canvas></div>
    <div><div class="panel-label">MVS_SURFACE_METRIC</div><canvas id="jbgs-roofer-fused" aria-label="Rotatable MVS surface depth Roofer evidence and output"></canvas></div>
  </div>
  <div class="legend text-small"><span class="swatch"></span>gray points: class-6 evidence · solid faces: actual Roofer output · outline: shared footprint · drag to rotate · wheel to zoom</div>
  <script>
    (() => {
      const root = document.getElementById('jbgs-roofer-qualitative-v1');
      const data = __DATA__;
      const view = document.getElementById('jbgs-roofer-view');
      const canvases = [document.getElementById('jbgs-roofer-raw'), document.getElementById('jbgs-roofer-fused')];
      const state = { azimuth: -0.95, elevation: 0.48, zoom: 1.0 };
      const themeColor = token => {
        const probe = document.createElement('span'); probe.style.color = `var(${token})`; probe.style.display = 'none'; root.appendChild(probe);
        const value = getComputedStyle(probe).color; probe.remove(); return value;
      };
      const palette = {
        raw: themeColor('--viz-series-1'), fused: themeColor('--viz-series-2'), point: themeColor('--muted-foreground'),
        foreground: themeColor('--foreground'), roof: null, wall: themeColor('--muted-foreground'), ground: themeColor('--border')
      };
      const project = (point, center) => {
        const x = point[0]-center[0], y = point[1]-center[1], z = point[2]-center[2];
        const ca=Math.cos(state.azimuth), sa=Math.sin(state.azimuth), ce=Math.cos(state.elevation), se=Math.sin(state.elevation);
        const xr=ca*x-sa*y, yr=sa*x+ca*y; return [xr, -ce*z+se*yr, se*z+ce*yr];
      };
      const draw = (canvas, armName) => {
        const arm=data.arms[armName], rect=canvas.getBoundingClientRect(), dpr=Math.min(window.devicePixelRatio||1,2);
        canvas.width=Math.max(1,Math.round(rect.width*dpr)); canvas.height=Math.max(1,Math.round(rect.height*dpr));
        const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr); ctx.clearRect(0,0,rect.width,rect.height);
        const surfacePoints=arm.surfaces.flatMap(surface=>surface.xyz);
        const all=view.value==='closeup' ? surfacePoints : Object.values(data.arms).flatMap(value=>value.class6.concat(value.surfaces.flatMap(surface=>surface.xyz)));
        const zmin=Math.min(...all.map(p=>p[2])), zmax=Math.max(...all.map(p=>p[2]));
        const center=view.value==='closeup'
          ? [(Math.min(...all.map(p=>p[0]))+Math.max(...all.map(p=>p[0])))/2,(Math.min(...all.map(p=>p[1]))+Math.max(...all.map(p=>p[1])))/2,(zmin+zmax)/2]
          : [0,0,(zmin+zmax)/2];
        const projected=all.map(p=>project(p,center));
        const maxx=Math.max(1,...projected.map(p=>Math.abs(p[0]))), maxy=Math.max(1,...projected.map(p=>Math.abs(p[1])));
        const scale=.82*state.zoom*Math.min(rect.width/(2*maxx),rect.height/(2*maxy));
        const sx=p=>rect.width/2+p[0]*scale, sy=p=>rect.height/2+p[1]*scale;
        if(view.value==='context'){
          const boundary=data.footprint.map(p=>project([p[0],p[1],arm.metrics.ground_z],center));
          ctx.strokeStyle=palette.foreground; ctx.lineWidth=1.3; ctx.beginPath(); boundary.forEach((p,i)=>i?ctx.lineTo(sx(p),sy(p)):ctx.moveTo(sx(p),sy(p))); ctx.stroke();
        }
        const items=[];
        if(view.value==='context') arm.class6.forEach(p=>{const q=project(p,center);items.push({depth:q[2],kind:'point',q});});
        arm.surfaces.forEach(surface=>{const q=surface.xyz.map(p=>project(p,center));items.push({depth:q.reduce((s,p)=>s+p[2],0)/q.length,kind:'surface',q,semantic:surface.semantic});});
        items.sort((a,b)=>a.depth-b.depth).forEach(item=>{
          if(item.kind==='point'){ctx.globalAlpha=.20;ctx.fillStyle=palette.point;ctx.beginPath();ctx.arc(sx(item.q),sy(item.q),1.1,0,Math.PI*2);ctx.fill();return;}
          ctx.globalAlpha=item.semantic==='RoofSurface'?.72:.38;
          ctx.fillStyle=item.semantic==='RoofSurface'?(armName==='RAW_DEPTH'?palette.raw:palette.fused):(item.semantic==='WallSurface'?palette.wall:palette.ground);
          ctx.strokeStyle=palette.foreground;ctx.lineWidth=.55;ctx.beginPath();item.q.forEach((p,i)=>i?ctx.lineTo(sx(p),sy(p)):ctx.moveTo(sx(p),sy(p)));ctx.closePath();ctx.fill();ctx.stroke();
        });
        ctx.globalAlpha=1;ctx.fillStyle=palette.foreground;ctx.font='12px sans-serif';
        ctx.fillText(`class 6 ${arm.metrics.class6.toLocaleString()} · planes ${arm.metrics.roof_planes} · ridges ${arm.metrics.ridgelines} · volume ${arm.metrics.volume_m3.toFixed(1)} m³`,10,rect.height-12);
      };
      const render=()=>{draw(canvases[0],'RAW_DEPTH');draw(canvases[1],'MVS_SURFACE_METRIC');};
      let drag=null;
      canvases.forEach(canvas=>{
        canvas.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
        canvas.addEventListener('pointermove',e=>{if(!drag)return;state.azimuth+=(e.clientX-drag[0])*.008;state.elevation=Math.max(-1.35,Math.min(1.35,state.elevation+(e.clientY-drag[1])*.006));drag=[e.clientX,e.clientY];render();});
        canvas.addEventListener('pointerup',()=>{drag=null;});canvas.addEventListener('pointercancel',()=>{drag=null;});
        canvas.addEventListener('wheel',e=>{e.preventDefault();state.zoom=Math.max(.55,Math.min(2.8,state.zoom*Math.exp(-e.deltaY*.001)));render();},{passive:false});
      });
      view.addEventListener('change',render);
      new ResizeObserver(render).observe(root);render();
    })();
  </script>
</div>'''.replace("__DATA__", encoded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(fragment + "\n")
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size}))


if __name__ == "__main__":
    main()
