"""Logging-only wrappers; each original method called exactly once, without RNG use."""
import json
import os
import runpy
import sys
from pathlib import Path
import numpy as np

source = Path(os.environ['GEOGS_SOURCE'])
output = Path(os.environ['GEOGS_OBSERVATIONS'])
output.mkdir(parents=True, exist_ok=True)
os.chdir(source)
sys.path.insert(0, str(source))
from scene.gaussian_model import GaussianModel
from scene import Scene

log = (output / 'events.jsonl').open('a', buffering=1)
context = []
counters = {'added': 0, 'removed': 0, 'clone_added': 0, 'split_added': 0,
            'split_parents_removed': 0, 'culled': 0}

def emit(x):
    log.write(json.dumps(x) + '\n')

def wrap(name):
    original = getattr(GaussianModel, name)
    def observed(self, *args, **kwargs):
        before = len(self.get_xyz)
        parent = context[-1] if context else None
        context.append(name)
        try:
            result = original(self, *args, **kwargs)
        finally:
            context.pop()
        after = len(self.get_xyz)
        if name == 'densification_postfix':
            n = after - before
            counters['added'] += n
            if parent == 'densify_and_clone': counters['clone_added'] += n
            if parent == 'densify_and_split': counters['split_added'] += n
        if name == 'prune_points':
            n = before - after
            counters['removed'] += n
            counters['split_parents_removed' if parent == 'densify_and_split' else 'culled'] += n
        if name == 'densify_and_prune':
            emit(dict(event=name, before=before, after=after, **counters))
        if name == 'set_frozen_mask':
            np.savez(output / 'actual_protection_registration.npz',
                     xyz=self.get_xyz.detach().cpu().numpy(),
                     mask=self.frozen_mask.detach().cpu().numpy())
            emit(dict(event=name, count=int(self.frozen_mask.sum().item()), total=after))
        return result
    setattr(GaussianModel, name, observed)

for name in ['densify_and_clone', 'densify_and_split', 'densification_postfix',
             'prune_points', 'densify_and_prune', 'set_frozen_mask']:
    wrap(name)
original_save = Scene.save

def save(self, iteration, *args, **kwargs):
    result = original_save(self, iteration, *args, **kwargs)
    mask = self.gaussians.frozen_mask
    if mask is not None:
        np.save(output / f'frozen_mask_{iteration}.npy', mask.detach().cpu().numpy())
    emit(dict(event='save', iteration=iteration, total=len(self.gaussians.get_xyz), **counters))
    return result
Scene.save = save
sys.argv[0] = str(source / 'train.py')
runpy.run_path(str(source / 'train.py'), run_name='__main__')
emit(dict(event='completed', **counters))
