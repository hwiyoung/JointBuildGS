"""Bind immutable parent inputs and choose common input-only ramp thresholds."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np
from PIL import Image

from common import read, record, require_docker, sha, write_new


def select_evenly(values, count):
    if len(values) <= count:
        return values.copy()
    return values[np.linspace(0, len(values) - 1, count, dtype=np.int64)]


def main():
    require_docker()
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/config.json')
    parser.add_argument('--output', default='/output')
    args = parser.parse_args()
    cfg = read(args.config)
    output = Path(args.output)
    if (output/'input_binding.json').exists():
        raise FileExistsError('Input binding already exists')
    started = time.time()
    binding = {'task_id':cfg['task_id'], 'scientific_verdict':None, 'config':record(args.config),
               'reference_accessed':False, 'regions':{}, 'threshold_policy':cfg['local_weight']}
    regional_samples = []
    for region in cfg['regions']:
        root = Path('/parent_inputs')/region
        manifest = read(root/'input_manifest.json')
        if manifest['status'] != 'INPUTS_SEALED_FOR_EXECUTION' or manifest['region'] != region:
            raise ValueError('Parent input seal is invalid')
        for item in manifest['files']:
            source = root/item['path']
            if not source.resolve().is_relative_to(root.resolve()):
                raise ValueError('Unexpected source escape')
            if sha(source) != item['sha256']:
                raise ValueError('Parent input hash mismatch: '+str(source))
        anchor = Path('/anchors')/region
        receipt = read(anchor/'receipt.json')
        checkpoint = record(anchor/'checkpoint.pth')
        if receipt['iteration'] != 8000 or checkpoint['sha256'] != receipt['checkpoint_sha256']:
            raise ValueError('Complete Anchor8k identity differs')
        samples = []
        views = []
        sizes = set()
        paths = manifest['training_paths']
        for item in manifest['images']:
            if item['role'] != 'train':
                continue
            name = Path(item['name']).stem
            image_path = root/'scene/images'/item['name']
            with Image.open(image_path) as image:
                size = image.size
            sizes.add(size)
            prior_path = root/paths['prior_depth']/'raw_depth'/f'{name}.npy'
            visual_path = root/paths['da3_depth']/'raw_depth'/f'{name}.npy'
            if not prior_path.is_file() or not visual_path.is_file():
                views.append({'name':name,'available_both':False})
                continue
            prior = cv2.resize(np.load(prior_path, allow_pickle=False), size, interpolation=cv2.INTER_LINEAR)
            visual = cv2.resize(np.load(visual_path, allow_pickle=False), size, interpolation=cv2.INTER_LINEAR)
            valid = np.isfinite(prior) & np.isfinite(visual) & (prior > 0) & (visual > 0)
            valid_indices = np.flatnonzero(valid.ravel())
            selected = select_evenly(valid_indices, cfg['local_weight']['samples_per_train_view'])
            values = np.abs(prior.ravel()[selected]-visual.ravel()[selected]).astype(np.float64)
            if len(values): samples.append(values)
            views.append({'name':name, 'available_both':True, 'size':size, 'valid_pixels':len(valid_indices),
                          'sampled_pixels':len(values), 'selection_indices_sha256':__import__('hashlib').sha256(selected.tobytes()).hexdigest(),
                          'prior_sha256':sha(prior_path), 'visual_sha256':sha(visual_path)})
        if len(sizes) != 1:
            raise ValueError('Mixed image sizes require exact native first-camera resize policy')
        if not samples:
            raise ValueError('No paired training targets in '+region)
        values = select_evenly(np.concatenate(samples), cfg['local_weight']['max_samples_per_region'])
        regional_samples.append(values)
        binding['regions'][region] = {'manifest':record(root/'input_manifest.json'), 'checkpoint':checkpoint,
            'anchor_receipt':record(anchor/'receipt.json'), 'training_paths':paths, 'views':views,
            'sample_quantiles_m':np.quantile(values,[0,.25,.5,.75,.9,.95,1]).tolist(),
            'verified_input_file_count':len(manifest['files'])}
    common_count = min(map(len, regional_samples))
    pooled = np.concatenate([select_evenly(values, common_count) for values in regional_samples])
    tau0, tau1 = np.quantile(pooled,cfg['local_weight']['threshold_quantiles']).tolist()
    if not np.isfinite([tau0,tau1]).all() or not 0 <= tau0 < tau1:
        raise ValueError('Degenerate threshold distribution; no arbitrary fallback')
    np.savez_compressed(output/'threshold_samples.npz', **{region:select_evenly(values,common_count) for region,values in zip(cfg['regions'],regional_samples)})
    binding.update(status='INPUTS_AND_COMMON_THRESHOLDS_FROZEN', tau0_m=tau0, tau1_m=tau1,
        samples_per_region=common_count, threshold_samples=record(output/'threshold_samples.npz'),
        wall_seconds=time.time()-started)
    write_new(output/'input_binding.json',binding)
    print(json.dumps({'status':binding['status'],'tau0_m':tau0,'tau1_m':tau1,'samples_per_region':common_count,
                      'seconds':binding['wall_seconds'],'scientific_verdict':None}))


if __name__ == '__main__':
    main()
