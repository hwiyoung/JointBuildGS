from common import *
def main():
    times={p.stem:json.loads(p.read_text()) for p in (O/'timing').glob('*.json')}
    base=json.loads((O/'timing/first_region_partial.json').read_text())
    measured=base['first_region_subtotal_seconds']
    measured+=times['B0_b10_truth']['seconds']+times['B0_b10_ring']['seconds']
    # Full-region shared cloud/image costs are counted once per region, not per core.
    items=dict(first_region_measured_seconds=measured,remaining_two_regions_upper_estimate_seconds=2*measured*2,
               calibration_reconciliation_and_if_needed_B0_photo_repeat_seconds=600,
               tables_figures_single_verification_packaging_reserve_seconds=1800)
    total=sum(items.values());result=dict(at=now(),components=items,total_estimate_seconds=total,limit_seconds=21600,
          basis='B0 full production stages; remaining regions each at twice B0; no per-core multiplication of shared costs',
          status='PASS' if total<=21600 else 'STOP_TIME_ESTIMATE',scientific_verdict=None)
    dump(O/'timing/first_region_gate.json',result)
    progress(f'첫 지역 본 셈 합계 {measured:.1f}초. 전체 어림 {total/3600:.3f}시간: 첫 지역 + 남은 두 지역 각 첫 지역의 2배 + 보정 재반영 600초 + 표·그림·한 번 검산·묶음 1800초. 공통 읽기 비용은 지역마다 한 번. 6시간 미만, 계속.')
    assert total<=21600;print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
