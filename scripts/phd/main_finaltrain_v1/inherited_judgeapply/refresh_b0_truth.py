"""Reuse already evaluated GT axis positions; no second GT point-cloud run."""
from common import *
for prior in cfg()['priors']:
    name=f'B0_b10__{prior}.npz';old=loadz(O/'revisions/pre_ring_photo/core_points'/name);d=loadz(O/'decisions'/name)
    for k in ['centre','normal','prior_height_m','mvs_mean_m','n']:
        assert np.array_equal(d[k],old[k],equal_nan=True),k
    for k in ['gt_p','gt_status','cell','tau_m']:d[k]=old[k]
    d['region'][6]=old['region'][6];savez(O/'core_points'/name,**d)
progress('B0 최종 사진 점수 후 판단 갱신. 참값 축과 두 높이·n이 이전과 동일하여 기존 참값 평가를 그대로 연결; 참값 점군 재계산 없음.')
