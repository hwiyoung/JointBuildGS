"""[jbgs r15] Read-only record of a CUDA out-of-memory stop (PHD-MAIN-STAGE3-v1 order 4.1 / 6.1; default off).

With --jbgs_oom_record 1, train.py's call of training() is wrapped: on a CUDA out-of-memory error the frames of the traceback are read
(nothing is computed before the error that would not be computed without the flag), this record is written to
<model_path>/monitor/oom_record.json and the error is raised again, so the run ends as before. The record holds, for the iteration that
stopped: the view being rendered (the camera found in the innermost frame that has one; else the training loop's viewpoint_cam), the
number of Gaussians, the screen radius of every Gaussian and the tiles it touches computed in Python with the surfel rasterizer's own
rules (diff-surfel-rasterization forward.cu preprocessCUDA: near cut p_view.z <= 0.2, T = splat2world[:, [0, 1, 3]] @ world2pix[:, [0, 1, 3]]
as gaussian_renderer's compute_cov3D_python branch, compute_aabb with cutoff 3 (TIGHTBBOX 0), radius = ceil(max(extent.x, extent.y,
cutoff * FilterSize)), getRect over 16 x 16 tiles, DUAL_VISIABLE's cos == 0 cut), their 99th percentile, maximum and sum, PyTorch's
allocated / reserved / max-allocated memory, the device memory in use (torch.cuda.mem_get_info and nvidia-smi), the traceback's function
names and the error text. surfel_radii() is also used by the stage-3 check that compares it with the rasterizer's returned radii.
scientific_verdict: null."""
import json
import math
import subprocess
import time
import traceback
from pathlib import Path

import torch

FILTER_SIZE = 0.707106      # auxiliary.h FilterSize
CUTOFF = 3.0                # forward.cu, TIGHTBBOX 0
BLOCK = 16                  # config.h BLOCK_X / BLOCK_Y
INT_MAX = 2147483647        # (int)radius in preprocessCUDA saturates here


def register_args(parser):
    g = parser.add_argument_group("jbgs r15 out-of-memory record")
    g.add_argument("--jbgs_oom_record", type=int, default=0, help="r15: 1 = write monitor/oom_record.json on a CUDA out-of-memory stop (records only)")


def is_oom(exc):
    return isinstance(exc, torch.cuda.OutOfMemoryError) or (isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower())


@torch.no_grad()
def surfel_radii(gaussians, camera, scaling_modifier=1.0, chunk=1_000_000):
    """(radius int64 [N], tiles int64 [N]) of every Gaussian for this camera by the rasterizer's preprocess rules (0 = not drawn; a radius
    beyond the int range is saturated at INT_MAX, as the rasterizer's int cast)."""
    xyz = gaussians.get_xyz.detach()
    n = xyz.shape[0]
    W, H = int(camera.image_width), int(camera.image_height)
    gx, gy = (W + BLOCK - 1) // BLOCK, (H + BLOCK - 1) // BLOCK
    near, far = camera.znear, camera.zfar
    ndc2pix = torch.tensor([[W / 2, 0, 0, (W - 1) / 2], [0, H / 2, 0, (H - 1) / 2], [0, 0, far - near, near], [0, 0, 0, 1]],
                           dtype=torch.float32, device=xyz.device).T
    world2pix = (camera.full_proj_transform @ ndc2pix)[:, [0, 1, 3]]
    t = torch.tensor([CUTOFF * CUTOFF, CUTOFF * CUTOFF, -1.0], dtype=torch.float32, device=xyz.device)
    radius = torch.zeros(n, dtype=torch.int64, device=xyz.device)
    tiles = torch.zeros(n, dtype=torch.int64, device=xyz.device)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        x = xyz[s:e]
        hom = torch.cat([x, torch.ones((e - s, 1), dtype=x.dtype, device=x.device)], 1)
        pv = hom @ camera.world_view_transform
        ok = pv[:, 2] > 0.2
        S2W = gaussians.covariance_activation(x, gaussians.get_scaling[s:e].detach(), scaling_modifier, gaussians._rotation[s:e].detach())
        M = S2W[:, [0, 1, 3]] @ world2pix                     # (k, 3, 3); glm T column c = M[:, :, c]
        T0, T1, T2 = M[:, :, 0], M[:, :, 1], M[:, :, 2]
        d = (t * T2 * T2).sum(-1)
        ok &= d != 0
        f = t / torch.where(d == 0, torch.ones_like(d), d)[:, None]
        px, py = (f * T0 * T2).sum(-1), (f * T1 * T2).sum(-1)
        hx = torch.sqrt(torch.clamp(px * px - (f * T0 * T0).sum(-1), min=1e-4))
        hy = torch.sqrt(torch.clamp(py * py - (f * T1 * T1).sum(-1), min=1e-4))
        r = torch.ceil(torch.maximum(torch.maximum(hx, hy), torch.full_like(hx, CUTOFF * FILTER_SIZE)))
        # the rasterizer stores (int)radius: a float beyond the int range saturates (CUDA cvt.rzi.s32.f32); kept saturated here
        r = torch.clamp(r.double(), max=float(INT_MAX))
        # DUAL_VISIABLE: cos = -dot(p_view, normal) == 0 -> not drawn (normal = L[:, 2] in view space)
        nrm = S2W[:, 2, :3] @ camera.world_view_transform[:3, :3]
        ok &= (-(pv[:, :3] * nrm).sum(-1)) != 0
        # getRect: min(grid, max(0, (int)((p - r) / 16))), min(grid, max(0, (int)((p + r + 15) / 16))); C casts truncate toward zero
        x0 = torch.clamp(torch.trunc((px - r) / BLOCK), 0, gx); x1 = torch.clamp(torch.trunc((px + r + BLOCK - 1) / BLOCK), 0, gx)
        y0 = torch.clamp(torch.trunc((py - r) / BLOCK), 0, gy); y1 = torch.clamp(torch.trunc((py + r + BLOCK - 1) / BLOCK), 0, gy)
        area = ((x1 - x0) * (y1 - y0)).to(torch.int64)
        ok &= area > 0
        radius[s:e] = torch.where(ok, r, torch.zeros_like(r)).to(torch.int64)
        tiles[s:e] = torch.where(ok, area, torch.zeros_like(area))
    return radius, tiles


def _q(r, q):
    """the q-quantile (lower) of a 1-D tensor of any size (torch.quantile refuses more than 2**24 elements)."""
    if r.numel() == 0:
        return 0.0
    k = max(1, min(r.numel(), int(round(q * (r.numel() - 1))) + 1))
    return float(torch.kthvalue(r.flatten(), k).values)


def _nvidia_smi():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True,
                             text=True, timeout=20).stdout.strip()
        return out
    except Exception as e:  # noqa: BLE001
        return f"unavailable: {e}"


def record(exc, model_path):
    """read the traceback's frames, write monitor/oom_record.json; never raises."""
    rec = dict(schema="jbgs.oom_record.r15", written_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), error=str(exc)[:2000],
               allocated_gib=torch.cuda.memory_allocated() / 2 ** 30, reserved_gib=torch.cuda.memory_reserved() / 2 ** 30,
               max_allocated_gib=torch.cuda.max_memory_allocated() / 2 ** 30)
    try:
        free, total = torch.cuda.mem_get_info()
        rec.update(device_used_gib=(total - free) / 2 ** 30, device_total_gib=total / 2 ** 30)
    except Exception as e:  # noqa: BLE001
        rec["device_used_gib"] = f"unavailable: {e}"
    rec["nvidia_smi_mib"] = _nvidia_smi()
    try:
        frames = [(fr, fr.f_code.co_name, fr.f_code.co_filename.rsplit("/", 1)[-1], ln) for fr, ln in traceback.walk_tb(exc.__traceback__)]
        rec["stack"] = [f"{fn}:{ln} {name}" for _, name, fn, ln in frames]
        loop = next((fr for fr, name, fn, _ in frames if name == "training" and fn == "train.py"), None)
        L = loop.f_locals if loop is not None else {}
        cam, where = None, None
        for fr, name, fn, _ in reversed(frames):           # innermost first: the camera being rendered when it stopped
            for k, v in fr.f_locals.items():
                if hasattr(v, "image_name") and hasattr(v, "full_proj_transform"):
                    cam, where = v, f"{fn}:{name}:{k}"
                    break
            if cam is not None:
                break
        gaussians = L.get("gaussians")
        rec.update(iteration=L.get("iteration"), loop_view=getattr(L.get("viewpoint_cam"), "image_name", None),
                   view=getattr(cam, "image_name", None), view_found_in=where)
        if gaussians is not None:
            rec["n_gaussians"] = int(gaussians.get_xyz.shape[0])
            if cam is not None:
                torch.cuda.empty_cache()
                radius, tiles = surfel_radii(gaussians, cam)
                vis = radius > 0
                r = radius[vis].float()
                rec.update(visible=int(vis.sum()), radius_q99=_q(r, 0.99),
                           radius_max=float(r.max()) if r.numel() else 0.0, n_radius_ge_10000=int((r >= 10000).sum()),
                           n_radius_saturated=int((r >= INT_MAX).sum()), tiles_touched_sum=int(tiles.sum()),
                           radius_rule="python re-computation of the surfel rasterizer's preprocess (jbgs_oom_record.surfel_radii)")
                big = torch.topk(r, min(20, r.numel())).values.tolist() if r.numel() else []
                rec["radius_top20"] = big
    except Exception as e:  # noqa: BLE001
        rec["record_error"] = f"{type(e).__name__}: {e}"
    try:
        mon = Path(model_path) / "monitor"
        mon.mkdir(parents=True, exist_ok=True)
        (mon / "oom_record.json").write_text(json.dumps(rec, indent=1, default=lambda o: o if isinstance(o, (int, float, str)) else str(o)))
    except Exception:  # noqa: BLE001
        pass
    return rec


def run_guarded(fn, args, *a):
    """call fn(*a); with --jbgs_oom_record 1 write the record on a CUDA out-of-memory error, then raise it again."""
    if not int(getattr(args, "jbgs_oom_record", 0)):
        return fn(*a)
    try:
        return fn(*a)
    except BaseException as exc:  # noqa: BLE001
        if is_oom(exc):
            record(exc, getattr(args, "model_path", "."))
        raise
