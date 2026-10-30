"""gsplat 1.4 planar rendering with frozen background and candidate geometry.

Baseline SH degree is always 3, including the SH0 candidate comparison. Only
candidate opacity and candidate appearance are Parameters. No depth/GT loss.
"""
import importlib.util
import json
import os
import uuid
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from plyfile import PlyData
from gsplat import rasterization_2dgs
from gsplat.cuda._wrapper import spherical_harmonics
from src.stage2.colmap_io import read_images_bin
from input_audit import S0
from prepare_places import SITES

_spec = importlib.util.spec_from_file_location('candpick_inherited_loss',
    '/repo/src/phd/forks/GeoGS-conf-guided-v1-r18/utils/loss_utils.py')
LOSS = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(LOSS)


def tensor(a):
    return torch.as_tensor(np.asarray(a).copy(), dtype=torch.float32, device='cuda')


def cameras(unit):
    short, prior = unit.split('_')
    initial = S0 / 'fork_inputs/s61' / SITES[short]
    root = initial / ('scene_' + prior)
    split = json.loads((initial / 'split.json').read_text())
    calibration = json.loads((root / 'jbgs_calibration.json').read_text())['images']
    images = read_images_bin(root / 'sparse/0/images.bin')
    by_name = {Path(i.name).stem: i for i in images.values()}
    result = []
    for filename in sorted(split['train']):
        name = Path(filename).stem; pose = by_name[name]; cal = calibration[name]
        K = np.asarray(cal['K']).copy()
        # Original calibrated rasterizer samples pixel i; gsplat samples i+0.5.
        K[0, 2] += .5; K[1, 2] += .5
        E = pose.world_to_camera().astype(np.float32)
        path = root / 'images' / pose.name
        if not path.exists():
            matches = sorted((root / 'images').glob(name + '.*'))
            assert len(matches) == 1
            path = matches[0]
        result.append(dict(name=name, path=path, K=K, E=E, width=cal['width'], height=cal['height'],
                           position=-E[:3, :3].T @ E[:3, 3]))
    return result


def photo(camera):
    im = Image.open(camera['path']).convert('RGB')
    assert im.size == (camera['width'], camera['height']), 'do not silently resize inherited photos'
    return np.asarray(im)


def project(xyz, camera):
    x = np.asarray(xyz) @ camera['E'][:3, :3].T + camera['E'][:3, 3]
    p = x @ camera['K'].T
    return p[:, :2] / p[:, 2:], x[:, 2]


def initialise_color(unit, cams, geometry):
    dest = Path('/out/scenes') / unit / 'candidate_color.npy'
    if dest.exists():
        return np.load(dest)
    p = len(geometry['means']) // 8
    positions = geometry['means'].reshape(p, 2, 4, 3).mean(2).reshape(-1, 3)
    total = np.zeros((p * 2, 3)); count = np.zeros(p * 2, int)
    for cam in cams:
        uv, depth = project(positions, cam)
        # Bilinear sampling in image array coordinates, whose centres are i+0.5.
        uv = uv - .5
        valid = ((depth > .01) & np.isfinite(uv).all(1) &
                 (uv[:, 0] >= 0) & (uv[:, 0] < cam['width'] - 1) &
                 (uv[:, 1] >= 0) & (uv[:, 1] < cam['height'] - 1))
        ids = np.flatnonzero(valid)
        xy = uv[ids]; low = np.floor(xy).astype(int); dx, dy = (xy - low).T
        image = photo(cam).astype(np.float32) / 255.
        x, y = low.T
        value = ((1 - dx[:, None]) * (1 - dy[:, None]) * image[y, x] +
                 dx[:, None] * (1 - dy[:, None]) * image[y, x + 1] +
                 (1 - dx[:, None]) * dy[:, None] * image[y + 1, x] +
                 dx[:, None] * dy[:, None] * image[y + 1, x + 1])
        total[ids] += value; count[ids] += 1
    # Both heights receive identical colour: mean of all valid training-photo
    # samples at either height. This initialization never reads truth geometry.
    total = total.reshape(p, 2, 3).sum(1); count = count.reshape(p, 2).sum(1)
    assert (count > 0).all(), f'UNAVAILABLE_COLOR: {int((count == 0).sum())} points'
    color = (total / count[:, None]).astype(np.float32)
    for target, values in [(dest.with_name('candidate_color_sample_count.npy'), count), (dest, color)]:
        temporary = target.with_name('.' + target.stem + '.' + uuid.uuid4().hex + '.npy')
        np.save(temporary, values)
        os.replace(temporary, target)
    return color


class Scene:
    def __init__(self, unit, start='wrong', sh_degree=3):
        self.unit, self.sh_degree = unit, sh_degree
        root = Path('/out/scenes') / unit
        v = PlyData.read(root / 'background.ply', mmap='r')['vertex'].data
        self.base = dict(means=tensor(np.column_stack([v[k] for k in ['x', 'y', 'z']])),
            quats=tensor(np.column_stack([v[f'rot_{i}'] for i in range(4)])),
            scales=tensor(np.column_stack([np.exp(v['scale_0']), np.exp(v['scale_1']), np.full(len(v), 1e-8)])),
            opacity=tensor(v['opacity']).sigmoid())
        dc = np.column_stack([v[f'f_dc_{i}'] for i in range(3)])[:, None]
        rest = np.column_stack([v[f'f_rest_{i}'] for i in range(45)]).reshape(-1, 3, 15).transpose(0, 2, 1)
        self.base['sh'] = tensor(np.concatenate([dc, rest], 1))
        del v
        with np.load(root / 'candidate_geometry.npz') as z:
            g = {k: z[k] for k in ['means', 'quats', 'scales']}
        self.geometry = {k: tensor(v) for k, v in g.items()}
        self.cams = cameras(unit)
        color = initialise_color(unit, self.cams, g)
        self.dc = torch.nn.Parameter(tensor(np.repeat((color - .5) / .28209479177387814, 8, axis=0))[:, None])
        self.rest = torch.nn.Parameter(torch.zeros((len(g['means']), 15, 3), device='cuda'), requires_grad=sh_degree == 3)
        with np.load(root / 'initial_right_candidate.npz') as z:
            right = z['right_candidate']
        a, b = {'right': (.9, .1), 'wrong': (.1, .9), 'equal': (.5, .5)}[start]
        initial = np.where(np.arange(2)[None] == right[:, None], a, b)
        opacity = tensor(np.repeat(initial[:, :, None], 4, axis=2).reshape(-1))
        self.opacity = torch.nn.Parameter(torch.logit(opacity))
        self.all_geometry = {k: torch.cat([self.base[k], self.geometry[k]]) for k in self.geometry}

    def render(self, camera, background_only=False, candidates_only=False):
        E, K = tensor(camera['E'])[None], tensor(camera['K'])[None]
        position = tensor(camera['position'])
        with torch.no_grad():
            base_colors = (spherical_harmonics(3, self.base['means'] - position, self.base['sh']) + .5).clamp_min(0)
        sh = torch.cat([self.dc, self.rest], 1)
        colors = (spherical_harmonics(self.sh_degree, self.geometry['means'] - position, sh) + .5).clamp_min(0)
        if background_only:
            geom, colors, opacity = self.base, base_colors, self.base['opacity']
        elif candidates_only:
            geom, opacity = self.geometry, self.opacity.sigmoid()
        else:
            geom = self.all_geometry
            colors = torch.cat([base_colors, colors])
            opacity = torch.cat([self.base['opacity'], self.opacity.sigmoid()])
        return rasterization_2dgs(means=geom['means'], quats=geom['quats'], scales=geom['scales'],
            opacities=opacity, colors=colors, viewmats=E, Ks=K, width=camera['width'], height=camera['height'],
            render_mode='RGB', packed=False, sh_degree=None, near_plane=.01, backgrounds=None)

    def loss(self, image, camera):
        target = tensor(photo(camera) / 255.)
        return .8 * (image - target).abs().mean() + .2 * (1 - LOSS.ssim(image.permute(2, 0, 1), target.permute(2, 0, 1)))
