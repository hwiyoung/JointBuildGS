"""Verify saved view order, export case tables, and plot an inspection contact sheet."""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).resolve().parents[1] / 'r1r5_comparison_v1'))
from analyze_final_surfaces import read, write, sha


def main(attempt, review_path):
    cfg = read(attempt / 'config.json'); review = read(review_path)
    root = Path(cfg['artifact_root']) / cfg['comparison_relative']; run = read(root / 'config.json')
    output = attempt / 'review'; output.mkdir(exist_ok=False)
    inspected = {c['case']['id']: c for c in read(attempt / 'inspection/receipt.json')['cases']}
    components = read(attempt / 'result/components.json')['components']
    view_checks = []; crops = {}; rows = []
    for cid, decision in review['cases'].items():
        item = inspected[cid]; c = item['case']; r = c['region']; xyz = np.load(attempt / 'result' / (r + '_sample_diagnostic.npz'))['xyz'][c['sample_indices']]
        inp = Path(cfg['artifact_root']) / run['r1_prep_relative'] / 'result/input' if r == 'R1' else root / r / 'preparation/input'
        views = {v['name']: v for v in read(inp / 'scene/split_manifest.json')['train']}
        for vi, obs in enumerate(item['observations']):
            source_image = np.asarray(Image.open(obs['image_path']).convert('RGB'))
            for branch, rec in obs['provenance'].items():
                if branch not in ['mvs', 'da3', 'local_prior0']: continue
                path = Path(rec['path']).parent.parent / 'gt' / ('%05d.png' % obs['rendered_view_index'])
                actual = np.asarray(Image.open(path).convert('RGB'))
                assert actual.shape == source_image.shape
                error = int(np.max(abs(actual.astype(np.int16) - source_image.astype(np.int16))))
                assert error <= 1, (cid, obs['name'], branch, error)
                view_checks.append(dict(case=cid, view=obs['name'], branch=branch, max_rgb_code_difference=error,
                                        gt_sha256=sha(path), source_sha256=obs['image_sha256']))
            v = views[obs['name']]; cam = xyz @ np.array(v['R']).T + v['t']; q = cam @ np.array(v['K']).T; uv = q[:, :2] / q[:, 2, None]
            xy = np.rint(uv).astype(int); inside = (cam[:, 2] > 0) & (xy[:, 0] >= 0) & (xy[:, 0] < v['width']) & (xy[:, 1] >= 0) & (xy[:, 1] < v['height'])
            maskpath = root / r / 'masks' / (Path(v['name']).stem + '.npy'); mask = np.load(maskpath)
            view_checks.append(dict(case=cid, view=obs['name'], existing_release_projection_count=int(mask[xy[inside, 1], xy[inside, 0]].sum()),
                                    in_frame_points=int(inside.sum()), mask_sha256=sha(maskpath)))
            if vi == 0:
                im = Image.fromarray(source_image); pts = uv[inside]; lo = pts.min(0); hi = pts.max(0); center = (lo + hi) / 2
                half = max(80., np.max(hi-lo) * .85); box = [max(0, int(center[0]-half)), max(0, int(center[1]-half)), min(im.width, int(center[0]+half)), min(im.height, int(center[1]+half))]
                crop = im.crop(box); draw = ImageDraw.Draw(crop)
                for x, y in pts: draw.ellipse([x-box[0]-2, y-box[1]-2, x-box[0]+2, y-box[1]+2], fill='#ff1646')
                crops[cid] = np.asarray(crop)
                crop.save(output / (cid + '_detail.png'))
        rows.append(dict(id=cid, region=r, zone=c['zone'], name=decision['name'], status=decision['status'],
            n=c['n'], u=c['center_uvz'][0], v=c['center_uvz'][1], local_z=c['center_uvz'][2],
            easting=c['centroid_epsg25832'][0], northing=c['centroid_epsg25832'][1], source_z=c['centroid_epsg25832'][2],
            median_prior_distance_m=c['prior_surface']['median'], median_mvs_geogs_distance_m=c['output_surface']['mvs']['median'],
            median_da3_geogs_distance_m=c['output_surface']['da3']['median'], median_views=c['views']['median'],
            separated_common_views=len(item['observations']), note=decision['note']))
    with (output / 'reviewed_sites.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    with (output / 'all_components.csv').open('w') as f:
        fields = ['id', 'region', 'zone', 'branch', 'category', 'context', 'direction', 'n', 'u', 'v', 'local_z', 'prior_m', 'mvs_geogs_m', 'da3_geogs_m']
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for c in components:
            w.writerow({**{k: c[k] for k in fields[:8]}, **dict(zip(fields[8:11], c['center_uvz'])),
                'prior_m': c['prior_surface']['median'], 'mvs_geogs_m': c['output_surface']['mvs']['median'], 'da3_geogs_m': c['output_surface']['da3']['median']})
    fig, axs = plt.subplots(2, 2, figsize=(13, 12))
    for ax, cid in zip(axs.ravel(), review['sheet_ids']):
        c = inspected[cid]['case']; ax.imshow(crops[cid], interpolation='nearest'); ax.axis('off')
        ax.set_title(f"{cid}  {c['region']} {c['zone']}   u/v/z = " + '/'.join('%.1f' % x for x in c['center_uvz']) + '\n' +
                     'MVS point to surface: Prior %.2fm | MVS-GeoGS %.2fm | DA3-GeoGS %.2fm' % (c['prior_surface']['median'], c['output_surface']['mvs']['median'], c['output_surface']['da3']['median']), fontsize=10)
    fig.suptitle('Four locations with different causes to review\nRed: projected candidate samples. Crop enlargement adds no image evidence.', fontsize=13)
    fig.tight_layout(); fig.savefig(output / 'candidate_sheet.png', dpi=150); plt.close(fig)
    # Unique native fused-MVS row identity avoids double counting overlapping regions.
    unique = {}
    for branch in cfg['branches']:
        ids = []
        for r in cfg['regions']:
            a = np.load(attempt / 'result' / (r + '_sample_diagnostic.npz'))
            ids.extend(a['source_rows'][a[branch + '_little_gain']].tolist())
        unique[branch] = dict(region_sum=len(ids), unique_source_rows=len(set(ids)))
    write(output / 'receipt.json', dict(status='PASS_REVIEW_EXPORT_AND_RENDER_VIEW_IDENTITY', scientific_verdict=None,
        review=review, view_checks=view_checks, unique_point_counts=unique, rows=rows,
        source_hashes={str(Path(__file__)): sha(__file__), str(review_path): sha(review_path)},
        inspection_receipt_sha256=sha(attempt / 'inspection/receipt.json'), search_receipt_sha256=sha(attempt / 'result/receipt.json'),
        files={p.name: sha(p) for p in output.iterdir() if p.is_file()},
        caveat='No global weight sweep or causal intervention; agent visual descriptions are not semantic ground truth.'))
    print(json.dumps(dict(status='PASS', checks=len(view_checks), unique=unique), ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--attempt', type=Path, required=True); p.add_argument('--review', type=Path, required=True)
    a = p.parse_args(); main(a.attempt, a.review)
