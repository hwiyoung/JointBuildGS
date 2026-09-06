"""Compare saved evaluation RGB on one frozen source-derived ray denominator.

Eight-bit saved renders are used; this is separate from B's float-image scores.
Missing/black predictions remain in the mask. No reference geometry is used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import cv2
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.write('\n')


def main(args):
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    inputs, results = {}, []
    base = args.b_root[0]
    anchors = [args.prior_anchor or base/'geometry_fixed', base/'image_only']
    if not all((p/'result.json').exists() for p in anchors):
        raise ValueError('Completed main prior geometry_fixed and image_only anchors required')
    view_path = base/'views.json'
    views = [v for v in json.loads(view_path.read_text())['views'] if v['role']=='eval']
    inputs[str(view_path)] = sha(view_path)
    masks, targets = {}, {}
    for v in views:
        i = v['image_id']
        masks[i] = np.zeros((v['height'], v['width']), bool)
        for folder in anchors:
            path = folder/f'observation_support_{i}.png'
            m = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if m is None or m.shape != masks[i].shape:
                raise ValueError(f'Invalid frozen observation support: {path}')
            masks[i] |= m > 0
            inputs[str(path)] = sha(path)
        target_path = anchors[0]/f'target_{i}.png'
        targets[i] = cv2.imread(str(target_path), cv2.IMREAD_COLOR).astype(np.float64)/255.
        inputs[str(target_path)] = sha(target_path)
        cv2.imwrite(str(args.output/f'common_support_{i}.png'), masks[i].astype(np.uint8)*255)
    for root in args.b_root:
        other_views_path = root/'views.json'
        other = {v['image_id']: v for v in json.loads(other_views_path.read_text())['views']}
        inputs[str(other_views_path)] = sha(other_views_path)
        for v in views:
            o = other[v['image_id']]
            for key in ['K', 'viewmat', 'width', 'height', 'role']:
                if o[key] != v[key]:
                    raise ValueError(f'Different fixed evaluation camera: {root} {v["image_id"]} {key}')
        for result_path in sorted(root.glob('*/result.json')):
            folder = result_path.parent
            if f'{root.name}/{folder.name}' in args.exclude_arm:
                continue
            if not (folder/'gaussians_final.npz').exists():
                continue
            record = dict(run=root.name, arm=folder.name, stages={})
            inputs[str(result_path)] = sha(result_path)
            for phase in ['initial', 'final']:
                per_view, ae, se, count, retained, rgb_retained = [], 0., 0., 0, 0, 0
                for v in views:
                    i, mask = v['image_id'], masks[v['image_id']]
                    rgb_path, alpha_path = folder/f'{phase}_rgb_{i}.png', folder/f'{phase}_alpha_{i}.npy'
                    mass_path = folder/f'{phase}_geometry_mass_{i}.npy'
                    target_path = folder/f'target_{i}.png'
                    if sha(target_path) != inputs[str(anchors[0]/f'target_{i}.png')]:
                        raise ValueError(f'Target bytes differ: {target_path}')
                    rgb = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR).astype(np.float64)/255.
                    alpha = np.load(alpha_path, allow_pickle=False)
                    mass = np.load(mass_path, allow_pickle=False)
                    if rgb.shape != targets[i].shape or alpha.shape != mask.shape or mass.shape != mask.shape:
                        raise ValueError(f'Image dimensions differ: {rgb_path}')
                    if not np.isfinite(mass).all() or np.any((mass < -1e-6) | (mass > 1+1e-6)):
                        raise ValueError(f'Invalid independent plane-hit mass: {mass_path}')
                    if not np.isfinite(alpha).all() or np.any((alpha < -1e-6) | (alpha > 1+1e-6)):
                        raise ValueError(f'Invalid RGB alpha: {alpha_path}')
                    error = (rgb-targets[i])[mask]
                    n, present = int(mask.sum()), int((mass[mask]>=.5).sum())
                    rgb_present = int((alpha[mask]>=.5).sum())
                    aa, ss = float(np.abs(error).sum()), float(np.square(error).sum())
                    per_view.append(dict(image_id=i, pixels=n, present_pixels=present, rgb_alpha_present_pixels=rgb_present,
                                         mae=aa/(3*n) if n else None,
                                         psnr_db=float(-10*np.log10(max(ss/(3*n), 1e-12))) if n else None))
                    ae += aa; se += ss; count += n; retained += present
                    rgb_retained += rgb_present
                    for path in [rgb_path, alpha_path, mass_path, target_path]: inputs[str(path)] = sha(path)
                record['stages'][phase] = dict(pixels=count, present_pixels=retained,
                    missing_pixels=count-retained, presence_fraction=retained/count if count else None,
                    rgb_alpha_presence_fraction=rgb_retained/count if count else None,
                    mae=ae/(3*count) if count else None,
                    psnr_db=float(-10*np.log10(max(se/(3*count),1e-12))) if count else None, per_view=per_view)
            results.append(record)
    if any(sha(p)!=h for p,h in inputs.items()): raise RuntimeError('Input changed')
    write(args.output/'appearance.json', dict(scientific_verdict=None, arms=results,
        mask='union of preoptimization conditional observation_support from main ALS geometry_fixed and MVS image_only; frozen for all arms including density controls',
        value_precision='saved RGB PNG uint8, clamped by renderer export; B float-image scores are separate',
        presence_definition='independent plane-hit geometry_mass >= 0.5; RGB low-pass alpha presence is separately reported',
        limitations='source-conditioned foreground masks can be wrong; camera/MVS shared errors remain; mask is not certified current surface area',
        input_sha256=inputs))
    shutil.copyfile(__file__, args.output/'source_snapshot.py')
    write(args.output/'technical_receipt.json', dict(
        task_id='PHD-P2-AB-V2-C-COMMON-APPEARANCE', status='COMMON_MASK_APPEARANCE_COMPLETE',
        scientific_verdict=None, arms=len(results), excluded_arms=args.exclude_arm,
        anchors=[str(p) for p in anchors], input_sha256=inputs, source_sha256=sha(__file__),
        git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'), container_image=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        versions=dict(numpy=np.__version__, opencv=cv2.__version__), elapsed_seconds=time.monotonic()-started))
    print(json.dumps({'arms':len(results),'common_pixels':int(sum(m.sum() for m in masks.values()))}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--b-root',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prior-anchor',type=Path)
    parser.add_argument('--exclude-arm',action='append',default=[])
    main(parser.parse_args())
