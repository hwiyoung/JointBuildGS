"""Build the concise report and portable local image index from validated records."""
from representative_draw import TITLES, NOTES, CASE
from rfcore import *
import html,os,shutil

def main():
    rev='representative_v1';root=DOC/rev;design=load(CFG/rev/'design.json');v=load(root/'verification.json')
    assert v['status']=='PASS';assert (root/'reviews/final_review.md').is_file()
    lines=['# 여덟 케이스 대표 그림 재작업','',
      '대표 그림 여덟 장과 기존 상세 근거 그림을 함께 제공한다. 같은 A 패치를 실제 사진·확대 사진·수치 판정·고정 단면에 연결했다. A는 사례를 설명하기 위해 결과를 확인한 뒤 고른 패치이며, 임의 표본이나 모집단을 대표하는 통계 표본이 아니다.','',
      '결과는 제공받은 **학습 없는 손실 최소점**이다. 새 학습·사진 검사·최적화를 하지 않았다. 맞고 틀림은 제공된 참조값과 허용 오차 기준이며 독립적인 진실 판정이 아니다. `scientific_verdict: null`.','',
      '[여덟 그림을 한 화면에서 열기](index.html) · [기존 상세 보고서](../영역표본그림_보고_v1.md)','',
      '| 사례 | A에서 보여주는 관계 | 사진 범위의 해당 영역: 범주별 / 검사 기반 맞은 넓이 |','|---|---|---|']
    rows=[]
    for i in range(1,9):
        r=load(root/f'대표그림_{i}.json');f=r['focus'];t=f['target'];rows.append(r)
        title,sub=TITLES[str(i)]
        lines.append(f'| [{i}. {title}](대표그림_{i}.png) | {sub.removeprefix("A: ")} | {t["ok_category_pct"]:.1f}% / {t["ok_check_pct"]:.1f}% ({t["area_m2"]:.1f} m²) |')
    lines += ['', '## 읽는 순서','',
      '① 원본 사진에서 A를 찾고 ② 확대 사진에서 사진 검사의 판단을 본다. ③은 같은 패치의 사전 정보·두 결과를 제공 참조값과 비교한 법선 방향 오차다. 초록 띠는 허용 범위이며 사례마다 축 범위가 다르다. ALS는 ±12.66 cm, LoD2는 ±20 cm다.','',
      '④⑤는 원래 고정 단면의 같은 축을 사용한다. 선·작은 점은 단면 폭 안에서 0.25 m별로 계산한 주변 중앙값이고, 큰 기호는 A 패치 원값이다. A가 선과 다를 수 있으므로 화살표로 원값을 직접 가리킨다. 사진의 A는 단면 폭 안에 속하는 패치이며 중심선 위의 점이라는 뜻은 아니다. ③의 법선 오차(cm)와 ④⑤의 연직 높이(m)는 서로 다른 양이다.','',
      '## 해석을 고친 두 사례','',
      '**4번:** 순수 보존 성공의 대표로 단정하지 않았다. A는 허용 범위 안에 남지만 오차가 사전 정보보다 커졌고, 전체 보존 영역의 검사 기반 맞은 넓이는 78.7%다. 기존 자리를 유지한 채 제목에 일부 실패가 포함된 사례임을 적었다.','',
      '**7번:** “비가시”를 “사진 정보 부족”으로 바꿨다. [기존 검사 기록 추적](photo_shortage_trace.json)에서 A의 적격 사진과 선택 사진은 모두 2장이다. 최소 3장 규칙에 못 미쳐 사진 부족으로 분류되었다. 사진에 지붕은 보이며, 물리적으로 가려진 원인은 확인 불가다.','',
      '## 표본 선정과 수치 범위','',
      '원래 사진·자른 상자·회전·건물·고정 단면을 모두 유지했다. 제공된 영역 분류와 해당 검사 판단·결과 조건을 같은 패치에서 동시에 충족하는 후보를 찾고, 단면 중간에 가장 가까운 패치를 선택했다. 동률은 중심선 거리와 patch_id 순으로 정했다. 이 결과 의존적 설명용 선정과 후보 수를 설정·개별 JSON에 남겼다. 원래 자리 5·7·8도 결과 확인 후 선정된 자리다.','',
      '그림 아래 비율의 분모는 사진 범위 안 해당 영역의 참조값이 있는 지붕 넓이다. 사진 전체의 비율이나 A 한 점을 영역 전체로 확대해 해석하지 않는다. 각 JSON에는 같은 영역·같은 검사 판단의 별도 집계와 패치 ID도 있다.','',
      '| 그림 | A 패치 | 사전 / 범주별 / 검사 기반 오차(cm) | 조건 충족 후보 수 |','|---|---|---|']
    for r in rows:
        f=r['focus'];e=r['focus_normal_error_cm']
        lines.append(f'| {r["id"]} | `{f["focus_patch_id"]}` | '+ ' / '.join(f'{x:+.2f}' for x in e)+f' | {f["eligible_count"]} |')
    lines += ['',
      'MVS의 원래 영역 분류는 원본 `mvs_a_e`에 기초한다. `mvs_p-gt_p`를 대신 써 영역 정의를 바꾸지 않았다. 참조값 일치는 자료 간 일치이며 독립적인 같은 표면·진실 검증을 추가한 것은 아니다. 다듬기 A에서 오차가 줄어도 영역 전체 정밀도 향상으로 일반화하지 않는다. 사진에서 보이는 이음선·돌출물·그늘을 실패 원인으로 단정하지 않는다.','',
      '## 점검과 재현','',
      '[제목 없는 시안 점검 답 전문](reviews/pilot_review.md)과 [보완본 점검 답 전문](reviews/final_review.md), [문제와 보완 기록](issues.md)을 보존했다. 검토자가 사례를 읽어낸 사실은 가독성 근거이며 과학적 성능 판정이 아니다.','',
      f'[수치·보존 검증](verification.json): **{v["passed"]}/{v["total"]} 통과**. 원본 {v["protected_files"]}개 파일의 해시 보존, 제공 NPZ와 A 원값 일치, 동일 패치 조건, 기존 사진 범위와 집계 분모, 단면 보존, 300 dpi PNG를 검사했다.','',
      '실행은 기존 `run_cpu.py`의 자원 보호 안에서 순차 처리했다. GPU 없음, CPU 2개, 컨테이너 4 GiB, 추가 swap 없음. 학습 후처리로 자원 잠금이 잡힌 동안 새 렌더링을 대기했다. 다른 작업의 프로세스나 파일은 변경하지 않았다.','',
      '재현 명령(저장소 루트, 기존 외부 입력과 Docker 이미지 필요):','',
      '```bash',
      'PYTHONDONTWRITEBYTECODE=1 python3 scripts/phd/main_regionfig_v2/run_cpu.py rep-draw python representative_draw.py 1',
      '# 같은 명령의 마지막 인수를 2~8로 바꿔 순서대로 실행',
      'PYTHONDONTWRITEBYTECODE=1 python3 scripts/phd/main_regionfig_v2/run_cpu.py rep-trace python representative_trace.py',
      'PYTHONDONTWRITEBYTECODE=1 python3 scripts/phd/main_regionfig_v2/run_cpu.py rep-verify python representative_verify.py',
      '```','',
      '설정은 먼저 잠갔으며 `representative_prepare.py`는 이미 잠긴 설정을 덮어쓰지 않는다. 기존 여덟 그림·보고서·단일 ZIP도 보존한다. 새 단일 ZIP은 기존 전달 파일에 새 대표 그림·설정·검토·검증을 추가한다. 원본 사진 전체·대형 학습 데이터는 포함하지 않아 외부 입력 없는 전체 재실행 묶음이라는 뜻은 아니다.','',
      f'기준 설정 SHA-256: `{design["base_config_sha256"]}`. [재작업 출처 기록](provenance.json).','']
    report='\n'.join(lines);assert len(report)<15000;(root/'대표그림_보고.md').write_text(report)
    cards=[]
    for r in rows:
        i=r['id'];title,sub=TITLES[i]
        cards.append(f'<article id="case{i}"><h2>{i}. {html.escape(title)}</h2><p>{html.escape(sub)}</p><a href="대표그림_{i}.png"><img src="미리보기_{i}.png" alt="{html.escape(sub)}" loading="lazy"></a><p><a href="대표그림_{i}.png">300 dpi 원본</a> · <a href="대표그림_{i}.json">동일 패치 수치</a></p></article>')
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>여덟 케이스 대표 그림</title><style>body{font:16px/1.65 sans-serif;color:#263542;background:#f6f7f8;margin:0}main{max-width:1500px;margin:auto;padding:24px}h1{margin-bottom:8px}nav{display:flex;gap:20px;flex-wrap:wrap}a{color:#196aab}article{background:white;padding:18px;margin:30px 0}img{display:block;width:100%;height:auto}h2{margin:0}p{margin:8px 0}</style><main><h1>여덟 케이스 대표 그림</h1><p>같은 A를 사진 → 검사 판단 → 제공 참조값 기준 판정 → 단면으로 따라갑니다. 결과는 학습 없는 손실 최소점이며 A는 결과 확인 후 고른 설명용 패치입니다.</p><nav>'''+''.join(f'<a href="#case{i}">{i}번</a>' for i in range(1,9))+'''</nav>'''+''.join(cards)+'''<p><a href="대표그림_보고.md">보고서</a> · <a href="verification.json">수치·원본 보존 검증</a></p></main></html>'''
    (root/'index.html').write_text(page)
    receipts=[];receipt_dir=root/'run_receipts';receipt_dir.mkdir(exist_ok=True)
    for p in sorted((PAY/'logs').glob('*.json')):
        receipt=load(p)
        if receipt.get('tag','').startswith('rep-') and receipt.get('status')!='RUNNING':
            shutil.copyfile(p,receipt_dir/p.name)
            log=p.with_suffix('.log')
            if log.is_file():shutil.copyfile(log,receipt_dir/log.name)
            receipts.append(dict(file=p.name,status=receipt['status'],sha256=sha(p)))
    dump(root/'runtime_receipts.json',dict(receipts=receipts,scientific_verdict=None))
    scripts={str(p):sha(p) for p in sorted(Path('/repo/scripts/phd/main_regionfig_v2').glob('*.py'))}
    source=dict(at=now(),base_commit=design['base_commit'],render_source_head=os.environ.get('JBGS_SOURCE_HEAD'),
      config_sha256=sha(CFG/rev/'design.json'),scripts_sha256=scripts,
      base_artifacts_preserved=True,figures=[dict(id=r['id'],sha256=r['figure_sha256']) for r in rows],
      report_characters=len(report),environment=environment(),scientific_verdict=None)
    dump(root/'provenance.json',source);print('REPORT',len(report),'characters; index and provenance complete')

if __name__=='__main__':main()
