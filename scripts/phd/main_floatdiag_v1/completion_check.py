"""Work-order coverage checks; technical completeness is not a scientific verdict."""
import json
from common import *
cfg=config();cases=json.loads((CFG/'cases_ALS.json').read_text())['cases'];assert len(cases)==7
for c in cases:
    for suffix in ['plate_A2','multiview_map_A2','multiview_examples_A2']:
        p=DOC/'figures'/(c['id']+'_'+suffix+'.json');assert p.exists()
        assert (DOC/'보기/img'/(c['id']+'_'+suffix+'.jpg')).exists()
for s in SITES:
    for key in [f'forces_{s}',f'gradients_{s}',f'gaussians_{s}_ALS',f'photo_{s}',f'four_depths_{s}_ALS',f'multiview_summary_{s}_ALS',f'multiview_histogram_{s}_ALS']:
        for suffix in ['.md','.json','.csv']:assert (DOC/'tables'/(key+suffix)).exists(),key+suffix
for case in ['R1-뜬면-1','R1-뜬면-2']:
    for suffix in ['formation_A2','formation_depth_A2','formation_population_A2']:assert (DOC/'figures'/(case+'_'+suffix+'.json')).exists()
g=json.loads((DOC/'tables/gate.json').read_text());assert g['definition_unchanged'] and g['gate1_status']=='FAIL'
assert g['stage_B']=='NOT_RUN_USER_DECISION'
assert not list((OUT/'runs').glob('*/fx_*'))
assert json.loads((OUT/'packages/A1_package_verified.json').read_text())['CRC']=='PASS'
assert json.loads((OUT/'qa/A2/receipt.json').read_text())['status']=='PASS'
assert json.loads((DOC/'provenance/multiview_validation.json').read_text())['status']=='PASS'
assert json.loads((DOC/'provenance/tsdf_update_behavior.json').read_text())['status']=='PASS'
assert json.loads((DOC/'provenance/replay_results.json').read_text())['status']=='PASS_RECEIPTS'
report=DOC/'뜬면진단_보고_v1.md';assert len(report.read_text())<20000
web_bytes=sum(p.stat().st_size for p in (DOC/'보기').rglob('*') if p.is_file());assert web_bytes<150000000
checks=[dict(requirement='4.2 r/sigma and own/opposite force',status='PASS'),dict(requirement='4.3 centre gradients',status='PASS'),
    dict(requirement='4.4 Gaussian counts and lineage',status='PASS_WITH_UNRECORDED_ORIGINAL_LINEAGE'),
    dict(requirement='4.6 original 15000/30000 observations',status='PASS'),
    dict(requirement='4.7 original two runs plus exactly one user-authorized current retry',status='PASS_WITH_PRESERVED_ORIGINAL_STOP'),
    dict(requirement='7 seven 3D/multiview/case plates',status='PASS_WITH_R1_PRESERVATION_MAIN_PHOTO_UNAVAILABLE'),
    dict(requirement='added same-pixel four depths',status='PASS_WITH_UNAVAILABLE_MAIN_VIEW_AND_MISSES'),
    dict(requirement='added all training-photo representative and full-pixel checks',status='PASS'),
    dict(requirement='TSDF source and actual Open3D behavior',status='PASS'),
    dict(requirement='Stage B, r18 and corrected-loss runs',status='NOT_APPLICABLE_USER_EXCLUDED')]
save(DOC/'provenance/completion_checks.json',dict(at=now(),status='TECHNICAL_DELIVERY_COMPLETE_WITH_EXPLICIT_UNAVAILABLE_FIELDS',checks=checks,
    report_characters=len(report.read_text()),viewer_bytes=web_bytes,scientific_verdict=None))
(DOC/'보내기전_점검.md').write_text('# 보내기 전 점검\n\n'+''.join('- '+r['requirement']+': '+r['status']+'\n' for r in checks)+'\n과학 판정은 하지 않았다. 원래 건강 중단과 사용자 승인 재시도를 구분했다. 묶음 검증 결과는 전달 목록에 있다.\n')
print('work order and both user additions: technical coverage PASS; unavailable fields retained')
