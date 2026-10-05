"""Freeze a reviewable task bundle without touching parent inputs or runs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mask-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--config', default='/repo/configs/phd/p1_single_view_weight_v1/experiment_v2.json')
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    out, source = Path(args.output), Path(args.mask_dir)
    out.mkdir(exist_ok=True)
    if (out / 'config.json').exists():
        raise FileExistsError('An experiment bundle is immutable')
    mask = source / 'r1_mask.npz'
    if not mask.is_file():
        raise FileNotFoundError(mask)
    import numpy as np
    with np.load(mask, allow_pickle=False) as arrays:
        r1 = arrays['r1_mask']
        use = arrays['use_mask']
        if r1.dtype != np.bool_ or r1.shape != (1013, 1400) or not r1.any():
            raise ValueError('Unexpected RGB boolean intervention mask')
        if use.dtype != np.bool_ or use.shape != r1.shape or np.any(r1 & ~use):
            raise ValueError('Unexpected frozen manually classified support')
        count = int(r1.sum())
    shutil.copytree(source, out / 'mask')
    script_root = Path('/repo/scripts/phd/p1_single_view_weight_v1')
    shutil.copytree(script_root, out / 'scripts')
    shutil.copytree('/repo/scripts/phd/geogs_mvs_pgsr_v1', out / 'parent_scripts')
    shutil.copytree('/repo/scripts/phd/geogs_p1p2p3_v1', out / 'legacy_scripts')
    shutil.copytree('/repo/src/phd/p1_single_view_weight_v1', out / 'implementation')
    cfg = json.loads(Path(args.config).read_text())
    cfg.update(mask_sha256=sha(out / 'mask/r1_mask.npz'), mask_rgb_pixels=count,
               used_rgb_pixels=int(use.sum()),
               created_unix=time.time(), repository_head=Path('/repository_head.txt').read_text().strip())
    (out / 'config.json').write_text(json.dumps(cfg, indent=2) + '\n')
    receipt = dict(task_id=cfg['task_id'], status='FROZEN_BUNDLE', scientific_verdict=None,
                   config_sha256=sha(out / 'config.json'), mask_sha256=cfg['mask_sha256'],
                   source_preparation_pending=True)
    (out / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
