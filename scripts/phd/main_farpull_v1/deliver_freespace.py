"""Immutable preflight ZIP; SHA/CRC is integrity, not a scientific verdict."""
import zipfile
from runtime import *


def report():
    root=OUT/'freespace_v1';doc=DOC/'freespace_v1'
    result=read(root/'preflight.json');unit=read(root/'unit.json');off=read(root/'off_ten.json')
    assert unit['status']=='PASS'
    rank=result['ranks']['roof_or_wall'];cal=result['calibration']
    stop=result['status']!='PASS'
    fmt=lambda x:'확인 불가' if x is None else f'{x:.8g}'
    lines=['# 빈 공간 손실 · 학습 전 점검','',
        '**'+('사전 관문 미통과 — 새 학습을 시작하지 않았다.' if stop else '사전 관문 통과 — 학습 무게를 잠갔다.')+'**','',
        f"B173 판 4의 30,000회 저장 모델과 학습 사진 {result['views']}장 전체를 검사했다. 새 학습·Adam 갱신은 0회다.",
        f"뜬 가우시안의 압력이 정상 지붕·벽보다 클 확률은 **{rank['strict']:.6f}**다. 발주 기준은 **0.8 이상**이다.",
        '','[이 발주에서 냄]. scientific_verdict: null.','',
        f"off 숫자 점검: **{off['status']}**, 첫 열 장 최대 상대차 **{off['maximum_relative_difference']:.8g}** (기준 1e-6).",
        f"기준 손실끼리 반복한 대조 역전파도 최대 {max(max(r['baseline_repeat_relative_l2'].values()) for r in off['rows']):.8g}의 상대차를 보였다. 같은 계산 그래프에서 off−base의 기울기는 정확히 0이다. 이는 독립 CUDA 누적의 재현 차이와 스위치 효과를 구분하는 기록이며, 발주의 수치 기준을 통과로 바꾸지 않았다.",'',
        '| 비교 | 엄격한 순위 확률 P(뜬 P > 정상 P) | 동률 비율 | 뜬 가우시안 | 비교 가우시안 |',
        '|---|---:|---:|---:|---:|']
    labels={'roof':'지붕','wall':'벽','roof_or_wall':'지붕·벽 합집합'}
    for name,r in result['ranks'].items():lines.append(f"| {labels[name]} | {fmt(r['strict'])} | {fmt(r['tie_fraction'])} | {r['n_a']:,} | {r['n_b']:,} |")
    lines+=['','확률은 모든 가우시안 쌍을 같은 무게로 비교했다. P가 같은 쌍은 ‘더 크다’에 포함하지 않는다. 동률에 절반을 주는 순위 확률은 JSON에 별도로 기록했다.','',
        '| 무리 | 수 | P 50% | P 90% | P 99% | P > 0 비율 |','|---|---:|---:|---:|---:|---:|']
    for r in result['groups']:lines.append('| '+' | '.join([r['group'],str(r['count']),*[fmt(r[k]) for k in ['p50','p90','p99','positive_fraction']]])+' |')
    lines+=['','P는 203장에 걸친 Σ G·w·f의 합이다. 평균 화소 손실의 색 기울기에 화소 수와 f를 곱해 가우시안별 압력을 복원했다. 원래 diagnostic_labels.npz의 표식과 체크포인트 가우시안 순서를 일치 확인했다.','',
        '| 칸 | 대응 화소 수 | G > 0.5 화소 수 | 비율 |','|---|---:|---:|---:|']
    for r in read(doc/'cells.json')['rows']:lines.append(f"| {r['cell']} | {r['pixels']:,} | {r['G_gt_half']:,} | {fmt(r['fraction'])} |")
    lines+=['','분모는 기존 패치 대응표에서 그 칸에 대응하는 모든 화소다. 자료가 없는 화소는 G=0이다. 칸은 보고에만 쓰며 손실에 쓰지 않았다.','',
        '| 무게 계산 | 값 |','|---|---:|',f"| 사진 기울기 중앙값 a | {fmt(cal['a'])} |",f"| 빈 공간 기울기 중앙값 b | {fmt(cal['b'])} |",
        f"| λ₁ = a/b | {fmt(cal['lambda1'])} |",f"| λ₄ = 4a/b | {fmt(cal['lambda4'])} |",'',
        '집계 순서의 명시가 없어 계산 전에 다음 규칙을 가정하여 잠갔다: 가우시안마다 203장의 |∂L/∂opacity_logit|을 평균한 다음 뜬 가우시안 13,934개의 중앙값을 취한다. 사진 손실은 판 4와 같은 L1+SSIM이며 λ_free=1의 손실과 비교했다. 사진×가우시안을 한꺼번에 펼친 중앙값은 a=b=0이므로 그 방식의 비율은 확인 불가다. 위 두 λ는 실제 학습에 사용하지 않았다.',
        '','| 단위 점검 | 결과 |','|---|---|','| 가짜 자료: 한 자료 가까움 / 둘 다 멂 / 자료 없음 | PASS |',
        '| 손계산 합성 0.284와 렌더 | '+fmt(unit['compositing']['actual'])+' |',
        '| 위치·크기·방향 기울기 | 정확히 0 |','| 불투명도 기울기 | 있음 |',
        f"| off 첫 10회 손실·기울기 상대차 | 최대 {off['maximum_relative_difference']:.6g} |",'',
        'off 점검은 초기 모델에서 씨앗 0이 고른 첫 열 장의 손실을 두 번 역전파해 비교했다. Adam을 갱신하는 10회 학습은 하지 않았다. off는 손실 텐서를 그대로 반환하고 렌더·난수·밀도 제어를 추가 호출하지 않는다.',
        f"저장 모델 색 렌더의 사진별 PSNR 최대 재현 차이: {result['max_psnr_replay_difference_db']:.8g} dB (허용 0.1 dB).",'',
        '중앙 깊이는 기존 렌더러의 allmap[5]를 읽었다. 기존 혼합 우도 손실의 기대 깊이 계산은 바꾸지 않았다. 자료 지도·σ·V·가용 화소는 기존 lt_losses와 같다. 별도의 깊이 자료를 만들지 않았다.',
        '기존 lt_losses는 유효 prior 깊이·패치 대응이 있는 화소에서만 MVS 항도 계산한다. 이 가용성 규칙을 그대로 재사용했으며, prior 대응 없이 MVS만 있는 곳에 σ나 V를 새로 배정하지 않았다.',
        '',
        '미분식의 추가 관찰: F의 투과율 w도 불투명도에 의존하므로, 이 식만으로 모든 불투명도가 낮아진다고 보장할 수 없다. 손계산 장면에서 앞 조각의 f=0.2, 뒤 조각의 f=0.8, 뒤 불투명도=0.4이면 ∂F/∂앞 불투명도=0.2−0.4×0.8=−0.12다. 손실을 줄이는 갱신이 앞 조각의 불투명도를 올릴 수 있다. 발주의 식에 별도 기울기 절단·부호 제한을 추가하지 않았고, 위치·크기·방향만 차단했다.',
        '','사례 그림은 학습 사진 / G / F 순서다. 밝은 값은 해당 지도가 켜진 부분이다.','']
    for case in ['B173-날개','B173-뜬면-1','B173-뜬면-2']:lines+=['![사진·G·F](figures/'+case+'.png)','']
    lines+=['그림 관찰: 날개 사진에서는 G가 넓게 꺼져 있고 F는 가는 띠와 가장자리 일부에 켜진다. 뜬면-1은 가운데 큰 영역에서 G와 F가 함께 켜진다. 뜬면-2는 아래쪽 덩어리와 지붕 경계에서 켜진 부분이 보인다. 세 사례 전체에서 덮개에만 켜지고 보존 영역에는 모두 꺼진다는 시각적 통과를 선언하지 않는다. 칸 2의 G>0.5 비율은 3.8856%다. 사람의 최종 시각 판정은 받지 않았다.','',
        '기존 B0 학습과 이미 시작했던 후처리 자식 프로세스는 정상 종료까지 보존했다. 이후 미시작 R1 다시점·기존 잔여 판을 시작하는 스케줄러만 종료하여 GPU·TSDF 잠금을 해제했다. 후처리의 빠진 호스트 영수증은 Linux 자식 종료 상태 0에서 복구했으며 정확한 시작·종료 시각은 확인 불가로 남겼다. 실행 중인 CPU 진단과 MESHPATCH 계산에는 종료 신호를 보내지 않았다.','',
        '학습 및 핵심 채점: '+('NOT_RUN_PREFLIGHT_GATE. fs1·fs4·R1 모델, 새 메시, 새 patch_z는 없다. 없는 결과를 0이나 성공으로 표시하지 않는다.' if stop else '별도 학습·후처리·채점 필요. 이 사전 검사 통과는 성능 기준 통과가 아니다.'),'',
        '묶음에 포함된 압력·기울기 배열로 분위수·순위 확률·무게는 다시 계산할 수 있다. 원본 대형 모델과 203장 영상은 포함하지 않으므로 새 렌더는 외부 원본이 필요하다. CRC·SHA-256은 파일 무결성을 확인하며 과학적 타당성이나 사람의 시각 판정을 뜻하지 않는다.','']
    (doc/'보고.md').write_text('\n'.join(lines))
    progress='\n'.join(lines[:11])+f"\n\nλ₁={fmt(cal['lambda1'])}, λ₄={fmt(cal['lambda4'])}. 집계 가정은 보고.md에 명시했다.\n\n"
    progress+='학습: '+('NOT_RUN_PREFLIGHT_GATE' if stop else '사전 관문 통과, 별도 학습 필요')+'\n'
    progress+='R1 다시점·미시작 잔여 판은 보류. 기존 실행 중이던 B0 학습·후처리 완료를 보존한 뒤 스케줄러만 종료했다.\n'
    (doc/'진행.md').write_text(progress)
    save(doc/'status.json',dict(at=now(),status=result['status'],new_training='NOT_RUN_PREFLIGHT_GATE' if stop else 'AUTHORIZED_AFTER_LOCK',
        ranks=result['ranks'],calibration=cal,scientific_verdict=None))
    p=CFG/'farpull_v1_freespace_lambda_v1.json'
    if not p.exists():
        save(p,dict(at=now(),calibration=cal,rank=result['ranks'],unit_status=off['status'],training_allowed=not stop,
            source_preflight_sha256=sha(root/'preflight.json'),scientific_verdict=None),True)
        save(p.with_suffix('.lock.json'),dict(at=now(),sha256=sha(p),scientific_verdict=None),True)
    # Preserve earlier task progress below a dated additive result section.
    p=DOC/'진행.md';p.write_text('# 빈 공간 사전 검사 · '+now()+'\n\n'+progress+'\n---\n\n'+p.read_text())
    p=DOC/'progress.md'
    if '빈 공간 사전 검사 · 203장' not in p.read_text():
        p.write_text('# 빈 공간 사전 검사 · 203장\n\n'+progress+'\n상세: [보고](freespace_v1/보고.md)\n\n---\n\n'+p.read_text())
    return result


def package():
    result=report();at=datetime.now(ZoneInfo('Asia/Seoul'));root=OUT/'freespace_v1';doc=DOC/'freespace_v1'
    members={}
    for p in doc.rglob('*'):
        if p.is_file() and p.name!='delivery.json' and not p.name.endswith('.receipt.json'):
            members[str(p.relative_to(doc))]=p.read_bytes()
    for name in ['unit.json','off_ten.json','preflight.json','views.json','pressure_and_gradients.npz','implementation_lock.json','legacy_scheduler_yield.json']:
        p=root/name
        if p.exists():members['evidence/'+name]=p.read_bytes()
    for p in root.glob('*_maps.npz'):members['evidence/'+p.name]=p.read_bytes()
    for p in [*root.glob('implementation_lock*.json'),root/'off_failure_1.json',root/'legacy_scheduler_retired.json']:
        if p.exists():members['evidence/'+p.name]=p.read_bytes()
    for p in (root/'execution').rglob('*'):
        if p.is_file() and p.name in ['command.json','receipt.json','run.log']:members['execution/'+str(p.relative_to(root/'execution'))]=p.read_bytes()
    for p in [CFG/'farpull_v1_freespace_v1.json',CFG/'farpull_v1_freespace_v1.lock.json',DOC/'request/freespace_v1_order.md',
              CFG/'farpull_v1_freespace_lambda_v1.json',CFG/'farpull_v1_freespace_lambda_v1.lock.json',
              *SCRIPTS.glob('*freespace*.py'),REPO/'src/phd/forks/GeoGS-conf-guided-v1-r18/jbgs_freespace.py']:
        members[str(p.relative_to(REPO))]=p.read_bytes()
    members['SHA256SUMS']=''.join(hashlib.sha256(b).hexdigest()+'  '+name+'\n' for name,b in sorted(members.items())).encode()
    dest=OUT/'packages'/f'PHD-MAIN-FARPULL-v1_빈공간점검_{at:%m%d-%H%M}.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for name,data in members.items():z.writestr(name,data)
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for row in z.read('SHA256SUMS').decode().splitlines():
            h,name=row.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==h
    receipt=dict(at=now(),status='PASS_INTEGRITY',path=str(dest),bytes=dest.stat().st_size,sha256=sha(dest),members=len(members),
        preflight_status=result['status'],scientific_verdict=None)
    for directory in [root,doc]:
        previous=read(directory/'delivery.json')
        if previous:
            old=directory/(Path(previous['path']).stem+'.receipt.json')
            if not old.exists():save(old,previous,True)
        save(directory/'delivery.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':package()
