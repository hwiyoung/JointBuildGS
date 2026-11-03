from common import *
import shutil
root=O/'revisions/pre_ring_photo';root.mkdir(parents=True,exist_ok=False)
for dirname in ['photo_prepared','photo_scores','photo_mapping','photo_geometry','photo_points','decisions','training_regions','core_points']:
    for p in (O/dirname).glob('B0_b10*'):
        dest=root/dirname/p.name;dest.parent.mkdir(parents=True,exist_ok=True)
        if p.is_dir():shutil.copytree(p,dest)
        else:shutil.copy2(p,dest)
for p in (O/'timing').glob('B0_b10*.json'):shutil.copy2(p,root/p.name)
progress('원래 링 재계산으로 ALS 44개 복구(B0 2, B173 38, R1 4). B0 r이 0.000000200177060304 m 변하여 잠정 B0 사진/판정/평가를 revisions/pre_ring_photo에 보존하고 최종 높이로 사진 재계산. 임계값 변경이나 CPU/GPU 재검산 없음. first_region_gate 키를 정확한 저장 키로 수정; tables/figures 스크립트 추가. 설정 재잠금 없음.')
issue('링 재계산의 기존 영벡터 법선에서 invalid divide 경고 발생. 해당 값은 확인 불가 유지; 법선 또는 불확실성을 임의 대체하지 않음.')
