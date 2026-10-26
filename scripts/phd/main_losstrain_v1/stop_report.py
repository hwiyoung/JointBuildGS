"""Report the user's revised join stop from saved geometry-only evidence."""
import csv
import json
from datetime import datetime
from pathlib import Path
import numpy as np
from inputs import OUT, SITES, PRIORS, sha, save

def csvwrite(path,rows):
    with Path(path).open('w') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    doc=Path('/docs');now=datetime.now().astimezone().isoformat()
    report=json.loads((OUT/'checks/join_v2.json').read_text())
    fail=[r for r in report['rows'] if r['gate']=='STOP']
    assert fail,'this script only produces a stop report'
    rows=[];hist=[]
    for r in report['rows']:
        site,prior=r['site'],r['prior']
        p=OUT/'checks/join_v2'/f'{site}__{prior}.npz'
        with np.load(p,allow_pickle=False) as z:
            d=z['distance_m'];ev=z['in_eval'];joined=z['joined']
            h=np.maximum(z['normal_height_stage1_m'],z['normal_height_vfile_m']);known=z['normal_defined']
        for scope,mask in [('all_stage1',np.ones(len(d),bool)),('evaluation',ev)]:
            q=np.quantile(d[mask],[0,.25,.5,.75,.90,.95,.99,1])
            row=dict(site=site,prior=prior,scope=scope,patches=int(mask.sum()),joined_patches=int((mask&joined).sum()),
                joined_percent=float(joined[mask].mean()*100),**dict(zip(['min_m','p25_m','p50_m','p75_m','p90_m','p95_m','p99_m','max_m'],q.tolist())),
                centre_over_18cm=int((mask&(d>.18)).sum()),
                within_18cm_height_over_10cm=int((mask&(d<=.18)&known&(h>.10)).sum()),
                within_18cm_unknown_normal=int((mask&(d<=.18)&~known).sum()),source=str(p),source_sha256=sha(p),
                value_origin='[이 발주에서 냄]')
            assert row['joined_patches']+row['centre_over_18cm']+row['within_18cm_height_over_10cm']+row['within_18cm_unknown_normal']==row['patches']
            rows.append(row)
            edges=[0,.05,.10,.18,.25,.5,1,2,5,10,np.inf]
            # Disjoint closed-upper bins: first [0,.05], then (.05,.10], etc.
            for i,(lo,hi) in enumerate(zip(edges[:-1],edges[1:])):
                m=mask&(d>=lo if i==0 else d>lo)&(d<=hi)
                hist.append(dict(site=site,prior=prior,scope=scope,lower_m=lo,upper_m=hi if np.isfinite(hi) else None,
                    lower_inclusive=i==0,upper_inclusive=True,patches=int(m.sum()),percent=float(m.sum()/mask.sum()*100)))
    save(doc/'tables/nearest_distance_v2.json',dict(rows=rows,histogram=hist,rules=report['config'],scientific_verdict=None))
    csvwrite(doc/'tables/nearest_distance_v2.csv',rows);csvwrite(doc/'tables/nearest_distance_histogram_v2.csv',hist)
    cpu=json.loads((OUT/'checks/loss_cpu.json').read_text())
    stop=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',status='STOPPED',at=now,
        user_rule='18cm centre distance + 10cm normal-direction height; stop if any of six units has patch linkage below 95%',
        failing_units=[dict(site=r['site'],prior=r['prior'],fraction=r['joined_fraction']) for r in fail],
        short_trainings_completed=0,full_trainings_completed=0,training_optimizer_steps=0,selected_lambda=None,
        GPU_current_checks='two r16 B0 initialization probes interrupted on the revised stop; no r17 GPU probe or optimizer step',
        scientific_verdict=None)
    save(OUT/'checks/STOP.json',stop)
    for name in ['r16_B0_b10_LoD2','r16_B0_b10_ALS']:
        p=OUT/'checks/current'/name
        if p.exists():save(p/'interrupted.json',dict(at=now,status='INTERRUPTED_BY_USER_GATE',reason=stop['user_rule'],
            optimizer_steps=0,comparison_complete=False,scientific_verdict=None))
    lines=['# 손실 학습 시험 준비 보고 v1 — 새 연결 규칙에서도 중단',
        '', '완료 학습: 짧은 학습 0/4, 본 학습 0/24, 선택 학습 0/6. 실패 학습은 없고 모두 시작 전 중단.',
        '고른 λ: 없음. 0.0025는 발주문의 기본 후보이며 선택된 값이 아니다.',
        '확인 불가: 학습 효과, 여섯 단위 r16/r17 GPU 동등성, 고정 체크포인트의 새 손실 화소 수, 좌표 어긋남의 원인.',
        '',f'기록: {now} · scientific_verdict: null',
        '', '## 중단 조건과 현재 결과',
        '', '사용자의 추가 지시를 적용했다. 같은 사전 정보에서 등록된 3차원 중심이 가장 가까운 패치를 찾은 뒤, 중심 거리 0.18 m 이하이고 두 패치 각각의 단위 법선 방향 높이 차가 모두 0.10 m 이하인 경우만 연결했다. 법선이 없는 패치는 연결하지 않았다. 참값은 읽지 않았다. 기존 5 cm 검사와 새 검사는 별도 파일로 보존했다.',
        '', '95% 기준의 분모는 원 발주 6.4절의 “1단계 패치” 전체다. 평가 범위의 비율도 별도 표시했다. 새 규칙에서도 세 단위가 기준에 미달하므로 진행을 중단했다. 평가 범위만 분모로 사용하더라도 B173 주변·항공 LiDAR는 72.00%로 미달한다.',
        '', '| 단위 | 사전 정보 | 전체 연결 / 전체 패치 | 전체 연결률 | 평가 범위 연결 / 평가 패치 | 평가 연결률 | 평가 범위 미연결 넓이 (m²) | 전체 기준 |',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for r in sorted(report['rows'],key=lambda r:(SITES.index(r['site']),PRIORS.index(r['prior']))):
        lines.append(f"| {r['site']} | {r['prior']} | {r['joined_patches']:,} / {r['patches']:,} | {r['joined_fraction']*100:.4f}% | {r['eval_joined_patches']:,} / {r['eval_patches']:,} | {r['eval_joined_fraction']*100:.4f}% | {r['eval_unmatched_area_m2']:.6f} | {r['gate']} |")
    lines+=['','위 수치와 아래 거리 분포는 모두 [이 발주에서 냄]. 표의 반올림 전 값, 표본 수, 입력 SHA-256은 `tables/patch_join_v2.json`, `tables/nearest_distance_v2.json`에 있다. 평가 범위 미연결 넓이는 1단계 패치 넓이의 합이며 채점 결과가 아니다.',
        '', '## 가장 가까운 중심까지의 거리 분포',
        '', '단위: cm. 연결 조건을 적용하기 전 최근접 거리이며, 참값까지의 오차가 아니다.',
        '', '| 단위 | 사전 정보 | 범위 | N | 최소 | 25분위 | 중앙값 | 75분위 | 95분위 | 99분위 | 최대 |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in sorted(rows,key=lambda r:(SITES.index(r['site']),PRIORS.index(r['prior']),r['scope'])):
        name='전체' if r['scope']=='all_stage1' else '평가'
        lines.append(f"| {r['site']} | {r['prior']} | {name} | {r['patches']:,} | "+' | '.join(f"{r[k]*100:.3f}" for k in ['min_m','p25_m','p50_m','p75_m','p95_m','p99_m','max_m'])+' |')
    lines+=['','0–5, 5–10, 10–18, 18–25, 25–50, 50–100, 100–200, 200–500, 500–1,000, 1,000 cm 초과 구간의 개수·비율은 `tables/nearest_distance_histogram_v2.csv`에 기록했다.',
        '', '## 연결되지 않은 패치의 검사상 원인',
        '', '| 단위 | 사전 정보 | 범위 | 중심 거리 18 cm 초과 | 18 cm 이내·법선 높이 10 cm 초과 | 18 cm 이내·법선 확인 불가 |',
        '|---|---|---|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['site']} | {r['prior']} | {'전체' if r['scope']=='all_stage1' else '평가'} | {r['centre_over_18cm']:,} | {r['within_18cm_height_over_10cm']:,} | {r['within_18cm_unknown_normal']:,} |")
    lines+=['', '이 분류는 연결 조건에서 탈락한 이유만 보여 준다. 좌표 어긋남, 등록 이동, 패치 생성 차이, 확인용/범위 밖 패치 제외 중 무엇이 원인인지는 아직 확정하지 않았다. 기존 5 cm 검사의 등록 전 중심 진단값도 본 연결에 사용하지 않았다.',
        '', '## 완료한 독립 준비 작업',
        '', '- 첨부 ZIP 4개: 발주문의 SHA-256 앞 16자리 일치, 전체 SHA-256 기록, CRC 통과. NPZ 48개. 첨부 제작 스크립트는 실행하지 않았다.',
        '- r17 초안: r16을 복사하고 `jbgs_judgment.py`만 변경했다. `train.py`와 나머지 파일은 동일하다. 변경 파일·전체 해시·diff는 `provenance/`에 있다.',
        f"- CPU 손실 검사: {cpu['checks']}개 통과(float32/float64, 두 손실, 단일/두 자료, 발주문의 거리·σ·V 조합). 상대 오차 기준 1e-4, 분모 바닥 1e-12. 최대 손실 상대 오차 {max(c['loss_relative_error'] for c in cpu['cases']):.9g}, 최대 기울기 상대 오차 {max(c['gradient_relative_error'] for c in cpu['cases']):.9g}.",
        '- 합성 화소 검사: MVS 없음은 사전 정보 항만, 패치 없음은 깊이 기울기 0, 두 손실의 대상 화소 수 확인. current의 CPU 손실·깊이 기울기는 r16과 같았다. 실제 여섯 단위 GPU 동등성을 증명하는 검사는 아니다.',
        '- r16 B0 두 단위의 GPU 초기화 검사는 새 중단 조건에 따라 중지했다. 옵티마이저 단계는 실행하지 않았다. 이 검사에는 PASS를 부여하지 않는다.',
        '- 규칙 설정과 해시를 기록했다. 정확한 그림 렌더 카메라, λ 선택, 모든 학습 전 검사 완료는 아직 남아 있으므로 학습 가능한 최종 잠금 상태가 아니다.',
        '', '## 미완료 항목과 남은 제한',
        '', '패치 연결이 막혀 짧은 학습, λ 선택, 24회(+선택 6회) 학습, 후처리, 채점, 기대 가~사 비교, 최종 그림, 패치별 학습 결과는 만들지 않았다. 학습 없는 시험의 전체·지역별 값 재계산도 아직 실행하지 않았다. r17 초안은 실제 연결값을 넣은 GPU 검증과 준비 절차를 완료하기 전 학습에 사용할 수 없다.',
        '', '이번 전달 묶음은 중단 근거와 준비 작업의 부분 인계다. 완성된 손실 학습 시험 결과로 사용하지 않는다. 원 발주문, 사용자의 18 cm 변경, 계산 스크립트, 해시·로그를 함께 보존한다.']
    text='\n'.join(lines)+'\n'
    (doc/'준비보고_v1.md').write_text(text)
    (doc/'손실학습시험_보고_v1.md').write_text(text.replace('준비 보고 v1','중단 보고 v1',1))
    (doc/'progress.md').write_text(f'# PHD-MAIN-LOSSTRAIN-v1\n\n{now}: STOPPED. 18 cm / 10 cm 연결 조건에서도 세 단위 미달. 학습 0회. scientific_verdict: null.\n\n'+
        '기록: 준비보고_v1.md, tables/patch_join_v2.json, tables/nearest_distance_v2.json, provenance/build_r17.json.\n')
    (doc/'issues.md').write_text('# Issues — PHD-MAIN-LOSSTRAIN-v1\n\n'+
        'LT-001 STOP: original 5 cm patch gate failed for five units. Superseded by the explicit user revision. Original evidence retained.\n\n'+
        'LT-002 STOP: revised 18 cm centre + 10 cm normal height gate failed for B0 LoD2, R1 LoD2, B173nb ALS. Evidence: tables/patch_join_v2.json. Training never started. Cause of coordinate/grid differences unconfirmed.\n\n'+
        'LT-003 INCOMPLETE: two r16 B0 GPU initialization probes were interrupted when LT-002 was confirmed. No r16/r17 GPU-equivalence PASS is claimed.\n\nscientific_verdict: null\n')
    md=['| 단위 | 사전 정보 | 전체 연결률 (%) | 평가 연결률 (%) | 미연결 평가 넓이 (m²) |','|---|---|---:|---:|---:|']
    for r in report['rows']:md.append(f"| {r['site']} | {r['prior']} | {r['joined_fraction']*100:.6f} | {r['eval_joined_fraction']*100:.6f} | {r['eval_unmatched_area_m2']:.6f} |")
    (doc/'tables/patch_join_v2.md').write_text('\n'.join(md)+'\n\n[이 발주에서 냄]; full counts and provenance: patch_join_v2.json.\n')
    print('STOPPED; reports and distance distributions written;',len(text),'characters')

if __name__=='__main__':main()
