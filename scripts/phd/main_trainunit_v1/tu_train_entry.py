"""Container entry: verify the TRAINUNIT lock, install the FINALTRAIN renderer, run the unchanged r23 train.py.

Only two host-side controls are added around the unchanged jbgs_state.after_step hook:
  - at iteration 500 the locked time rule (projected = factor x elapsed) may stop the run (no state needed);
  - a stop file (deadline) makes the unchanged capture code write a complete state at the next multiple of 100, then stop.
Neither control changes any value used by the optimisation.
"""
import datetime as dt
import hashlib
import importlib.util
import json
import runpy
import sys
import time
from pathlib import Path

C = Path('/repo/configs/phd/main_trainunit_v1')
# addendum 12: elongation-filter runs (stop iteration, fixed extent, watched families)
EF = {
    'probe3ef_ALS_s0': dict(stop=15000, extent=185.84960770264462, watch_unit='probe3'),
    'probe4ef_ALS_s0': dict(stop=15000, extent=199.23552905804456, watch_unit='probe4'),
    'cell0ef_ALS_s0': dict(stop=15000, extent=None, watch={'cell0#1': [124654], 'cell0#2': [123105], 'cell0#3': [130744]}),
    'B0ef_ALS_s0': dict(stop=None, extent=None, watch={'base_s0#1': [17310], 'base_s0#2': [15779], 'base_s0#3': [17176], 'base_s0#bg1': [45212]}),
    # addendum 13: the same run with seed 1 (the seed of the seed-1 repeat)
    'B0ef_ALS_s1': dict(stop=None, extent=None, watch={'base_s0#1': [17310], 'base_s0#2': [15779], 'base_s0#3': [17176], 'base_s0#bg1': [45212]}),
    # addendum 14: 판 다 ALS cells with the filter (count rule recorded only, as addendum 4) and filter single-site runs of R1rep/B173nb
    **{f'cellsef_ALS_s0_cell{k}': dict(stop=None, extent=None, watch={}, count_record_only=True, addendum=14) for k in range(4)},
    'R1repef_ALS_s0': dict(stop=None, extent=None, watch={}, addendum=14),
    'B173nbef_ALS_s0': dict(stop=None, extent=None, watch={}, addendum=14),
    # addendum 15: R1repef with seed 1 (filter seed spread at R1rep)
    'R1repef_ALS_s1': dict(stop=None, extent=None, watch={}, addendum=15),
    # addendum 16: 판 가 and 판 나 with the filter (count rule recorded only, as the 판 다 cells), B173nbef with seed 1
    'campusef30k_ALS_s0': dict(stop=None, extent=None, watch={}, count_record_only=True, addendum=16),
    'campusef120k_ALS_s0': dict(stop=None, extent=None, watch={}, count_record_only=True, addendum=16),
    'B173nbef_ALS_s1': dict(stop=None, extent=None, watch={}, addendum=16),
    # addendum 17: 판 다 cell 1 with the scene radius of the R1rep single-site run (R1repef_ALS_s0 extent_override.json)
    'cellsef_ALS_s0_cell1fix': dict(stop=None, extent=229.69646911621095, watch={}, count_record_only=True, addendum=17),
}
FTC = Path('/repo/configs/phd/main_finaltrain_v1/finaltrain_v1.json')
KST = dt.timezone(dt.timedelta(hours=9))


def now():
    return dt.datetime.now(KST)


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def dump(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def install_count_record_only(cls):
    """addendum 4: when FINALTRAIN would raise FINALTRAIN_HEALTH_STOP_count_gt_3x_6000, rename its STOP.json to
    health_override_<iteration>.json, append health_override.jsonl and let training continue. Other errors are re-raised."""
    original_observe = cls.observe

    def observe(self, iteration, g, loss, rgb, depth, name):
        try:
            return original_observe(self, iteration, g, loss, rgb, depth, name)
        except RuntimeError as e:
            if str(e) != 'FINALTRAIN_HEALTH_STOP_count_gt_3x_6000':
                raise
            stop = self.mon / 'STOP.json'
            rec = json.loads(stop.read_text())
            stop.rename(self.mon / f'health_override_{iteration}.json')
            with (self.mon / 'health_override.jsonl').open('a') as f:
                f.write(json.dumps(dict(at=now().isoformat(), iteration=iteration, gaussians=rec['gaussians'],
                                        count_at_6000=rec.get('count_at_6000'), reason=rec['reason'], addendum=4,
                                        action='recorded, training continues', scientific_verdict=None)) + '\n')
            print('TRAINUNIT_HEALTH_OVERRIDE', iteration, rec['gaussians'], rec.get('count_at_6000'), flush=True)

    cls.observe = observe


def install_elongation_filter(root, threshold=0.01):
    """addendum 12: CityGaussianV2 elongation filter (axis_ratio_threshold 0.01, Linketic/CityGaussian 3041bf5a). Rows whose
    min(scale)/max(scale) <= threshold get xyz_gradient_accum = 0 before the unchanged densify_and_prune, so neither clone nor split
    (both select grads = accum/denom >= threshold) picks them. Pruning does not read the gradient; densification_postfix resets the
    accumulator for all rows right after, as before."""
    import torch
    from scene.gaussian_model import GaussianModel
    original = GaussianModel.densify_and_prune

    def densify_and_prune(self, max_grad, min_opacity, extent, max_screen_size):
        with torch.no_grad():
            s = self.get_scaling
            needle = (s.min(dim=1).values / s.max(dim=1).values) <= threshold
            self.xyz_gradient_accum[needle] = 0.0
        return original(self, max_grad, min_opacity, extent, max_screen_size)

    GaussianModel.densify_and_prune = densify_and_prune
    dump(root / 'addendum12_filter.json', dict(at=now().isoformat(), threshold=threshold, rule='axis_ratio > threshold eligible for clone and split',
                                               source='Linketic/CityGaussian 3041bf5a citygsv2_density_controller.py', scientific_verdict=None))


def install_family_monitor(root, watch_path, state, watch=None, filter_threshold=None):
    """addendum 8: read-only record of each densification step, grouped by seed family (init_id) and lineage (origin).
    Recomputes on copies the clone/split selection of the unchanged densify_and_prune, then calls it unchanged.
    No random numbers are drawn and no model tensor is written.
    addendum 12: watch may be given directly; with filter_threshold the recorded clone/split are those after the elongation filter,
    and every group also records needle rows (elongation <= 0.01) and gradient-selected rows excluded by the filter."""
    import time as _t
    import torch
    from scene.gaussian_model import GaussianModel
    if watch is None:
        w = json.loads(Path(watch_path).read_text())
        watch = {f"{f['cell']}#{f['rank']}": [int(i) for i in f['unit_init_ids']] for f in w['families']}
    original = GaussianModel.densify_and_prune
    out = (root / 'family_monitor.jsonl').open('a')

    def qs(x, q):
        if x.numel() == 0:
            return None
        y = x[::max(1, x.numel() // 1_000_000)].float()
        return [float(v) for v in torch.quantile(y, torch.tensor(q, device=y.device))]

    def densify_and_prune(self, max_grad, min_opacity, extent, max_screen_size):
        t0 = _t.perf_counter()
        with torch.no_grad():
            g = self.xyz_gradient_accum / self.denom
            g[g.isnan()] = 0.0
            g = g.reshape(-1)
            den = self.denom.reshape(-1)
            sc = self.get_scaling
            ms = sc.max(dim=1).values
            ar = sc.min(dim=1).values / ms
            needle = ar <= .01
            op = self.get_opacity.reshape(-1)
            thr = self.percent_dense * extent
            sel = g >= max_grad
            ex = self.density_exempt()
            if ex is not None:
                sel = sel & ~ex
            excluded = sel & (ar <= filter_threshold) if filter_threshold is not None else torch.zeros_like(sel)
            sel = sel & ~excluded
            clone, split = sel & (ms <= thr), sel & (ms > thr)
            iid = self.init_id.long()
            org = self.origin.long() if self.origin is not None else torch.full_like(iid, -1)
            cnt = torch.bincount(iid[iid >= 0])
            top = torch.topk(cnt, min(5, cnt.numel()))
            groups = {f'watch:{k}': torch.tensor(v, device=iid.device) for k, v in watch.items() if v}
            groups |= {f'top{r + 1}:{int(i)}': torch.tensor([int(i)], device=iid.device) for r, i in enumerate(top.indices.tolist())}

            def stat(m):
                return dict(n=int(m.sum()), clone=int((clone & m).sum()), split=int((split & m).sum()),
                            needle=int((needle & m).sum()), filter_excluded=int((excluded & m).sum()),
                            grad_p50_p90=qs(g[m], [.5, .9]), grad_max=float(g[m].max()) if m.any() else None,
                            denom_p50=qs(den[m], [.5]), max_scale_p50_p90=qs(ms[m], [.5, .9]), opacity_p50=qs(op[m], [.5]),
                            radii2d_p50_p90=qs(self.max_radii2D[m], [.5, .9]))
            masks = {k: torch.isin(iid, v) for k, v in groups.items()}
            masks |= {'prior_lineage': org == 1, 'background_lineage': org == 0}
            before = {k: stat(m) for k, m in masks.items()}
            ids = {k: v for k, v in groups.items()}
            n0 = len(iid)
        t1 = _t.perf_counter()
        res = original(self, max_grad, min_opacity, extent, max_screen_size)
        t2 = _t.perf_counter()
        with torch.no_grad():
            iid2 = self.init_id.long()
            org2 = self.origin.long() if self.origin is not None else torch.full_like(iid2, -1)
            after = {k: int(torch.isin(iid2, v).sum()) for k, v in ids.items()}
            after |= {'prior_lineage': int((org2 == 1).sum()), 'background_lineage': int((org2 == 0).sum())}
        for k in before:
            b = before[k]
            b['n_after'] = after[k]
            b['pruned_est'] = b['n'] + b['clone'] + b['split'] - after[k]  # split: +2 children -1 parent
        rec = dict(iteration=state.get('it', 0) + 1, n_before=n0, n_after=len(iid2), max_grad=float(max_grad), min_opacity=float(min_opacity),
                   extent=float(extent), clone_scale_threshold=float(thr), max_screen_size=max_screen_size,
                   clone_total=int(clone.sum()), split_total=int(split.sum()), needle_total=int(needle.sum()),
                   filter_excluded_total=int(excluded.sum()), filter_threshold=filter_threshold, groups=before,
                   monitor_seconds=(t1 - t0) + (_t.perf_counter() - t2), densify_seconds=t2 - t1)
        out.write(json.dumps(rec) + '\n')
        out.flush()
        return res

    GaussianModel.densify_and_prune = densify_and_prune
    dump(root / 'addendum8_monitor.json', dict(at=now().isoformat(), watch=watch, groups='watched families, 5 largest families, prior/background lineage',
                                               scientific_verdict=None))


def main():
    run_name = sys.argv[1]
    lock = json.loads((C / 'trainunit_v1.initial.lock.json').read_text())
    assert sha(C / 'trainunit_v1.json') == lock['config_sha256'], 'TRAINUNIT config changed after lock'
    cfg = json.loads((C / 'trainunit_v1.json').read_text())
    deadline = dt.datetime.fromisoformat(cfg['gpu']['deadline'])
    add2 = json.loads((C / 'addendum2.json').read_text())
    assert sha(C / 'addendum2.json') == json.loads((C / 'addendum2.lock.json').read_text())['sha256']
    factor = 229.7
    lifted = False
    if (C / 'addendum3.json').exists() and run_name.startswith('cells_'):
        assert sha(C / 'addendum3.json') == json.loads((C / 'addendum3.lock.json').read_text())['sha256']
        lifted = True  # addendum 3: no 11:00 deadline and no 500-iteration time stop for 판 다
    probe_stop = None
    if run_name in EF:
        # addendum 12: no deadline / 500-iteration stop (the TRAINUNIT deadline has passed); stop as locked per run
        assert sha(C / 'addendum12.json') == json.loads((C / 'addendum12.lock.json').read_text())['sha256']
        if run_name == 'B0ef_ALS_s1':
            assert sha(C / 'addendum13.json') == json.loads((C / 'addendum13.lock.json').read_text())['sha256']
        if EF[run_name].get('addendum') == 14:
            assert sha(C / 'addendum14.json') == json.loads((C / 'addendum14.lock.json').read_text())['sha256']
        if EF[run_name].get('addendum') == 15:
            assert sha(C / 'addendum15.json') == json.loads((C / 'addendum15.lock.json').read_text())['sha256']
        if EF[run_name].get('addendum') == 16:
            assert sha(C / 'addendum16.json') == json.loads((C / 'addendum16.lock.json').read_text())['sha256']
        if EF[run_name].get('addendum') == 17:
            assert sha(C / 'addendum17.json') == json.loads((C / 'addendum17.lock.json').read_text())['sha256']
        lifted = True
        probe_stop = EF[run_name]['stop']
    elif run_name.startswith('probe'):
        # addendum 5 (원인 확인): no deadline / 500-iteration stop; count rule recorded only; stop right after iteration 15,000
        assert sha(C / 'addendum5.json') == json.loads((C / 'addendum5.lock.json').read_text())['sha256']
        lifted = True
        probe_stop = 15000
    argv = sys.argv[2:]
    model = Path(argv[argv.index('-m') + 1])
    assert not model.exists(), model
    control = Path(argv[argv.index('--jbgs_target_dir') + 1])
    stopfile = Path('/tu/control') / f'STOP_{run_name}'
    root = model.parent

    ft = json.loads(FTC.read_text())['renderer']
    import torch
    import diff_surfel_rasterization as raster
    assert sha(ft['path']) == ft['sha256']
    spec = importlib.util.spec_from_file_location('jbgs_rfix_speed_target', ft['path'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.jbgs_set_guard(ft['binning_guard_fraction'])
    raster._C = module

    sys.path.insert(0, '/source')
    import jbgs_state
    import math
    import jbgs_target_r6
    original_restore = jbgs_target_r6.restore_complete

    def restore_complete(path, saved, env):
        # addendum 3: r6 resume compares saved and current args with !=, which is True for NaN == NaN defaults
        # (jbgs_tau_v/roof/wall). Only keys whose saved and current values are both NaN are treated as equal.
        args = env['args']
        same_nan = [k for k, v in saved['args'].items() if isinstance(v, float) and isinstance(getattr(args, k, None), float)
                    and math.isnan(v) and math.isnan(getattr(args, k))]
        for k in same_nan:
            del saved['args'][k]
        dump(root / 'resume_nan_args.json', dict(at=now().isoformat(), checkpoint=str(path), keys_both_nan=same_nan, scientific_verdict=None))
        return original_restore(path, saved, env)

    jbgs_target_r6.restore_complete = restore_complete
    if probe_stop is not None or EF.get(run_name, {}).get('count_record_only') or ((C / 'addendum4.json').exists() and run_name.startswith('cells_')):
        # addendum 4 (user '이어 돌리기'): the FINALTRAIN count rule is recorded, not enforced, for 판 다 cells.
        assert sha(C / 'addendum4.json') == json.loads((C / 'addendum4.lock.json').read_text())['sha256']
        import jbgs_finaltrain
        install_count_record_only(jbgs_finaltrain.FinalTrain)
        dump(root / ('addendum5_entry.json' if probe_stop else 'addendum4_entry.json'),
             dict(at=now().isoformat(), count_rule='record-only', probe_stop=probe_stop, scientific_verdict=None))
    original = jbgs_state.after_step
    state = dict(checked500=False, stop_capture=None)
    if run_name in EF:
        # addendum 12: elongation filter first, then the read-only monitor around it; probe units keep the addendum 9 extent
        e = EF[run_name]
        install_elongation_filter(root, 0.01)
        if e.get('watch_unit'):
            install_family_monitor(root, Path('/tu/stage1') / f'{e["watch_unit"]}__ALS' / 'watch.json', state, filter_threshold=0.01)
        else:
            install_family_monitor(root, None, state, watch=e['watch'], filter_threshold=0.01)
        import scene.dataset_readers as dr
        fork_norm12 = dr.getNerfppNorm

        def getNerfppNorm12(cam_info):
            n = fork_norm12(cam_info)
            dump(root / 'extent_override.json', dict(at=now().isoformat(), run=run_name, fork_radius=float(n['radius']), cameras=len(cam_info), addendum=12,
                                                     used_radius=float(e['extent'] or n['radius']), fixed=e['extent'] is not None, scientific_verdict=None))
            return dict(n, radius=float(e['extent'])) if e['extent'] is not None else n

        dr.getNerfppNorm = getNerfppNorm12
    elif run_name.startswith(('probe3', 'probe4')):
        # addendum 8: runaway-roof probes get the read-only family monitor
        assert sha(C / 'addendum8.json') == json.loads((C / 'addendum8.lock.json').read_text())['sha256']
        install_family_monitor(root, Path('/tu/stage1') / f'{run_name.split("_")[0].replace("own", "")}__ALS' / 'watch.json', state)
        # addendum 9: probe3/probe4 use the scene extent of the cell where the roof ran away (probe3own keeps its own)
        assert sha(C / 'addendum9.json') == json.loads((C / 'addendum9.lock.json').read_text())['sha256']
        fixed = {'probe3_ALS_s0': 185.84960770264462, 'probe4_ALS_s0': 199.23552905804456}.get(run_name)
        import scene.dataset_readers as dr
        fork_norm = dr.getNerfppNorm

        def getNerfppNorm(cam_info):
            n = fork_norm(cam_info)
            rec = dict(at=now().isoformat(), run=run_name, fork_radius=float(n['radius']), cameras=len(cam_info), addendum=9,
                       used_radius=float(fixed) if fixed is not None else float(n['radius']), fixed=fixed is not None, scientific_verdict=None)
            dump(root / 'extent_override.json', rec)
            if fixed is not None:
                n = dict(n, radius=float(fixed))
            return n

        dr.getNerfppNorm = getNerfppNorm

    def after_step(env):
        it = env['iteration']
        state['it'] = it
        args = env['args']
        if it == 501 and not state['checked500'] and not lifted:
            # same clock as the locked factor: target_monitor/curve.jsonl elapsed_seconds at iteration 500
            state['checked500'] = True
            rows = [json.loads(l) for l in (model / 'target_monitor/curve.jsonl').read_text().splitlines() if l.strip()]
            elapsed = next(r['elapsed_seconds'] for r in rows if r['iteration'] == 500)
            e1 = next(r['elapsed_seconds'] for r in rows if r['iteration'] == 1)
            d = elapsed - e1
            total_iter = args.iterations
            projected = factor * d * (total_iter / 30000.0)
            end = now() + dt.timedelta(seconds=projected - d)
            rec = dict(at=now().isoformat(), iteration=500, elapsed_seconds=elapsed, elapsed_at_1=e1, d_1_to_500=d,
                       rule='addendum2: projected end = now + (factor - 1) x d', clock='target_monitor curve.jsonl elapsed_seconds',
                       factor=factor, projected_total_seconds=projected, projected_end=end.isoformat(), deadline=deadline.isoformat(),
                       gaussians=len(env['gaussians'].get_xyz),
                       peak_reserved_bytes=torch.cuda.max_memory_reserved(), scientific_verdict=None)
            dump(root / 'time_check_500.json', rec)
            if end > deadline:
                rec['status'] = 'TIME_STOP_500'
                dump(root / 'TIME_STOP.json', rec)
                print('TRAINUNIT_TIME_STOP', json.dumps(rec), flush=True)
                original(env)
                return True
        if state['stop_capture'] is None and it % 100 == 0 and stopfile.exists():
            state['stop_capture'] = it
            if it not in args.jbgs_capture_iterations:
                args.jbgs_capture_iterations = list(args.jbgs_capture_iterations) + [it]
            dump(root / 'DEADLINE_STOP.json', dict(at=now().isoformat(), iteration=it, gaussians=len(env['gaussians'].get_xyz),
                 complete_state=f'model/jbgs_complete/iteration_{it}', peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                 scientific_verdict=None))
            original(env)
            print('TRAINUNIT_DEADLINE_STOP', it, flush=True)
            return True
        if probe_stop is not None and it == probe_stop:
            out = original(env)  # unchanged hook first (the 15,000 complete state is captured as in every run)
            dump(root / 'PROBE_STOP.json', dict(at=now().isoformat(), iteration=it, gaussians=len(env['gaussians'].get_xyz),
                 peak_reserved_bytes=torch.cuda.max_memory_reserved(), peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                 hook_returned=bool(out), scientific_verdict=None))
            print('TRAINUNIT_PROBE_STOP', it, flush=True)
            return True
        return original(env)

    jbgs_state.after_step = after_step
    dump(root / 'input_binding.json', dict(at=now().isoformat(), run=run_name, config_sha256=lock['config_sha256'],
         renderer=ft, target_dir=str(control), argv=argv, scientific_verdict=None))
    sys.argv = ['/source/train.py'] + argv
    try:
        runpy.run_path('/source/train.py', run_name='__main__')
    except Exception as e:
        text = f'{type(e).__name__}: {e}'
        dump(root / 'ERROR.json', dict(at=now().isoformat(), error=text[:4000], oom='out of memory' in text.lower(),
             peak_reserved_bytes=torch.cuda.max_memory_reserved(), peak_allocated_bytes=torch.cuda.max_memory_allocated(),
             scientific_verdict=None))
        raise
    final = args_iterations(argv)
    if (model / f'jbgs_complete/iteration_{final}/checkpoint.pth').is_file() and (model / f'point_cloud/iteration_{final}/point_cloud.ply').is_file():
        dump(root / 'TRAINING_COMPLETE.json', dict(at=now().isoformat(), iteration=final, scientific_verdict=None))


def args_iterations(argv):
    return int(argv[argv.index('--iterations') + 1])


if __name__ == '__main__':
    main()
