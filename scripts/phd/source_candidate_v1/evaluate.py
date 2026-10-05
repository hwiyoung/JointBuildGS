"""Evaluate sealed source decisions against UAS; never fit or change decisions.

Errors below are numerical discrepancies to the existing UAS reference frame,
not calibrated geometric accuracy. Native inlier point sets are scored directly;
no fitted-plane extrapolation, reference alignment, or threshold selection occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial import cKDTree

from scripts.phd.source_candidate_v1.common import sha, write, describe
from src.phd.source_candidate_v1.geometry import cell_membership

REFERENCE_SHAS = {
    'P1': '3d111cf0cd8ab39fccb85ce0075486ec40f4f60584b5c68b2ab122918b321543',
    'P2': '9dc75111e8a5e83808d566c0b6621092423898a1f6badb9438f1a0d75e16e7ba',
    'P3': 'a72041a28c8242d3901f5696d88e607473814299baab43103fda89fc179b1f81'}
DEFAULT_THRESHOLDS = [.1, .2, .5, 1., 2.]


def verify_method_seal(run):
    """Must complete before hashing, opening or loading any UAS reference."""
    run = Path(run)
    seal_path, config_path = run/'method_seal.json', run/'config.json'
    seal = json.loads(seal_path.read_text())
    if (seal.get('status') != 'METHOD_FROZEN_BEFORE_REFERENCE_ACCESS'
            or seal.get('scientific_verdict') is not None or seal.get('reference_accessed') is not False):
        raise ValueError('No complete reference-free method seal')
    if sha(config_path) != seal['config_sha256']:
        raise ValueError('Method configuration changed after seal')
    config = json.loads(config_path.read_text())
    if set(config['regions']) != set(REFERENCE_SHAS):
        raise ValueError('All P1/P2/P3 methods must be frozen before reference access')
    required = {'sensitivity.json'}
    for region in config['regions']:
        required.update(f'{region}/{name}' for name in (
            'candidates.json', 'membership.npz', 'observations.json', 'decisions.json',
            'input_summary.json', 'observation_summary.json', 'decision_summary.json', 'rgb_ledger.json'))
    if not required <= set(seal['files']):
        raise ValueError('Incomplete all-region method seal')
    for relative, expected in seal['files'].items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Invalid method seal path')
        actual = run/path
        if not actual.is_file() or sha(actual) != expected:
            raise ValueError('Sealed method bytes changed: ' + relative)
    return config, seal, sha(seal_path)


def points(value):
    result = np.asarray(value, dtype=np.float64).reshape(-1, 3)
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite geometric input')
    return result


def load_reference_npz(path):
    """Load the audited UAS export schema, after the caller verifies the seal.

    The first evaluation attempt exposed ``uas_xyz``/``uas_raw_rows`` in the
    immutable reference package. This adapter changes only the evaluation reader;
    candidate construction, observations and source decisions remain sealed.
    """
    with np.load(path, allow_pickle=False) as archive:
        if not {'uas_xyz', 'uas_raw_rows'} <= set(archive.files):
            raise ValueError('Reference requires exact uas_xyz and uas_raw_rows arrays')
        xyz, rows = archive['uas_xyz'], archive['uas_raw_rows']
        if (xyz.ndim != 2 or xyz.shape[1] != 3 or xyz.dtype != np.dtype('float64')
                or rows.shape != (len(xyz),) or rows.dtype != np.dtype('int64')
                or not np.isfinite(xyz).all()):
            raise ValueError('Reference UAS coordinates/raw-row lineage schema mismatch')
        return xyz


def geometric_discrepancy(prediction, reference, thresholds=DEFAULT_THRESHOLDS):
    """Equal directional mean of raw NN distances; retain missing cases."""
    prediction, reference = points(prediction), points(reference)
    result = dict(status='OK', prediction_count=len(prediction), reference_count=len(reference),
                  symmetric_mean_m=None, forward=describe([]), backward=describe([]), thresholds=[])
    if not len(reference):
        result['status'] = 'NOT_ASSESSED_REFERENCE_ABSENT'
        return result
    if not len(prediction):
        result['status'] = 'PREDICTION_ABSENT_WITH_REFERENCE'
        result['missing_reference_points'] = len(reference)
        result['thresholds'] = [dict(threshold_m=float(t), precision=None, recall=0., f1=0.,
                                     reference_missing_count=len(reference)) for t in thresholds]
        return result
    forward = cKDTree(reference).query(prediction, workers=1)[0]
    backward = cKDTree(prediction).query(reference, workers=1)[0]
    result.update(symmetric_mean_m=float((forward.mean()+backward.mean())/2),
                  forward=describe(forward), backward=describe(backward), missing_reference_points=0)
    for threshold in thresholds:
        precision, recall = float(np.mean(forward <= threshold)), float(np.mean(backward <= threshold))
        result['thresholds'].append(dict(threshold_m=float(threshold), precision=precision, recall=recall,
            f1=2*precision*recall/(precision+recall) if precision+recall else 0.,
            reference_missing_count=int((backward > threshold).sum())))
    return result


def assess_selection(mvs_error, als_error, action, deadband):
    """Reference-derived local oracle, computed only after immutable decisions."""
    finite = [v for v in (mvs_error, als_error) if v is not None and np.isfinite(v)]
    chosen = {'IMAGE': mvs_error, 'PRIOR': als_error}.get(action)
    paired = len(finite) == 2
    oracle = min(finite) if paired else None
    gap = abs(mvs_error-als_error) if paired else None
    correct = None
    status = 'UNASSESSED_OR_ABSTAIN'
    if chosen is not None and paired:
        if gap <= deadband:
            status = 'WITHIN_EVALUATION_DEADBAND'
        else:
            correct = bool(chosen == oracle)
            status = 'CORRECT_RELATIVE_TO_REFERENCE' if correct else 'INCORRECT_RELATIVE_TO_REFERENCE'
    return dict(selected_error_m=chosen, oracle_error_m=oracle,
                regret_m=chosen-oracle if chosen is not None and oracle is not None else None,
                source_gap_m=gap, selection_correct=correct, selection_evaluation_status=status)


def summarize_cells(rows):
    """All comparisons use the same row set and equal-cell weighting."""
    paired = [r for r in rows if r['both_valid'] and r['mvs_error_m'] is not None and r['als_error_m'] is not None]
    accepted = [r for r in rows if r['action'] in ('IMAGE', 'PRIOR')]
    common = [r for r in paired if r['action'] in ('IMAGE', 'PRIOR') and r['selected_error_m'] is not None]
    reference_supported = [r for r in rows if r['reference_count'] > 0]
    clear = [r for r in common if r['selection_correct'] is not None]
    def errors(subset, keys=('mvs_error_m', 'als_error_m', 'selected_error_m', 'oracle_error_m', 'regret_m')):
        return {key: describe([r[key] for r in subset if r[key] is not None]) for key in keys}
    return dict(total_cells=len(rows), reference_supported_cells=len(reference_supported), paired_cells=len(paired),
        accepted_cells=len(accepted), common_accepted_cells=len(common),
        abstain_cells=sum(r['action']=='ABSTAIN' for r in rows), action_counts=dict(Counter(r['action'] for r in rows)),
        accepted_fraction_all_cells=len(accepted)/len(rows) if rows else None,
        accepted_fraction_paired_cells=len(common)/len(paired) if paired else None,
        reference_supported_abstain_cells=sum(r['action']=='ABSTAIN' for r in reference_supported),
        native_point_counts={s:sum(r[s+'_native_count'] for r in rows) for s in ('mvs','als')},
        candidate_inlier_counts={s:sum(r[s+'_candidate_count'] for r in rows) for s in ('mvs','als')},
        reference_point_count=sum(r['reference_count'] for r in rows),
        equal_cell_discrepancy={'all_paired_same_cells':errors(paired, ('mvs_error_m','als_error_m','oracle_error_m')),
                               'accepted_same_cells':errors(common)},
        accepted_clear_gap_cells=len(clear), accepted_correct_clear_gap_cells=sum(r['selection_correct'] for r in clear),
        accepted_selection_accuracy_clear_gap=sum(r['selection_correct'] for r in clear)/len(clear) if clear else None,
        accepted_tie_deadband_cells=sum(r['selection_evaluation_status']=='WITHIN_EVALUATION_DEADBAND' for r in common),
        selection_vs_mvs_same_accepted_cells=describe([r['selected_error_m']-r['mvs_error_m'] for r in common]),
        selection_vs_als_same_accepted_cells=describe([r['selected_error_m']-r['als_error_m'] for r in common]),
        weighting='Equal cells for discrepancy means; native/reference point counts reported separately; no comparison of accepted subset against whole-region baseline.')


def grouped_indices(ids):
    order = np.argsort(ids, kind='stable')
    values, start = np.unique(ids[order], return_index=True)
    return {int(value): block for value, block in zip(values, np.split(order, start[1:]))}


def evaluate_region(region, native, membership, reference, candidates, decisions, domain, cell_m,
                    deadband=.1, thresholds=DEFAULT_THRESHOLDS):
    reference = points(reference)
    ref_ids, shape = cell_membership(reference, domain, cell_m)
    inside = ref_ids >= 0
    reference, ref_ids = reference[inside], ref_ids[inside]
    ref_groups = grouped_indices(ref_ids)
    decision_map = {row['cell_id']:row for row in decisions}
    if len(decision_map) != len(decisions) or set(decision_map) != {r['cell_id'] for r in candidates}:
        raise ValueError('Candidate/decision cell identity mismatch')
    xyz, groups, selected_masks = {}, {}, {}
    for source in ('mvs','als'):
        xyz[source] = points(native[source+'_xyz'])
        ids, inlier = membership[source+'_cell'], membership[source+'_inlier']
        if len(ids) != len(xyz[source]) or inlier.shape != ids.shape or inlier.dtype != bool:
            raise ValueError('Native candidate membership shape/dtype mismatch')
        expected, _ = cell_membership(xyz[source], domain, cell_m)
        if not np.array_equal(expected, ids):
            raise ValueError('Native point identity does not match frozen cell assignment')
        groups[source] = grouped_indices(ids)
        selected_masks[source] = np.zeros(len(ids), bool)
    rows=[]
    for candidate in candidates:
        cid=candidate['cell_id'];decision=decision_map[cid]
        if decision['action'] not in ('IMAGE','PRIOR','ABSTAIN'):
            raise ValueError('Unknown method action')
        ref=reference[ref_groups.get(cid,np.empty(0,int))]
        row=dict(region=region,cell_id=cid,action=decision['action'],reference_count=len(ref),
                 both_valid=bool(candidate['both_valid']), area_m2=candidate['area_m2'])
        for source in ('mvs','als'):
            indices=groups[source].get(cid,np.empty(0,int))
            keep=indices[membership[source+'_inlier'][indices]]
            metric=geometric_discrepancy(xyz[source][keep],ref,thresholds=thresholds)
            row.update({source+'_native_count':len(indices),source+'_candidate_count':len(keep),
                        source+'_valid':bool(candidate['candidates'][source]['valid']),
                        source+'_error_m':metric['symmetric_mean_m'],source+'_metrics':metric})
            row.update({source+'_'+direction+'_'+stat+'_m':metric[direction][stat]
                        for direction in ('forward','backward') for stat in ('mean','median','p95','rmse')})
            if decision['action']=={'mvs':'IMAGE','als':'PRIOR'}[source]:
                if not candidate['candidates'][source]['valid']:
                    raise ValueError('Sealed selection chose an invalid source candidate')
                selected_masks[source][keep]=True
        row.update(assess_selection(row['mvs_error_m'],row['als_error_m'],row['action'],deadband))
        rows.append(row)
    selected=np.concatenate([xyz[s][selected_masks[s]] for s in ('mvs','als')])
    whole={}
    for source in ('mvs','als'):
        whole[source+'_whole_native']=geometric_discrepancy(xyz[source],reference,thresholds)
        whole[source+'_all_inliers']=geometric_discrepancy(xyz[source][membership[source+'_inlier']],reference,thresholds)
    whole['selected_inlier_union']=geometric_discrepancy(selected,reference,thresholds)
    # Cells with no selected prediction are missing even if a neighbor's points
    # happen to lie near their UAS samples. NN recall is separately reported above.
    for threshold_row in whole['selected_inlier_union'].get('thresholds',[]):
        threshold_row['reference_points_in_abstain_cells']=sum(r['reference_count'] for r in rows if r['action']=='ABSTAIN')
    completeness=[]
    for index,threshold in enumerate(thresholds):
        missing=0
        for row in rows:
            source={'IMAGE':'mvs','PRIOR':'als'}.get(row['action'])
            if not row['reference_count']:
                continue
            missing += (row[source+'_metrics']['thresholds'][index]['reference_missing_count']
                        if source else row['reference_count'])
        completeness.append(dict(threshold_m=float(threshold),reference_count=len(reference),
            reference_missing_count=missing,recall=1-missing/len(reference) if len(reference) else None))
    whole['selected_full_target_cell_constrained_completeness']=dict(thresholds=completeness,
        interpretation='Every reference point in an abstained cell is missing; accepted cells use only the native selected candidate points belonging to that same fixed cell.')
    summary=summarize_cells(rows)
    summary.update(region=region,reference_points_outside_fixed_prism=int((~inside).sum()),
                   whole_native_point_weighted_diagnostics=whole)
    return rows,summary


def write_csv(path, rows):
    if not rows:
        Path(path).write_text('')
        return
    keys=list(dict.fromkeys(k for row in rows for k in row if not isinstance(row[k],(dict,list))))
    with Path(path).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k:row.get(k) for k in keys})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);parser.add_argument('--config',required=True)
    args=parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Evaluation requires Docker')
    started=time.monotonic();run=Path(args.run)
    eval_cfg=json.loads(Path(args.config).read_text())
    config,seal,seal_sha=verify_method_seal(run)  # No reference read is permitted above this line.
    deadband=float(eval_cfg.get('selection_deadband_m',.1))
    thresholds=eval_cfg.get('completeness_thresholds_m',DEFAULT_THRESHOLDS)
    if not np.isfinite(deadband) or deadband<0 or not all(np.isfinite(t) and t>0 for t in thresholds):
        raise ValueError('Invalid fixed evaluation thresholds')
    output=run/'evaluation'
    output.mkdir(exist_ok=False)
    all_rows=[];summaries={};inputs={}
    for region,spec in config['regions'].items():
        native_path=Path('/inputs')/region/'native.npz'
        if sha(native_path)!=spec['native_sha256']:
            raise ValueError('Native input changed: '+region)
        rspec=eval_cfg.get('references',{}).get(region,{})
        ref_path=Path(rspec.get('path',f'/reference/{region}/reference.npz'))
        expected=rspec.get('sha256',REFERENCE_SHAS[region])
        if expected!=REFERENCE_SHAS[region] or sha(ref_path)!=expected:
            raise ValueError('Frozen UAS reference identity changed: '+region)
        with np.load(native_path,allow_pickle=False) as archive:
            native={k:archive[k] for k in archive.files}
        reference=load_reference_npz(ref_path)
        with np.load(run/region/'membership.npz',allow_pickle=False) as archive:
            membership={k:archive[k] for k in archive.files}
        candidates=json.loads((run/region/'candidates.json').read_text())
        decisions=json.loads((run/region/'decisions.json').read_text())
        rows,summary=evaluate_region(region,native,membership,reference,candidates,decisions,spec['domain'],
                                     config['geometry']['cell_m'],deadband,thresholds)
        all_rows.extend(rows);summaries[region]=summary
        inputs[region]=dict(native_sha256=spec['native_sha256'],reference_sha256=expected,
                            reference_array='uas_xyz',reference_membership_array='uas_raw_rows',reference_path=str(ref_path))
        print(json.dumps(dict(stage='reference_evaluation',region=region,paired=summary['paired_cells'],
                              accepted=summary['accepted_cells'])),flush=True)
    sensitivity=json.loads((run/'sensitivity.json').read_text());risk=[]
    by_region={region:[r for r in all_rows if r['region']==region] for region in config['regions']}
    for settings in sensitivity:
        base=by_region[settings['region']]
        if len(settings['actions'])!=len(base):
            raise ValueError('Frozen sensitivity cell count mismatch')
        changed=[]
        for row,action in zip(base,settings['actions'],strict=True):
            if action not in ('IMAGE','PRIOR','ABSTAIN'):
                raise ValueError('Unknown sensitivity action')
            changed.append(dict(row,action=action,**assess_selection(row['mvs_error_m'],row['als_error_m'],action,deadband)))
        ss=summarize_cells(changed)
        risk.append(dict(region=settings['region'],max_cost=settings['max_cost'],margin=settings['margin'],
            min_support_fraction=settings['min_support_fraction'],coverage=ss['accepted_fraction_paired_cells'],
            accepted_cells=ss['accepted_cells'],common_accepted_cells=ss['common_accepted_cells'],
            risk_mean_m=ss['equal_cell_discrepancy']['accepted_same_cells']['selected_error_m']['mean'],
            regret_mean_m=ss['equal_cell_discrepancy']['accepted_same_cells']['regret_m']['mean'],
            same_accepted_mvs_mean_m=ss['equal_cell_discrepancy']['accepted_same_cells']['mvs_error_m']['mean'],
            same_accepted_als_mean_m=ss['equal_cell_discrepancy']['accepted_same_cells']['als_error_m']['mean'],
            accuracy_clear_gap=ss['accepted_selection_accuracy_clear_gap']))
    if sha(run/'method_seal.json')!=seal_sha:
        raise ValueError('Method seal changed during evaluation')
    summary=dict(status='COMPLETED_NONCONFIRMATORY_REFERENCE_DISCREPANCY',scientific_verdict=None,
        method_seal_sha256=seal_sha,method_config_sha256=seal['config_sha256'],evaluation_config=eval_cfg,
        evaluation_config_sha256=sha(args.config),input_hashes=inputs,regions=summaries,pooled=summarize_cells(all_rows),
        wall_seconds=time.monotonic()-started,limitations=[
            'UAS datum/registration and coverage uncertainty remain; distances are numerical discrepancies, not calibrated accuracy.',
            'Native point density and gaps affect nearest-neighbor distances; no reference surface fitting.',
            'Reference-absence cells are unassessed; abstention is missing selected geometry for full-target completeness.',
            'Both-source and accepted-subset comparisons use identical finite reference-supported cells and equal-cell weighting.',
            'P1/P2/P3 and shared observations are development evidence; no independent population inference.',
            'All sensitivity configurations were frozen before reference access; none is selected using UAS.'])
    write(output/'per_cell.json',all_rows);write(output/'summary.json',summary);write(output/'risk_coverage.json',risk)
    write_csv(output/'per_cell.csv',all_rows);write_csv(output/'risk_coverage.csv',risk)
    write(output/'evaluation_receipt.json',dict(scientific_verdict=None,method_seal_sha256=seal_sha,
        output_sha256={p.name:sha(p) for p in output.iterdir() if p.is_file()},reference_accessed_only_after_all_method_verification=True))


if __name__=='__main__':
    main()
