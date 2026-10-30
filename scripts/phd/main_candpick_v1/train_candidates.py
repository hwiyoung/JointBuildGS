"""Frozen-background, fixed-geometry candidate opacity/appearance experiment."""
import argparse
import gc
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import torch
from gs_engine import Scene, LOSS, photo, tensor
from input_audit import sha
from prepare_places import save

OUT, DOC = Path('/out'), Path('/docs')


def now(): return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    save(tmp, value); os.replace(tmp, path)


def frozen_hashes(scene):
    values = {**{'base.' + k: v for k, v in scene.base.items()},
              **{'candidate.' + k: v for k, v in scene.geometry.items()},
              **{'render_geometry.' + k: v for k, v in scene.all_geometry.items()}}
    result = {}
    for k, value in values.items():
        assert not value.requires_grad and value.grad is None, k
        arr = value.detach().cpu().contiguous().numpy()
        result[k] = hashlib.sha256(memoryview(arr).cast('B')).hexdigest()
    return result


class Monitor:
    def __init__(self, scene):
        self.scene = scene
        unit = scene.unit
        with np.load(OUT / 'places' / (unit + '.npz')) as z:
            self.d = {k: z[k] for k in ['point_id', 'right', 'group', 'side', 'area']}
        root = OUT / 'render_masks' / unit
        self.index = json.loads((root / 'index.json').read_text())
        with np.load(root / 'masks.npz') as z: packed = z['packed_masks']
        self.masks = {}
        for i, cam in enumerate(scene.cams):
            n = cam['height'] * cam['width']
            self.masks[cam['name']] = np.unpackbits(packed[i], count=n).reshape(cam['height'], cam['width']).astype(bool)
        self.cameras = {c['name']: c for c in scene.cams}
        self.photos = {}

    def target(self, cam):
        if cam['name'] not in self.photos: self.photos[cam['name']] = photo(cam)
        return tensor(self.photos[cam['name']] / 255.)

    def loss(self, image, cam):
        target = self.target(cam)
        return .8 * (image - target).abs().mean() + .2 * (1 - LOSS.ssim(image.permute(2, 0, 1), target.permute(2, 0, 1)))

    @torch.no_grad()
    def errors(self, all_views=False):
        names = ([c['name'] for c in self.scene.cams] if all_views else
                 list(dict.fromkeys(self.index['error_monitor_views'] + self.index['psnr_monitor_views'])))
        rows, abs_sum, sq_sum, count = [], 0., 0., 0
        for name in names:
            cam = self.cameras[name]
            render = self.scene.render(cam)[0][0]
            diff = render - self.target(cam)
            full_mse = float(diff.square().mean())
            mask = torch.as_tensor(self.masks[name], device='cuda')
            n = int(mask.sum())
            l1 = float(diff[mask].abs().sum()) if n else 0.
            sse = float(diff[mask].square().sum()) if n else 0.
            if all_views or name in self.index['error_monitor_views']:
                abs_sum += l1; sq_sum += sse; count += n * 3
            rows.append(dict(view=name, candidate_pixels=n,
                candidate_l1=l1 / (n * 3) if n else None,
                candidate_mse=sse / (n * 3) if n else None,
                full_psnr_db=float(-10 * np.log10(full_mse)) if full_mse > 0 else None))
        psnr = [r['full_psnr_db'] for r in rows if r['view'] in self.index['psnr_monitor_views']]
        assert len(psnr) == 5 and all(v is not None and np.isfinite(v) for v in psnr)
        return dict(scope='all_training_views' if all_views else 'fixed_five_largest_candidate_support_views',
            candidate_l1=abs_sum / count if count else None,
            candidate_mse=sq_sum / count if count else None,
            candidate_pixel_observations=count // 3,
            first_five_train_psnr_db=float(np.mean(psnr)), views=rows)

    @torch.no_grad()
    def opacity(self):
        a = self.scene.opacity.sigmoid().cpu().numpy().reshape(-1, 2, 4)
        pair = a.mean(2)
        index = (self.d['right'] == 'image').astype(int)
        right = pair[np.arange(len(pair)), index]
        wrong = pair[np.arange(len(pair)), 1 - index]
        rows = []
        for group in ['a', 'b', 'c']:
            for side in ['front', 'back']:
                mask = (self.d['group'] == group) & (self.d['side'] == side)
                rows.append(dict(group=group, side=side, points=int(mask.sum()),
                    mean_right_minus_wrong=float((right[mask] - wrong[mask]).mean()) if mask.any() else None,
                    area_weighted_right_minus_wrong=float(np.average(right[mask] - wrong[mask], weights=self.d['area'][mask])) if mask.any() else None))
        return rows


def snapshot(scene, path, step):
    tmp = path.with_suffix('.tmp.npz')
    np.savez_compressed(tmp, iteration=np.array(step), opacity_logits=scene.opacity.detach().cpu().numpy(),
        opacity=scene.opacity.detach().sigmoid().cpu().numpy(),
        color_dc=scene.dc.detach().cpu().numpy(), color_sh=scene.rest.detach().cpu().numpy())
    os.replace(tmp, path)


def save_resume(scene, optimizer, path, step, hashes, config_sha, elapsed):
    tmp = path.with_suffix('.tmp.pt')
    torch.save(dict(iteration=step, opacity=scene.opacity.detach().cpu(), dc=scene.dc.detach().cpu(),
        rest=scene.rest.detach().cpu(), optimizer=optimizer.state_dict(), torch_rng=torch.get_rng_state(),
        cuda_rng=torch.cuda.get_rng_state(), frozen_before=hashes, config_sha256=config_sha,
        elapsed_seconds=elapsed), tmp)
    os.replace(tmp, path)


def run(unit, start, degree):
    cfg_path = Path('/config/candpick_v1.json')
    cfg = json.loads(cfg_path.read_text()); config_sha = sha(cfg_path)
    assert config_sha == json.loads(Path('/config/candpick_v1.lock.json').read_text())['sha256']
    assert cfg['preflight']['status'] == 'PASS_RENDER_SUPPORT_SCOPE'
    for rel, digest in cfg['implementation_sha256'].items(): assert sha(Path('/repo') / rel) == digest, rel
    for item in cfg['units'][unit]['bindings']: assert sha(Path(item['path'])) == item['sha256'], item['path']
    arm = f'cp_{start}_sh{degree}_{unit}'
    root = OUT / 'runs' / arm; root.mkdir(parents=True, exist_ok=True)
    if (root / 'complete.json').exists():
        report = json.loads((root / 'complete.json').read_text()); assert report['config_sha256'] == config_sha
        print(arm, 'already complete', flush=True); return
    torch.manual_seed(0); np.random.seed(0)
    scene = Scene(unit, start=start, sh_degree=degree)
    monitor = Monitor(scene)
    params = [dict(params=[scene.opacity], lr=cfg['learning_rates']['opacity'], name='opacity'),
              dict(params=[scene.dc], lr=cfg['learning_rates']['dc'], name='color_dc')]
    if degree == 3: params.append(dict(params=[scene.rest], lr=cfg['learning_rates']['sh_rest'], name='color_sh'))
    optimizer = torch.optim.Adam(params, lr=0., betas=tuple(cfg['adam']['betas']), eps=cfg['adam']['eps'])
    allowed = {id(scene.opacity), id(scene.dc)} | ({id(scene.rest)} if degree == 3 else set())
    assert {id(p) for g in optimizer.param_groups for p in g['params']} == allowed
    hashes = frozen_hashes(scene)
    initial_step, previous_elapsed = 0, 0.
    resume_path = root / 'resume.pt'
    if resume_path.exists():
        state = torch.load(resume_path, map_location='cpu', weights_only=False)
        assert state['config_sha256'] == config_sha and state['frozen_before'] == hashes
        with torch.no_grad():
            for key, target in [('opacity', scene.opacity), ('dc', scene.dc), ('rest', scene.rest)]: target.copy_(state[key])
        optimizer.load_state_dict(state['optimizer'])
        torch.set_rng_state(state['torch_rng']); torch.cuda.set_rng_state(state['cuda_rng'])
        initial_step, previous_elapsed = state['iteration'], state['elapsed_seconds']
    metrics_path = root / 'metrics.jsonl'
    metrics = []
    if metrics_path.exists():
        for line in metrics_path.read_text().splitlines():
            try: row = json.loads(line)
            except json.JSONDecodeError: continue
            if row['iteration'] <= initial_step: metrics.append(row)
        metrics_path.write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in metrics))
    started = time.monotonic()
    receipt = dict(arm=arm, unit=unit, start=start, sh_degree=degree, config_sha256=config_sha,
        at=now(), status='RUNNING', resumed_from_iteration=initial_step,
        commit=os.environ.get('CANDPICK_COMMIT'), docker_image=os.environ.get('CANDPICK_IMAGE'),
        scientific_verdict=None)
    save(root / ('attempt_' + datetime.now().strftime('%Y%m%dT%H%M%S') + '.json'), receipt)
    cameras = {c['name']: c for c in scene.cams}
    sequence = cfg['units'][unit]['camera_sequence']
    assert len(sequence) == cfg['iterations'] and set(sequence) == set(cameras)
    def log(step):
        result = dict(iteration=step, at=now(), opacity=monitor.opacity(), photo_error=monitor.errors(),
            elapsed_seconds=previous_elapsed + time.monotonic() - started,
            peak_gpu_bytes=torch.cuda.max_memory_allocated())
        with metrics_path.open('a') as f:
            f.write(json.dumps(result, allow_nan=False) + '\n'); f.flush(); os.fsync(f.fileno())
        atomic_json(root / 'progress.json', dict(**receipt, iteration=step, elapsed_seconds=result['elapsed_seconds']))
        print(arm, step, 'masked L1', result['photo_error']['candidate_l1'],
              'PSNR(first5)', result['photo_error']['first_five_train_psnr_db'], flush=True)
        return result
    try:
        if initial_step == 0 and not resume_path.exists():
            print(arm, 'START; computing initial photo error on all training views', flush=True)
            save(root / 'photo_error_0.json', monitor.errors(all_views=True))
            snapshot(scene, root / 'candidate_0.npz', 0)
            log(0)
            save_resume(scene, optimizer, resume_path, 0, hashes, config_sha, time.monotonic() - started)
        elif initial_step == 0 and not metrics:
            log(0)
        for step in range(initial_step + 1, cfg['iterations'] + 1):
            cam = cameras[sequence[step - 1]]
            optimizer.zero_grad(set_to_none=True)
            rendered = scene.render(cam)[0][0]
            loss = monitor.loss(rendered, cam)
            assert torch.isfinite(loss), f'nonfinite loss at {step}'
            loss.backward()
            for group in optimizer.param_groups:
                for p in group['params']:
                    assert p.grad is not None and torch.isfinite(p.grad).all(), f'bad gradient {group["name"]} at {step}'
            optimizer.step()
            for group in optimizer.param_groups:
                assert all(torch.isfinite(p).all() for p in group['params']), f'nonfinite parameters at {step}'
            del rendered, loss
            if step in cfg['snapshot_iterations']: snapshot(scene, root / f'candidate_{step}.npz', step)
            if step % cfg['log_every'] == 0:
                log(step)
                save_resume(scene, optimizer, resume_path, step, hashes, config_sha,
                            previous_elapsed + time.monotonic() - started)
        final_hashes = frozen_hashes(scene)
        assert hashes == final_hashes, 'frozen data changed'
        save(root / 'photo_error_3000.json', monitor.errors(all_views=True))
        report = dict(**{k: v for k, v in receipt.items() if k != 'status'}, status='COMPLETE',
            finished_at=now(), iterations=cfg['iterations'], optimizer_steps=cfg['iterations'],
            elapsed_seconds=previous_elapsed + time.monotonic() - started,
            frozen_before=hashes, frozen_after=final_hashes, frozen_unchanged=True,
            final_candidate_sha256=sha(root / 'candidate_3000.npz'),
            depth_loss_used=False, truth_used_in_loss=False, densification=False,
            opacity_reset=False, opacity_prune=False)
        atomic_json(root / 'complete.json', report)
        save(DOC / 'training' / (arm + '.json'), report)
        print(arm, 'COMPLETE', report['elapsed_seconds'], 'seconds', flush=True)
    except BaseException as e:
        save(root / ('failure_' + datetime.now().strftime('%Y%m%dT%H%M%S') + '.json'),
             dict(arm=arm, at=now(), error_type=type(e).__name__, error=str(e),
                  last_recoverable_checkpoint=str(resume_path), scientific_verdict=None))
        raise
    finally:
        del scene, monitor, optimizer; gc.collect(); torch.cuda.empty_cache()


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('unit'); p.add_argument('start', choices=['right', 'wrong', 'equal'])
    p.add_argument('degree', type=int, choices=[0, 3]); args = p.parse_args()
    run(args.unit, args.start, args.degree)
