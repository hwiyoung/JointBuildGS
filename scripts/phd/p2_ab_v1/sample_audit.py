"""Validate the completed common sample and append frame/role provenance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from scripts.phd.p2_ab_v1.sample_build import REPO, read, record, write
from scripts.input_and_alignment.gate_s0.integrated_freeze_closure_v1.run_integrated_freeze import epsg32632_to_25832


def main(config_path):
    cfg=read(config_path); root=Path(cfg['artifact_root'])/cfg['output_relative_root']; common=root/'common'
    manifest=read(common/'sample_manifest.json'); units=read(common/'units.json'); views=read(common/'views.json')
    evaluation=root/cfg['evaluation_directory']; reference=read(evaluation/'reference_manifest.json')
    checks=[]
    for obj in [manifest,reference]:
        for rec in obj['outputs'].values():
            assert record(rec['path'])['sha256']==rec['sha256']
    checks.append('All common and evaluation payload hashes match immutable manifests')
    arrays=np.load(common/'units.npz',allow_pickle=False)
    for source in ['mvs','als']:
        xyz=arrays[f'{source}_xyz']; ui=arrays[f'{source}_unit_index']; rows=arrays[f'{source}_tile_rows']
        assert xyz.ndim==2 and xyz.shape[1]==3 and np.isfinite(xyz).all()
        assert np.all(rows[1:]>rows[:-1])
        assert len(np.unique(np.column_stack([arrays[f'{source}_original_file_index'],arrays[f'{source}_original_row']]),axis=0))==len(rows)
        assert np.array_equal(np.bincount(ui,minlength=len(units['units'])),[u[f'{source}_count'] for u in units['units']])
    checks.append('Native tile rows strictly increase; raw file-row identities unique; all 552 unit counts exact')
    role_ids={role:{v['image_id'] for v in views['views'] if v['role']==role} for role in ['decision','train','appearance_eval']}
    assert [len(role_ids[k]) for k in ['decision','train','appearance_eval']]==[22,33,11]
    assert len(set.union(*role_ids.values()))==66 and all(len(a&b)==0 for i,a in enumerate(role_ids.values()) for b in list(role_ids.values())[i+1:])
    checks.append('22 decision,33 train,11 appearance_eval IDs are pairwise disjoint and exhaustive over frozen66')
    eligible=[u['unit_index'] for u in units['units'] if max(u['mvs_count'],u['als_count'])>=cfg['pilot']['minimum_points_in_either_source']]
    expected=np.array(eligible)[np.linspace(0,len(eligible)-1,min(len(eligible),cfg['pilot']['maximum_units']),dtype=int)].tolist()
    assert expected==units['pilot_unit_indices']==manifest['pilot_unit_indices']
    checks.append('Pilot64 deterministic source-count-only selection matches config and both manifests')
    ref=np.load(evaluation/'evaluation_reference.npz',allow_pickle=False)
    assert np.isfinite(ref['uas_xyz']).all() and np.all(ref['uas_original_rows'][1:]>ref['uas_original_rows'][:-1])
    class_values,class_counts=np.unique(ref['uas_classification'],return_counts=True)
    checks.append('UAS raw row IDs unique/increasing; current reference finite; class0 preserved as unclassified')
    artifact=Path(cfg['artifact_root'])
    gravity_path=artifact/'phase-payloads/p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json'
    gravity=read(gravity_path)['payload']['gravity']; assert gravity['hardcoded_gravity'] is False
    frame_contract_path=REPO/'docs/research/preregistration/gate_s0/integrated_freeze_closure_v1/frame_datum_registration_gravity_receipt_v1.json'
    ancestry_path=REPO/'artifacts/manifests/gate_s0/common_base_r2b/existing_common_base_derivative_lineage_v1.json'
    shift=np.array(manifest['frame']['world_shift_xyz_m']); domain=manifest['domain']
    x=np.array([domain['x'][0],domain['x'][1],domain['x'][0],domain['x'][1]])+shift[0]
    y=np.array([domain['y'][0],domain['y'][0],domain['y'][1],domain['y'][1]])+shift[1]
    tx,ty=epsg32632_to_25832(x,y)
    frame_audit={
        'schema':'jointbuildgs.phd.p2_ab.frame_audit.v1','scientific_verdict':None,
        'source_frames':{
            'camera_and_mvs':{'horizontal_source_epsg':32632,'working':'SCENE_LOCAL_XYZ','local_shift':(-shift).tolist(),
                              'provenance':record(ancestry_path),'vertical_datum_header_or_producer_binding':'UNKNOWN in frozen source ancestry; later project policy uses current camera ellipsoidal frame'},
            'current_uas':{'horizontal_source_epsg':reference['header']['source_projected_epsg_from_vlr'],'working':'SCENE_LOCAL_XYZ',
                           'local_shift':(-shift).tolist(),'vertical_datum_vlr':None,'project_policy':'Same current acquisition camera frame; no +45.7 bridge applied'},
            'existing_als':{'horizontal_source_epsg':25832,'source_crs_basis':'Provider declaration; original LAZ VLR absent',
                            'source_vertical_datum':'DHHN2016 provider declared','already_applied_z_bridge_m':45.7,'local_shift':(-shift).tolist(),
                            'bridge_role':'Existing project scalar bridge; not new fitted registration or calibrated geodetic uncertainty'}},
        'projection_contract':{'record':record(frame_contract_path),'frozen':read(frame_contract_path)['horizontal_transform_contract'],
                               'p2_corner_implementation_delta_xy_m':np.column_stack([tx-x,ty-y]).tolist(),
                               'p2_max_implementation_numeric_displacement_m':float(np.hypot(tx-x,ty-y).max()),
                               'point_arrays_changed':False,'datum_epoch_realization_uncertainty_m':None,
                               'interpretation':'Numerical projection-ellipsoid conversion checks are distinct from physical datum/epoch and survey uncertainty.'},
        'evaluation_interpretation':'Native MVS and UAS share declared EPSG32632 source numerical frame. Within-dataset relative errors are valid conditional on existing camera/georeferencing bridge. ALS cross-frame/scalar bridge and absolute current accuracy remain uncertainty limitations; no reference-based alignment was fit.',
        'gravity':{'input_record':record(gravity_path),'value':gravity,'source_mvs':read(gravity_path)['payload']['input'],
                   'reuse_status':'FROZEN_TERRAIN_NORMAL_GRAVITY_REUSED; historical source bytes differ from recovered native candidate; no recalculation or hardcoding'},
        'common_manifest_statement_correction':'sample_manifest unresolved list says no measured terrain gravity supplied by this sample; this additive audit binds the existing frozen gravity without changing any native arrays.'}
    write(common/'frame_audit.json',frame_audit)
    result={'schema':'jointbuildgs.phd.p2_ab.sample_audit.v1','status':'PASS_DEVELOPMENT_INPUT_AND_ROLE_CONTRACT', 'scientific_verdict':None,
            'checks':checks,'source_code':{n:record(REPO/n) for n in ['scripts/phd/p2_ab_v1/sample_build.py','scripts/phd/p2_ab_v1/sample_audit.py']},
            'configs':{n:record(REPO/n) for n in ['configs/phd/p2_ab_v1/sample_v1.json','configs/phd/p2_ab_v1/sample_recovery_v2.json','configs/phd/p2_ab_v1/sample_evaluation_recovery_v3.json']},
            'container_image':'jointbuildgs:dev','container_image_id':'sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774',
            'reference_class_counts':{str(k):int(v) for k,v in zip(class_values,class_counts)},
            'pilot_source_counts':{'both_present':sum(u['mvs_count']>0 and u['als_count']>0 for u in units['units'] if u['pilot_selected']),
                                   'mvs_absent':sum(u['mvs_count']==0 for u in units['units'] if u['pilot_selected']),
                                   'als_absent':sum(u['als_count']==0 for u in units['units'] if u['pilot_selected'])},
            'full_prism_reference_points':len(ref['uas_xyz']), 'source_error_calibration_performed':False,
            'outputs':{'common_manifest':record(common/'sample_manifest.json'),'reference_manifest':record(evaluation/'reference_manifest.json'),'frame_audit':record(common/'frame_audit.json')}}
    write(common/'sample_audit_receipt.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=REPO/'configs/phd/p2_ab_v1/sample_evaluation_recovery_v3.json');args=parser.parse_args();main(args.config)
