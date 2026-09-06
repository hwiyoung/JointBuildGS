"""Join frozen P2 judgment and reconstruction outputs to evaluation-only UAS."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np
from src.phd.p2_ab_v1.evaluation import geometry_metrics, decision_accounting

REPO = Path(__file__).resolve().parents[3]


def read(p):
    return json.loads(Path(p).read_text())


def write(p, value):
    Path(p).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def csv_write(p, rows):
    if not rows:
        Path(p).write_text('status\nNO_ROWS\n')
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open('w') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def display_block(xyz, units, cap_per_unit=128):
    xyz, units = np.asarray(xyz), np.asarray(units)
    selected = []
    for u in np.unique(units):
        ids = np.flatnonzero(units == u)
        selected.extend(ids[np.linspace(0, len(ids)-1, min(len(ids), cap_per_unit), dtype=int)])
    ids = np.asarray(selected, dtype=int)
    return dict(xyz=np.round(xyz[ids], 4).reshape(-1).tolist(), unit_index=units[ids].astype(int).tolist(),
                full_point_count=len(xyz), display_point_count=len(ids))


def main(args):
    start = time.monotonic()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    cfg = read(args.config)
    write(out/'STARTED.json', dict(task_id=cfg['task_id'], scientific_verdict=None))
    common, a = args.common, args.a_root
    units = read(common/'units.json')['units']
    source = np.load(common/'units.npz', allow_pickle=False)
    ref = np.load(args.reference/'evaluation_reference.npz', allow_pickle=False)
    ref_manifest = read(args.reference/'reference_manifest.json')
    ref_xyz, ref_units = ref['uas_xyz'], ref['uas_unit_index']
    candidates = read(a/'candidates.json')
    cp = np.load(a/'candidates.npz', allow_pickle=False)
    candidate_xyz = cp['xyz']
    payload_group = cp['candidate_index']
    inputs = [args.config, common/'sample_manifest.json', common/'units.npz', common/'units.json',
              a/'candidates.npz', a/'candidates.json', a/'decision_rows.jsonl', a/'handoff.jsonl',
              args.reference/'evaluation_reference.npz', args.reference/'reference_manifest.json']
    input_hashes = {str(p):sha(p) for p in inputs}
    r_by_u = {u['unit_index']: ref_xyz[ref_units == u['unit_index']] for u in units}
    neighboring = {}
    for u in units:
        neighboring[u['unit_index']] = [v['unit_index'] for v in units
            if abs(v['grid_ix']-u['grid_ix']) <= 1 and abs(v['grid_iy']-u['grid_iy']) <= 1]
    reference_cache = {}

    def reference_for(ui):
        if ui not in reference_cache:
            reference_cache[ui] = np.concatenate([r_by_u[v] for v in neighboring[ui]])
        return r_by_u[ui], reference_cache[ui]

    evaluated = {}
    def evaluate_candidate(ci, offset):
        key = (int(ci), float(offset))
        if key not in evaluated:
            candidate = candidates[ci]
            xyz = candidate_xyz[payload_group == ci].copy()
            xyz[:,2] += offset
            r, rf = reference_for(candidate['unit_index'])
            m, _ = geometry_metrics(xyz, r, cfg['tolerances_m'], cfg['reference_xy_radius_m'], rf)
            # No unmeasured reference precision or surface authority is fabricated.
            m.update(candidate_index=int(ci), source=candidate['source'], unit_id=candidate['unit_id'],
                     unit_index=candidate['unit_index'], offset_z_m=float(offset),
                     coordinate_assumption='legacy numeric local-frame bridge; datum/epoch uncertainty uncalibrated',
                     conditional_reference_label=True)
            evaluated[key] = m
        return evaluated[key]

    grouped = defaultdict(list)
    default_rows = []
    all_count = 0
    with (out/'joined_decision_units.jsonl').open('w') as joined:
        with (a/'decision_rows.jsonl').open() as rows:
            for line in rows:
                row = json.loads(line)
                all_count += 1
                labels, errors = {}, {}
                for action, state in row['candidate_states'].items():
                    ci = int(state['candidate_index'])
                    offset = float(state.get('offset_z_m', state.get('candidate_offset_z_m', 0)))
                    if row['condition'] != 'REAL' and 'offset_z_m' not in state and 'candidate_offset_z_m' not in state:
                        raise ValueError('Controlled candidate must publish explicit offset_z_m')
                    m = evaluate_candidate(ci, offset)
                    supported = m['xy_supported_count'] == m['prediction_count'] and m['prediction_count'] > 0
                    error = m['prediction_to_reference']['p90_m']
                    labels[action] = bool(error <= row['tolerance_m']) if supported and error is not None else None
                    errors[action] = dict(candidate_index=ci, offset_z_m=offset, p90_m=error,
                        xy_nearest_abs_dz_p90_m=m['xy_nearest_abs_dz']['p90_m'],
                        finite_height_range=state.get('range'),posterior=state.get('posterior'),
                        common_pair_count=state.get('common_pair_count'),
                        component_warning='Height-set bound and nearest3d error differ; nearestXY height is correspondence-conditional, not bound calibration',
                        reference_supported=supported, conditional_candidate_ok=labels[action])
                key = (row['condition'], row['threshold'], row['tolerance_m'], row['method'])
                grouped[key].append(dict(action=row['action'], candidate_ok=labels))
                record = {k:row[k] for k in ['unit_id','unit_index','condition','method','threshold','tolerance_m',
                                             'action','strict_current_use_action','conditional_displacement_budget_m']}
                record.update(candidate_evaluation=errors, reference_label_scope='conditional numeric-frame point-set diagnostic',
                              scientific_verdict=None)
                joined.write(json.dumps(record, allow_nan=False)+'\n')
                if row['condition']=='REAL' and row['threshold']==.3 and row['tolerance_m']==.5:
                    default_rows.append(dict(row, candidate_evaluation=errors))
    risk=[]
    for (condition,threshold,tolerance,method),rows in grouped.items():
        risk.append(dict(condition=condition,threshold=threshold,tolerance_m=tolerance,method=method,
                         **decision_accounting(rows),reference_frame_status='CONDITIONAL_LEGACY_NUMERIC_BRIDGE'))
    csv_write(out/'decision_risk_coverage.csv', risk)
    write(out/'decision_risk_coverage.json', risk)
    write(out/'candidate_metrics.json', list(evaluated.values()))
    write(out/'default_real_decisions.json', default_rows)
    print(json.dumps({'candidate_evaluations':len(evaluated),'decision_rows':all_count,'risk_rows':len(risk)}),flush=True)

    inspection = dict(units=[{k:u[k] for k in ['unit_id','unit_index','bbox_xy','pilot_selected']} for u in units],
        centre=[134.,109.,-33.5], scientific_verdict=None,
        display_note='Deterministic native-row display thinning only; numeric evaluation uses full declared input support.',
        sources={k:display_block(source[k+'_xyz'],source[k+'_unit_index']) for k in ['mvs','als']},arms=[])
    inspection['sources']['uas']=display_block(ref_xyz,ref_units)
    # The same fixed point representation across A methods isolates decision changes.
    for method in sorted({r['method'] for r in default_rows}):
        rows=[r for r in default_rows if r['method']==method]
        xyz, uids=[],[]
        for row in rows:
            if row['candidate_index'] is None:
                continue
            p=candidate_xyz[payload_group==row['candidate_index']].copy()
            p[:,2]+=float(row['selected_offset_z_m'] or 0)
            xyz.append(p);uids.extend([row['unit_index']]*len(p))
        p=np.concatenate(xyz) if xyz else np.empty((0,3))
        inspection['arms'].append(dict(key='A/'+method,label='A · '+method+' · 고정 후보',
            comparison='Same fixed point representation; no surface-area approval or GS training in this arm',
            initial=display_block(p,np.asarray(uids,dtype=int)),final=display_block(p,np.asarray(uids,dtype=int)),
            decisions=[{k:r[k] for k in ['unit_id','unit_index','action','strict_current_use_action','candidate_evaluation']} for r in rows],
            metrics=next(v for v in risk if v['condition']=='REAL' and v['method']==method and v['threshold']==.3 and v['tolerance_m']==.5),images=[]))

    b_metrics=[]
    viewer=out/'viewer';viewer.mkdir()
    image_dir=viewer/'images';image_dir.mkdir()
    pilot=read(common/'units.json')['pilot_unit_indices']
    for b in args.b_root:
        result=read(b/'result.json');inputs.append(b/'result.json')
        input_hashes[str(b/'result.json')]=sha(b/'result.json')
        if result['status']=='ABSTAIN_NO_GEOMETRY':
            abstain_handoff=read(b/'handoff_receipt.json')
            missing=[]
            for ui in pilot:
                r,rf=reference_for(ui)
                m,_=geometry_metrics(np.empty((0,3)),r,cfg['tolerances_m'],cfg['reference_xy_radius_m'],rf)
                m.update(unit_index=ui,unit_id=units[ui]['unit_id'])
                missing.append(m)
            b_metrics.append(dict(run=b.name,status=result['status'],units=missing,
                decision_method=abstain_handoff['method'],condition=abstain_handoff['condition'],
                arm='no_geometry',scientific_verdict=None))
            inspection['arms'].append(dict(key=b.name,label='B · '+b.name+' · 전체 유보',
                comparison='No accepted geometry; all fixed reference units remain in completeness denominator',
                initial=None,final=None,metrics=dict(status=result['status'],reference_units=len(pilot)),
                decisions=result.get('units'),images=[]))
            continue
        for arm in result.get('arms',[]):
            folder=b/arm['arm']
            pp=np.load(folder/'extracted_surface.npz',allow_pickle=False)
            ix=pp['unit_index']
            initial_path=folder/'initial_extracted_surface.npz'
            initial=np.load(initial_path,allow_pickle=False) if initial_path.exists() else None
            per_unit=[]
            for ui in pilot:
                r,rf=reference_for(ui)
                m,_=geometry_metrics(pp['xyz'][ix==ui],r,cfg['tolerances_m'],cfg['reference_xy_radius_m'],rf)
                m.update(unit_index=ui,unit_id=units[ui]['unit_id'])
                if initial is not None:
                    im,_=geometry_metrics(initial['xyz'][initial['unit_index']==ui],r,cfg['tolerances_m'],cfg['reference_xy_radius_m'],rf)
                    m['initial_metrics']=im
                    aerr=im['prediction_to_reference']['p90_m'];berr=m['prediction_to_reference']['p90_m']
                    m['final_minus_initial_p90_m']=berr-aerr if aerr is not None and berr is not None else None
                    m['final_minus_initial_reference_recall']=[dict(tolerance_m=f['tolerance_m'],
                        change=f['reference_recall']-j['reference_recall'] if f['reference_recall'] is not None and j['reference_recall'] is not None else None)
                        for f,j in zip(m['tolerance_sweep'],im['tolerance_sweep'])]
                    m['final_minus_initial_point_count']=m['prediction_count']-im['prediction_count']
                per_unit.append(m)
            source_receipt=read(b/'handoff_receipt.json')
            summary=dict(run=b.name,arm=arm['arm'],decision_method=arm['decision_method'],
                condition=arm['condition'],status=result['status'],units=per_unit,
                appearance=arm.get('appearance'),runtime_seconds=arm.get('runtime_seconds'),
                source_contract=source_receipt,scientific_verdict=None)
            b_metrics.append(summary)
            imlist=[]
            for p in sorted(folder.glob('target_*.png')):
                iid=int(p.stem.split('_')[-1]); record=dict(image_id=iid)
                for prefix,key in [('target','target'),('initial_rgb','initial'),('rgb','final'),('alpha','alpha')]:
                    source_path=folder/f'{prefix}_{iid}.png'
                    if source_path.exists():
                        dest=image_dir/f'{b.name}_{arm["arm"]}_{source_path.name}'
                        shutil.copyfile(source_path,dest);record[key]='images/'+dest.name
                imlist.append(record)
            display=dict(key=b.name+'/'+arm['arm'],label='B · '+arm['decision_method']+' · '+arm['arm'],
                comparison='Same measured conditional A handoff across these B arms',
                initial=display_block(initial['xyz'],initial['unit_index']) if initial is not None else None,
                final=display_block(pp['xyz'],ix),metrics={k:v for k,v in arm.items() if k not in ['history','evaluation_surface_guard']},
                decisions=source_receipt.get('units'),images=imlist)
            inspection['arms'].append(display)
            input_hashes[str(folder/'extracted_surface.npz')]=sha(folder/'extracted_surface.npz')
    write(out/'reconstruction_unit_metrics.json',b_metrics)
    write(viewer/'inspection.json',inspection)
    for name in ['index.html','app.js']:
        shutil.copyfile(REPO/'src/apps/p2_ab_inspector_v1'/name,viewer/name)
    shutil.copyfile(REPO/'src/apps/gs3d_4way_viewer/build/three.module.min.js',viewer/'three.module.min.js')
    snapshots=[Path(__file__),REPO/'src/phd/p2_ab_v1/evaluation.py',args.config,
               REPO/'src/apps/p2_ab_inspector_v1/index.html',REPO/'src/apps/p2_ab_inspector_v1/app.js']
    for p in snapshots:
        dest=out/'source_snapshot'/p.relative_to(REPO);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    if not all(sha(p)==h for p,h in input_hashes.items()):
        raise RuntimeError('Evaluation input changed during run')
    write(out/'technical_receipt.json',dict(task_id=cfg['task_id'],status='CONDITIONAL_DEVELOPMENT_EVALUATED',
        common_root=str(common),a_root=str(a),reference_root=str(args.reference),b_roots=list(map(str,args.b_root)),
        input_sha256=input_hashes,source_sha256={str(p.relative_to(REPO)):sha(p) for p in snapshots},
        elapsed_seconds=time.monotonic()-start,decision_rows=all_count,risk_settings=len(risk),
        candidate_evaluations=len(evaluated),b_arm_results=len(b_metrics),reference_metadata=ref_manifest,
        scientific_verdict=None,limitations=['Uncalibrated camera/registration/occlusion/continuous domain',
        'UAS native point accuracy and datum/epoch relation uncalibrated; numeric-frame diagnostic only',
        'All image roles historically used development views; exact937 camera/MVS dependencies shared',
        'Point/ray-sampled metrics are not certified surface area or building-level usability']))
    print(json.dumps({'status':'CONDITIONAL_DEVELOPMENT_EVALUATED','output':str(out),'b_arms':len(b_metrics)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--common',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--a-root',type=Path,required=True);p.add_argument('--b-root',type=Path,action='append',default=[])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,default=REPO/'configs/phd/p2_ab_v1/c_evaluation_v1.json')
    main(p.parse_args())
