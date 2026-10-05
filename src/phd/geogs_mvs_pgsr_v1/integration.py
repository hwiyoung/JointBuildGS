"""Frozen MVS inputs and PGSR-style losses for an isolated GeoGS copy.

Copied as jbgs_mvs_pgsr.py by the source preparer. Original ``da_*`` arguments
remain compatibility identifiers for Anchor8k restoration; this module records
the actual current-depth source and every supplemental binding independently.
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch

from jbgs_mvs_pgsr_depth import read_colmap_depth, resample_depth_to_camera
from jbgs_mvs_pgsr_geometry import pgsr_geometry_losses


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _load_bound(path, expected):
    if _sha(path) != expected:
        raise ValueError('Frozen supplemental input changed: ' + str(path))
    return json.loads(Path(path).read_text())


def _value(tensor):
    return float(tensor.detach().item()) if torch.is_tensor(tensor) else float(tensor)


def _write(path, row, mode='a'):
    with Path(path).open(mode) as stream:
        stream.write(json.dumps(row, allow_nan=False) + '\n')


class _DepthSet:
    """Keep immutable targets on CPU, transfer just the currently sampled view."""
    def __init__(self, maps):
        self.maps = maps

    def get(self, name, default=None):
        value = self.maps.get(name)
        return default if value is None else value.to(device='cuda', non_blocking=False)


class Controller:
    def __init__(self, dataset, opt, pipe, args):
        self.output = Path(dataset.model_path)
        self.mode = os.environ['JBGS_MVS_PGSR_MODE']
        self.region = os.environ['JBGS_MVS_REGION']
        self.config_path = Path(os.environ['JBGS_MVS_CONFIG'])
        self.config_sha = os.environ['JBGS_MVS_CONFIG_SHA256']
        self.config = _load_bound(self.config_path, self.config_sha)
        self.binding_path = Path(os.environ['JBGS_MVS_BINDING'])
        self.binding_sha = os.environ['JBGS_MVS_BINDING_SHA256']
        self.binding = _load_bound(self.binding_path, self.binding_sha)
        if self.mode not in self.config['modes'] or self.region not in self.config['regions']:
            raise ValueError('Unfrozen experiment mode or region')
        if (self.binding['region'] != self.region or self.binding['config_sha256'] != self.config_sha
                or self.binding['scientific_verdict'] is not None):
            raise ValueError('Supplemental input/config binding mismatch')
        if (args.use_scale_invariant or args.use_confidence or args.jbgs_release_protection
                or args.stage_switch_iter != 8000 or not args.jbgs_resume_full
                or args.lambda_lod_anchor not in self.config['prior_weights']):
            raise ValueError('Experiment requires metric depth and native shared Anchor8k')
        if pipe.depth_ratio != 0:
            raise ValueError('Frozen GeoGS expected depth must be retained')
        if _sha(args.jbgs_input_manifest) != self.binding['parent_input_manifest_sha256']:
            raise ValueError('Original scene identity differs from supplemental MVS binding')
        self.views = {Path(v['name']).stem: v for v in self.binding['train']}
        if len(self.views) != len(self.binding['train']):
            raise ValueError('Duplicate train image stems')
        self.graph = self.binding['neighbor_graph']['graph']
        self.geometry = self.config['geometry']
        self.last = {}
        self.cameras = {}
        self.calibration = {}
        _write(self.output / 'mvs_pgsr_binding.json', {
            'task_id': self.config['task_id'], 'mode': self.mode, 'region': self.region,
            'config_sha256': self.config_sha, 'binding_sha256': self.binding_sha,
            'visual_source': self.config['depth']['source'],
            'legacy_da_fields': 'compatibility names only; actual target is existing COLMAP MVS',
            'normal_policy': 'native' if self.mode == 'mvs' else 'replace_with_pgsr_style_geometry',
            'geometry': self.geometry, 'scientific_verdict': None}, 'x')

    def load_mvs_depth_set(self, all_cameras, target_size, *, train_camera_names):
        self.cameras = {camera.image_name: camera for camera in all_cameras}
        if len(self.cameras) != len(all_cameras) or set(train_camera_names) != set(self.views):
            raise ValueError('Actual train camera membership differs from supplemental MVS binding')
        if not set(self.views) <= set(self.cameras):
            raise ValueError('Training camera metadata missing from actual GeoGS scene')
        maps, rows = {}, []
        for name, view in self.views.items():
            camera = self.cameras[name]
            if target_size != (view['height'], view['width']):
                raise ValueError('Unexpected RGB raster size')
            if (camera.image_height, camera.image_width) != target_size:
                raise ValueError('Actual camera image dimensions differ from bound MVS target')
            if not hasattr(camera, 'jbgs_source_intrinsics') or not np.allclose(
                    camera.jbgs_source_intrinsics, np.asarray(view['K']), rtol=0, atol=1e-9):
                raise ValueError('Actual renderer intrinsics differ from bound MVS calibration')
            projection = camera.projection_matrix.detach().cpu().numpy().T
            k, w, h = np.asarray(view['K']), view['width'], view['height']
            if not np.allclose([projection[0, 0], projection[1, 1], projection[0, 2], projection[1, 2]],
                               [2*k[0, 0]/w, 2*k[1, 1]/h, (2*k[0, 2]+1-w)/w, (2*k[1, 2]+1-h)/h],
                               rtol=1e-6, atol=1e-7):
                raise ValueError('Actual renderer projection differs from bound intrinsics')
            actual_w2c = camera.world_view_transform.detach().cpu().numpy().T
            expected_w2c = np.eye(4)
            expected_w2c[:3, :3] = view['R']
            expected_w2c[:3, 3] = view['t']
            if not np.allclose(actual_w2c, expected_w2c, rtol=1e-6, atol=1e-5):
                raise ValueError('Actual renderer pose differs from MVS calibration: ' + name)
            meta = view['maps']['depth']
            native = read_colmap_depth(self.binding_path.parent / view['local_depth'], meta)
            depth, valid = resample_depth_to_camera(native, meta['K'], view['K'], view['width'], view['height'])
            maps[name] = torch.from_numpy(depth)
            self.calibration[name] = tuple(torch.tensor(view[key], dtype=torch.float32, device='cuda')
                                           for key in ('K', 'R', 't'))
            rows.append({'name': name, 'depth_sha256': meta['sha256'],
                         'valid_pixels': int(valid.sum()), 'pixels': int(valid.size)})
        _write(self.output / 'mvs_depth_loaded.json', {
            'train_count': len(maps), 'evaluation_depth_count': 0, 'rows': rows,
            'mapping': self.config['depth']['mapping'], 'scientific_verdict': None}, 'x')
        print(f'[MVS] Loaded {len(maps)} bound train-only metric depth targets; legacy DA3 target load replaced.')
        return _DepthSet(maps)

    def _seed(self, iteration, name):
        text = f"{self.config['seed']}:{self.region}:{iteration}:{name}"
        return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], 'little') % (2**31)

    def geometry_loss(self, camera, render_pkg, gaussians, pipe, background, iteration, *, native_normal_loss):
        self.last = {'mode': self.mode, 'native_normal_weighted': _value(native_normal_loss)}
        if self.mode == 'mvs' or iteration < self.geometry['start_iteration']:
            return native_normal_loss
        from gaussian_renderer import render
        name = camera.image_name
        candidates = self.graph[self.views[name]['name']]['selected']
        seed = self._seed(iteration, name)
        near_name = None
        near_args = {}
        if candidates:
            near_name = Path(candidates[seed % len(candidates)]).stem
            if near_name not in self.views:
                raise ValueError('An evaluation camera entered the geometry neighbor graph')
            near = self.cameras[near_name]
            near_pkg = render(near, gaussians, pipe, background)
            near_args = dict(depth_near=near_pkg['surf_depth'], alpha_near=near_pkg['rend_alpha'],
                             rgb_near=near.original_image.cuda(),
                             K_near=self.calibration[near_name][0], R_near=self.calibration[near_name][1], t_near=self.calibration[near_name][2])
        elif self.geometry.get('empty_neighbor_policy') != 'single_view_only_record_skip':
            raise ValueError('No frozen geometry neighbor and no explicit skip policy')
        keys = ('max_samples', 'microbatch_size', 'patch_radius', 'reprojection_threshold', 'alpha_min', 'grazing_cos_min')
        losses = pgsr_geometry_losses(
            render_pkg['surf_depth'], render_pkg['rend_normal'], render_pkg['rend_alpha'],
            camera.original_image.cuda(), *self.calibration[name],
            seed=seed, **near_args, **{key: self.geometry[key] for key in keys})
        self.last.update(neighbor=near_name, multiview_skipped=not bool(candidates), sampling_seed=seed, counts=losses['counts'])
        total = native_normal_loss * 0
        for key in ('svgeo', 'mvrgb', 'mvgeom'):
            weight = self.geometry[key + '_weight']
            self.last[key] = _value(losses[key])
            self.last[key + '_weighted'] = weight * self.last[key]
            total = total + weight * losses[key]
        if not all(np.isfinite(self.last[key]) for key in ('svgeo', 'mvrgb', 'mvgeom')):
            raise FloatingPointError('Nonfinite geometry loss')
        if iteration == 8001:
            gradients = {}
            parameters = (gaussians._xyz, gaussians._rotation, gaussians._scaling)
            for key in ('svgeo', 'mvrgb', 'mvgeom'):
                values = torch.autograd.grad(losses[key], parameters, retain_graph=True, allow_unused=True)
                gradients[key] = self._gradient_summary(zip(('xyz', 'rotation', 'scaling'), values))
            _write(self.output / 'geometry_first_step_gradients.json',
                   {'iteration': iteration, 'per_term_gradients': gradients, 'counts': losses['counts'],
                    'protected_hooks_applied': True, 'scientific_verdict': None}, 'x')
        return total

    @staticmethod
    def _gradient_summary(pairs):
        rows = {}
        for name, gradient in pairs:
            if gradient is None:
                rows[name] = {'present': False}
                continue
            value = gradient.detach()
            finite = bool(torch.isfinite(value).all().item())
            rows[name] = {'present': True, 'finite': finite,
                          'nonzero_elements': int(torch.count_nonzero(value).item()),
                          'max_abs': _value(value.abs().max())}
            if not finite:
                raise FloatingPointError('Nonfinite geometry gradient: ' + name)
        return rows

    def training_trace(self, *, iteration, camera, prior_loss, visual_loss, prior_weight, visual_weight, geometry_loss, rgb_loss):
        if iteration == 8001 or iteration % 100 == 0:
            _write(self.output / 'mvs_pgsr_trace.jsonl', {
                'iteration': iteration, 'camera': camera, 'visual_source': 'COLMAP_MVS_CAMERA_Z',
                'prior_loss': _value(prior_loss), 'mvs_loss': _value(visual_loss),
                'prior_weight': _value(prior_weight), 'mvs_weight': _value(visual_weight),
                'geometry_weighted_total': _value(geometry_loss), 'rgb_loss': _value(rgb_loss),
                **self.last, 'scientific_verdict': None})

    def after_backward(self, iteration, gaussians):
        if iteration == 8001 or iteration % 100 == 0:
            summary = self._gradient_summary((name, parameter.grad) for name, parameter in
                                             (('xyz', gaussians._xyz), ('rotation', gaussians._rotation), ('scaling', gaussians._scaling)))
            _write(self.output / 'mvs_pgsr_gradient_trace.jsonl',
                   {'iteration': iteration, 'total_loss_gradients': summary,
                    'peak_cuda_allocated_bytes': torch.cuda.max_memory_allocated(),
                    'peak_cuda_reserved_bytes': torch.cuda.max_memory_reserved(), 'scientific_verdict': None})


def from_environment(dataset, opt, pipe, args):
    return Controller(dataset, opt, pipe, args)
