"""Record absent inputs without substituting a neighbouring region's patch data."""
from common import *
def main():
 site='B173_b0';rows=[]
 for prior in ['ALS','LoD2']:
  missing=[p for p in [JA/'core_points'/f'{site}__{prior}.npz',PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/work'/f'normals_{site}.npz'] if not p.exists()]
  assert missing,'Inputs appeared: inspect them instead of retaining an unavailable result'
  for family in ['prior','mvs','fusion','baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000']:
   key=f'{site}__{prior}__{family}';meshkey=f'{site}__LoD2__2DGS_30000' if family=='2DGS_30000' else key;mesh=O/'meshes'/meshkey/'final.ply'
   row=dict(site=site,prior=prior,key=key,method=family,status='확인 불가',reason='JUDGEAPPLY 핵심점 없음. MVS의 앞 작업 표면과 기준선 저장 상태도 없음. 해당 없는 값은 채우지 않음.',missing_sources=[str(p) for p in missing],surface=str(mesh) if mesh.exists() else None,surface_sha256=sha(mesh) if mesh.exists() else None,source_tag='[이 발주에서 냄]',n_gt=None,n_result=None,completeness=None,accuracy=None,gt_mean_m=None,result_mean_m=None,regional_status='확인 불가: JUDGEAPPLY 핵심점 없음')
   score=O/'scores'/key/'values.json'
   if score.exists():
    v=json.loads(score.read_text());row.update(v['scene']);row.update(status=v['status'],surface=v['mesh'],surface_sha256=v['mesh_sha256'],source=str(score),reason='장면 전체만 셈. 참값 법선은 원래 AXES71의 0.5 m / KNN 10 식으로 이 발주 출력에 계산. 영역·기둥은 핵심점 부재로 확인 불가.')
   rows.append(row)
 table('unavailable_B173_only',rows);progress('B173만: 입력 사전 정보·있는 비교 방법의 장면 전체 채점. 영역·기둥은 핵심점 부재로 확인 불가. 다른 지역 패치를 대입하지 않음.')
if __name__=='__main__':main()
