"""Forward-only diagnosis of large projected Gaussian contributions at 30k."""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw
import torch

OUT = Path('/out')
TASK = Path('/task')
BASE = Path('/base')
SOURCE = TASK / 'sources/GeoGS-mvs-pgsr-v1'
sys.path.insert(0, str(SOURCE))
from scene.cameras import Camera
from scene.gaussian_model import GaussianModel
from gaussian_renderer import render
from jbgs_camera_adapter import apply_projection
from utils.loss_utils import ssim


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def cfg_args(path):
    tree = ast.parse(Path(path).read_text(), mode='eval').body
    assert isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name)
    assert tree.func.id == 'Namespace' and not tree.args
    return {item.arg: ast.literal_eval(item.value) for item in tree.keywords}


def rgb(path):
    with Image.open(path) as im:
        return np.array(im.convert('RGB'))


def u8(tensor):
    return (tensor.detach().clamp(0, 1).permute(1, 2, 0).cpu().numpy()*255 + .5).astype(np.uint8)


def image_tensor(array):
    return torch.from_numpy(array.copy()).permute(2, 0, 1).float()/255


def metrics(photo, pred, alpha):
    gt, pr = image_tensor(photo)[None], image_tensor(pred)[None]
    mse = float(np.mean((photo.astype(float)-pred.astype(float))**2))
    return {'psnr_db': float(10*np.log10(255**2/max(mse, 1e-12))),
            'ssim': float(ssim(pr, gt)), 'alpha_mean': float(alpha.mean()),
            'alpha_ge_095_fraction': float((alpha >= .95).mean())}


def montage(folder, photo, baseline, interventions, masses, thresholds):
    h, w = photo.shape[:2]
    canvas = Image.new('RGB', (4*w, 2*(h+32)), '#eeeeee')
    draw = ImageDraw.Draw(canvas)
    panels = [('Photo', photo), ('30k baseline', baseline)]
    panels += [(f'Exclude radius > {thresholds[i]}px', interventions[i]) for i in [1, 2]]
    panels += [(f'Contribution > {t}px', np.repeat((masses[i].clip(0, 1)*255+.5).astype(np.uint8)[..., None], 3, 2)) for i, t in enumerate(thresholds)]
    panels += [(f'Exclude radius > {thresholds[0]}px', interventions[0])]
    for index, (label, array) in enumerate(panels):
        x, y = (index % 4)*w, (index // 4)*(h+32)
        draw.text((x+6, y+8), label, fill='black')
        canvas.paste(Image.fromarray(array), (x, y+32))
    canvas.save(folder / 'montage.png')


@torch.no_grad()
def main():
    started = time.time()
    torch.set_num_threads(2)
    cfg = read('/config.json')
    diagnostic = TASK / 'viewer_rgb_v1/rgb_diagnostic_v1' / cfg['diagnostic_attempt']
    assert sha(diagnostic / 'manifest.json') == cfg['diagnostic_manifest_sha256']
    manifest = read(diagnostic / 'manifest.json')
    thresholds = cfg['radius_thresholds_px']
    assert thresholds == [20, 50, 100] and cfg['scientific_verdict'] is None
    pipe = SimpleNamespace(compute_cov3D_python=False, convert_SHs_python=False, depth_ratio=0.0)
    black = torch.zeros(3, device='cuda')
    records = []
    pc, model_path = None, None
    for item in cfg['cases']:
        tick = time.time()
        case = next(v for v in manifest['cases'] if v['id'] == item['case'])
        condition = next(v for v in case['conditions'] if v['id'] == item['condition'])
        args_path = Path(condition['cfg_args']['path'])
        assert sha(args_path) == condition['cfg_args']['sha256']
        values = cfg_args(args_path)
        assert values['sh_degree'] == 3 and values['resolution'] == 1
        ply = args_path.parent / 'point_cloud/iteration_30000/point_cloud.ply'
        if model_path != ply:
            del pc
            torch.cuda.empty_cache()
            pc = GaussianModel(3)
            pc.load_ply(str(ply))
            model_path = ply
        assert pc.active_sh_degree == 3
        k = np.asarray(case['K'])
        assert sha(diagnostic / case['photo_full_url']) == case['photo_full_sha256']
        full_photo = rgb(diagnostic / case['photo_full_url'])
        assert (full_photo.shape[1], full_photo.shape[0]) == (case['full_width'], case['full_height'])
        camera = Camera(colmap_id=case['camera_id'], R=np.asarray(case['R']).T,
            T=np.asarray(case['t']), FoVx=2*math.atan(case['full_width']/(2*k[0, 0])),
            FoVy=2*math.atan(case['full_height']/(2*k[1, 1])), image=image_tensor(full_photo),
            gt_alpha_mask=None, image_name=Path(case['name']).stem, uid=case['index'])
        apply_projection(camera, {'K': case['K'], 'width': case['full_width'], 'height': case['full_height']})
        bg = torch.ones(3, device='cuda') if values['white_background'] else black
        original = render(camera, pc, pipe, bg)
        full_base = u8(original['render'])
        saved = rgb(diagnostic / condition['render_full_url'])
        assert sha(diagnostic / condition['render_full_url']) == condition['render_full_sha256']
        parity = np.abs(full_base.astype(np.int16)-saved.astype(np.int16))
        if int(parity.max()) > 1:
            raise ValueError(f'Native rendering parity failed: {item}, max_delta={parity.max()}')
        radii = original['radii'].detach()
        alpha = original['rend_alpha'].squeeze().cpu().numpy()
        colors = torch.stack([(radii > t).float() for t in thresholds], dim=1)
        contribution = render(camera, pc, pipe, black, override_color=colors)
        mass = contribution['render'].cpu().numpy()
        alpha_delta = float((contribution['rend_alpha']-original['rend_alpha']).abs().max())
        assert alpha_delta < 1e-6
        assert (mass[2] <= mass[1]+1e-5).all() and (mass[1] <= mass[0]+1e-5).all()
        assert (mass >= -1e-6).all() and (mass <= alpha[None]+1e-5).all()
        x0, y0, x1, y1 = case['bbox']
        sl = np.s_[y0:y1, x0:x1]
        photo, baseline, roi_alpha = full_photo[sl], full_base[sl], alpha[sl]
        folder = OUT / (item['case'] + '__' + item['condition'])
        folder.mkdir()
        Image.fromarray(photo).save(folder / 'photo.png')
        Image.fromarray(baseline).save(folder / 'baseline.png')
        np.savez_compressed(folder / 'contribution.npz', baseline_alpha=roi_alpha,
                            contribution=mass[:, y0:y1, x0:x1], thresholds_px=np.array(thresholds))
        opacity = pc._opacity.detach().clone()
        interventions, details = [], []
        for i, threshold in enumerate(thresholds):
            mask = radii > threshold
            try:
                pc._opacity[mask] = -torch.inf
                changed = render(camera, pc, pipe, bg)
                pred = u8(changed['render'])[sl]
                altered_alpha = changed['rend_alpha'].squeeze().cpu().numpy()[sl]
            finally:
                pc._opacity.copy_(opacity)
            torch.testing.assert_close(pc._opacity, opacity, rtol=0, atol=0)
            Image.fromarray(pred).save(folder / f'exclude_radius_gt_{threshold}.png')
            np.save(folder / f'alpha_exclude_radius_gt_{threshold}.npy', altered_alpha)
            roi_mass = mass[i][sl]
            frac = roi_mass/np.maximum(roi_alpha, 1e-8)
            support = roi_alpha >= .95
            row = {'threshold_px': threshold, 'excluded_gaussians': int(mask.sum()),
                   'baseline_roi_contribution_mass_mean': float(roi_mass.mean()),
                   'baseline_supported_roi_contribution_fraction_mean': float(frac[support].mean()) if support.any() else None,
                   'baseline_roi_fraction_mass_gt_05': float((roi_mass > .5).mean()),
                   **metrics(photo, pred, altered_alpha)}
            interventions.append(pred)
            details.append(row)
            del changed
        restored = render(camera, pc, pipe, bg)
        restore_delta = float((restored['render']-original['render']).abs().max())
        assert restore_delta < 1e-6
        montage(folder, photo, baseline, interventions, mass[:, y0:y1, x0:x1], thresholds)
        record = {'case': item, 'photo_name': case['name'], 'bbox': case['bbox'],
                  'ply_path': str(ply), 'ply_sha256': sha(ply), 'gaussian_count': len(radii),
                  'native_png_max_abs_u8_delta': int(parity.max()), 'contribution_alpha_max_delta': alpha_delta,
                  'restored_render_max_delta': restore_delta, 'baseline': metrics(photo, baseline, roi_alpha),
                  'interventions': details, 'wall_seconds': time.time()-tick}
        write(folder / 'result.json', record)
        records.append(record)
        print(json.dumps(record), flush=True)
        del original, contribution, restored, opacity, colors, camera
    receipt = {'status': 'PASS_RENDER_ONLY_DIAGNOSTIC', 'scientific_verdict': None,
               'config': cfg, 'script_sha256': sha(__file__), 'config_sha256': sha('/config.json'),
               'runtime_image_id': os.environ['DIAGNOSTIC_IMAGE_ID'],
               'operator_head': (OUT / 'operator_head.txt').read_text().strip(),
               'torch_version': torch.__version__, 'gpu': torch.cuda.get_device_name(),
               'wall_seconds': time.time()-started, 'new_training_steps': 0,
               'source_sha256': {str(p.relative_to(SOURCE)): sha(p) for p in [SOURCE/'gaussian_renderer/__init__.py', SOURCE/'scene/gaussian_model.py', SOURCE/'jbgs_camera_adapter.py']},
               'interpretation': 'Contributions keep original visibility. Exclusion changes visibility and may create holes; full-ROI photo error and alpha are reported together. Neither sharper appearance nor higher PSNR establishes correct geometry. Diagnostic views are not independent tests.',
               'results': records}
    write(OUT / 'receipt.json', receipt)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        write(OUT / 'failure.json', {'status': 'FAIL', 'scientific_verdict': None, 'traceback': traceback.format_exc()})
        raise
