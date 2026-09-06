"""Additive native-lineage audit and decision evidence plots, no references."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from scripts.phd.p2_ab_v1.a_run import sha, write_json
from src.phd.p2_ab_v1.decision import common_curve, gaussian_uniform_posterior


def main(run, common, output):
    output.mkdir(parents=True, exist_ok=False)
    lineage = json.loads((run / 'PREMEASUREMENT.json').read_text())
    config = lineage['config']
    m = np.load(run / 'measurements.npz', allow_pickle=False)
    geo = np.load(run / 'candidates.npz', allow_pickle=False)
    original = np.load(common / 'units.npz', allow_pickle=False)
    candidates = json.loads((run / 'candidates.json').read_text())
    units = json.loads((run / 'selected_units.json').read_text())
    default_rows = [json.loads(line) for line in (run / 'handoff.jsonl').read_text().splitlines()]
    bysource = {s: {int(row): i for i, row in enumerate(original[f'{s}_tile_rows'])} for s in ('mvs', 'als')}
    native_verified, fusion_verified = 0, 0
    exclusions = []
    for c in candidates:
        ci = c['candidate_index']
        mask = geo['candidate_index'] == ci
        xyz = geo['xyz'][mask]
        assert len(xyz) == c['count'] == c['point_stop'] - c['point_start']
        assert np.array_equal(np.flatnonzero(mask), np.arange(c['point_start'], c['point_stop']))
        if c['source'] in ('IMAGE', 'PRIOR'):
            s = 'mvs' if c['source'] == 'IMAGE' else 'als'
            rows = np.array([bysource[s][int(r)] for r in geo[f'{s}_tile_rows'][mask]])
            assert np.array_equal(xyz, original[f'{s}_xyz'][rows])
            assert np.all(original[f'{s}_unit_index'][rows] == c['unit_index'])
            assert np.all(original[f'{s}_patch_id'][rows] == c['patch_id'])
            native_verified += 1
            total = int((original[f'{s}_unit_index'] == c['unit_index']).sum())
            exclusions.append(dict(unit_id=c['unit_id'], source=c['source'], selected_patch_id=c['patch_id'],
                all_native_points_in_unit=total, selected_patch_points_in_unit=c['native_patch_points_in_unit'],
                excluded_other_patch_points=total - c['native_patch_points_in_unit'], sampled_points=len(xyz)))
        else:
            mr = [bysource['mvs'][int(r)] for r in geo['mvs_tile_rows'][mask]]
            ar = [bysource['als'][int(r)] for r in geo['als_tile_rows'][mask]]
            mean = (original['mvs_xyz'][mr].astype(float) + original['als_xyz'][ar].astype(float)) / 2
            np.testing.assert_array_equal(xyz, mean)
            fusion_verified += 1
    for row in default_rows:
        if row['action'] == 'ABSTAIN':
            assert row['candidate_index'] is None
        else:
            c = candidates[row['candidate_index']]
            assert c['unit_id'] == row['unit_id'] and c['source'] == row['action']
            assert row['selected_offset_z_m'] == row['candidate_states'][row['action']]['offset_z_m']
        assert row['strict_current_use_action'] == 'ABSTAIN'
        if row['condition'] in ('MVS_REMOVED', 'MVS_MARKED_UNUSABLE'):
            assert row['action'] in ('PRIOR', 'ABSTAIN')
        if row['conditional_displacement_budget_m'] is not None:
            assert row['method'].startswith('DISCRETE_RANGE')
            np.testing.assert_allclose(row['conditional_displacement_budget_m'],
                row['tolerance_m'] - row['candidate_states'][row['action']]['range']['upper_m'])
    assert all(sha(path) == digest for path, digest in lineage['input_sha256'].items())
    posterior = np.full((len(candidates), 2, len(m['heights'])), np.nan)
    post_meta = []
    for c in candidates:
        ci = c['candidate_index']
        for mi, mode in enumerate(('all', 'disjoint')):
            curve, keep = common_curve(m['rho'][:, :, ci], m['pair_view_ids'],
                config['measurement']['min_common_pairs'], disjoint=mode == 'disjoint')
            if mode == 'disjoint':
                assert len(np.unique(m['pair_view_ids'][keep])) == 2 * len(keep)
            p = (gaussian_uniform_posterior(m['heights'], m['rho'][:, keep, ci], m['sigma_m'][ci, keep])
                 if len(keep) >= config['measurement']['min_common_pairs'] else None)
            if p is not None:
                posterior[ci, mi] = p.pop('height_mass')
            post_meta.append(dict(candidate_index=ci, pair_mode=mode, selected_pair_indices=keep.tolist(),
                                  selected_pair_view_ids=m['pair_view_ids'][keep].tolist(), posterior_summary=p))
    np.savez_compressed(output / 'bayes_native_posterior.npz', heights=m['heights'], height_mass=posterior,
                        modes=np.array(['all', 'disjoint']))
    write_json(output / 'bayes_native_output.json', post_meta)
    write_json(output / 'excluded_layers.json', exclusions)
    counts = defaultdict(dict)
    for row in default_rows:
        counts[row['condition']].setdefault(row['method'], Counter())[row['action']] += 1
    write_json(output / 'default_condition_counts.json', {c: {k: dict(v) for k,v in methods.items()} for c,methods in counts.items()})
    real = {(r['unit_id'], r['method']):r for r in default_rows if r['condition'] == 'REAL'}
    pair_methods = [('SCORE_GATE','DISCRETE_RANGE'), ('BAYES_GAUSS_UNIFORM','DISCRETE_RANGE'),
                    ('BAYES_GAUSS_UNIFORM','BAYES_GAUSS_UNIFORM_ALL_PAIRS')]
    transitions = {}
    representatives = []
    for a,b in pair_methods:
        table = Counter((real[u['unit_id'],a]['action'],real[u['unit_id'],b]['action']) for u in units)
        transitions[a+'__'+b] = [{'from':x,'to':y,'count':n} for (x,y),n in sorted(table.items())]
        for u in units:
            if real[u['unit_id'],a]['action'] != real[u['unit_id'],b]['action']:
                if u['unit_id'] not in representatives:
                    representatives.append(u['unit_id'])
                break
    for u in units:
        if real[u['unit_id'],'DISCRETE_RANGE']['action'] != 'ABSTAIN' and u['unit_id'] not in representatives:
            representatives.append(u['unit_id'])
    write_json(output / 'decision_transitions.json', transitions)
    fig, axes = plt.subplots(len(representatives), 2, figsize=(12, 3.2 * len(representatives)), squeeze=False)
    colors = {'IMAGE':'#2464ac', 'PRIOR':'#d27121', 'FUSION':'#27815b'}
    for ri, uid in enumerate(representatives):
        for c in (c for c in candidates if c['unit_id'] == uid):
            ci, s = c['candidate_index'], c['source']
            curve, _ = common_curve(m['rho'][:,:,ci],m['pair_view_ids'],config['measurement']['min_common_pairs'])
            axes[ri,0].plot(m['heights'],curve,label=s,color=colors[s], marker='.',markersize=3)
            if np.isfinite(posterior[ci,1]).any():
                axes[ri,1].plot(m['heights'],posterior[ci,1],label=s+' disjoint',color=colors[s])
            if np.isfinite(posterior[ci,0]).any():
                axes[ri,1].plot(m['heights'],posterior[ci,0],label=s+' all',color=colors[s],linestyle='--',alpha=.7)
        axes[ri,0].axhline(.3,color='black',linestyle=':',label='tau=.3')
        for ax in axes[ri]:
            ax.axvspan(-.5,.5,color='gray',alpha=.12)
            ax.axvline(0,color='gray',linewidth=.7)
            ax.set_xlabel('Scene-Z offset from each native candidate (m)')
            ax.grid(alpha=.15)
            ax.legend(fontsize=7)
        axes[ri,0].set_ylabel('Common-pair median ZNCC')
        axes[ri,1].set_ylabel('Conditional posterior mass')
        a = ', '.join(k+':'+real[uid,k]['action'] for k in ('SCORE_GATE','BAYES_GAUSS_UNIFORM','DISCRETE_RANGE'))
        axes[ri,0].set_title(uid+' | '+a,fontsize=8)
        axes[ri,1].set_title('Same measured curves; posterior assumptions differ',fontsize=9)
    fig.suptitle('P2 measured conditional decisions; absolute current-use certification unavailable',fontsize=11)
    fig.tight_layout()
    fig.savefig(output / 'representative_decision_curves.png',dpi=180)
    fig.savefig(output / 'representative_decision_curves.pdf')
    plt.close(fig)
    write_json(output / 'ANALYSIS_RECEIPT.json', dict(status='PASS', scientific_verdict=None,
        input_run=str(run), source=__file__, source_sha256=sha(__file__),
        native_candidates_exact_verified=native_verified, fusion_means_exact_verified=fusion_verified,
        handoff_rows_audited=len(default_rows), common_input_hashes_unchanged=True,
        representatives=representatives,
        representative_selection='first differing unit in frozen unit order for each prespecified method pair, then range-accepted units; no reference errors used',
        output_sha256={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()}))
    print(json.dumps(dict(status='PASS',native=native_verified,fusion=fusion_verified,representatives=representatives)),flush=True)


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--run',type=Path,required=True)
    ap.add_argument('--common',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    main(a.run,a.common,a.output)
