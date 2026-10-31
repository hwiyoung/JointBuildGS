"""Validate v1 bytes and prepare geometry limits without reading GT heights."""
import json
import random
import os
from scipy import ndimage
from cp2_common import *
from prepare_places import representative

def main():
    oldpath = Path('/repo/configs/phd/main_candpick_v1/candpick_v1.json')
    old = json.loads(oldpath.read_text())
    assert sha(oldpath) == json.loads(oldpath.with_suffix('.lock.json').read_text())['sha256']
    checks = []; unitcfg = {}; inputs = [bind(oldpath)]
    jnc = json.loads(Path('/repo/configs/phd/main_judgenum_v1/judgenum_v1.json').read_text())
    sigmas = jnc['detection']['prior_sigma']['LoD2_roof']
    reps = json.loads(Path('/repo/docs/experiments/phd/main_candpick_v1/representatives_v1.json').read_text())['rows'][:3]
    (OUT / 'bounds').mkdir(exist_ok=True)
    for unit in UNITS:
        for b in old['units'][unit]['bindings']:
            path = Path(b['path'].replace('/out/', '/cp1/'))
            assert sha(path) == b['sha256'], path
            inputs.append(bind(path))
        for start in ['equal', 'right']:
            run = CP1 / 'runs' / f'cp_{start}_sh3_{unit}'
            receipt = json.loads((run / 'complete.json').read_text())
            assert receipt['status'] == 'COMPLETE' and receipt['iterations'] == 3000
            assert receipt['config_sha256'] == sha(oldpath)
            assert sha(run / 'candidate_3000.npz') == receipt['final_candidate_sha256']
            checks.append(dict(unit=unit, start=start, status='PASS', seconds=receipt['elapsed_seconds']))
            inputs += [bind(run / 'complete.json'), bind(run / 'candidate_3000.npz')]
        # No truth coordinates enter bounds. Read prior uncertainty/type and MVS uncertainty only.
        d = arrays(CP1 / 'places' / (unit + '.npz')); prior = unit.split('_')[1]
        sp = np.full(len(d['point_id']), np.nan); sm = sp.copy(); source_types = np.full(len(sp), '', dtype='<U40')
        for tile in sorted(set(d['tile'])):
            ppath = PC / 'points' / f'{tile}__{prior}.npz'
            mpath = PC / 'geometry' / f'{tile}__{prior}__mapping.npz'
            rpath = W / 'patch_values' / f'{tile}__{prior}__R1.5.npz'
            with np.load(ppath) as p, np.load(mpath) as mp, np.load(rpath) as raw:
                ix = np.flatnonzero(d['tile'] == tile)
                look = {str(x): i for i, x in enumerate(p['point_id'])}
                ids = np.array([look[str(x)] for x in d['point_id'][ix]])
                sm[ix] = np.sqrt(p['raw_u_mvs'][ids] ** 2 + .0275 ** 2)
                own = mp['point_index']; src = mp['source_index']
                geom = p['geometry_index'][ids]
                up = raw['u_prior'][src]; rt = raw['roof_type'][src]
                for target, owner in zip(ix, geom):
                    mask = own == owner
                    assert mask.any()
                    types = np.unique(rt[mask])
                    if prior == 'LoD2':
                        assert len(types) == 1, (unit, str(d['point_id'][target]), 'mixed roof type')
                        source_types[target] = types[0]
                        sp[target] = sigmas.get(str(types[0]), .11)
                    else:
                        v = up[mask]; v = v[np.isfinite(v)]
                        if len(v): sp[target] = np.sqrt(np.median(v) ** 2 + .0275 ** 2)
            inputs += [bind(ppath), bind(mpath), bind(rpath)]
        bpath = OUT / 'bounds' / (unit + '.npz')
        np.savez_compressed(bpath, point_id=d['point_id'], prior_sigma_m=sp, image_sigma_m=sm, roof_type=source_types)
        index = json.loads((CP1 / 'render_masks' / unit / 'index.json').read_text())
        names = [x['name'] for x in index['views']]
        rng = random.Random(0); remain = []; seq = []
        for _ in range(4000):
            if not remain: remain = names.copy()
            seq.append(remain.pop(rng.randint(0, len(remain)-1)))
        assert seq[:3000] == old['units'][unit]['camera_sequence']
        unitcfg[unit] = dict(camera_sequence=seq, bounds=bind(bpath), missing_prior_sigma=int((~np.isfinite(sp)).sum()),
                             missing_image_sigma=int((~np.isfinite(sm)).sum()), train_views=len(names))
        if unit == 'B173_LoD2':
            r = representative(d, (d['group'] == 'a') & (d['side'] == 'front'))
            reps.append(dict(id='B173_LoD2_front', unit=unit, selection=r,
                             status='AVAILABLE' if r else 'UNAVAILABLE_NO_1_TO_3M2_COMPONENT'))
        print(unit, 'validated inputs; sigma missing', unitcfg[unit]['missing_prior_sigma'], unitcfg[unit]['missing_image_sigma'], flush=True)
    cfg = dict(task_id='PHD-MAIN-CANDPICK-v2', prepared_at=now(), seed=0, units=unitcfg,
        inherited_config=bind(oldpath), docker_image=old['docker_image'], gsplat_version='1.4.0',
        loss=old['loss'], learning_rates=old['learning_rates'], adam=old['adam'], scoring=old['scoring'],
        initial_geometry=old['geometry'], opacity_initial=old['opacity_initial'], sh_degree=3,
        arms={
            'a':dict(name='앞 후보만', iterations=3000, change='Keep only four Gaussians of larger normal height per point; absent candidate opacity is zero in summaries.'),
            'b':dict(name='색 먼저 맞추기', iterations=4000, change='Opacity fixed for updates 1..1000, enabled for updates 1001..4000; same seed-zero sequence continued.'),
            'c':dict(name='모양 학습', iterations=3000, change='Train candidate means, raw quaternions and log inplane scales; clamp means to own normal-height +/-1.96 sigma and tangent coordinates +/-0.25m after each update.',
                     position_lr_init=.00016, position_lr_final=.0000016, position_lr_delay_mult=.01, position_lr_max_steps=30000,
                     position_lr_delay_steps=0, spatial_lr_scale='inherited exact camera normalization radius', rotation_lr=.001, scaling_lr=.005,
                     prior_sigma_rule='Appendix C; median finite raw u_prior for ALS; same-surface roof type for LoD2',
                     image_sigma_rule='sqrt(stored point raw_u_mvs squared + 0.0275 squared)',
                     missing_sigma='Stop only arm c for affected case; no imputation'),
            'd':dict(name='둘레 장면 학습', iterations=3000, change='Train only opacity/DC/SH of background centers within XY 3m of any original place point; background geometry and all other values fixed.')},
        log_every=100, snapshot_iterations=[0,500,1000,'end'], representatives=reps,
        representative_rule='Reuse first three v1 representatives. New B173_LoD2 uses the exact v1 representative() rule restricted to group a/front; maximize point count then area then lexical seed ID.',
        depth=dict(mode='expected', depth_ratio=0., source='GeoGS-conf-guided-v1-r18 arguments depth_ratio=0.0; gaussian_renderer surf_depth=sum(weight*ray-splat depth)/alpha; mesh_utils uses surf_depth',
            tau_m={'ALS':.1266,'LoD2':.2}, per_point='Pool equally weighted valid pixels across three largest native-support training views; median height along original point normal.',
            selection='Native v1 opacity-one candidate contributor IDs intersected with frozen v1 union mask; count unique point-pixel pairs, rank count descending then view name.',
            invalid='No finite positive rendered depth or fewer than three nonempty views retained as unavailable, never zero.'),
        photo=dict(range='abs(h)<=DL_point; DL_point=median finite JUDGENUM base DL_cm of owned source patches divided by 100',
            inherited_judgments=json.loads(Path('/repo/configs/phd/main_photocheck_v1/photocheck_v1.json').read_text())['judgments'],
            competition='outside range AND (inherited local maximum OR abs(h)>DL_point+0.3m)',
            selection='Reuse JUDGENUM-v1 analysis_core.select/summaries and frozen base judgment_after, 135 choices, ties, building equal and leave-one-out; no new geometry or images',
            stored_precision='Use stored float16 curves promoted to float32, preserve all other derive() operations; compare old-range replay with stored judgments and disclose precision differences.',
            holdout='All detailed values only /out/holdout; public counts, areas and SHA-256 only'),
        no_depth_loss=True, no_density_control=True, no_opacity_reset=True, no_cleanup=True, truth_used_in_loss=False,
        input_bindings=inputs, source=SOURCE, scientific_verdict=None)
    save(CFG / 'plan_before_views.json', cfg)
    save(DOC / 'tables/input_preflight.json', dict(status='PASS_V1_INPUTS', baselines=checks, units=unitcfg.keys() if False else list(unitcfg), at=now(), scientific_verdict=None))

if __name__ == '__main__': main()
