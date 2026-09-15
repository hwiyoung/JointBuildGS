"""Inspect frozen candidate points in supported source views and saved depth renders."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

sys.path.append(str(Path(__file__).resolve().parents[1] / 'r1r5_comparison_v1'))
from analyze_final_surfaces import read, write, sha
from search import number_stats


def main(attempt, selected):
    cfg = read(attempt / 'config.json'); art = Path(cfg['artifact_root'])
    root = art / cfg['comparison_relative']; run = read(root / 'config.json')
    cases = {c['id']: c for c in read(attempt / 'result/components.json')['components']}
    out = attempt / 'inspection'; out.mkdir(exist_ok=False)
    results = []; inputs = {}
    for cid in selected:
        c = cases[cid]; r = c['region']; ids = np.array(c['sample_indices'])
        a = np.load(attempt / 'result' / (r + '_sample_diagnostic.npz')); xyz = a['xyz'][ids]
        inp = art / run['r1_prep_relative'] / 'result/input' if r == 'R1' else root / r / 'preparation/input'
        evdir = art / cfg['r1_audit_relative'] if r == 'R1' else root / r / 'audit/result'
        pv = np.load(evdir / 'per_view_relations.npz'); relation = pv['mvs'][:, ids]
        membership = {str(name): i for i, name in enumerate(pv['names'])}
        views = sorted(read(inp / 'scene/split_manifest.json')['train'], key=lambda v: v['name'])
        # Camera-depth indices follow the saved renderer's alphabetical train order.
        models = read(root / cfg['analysis'] / (r + '_summary.json'))['metadata']['models']
        support = (relation > 0).sum(1)
        rank = np.argsort(-support, kind='stable'); chosen = []; name_to_v = {v['name']: (i, v) for i, v in enumerate(views)}
        for ri in rank:
            if support[ri] < max(3, len(ids) * .5): continue
            i, v = name_to_v[str(pv['names'][ri])]; R = np.array(v['R']); t = np.array(v['t']); cc = -t @ R
            if any(np.linalg.norm(cc - old[3]) < 8 for old in chosen): continue
            chosen.append((i, v, ri, cc))
            if len(chosen) == 3: break
        canvas = Image.new('RGB', (1560, max(1, len(chosen)) * 630), 'white'); draw = ImageDraw.Draw(canvas)
        obs = []
        for row, (i, v, ri, cc) in enumerate(chosen):
            R = np.array(v['R']); t = np.array(v['t']); cam = xyz @ R.T + t
            q = cam @ np.array(v['K']).T; uv = q[:, :2] / q[:, 2, None]
            x, y = np.rint(uv).astype(int).T
            supported = (relation[ri] > 0) & (cam[:, 2] > 0) & (x >= 0) & (x < v['width']) & (y >= 0) & (y < v['height'])
            use = np.flatnonzero(supported); xx = x[use]; yy = y[use]; stem = Path(v['name']).stem
            vals = {}; provenance = {}
            for key, folder in [('prior', inp / 'prior/raw_depth'), ('mvs_target', inp / 'mvs_rgb/raw_depth')]:
                path = folder / (stem + '.npy'); vals[key] = np.load(path, mmap_mode='r')[yy, xx]
                provenance[key] = dict(path=str(path), sha256=sha(path))
            for branch, model in models.items():
                path = Path(model['path']).parent / 'vis' / f'depth_{i:05}.tiff'
                vals[branch] = np.asarray(Image.open(path))[yy, xx]
                provenance[branch] = dict(path=str(path), sha256=sha(path))
            active = np.isfinite(vals['mvs_target']) & (vals['mvs_target'] > 0) & (abs(vals['mvs_target'] - cam[use, 2]) <= .5)
            metrics = {}
            for branch in models:
                valid = active & np.isfinite(vals[branch]) & (vals[branch] > 0)
                valid_p = valid & np.isfinite(vals['prior']) & (vals['prior'] > 0)
                metrics[branch] = dict(valid_pixels=int(valid.sum()),
                    abs_render_minus_mvs=number_stats(abs(vals[branch][valid] - vals['mvs_target'][valid])),
                    signed_render_minus_mvs=number_stats(vals[branch][valid] - vals['mvs_target'][valid]),
                    prior_like_fraction=float(np.mean((abs(vals[branch][valid_p] - vals['prior'][valid_p]) <= .5) & (abs(vals[branch][valid_p] - vals['mvs_target'][valid_p]) > .5))) if valid_p.any() else None)
            photo = inp / 'scene/images' / v['name']; digest = sha(photo); assert digest == v['sha256']
            im = Image.open(photo).convert('RGB'); assert im.size == (v['width'], v['height'])
            full = im.copy(); dd = ImageDraw.Draw(full)
            pts = uv[use]; lo = pts.min(0); hi = pts.max(0); dd.rectangle([*lo, *hi], outline='#ff1646', width=4)
            for px, py in pts: dd.ellipse([px-3, py-3, px+3, py+3], fill='#ff1646')
            full.thumbnail((900, 580)); canvas.paste(full, (0, row * 630 + 40))
            center = (lo + hi) / 2; half = max(75., np.max(hi - lo) * .8)
            box = [max(0, int(center[0]-half)), max(0, int(center[1]-half)), min(im.width, int(center[0]+half)), min(im.height, int(center[1]+half))]
            crop = im.crop(box); dd = ImageDraw.Draw(crop)
            for px, py in pts: dd.ellipse([px-box[0]-2, py-box[1]-2, px-box[0]+2, py-box[1]+2], fill='#ff1646')
            crop.thumbnail((640, 580)); canvas.paste(crop, (915, row * 630 + 40))
            draw.text((10, row * 630 + 8), f'{cid} {r} {c["zone"]} / {v["name"]} / supported sample projections (red)', fill='black')
            obs.append(dict(name=v['name'], rendered_view_index=i, supported_points=len(use), target_agreeing_points=int(active.sum()),
                camera_center=cc.tolist(), source_gap_camera_z=number_stats(vals['mvs_target'][active]-vals['prior'][active]),
                metrics=metrics, image_path=str(photo), image_sha256=digest, provenance=provenance))
        canvas.save(out / (cid + '_photos.jpg'), quality=93)
        # Reference is a secondary surface-correspondence diagnostic, never a selector.
        ur = root / cfg['uas_analysis'] / (r + '_reference.npz'); ref = np.load(ur)['xyz']; tree = cKDTree(ref)
        near, nearest_ids = tree.query(xyz, workers=2)
        udpath = root / cfg['uas_analysis'] / (r + '_uas_distances.npz'); ud = np.load(udpath)
        prpath = root / cfg['uas_analysis'] / (r + '_uas_to_prior.npy'); pr = np.load(prpath)
        nearby = np.unique(nearest_ids[near <= .5])
        reference = dict(role='SECONDARY_EVALUATION_ONLY_NOT_SELECTION', mvs_to_uas_nearest_point=number_stats(near),
            fraction_mvs_within_05m=float(np.mean(near <= .5)), nearby_unique_uas=len(nearby),
            distances_on_nearby_uas={b: number_stats(d[nearby]) for b, d in [('prior', pr), *[(b, ud[b]) for b in models]]})
        for p in [ur, udpath, prpath]: inputs[str(p)] = sha(p)
        item = dict(case=c, observations=obs, reference=reference, photo=cid+'_photos.jpg', scientific_verdict=None)
        write(out / (cid + '.json'), item); results.append(item)
        print(cid, 'views', len(obs), 'UAS near', reference['fraction_mvs_within_05m'],
            'render residuals', {b: [round(o['metrics'][b]['abs_render_minus_mvs']['median'], 3) if o['metrics'][b]['abs_render_minus_mvs']['median'] is not None else None for o in obs] for b in models}, flush=True)
    write(out / 'receipt.json', dict(status='PASS_SUPPORTED_VIEW_INSPECTION', scientific_verdict=None,
        selected_ids=selected, cases=results, reference_sha256=inputs, script_sha256=sha(__file__),
        limitations=['Three separated supported views are a diagnostic, not all-view loss attribution.',
        'Surface point distance and saved rendered depth are distinct observables; extraction can fail while rendered depth agrees.',
        'Nearest UAS point proximity is not exact same-surface or semantic certification.']))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--attempt', type=Path, required=True); p.add_argument('--ids', nargs='+', required=True)
    a = p.parse_args(); main(a.attempt, a.ids)
