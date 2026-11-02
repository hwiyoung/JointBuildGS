import json,shutil
from preflight import C,D,O,Path,dump,sha,now

def main():
    rev=C/'revisions/r1';assert not rev.exists();rev.mkdir(parents=True)
    for name in ['judgecheck_v1.json','judgecheck_v1.reply1.lock.json']:shutil.copy2(C/name,rev/name)
    p=C/'judgecheck_v1.json';old=sha(p);cfg=json.loads(p.read_text());at=now()
    amendment=dict(at=at,reason='CPU/GPU full-curve parity failed at a very low-texture sample. Preserve the same geometry, views, masks, sampling, NCC and tolerances; use float64 interpolation and NCC accumulation.',
        previous_config_sha256=old,previous_score_source_sha256=sha(O/'r1/photo_benchmark/revisions/r0/photo_score.py'),
        new_score_source_sha256=sha(Path(__file__).parent/'photo_score.py'),
        diagnosis_sha256=sha(O/'r1/photo_benchmark/revisions/r0/parity_diagnosis.json'),
        changed='new corrected-photo numerical precision only; inherited curves never recomputed',
        heldout_values_opened=False,GT_used=False,scientific_verdict=None)
    cfg['amendments'].append(amendment);cfg['photos']['corrected_photo_numeric_precision']='float64 interpolation and NCC accumulation; inherited grayscale unchanged'
    dump(p,cfg);dump(C/'judgecheck_v1.reply1.lock.json',dict(at=at,config_sha256=sha(p),
        authority_sha256=sha(C/'reply_1.txt'),previous_lock='revisions/r1/judgecheck_v1.reply1.lock.json',
        before_resumed_calculation=False,before_corrected_photo_precision_rerun=True,scientific_verdict=None))
    dump(C/'photo_precision_amendment.reply1.json',amendment)
    with (D/'issues.md').open('a') as f:f.write(f'\n- JC-006 — REPAIR_IN_PROGRESS — {at}: 처음 200점의 전체 곡선 CPU/GPU 최대 차이 0.0078153163으로 정밀도 검사 실패. 최고 점수 차이는 2.98e-7이었다. 낮은 무늬의 정규화에서 생긴 수치 차이 가설을 확인하기 위해 보간·NCC를 float64로 바꾸고 같은 200점을 재측정한다. 허용 오차를 완화하지 않았다. 앞 코드·결과·설정은 보존했다.\n')
    print('NUMERIC_AMENDMENT',sha(p))

if __name__=='__main__':main()
