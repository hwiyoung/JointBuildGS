"""Meaningful pre-GPU gates: frozen splits, exact camera lineage, evaluation exclusion."""
import ast
import datetime as dt
import json
from pathlib import Path
import numpy as np
from preflight import images,sha,dump,DENSE
O,D,R=Path('/out'),Path('/docs'),Path('/repo')

def main():
    cfg=json.loads(Path('/cfg/widen0_v2.json').read_text());lock=json.loads(Path('/cfg/widen0_v2.lock.json').read_text())
    assert sha('/cfg/widen0_v2.json')==lock['config_sha256']
    for p in (R/'scripts/phd/main_widen0_v2').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
    sp=json.loads((O/'building_split.json').read_text());sl=json.loads((O/'building_split.lock.json').read_text())
    assert sha(O/'building_split.json')==sl['split_sha256']
    expected=sorted(np.random.default_rng(20261023).choice(sp['other_sorted'],int(.3*len(sp['other_sorted'])),replace=False).tolist())
    assert expected==sp['holdout'];assert not set(sp['development'])&set(sp['holdout'])
    assert set(sp['forced_development'])<=set(sp['development'])
    isp=json.loads((O/'image_split.json').read_text());il=json.loads((O/'image_split.lock.json').read_text())
    assert sha(O/'image_split.json')==il['image_split_sha256']
    assert isp['evaluation']==isp['candidates'][::8]
    assert not set(isp['train'])&set(isp['evaluation'])
    model=images(O/'mvs/full/sparse/images.bin');original=images(DENSE/'sparse/images.bin')
    assert sorted(model)==sorted(isp['train'])
    for name,rec in model.items():
        assert rec['q']==original[name]['q'] and rec['t']==original[name]['t']
    assert sha(O/'mvs/full/sparse/cameras.bin')==sha(DENSE/'sparse/cameras.bin')
    assert cfg['tau_m']==dict(ALS=.1266,LoD2=.2)
    est=json.loads((D/'tables/image_inventory.json').read_text())['mvs_estimate']
    assert est['single_gpu_hours']<=48
    assert (D/'중간보고_v1.md').is_file()
    assert not cfg['execution']['training'] and not cfg['ground_truth']['manual_uls']
    result=dict(status='PASS',made=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        checks=['script_syntax','config_lock','building_split_lock','deterministic_building_split','disjoint_buildings',
                'forced_development','image_split_lock','audit_image_split','evaluation_excluded_from_mvs_model',
                'exact_pose_and_camera_lineage','tau_user_decision','single_gpu_under_48_hours','intermediate_exists','no_training_no_manual_uls'],
        config_sha256=sha('/cfg/widen0_v2.json'),image_split_sha256=sha(O/'image_split.json'),
        building_split_sha256=sha(O/'building_split.json'),scientific_verdict=None)
    dump(O/'gates/input_pass.json',result);dump(D/'tables/input_validation.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
