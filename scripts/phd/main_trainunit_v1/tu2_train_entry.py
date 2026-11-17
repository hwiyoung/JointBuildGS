"""PHD-MAIN-TRAINUNIT-v2 container entry: the unchanged v1 entry (tu_train_entry.main) with
  - the v2 run names added to its EF table with the settings of the runs they copy (trainunit_v2.json runs), and
  - one read-only recorder (order v2 3.5 rows 1-3) every 1,000 iterations and at iteration 1: gaussian count, share of rows
    with min(scale)/max(scale) < 0.01 and < 0.1, host memory of the training process (VmRSS, VmHWM) and of the container
    (cgroup memory.current / memory.peak), CUDA allocated/reserved now and peak. No random numbers, no model write.
  python tu2_train_entry.py <run_name> <train.py args...>
"""
import hashlib
import json
import runpy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tu_train_entry as T  # noqa: E402

C = Path('/repo/configs/phd/main_trainunit_v1')
lock = json.loads((C / 'trainunit_v2.lock.json').read_text())
assert hashlib.sha256((C / 'trainunit_v2.json').read_bytes()).hexdigest() == lock['config_sha256'], 'trainunit_v2.json changed after lock'

# cells9ef = cellsef_ALS_s0_cell<k> (count rule recorded only, fork radius); <site>ef_LoD2_s<seed> = <site>ef_ALS_s<seed> (watch {})
T.EF.update({f'cells9ef_ALS_s0_cell{k}': dict(stop=None, extent=None, watch={}, count_record_only=True, v2=True) for k in range(9)})
T.EF.update({f'{s}ef_LoD2_s{seed}': dict(stop=None, extent=None, watch={}, v2=True) for s in ['B0', 'R1rep', 'B173nb'] for seed in [0, 1]})
# order v2 section 4 (prepared only, not launched): LoD2 for 전체 / 넷 / 아홉 with the settings of the ALS runs of the same plan
T.EF.update({'campusef30k_LoD2_s0': dict(stop=None, extent=None, watch={}, count_record_only=True, v2=True)})
T.EF.update({f'cellsef_LoD2_s0_cell{k}': dict(stop=None, extent=None, watch={}, count_record_only=True, v2=True) for k in range(4)})
T.EF.update({f'cells9ef_LoD2_s0_cell{k}': dict(stop=None, extent=None, watch={}, count_record_only=True, v2=True) for k in range(9)})
run_name = sys.argv[1]
assert run_name in T.EF and T.EF[run_name].get('v2'), run_name
argv = sys.argv[2:]
root = Path(argv[argv.index('-m') + 1]).parent


def cg(name):
    for p in [Path('/sys/fs/cgroup') / name]:
        try:
            return int(p.read_text().split()[0])
        except Exception:
            return None
    return None


def proc_status():
    out = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS', 'VmHWM')):
            k, v = line.split(':')
            out[k] = int(v.split()[0]) * 1024
    return out


_run_path = runpy.run_path
start = time.monotonic()


def run_path(path, run_name=None):
    import jbgs_state
    import torch
    inner = jbgs_state.after_step   # tu_train_entry.main has installed its after_step already
    f = (root / 'trace1000.jsonl').open('a')

    def after_step(env):
        it = env['iteration']
        if it == 1 or it % 1000 == 0:
            try:
                rec = record(env, it)
            except Exception as e:   # the recorder never stops training
                rec = dict(iteration=it, recorder_error=f'{type(e).__name__}: {e}'[:500])
            f.write(json.dumps(rec) + '\n')
            f.flush()
        return inner(env)

    def record(env, it):
        if True:
            with torch.no_grad():
                g = env['gaussians']
                s = g.get_scaling
                ar = s.min(dim=1).values / s.max(dim=1).values
                n = int(ar.numel())
                st = proc_status()
                rec = dict(iteration=it, seconds=time.monotonic() - start, gaussians=n,
                           elong_lt_001=float((ar < .01).float().mean()) if n else None, elong_lt_01=float((ar < .1).float().mean()) if n else None,
                           elong_q01_q10_q50=[float(v) for v in torch.quantile(ar[::max(1, n // 1_000_000)].float(), torch.tensor([.01, .1, .5], device=ar.device))] if n else None,
                           rss_bytes=st.get('VmRSS'), rss_peak_bytes=st.get('VmHWM'), cgroup_current_bytes=cg('memory.current'), cgroup_peak_bytes=cg('memory.peak'),
                           cuda_allocated_bytes=torch.cuda.memory_allocated(), cuda_reserved_bytes=torch.cuda.memory_reserved(),
                           cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated(), cuda_peak_reserved_bytes=torch.cuda.max_memory_reserved())
        return rec

    jbgs_state.after_step = after_step
    return _run_path(path, run_name=run_name)


runpy.run_path = run_path
T.main()
