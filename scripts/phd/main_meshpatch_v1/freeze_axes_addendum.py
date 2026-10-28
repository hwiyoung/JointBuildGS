"""Freeze the user's 2026-10-29 addendum without replacing earlier input locks."""
import json
from pathlib import Path
from axes_adapter import ax, dm, MP, np
from mesh_common import sha, dump, now
C = Path('/config')
D = Path('/docs')


def canonical(p):
    p = Path(p)
    return ax.PH / 'main_stage1_v1/PHD-MAIN-STAGE1-v1' / p.relative_to('/out') if str(p).startswith('/out/') else p


def main():
    dest = C / 'axes_addendum_v1.json'
    assert not dest.exists(), dest
    old = json.loads((C / 'mesh_targets_v1.json').read_text())
    targets = {r['key']: r for r in old['targets']}
    additions, priority, choices, pins = [], [], [], {}
    def pin(p, site=None):
        p = Path(p)
        if str(p) not in pins:
            assert p.is_file(), p
            pins[str(p)] = dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p), site=site)
    for site in ax.SITES:
        for prior in ax.PRIORS:
            for method in ['twodgs', 'geogs', 'mvsfuse', 'cdgs', 'method']:
                for result in ax.results_of(method, prior):
                    key = f'{site}__{prior}__{result}'
                    priority.append(key)
                    mesh = canonical(ax.mesh_of(site, result)[0])
                    if key not in targets:
                        ev = ax.PH / 'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2' / f'{site}__{prior}/evaluation.npz'
                        val = ev.with_name('values.npz')
                        r = dict(key=key, site=site, prior=prior, result=result, groups=['stage1', 'axes_addendum'],
                                 mesh=str(mesh), exists=mesh.is_file(), evaluation=str(ev), values=str(val), method=method)
                        if mesh.is_file():
                            r.update(status='READY', bytes=mesh.stat().st_size, sha256=sha(mesh), evaluation_sha256=sha(ev), values_sha256=sha(val))
                        else:
                            r.update(status='UNAVAILABLE', reason='AXES71-v2 method mesh absent')
                        additions.append(r)
                        targets[key] = r
                    r = targets[key]
                    if r['status'] == 'READY':
                        choices.append(dict(key=key, method=method, bytes=r['bytes']))
            for p in [ax.S1 / f'regions_v3/regions_ext_v3_{site}_{prior}.npz',
                      ax.S1 / f'defs/{site}/rows_{prior}.npz',
                      ax.S1 / f'v3/box_gt/{site}/gt_owner_{"uls_" if site.startswith("B0") else ""}{prior}.npz',
                      ax.WORK / f'cells_{site}_{prior}.npz', ax.WORK / f'prefilter_{site}_{prior}.npz',
                      ax.FL / f'work/obs_masked/region_{site}_{prior}.npz',
                      Path('/s0') / f's61/box/{site}/{prior}/units.npz']:
                pin(p, site)
            e = np.load(targets[f'{site}__{prior}__prop_{prior}_s0']['evaluation'])
            reg = np.load(ax.S1 / f'regions_v3/regions_ext_v3_{site}_{prior}.npz')
            assert np.array_equal(e['centre'], reg['centre']), (site, prior, 'cell identity')
        for p in [ax.S1 / f'defs/{site}/gt_classes.npz', ax.S1 / f'defs/{site}/bsurf.npz',
                  ax.WORK / f'normals_{site}.npz', Path('/dr') / f's02_box/{site}/lod2_surfaces.json']:
            pin(p, site)
    for folder in ['scripts/phd/main_axes71_v2', 'scripts/phd/main_dist71_v1', 'scripts/phd/main_stage1_v1', 'src/phd/metrics_v3']:
        for p in sorted((Path('/repo') / folder).glob('*.py')):
            pin(p)
    for p in [ax.CFGP, ax.CFGP.with_name('axes71_v2.lock.json'), ax.TAB/'a3_metrics.json', ax.TAB/'a4_axes.json',
              C/'mesh_targets_v1.json', C/'mesh_metric_inputs_v1.json']:
        pin(p)
    # The smallest named stage-1 result is an execution-cost choice, made before its values are read.
    baseline = min(choices, key=lambda x: (x['bytes'], x['key']))
    cfg = dict(task_id='PHD-MAIN-MESHPATCH-v1', addendum='2026-10-29 01:00 KST user message', frozen_at=now(),
               extra_targets=additions, stage1_first_keys=priority, metric_keys=list(targets), baseline=baseline,
               inputs=list(pins.values()), crs='EPSG:25832',
               metrics=dict(scripts='AXES71-v2 a2x_sample.full_dist, Ref.query, ax_arrays.gt_block/res_block, a4_axes.bins_of/value unchanged',
                            result_count='E: normal distance, lateral distance <= 0.5 m; excluded counts retained',
                            means='uncapped; stored cm, shares 0..1', gt_appendix=['med', 'out4', 'far1'],
                            cells='Existing LOSSTRAIN cells 0..5 with original eligibility; all AXES71 named cells separately retained',
                            axes='Original region-v3 axes, original cached cells/prefilter; no new visibility or region calculation',
                            virtual='Only requested training-view whole-mesh cleanup. AXES71 virtual-only cells remain unavailable.'),
               parity_tolerance=dict(share_abs=1e-10, distance_cm_abs=1e-5), deadline_kst='2026-10-30T09:30:00+09:00',
               resource_rule='GPU training first; shared tsdf.lock, MemAvailable >=56 GiB for60 s,40GiB/8CPU max', scientific_verdict=None)
    dump(dest, cfg)
    dump(C/'axes_addendum_v1.lock.json', dict(sha256=sha(dest), frozen_at=now(), before_first_axes_calculation=True, scientific_verdict=None))
    dump(D/'tables/axes_addendum_inventory.json', dict(extra_targets=additions, stage1_first_keys=priority, metric_targets=len(targets), baseline=baseline, scientific_verdict=None))
    print(json.dumps(dict(extra_targets=len(additions), metric_targets=len(targets), priority_targets=len(priority), baseline=baseline, pins=len(pins)), ensure_ascii=False))


if __name__ == '__main__':
    main()
