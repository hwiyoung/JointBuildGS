"""Seal identity metadata and lock documented unavailable handling before calibration."""
import json
from pathlib import Path
import shutil
from lock_config import dump,sha,stamp
C=Path('/cfg');O=Path('/out');S=Path(__file__).parent;D=Path('/docs')

def main():
    assert (O/'census_complete.json').exists()
    cfg=json.loads((C/'judgenum_v1.json').read_text())
    assert isinstance(cfg['scope']['holdout'],list),'Already sealed'
    private=O/'holdout/private_config_history';private.mkdir(exist_ok=True,parents=True)
    held=cfg['scope']['holdout'];membership=O/'holdout/scope_membership.json'
    dump(membership,{'buildings':held,'scientific_verdict':None})
    before=sha(C/'judgenum_v1.json')
    for name in ['judgenum_v1.r0.json','judgenum_v1.r0.lock.json']:
        shutil.move(str(C/name),str(private/name))
    shutil.copyfile(C/'judgenum_v1.json',private/'judgenum_v1.r1.json')
    shutil.copyfile(C/'judgenum_v1.lock.json',private/'judgenum_v1.r1.lock.json')
    shutil.copyfile(C/'scope_geometry.json',private/'scope_geometry.r1.json')
    geo=json.loads((C/'scope_geometry.json').read_text())
    for ft in geo['features']:
        if ft['properties']['split']=='holdout':ft['properties']={'split':'holdout'}
    dump(C/'scope_geometry.json',geo)
    cfg['scope']['holdout']={'building_count':len(held),'membership_path':'/out/holdout/scope_membership.json',
      'sha256':sha(membership)}
    cfg['scope']['geometry_sha256']=sha(C/'scope_geometry.json')
    cfg['availability']={'judgment_unavailable_code':-1,'never_inherit_for_undefined_axis':True,
      'missing_prior_sigma':'DL unavailable when n>=4; no sigma substitution',
      'ALS_normal_scale':'Source TIN triangle normal, not fitted-neighbourhood normal; neighbourhood size and residual standard deviation unavailable, check code -1',
      'null_component_strata':'Compute A separately from roof-only and wall-only cell0 core sets, per section 3.3; preserve full building/prior/judgment components for smoothing',
      'mixed_kind_component':'Use full component area. If all present kinds agree that it is small, apply the common boundary rule; if all agree large, retain it; if thresholds disagree, postprocessing is unavailable and no initial choice is fabricated',
      'half_spacing':'Exact inherited photo point_id groups, lexicographically first eligible patch; representative gets the sum of member areas; values are those of the retained patch'}
    cfg['execution']['cpu_census_workers']=4;cfg['execution']['shared_container_memory_gib']=32
    cfg['amendments'].append({'at':stamp(),'previous_config_sha256':before,
      'reason':'Seal holdout identity metadata and previous full configs outside public bundle; document unavailable handling before calibration. Original order and prior config hashes retained. Cylinder geometry and arithmetic unchanged.'})
    dump(C/'judgenum_v1.json',cfg)
    old=json.loads((private/'judgenum_v1.r1.lock.json').read_text())
    dump(C/'judgenum_v1.lock.json',{**old,'locked_at':stamp(),
      'before_first_calculation':False,'before_first_cylinder_calculation':False,
      'before_first_calibration':True,'config_sha256':sha(C/'judgenum_v1.json'),
      'history':[{'file':p.name,'sha256':sha(p),'sealed':True} for p in sorted(private.glob('*'))]})
    dump(C/'analysis_implementation.lock.json',{'at':stamp(),'before_first_calibration':True,
      'config_sha256':sha(C/'judgenum_v1.json'),
      'sources':{p.name:sha(p) for p in [S/'analysis_core.py',S/'analyse.py']},'scientific_verdict':None})
    (D/'issues.md').open('a').write('\n- 항공 LiDAR 패치 법선은 원자료 TIN 삼각형의 법선이다. 이 법선을 만든 평면 맞춤 둘레 크기와 잔차 표준 편차가 없어 25배 규칙의 통과·미달을 구할 수 없다. 다시 법선을 맞추지 않고 확인 불가로 남긴다.\n- 지붕·벽에 함께 걸친 덩어리에서 두 최소 넓이가 서로 다른 처리를 요구하면 처리 뒤 판단과 처음 선택을 확인 불가로 남긴다. 새 문턱을 만들지 않는다.\n')
    print('CALIBRATION_LOCKED',sha(C/'judgenum_v1.json'))

if __name__=='__main__':main()
