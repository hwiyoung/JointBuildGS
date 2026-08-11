#!/usr/bin/env python3
"""Build the thread-scoped interactive 3D comparison fragment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


DATA = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1/representative_images/geometry_3d/geometry_3d_samples.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(DATA.read_text())
    encoded = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    fragment = r'''<div id="jbgs-geometry-3d-v1">
  <style>
    #jbgs-geometry-3d-v1 { color: var(--foreground); width: 100%; }
    #jbgs-geometry-3d-v1 .plots { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    #jbgs-geometry-3d-v1 .panel { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--card); }
    #jbgs-geometry-3d-v1 .panel-title { padding: 8px 10px 0; font-size: 13px; font-weight: 600; }
    #jbgs-geometry-3d-v1 canvas { display: block; width: 100%; height: 430px; cursor: grab; touch-action: none; }
    #jbgs-geometry-3d-v1 canvas:active { cursor: grabbing; }
    #jbgs-geometry-3d-v1 .viz-controls { margin-bottom: 10px; }
    #jbgs-geometry-3d-v1 .legend { color: var(--muted-foreground); margin-top: 8px; }
    #jbgs-geometry-3d-v1 .swatch { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin: 0 4px 0 12px; }
    @media (max-width: 700px) {
      #jbgs-geometry-3d-v1 .plots { grid-template-columns: 1fr; }
      #jbgs-geometry-3d-v1 canvas { height: 390px; }
    }
  </style>
  <div class="viz-controls">
    <label class="form-label" for="jbgs-geometry-mode">Geometry</label>
    <select class="form-select" id="jbgs-geometry-mode">
      <option value="ordinary">Ordinary surface inside footprint</option>
      <option value="high">Global high-Z tail</option>
    </select>
  </div>
  <div class="plots">
    <div class="panel"><div class="panel-title">RAW_DEPTH</div><canvas id="jbgs-raw-canvas" aria-label="Rotatable RAW depth geometry"></canvas></div>
    <div class="panel"><div class="panel-title">MVS_SURFACE_METRIC</div><canvas id="jbgs-fused-canvas" aria-label="Rotatable OpenMVS surface depth geometry"></canvas></div>
  </div>
  <div class="legend text-small" id="jbgs-geometry-legend"></div>
  <script>
    (() => {
      const root = document.getElementById('jbgs-geometry-3d-v1');
      const mode = document.getElementById('jbgs-geometry-mode');
      const legend = document.getElementById('jbgs-geometry-legend');
      const canvases = [document.getElementById('jbgs-raw-canvas'), document.getElementById('jbgs-fused-canvas')];
      const data = __DATA__;
      const css = getComputedStyle(root);
      const color = name => css.getPropertyValue(name).trim();
      const palette = {
        raw: '#2563eb',
        fused: '#f97316',
        reference: '#737373',
        foreground: color('--foreground') || '#171717',
        border: color('--border') || '#d4d4d4',
        card: color('--card') || '#ffffff'
      };
      const state = { azimuth: -0.95, elevation: 0.48, zoom: 1.0 };
      const rows = source => source.x.map((x, i) => [x, source.y[i], source.z[i], source.opacity ? source.opacity[i] : 1]);
      const footprint = z => data.footprint.x.map((x, i) => [x, data.footprint.y[i], z, 1]);
      const tracesFor = arm => mode.value === 'ordinary'
        ? [{ points: rows(data.ordinary.mvs), color: palette.reference, alpha: 0.24, size: 1.3 },
           { points: rows(data.ordinary[arm]), color: arm === 'RAW_DEPTH' ? palette.raw : palette.fused, alpha: 0.72, size: 2.0 }]
        : [{ points: rows(data.high_z[arm]), color: arm === 'RAW_DEPTH' ? palette.raw : palette.fused, alpha: 0.70, size: 2.6, opacityScale: true }];
      const project = (point, center) => {
        const x = point[0] - center[0], y = point[1] - center[1], z = point[2] - center[2];
        const ca = Math.cos(state.azimuth), sa = Math.sin(state.azimuth);
        const ce = Math.cos(state.elevation), se = Math.sin(state.elevation);
        const xr = ca * x - sa * y;
        const yr = sa * x + ca * y;
        return [xr, -ce * z + se * yr, se * z + ce * yr, point[3]];
      };
      const worldBounds = () => {
        const sources = mode.value === 'ordinary'
          ? [data.ordinary.mvs, data.ordinary.RAW_DEPTH, data.ordinary.MVS_SURFACE_METRIC]
          : [data.high_z.RAW_DEPTH, data.high_z.MVS_SURFACE_METRIC];
        const values = sources.flatMap(rows);
        const center = [0, 0, (Math.min(...values.map(p => p[2])) + Math.max(...values.map(p => p[2]))) / 2];
        return { values, center };
      };
      const draw = (canvas, arm) => {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.max(1, Math.round(rect.width * dpr));
        canvas.height = Math.max(1, Math.round(rect.height * dpr));
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr); ctx.clearRect(0, 0, rect.width, rect.height);
        const { values, center } = worldBounds();
        const projectedAll = values.map(p => project(p, center));
        const maxAbsX = Math.max(1, ...projectedAll.map(p => Math.abs(p[0])));
        const maxAbsY = Math.max(1, ...projectedAll.map(p => Math.abs(p[1])));
        const scale = 0.83 * state.zoom * Math.min(rect.width / (2 * maxAbsX), rect.height / (2 * maxAbsY));
        const sx = p => rect.width / 2 + p[0] * scale;
        const sy = p => rect.height / 2 + p[1] * scale;
        const boundary = footprint(mode.value === 'ordinary' ? 563 : 650).map(p => project(p, center));
        ctx.strokeStyle = palette.foreground; ctx.lineWidth = 1.4; ctx.beginPath();
        boundary.forEach((p, i) => i ? ctx.lineTo(sx(p), sy(p)) : ctx.moveTo(sx(p), sy(p))); ctx.stroke();
        tracesFor(arm).forEach(trace => {
          const plotted = trace.points.map(p => project(p, center)).sort((a, b) => a[2] - b[2]);
          ctx.fillStyle = trace.color;
          plotted.forEach(p => {
            ctx.globalAlpha = trace.opacityScale ? Math.max(0.16, trace.alpha * p[3]) : trace.alpha;
            ctx.beginPath(); ctx.arc(sx(p), sy(p), trace.size, 0, Math.PI * 2); ctx.fill();
          });
        });
        ctx.globalAlpha = 1; ctx.fillStyle = palette.foreground; ctx.font = '12px sans-serif';
        const count = mode.value === 'ordinary' ? data.counts[arm].fused_inside_footprint : data.counts[arm].z_gt_650;
        ctx.fillText(`${mode.value === 'ordinary' ? 'inside-footprint fused points' : 'Z>650 Gaussians'}: ${count.toLocaleString()}`, 10, rect.height - 12);
      };
      const render = () => {
        draw(canvases[0], 'RAW_DEPTH'); draw(canvases[1], 'MVS_SURFACE_METRIC');
        legend.innerHTML = mode.value === 'ordinary'
          ? `<span class="swatch" style="background:${palette.reference}"></span>MVS reference <span class="swatch" style="background:${palette.raw}"></span>RAW surface <span class="swatch" style="background:${palette.fused}"></span>MVS-depth surface · drag to rotate · wheel to zoom`
          : `<span class="swatch" style="background:${palette.raw}"></span>RAW high-Z <span class="swatch" style="background:${palette.fused}"></span>MVS-depth high-Z · opacity controls point transparency · footprint is the small outline at Z=650`;
      };
      let drag = null;
      canvases.forEach(canvas => {
        canvas.addEventListener('pointerdown', event => { drag = [event.clientX, event.clientY]; canvas.setPointerCapture(event.pointerId); });
        canvas.addEventListener('pointermove', event => {
          if (!drag) return;
          state.azimuth += (event.clientX - drag[0]) * 0.008;
          state.elevation = Math.max(-1.35, Math.min(1.35, state.elevation + (event.clientY - drag[1]) * 0.006));
          drag = [event.clientX, event.clientY]; render();
        });
        canvas.addEventListener('pointerup', () => { drag = null; });
        canvas.addEventListener('pointercancel', () => { drag = null; });
        canvas.addEventListener('wheel', event => { event.preventDefault(); state.zoom = Math.max(0.55, Math.min(2.8, state.zoom * Math.exp(-event.deltaY * 0.001))); render(); }, { passive: false });
      });
      mode.addEventListener('change', render);
      new ResizeObserver(render).observe(root);
      render();
    })();
  </script>
</div>'''.replace("__DATA__", encoded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(fragment + "\n")
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size}))


if __name__ == "__main__":
    main()
