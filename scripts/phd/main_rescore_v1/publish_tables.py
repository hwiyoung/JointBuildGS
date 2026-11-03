"""Publish unrounded tables from completed score receipts; no geometry recomputation."""
from common import *
import sys
NAMES={'prior':'사전 정보','mvs':'MVS','fusion':'결합','baseline_30000':'기준선 30,000회','GeoGS_30000':'GeoGS 30,000회','2DGS_30000':'2DGS 30,000회','CDGS_30000':'CDGS 30,000회','r8_30000':'r8 30,000회 · 옛 판단으로 학습한 임시값','r8_7000':'r8 7,000회 · 옛 판단으로 학습한 임시값','judgment_mesh':'판단으로 조합한 메시','oracle':'상한'}
CELL_NAMES={0:'둘 다 맞음',1:'보정이 맞음',2:'보존이 맞음',3:'둘 다 틀림',4:'결측이 맞음'}
def collect(sites,extra=False):
 allrows={str(i):[] for i in [3,4,5,7,8]};records=[]
 for site in sites:
  for prior in ['ALS','LoD2']:
   families=['prior','mvs','fusion','baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000']+(['r8_30000' if prior=='ALS' else 'r8_7000'] if site=='B173nb_b10' else [])+(['judgment_mesh','oracle'] if extra else [])
   for family in families:
    key=f'{site}__{prior}__{family}';p=O/'scores'/key/'values.json'
    if not p.exists():
     absent=json.loads((O/'unavailable'/f'{site}.json').read_text());row=dict(next(r for r in absent['rows'] if r['key']==key),method=NAMES[family]);allrows['3'].append(row)
     for cell in [0,1,2,4,3]:
      region=dict(row,cell=cell,cell_name=CELL_NAMES[cell]);allrows['4'].append(region)
      if family in ['baseline_30000','judgment_mesh','oracle']:allrows['7'].append(region)
     for cell in [1,2]:
      for band in ['0–0.5','0.5–1','1–2','2–4','>4']:allrows['5'].append(dict(row,cell=cell,offset_band_m=band))
     allrows['8'].append(row);continue
    v=json.loads(p.read_text());base=dict(site=site,prior=prior,key=key,method=NAMES[family],source=str(p),source_sha256=sha(p),surface=v['mesh'],surface_sha256=v['mesh_sha256'],source_tag='[이 발주에서 냄]');records.append(v)
    diagnostic={('n_result_sample_total' if k=='n_result' else k):x for k,x in v['diagnostic'].items()}
    allrows['3'].append(dict(base,**v['scene'],**diagnostic))
    for row in v['cells']:
     out=dict(base,**row,cell_name=CELL_NAMES[row['cell']],**diagnostic);allrows['4'].append(out)
     if family in ['baseline_30000','judgment_mesh','oracle','r8_30000','r8_7000']:allrows['7'].append(out)
    for row in v['offsets']:allrows['5'].append(dict(base,**row))
    allrows['8'].append(dict(base,**v['band']))
 return allrows,records

def main():
 early=sys.argv[1]=='b173';b173=sys.argv[1].startswith('b173');sites=['B173nb_b10'] if b173 else SITES[:3];rows,rec=collect(sites,not early)
 if not b173:
  missing=json.loads((D/'tables/unavailable_B173_only.json').read_text())['rows'];rows['3'].extend(missing)
  rows['4'].extend(dict(r,cell=c,cell_name=CELL_NAMES[c],status='확인 불가',n_gt=None,n_result=None,completeness=None,accuracy=None,gt_mean_m=None,result_mean_m=None) for r in missing for c in [0,1,2,4,3])
  for site in ['B0_b10','R1rep_b10']:
   for prior in ['ALS','LoD2']:
    absent=dict(site=site,prior=prior,key=f'{site}__{prior}__r8_unavailable',method='r8 본 방법 · 옛 판단으로 학습한 임시값',status='확인 불가',reason='해당 지역 r8 저장 상태 없음',n_gt=None,n_result=None,completeness=None,accuracy=None,gt_mean_m=None,result_mean_m=None,source=str(O/'inventory.json'),source_sha256=sha(O/'inventory.json'),source_tag='[이 발주에서 냄]')
    rows['3'].append(absent)
    for cell in [0,1,2,4,3]:
     regional=dict(absent,cell=cell,cell_name=CELL_NAMES[cell]);rows['4'].append(regional);rows['7'].append(regional)

 if not early:
  quality=[]
  for p in sorted((D/'tables').glob('target_quality_*.json')):quality.extend(r for r in json.loads(p.read_text())['rows'] if r['site'] in sites)
  table(('b173_' if b173 else '')+'table6',quality)
 for k,v in rows.items():table(('b173_' if b173 else '')+'table'+k,v)
 if b173:
  lines=['# B173 주변 비교 방법 채점 [이 발주에서 냄]','','새 τ: 항공 LiDAR 21.185600298468488 cm, LoD2 지붕 24.70203074282035 cm, 벽 39.23140804711729 cm. 학습한 판과 결합은 공통 203 학습 시점+16 가상 시점, TSDF 0.05 m/0.25 m, 연결 성분 50개 및 평가 범위 자르기다. 입력은 원래 삼각형 면과 앞 작업의 MVS 표면이며, 새 표본·거리를 다시 계산했다.','', 'r8은 옛 판단으로 학습한 임시값이다. LoD2 r8은 30,000회 저장 상태가 없어 7,000회다.','', '## 표 3: 장면 전체','','| 사전 정보 | 판 | 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm | 참값 수 | 유효 결과 점 수 |','|---|---|---:|---:|---:|---:|---:|---:|']
  for r in rows['3']:lines.append('| '+ ' | '.join([r['prior'],r['method'],*[f'{100*r[k]:.3f}' if r[k] is not None else '확인 불가' for k in ['completeness','accuracy','gt_mean_m','result_mean_m']],str(r['n_gt']),str(r['n_result'])])+' |')
  lines+=['','## 표 4: 맞는 판단 영역 전체','','| 사전 정보 | 판 | 칸 | 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm | 기둥 밖 % |','|---|---|---|---:|---:|---:|---:|---:|']
  for r in rows['4']:lines.append('| '+' | '.join([r['prior'],r['method'],r['cell_name'],*[f'{100*r[k]:.3f}' if r[k] is not None else '확인 불가' for k in ['completeness','accuracy','gt_mean_m','result_mean_m','outside_column_fraction']]])+' |')
  lines+=['','반올림 전 값·표본 수·입력 경로·SHA-256은 tables/b173_table3 및 b173_table4의 json/csv에 있다. 기둥 중복·지붕 기둥의 최근접 벽 비율과 참조 유효성 제외 비율도 함께 기록했다. scientific_verdict: null.']
  (D/'B173주변_비교방법_채점.md').write_text('\n'.join(lines)+'\n');progress('B173 주변 비교 방법 표 3·4 완료. B173주변_비교방법_채점.md 및 tables/b173_table*.')
if __name__=='__main__':main()
