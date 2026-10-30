"""Create inspectable stage-one tables; preserve failed gates and non-results."""
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
from input_audit import PC, sha
from prepare_places import save

OUT, DOC = Path('/out'), Path('/docs')
UNITS = ['B173_ALS', 'R1_LoD2', 'B173_LoD2', 'R1_ALS']


def read(path):
    return json.loads(path.read_text())


def csv_write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader(); w.writerows(rows)


def main():
    original = {}
    for prior in ['ALS', 'LoD2']:
        original[prior] = {}
        for p in sorted((PC / 'points').glob('*__' + prior + '.npz')):
            with np.load(p) as z:
                assert not z['holdout'].any()
                original[prior].update({str(i): j for i, j in zip(z['point_id'], z['judgment'])})
    rows, groups = [], []
    (OUT / 'validation').mkdir(exist_ok=True)
    for unit in UNITS:
        scene = read(DOC / 'scenes' / (unit + '.json'))
        pre = read(DOC / 'preflight' / (unit + '_all_views.json'))
        grad = read(DOC / 'preflight' / (unit + '_variants.json'))
        occ = read(DOC / 'occlusion' / (unit + '.json'))
        with np.load(OUT / 'places' / (unit + '.npz')) as z:
            d = {k: z[k] for k in z.files}
        with np.load(OUT / 'occlusion' / unit / 'points.npz') as z:
            o = {k: z[k] for k in z.files}
        assert np.array_equal(d['point_id'], o['point_id'])
        assert sha(OUT / 'occlusion' / unit / 'points.npz') == occ['payload_sha256']
        j = np.asarray([original[unit.split('_')[1]][str(i)] for i in d['point_id']])
        assert np.array_equal(j[:, 4], d['judgment'])
        target = OUT / 'validation' / (unit + '_photo_judgments.npz')
        assert not target.exists(), target
        np.savez_compressed(target, point_id=d['point_id'], judgment=j)
        high = o['over_30pct']; n = len(high)
        outside = pre['outside']
        row = dict(unit=unit, points=n, area_m2=float(d['area'].sum()),
            original_gaussians=scene['original_count'], deleted_evidence=scene['deleted_evidence'],
            deleted_columns_additional=scene['deleted_columns_after_evidence'], remaining=scene['remaining'],
            occlusion_over_30pct_points=int(high.sum()), occlusion_over_30pct_area_m2=float(d['area'][high].sum()),
            occlusion_over_30pct_point_percent=100 * float(high.mean()),
            occlusion_unavailable_points=occ['unavailable_points'], train_views=pre['tested_views'],
            views_with_outside_cell_changes=sum(x['changed_outside_pixels'] > 0 for x in outside),
            outside_cell_changed_pixel_observations=sum(x['changed_outside_pixels'] for x in outside),
            outside_cell_max_abs_rgb=max(x['max_abs_outside_rgb'] or 0 for x in outside),
            outside_photo_psnr_delta_min_db=min(x['outside_photo_psnr_delta_db'] or 0 for x in outside),
            outside_photo_psnr_delta_max_db=max(x['outside_photo_psnr_delta_db'] or 0 for x in outside),
            strict_cell_status=pre['strict_cell_status'], actual_support_status=pre['actual_support_status'],
            changed_beyond_actual_support=sum(x['changed_beyond_actual_splat_support'] for x in outside),
            gradient_variants_status=grad['status'], gradient_variants=len(grad['checks']),
            optimizer_steps=0)
        rows.append(row)
        per_point = []
        for i in range(n):
            per_point.append(dict(point_id=str(d['point_id'][i]), building=str(d['building'][i]),
                group=str(d['group'][i]), side=str(d['side'][i]), right=str(d['right'][i]), area_m2=float(d['area'][i]),
                observed_prior_pixels=int(o['observed_pixels'][i, 0]), observed_image_pixels=int(o['observed_pixels'][i, 1]),
                occluded_prior_pixels=int(o['occluded_pixels'][i, 0]), occluded_image_pixels=int(o['occluded_pixels'][i, 1]),
                occluded_fraction=float(o['occluded_fraction'][i]) if np.isfinite(o['occluded_fraction'][i]) else None,
                over_30pct=bool(high[i])))
        csv_write(OUT / 'occlusion' / unit / 'points.csv', per_point)
        for right in ['image', 'prior']:
            for group in ['a', 'b', 'c']:
                for side in ['front', 'back']:
                    m = (d['right'] == right) & (d['group'] == group) & (d['side'] == side)
                    groups.append(dict(unit=unit, right=right, group=group, side=side,
                        points=int(m.sum()), area_m2=float(d['area'][m].sum()),
                        over_30pct_points=int((m & high).sum()), over_30pct_area_m2=float(d['area'][m & high].sum()),
                        unavailable_points=int((m & ~np.isfinite(o['occluded_fraction'])).sum())))
    report = dict(task_id='PHD-MAIN-CANDPICK-v1', at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        status='STOP_PREFLIGHT', failed_gate='3.3_OUTSIDE_TRIAL_CELL_IDENTITY',
        pending_decision='Definition of outside trial place; actual Gaussian support is diagnostic only until user resolves it.',
        training_config_locked=False, completed_training_arms=0, designed_training_arms=24,
        scientific_verdict=None, rows=rows,
        note='Pixel observations sum across views, not unique physical pixels. Rendering tested wrong/SH3; gradients tested all six variants per case.',
        script_sha256=sha(__file__))
    save(DOC / 'stage1_summary.json', report)
    csv_write(DOC / 'tables/scene_preflight.csv', rows)
    csv_write(DOC / 'tables/occlusion_groups.csv', groups)
    text = ['# 장면 정리·가림·사전 점검', '',
        '자리 표와 장면 생성·가림 계산을 마쳤다. 발주문 3.3의 시험 자리 밖 동일 검사는 50cm 칸 기준에서 실패했다. 학습은 **0/24판**이며 결과 채점은 없다. `scientific_verdict: null`.', '',
        '| 경우 | 근거 밖 제거 | 칸 기둥 추가 제거 | 남은 바탕 | 가림 >30% 점 / 전체 |',
        '|---|---:|---:|---:|---:|']
    for r in rows:
        text.append(f"| {r['unit']} | {r['deleted_evidence']:,} | {r['deleted_columns_additional']:,} | {r['remaining']:,} | {r['occlusion_over_30pct_points']:,} / {r['points']:,} |")
    text += ['', '가림은 학습 사진 전체에서 사전 정보·영상 두 후보의 50cm 면을 보는 화소 관측을 합쳐 계산했다. 후보 면 앞 바탕의 투과율 <0.5인 관측 비율이다. 각 후보의 분자·분모도 별도로 보존했다. >30% 점은 제외하지 않으며 별도 결과 표를 위한 표시다. 관측 불가 점은 네 경우 모두 0개다.', '',
        '전체 1,072개 경우별 학습 뷰를 검사했다(B173 203장 × 두 사전 정보, R1 333장 × 두 사전 정보). 이는 서로 다른 사진 1,072장을 뜻하지 않는다.', '',
        '| 경우 | 50cm 칸 밖 변화가 있는 뷰 | 실제 후보 렌더 영향영역 밖 변화 | 기울기 6설정 |',
        '|---|---:|---:|---|']
    for r in rows:
        text.append(f"| {r['unit']} | {r['views_with_outside_cell_changes']} / {r['train_views']} | {r['changed_beyond_actual_support']} | {r['gradient_variants_status']} |")
    text += ['', '칸을 덮는 가우시안의 꼬리가 칸 밖에도 그려진다. 최초 B173-ALS 사진에서 칸 밖 3,523화소가 달라졌고, 정리 바탕 대비 동일성 PSNR은 55.2113dB, 실제 사진에 대한 칸 밖 PSNR 변화는 −0.00036493dB였다. 칸 밖의 변화 화소 수·최대 RGB 차·PSNR 변화는 모든 뷰의 JSON에 보존했다.', '',
        '실제 렌더 영향영역 밖은 네 경우 모두 변화 0이다. 이 진단을 원래 50cm 칸 기준의 통과로 바꾸지 않았다. 판정 범위에 대한 사용자 답을 받기 전에는 `candpick_v1.json` 학습 설정 잠금과 학습을 진행하지 않는다.', '',
        '바탕 전체와 후보 자리·방향·크기는 requires_grad=False이고 기울기는 생성되지 않았다(값 0). 24개 초기 설정의 미분 점검에서 불투명도와 DC 색에 유한한 비영 기울기가 있었고, SH3에서는 높은 차수 색에도 있었다. SH0의 높은 차수는 고정이며 기울기가 없다. 어느 점검에서도 optimizer.step을 실행하지 않았다.', '',
        '렌더는 gsplat 1.4.0의 rasterization_2dgs를 사용했다. 상속 모델의 PLY 값은 그대로 읽으며 바탕 색은 후보 SH0 조건에서도 SH3를 유지한다. 이는 기존 GeoGS 렌더러와의 픽셀 동일성 검증을 뜻하지 않는다. 카메라 중심은 두 렌더러의 화소 중심 관례 차이에 맞춰 +0.5 보정했다.', '',
        '가림용 CUDA 투과율 계산은 네 경우의 앞 5장, 장당 2,048화소에서 gsplat 전체 배경 알파와 대조했다. 최대 차는 2e-5 허용값 안이다. 이는 구현 대조이며 참값을 이용한 가림 정확도 평가가 아니다.', '',
        '대표 낙엽 지붕은 대체 자리로 잠갔고 B173 유리 채광창 예시는 확인 불가다. 학습 결과에 따른 대표 자리 재선택은 하지 않았다.', '']
    (DOC / 'stage1_report.md').write_text('\n'.join(text))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__': main()
