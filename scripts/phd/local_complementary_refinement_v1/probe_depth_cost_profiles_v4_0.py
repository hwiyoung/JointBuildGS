"""Bounded synthetic cost profiles. No learned confidence or new depth targets."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scripts.phd.local_complementary_refinement_v1 import photometric_walkthrough_v3_2 as photo
from scripts.phd.local_complementary_refinement_v1 import audit_observation_identifiability_v3_9 as fixtures
from src.phd import local_normal_photometry_v3_7 as geometry


def intervals(mask, depths):
    ids = np.flatnonzero(mask)
    if not len(ids):
        return []
    groups = np.split(ids, np.flatnonzero(np.diff(ids) > 1) + 1)
    return [{'minimum_depth_m': float(depths[g].min()),
             'maximum_depth_m': float(depths[g].max()), 'grid_points': len(g)} for g in groups]


def describe(costs, inverse_depths, levels, tol):
    if not np.isfinite(costs).all():
        return {'status': 'UNDEFINED_PROFILE', 'valid_points': int(np.isfinite(costs).sum())}
    depths = 1 / inverse_depths
    emin, emax = float(costs.min()), float(costs.max())
    best = int(np.argmin(costs))
    # Numerical plateaus are separate from a calibrated near-equal-cost basin.
    at_best = costs <= emin + tol
    is_flat = emax - emin <= tol
    local = np.zeros(len(costs), bool)
    if not is_flat:
        local[1:-1] = ((costs[1:-1] <= costs[:-2] + tol) &
                       (costs[1:-1] <= costs[2:] + tol) &
                       ((costs[1:-1] < costs[:-2] - tol) |
                        (costs[1:-1] < costs[2:] - tol)))
    groups = intervals(at_best, depths)
    minima = [{'depth_m': float(depths[k]), 'cost': float(costs[k])} for k in np.flatnonzero(local)]
    return {'status': 'NUMERICALLY_FLAT' if is_flat else 'FINITE_PROFILE',
            'minimum_cost': emin, 'maximum_cost': emax, 'cost_range': emax-emin,
            'argmin_depth_m': float(depths[best]),
            'argmin_is_unique_at_numeric_tolerance': bool(at_best.sum() == 1),
            'argmin_reporting_rule': 'first_numeric_argmin_only_not_a_selected_depth',
            'minimum_touches_boundary': bool(at_best[0] or at_best[-1]),
            'global_minimum_intervals_at_numeric_tolerance': groups,
            'local_minima': minima,
            'excess_cost_intervals': [{'excess_cost': float(eps),
                'intervals': intervals(costs <= emin + eps + tol, depths)} for eps in levels],
            'calibrated_identifiability': None, 'source_weight': None}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--commit', required=True)
    a = p.parse_args()
    assert Path('/.dockerenv').exists()
    cfg = photo.read(a.config)
    fixture_config = ROOT / cfg['fixture_config']
    old = photo.read(fixture_config)
    assert cfg['scientific_verdict'] is None and not cfg['real_gt_input'] and not cfg['training']
    assert os.environ['JBGS_RUNTIME_IMAGE_ID'] == cfg['docker_image']
    a.output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    dependencies = [a.config, fixture_config, Path(__file__), Path(fixtures.__file__),
                    Path(photo.__file__), Path(geometry.__file__)]
    before = {str(f): photo.sha(f) for f in dependencies}
    rows, summaries, checks, arrays = [], [], [], {}
    def check(name, ok):
        checks.append({'name': name, 'passed': bool(ok)})
    size, f = old['image_size'], old['focal_px']
    cx, cy = old['center']
    K = np.array([[f,0,cx],[0,f,cy],[0,0,1.]])
    ref = dict(K=K, R=np.eye(3), t=np.zeros(3))
    y, x = np.mgrid[:size,:size].astype(float)
    image_rays = geometry.rays(np.stack([x,y],-1), K)
    for kind in old['fixture_names']:
        true_normal = np.array(old['slanted_normal'] if kind == 'slanted_textured_plane' else [0,0,1.])
        true_offset = old['plane_offset']
        ref_rgb = np.repeat(fixtures.texture(x,y,kind)[...,None],3,-1)
        neighbors = []
        for j,b in enumerate(old['neighbor_baselines']):
            z = (true_offset - true_normal[0]*b) / (image_rays @ true_normal)
            X = image_rays*z[...,None] + np.array([b,0,0])
            g = fixtures.texture(f*X[...,0]/X[...,2]+cx, f*X[...,1]/X[...,2]+cy, kind)
            if kind == 'affine_brightness':
                g = .7*g + .12
            if kind == 'occluding_patch':
                occ = (abs(x-(cx-f*b/true_offset)) <= 20) & (abs(y-cy) <= 20)
                noise = np.random.default_rng(old['occluder_random_seed']+j).uniform(.1,.9,g.shape)
                g = np.where(occ, noise, g)
            neighbors.append((dict(K=K,R=np.eye(3),t=np.array([-b,0,0])), np.repeat(g[...,None],3,-1)))
        uv9 = photo.uv_grid(old['center'],9)
        d9 = true_offset/(geometry.rays(uv9,K)@true_normal)
        normal = geometry.estimate_normal(uv9,d9,np.ones_like(d9,bool),K,9,.8)
        n = np.asarray(normal['normal_camera'])
        for grid in cfg['inverse_depth_grids']:
            eta = np.linspace(grid['minimum'],grid['maximum'],grid['count'])
            curves = []
            for r in old['patch_sizes']:
                uv = photo.uv_grid(old['center'],r)
                rays = geometry.rays(uv,K)
                A = geometry.crop(ref_rgb,r)
                # The center depth varies; orientation and source-valid support stay fixed.
                depth_stack = (n[2]/eta)[:,None,None] / (rays@n)[None,...]
                for j,(camera,rgb) in enumerate(neighbors):
                    projected, z, _ = photo.project(np.broadcast_to(uv,depth_stack.shape+(2,)), depth_stack, ref,camera)
                    warped, mask = photo.bilinear(rgb,projected)
                    common = np.all(mask & (z>0),axis=0)
                    costs, stds = [], []
                    for W in warped:
                        score,_ = photo.score(A,W,common,old['epsilon'])
                        costs.append(np.nan if score['cost'] is None else score['cost'])
                        stds.append([score['std_reference'],score['std_warp']])
                    curve = np.asarray(costs)
                    curves.append(curve)
                    stats = describe(curve,eta,cfg['display_excess_cost_levels'],cfg['numeric_tolerance'])
                    key = f'{kind}_{grid["name"]}_r{r}_j{j}'
                    arrays[key] = curve
                    rows.append({'fixture':kind,'grid':grid['name'],'patch_size':r,'neighbor':j,
                        'common_count':int(common.sum()),'common_fraction':float(common.mean()),
                        'texture_std_by_grid': stds, 'array_key':key,'statistics':stats})
            curves = np.asarray(curves)
            aggregate = np.median(curves,axis=0)
            key = kind+'_'+grid['name']+'_aggregate'
            arrays[key] = aggregate
            arrays['eta_'+grid['name']] = eta
            summary = {'fixture':kind,'grid':grid['name'],'array_key':key,
                'statistics':describe(aggregate,eta,cfg['display_excess_cost_levels'],cfg['numeric_tolerance']),
                'target_samples':[]}
            for d in cfg['source_target_depths_m']:
                idx = int(np.argmin(abs(eta-1/d)))
                available = abs(eta[idx]-1/d) <= cfg['numeric_tolerance']
                e = float(aggregate[idx]) if available and np.isfinite(aggregate[idx]) else None
                summary['target_samples'].append({'depth_m':d,'on_grid':bool(available),'cost':e})
            summaries.append(summary)
    main_stats = {s['fixture']:s for s in summaries if s['grid']==cfg['primary_grid']}
    for kind in ['textured_plane','slanted_textured_plane','affine_brightness']:
        check(kind+'_minimum_at_known_depth', abs(main_stats[kind]['statistics']['argmin_depth_m']-old['plane_offset']) < 1e-9)
    check('periodic_two_separated_global_minima',len(main_stats['periodic_texture']['statistics']['global_minimum_intervals_at_numeric_tolerance']) >= 2)
    check('ramp_flat_across_depths',main_stats['linear_brightness_ramp']['statistics']['status']=='NUMERICALLY_FLAT')
    check('flat_texture_undefined',main_stats['flat_texture']['statistics']['status']=='UNDEFINED_PROFILE')
    for kind in ['textured_plane','periodic_texture','linear_brightness_ramp']:
        all_s = [s for s in summaries if s['fixture']==kind]
        if kind=='textured_plane':
            check('textured_depth_stable_across_grid_variants',all(abs(s['statistics']['argmin_depth_m']-10)<1e-9 for s in all_s))
        if kind=='periodic_texture':
            narrow = next(s for s in all_s if s['grid']=='narrow')
            check('narrow_range_can_hide_periodic_alternative',len(narrow['statistics']['global_minimum_intervals_at_numeric_tolerance']) < len(main_stats[kind]['statistics']['global_minimum_intervals_at_numeric_tolerance']))
    check('identical_input_hashes_before_after', before=={str(f):photo.sha(f) for f in dependencies})
    fig,axes = plt.subplots(4,2,figsize=(13,13),constrained_layout=True)
    for ax,kind in zip(axes.flat,old['fixture_names']):
        eta = arrays['eta_'+cfg['primary_grid']]
        d = 1/eta
        group = [r for r in rows if r['fixture']==kind and r['grid']==cfg['primary_grid']]
        for row in group:
            ax.plot(d,arrays[row['array_key']],alpha=.3,lw=.8)
        ax.plot(d,arrays[main_stats[kind]['array_key']],color='black',lw=1.8,label='Median (6 curves)')
        ax.axvline(10,color='tab:green',ls='--',label='Known synthetic depth 10 m')
        ax.axvline(20,color='tab:red',ls=':',label='Alternative 20 m')
        ax.set(xlabel='Candidate center camera Z (m)',ylabel='ZNCC cost (lower is better)',title=kind,
               ylim=(-.03,.8),xlim=(float(d.min()),float(d.max())))
        if not np.isfinite(arrays[main_stats[kind]['array_key']]).any():
            ax.text(.5,.5,'ZNCC undefined: no texture',ha='center',transform=ax.transAxes)
        ax.grid(alpha=.2)
        ax.legend(fontsize=7)
    axes.flat[-1].axis('off')
    axes.flat[-1].text(0,1,'Each thin line: one view / one patch size.\n\nLow cost is not a correctness certificate.\n\nFlat or repeated minima leave depth ambiguous.\n\nA narrow search may hide other minima.\n\nThese curves do not yet produce confidence\nor operational source weights.',va='top',fontsize=11)
    fig.suptitle('Synthetic depth-cost profiles v4.0 | no real GT, no training')
    fig.savefig(a.output/'depth_cost_profiles.png',dpi=140);plt.close(fig)
    np.savez_compressed(a.output/'profiles.npz',**arrays)
    photo.write(a.output/'results.json',{'scientific_verdict':None,'rows':rows,'summaries':summaries,'checks':checks})
    photo.write(a.output/'config.json',cfg)
    receipt={'task_id':cfg['task_id'],'scientific_verdict':None,
        'status':'PASS_MECHANISM_PROFILE_CHECKS' if all(c['passed'] for c in checks) else 'FAIL_MECHANISM_PROFILE_CHECKS',
        'commit':a.commit,'docker_image':cfg['docker_image'],'resources':cfg['resources'],
        'python':platform.python_version(),'numpy':np.__version__,'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds':time.time()-started,'real_gt_read':False,'training_executed':False,
        'check_count':len(checks),'failed_checks':[c for c in checks if not c['passed']],
        'inputs_sha256':before,'outputs_sha256':{f.name:photo.sha(f) for f in a.output.iterdir() if f.is_file()},
        'limitations':['synthetic profiles, not operational confidence or accuracy evaluation',
          'numerical tolerance is not an observation-noise calibration',
          'normal orientation from the same depth is not independent evidence',
          'cost profile minimum depends on search range, support and image formation']}
    photo.write(a.output/'receipt.json',receipt)
    print(json.dumps({k:receipt[k] for k in ['status','elapsed_seconds','check_count','failed_checks']}))
    return 0 if all(c['passed'] for c in checks) else 1


if __name__=='__main__':
    raise SystemExit(main())
