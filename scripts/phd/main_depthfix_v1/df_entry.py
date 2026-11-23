"""Training entry (GPU container, FINALTRAIN fork r23 at /source, unchanged). argv: <arm> <stem> <run> <stop_after|0> <train.py args...>
- checks the arm folder hashes (ready.json) and, for result runs, the config lock;
- installs the FINALTRAIN speed renderer (finaltrain_v1.json 'renderer', read only), as GTTARGET-v1/PRESCRIBE-v1;
- two-target arms (config arms[arm].two): Target.loss gets a second term over map keys depth2/weight2:
      loss = (Σ_valid1 w1|D̂−D1| + Σ_valid2 w2|D̂−D2|) / numel  (same validity rule and full-image denominator as r23 Target.loss)
  arms with two == false use r23 Target.loss untouched (no module patched);
- stop_after > 0: leave after the observe step of that iteration (probe / off-check), schedules unchanged."""
import runpy, sys, os, types
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *

class ProbeDone(Exception): pass

def main():
    arm, stem, run, stop = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]); argv = sys.argv[5:]
    probe = stop > 0
    c = cfg(locked=not probe); a = c['arms'][arm] if arm in c['arms'] else dict(two=False)
    root = Path(argv[argv.index('--jbgs_target_dir')+1]); rd = json.loads((root/'ready.json').read_text())
    tfile = root.parent.parent/'targets'/f'{stem}.npz'
    assert sha(tfile) == rd['target_sha256'] and sha(root/'seeds.npz') == rd['seeds_sha256'] and sha(root/'maps/index.json') == rd['index_sha256']
    for meta in json.loads((root/'maps/index.json').read_text())['views'].values(): assert sha(root/'maps'/meta['file']) == meta['sha256']
    model = Path(argv[argv.index('-m')+1]); assert not model.exists()
    dump(model.parent/'input_binding.json', dict(at=now(), arm=arm, stem=stem, run=run, probe=probe, config_sha256=sha(C/'depthfix_v1.json'), ready=rd,
        source_files={str(p.relative_to('/source')): sha(p) for p in sorted(Path('/source').glob('*.py'))},
        entry_sha256=sha(Path(__file__)), argv=sys.argv, scientific_verdict=None))
    sys.path.insert(0, '/source')
    shim = types.ModuleType('common'); shim.sha = sha
    shim.cfg = lambda: dict(renderer=json.loads((R/'configs/phd/main_finaltrain_v1/finaltrain_v1.json').read_text())['renderer'])
    sys.modules['common'] = shim; sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from renderer import install
    install()
    import torch, jbgs_target, jbgs_finaltrain
    if a.get('two'):
        orig_create = jbgs_target.create
        @torch.no_grad()
        def create(args, scene, g, render, pipe):
            tc = orig_create(args, scene, g, render, pipe)
            tc.maps2 = {}; n2 = 0
            for name, meta in tc.index['views'].items():
                with np.load(tc.root/'maps'/meta['file']) as z:
                    tc.maps2[name] = {k: torch.from_numpy(z[k]).pin_memory() for k in ['depth2', 'weight2']}; n2 += int((z['weight2'] > 0).sum())
            write = jbgs_target.write; write(tc.mon/'two_target.json', dict(views=len(tc.maps2), second_term_pixels=n2, scientific_verdict=None))
            return tc
        jbgs_target.create = create
        base_loss = jbgs_target.Target.loss
        def loss(self, name, render_depth):
            first = base_loss(self, name, render_depth)
            m = self.maps2[name]; D = render_depth.squeeze(0)
            t2 = m['depth2'].to(D.device, non_blocking=True); w2 = m['weight2'].to(D.device, non_blocking=True)
            v2 = torch.isfinite(t2) & (t2 > 0) & torch.isfinite(D) & (D > 0) & (w2 > 0)
            return first + (torch.abs(D[v2]-t2[v2])*w2[v2]).sum()/float(D.numel())
        jbgs_target.Target.loss = loss
    if probe:
        orig_obs = jbgs_finaltrain.FinalTrain.observe
        def observe(self, iteration, g, loss, rgb, depth, name):
            orig_obs(self, iteration, g, loss, rgb, depth, name)
            if iteration >= stop: raise ProbeDone(iteration)
        jbgs_finaltrain.FinalTrain.observe = observe
    sys.argv = ['/source/train.py'] + argv
    try:
        runpy.run_path('/source/train.py', run_name='__main__')
    except ProbeDone as e:
        dump(model.parent/'PROBE_COMPLETE.json', dict(at=now(), iteration=int(e.args[0]), scientific_verdict=None)); return
    last = int(argv[argv.index('--iterations')+1])
    assert (model/f'jbgs_complete/iteration_{last}/checkpoint.pth').is_file() and (model/f'point_cloud/iteration_{last}/point_cloud.ply').is_file()
    dump(model.parent/'TRAINING_COMPLETE.json', dict(at=now(), iteration=last, scientific_verdict=None))

if __name__ == '__main__': main()
