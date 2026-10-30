"""Check all six parameter restrictions per case, without an optimizer step."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import torch
from gs_engine import Scene, tensor
from input_audit import sha
from prepare_places import save


def run(unit):
    dest = Path('/out/preflight') / (unit + '_variants.json')
    assert not dest.exists(), dest
    probe = json.loads((Path('/docs/preflight') / (unit + '_all_views.json')).read_text())
    scene = Scene(unit)
    cam = next(c for c in scene.cams if c['name'] == probe['gradient_view'])
    with np.load(Path('/out/scenes') / unit / 'initial_right_candidate.npz') as z:
        right = z['right_candidate']
    frozen = {**{'base.' + k: v for k, v in scene.base.items()},
              **{'candidate.' + k: v for k, v in scene.geometry.items()}}
    checks = []
    for degree in [3, 0]:
        scene.sh_degree = degree
        scene.rest.requires_grad_(degree == 3)
        for start, (a, b) in [('right', (.9, .1)), ('wrong', (.1, .9)), ('equal', (.5, .5))]:
            initial = np.where(np.arange(2)[None] == right[:, None], a, b)
            values = tensor(np.repeat(initial[:, :, None], 4, axis=2).reshape(-1))
            with torch.no_grad(): scene.opacity.copy_(torch.logit(values))
            for p in [scene.opacity, scene.dc, scene.rest]: p.grad = None
            image = scene.render(cam)[0][0]
            loss = scene.loss(image, cam)
            loss.backward()
            params = [('opacity', scene.opacity), ('color_dc', scene.dc), ('color_sh', scene.rest)]
            trainable = {k: dict(requires_grad=v.requires_grad, grad_exists=v.grad is not None,
                grad_finite=bool(torch.isfinite(v.grad).all()) if v.grad is not None else None,
                nonzero=int(torch.count_nonzero(v.grad)) if v.grad is not None else 0) for k, v in params}
            fixed = all(not v.requires_grad and v.grad is None for v in frozen.values())
            active = all(v['grad_exists'] and v['grad_finite'] and v['nonzero'] > 0
                         if v['requires_grad'] else not v['grad_exists'] for v in trainable.values())
            row = dict(start=start, sh_degree=degree, status='PASS' if fixed and active else 'FAIL',
                       frozen_gradient_zero=fixed, trainable=trainable, loss=float(loss.detach()))
            checks.append(row)
            print(unit, start, degree, row['status'], flush=True)
            del image, loss
    report = dict(task_id='PHD-MAIN-CANDPICK-v1', unit=unit,
        at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), camera=cam['name'],
        status='PASS' if all(r['status'] == 'PASS' for r in checks) else 'FAIL',
        checks=checks, optimizer_steps=0, scientific_verdict=None,
        code_sha256={p.name: sha(p) for p in [Path(__file__), Path(__file__).with_name('gs_engine.py')]})
    save(dest, report)
    save(Path('/docs/preflight') / dest.name, report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('units', nargs='+'); args = parser.parse_args()
    for unit in args.units: run(unit)
