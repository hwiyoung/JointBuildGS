"""Full-resolution row strips with recomputed backward for bounded raster memory.

RGB/depth losses still consume the stitched full image. No pixel or Gaussian is
removed. Strip origins align to the rasterizer's 16-pixel tile grid.
"""
import gc
import json
import math
import os
from pathlib import Path

import torch
from torch.utils.checkpoint import checkpoint

_original = None
_context = {}
TARGET = 'DJI_20241217101311_0008_D'


def set_context(camera, iteration, gaussians=None):
    _context.update(camera=camera, iteration=int(iteration))
    if gaussians is not None:
        _context['gaussians'] = len(gaussians.get_xyz)
    if camera == TARGET:
        record(dict(event='before_render', allocated=torch.cuda.memory_allocated(),
                    free=torch.cuda.mem_get_info()[0]))


def record(row):
    path = os.environ.get('JBGS_RASTER_TRACE')
    if path:
        with Path(path).open('a') as stream:
            stream.write(json.dumps(dict(_context, **row)) + '\n')


def strip_settings(settings, start, height):
    full_height = settings.image_height
    # Homogeneous NDC transform preserves every original pixel center exactly
    # in real arithmetic: y_strip = y_full - start.
    projection = settings.projmatrix.clone()
    projection[:, 1] = (settings.projmatrix[:, 1] * (full_height / height)
                        + settings.projmatrix[:, 3] * ((full_height - 2*start - height) / height))
    return settings._replace(image_height=height, projmatrix=projection,
                             tanfovy=settings.tanfovy * height / full_height)


def striped(self, means3D, means2D, opacities, shs=None, colors_precomp=None,
            scales=None, rotations=None, cov3D_precomp=None, *, rows=512):
    from diff_surfel_rasterization import GaussianRasterizer
    assert cov3D_precomp is None, 'Only the verified native scale/rotation path is supported'
    assert rows > 0 and rows % 16 == 0
    settings = self.raster_settings
    images, maps, radii = [], [], []
    values = (means3D, means2D, opacities, shs, colors_precomp, scales, rotations)
    for start in range(0, settings.image_height, rows):
        height = min(rows, settings.image_height - start)
        rasterizer = GaussianRasterizer(strip_settings(settings, start, height))
        # Native densification gradients are NDC-scaled by the raster height.
        factor = means2D.new_tensor([1, settings.image_height / height, 1])

        def invoke(xyz, xy, opacity, sh, color, scale, rotation,
                   rasterizer=rasterizer, factor=factor):
            return _original(rasterizer, xyz, xy * factor, opacity,
                             shs=sh, colors_precomp=color, scales=scale,
                             rotations=rotation, cov3D_precomp=None)

        if torch.is_grad_enabled() and any(x is not None and x.requires_grad for x in values):
            rgb, rad, auxiliary = checkpoint(invoke, *values, use_reentrant=True,
                                             preserve_rng_state=False)
        else:
            rgb, rad, auxiliary = invoke(*values)
        images.append(rgb); maps.append(auxiliary); radii.append(rad)
    return torch.cat(images, dim=1), torch.stack(radii).amax(0), torch.cat(maps, dim=1)


def install():
    global _original
    if _original is not None:
        return
    import diff_surfel_rasterization as module
    _original = module.GaussianRasterizer.forward
    original_function = module._RasterizeGaussians.forward

    def measured(ctx, *args):
        result = original_function(ctx, *args)
        if _context.get('camera') == TARGET or _context.get('iteration', 0) % 1000 == 0:
            record(dict(event='raster_forward', gaussian_tile_pairs=int(ctx.num_rendered),
                        height=ctx.raster_settings.image_height,
                        allocated=torch.cuda.memory_allocated()))
        return result

    module._RasterizeGaussians.forward = staticmethod(measured)
    original_cpp = module._C.rasterize_gaussians

    def measured_cpp(*args):
        result = original_cpp(*args)
        if _context.get('camera') == TARGET and _context.get('iteration',0) >= 14000:
            radius = result[3]
            values, ids = torch.topk(radius, min(16, len(radius)))
            record(dict(event='large_projected_splats', ids=ids.cpu().tolist(),
                        radii=values.cpu().tolist(), xyz=args[1][ids].detach().cpu().tolist(),
                        scale=args[4][ids].detach().cpu().tolist(),
                        opacity=args[3][ids].detach().cpu().tolist(),
                        binning_bytes=result[5].numel()*result[5].element_size()))
        return result

    module._C.rasterize_gaussians = measured_cpp

    def forward(self, means3D, means2D, opacities, shs=None, colors_precomp=None,
                scales=None, rotations=None, cov3D_precomp=None):
        args=(self, means3D, means2D, opacities, shs, colors_precomp, scales, rotations, cov3D_precomp)
        if _context.get('camera') != TARGET and not os.environ.get('JBGS_FORCE_STRIPES'):
            try:
                return _original(*args)
            except torch.cuda.OutOfMemoryError:
                record(dict(event='native_render_oom_fallback'))
            gc.collect(); torch.cuda.empty_cache()
        for rows in [512, 256, 128]:
            try:
                result = striped(*args, rows=rows)
                record(dict(event='striped_render', rows=rows))
                return result
            except torch.cuda.OutOfMemoryError:
                record(dict(event='strip_render_oom', rows=rows))
            gc.collect(); torch.cuda.empty_cache()
        raise torch.cuda.OutOfMemoryError('Raster exceeded memory at all configured strip heights')

    module.GaussianRasterizer.forward = forward
    import gaussian_renderer
    original_render = gaussian_renderer.render

    def render_with_context(camera, *args, **kwargs):
        set_context(getattr(camera, 'image_name', 'virtual'), _context.get('iteration',0))
        return original_render(camera, *args, **kwargs)

    gaussian_renderer.render = render_with_context
