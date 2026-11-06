"""Bounded factual report and independent section / precision archives."""
from add6_common import *

def report():
 text=[];labels={'FINALTRAIN_30000':'본 방법','GeoGS_30000':'GeoGS','fusion':'LGDM','judgment_mesh':'판단 메시'};direction={'perpendicular':'수직','parallel':'나란','inherited':'기존 방향'}
 for c in AC['cases']:
  key=c['id'].split('_')[0];r=selected(c);v=r['selection'];pairs=' · '.join(f"{labels[m]} {v[m+'_completeness_pct']:.2f}/{target:.1f}" for m,target in A6['targets'][key].items());text.append(f"- {key}: {direction[v['direction']]} {v['length_m']:.2f}m, 경우 {c['case_id']} {v['n_case_points']:,}점; 완전성(띠/목표 %) {pairs}; 조건2 {'통과' if v['condition2_pass'] else '미통과, 순위 조건 없이 선택'}.")
 text += ['', 'scientific_verdict: null', '', '후보는 경우 점 전체의 면적 가중 주축, 1m 간격, 폭 1m이다. 소유 패치 면적을 해당 참값 행 수로 나눠 가중했다. 사전 정보 지붕 면은 kind=1 prior 패치·75도·1m 규칙으로 찾았다. 기존 건물 식별자(없는 패치는 공통 GroundSurface XY)로 지붕 층을 묶고, 실제 사전 정보 교선 양끝에 1m씩 더했다. GroundSurface 끝·높이는 쓰지 않았다. c1은 지붕 전체를 가로지르는 수직 선이다. 채점·경우는 저장값을 재사용했다.', '', '조건을 만족한 후보 중 점수 순 위 셋(점수=목표와의 절대 차 합, %p):', '', '|자리|후보|경우 점|점수|조건2|','|---|---|---:|---:|---|']
 for c in AC['cases']:
  for v in selected(c)['top3']:text.append(f"|{c['id'].split('_')[0]}|{v['candidate_id']}|{v['n_case_points']}|{v['score_sum_abs_pp']:.3f}|{'통과' if v['condition2_pass'] else '미통과'}|")
 text += ['', '단면 원자료는 모든 경우의 참값·부호 거리·in/far/none과 단일 연직면 교선을 담았다. strip_metrics는 해당 경우만 집계했다. 확인용 그림은 해당 경우의 높이 범위 ±2m, 세로 과장 약 3배이며 원자료에는 화면 밖 교선도 남겼다.', 'c1·c2·c4는 기존 카메라·크기·거리 색을 유지했다. c3은 MVS 가림만으로 고른 45~70도 새 카메라다. 잘라 낸 원본 삼각형 번호는 각 JSON에 기록했다. 새 그림에는 단면 선·글자가 없다. 위 사진은 덧붙임5 색·겹침 순서다. 기존 그림은 덮어쓰지 않았다.']
 vpath=D/'verification/addendum6_delivery.json'
 if vpath.exists():
  v=json.loads(vpath.read_text());outside=[r['case'].split('_')[0] for r in v['checks'] if any(x['line_inside_fraction']<1 for x in r['frames'])]
  if outside:
   text.append('지정한 사진 범위·카메라를 유지한 '+', '.join(outside)+'는 새 선이 전부 또는 일부 화면 밖이다. 좌표와 가림은 JSON에 그대로 남겼다.')
   for r in v['checks']:
    short=[f"{x['method']} {100*x['line_inside_fraction']:.1f}%" for x in r['frames'] if x['line_inside_fraction']<1 and x['method'] not in ['fusion','GeoGS_30000']]
    if short:text.append(r['case'].split('_')[0]+' 새 선의 화면 내 비율: '+', '.join(short)+'.')
 text += ['', '정확성의 경우 배정: scripts/phd/main_release_v1/stage0.py:55–65에서 결과점의 기존 sample_owner와 같은 소유 패치의 3D 최근접 참값 행을 찾는다. 소유 일치가 없으면 -1이다. scripts/phd/main_gtjudge_v1/stage0.py:58–62가 이를 재사용하고 collect.py:31–38이 그 행의 stage1 case_id와 sample_eligible로 정확성을 집계한다. 전체 참값의 무조건 최근접 경우 배정이 아니다.', '덧붙임2 add2_scores.py:18–25는 같은 배정에 ALS |n_z|<0.5 제외를 더한다. precision_where.csv는 원 단계1과 이 수정판을 accuracy_version으로 분리한다. 지도는 원 단계1 분모다. 오류 분해는 전역 3D 최근접 채점 참값 행의 LGDM 면 없음과 저장된 네 특징 구분을 사용한다.']
 pp=D/'verification/addendum6_precision.json'
 if pp.exists():
  p=json.loads(pp.read_text());text.append('정확성 표 재현과 오류 분할 수 보존 통과. 원 단계1 오류 수(본 방법/LGDM): '+ ' · '.join(c+': '+ '/'.join(str(next(x['bad_n'] for x in p['checks'] if x['case'].startswith(c+'_') and x['method']==m and x['version']=='stage1_original')) for m in ['FINALTRAIN_30000','fusion']) for c in ['c1','c4'])+'점.')
 else:text.append('정확성 오류 분해는 별도 묶음으로 후속 제공한다.')
 text.append('확인 불가: 원 정사영상의 화소별 고도 캐시는 없어 위 사진 가림은 MVS 연직 광선의 대리값이다. 특징 미관측(-2)은 그 밖으로 합치지 않고 별도 표시한다.')
 out='\n'.join(text)+'\n';assert len(out)<=3000,len(out);(D/'보고_덧붙임6.md').write_text(out);print('ADD6_REPORT_CHARACTERS',len(out),flush=True)

def package(kind):
 assert kind in ['sections','precision']
 verification=D/'verification'/('addendum6_delivery.json' if kind=='sections' else 'addendum6_precision.json');assert json.loads(verification.read_text())['status'].startswith('PASS_')
 report()
 if kind=='sections':files=sorted(p for p in F6.iterdir() if p.is_file() and '_precision_map' not in p.name)+sorted(T6.glob('section_candidates_*.csv'));name='사례단면렌더'
 else:files=[T6/'precision_where.csv']+sorted(F6.glob('*_precision_map.*'));name='정확성확인'
 files.append(D/'보고_덧붙임6.md')
 rows=[dict(member=str(p.relative_to(D)),bytes=p.stat().st_size,sha256=sha(p)) for p in files];dest=O/'delivery'/f'PHD-MAIN-GTJUDGE-v1_{name}.zip'
 assert not dest.exists(), 'Preserve an already delivered archive; use an explicitly versioned follow-up.'
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for p,r in zip(files,rows):z.write(p,r['member'])
  z.writestr('manifest.json',json.dumps(dict(task_id='PHD-MAIN-GTJUDGE-v1',addendum=6,kind=kind,files=rows,config=A6,config_sha256=sha(C/'addendum6.json'),scientific_verdict=None),ensure_ascii=False,indent=2))
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for r in rows:assert hashlib.sha256(z.read(r['member'])).hexdigest()==r['sha256']
 receipt=dict(at=now(),status='PASS_ZIP_CRC_AND_MEMBER_SHA256',path=str(dest),sha256=sha(dest),bytes=dest.stat().st_size,members=len(rows)+1,scientific_verdict=None);dump(D/'verification'/f'addendum6_{kind}_archive.json',receipt);print('ADD6_DELIVERED',json.dumps(receipt,ensure_ascii=False),flush=True)

if __name__=='__main__':
 if sys.argv[1]=='report':report()
 else:package(sys.argv[1])
