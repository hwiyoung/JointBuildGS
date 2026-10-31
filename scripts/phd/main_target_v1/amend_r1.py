"""User decision of 2026-10-31; immutable old config and stops remain available."""
import os
import shutil
from common import *


def main():
    c, previous = locked()
    assert not c.get('revision'), 'r1 already locked'
    history = CFG/'revisions/r0';history.mkdir(parents=True,exist_ok=False)
    for name in ['target_v1.json','target_v1.stage0.lock.json']:
        shutil.copyfile(CFG/name,history/name)
    olddocs=DOC/'revisions/r0';olddocs.mkdir(parents=True,exist_ok=False)
    for p in DOC.iterdir():
        if p.name=='revisions':continue
        if p.is_file():shutil.copyfile(p,olddocs/p.name)
        else:shutil.copytree(p,olddocs/p.name)
    c['revision']='r1_user_decision_20261031'
    c['amendments'].append({'at':stamp(),'reason':'Direct user decision 1-6 after stage0 stop',
        'decision_sha256':sha(CFG/'decision_20261031.txt'),'previous_config_sha256':previous['config_sha256'],
        'previous_config':'revisions/r0/target_v1.json','prior_results_seen':'input missingness and geometric join only; no T2, judgment accuracy, target or training'})
    c['sites']=['B0_b10','B173nb_b10','R1rep_b10']
    c['deferred_sites']=['B173_b0']
    c['training']['initial_arm_count']=6;c['training']['deferred_arm_count']=2
    c['training']['deferred_release']='own uncertainty complete, stage0 gates and existing 7000-step pilot pass'
    c['uncertainty']['parent_candidate']={}
    c['uncertainty']['missing_value_fallback']='median of finite raw u in the same unit and kind; never zero or a-only'
    c['uncertainty']['missing_prior_sigma']='median finite sigma_P in the same unit and kind'
    c['uncertainty']['median_donor_scope']='same unit and same prior; kind 1 roof / kind 2 wall; evaluation and stored band combined; raw finite values only, unweighted median'
    c['uncertainty']['jn_unit']='one stable building ID across tiles, separately within development or holdout; no cross-building or cross-split donors'
    c['uncertainty']['empty_donor_group']='remain unavailable, never invent a median'
    c['uncertainty']['replacement_flags']=['u_replaced','sigma_p_replaced','any_replaced']
    c['uncertainty']['report_strata']=['original','replaced','all']
    c['uncertainty']['sensitivity_missing_a']='same unit/kind raw finite a median; no zero substitution'
    c['b173_uncertainty']={'site':'B173_b0','seed_site_id':3,'seed':20261023,
        'definition':'exact UNCERT-v1 1.5m ring, mvs_a and raw ALS; own cameras, training split, depth and confidence',
        'sets':['ALS','LoD2'],'data':{'ALS':['mvs_a','als'],'LoD2':['mvs_a']},
        'use_gt':False,'copy_neighbour_values':False,'workers':4}
    c['stops']['stage0_unavailable_denominator']='in_eval area only; band reported separately'
    c['stops']['stage0_unavailable_definition']='missing/zero normal or values still unavailable after same-unit same-kind median filling'
    c['lod2_sigma_provenance']={'authority':'User decision 2026-10-31 item 4',
        'statement':'2026-10-26 방법 재정리 세션이 참값 없이 구한 값이다. 정밀한 MVS(u 5 cm 이하)와 LoD2의 차 분포를 두 무리로 맞추고, 좁은 무리의 폭에서 MVS 흔들림을 뺐다. 참값으로 한 같은 셈(평지붕 17.1 cm)은 점검에만 썼다.',
        'verification_boundary':'source statement supplied by user; original fitting session not independently replayed'}
    c['stage_status']='REOPENED_STAGE0'
    dump(CFG/'target_v1.json',c)
    newlock={'at':stamp(),'stage':0,'revision':c['revision'],'config_sha256':sha(CFG/'target_v1.json'),
        'decision_sha256':sha(CFG/'decision_20261031.txt'),'previous_config_sha256':previous['config_sha256'],
        'source_commit':os.environ['TARGET_COMMIT'],'image_id':os.environ['TARGET_IMAGE'],
        'pre_computation':True,'scientific_verdict':None}
    dump(CFG/'target_v1.stage0.lock.json',newlock);dump(CFG/'target_v1.r1.lock.json',newlock)
    progress=f'''# PHD-MAIN-TARGET-v1

{stamp()} — REOPENED_STAGE0. 사용자 10/31 결정 1~6 반영.

- 첫 학습 대상: B0·B173 주변·R1 × 두 사전 정보 = 6판.
- B173만: 자체 MVS/항공 LiDAR 불확실도 계산 후 단계 0을 적용해 2판 추가.
- 누락 u·항공 LiDAR σ_P: 같은 단위·같은 면 종류의 원래 유효값 중앙값, 대체 표시와 별도 집계.
- 셀 수 없음 중단 기준: 평가 범위 넓이만. 법선 없음은 그대로 셀 수 없음.
- LoD2 σ_P 출처: 사용자 제공 문장을 설정에 보존.
- T2·판단 정확도·학습은 아직 미실행. scientific_verdict: null.
- 단계 0 예상: CPU 2~4시간, 실제 원통·B173 계산 속도로 갱신.
'''
    (DOC/'progress.md').write_text(progress);(OUT/'progress.md').write_text(progress)
    print('R1_LOCKED',newlock['config_sha256'],newlock['at'])


if __name__=='__main__':main()
