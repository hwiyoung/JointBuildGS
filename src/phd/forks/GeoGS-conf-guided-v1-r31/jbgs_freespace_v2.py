"""Freespace v2: detached native pressure times activated opacity.

Uses the exact explicitly requested historical renderer and v1 source semantics.
GT labels and deletion labels are never consumed by this training module.
"""
import torch
import torch.nn.functional as functional
import jbgs_freespace as v1


@torch.no_grad()
def local_ranges(target, present, pixels, radius):
    """Exact integer-radius square windows, ignoring missing depths and image padding.

    Repeated 3x3 pooling builds widths 3,5,...,31; this covers the specified
    radius 1..15 without truncating a radius-15 footprint to a width-15 window.
    """
    high = torch.where(present, target, -torch.inf)[None, None]
    low = torch.where(present, -target, -torch.inf)[None, None]
    result = torch.full((len(pixels),), torch.inf, device=target.device, dtype=target.dtype)
    if not len(pixels):
        return result
    x, y = pixels[:, 0], pixels[:, 1]
    for r in range(1, int(radius.max()) + 1):
        high = functional.max_pool2d(high, 3, 1, 1)
        low = functional.max_pool2d(low, 3, 1, 1)
        selected = radius == r
        result[selected] = high[0, 0, y[selected], x[selected]] + low[0, 0, y[selected], x[selected]]
    return result


@torch.no_grad()
def centre_flags(cam, g, sources, margins, inside, radii):
    xyz = g.get_xyz.detach()
    xyzh = torch.cat((xyz, torch.ones_like(xyz[:, :1])), 1)
    camera = xyzh @ cam.world_view_transform
    clip = xyzh @ cam.full_proj_transform
    uv = (clip[:, :2] / clip[:, 3:4] + 1) * xyz.new_tensor([cam.image_width, cam.image_height]) / 2 - .5
    pixels = torch.round(torch.nan_to_num(uv, nan=-1e6, posinf=-1e6, neginf=-1e6)).long()
    good = (torch.isfinite(uv).all(1) & torch.isfinite(camera[:, 2]) & (camera[:, 2] > 0)
            & (pixels[:, 0] >= 0) & (pixels[:, 0] < cam.image_width)
            & (pixels[:, 1] >= 0) & (pixels[:, 1] < cam.image_height) & inside)
    if g.frozen_mask is not None:
        good &= ~g.frozen_mask
    ids = torch.where(good)[0]
    xy = pixels[ids]
    x, y = xy[:, 0], xy[:, 1]
    radius = radii.detach().flatten()[ids].ceil().clamp(1, 15).long()
    available = torch.zeros(len(xyz), device=xyz.device, dtype=torch.bool)
    clean = torch.zeros_like(available)
    band = torch.zeros_like(available)
    front_any = torch.zeros_like(available)
    f = torch.zeros(len(xyz), device=xyz.device, dtype=xyz.dtype)
    for (target, sigma, validity, present), margin in zip(sources, margins):
        defined = present[y, x] & torch.isfinite(margin[y, x])
        available[ids] |= defined
        spread = local_ranges(target, present, xy, radius)
        usable = defined & (spread <= margin[y, x])
        clean[ids] |= usable
        z = camera[ids, 2]
        band[ids] |= usable & ((z - target[y, x]).abs() <= margin[y, x])
        front = usable & (z < target[y, x] - margin[y, x])
        front_any[ids] |= front
        f[ids] = torch.maximum(f[ids], torch.where(front, validity[y, x].clamp(1e-4, 1-1e-4), 0.))
    f[band] = 0.
    return f.detach(), dict(available=available, clean=clean, band=band,
                            clean_outside_band=clean & ~band, front=front_any,
                            in_scope_and_image=good)


def detached_pressure(cam, g, G, f, visibility=False):
    """Colour adjoints recover native sum(G*w*f); no parameter gradient survives."""
    with torch.enable_grad():
        feature = f.detach().clone().requires_grad_(True)
        image, _ = v1.feature_render(cam, g, feature, opacity=g.get_opacity.detach())
        weighted = torch.autograd.grad((G.detach() * image).sum(), feature,
                                       retain_graph=visibility)[0]
        wsum = torch.autograd.grad(image.sum(), feature)[0].detach() if visibility else None
    p = (weighted.detach() * f.detach()).detach()
    assert bool(torch.isfinite(p).all()) and bool((p >= 0).all())
    assert bool((p[f == 0] == 0).all())
    return p, image.detach(), wsum


def opacity_loss(g, pressure, pixels):
    return (pressure.detach() * g.get_opacity.flatten()).sum() / pixels


class Control:
    def __init__(self, folder, weight):
        self.scope = v1.XYScope(folder)
        self.weight = float(weight)
        assert 0 < self.weight < float('inf')
        self.deleted = 0
        self.last = {}
        self.count_history = []

    def loss(self, j, cam, g, median, radii, iteration):
        if not 500 <= iteration <= 30000:
            return None
        sources, _ = v1.sources_for(j, cam)
        G, margins, _ = v1.source_gate(median.detach().squeeze(0), sources)
        f, _ = centre_flags(cam, g, sources, margins, self.scope(g.get_xyz), radii)
        p, _, _ = detached_pressure(cam, g, G, f)
        free = opacity_loss(g, p, G.numel())
        self.last = dict(L_free=float(free.detach()), G_gt_half_fraction=float((G > .5).float().mean()),
                         pressure_positive_gaussians=int((p > 0).sum()))
        return self.weight * free


def add_loss(total, control, j, cam, g, render_pkg, iteration):
    if control is None:
        return total
    extra = control.loss(j, cam, g, render_pkg['fs_median_depth'], render_pkg['radii'], iteration)
    return total if extra is None else total + extra
