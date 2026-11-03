"""Independent retained-scope and evaluation-cell census; no score or threshold fitting."""
import json,ast,zipfile
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz
from prepare import array
BASE=O/'r2';INPUT=O/'r1'
def main():
    scope=json.loads((INPUT/'scope_audit.json').read_text());excluded={v for r in scope['rows'] for v in r['patch_ids']};excluded_photos={(r['tile'],r['prior'],r['kind'],r['point_id']) for r in scope['rows']};cfg=json.loads((C/'judgecheck_v1.json').read_text());allowed=set(cfg['scope']['development']);counts={};reference_counts={}
    assert len(excluded)==73
    for p in sorted((INPUT/'geometry').glob('*.npz')):
        d=loadz(p);e=loadz(BASE/'truth'/p.name);s=loadz(BASE/'sight'/p.name);tile,prior=p.stem.split('__');assert np.array_equal(d['patch_id'],e['patch_id']) and np.array_equal(d['patch_id'],s['patch_id']);assert not set(d['patch_id'])&excluded;assert set(d['building'])<=allowed
        gt=e['gt_p'];valid=(e['gt_status']==0)&np.isfinite(gt);hp=d['prior_height_m'];hm=d['mvs_mean_m'];tau=.1266 if prior=='ALS' else .2
        # Reconstruct each class from physical closeness booleans, independently
        # of the production cells() function and never fitting parameters.
        correct_p=np.less_equal(np.abs(hp-gt),tau);correct_m=np.less_equal(np.abs(hm-gt),tau);present=(d['n']>=4)&np.isfinite(hm)
        cell=np.full(len(gt),6,np.int8);normal_ok=np.isfinite(d['normal']).all(1);active=valid&np.isfinite(hp)&normal_ok
        for pc,mc,code in [(True,True,0),(False,True,1),(True,False,2),(False,False,3)]:cell[active&present&(correct_p==pc)&(correct_m==mc)]=code
        cell[active&~present&correct_p]=4;cell[active&~present&~correct_p]=5;cell[~np.isfinite(hp)|~normal_ok]=9;assert np.array_equal(cell,e['cell'])
        if prior=='LoD2':
            before=loadz(INPUT/'evaluation_inputs'/p.name);assert np.array_equal(before['gt_p'],gt,equal_nan=True) and np.array_equal(before['gt_status'],e['gt_status'])
        votes=s['votes'];through=(votes[:,0]>=2)&(2*votes[:,0]>votes[:,:3].sum(1));assert np.array_equal(s['free10'],through&(d['n']<4));assert not (s['sight_unavailable']&s['free10']).any()
        for kind in np.unique(d['kind']):
            key=f'{prior}_{kind}';m=d['kind']==kind;counts[key]=counts.get(key,0)+int(m.sum());reference_counts[key]=reference_counts.get(key,0)+int((m&valid).sum())
    assert counts=={'ALS_1':501840,'LoD2_1':644427,'LoD2_2':1485308},counts
    group_targets={};duplicate_photo_strings=0
    for p in sorted((BASE/'photo_targets').glob('*.npz')):
        tile,prior,kind=p.stem.split('__');kind=int(kind);g=loadz(p);old=loadz(INPUT/'photo_targets'/p.name);assert np.array_equal(g['point_id'],old['point_id']);assert np.array_equal(g['target_type1'],old['target_type']==1) and np.array_equal(g['target_type2'],old['target_type']==2)
        assert not g['holdout'].any()
        if 'building_ids' in g:assert all(set(str(b).split(';'))<=allowed for b in g['building_ids'])
        else:
            src=cfg['sources'];root=Path(src['wall_photo'] if kind==2 else src['roof_photo']);wf=Path(src['widen'])/'patch_values'/f'{tile}__{prior}__R1.5.npz'
            with zipfile.ZipFile(wf) as z:identity=dict(zip(array(z,'patch_id'),array(z,'building')))
            with zipfile.ZipFile(root/'geometry'/f'{tile}__{prior}__mapping.npz') as z:ids=array(z,'patch_id');owners=array(z,'point_index')
            if not set(ids)<=set(identity):
                with zipfile.ZipFile(Path(src['widen'])/'holdout/patch_values'/wf.name) as z:identity.update(zip(array(z,'patch_id'),array(z,'building')))
            selected_ids=set(g['geometry_index']);assert all(identity[pid] in allowed for pid,owner in zip(ids,owners) if owner in selected_ids)
        assert not any((tile,prior,kind,pid) in excluded_photos for pid in g['point_id'])
        assert np.array_equal(g['curve'],old['curve'],equal_nan=True);key=f'{prior}_{kind}';group_targets[key]=group_targets.get(key,0)+int((g['target_type']>0).sum())
    assert group_targets==json.loads((BASE/'target_census.json').read_text())['group_targets']
    for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text())
    result=dict(at=now(),status='PASS_REPLY2_RETAINED_SCOPE_AND_CELLS',core_counts=counts,reference_available_counts=reference_counts,target_counts=group_targets,
        excluded_shared_count=73,excluded_shared_area_m2=5.442552935831812,calibration_sample_membership_unchanged=True,old_curves_unchanged=True,
        cells_recomputed_independently=True,sight_free_rule_recomputed=True,holdout_values_opened=False,initial_preparation_used=False,scientific_verdict=None)
    dump(BASE/'audit_inputs.json',result);dump(D/'tables/reply2_input_audit.json',result);print(result['status'],counts,group_targets,flush=True)
if __name__=='__main__':main()
