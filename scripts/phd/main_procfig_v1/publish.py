"""Requested compact report, data dictionary and package; no scientific verdict."""
from common import *
import zipfile
HOST='/media/innopam/InnoPAM-8TB/hwiyoung/code'
def hostpath(s):return s.replace('/art/',HOST+'/JointBuildGS-artifacts/').replace('/repo/',HOST+'/JointBuildGS-exp/').replace('/out/',HOST+'/JointBuildGS-artifacts/phase-payloads/phd/main_procfig_v1/PHD-MAIN-PROCFIG-v1/')
def main():
 c=cfg();lock=json.loads((D/'input_lock.json').read_text());rec=json.loads((D/'measure_receipt.json').read_text());cp=json.loads((D/'section2_checkpoints.json').read_text())['rows'];sch=json.loads((D/'schedule_receipt.json').read_text());attr=json.loads((D/'attribution_receipt.json').read_text());ver=json.loads((D/'verification.json').read_text());gt=loadz(c['sources']['target']);counts=rec['building_counts'];lineage=list(csv.DictReader((D/'tables/wrong_patch_lineage.csv').open()));fills=list(csv.DictReader((D/'tables/filling_intervals.csv').open()));last=next(r for r in lineage if r['iteration']=='30000' and r['group']=='틀린 판정');first=next(r for r in lineage if r['iteration']=='0' and r['group']=='틀린 판정');edges={r['judgment']:float(r['interval_edge_fraction']) for r in fills if r['iteration']=='30000' and r['origin']=='묶임' and r['face']=='지붕' and r['judgment'] in ['일치','보정','보존'] and r['interval_edge_fraction']}
 rows=[dict(item='run',path=hostpath(str(MODEL.parent)),commit_record='training HEAD not recorded; source config base 47ce3030ce58aded1e814316a3b4ab8cd6aaec89; r23 Git incorporation 926bf2d1dc8cd994774a985b007f34ed500644b1',columns='',count='')]
 for r in cp:rows.append(dict(item=f"checkpoint_{r['iteration']}",path=hostpath(r['path']),sha256=r['sha256'],count=r['gaussians'],columns='xyz=model[1]; quaternion_wxyz=model[5]; log_scale=model[4]; logit_alpha=model[6]; origin; init_id; target_r6.meta.target_tag/target_index/target_released_at'))
 for label in ['prior','mvs_points','target','seeds']:
  src=lock['sources'][label];rows.append(dict(item=label,path=hostpath(src['path']),sha256=src['sha256'],count=len(gt['centre']) if label=='target' else '',columns=';'.join(gt) if label=='target' else ''))
 table('section2_inventory',rows)
 targetcols=', '.join(gt.keys());fullroot=hostpath(str(MODEL.parent));priorrel='S1/defs/B173nb_b10/prior_ALS.npz';mvsrel='UNCERT/points/B173nb_b10/mvs_a_xyz.npy'
 report=['|항목|자료 확인|','|---|---|',f'|판의 폴더|`{fullroot}`. 설정 source_commit `47ce3030`; r23 Git 편입 `926bf2d1`. 실행 당시 HEAD는 미기록. 전체 해시·경로: `tables/section2_inventory.csv`.|']
 for r in cp:report.append(f"|{r['iteration']:,}회|`model/jbgs_complete/iteration_{r['iteration']}/checkpoint.pth`; {r['gaussians']:,}개.|")
 report+=['|저장 열|중심, wxyz 회전, log 크기, logit 불투명도, origin, init_id, 현재 target_tag·target_index·released_at. 계산은 활성화 값.|','|0회|CPU 재구성. r23 seeds와 저장된 불변 initial_scale·normal 사용. 패치 회전은 원래 값, 배경 회전은 같은 법선의 원형 원반으로 재구성. 학습 0회.|',f"|입력 ALS|`{priorrel}`; SHA256 `{lock['sources']['prior']['sha256']}`.|",f"|입력 MVS|`{mvsrel}`; SHA256 `{lock['sources']['mvs_points']['sha256']}`.|",f'|목표|`FINALTRAIN/targets/B173nb_b10__ALS.npz`; {len(gt["centre"]):,}패치. 열: {targetcols}.|',f'|실제 일정|불투명도 되돌림: {"·".join(map(str,sch["opacity_reset_iterations"]))}회. 밀도 제어: 600~14,900회, 매 100회({len(sch["densification_iterations"])}회, 실행 로그 대조).|','',f"건물 `{c['scope']['building_id']}`의 기존 윤곽 XY+1m, 지역 Z {c['scope']['z_min']:.6f}~{c['scope']['z_max']:.6f}m. 지면은 고정 DTM 사례 중심 셀. 입력은 가우시안 시점이 아니며 수·넓이는 `input_counts`에 별도 기록.",'','|회|건물 전체|지붕|벽|','|---:|---:|---:|---:|']
 for r in counts:report.append(f"|{r['iteration']}|{r['building_gaussians']}|{r['roof']}|{r['wall']}|")
 report+=['',f"3.2: 지붕 분모 {rec['roof_area_m2']:.6f}m². 출신·면·현재 판정별 불투명도, 크기, 밀도, 구간·거리: `filling_intervals.csv/md`. 30,000회 지붕의 구간 끝 비율: "+', '.join(k+f' {100*v:.3f}%' for k,v in edges.items())+'.',f"3.3: 틀린 판정 {rec['selected_wrong_patches']}패치·{float(first['area_m2']):.6f}m², 비교 {rec['selected_control_patches']}패치. 30,000회 틀린 판정 계보 {last['live_init_ids']}개·자손 {last['descendants']}개, 덮는 양 비 {float(last['coverage_ratio']):.6f}, 옛 지붕 쪽 α 중앙값 {float(last['near_old_roof_opacity_median']):.6f}. 전체 시점은 `wrong_patch_lineage`, 패치 목록은 `selected_patches`.",f"실제 α×T 출신: {attr.get('attributed_rows',0):,}/{attr.get('reference_rows',0):,}행 연결, {attr.get('unavailable_rows',0)}행 확인 불가(해당 학습 화소에서 보이지 않음). 표·NPZ 제공.",'','그림: 입체 30장, 확대 15장, 위 지도 2장, 단면 확인 1장. 입력·0·7천·1만5천·3만, 1위 a–d/2·3위 a, 확대 a–c. PNG마다 카메라·축척·SHA JSON. `proc_section_data.json`, `gaussians/`, `README_자료.md` 포함.','',f"확인: 30,000회 저장 상태를 독립 재집계한 {ver['direct_checkpoint_building_count']:,}개와 일치. 그림 48장 해독·크기·sRGB 및 카메라 일치 검사. 배경 초기 쿼터니언의 원래 바이트·실행 당시 Git HEAD는 확인 불가. PLY와 완전 체크포인트 저장 단계 차이는 `saved_phase_audit.json`에 기록. 선택 단계3은 이번 묶음에서 안 함. 학습·기존 파일 변경 없음. scientific_verdict: null."]
 text='\n'.join(report)+'\n';assert len(text)<=3000,len(text);(D/'보고_v1.md').write_text(text)
 readme='''# 자료 읽기

작업: PHD-MAIN-PROCFIG-v1 / 덧붙임1. scientific_verdict: null. 학습 반복 0.

`PH`는 저장소 루트가 아니라 기존 외부 `JointBuildGS-artifacts/phase-payloads/phd` 별칭이다.
아래 숫자·모든 파일은 같은 고정 건물 범위이다. 입력은 원자료이고 가우시안 상태는 0/7000/15000/30000 네 개다.
표의 빈 수치는 해당 없음/빈 모집단이며 0으로 채우지 않았다. 구간 끝은 목표 법선 구간 양 끝 중 가까운 끝에서 0.001m 이내이다.

## gaussians/<회>.npz

|열|뜻|
|---|---|
|xyz|N×3, 지역 XYZ m, float32. EPSG:25832 좌표 = xyz + [690953,5336071,604]|
|normal|N×3 단위 원반 법선. 회전의 세 번째 축|
|rotation|N×4 정규화 쿼터니언 w,x,y,z; 첫 두 축이 원반 접선|
|scale|N×2 활성화 접선 축 반지름 m. 긴/짧은 축은 max/min. 표시 배율은 별도 적용|
|opacity|활성화 sigmoid α, float32|
|origin|불변 출신: 0 SfM 배경, 1 패치 씨앗|
|target_tag|현재 상태: 0 배경, 1 묶임, 2 풀림|
|judgment|현재 묶인 패치 판정: 0 일치, 2 보정, 1 보존, 4 결측. -1 묶이지 않음|
|current_patch|현재 묶인 원래 FINALTRAIN targets 행 번호. -1 묶이지 않음|
|target_index|r23 valid-patch 목록 내부 인덱스. 풀린 행은 과거 값이 남을 수 있어 current_patch로 해석|
|initial_patch|불변 init_id 씨앗의 targets 행 번호. -1 배경|
|init_id|불변 처음 씨앗 행 번호. clone/split 자손에 유지되는 int32. 가우시안 고유 번호가 아님|
|group33|고정 초기 계보 무리: 0 기타, 1 틀린 판정, 2 보정 비교. 처음 범위 밖 씨앗은 0|
|wall|abs(normal dot 고정 gravity up)<0.5|
|full_gaussian_index|해당 저장 상태 전체 배열의 행 번호|
|target_xyz,target_sigma|묶였을 때 현재 목표 XYZ와 σ. 미묶임은 NaN|
|normal_offset|현재 중심−목표를 목표 법선에 투영한 m. 부호 있음|
|target_released_at|풀림 반복 번호, -1 미발생|

0회는 r23의 CUDA 전용 로더 대신 저장 seeds와 불변 초기 scale/normal을 사용했다. 새 위치·새 씨앗·새 제외 규칙을 만들지 않았다.
패치의 quaternion은 seeds 원본이다. 배경의 초기 두 축 scale이 정확히 같음을 확인하고 기존 axes/quat 함수로 같은 원반을 구성했다.
따라서 초기 원반의 위치·형태·법선은 재현하지만 배경 원래 quaternion 바이트나 재개 가능한 전체 훈련 상태를 주장하지 않는다.

## 그림과 단면

색은 일치 #7FA7D9, 보정 #D85A30, 보존 #1D9E75, 결측 #E8B931, 배경/풀림 #B4B2A9, 틀린 판정 계보 #C2378A.
a=0.6배 모두 불투명, b=1배 모두 불투명, c=0.6배 실제 α, d=0.6배 α≥0.1만 불투명(자주 계보에도 적용). 덧붙임1의 d 정의에 맞춘 표시 정정 잠금 display_fix1은 수치 계산과 읽는 기준을 변경하지 않는다.
같은 카메라 번호의 모든 상태·표시판은 동일 정사 투영. 광원은 고정, 원반은 GS 영상 렌더가 아니다.
화소 중심마다 원반 평면 깊이를 계산하고 깊이 순서로 합성한다. 건물·확대 범위 경계에서도 화소 XYZ를 검사해 자른다.
위 지도 NPZ counts[y,x,group]는 0.25m 칸별 지붕 중심 수다. 겹친 칸은 자주→보정→기타 순으로 색만 우선한다. 수치는 각 채널을 모두 보존한다.
단면 JSON states는 배열 열 형식이다. 순서는 각 시점 배열 순서이며 s,z,α,출신,현재판정,계보표시,목표,σ를 보존한다. null은 미묶임 등 실제 미정값이다.
단면 확인 그림은 위에서 0,7000,15000,30000회. 네 패널의 s/Z 범위가 같다. 위치 확인용 가우시안 표식은 불투명이며 실제 α는 JSON에 있다.
카메라 순위는 건물 범위 경우1 참값의 기존 30,000회 결과 메시 가림 검사로 정했다. 이 참값 사용은 발주문 4.1의 표시 시점 선택에 한정된다.

## 계보와 검증

3.3 선택은 기존 참값 행 소유권 row_owner → core.source_index를 그대로 사용했다. patch_id 동일성을 확인했다.
다수는 유일 최빈 경우1이며 동률을 임의로 풀지 않는다. 높이 비교는 원래 prior 위치와 배정 참값 Z 중앙값이다.
처음 건물 범위의 씨앗 무리를 고정하고 이후 같은 범위 안 자손을 집계했다. 범위 밖 자손도 표의 별도 열에 있다.
실제 출신 NPZ attribution_30000은 기존 FINALTRAIN PLY/렌더를 원래 α×T 계보 도구로 재현한 것이다. 표의 분모는 선택 패치에 소유된 건물 범위 참값 행이다.
snapshot/PLY 저장 뒤 한 번 더 경계 투영하는 완전 체크포인트의 단계 차이는 saved_phase_audit.json에 별도로 기록했다. 그림·정량은 완전 체크포인트, 카메라 순위·실제 출신은 기존 최종 결과 계보를 쓴다.
입력 해시 input_lock.json, 개별 확인표 section2_inventory, 독립 검사 verification.json, 오류·보완 issues.md, 설정 잠금 procfig_v1.lock.json을 함께 읽는다.
재실행은 scripts/run.sh cpu freeze.py → torch checkpoints.py → cpu measure.py → cpu schedules.py → cpu render.py → cpu sections.py → gpu attribution.py → cpu attribution_tables.py → cpu phase_audit.py → cpu verify.py → cpu publish.py 순서다.
기존 잠금이 있으면 freeze.py는 재실행을 거부한다. 위 명령은 원래 저장소 scripts/phd/main_procfig_v1/ 위치에서 실행하며 번들 scripts/는 같은 코드의 보관본이다.
'''
 (D/'README_자료.md').write_text(readme)
 payload=[]
 for folder in [O/'figures',O/'gaussians']:
  for p in sorted(folder.iterdir()):
   if p.is_file():payload.append(dict(path=hostpath(str(p)),archive_path=p.relative_to(O).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 dump(D/'payload_manifest.json',dict(PH_resolution=hostpath(str(PH)),members=payload,scientific_verdict=None))
 checklist='''# 보내기 전 점검

- [x] 학습 반복 0; 기존 학습/서비스 중단 없음.
- [x] 보고서 첫 표 및 section2_inventory에 실제 자료 경로·열·개수·해시·일정 기록.
- [x] 0회는 r23 저장 씨앗/초기 불변 필드에 의한 CPU 재구성임을 명시.
- [x] 입력 원자료 수·넓이와 가우시안 네 시점이 같은 건물 범위. 입력에 가우시안 수를 대입하지 않음.
- [x] 30,000회 저장 완전 체크포인트를 별도로 읽어 건물 범위 개수/행을 대조.
- [x] 각 카메라의 모든 상태/표시판 동일 투영. 그림은 글자 없이 축척 막대만.
- [x] 참값은 발주문 3.3 패치 선택 및 4.1 표시 카메라 순위/표시·출신 확인에 사용. 목표·학습 파라미터 변경 없음. 패치 수·넓이 보존.
- [x] 산출물은 네 지정 경로만 사용. PH는 기존 외부 artifact 경로로 해석. 입력 저장소·artifact는 Docker read-only.
- [x] 선택 단계3은 이번 묶음에서 안 함으로 기록. 단계1·2를 기다리게 하지 않음.
- [x] scientific_verdict: null. 읽는 조건의 충족 여부와 발표 문구는 자동 판정하지 않음.
'''
 (D/'체크리스트.md').write_text(checklist)
 # Package frozen results with inner hashes; no work caches or inherited payloads.
 entries=[]
 for root,prefix in [(D,'docs'),(C,'config'),(R/'scripts/phd/main_procfig_v1','scripts'),(O/'figures','figures'),(O/'gaussians','gaussians')]:
  for p in sorted(root.rglob('*')):
   if p.is_file() and p.name not in ['worktree_before.z','package_receipt.json','delivery_receipt.json'] and '__pycache__' not in p.parts:entries.append((p,prefix+'/'+p.relative_to(root).as_posix()))
 sums=''.join(sha(p)+'  '+name+'\n' for p,name in entries);dest=O/'work/package_finalizing.zip'
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p,name in entries:z.write(p,name)
  z.writestr('SHA256SUMS',sums)
 assert dest.stat().st_size<=350_000_000,'split gaussians required'
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for line in z.read('SHA256SUMS').decode().splitlines():h,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==h
 final=O/'PHD-MAIN-PROCFIG-v1.zip';dest.replace(final);dest=final
 receipt=dict(at=now(),status='PASS_ZIP_CRC_AND_MEMBER_SHA256',path=hostpath(str(dest)),bytes=dest.stat().st_size,sha256=sha(dest),members=len(entries)+1,report_characters=len(text),figures=48,scientific_verdict=None,stage3='not executed optional')
 dump(D/'package_receipt.json',receipt);(O/'PHD-MAIN-PROCFIG-v1.zip.sha256').write_text(receipt['sha256']+'  '+dest.name+'\n');print('PACKAGE_PASS',receipt['bytes'],receipt['sha256'],len(text),flush=True)
if __name__=='__main__':main()
