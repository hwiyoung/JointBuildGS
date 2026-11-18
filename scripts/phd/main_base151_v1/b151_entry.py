"""PHD-MAIN-BASE151-v1 container entry for the training of one cell with a method's unchanged official train.py
(2DGS, GeoGS: flat 2D Gaussians; CDGS: 3D Gaussians). Everything below is a wrapper; no method file is edited.

  python /b151s/b151_entry.py <run> <cell> <2D|3D> train.py <train.py args...>

Installed before train.py runs (runpy, /source on sys.path):
  1. CUDA cap (order 1.2): JBGS_GPU_CAP_GIB -> torch.cuda.set_per_process_memory_fraction (the host sets it to GPU 1 free - 2 GiB).
  2. Elongation filter (order 1.7, config filter): GaussianModel.densify_and_prune is wrapped; right before the unchanged call the rows with
     axis ratio <= 0.01 get xyz_gradient_accum = 0, so densify_and_clone / densify_and_split (grads = accum / denom >= threshold) skip them.
       2D: ratio = min(scale) / max(scale) (TRAINUNIT tu_train_entry.install_elongation_filter, same code)
       3D: ratio = second largest scale / largest scale
     Each call appends one line to <root>/densify.jsonl (gaussians before/after, needle rows, gradient-selected rows before/after the filter).
  3. Recorder (order 3.2) through GaussianModel.update_learning_rate(iteration), which train.py calls once at the start of every iteration:
     iteration 1 and every 1,000 -> <root>/trace1000.jsonl (gaussians, ratio < 0.01 / < 0.1 shares and quantiles, VmRSS/VmHWM,
     cgroup memory.current/peak, CUDA allocated/reserved now and peak); iteration 500 -> time_check_500.json (seconds 1 -> 500).
     Count rule (TRAINUNIT-v2 cells, record only): gaussians > 3 x the count at 6,000 -> health_override.jsonl, training continues.
  4. GPU sharing pause (TRAINUNIT-v2 rule): at every multiple of 100, if /control/STOP_<run>_cell<k> exists, the state is saved with the
     official capture() as <model>/chkpnt_pause<it-1>.pth (resumable with the official --start_checkpoint) and the process exits (code 75).
Outputs next to the model (<root> = parent of -m). scientific_verdict: null
"""
import datetime as dt
import json
import os
import runpy
import sys
import time
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
run, cell, dim = sys.argv[1], int(sys.argv[2]), sys.argv[3]
assert dim in ('2D', '3D')
argv = sys.argv[4:]
assert argv[0] == 'train.py'
model = Path(argv[argv.index('-m') + 1])
root = model.parent
stopfile = Path('/control') / f'STOP_{run}_cell{cell}'
THRESH = 0.01


def now():
    return dt.datetime.now(KST).isoformat()


def dump(p, v):
    Path(p).write_text(json.dumps(v, ensure_ascii=False, indent=1) + '\n')


def jl(name, v):
    with (root / name).open('a') as f:
        f.write(json.dumps(v) + '\n')


sys.path.insert(0, '/source')
os.chdir('/source')
import torch  # noqa: E402

cap = os.environ.get('JBGS_GPU_CAP_GIB')
if cap:
    total = torch.cuda.get_device_properties(0).total_memory
    frac = min(1.0, float(cap) * 2 ** 30 / total)
    torch.cuda.set_per_process_memory_fraction(frac, 0)
    dump(root / 'gpu_cap.json', dict(at=now(), cap_GiB=float(cap), device_total_bytes=total, fraction=frac,
                                    rule='GPU 1 free right before the launch - 2 GiB (order 1.2)', scientific_verdict=None))

from scene.gaussian_model import GaussianModel  # noqa: E402

state = dict(it=0, start=time.monotonic(), t1=None, count6000=None, health_last=None)


def ratio(s):
    if dim == '2D':
        return s.min(dim=1).values / s.max(dim=1).values
    q = torch.sort(s, dim=1).values
    return q[:, -2] / q[:, -1]


original_dp = GaussianModel.densify_and_prune


def densify_and_prune(self, max_grad, min_opacity, extent, max_screen_size, *a, **k):
    with torch.no_grad():
        n0 = int(self.get_xyz.shape[0])
        r = ratio(self.get_scaling)
        needle = r <= THRESH
        g = self.xyz_gradient_accum / self.denom
        g[g.isnan()] = 0.0
        sel0 = torch.norm(g, dim=-1) >= max_grad
        self.xyz_gradient_accum[needle] = 0.0
        g = self.xyz_gradient_accum / self.denom
        g[g.isnan()] = 0.0
        sel1 = torch.norm(g, dim=-1) >= max_grad
    out = original_dp(self, max_grad, min_opacity, extent, max_screen_size, *a, **k)
    jl('densify.jsonl', dict(iteration=state['it'], gaussians_before=n0, gaussians_after=int(self.get_xyz.shape[0]), needle=int(needle.sum()),
                             grad_selected_before_filter=int(sel0.sum()), grad_selected_after_filter=int(sel1.sum()),
                             excluded_by_filter=int((sel0 & needle).sum()), max_grad=float(max_grad), extent=float(extent)))
    return out


GaussianModel.densify_and_prune = densify_and_prune
dump(root / 'filter.json', dict(at=now(), dim=dim, threshold=THRESH, comparison='<=',
                                definition='min/max scale' if dim == '2D' else 'second largest / largest scale',
                                where='b151_entry.py densify_and_prune wrapper (xyz_gradient_accum = 0 before the unchanged call)',
                                source='CityGaussianV2 (Linketic/CityGaussian 3041bf5a); TRAINUNIT tu_train_entry.install_elongation_filter', scientific_verdict=None))


def cg(name):
    try:
        return int((Path('/sys/fs/cgroup') / name).read_text().split()[0])
    except Exception:
        return None


def proc_status():
    out = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS', 'VmHWM')):
            k, v = line.split(':')
            out[k] = int(v.split()[0]) * 1024
    return out


def record(self, it):
    with torch.no_grad():
        r = ratio(self.get_scaling)
        n = int(r.numel())
        st = proc_status()
        q = [float(x) for x in torch.quantile(r[::max(1, n // 1_000_000)].float(), torch.tensor([.01, .1, .5], device=r.device))] if n else None
        return dict(iteration=it, at=now(), seconds=time.monotonic() - state['start'], gaussians=n,
                    elong_lt_001=float((r < .01).float().mean()) if n else None, elong_lt_01=float((r < .1).float().mean()) if n else None,
                    elong_q01_q10_q50=q, rss_bytes=st.get('VmRSS'), rss_peak_bytes=st.get('VmHWM'),
                    cgroup_current_bytes=cg('memory.current'), cgroup_peak_bytes=cg('memory.peak'),
                    cuda_allocated_bytes=torch.cuda.memory_allocated(), cuda_reserved_bytes=torch.cuda.memory_reserved(),
                    cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated(), cuda_peak_reserved_bytes=torch.cuda.max_memory_reserved())


original_lr = GaussianModel.update_learning_rate


def update_learning_rate(self, iteration, *a, **k):
    out = original_lr(self, iteration, *a, **k)
    it = int(iteration)
    state['it'] = it
    if state['t1'] is None:
        state['t1'] = (it, time.monotonic())
    if it % 100 == 0 and stopfile.exists():
        path = model / f'chkpnt_pause{it - 1}.pth'
        torch.save((self.capture(), it - 1), str(path))
        dump(root / 'PAUSE.json', dict(at=now(), iteration_done=it - 1, checkpoint=str(path), gaussians=int(self.get_xyz.shape[0]),
                                      peak_reserved_bytes=torch.cuda.max_memory_reserved(), note='GPU sharing pause; resume with --start_checkpoint',
                                      scientific_verdict=None))
        print('B151_PAUSE_SAVED', it - 1, flush=True)
        sys.stdout.flush()
        os._exit(75)
    try:
        if it == 1 or it % 1000 == 0:
            rec = record(self, it)
            jl('trace1000.jsonl', rec)
            n = rec['gaussians']
            if it == 6000:
                state['count6000'] = n
            if state['count6000'] and n > 3 * state['count6000']:
                jl('health_override.jsonl', dict(at=now(), iteration=it, gaussians=n, count_at_6000=state['count6000'],
                                                 reason='count > 3 x count at 6000', action='recorded, training continues (TRAINUNIT-v2 cell rule)',
                                                 scientific_verdict=None))
        if it == 500 and state['t1'] is not None:
            i1, t1 = state['t1']
            d = time.monotonic() - t1
            dump(root / 'time_check_500.json', dict(at=now(), first_iteration=i1, iteration=it, seconds_first_to_500=d,
                                                   seconds_per_iteration=d / max(1, it - i1), gaussians=int(self.get_xyz.shape[0]),
                                                   peak_reserved_bytes=torch.cuda.max_memory_reserved(), scientific_verdict=None))
    except Exception as e:   # the recorder never stops training
        jl('trace1000.jsonl', dict(iteration=it, recorder_error=f'{type(e).__name__}: {e}'[:500]))
    return out


GaussianModel.update_learning_rate = update_learning_rate
dump(root / 'input_binding.json', dict(at=now(), run=run, cell=cell, dim=dim, argv=argv, cap_GiB=cap, stopfile=str(stopfile),
                                      split=os.environ.get('JBGS_SPLIT_JSON'), scientific_verdict=None))
sys.argv = ['/source/train.py'] + argv[1:]
try:
    runpy.run_path('/source/train.py', run_name='__main__')
except SystemExit as e:
    if e.code not in (0, None):
        raise
except Exception as e:
    text = f'{type(e).__name__}: {e}'
    dump(root / 'ERROR.json', dict(at=now(), iteration=state['it'], error=text[:4000], oom='out of memory' in text.lower(),
                                  peak_reserved_bytes=torch.cuda.max_memory_reserved(), peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                                  scientific_verdict=None))
    raise
final = int(argv[argv.index('--iterations') + 1]) if '--iterations' in argv else 30000
ply = model / f'point_cloud/iteration_{final}/point_cloud.ply'
if ply.is_file():
    dump(root / 'TRAINING_COMPLETE.json', dict(at=now(), iteration=final, ply=str(ply), seconds=time.monotonic() - state['start'],
                                              peak_reserved_bytes=torch.cuda.max_memory_reserved(), peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                                              scientific_verdict=None))
    print('B151_TRAINING_COMPLETE', run, cell, flush=True)
