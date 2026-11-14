"""r31 PHD-MAIN-TRAINERR-v1 addendum 4: diagnostic switches for order 8 (work sa-1, sa-2). Defaults = r30 behaviour.

--jbgs_a4_grad_signed on   : the r28 gradient record (--jbgs_trainlog_grads on, at the trainlog save iterations) also stores, per in-range
                             Gaussian and per loss term, the full signed position gradient dL/dxyz (3 values) and the signed
                             dL/d opacity-logit. The r28 magnitude fields are written unchanged. torch.autograd.grad returns values only.
--jbgs_a4_stop_at N        : leave the training loop after the end-of-iteration records of iteration N (default -1 = never).
                             --iterations (and every schedule derived from it) is unchanged, so iterations 1..N run exactly as in a
                             30,000-iteration run.
--jbgs_a4_occl_mask_m M    : (work sa-2) before training, target-depth pixels whose image depth (STAGE0 s61 maps/mvs, finite and > 0)
                             is closer than the written target depth by more than M metres get depth-supervision weight 0.
                             Pixels without image depth are unchanged. Default -1 = off (maps untouched).
--jbgs_a4_dual_depth on   : (r32, work sa-3) target maps carry depth2/weight2 (image depth); Target.loss adds the same weighted absolute
                             difference for them with the same full-image denominator. Default off = r31.
With every switch at its default no model, optimizer, map or random state is touched by this module.
"""
import json
from pathlib import Path
import numpy as np
import torch


def register_args(parser):
    parser.add_argument('--jbgs_a4_grad_signed', choices=['on', 'off'], default='off')
    parser.add_argument('--jbgs_a4_stop_at', type=int, default=-1)
    parser.add_argument('--jbgs_a4_occl_mask_m', type=float, default=-1.)
    parser.add_argument('--jbgs_a4_mvs_dir', default='')
    parser.add_argument('--jbgs_a4_dual_depth', choices=['on', 'off'], default='off')  # [r32] sa-3: maps carry depth2/weight2 (image depth), loss adds that term


def grad_signed(args):
    return getattr(args, 'jbgs_a4_grad_signed', 'off') == 'on'


def stop_now(iteration, args):
    n = getattr(args, 'jbgs_a4_stop_at', -1)
    return n > 0 and iteration >= n


@torch.no_grad()
def apply_occl_mask(target_control, args):
    m = float(getattr(args, 'jbgs_a4_occl_mask_m', -1.))
    if m < 0 or target_control is None: return
    mvs_dir = Path(args.jbgs_a4_mvs_dir); assert mvs_dir.is_dir(), mvs_dir
    rows = []; tot = dict(target_pixels=0, image_depth_pixels=0, masked=0)
    for name, d in target_control.maps.items():
        dep = d['depth'].numpy(); w = d['weight'].numpy(); own = d['owner'].numpy()
        mvs = np.load(mvs_dir / f'{name}.npy'); assert mvs.shape == dep.shape, (name, mvs.shape, dep.shape)
        tgt = np.isfinite(dep) & (dep > 0) & (w > 0)
        have = np.isfinite(mvs) & (mvs > 0)
        mask = tgt & have & (mvs < dep - m)
        if mask.any():
            w2 = w.copy(); w2[mask] = 0
            d['weight'] = torch.from_numpy(w2).pin_memory()
        rows.append(dict(view=name, target_pixels=int(tgt.sum()), owner_target_pixels=int((tgt & (own >= 0)).sum()), image_depth_pixels=int((tgt & have).sum()),
                         masked=int(mask.sum()), masked_owner=int((mask & (own >= 0)).sum())))
        tot['target_pixels'] += rows[-1]['target_pixels']; tot['image_depth_pixels'] += rows[-1]['image_depth_pixels']; tot['masked'] += rows[-1]['masked']
    out = Path(args.model_path) / 'a4_occl_mask'; out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(out / 'masked_pixels.npz', **{n: (np.isfinite(target_control.maps[n]['depth'].numpy()) & (target_control.maps[n]['weight'].numpy() == 0)) for n in target_control.maps})
    (out / 'summary.json').write_text(json.dumps(dict(threshold_m=m, rule='image depth finite > 0 and image depth < target depth - threshold -> weight 0; no image depth unchanged',
                                                      mvs_dir=str(mvs_dir), totals=tot, views=rows, scientific_verdict=None), indent=1))
    print('[jbgs r31] occlusion mask', tot, flush=True)
