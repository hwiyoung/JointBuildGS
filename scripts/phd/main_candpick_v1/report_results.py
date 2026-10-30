"""Evidence-led Korean report; numeric criteria are not a scientific verdict."""
import json
from pathlib import Path
from input_audit import sha
from result_io import save

DOC = Path('/docs')


def percent(value): return '확인 불가' if value is None else f'{100 * value:.2f}%'
def pp(value): return '확인 불가' if value is None else f'{value:+.2f}%p'
def flag(value): return '확인 불가' if value is None else '충족' if value else '미충족'


def main():
    root = DOC / 'results'
    status = json.loads((root / 'status.json').read_text())
    criteria = json.loads((root / 'criteria.json').read_text())['rows']
    outcomes = json.loads((root / 'outcomes.json').read_text())['rows']
    photos = json.loads((root / 'photo_error.json').read_text())['rows']
    representatives = json.loads((root / 'representative_outcomes.json').read_text())['rows']
    config = json.loads(Path('/config/candpick_v1.json').read_text())
    n = status['completed_count']
    full = [r for r in criteria if r['sh_degree'] == 3 and r['subset'] == 'all' and r['side'] == 'all']
    tested1 = [r for r in full if r['criterion1_equal_ge70pct'] is not None]
    passed1 = sum(bool(r['criterion1_equal_ge70pct']) for r in tested1)
    tested2 = [r for r in full if r['criterion2_wrong_drop_le10pp'] is not None]
    passed2 = sum(bool(r['criterion2_wrong_drop_le10pp']) for r in tested2)
    tested3 = [r['criterion3_' + s + '_le20pct'] for r in full for s in ['equal', 'right', 'wrong'] if r['criterion3_' + s + '_le20pct'] is not None]
    lines = ['# 두 후보를 함께 두면 사진이 맞는 쪽을 남기는가', '',
        f'**학습 {n}/24판 완료.** 묶음 가·SH3의 앞뒤 전체에서 같은 출발의 맞게 남음 ≥70%는 채점된 {len(tested1)}경우 중 {passed1}경우, 틀린 출발의 하락 ≤10%p는 비교 가능한 {len(tested2)}경우 중 {passed2}경우가 충족했다.', '',
        f'같은 범위에서 둘 다 남음+둘 다 사라짐 ≤20%는 채점된 SH3 {len(tested3)}판 중 {sum(bool(v) for v in tested3)}판이 충족했다. 앞뒤를 나눈 결과는 아래에서 별도로 대조한다.', '',
        '이는 발주에서 미리 정한 수치 기준과의 대조다. 방법 채택·기각과 연구적 판정은 사람이 한다. `scientific_verdict: null`.', '',
        f"자료 기준: {status['at']}. 설정 SHA-256: `{status['config_sha256']}`.", '',
        '## 핵심 비교: 사진 정보가 있는 자리', '',
        '모든 비율의 분모는 해당 경우·묶음 가·앞뒤 범위에 속하는 원본 지붕 패치 넓이의 합이다. 표의 출발은 맞는 후보/틀린 후보의 초기 불투명도를 뜻한다(맞음 0.9/0.1, 틀림 0.1/0.9, 같음 0.5/0.5).', '']
    for degree in [3, 0]:
        lines += [f'### 후보 색 SH{degree}', '',
            '| 경우 | 같은 출발: 맞게 남음 | 맞는 출발: 맞게 남음 | 틀린 출발: 맞게 남음 | 틀림−맞음 | 같은 출발: 둘 다 남음+사라짐 |',
            '|---|---:|---:|---:|---:|---:|']
        for r in criteria:
            if r['sh_degree'] == degree and r['subset'] == 'all' and r['side'] == 'all':
                lines.append(f"| {r['unit']} | {percent(r['equal_right_only'])} | {percent(r['right_right_only'])} | {percent(r['wrong_right_only'])} | {pp(r['wrong_minus_right_pp'])} | {percent(r['equal_both_plus_neither'])} |")
        lines += ['']
    lines += ['SH0에서도 방향과 무관한 DC 색은 학습한다. 바탕 장면은 두 색 조건 모두 원래 SH3를 유지한다. 기준 3(둘 다 남음+둘 다 사라짐 ≤20%)은 같은·맞는·틀린 출발 각각 대조하며, 모든 값은 [기준 원표](results/criteria.csv)에 있다. ‘둘 다 사라짐’은 후보별 평균 불투명도가 모두 0.5 미만이라는 분류다. 가우시안이 겹쳐 그려지므로 렌더 기여가 완전히 0이라는 뜻은 아니다.', '',
        '### 맞는 후보가 앞인지 뒤인지', '',
        '| 경우 | 후보 색 | 맞는 후보 위치 | 같은 출발: 맞게 남음 | 틀림−맞음 | 기준 1 | 기준 2 |',
        '|---|---|---|---:|---:|---|---|']
    for r in criteria:
        if r['subset'] == 'all' and r['side'] != 'all':
            lines.append(f"| {r['unit']} | SH{r['sh_degree']} | {'앞' if r['side'] == 'front' else '뒤'} | {percent(r['equal_right_only'])} | {pp(r['wrong_minus_right_pp'])} | {flag(r['criterion1_equal_ge70pct'])} | {flag(r['criterion2_wrong_drop_le10pp'])} |")
    lines += ['', '### 가림 30% 초과 점만 본 비교', '',
        '| 경우 | 묶음 가의 점 / 넓이 | 같은 출발 SH3 | 맞는 출발 SH3 | 틀린 출발 SH3 |',
        '|---|---:|---:|---:|---:|']
    for r in criteria:
        if r['sh_degree'] == 3 and r['subset'] == 'occlusion_over_30pct' and r['side'] == 'all':
            example = next((x for x in outcomes if x['unit'] == r['unit'] and x['group'] == 'a' and x['subset'] == r['subset'] and x['side'] == 'all'), None)
            count = f"{example['points']:,} / {example['area_m2']:.2f} m²" if example else '확인 불가'
            lines.append(f"| {r['unit']} | {count} | {percent(r['equal_right_only'])} | {percent(r['right_right_only'])} | {percent(r['wrong_right_only'])} |")
    lines += ['', '가림은 두 후보 면을 보는 모든 학습 사진의 화소 관측을 합친 비율이다. 바탕 투과율 <0.5인 관측이 30%를 넘는 점을 표시했다. 이 점들을 학습에서 빼지 않았다. 후보 앞뒤 각각의 분자·분모도 보존했다.', '',
        '## 전체 정량 결과와 사진 오차', '',
        '[결과 표 1·3](results/outcomes.csv)은 네 경우 × 가/나/다 × 앞/뒤/전체 × 6판을 모두 담는다. 네 결과의 넓이 비율과 건물별 넓이 비율의 중앙값, 건물 수를 함께 제공한다. 한 건물이 여러 층에 걸리면 각 층에서 따로 계산하므로 건물 수를 단순 합산하지 않는다.', '',
        '| 판 | 고정 후보 화소 L1: 시작 | 끝 | 변화 | 앞 5장 PSNR: 시작→끝 (dB) |',
        '|---|---:|---:|---:|---:|']
    for r in photos:
        lines.append(f"| {r['arm']} | {r['candidate_l1_start']:.5f} | {r['candidate_l1_end']:.5f} | {r['candidate_l1_delta']:+.5f} | {r['first_five_psnr_start']:.3f} → {r['first_five_psnr_end']:.3f} |")
    lines += ['', '시작·끝 L1은 모든 학습 사진의 동일한 후보 영향영역 화소에서 계산했다. 100회 간격 곡선의 사진 오차는 미리 고정한 후보 영역이 큰 5개 사진을 쓴다. 학습 PSNR은 발주대로 정렬된 앞 5장이므로 후보가 보이지 않는 사진이면 값이 변하지 않을 수 있다. 사진 오차 감소를 맞는 후보 선택으로 대신 판정하지 않는다.', '',
        '### 불투명도 곡선', '']
    for unit in config['units']:
        p = DOC / 'figures' / (unit + '_opacity_curves.png')
        if p.exists():
            lines += [f'![{unit} 불투명도 곡선](figures/{p.name})', '',
                f'[{unit} 넓이 구성 그림](figures/{unit}_outcomes_all.png) · [가림 30% 초과 그림](figures/{unit}_outcomes_occlusion_over_30pct.png)', '']
    lines += ['## 고정 대표 자리', '', '대표 자리는 학습 전 고정했다. 요청 낙엽 지붕의 적격 덩어리는 없어 같은 조건의 대체 자리를 사용했다. B173 유리 채광창 예시는 적격 1–3m² 덩어리가 없어 확인 불가로 남겼다.', '']
    for name, label in [('B173_wing', 'B173 날개'), ('R1_stairs', 'R1 계단 지붕'), ('leaf_flat_roof', '낙엽 지붕 요청의 대체 자리')]:
        lines += [f'### {label}', '']
        chosen = [r for r in representatives if r['representative'] == name]
        if chosen:
            lines += ['출발 틀림의 고정 대표 자리 전체 점을 센 결과다. 아래 단면은 중앙 띠만 표시하므로 이 표와 점 수가 다를 수 있다.', '',
                '| 후보 색 | 대표 점 | 맞게 남음 | 틀리게 남음 | 둘 다 남음 | 둘 다 사라짐 | 맞게 남은 넓이 |',
                '|---|---:|---:|---:|---:|---:|---:|']
            for r in chosen:
                lines.append(f"| SH{r['sh_degree']} | {r['points']} | {r['right_only_points']} | {r['wrong_only_points']} | {r['both_points']} | {r['neither_points']} | {percent(r['right_only_area_fraction'])} |")
            lines += ['']
        for suffix, caption in [('photo_overlay_1', '실제 사진과 고정 시험 자리'), ('sections', '출발 틀림의 단면: 0·500·3,000회'),
                                ('render_comparison_1', '실제 사진·시작·끝 렌더'), ('3d_sh3', 'SH3 후보 불투명도의 세 시점')]:
            p = DOC / 'figures/representatives' / (name + '_' + suffix + '.png')
            if p.exists(): lines += [f'![{caption}](figures/representatives/{p.name})', '']
        extras = []
        for suffix, label in [('3d_sh0', 'SH0 세 시점'), ('render_comparison_2', '관측 사진 2'), ('render_comparison_3', '관측 사진 3')]:
            p = DOC / 'figures/representatives' / (name + '_' + suffix + '.png')
            if p.exists(): extras.append(f'[{label}](figures/representatives/{p.name})')
        if extras: lines += [' · '.join(extras), '']
    lines += ['## 통제·검증과 해석 범위', '',
        '- 자리: PHOTOCHECK-v1 최종 점·패치. 학습·채점은 0부터 4번 열(δ=0.10, 최소 점수 0.3). 1단계 값은 자리 표에만 사용했다.',
        '- 후보의 위치·방향·크기와 정리 뒤 바탕 전체는 고정했다. 완료 판은 메모리 텐서의 전후 SHA-256 일치를 확인했다.',
        '- 손실은 전체 학습 사진의 0.8 L1 + 0.2(1−SSIM). 참값은 자리·묶음·초기 불투명도·채점에만 사용했다. 깊이 손실·밀도 제어·불투명도 재설정·정리를 사용하지 않았다.',
        '- 렌더는 gsplat 1.4.0이며 상속 GeoGS 렌더러와의 픽셀 동등성을 주장하지 않는다. 모든 판은 같은 gsplat 구현을 썼다.',
        '- 최초 50cm 칸 밖 동일 검사는 정상적인 가우시안 꼬리 때문에 실패했다. [후속 해석](render_scope_resolution.md)에 따라 실제 렌더 영향영역 밖 불변을 확인하고 학습했다. 이전 실패와 첫 ZIP은 보존했다.',
        '- 실험은 고정한 개발 지역·적격 지붕 점·seed 0의 진단이다. 다른 지역·벽·다른 난수 씨앗의 결과나 통계적 일반화를 계산하지 않았다.', '',
        '[독립 재계산 검증](results/validation.json) · [학습 설정 잠금](training_lock.json) · [실행 이슈](issues.md) · [첫 자리 표](tables/places.csv)', '',
        '원본 사진과 큰 바탕 모델은 외부 입력 저장소에 보존한다. 결과 묶음은 점별 후보 상태와 집계 재계산에 필요한 자료를 포함하며, 전체 학습 재실행에는 기록된 외부 입력과 실행 환경이 필요하다.', '',
        'scientific_verdict: null', '']
    (DOC / 'result_report.md').write_text('\n'.join(lines))
    save(root / 'report_sources.json', dict(source_cutoff=status['at'],
        hashes={p.name: sha(p) for p in [root / 'status.json', root / 'outcomes.json', root / 'criteria.json', root / 'photo_error.json', root / 'representative_outcomes.json']},
        report_sha256=sha(DOC / 'result_report.md'), script_sha256=sha(__file__), scientific_verdict=None))
    print('Report updated for', n, 'complete arms')


if __name__ == '__main__': main()
