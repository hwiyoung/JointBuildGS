"""Same rendered RGB/depth and Open3D TSDF, serialized spatial tiles.

No optimizer, changed voxel size, image sampling, mesh simplification, or score.
The legacy extractor remains the reference for actual-input equivalence checks.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, '/repo/src/phd')
import streamed_tsdf as T

SCRIPT = Path(__file__).resolve()
CHECK = Path('/o/checks/tiled_post_v1')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def code_binding():
    return {str(p): sha(p) for p in [SCRIPT, Path(T.__file__), Path(T.__file__).with_name('umap_order.cpp')]}


def save_inputs(ext, box, wd, site, result, prior, mask_background=True):
    from utils.mesh_utils import to_cam_open3d
    started = time.time()
    folder = Path(wd) / 'inputs'
    folder.mkdir(parents=True, exist_ok=False)
    cameras = ext.viewpoint_stack
    height, width = cameras[0].image_height, cameras[0].image_width
    shape = (len(cameras), height, width)
    depths = np.lib.format.open_memmap(folder / 'depth_masked.npy', mode='w+', dtype=np.float32, shape=shape)
    colors = np.lib.format.open_memmap(folder / 'rgb.npy', mode='w+', dtype=np.uint8, shape=(*shape, 3))
    kept = []
    for i, camera in enumerate(cameras):
        assert (camera.image_height, camera.image_width) == (height, width)
        depth = ext.depthmaps[i].clone()
        mask = camera.gt_alpha_mask
        if mask_background and mask is not None:
            depth[mask < .5] = 0
        depths[i] = depth.squeeze(0).cpu().numpy()
        colors[i] = np.asarray(np.clip(ext.rgbmaps[i].permute(1, 2, 0).cpu().numpy(), 0., 1.) * 255,
                               order='C', dtype=np.uint8)
        kept.append(float(mask.float().mean()) if mask is not None else 1.)
    depths.flush(); colors.flush()
    del depths, colors
    cams = to_cam_open3d(cameras)
    np.savez(folder / 'cams.npz', names=np.array([c.image_name for c in cameras]),
             intr=np.array([[*c.intrinsic.get_focal_length(), *c.intrinsic.get_principal_point()] for c in cams]),
             wh=np.array([[c.intrinsic.width, c.intrinsic.height] for c in cams]),
             extrinsic=np.stack([np.asarray(c.extrinsic) for c in cams]))
    T.jdump(folder / 'meta.json', dict(site=site, result=result, prior_scene=prior, box=np.asarray(box).tolist(),
        views=len(cameras), width=width, height=height, views_without_depth=[], depth_dir=str(folder),
        mean_share_of_pixels_in_box=float(np.mean(kept)), mean_share_of_pixels_with_depth=None,
        seconds=time.time()-started, rgb='same clipped uint8 RGB as legacy extractor', scientific_verdict=None))
    T.jdump(folder / 'binding.json', dict(files={p.name: sha(p) for p in folder.glob('*') if p.is_file()},
                                        code=code_binding(), scientific_verdict=None))


def step(mode, wd, *args):
    command = [sys.executable, str(SCRIPT), 'worker', mode, str(wd), *map(str, args)]
    log = Path(wd) / ('worker_' + mode + ('_' + str(args[0]) if mode == 'tile' else '') + '.log')
    with log.open('x') as f:
        subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=True)


def fuse(wd, layout='auto:16'):
    wd = Path(wd)
    step('plan', wd, layout)
    step('order', wd)
    for tile in json.loads((wd / 'plan/layout.json').read_text())['tiles']:
        step('tile', wd, tile['k'])
    step('merge', wd)


def legacy(wd):
    """Run the unmodified r17 extractor on precisely the saved per-view arrays."""
    import torch
    import open3d as o3d
    from types import SimpleNamespace
    sys.path.insert(0, '/source')
    import utils.mesh_utils as M
    meta, cams, depth = T.load_inputs(wd)
    rgb = np.load(Path(wd) / 'inputs/rgb.npy', mmap_mode='r')
    stack = []
    for i in range(len(depth)):
        co = o3d.camera.PinholeCameraParameters()
        co.intrinsic = o3d.camera.PinholeCameraIntrinsic(meta['width'], meta['height'], *cams['intr'][i])
        co.extrinsic = cams['extrinsic'][i]
        stack.append(co)
    ext = M.GaussianExtractor.__new__(M.GaussianExtractor)
    ext.viewpoint_stack = [SimpleNamespace(gt_alpha_mask=None) for _ in stack]
    ext.depthmaps = [torch.from_numpy(np.array(d))[None] for d in depth]
    # uint8 / 255 would introduce float rounding on conversion back. Float64
    # gives the exact original uint8 on the legacy clip * 255 cast below.
    ext.rgbmaps = [torch.from_numpy(np.asarray(c, np.float64).transpose(2, 0, 1) / 255.) for c in rgb]
    for i, c in enumerate(rgb):
        assert np.array_equal(np.asarray(ext.rgbmaps[i].permute(1, 2, 0).numpy() * 255, dtype=np.uint8), c)
    M.to_cam_open3d = lambda _: stack
    mesh = ext.extract_mesh_bounded(voxel_size=.05, sdf_trunc=.25, depth_trunc=300.)
    o3d.io.write_triangle_mesh(str(Path(wd) / 'legacy.ply'), mesh)
    T.jdump(Path(wd) / 'legacy.json', dict(peak_host_gib=T.rss_peak_gb(), cgroup_peak_gib=T.cg_peak_gb(),
                                        scientific_verdict=None))


def collect(site, result, prior, destination):
    """Only render a completed model; save full inputs and two 16 m validation boxes."""
    import torch
    import gpu_post as P
    G = P.G
    G.model_dir = P.model_dir
    _, pipe, g, scene = G.load(site, prior, P.model_dir(site, result))
    ext = G.GaussianExtractor(g, G.render, pipe, bg_color=[0, 0, 0])
    ext.gaussians.active_sh_degree = 0
    ext.reconstruction(list(scene.getTrainCameras()))
    box = G.box_of(site)
    boxes = [('full', box)]
    for tag, offset in [('center16', [0., 0.]), ('offset16', [8.37, -7.19])]:
        b = box.copy()
        center = box.mean(axis=0)[:2] + np.array(offset)
        b[0, :2] = center - 8
        b[1, :2] = center + 8
        boxes.append((tag, b))
    for tag, b in boxes:
        for i, cam in enumerate(ext.viewpoint_stack):
            cam.gt_alpha_mask = G.box_mask(cam, ext.depthmaps[i], b).cpu()
        save_inputs(ext, b, Path(destination) / tag, site, result, prior)
    T.jdump(Path(destination) / 'collect.json', dict(model=str(P.model_dir(site, result)),
        model_sha256=sha(P.model_dir(site, result) / 'point_cloud/iteration_30000/point_cloud.ply'),
        optimizer_steps=0, code=code_binding(), peak_host_gib=T.rss_peak_gb(), scientific_verdict=None))


def validate(destination):
    rows = []
    for tag in ['center16', 'offset16']:
        wd = Path(destination) / tag
        step('legacy', wd)
        fuse(wd, '2x2')
        step('compare', wd)
        result = json.loads((wd / 'compare.json').read_text())
        assert result['same_triangle_order'] and result['same_triangle_multiset'] and result['same_vertex_set']
        assert result['same_triangle_colours']
        step('scorecheck', wd)
        result['scorecheck'] = json.loads((wd / 'scorecheck.json').read_text())
        assert result['scorecheck']['status'] == 'PASS'
        rows.append(result)
    T.jdump(CHECK / 'validation.json', dict(status='PASS', comparisons=rows, code=code_binding(),
        full_inputs=str(Path(destination) / 'full'), settings=dict(voxel_m=.05, sdf_trunc_m=.25, depth_trunc_m=300.),
        scientific_verdict=None))


def scorecheck(wd):
    """Apply the existing 8.1 scorer to both meshes, in a separate test folder."""
    import mesh_score as M
    wd = Path(wd)
    meta = json.loads((wd / 'inputs/meta.json').read_text())
    M.OUT = wd / 'scores'
    (M.OUT / 'patch_z').mkdir(parents=True, exist_ok=False)
    (M.OUT / 'direct_stage1_v2').symlink_to('/o/direct_stage1_v2', target_is_directory=True)
    M.source_mesh = lambda site, prior, result: wd / ('legacy.ply' if result == 'legacy' else 'merged.ply')
    for result in ['legacy', 'tiled']:
        M.score(meta['site'], meta['prior_scene'], result)
    prefix = meta['site'] + '__' + meta['prior_scene'] + '__'
    with np.load(M.OUT / 'patch_z' / (prefix + 'legacy.npz')) as a, np.load(M.OUT / 'patch_z' / (prefix + 'tiled.npz')) as b:
        checks = {key: bool(np.array_equal(a[key], b[key], equal_nan=True) if a[key].dtype.kind == 'f'
                            else np.array_equal(a[key], b[key])) for key in a.files}
        count = int((a['in_eval'] & a['scoring_allowed']).sum())
    assert all(checks.values()), checks
    T.jdump(wd / 'scorecheck.json', dict(status='PASS', exact_arrays=checks, evaluation_patches=count,
        unchanged_scorer_sha256=sha(Path(M.__file__)), scientific_verdict=None))


def extract(ext, box, wd, site, result, prior, voxel_size=.004, sdf_trunc=.02, depth_trunc=3, mask_backgrond=True):
    import open3d as o3d
    assert (voxel_size, sdf_trunc, depth_trunc) == (.05, .25, 300.)
    check = json.loads((CHECK / 'validation.json').read_text())
    assert check['status'] == 'PASS' and check['code'] == code_binding()
    save_inputs(ext, box, wd, site, result, prior, mask_backgrond)
    ext.depthmaps.clear(); ext.rgbmaps.clear()
    gc.collect()
    fuse(wd)
    return o3d.io.read_triangle_mesh(str(Path(wd) / 'merged.ply'))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('collect')
    for arg in ['site', 'result', 'prior', 'destination']: p.add_argument(arg)
    p = sub.add_parser('validate'); p.add_argument('destination')
    p = sub.add_parser('worker'); p.add_argument('step'); p.add_argument('wd'); p.add_argument('extra', nargs='*')
    a = ap.parse_args()
    if a.mode == 'collect': collect(a.site, a.result, a.prior, a.destination)
    elif a.mode == 'validate': validate(a.destination)
    elif a.step == 'plan': T.plan(a.wd, a.extra[0])
    elif a.step == 'order': T.order(a.wd)
    elif a.step == 'tile': T.tile(a.wd, int(a.extra[0]))
    elif a.step == 'merge': T.merge(a.wd, Path(a.wd) / 'merged.ply', Path(a.wd) / 'merged.json')
    elif a.step == 'legacy': legacy(a.wd)
    elif a.step == 'compare': T.compare(Path(a.wd) / 'legacy.ply', Path(a.wd) / 'merged.ply', Path(a.wd) / 'compare.json')
    elif a.step == 'scorecheck': scorecheck(a.wd)
    else: raise ValueError(a.step)


if __name__ == '__main__': main()
