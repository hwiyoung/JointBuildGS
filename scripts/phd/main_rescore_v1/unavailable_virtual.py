"""Record absent inherited virtual targets without substituting train-only surfaces."""
from common import *
import sys
def main(site):
 cfg();assert site in ['B0_b10','R1rep_b10'];source=S1/'defs'/site/'unseen.npz';assert not source.exists()
 views=O/'views'/f'{site}.json';v=json.loads(views.read_text());assert v['final_views_status']=='확인 불가' and not any(x['virtual'] for x in v['views'])
 reason='기존 stage1/fill의 가상 시점 입력 unseen.npz가 없는 지역. 새 시점 정의나 학습 시점 메시의 최종 메시 대체를 하지 않음(발주 1.3, 1.5, 4.1).'
 rows=[]
 for prior in ['ALS','LoD2']:
  for family in ['fusion','baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000','judgment_mesh','oracle']:
   rows.append(dict(site=site,prior=prior,key=f'{site}__{prior}__{family}',status='확인 불가',reason=reason,missing_source=str(source),source=str(views),source_sha256=sha(views),n_gt=None,n_result=None,completeness=None,accuracy=None,gt_mean_m=None,result_mean_m=None,source_tag='[이 발주에서 냄]'))
 record=dict(site=site,rows=rows,definition_sources=['scripts/phd/main_stage1_v1/gpu_s1.py:307-314 (only if unseen exists)','scripts/phd/main_fill_v1/virtual/vv_defs.py:47-54 (B0/R1 explicitly excluded)'],scientific_verdict=None)
 dump(O/'unavailable'/f'{site}.json',record);table('unavailable_final_views_'+site,rows)
 table('low_cell0_'+site,[dict(site=site,status='확인 불가',reason='기준선 및 비교 방법 최종 메시 부재로 칸 0 저하 조건을 검사할 수 없음.')])
 progress(f'{site}: 원래 가상 시점 입력 없음. 입력 둘 채점·목표 계산·기존 학습 시점 메시 확보 완료. 최종 메시와 의존 값은 확인 불가.')
if __name__=='__main__':main(sys.argv[1])
