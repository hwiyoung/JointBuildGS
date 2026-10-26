"""Incremental report and self-verifying ZIP delivery; no legacy writes."""
import sys,zipfile,hashlib,shutil,datetime,json
from common import *
HOST='/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp'
ART=HOST.rsplit('/',1)[0]+'/JointBuildGS-artifacts/phase-payloads/phd/slide_photo_v1/PHD-SLIDE-PHOTO-v1'
def report(stage):
    cfg=config();elapsed=(datetime.datetime.fromisoformat(now())-datetime.datetime.fromisoformat(cfg['locked_at'])).total_seconds();rows=['# 설명 자료용 실사 그림 — 보고 v1','',f'- 작업: `{cfg["task_id"]}` / 발주문 v5 / 갱신: {now()}', '- `scientific_verdict: null` · 학습 없음 · CPU만 사용',f'- 설정 잠금: `{sha(CFG/"slide_photo_v1.json")}`',f'- 기준 커밋: `{(PAY/"base_commit.txt").read_text().strip()}`',f'- 설정 잠금부터 보고서까지: **{elapsed/60:.1f}분** (입력 재계산, 점검, 대기 포함 경과 시간)','', '## 1. 범위와 기존 자료','',
      '일 0은 WIDEN0-v2 공개 개발용 NPZ에서 좌표·법선·패치 면적·건물 ID 등 허용된 입력 기하 키만 읽었다. 기존 판정, 칸, 오차 값과 학습 결과는 읽지 않았다. 원본 입력 타일, 학습 영상과 기하 일관성 검사 후 깊이로 다시 계산했다. `holdout/` 경로는 열지 않았다.',
      '새 수치는 **[이 발주에서 냄]**으로 표시한다. 드론 LiDAR는 기존 정합 좌표의 평가 참조다. MVS와의 일치가 독립적인 실제 표면 검증을 뜻하지 않으며, 재질의 원인 효과도 확정하지 않는다. 사진 재질 답은 외관 판단이다.','',
      '기존 그림은 다음 위치에서 확인했다. 이전 판은 설명 글자와 여러 도표를 포함하고 이번 슬라이드 배치·글자 크기·색에 맞지 않아 입력과 스크립트 일부를 재사용했다.',
      '- `docs/experiments/phd/main_regionfig_v1/figures/영역예시_보정.png`: 두 단면, 최종 숫자 JSON, 원본 및 표시 사진 재사용.',
      '- `docs/experiments/phd/main_photofig_v1/figures/photo_fig1_glass.png`: B173 유리 채광창 비교 위치 확인용. 일 0의 자리를 이 그림으로 고정하지 않았다.',
      '- `docs/experiments/phd/main_photofig_v1/figures/photo_fig3_r1.png`: 고정 R1 벽면 19 위치와 영상 이름 재사용.',
      '- `PHD-MAIN-STAGE1-v1/stage1/B0_b10/prop_LoD2_s0/model/dump/iteration_30000/`: 기존 RGB·깊이 렌더 재사용.',
      '- 발주문의 `docs/figures/영역예시_보정.png`는 현재 없으며 위 승격된 경로를 사용했다.','',
      '## 2. 일 0 — 전역 입력 검색','']
    p=DOC/'figures/task0_specular_candidates.json'
    if p.exists():
        d=load(p);rows += [f'상태: **{d["status"]}**. 24개 입력 타일의 개발용 기하를 검색했다. 기존 전역 칸은 사용하지 않았다.','', '|원래 면적 순위|건물|면|재질 답|넓이 m²|MVS−참조 절댓값 중앙값 cm|검사 통과 %|사전 정보−참조 중앙값 cm|색 흩어짐|','|---:|---|---|---|---:|---:|---:|---:|---:|']
        for r in d['top_five']:rows.append(f'|{r["rank"]}|{r["building"]}|{"지붕" if r["roof"] else "벽"}|{r["material_ko"]}|{r["area_m2"]:.2f}|{r["mvs_abs_median_m"]*100:.2f}|{r["pass_share"]*100:.2f}|{r["prior_signed_median_m"]*100:.2f}|{r["colour_scatter"]:.5f}|')
        rows += ['',f'유리·금속으로 판독된 적격 후보는 {len(d["top_five"])}개다. 다섯보다 적으면 나머지를 임의로 채우지 않는다. 원래 면적 상위 열 후보와 재질 답도 JSON에 모두 보존했다.']
        r=d['selected'];rows += ['',f'선택: `{r["component_id"]}` / `{r["building"]}` / {r["material_ko"]}.' if r else '유리 또는 금속으로 확인된 적격 덩어리가 없다. 임계값을 완화하거나 다른 자리를 대신 선택하지 않았다.',f'B173 기존 유리 채광창이 재질 확인 후 상위 다섯 안에 포함: **{d["b173_glass_in_top_five"]}**. 모든 후보의 패치 ID·영상·자른 상자는 JSON에 있다.','', '![상위 열 덩어리 접촉 시트](figures/task0_contact_sheet.png)','',
        '입력 선택 정의: 사전 정보 우선순위는 ALS, ALS 지원이 없는 위치에서만 LoD2. 허용 오차는 광역 동결값 ALS 12.66 cm, LoD2 20 cm. 지붕은 100점/m², 벽은 30점/m² 이상. 앞쪽 카메라에서 보이는 실제 GT 점을 깊이 화소에 대응시켜 법선 방향 잔차의 절댓값 중앙값을 계산했다. 두 개 이상 시점의 검사 통과가 필요하다. 연결은 같은 건물·면·유형과 15° 법선 조건, 거리 0.36 m 이내다.',
        '색 흩어짐은 RGB [0,1]에서 시점별 색과 중앙색 사이 유클리드 거리의 중앙값이다. 영상에서 보이는 실제 GT 대표점에 대해 계산한다. 참조 층이 여러 개라 대응이 모호한 패치는 제외했다. 24개 공개 입력 타일 전체의 점으로 만든 z-buffer를 사용했으며 이웃 화소로 채우지 않았다. 공개 개발용 LoD2 입력 면이 같은 광선에 0.5m 이상 앞서 있으면 가림으로 제외하는 보수적 검사도 적용했다. 최종 계산은 `mvs_v4`이며 가림 전 후보와 재질 판독은 무효 기록으로 분리했다.',
        '선택은 금속 외관과 깊이 불일치가 함께 관측된 사례다. 반사가 불일치의 원인이라는 독립 검증은 아니다. 사진에서 금속으로 읽히는 면이라도 MVS 점이 같은 실제 표면의 복원인지 완전히 보장하지는 않는다.','']
    else:rows += ['계산 또는 독립 재질 확인 진행 중.','']
    rows+=['## 3. 그림별 산출물과 값','', '|그림|파일|현재 상태|','|---|---|---|']
    figs=[('다 · 실제 변화','figS_c_change'),('다 · 표현 오차','figS_c_repr'),('다 · 영상이 틀림','figS_c_specular'),('가','figS_a_image_limits'),('라','figS_d_gs_real'),('마 · 보존','figS_e_aim_keep'),('마 · 보정','figS_e_aim_correct'),('마 · 다듬기','figS_e_aim_refine'),('마 · 상속','figS_e_aim_inherit'),('나','figS_b_correction_sections')]
    for label,name in figs:
        p=DOC/'figures'/f'{name}.png';qa=DOC/'qa'/f'{name}.json';state='그림 생성 · 독립 점검 대기' if p.exists() else '미완료'
        if qa.exists():state=load(qa).get('status','점검 기록 있음')
        rows.append(f'|{label}|[{name}.png](figures/{name}.png)|{state}|')
    if stage=='final':
        from report_details import details
        rows+=['']+details()
    rows+=['','B173 보정 참조값은 최종 REGIONFIG JSON의 **+455.634 cm**, MVS **+0.800 cm**이다. 옛 설정의 +484.1 cm 예상값은 쓰지 않았다. R1은 LoD2 **−101.607 cm**, MVS **−1.9 cm**의 방향을 확인한다.',
      'B0 표현 오차는 발주문의 양의 방향 조건을 만족하는 면이 없어 허용된 반대 부호 규칙을 적용했다. 면 7의 945개 입력 패치에서 LoD2−참조 중앙값 **−14.610 cm**, |MVS−참조| 중앙값 **2.111 cm**다. τ는 **19.75 cm**이며 20 cm에 맞추지 않았다.',
      '그림 라는 원본 화면 점유 조건을 충족하는 시점이 없어, 사용자가 승인한 동일 부분 자르기를 적용했다. 자른 사진과 렌더·깊이의 픽셀 범위를 같게 유지한다. 중간 학습 장면은 넣지 않았다.','',
      '## 4. 맥락 없는 독립 확인 답 전문','']
    for p in sorted((DOC/'qa').glob('*.json')):
        d=load(p)
        if 'round1' not in d and 'answers' not in d:continue
        rows += [f'### {p.stem}', '', '```json',json.dumps(d,ensure_ascii=False,indent=2),'```','']
    rows+=['## 5. 변경·예외·검증','', '자세한 실패 및 수정 기록은 [issues.md](issues.md)에 있다. 가시성 구현 결함과 보충 기록 03~05, 그때까지 본 자료를 모두 기록했다. 앞의 재질 답으로 최종 자리를 고르지 않고, 전수 재계산 후 새로운 맥락 없는 판독자의 답을 사용했다.',
      '원래 `regionfig_v1/common.py`의 COLMAP 파서·원본 카메라 투영, `photofig_v1/pf_geo.py`의 TSDF 단면 도구를 재사용했다. 이번 스크립트는 저장된 원본에 덮어쓰지 않으며 읽기 전용 마운트에서 실행한다. 가시성 C++ 최적화는 동일 화소 점유 및 1e-9 m 미만 수치 오차 조건을 통과했다.',
      '각 PNG는 요청한 픽셀 크기로 저장한다. 최종 전달 검증 JSON에 실제 크기·최소 글자 규격·PNG 해시를 남긴다. ZIP CRC와 구성 파일 해시 검사는 외부 `package_<단계>.json`에 남긴다. 독립 점검은 그림만 보고 답하도록 요청한다. PASS 표시는 해당 기술 검사에만 해당하며 과학적 판정이 아니다.',
      '입력 파일 SHA-256과 Python·수치/그림 라이브러리 버전은 [input_lineage.json](input_lineage.json), 큰 가림 오류의 회귀 검사는 [global_visibility_regression.json](qa/global_visibility_regression.json)에 있다. 원본 사진은 각 그림 JSON의 ZIP 멤버 해시로 식별한다.','',
      '## 6. 전달과 시간','',f'현재 단계: `{stage}`. 외부 전달 폴더: `{ART}`.',f'시작 설정 저장: {cfg["locked_at"]}. 현재 보고 저장: {now()}. 각 실행 시간과 종료 기록은 외부 payload의 `logs/`에 있다.',
      '최종본 이름: `PHD-SLIDE-PHOTO-v1_handover.zip`. 각 단계별 `_part_<단계>.zip`에는 그 시점까지의 그림, JSON, 보고서, 설정, 스크립트가 들어 있다.','']
    (DOC/'보고_v1.md').write_text('\n'.join(rows))
def package(stage):
    report(stage);entries=[]
    for root,prefix in [(DOC,'docs/experiments/phd/slide_photo_v1'),(CFG,'configs/phd/slide_photo_v1'),(REPO/'scripts/phd/slide_photo_v1','scripts/phd/slide_photo_v1')]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:entries.append((p,str(Path(prefix)/p.relative_to(root))))
    target=PAY/f'PHD-SLIDE-PHOTO-v1_handover_part_{stage}.zip';manifest={name:sha(p) for p,name in entries}
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for p,name in entries:z.write(p,name)
        z.writestr('MANIFEST_SHA256.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for name,h in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==h,name
    latest=PAY/'PHD-SLIDE-PHOTO-v1_handover.zip';shutil.copyfile(target,latest)
    rec=dict(stage=stage,at=now(),archive=str(target),sha256=sha(target),bytes=target.stat().st_size,members=len(entries)+1,crc='PASS',member_hashes='PASS',scientific_verdict=None)
    dump(PAY/f'package_{stage}.json',rec);(PAY/'SHA256SUMS').write_text(f'{rec["sha256"]}  {target.name}\n{sha(latest)}  {latest.name}\n');print(rec)
if __name__=='__main__':package(sys.argv[1])
