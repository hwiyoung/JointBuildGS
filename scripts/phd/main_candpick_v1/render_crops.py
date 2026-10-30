"""Photographs, locked place overlays, and start/end crops of wrong-start arms."""
import argparse
import json
from pathlib import Path
import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image
from gs_engine import Scene, cameras, photo, project, tensor
from plot_results import setup, write
from representative_figures import NAMES, COLORS
from input_audit import sha
from result_io import save

OUT, DOC = Path('/out'), Path('/docs')


def load_snapshot(scene, path):
    with np.load(path) as z, torch.no_grad():
        scene.opacity.copy_(tensor(z['opacity_logits']))
        scene.dc.copy_(tensor(z['color_dc']))
        scene.rest.copy_(tensor(z['color_sh']))


def overlay(image, d, ids, cam):
    base = image.copy(); mask = np.zeros(image.shape[:2], np.uint8)
    offsets = np.array([[-.25, -.25], [.25, -.25], [.25, .25], [-.25, .25]])
    c, a, b, n, m = [d[k][ids] for k in ['centre', 'tangent1', 'tangent2', 'normal', 'mvs_p']]
    cells = c[:, None] + a[:, None] * offsets[None, :, :1] + b[:, None] * offsets[None, :, 1:]
    polygons = []
    for kind, height in enumerate([np.zeros_like(m), m]):
        uv, depth = project((cells + n[:, None] * height[:, None, None]).reshape(-1, 3), cam)
        uv = (uv - .5).reshape(-1, 4, 2)
        color = (188, 132, 37) if kind == 0 else (40, 108, 158)
        for points in uv:
            p = np.rint(points).astype(np.int32)
            cv2.fillConvexPoly(mask, p, 1)
            polygons.append((p, color))
    base[mask > 0] = np.rint(.84 * base[mask > 0] + .16 * np.array([255, 245, 170])).astype(np.uint8)
    for p, color in polygons: cv2.polylines(base, [p], True, color, 1, cv2.LINE_AA)
    return base


def run(unit, photos_only=False):
    setup(); root = DOC / 'figures/representatives'; root.mkdir(parents=True, exist_ok=True)
    index = json.loads((OUT / 'render_masks' / unit / 'index.json').read_text())
    reps = [r for r in json.loads((DOC / 'representatives_v1.json').read_text())['rows'] if r['unit'] == unit and r['selection']]
    if not reps: return
    with np.load(OUT / 'places' / (unit + '.npz')) as z: d = {k: z[k] for k in z.files}
    scene = None if photos_only else Scene(unit, start='wrong', sh_degree=3)
    cams = {c['name']: c for c in (cameras(unit) if photos_only else scene.cams)}
    outputs = []
    for rep in reps:
        ids = np.flatnonzero(np.isin(d['point_id'], rep['selection']['point_ids']))
        selections = index['representative_views'][rep['id']]['views']
        for number, view in enumerate(selections, 1):
            cam = cams[view['view']]; actual = photo(cam); annotated = overlay(actual, d, ids, cam)
            x0, y0, x1, y1 = view['crop']; sl = np.s_[y0:y1, x0:x1]
            fig, axes = plt.subplots(1, 2, figsize=(12, 6))
            axes[0].imshow(actual); axes[0].set_title('학습 사진 전체')
            import matplotlib.patches as patches
            axes[0].add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor='#f5c547', linewidth=1.5))
            axes[1].imshow(annotated[sl], interpolation='nearest'); axes[1].set_title('고정 대표 자리 확대')
            for ax in axes: ax.axis('off')
            fig.suptitle(NAMES[rep['id']] + f' · 관측 {number}', fontsize=16)
            fig.text(.5, .02, '황색 선=사전 정보 후보 자리 · 청색 선=영상 후보 자리\n' + cam['name'], ha='center', fontsize=10)
            fig.tight_layout(rect=[0, .08, 1, .94]); path = root / f"{rep['id']}_photo_overlay_{number}"; write(fig, path)
            outputs.append(path.name + '.png')
            if photos_only: continue
            fig, axes = plt.subplots(2, 3, figsize=(12, 8))
            for row, degree in enumerate([3, 0]):
                scene.sh_degree = degree
                axes[row, 0].imshow(actual[sl], interpolation='nearest'); axes[row, 0].set_title(f'SH{degree} 비교 · 실제 사진')
                for col, step in enumerate([0, 3000], 1):
                    runroot = OUT / 'runs' / f'cp_wrong_sh{degree}_{unit}'
                    assert (runroot / 'complete.json').exists()
                    load_snapshot(scene, runroot / f'candidate_{step}.npz')
                    with torch.no_grad(): rendered = scene.render(cam)[0][0].cpu().numpy()
                    axes[row, col].imshow(np.clip(rendered[sl], 0, 1), interpolation='nearest')
                    axes[row, col].set_title(f'SH{degree} · {step:,}회 렌더')
                    dest = OUT / 'visuals' / rep['id']; dest.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(np.rint(np.clip(rendered[sl], 0, 1) * 255).astype(np.uint8)).save(dest / f'view{number}_sh{degree}_{step}.png')
                for ax in axes[row]: ax.axis('off')
            fig.suptitle(NAMES[rep['id']] + f' · 관측 {number} · 출발 틀림', fontsize=16)
            fig.text(.5, .015, '같은 학습 사진·같은 자르기 범위. 밝기·색 보정 없음.\n' + cam['name'], ha='center', fontsize=10)
            fig.tight_layout(rect=[0, .07, 1, .95]); path = root / f"{rep['id']}_render_comparison_{number}"; write(fig, path)
            outputs.append(path.name + '.png')
    save(root / (unit + ('_overlays_index.json' if photos_only else '_photos_index.json')), dict(unit=unit, files=outputs,
        locked_view_index_sha256=sha(OUT / 'render_masks' / unit / 'index.json'), script_sha256=sha(__file__), scientific_verdict=None))
    print(unit, len(outputs), 'photo/comparison figures')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('units', nargs='+'); p.add_argument('--photos-only', action='store_true'); args = p.parse_args()
    for unit in args.units: run(unit, args.photos_only)
