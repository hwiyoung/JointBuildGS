"""Compact Korean report from completed receipts, with explicit pending states."""
from mesh_common import *
import csv
from priority_delivery import snapshot, update as update_priority

def read(p):return json.loads(p.read_text()) if p.exists() else None
def num(x,d=3):return '확인 불가' if x is None else f'{x:.{d}f}'
def main():
    from verify_priority import verify
    verify()
    files=sorted((D/'tables/meshes').glob('*.json'));meshes=[read(p) for p in files];passed=[r for r in meshes if r['status']=='PASS']
    target=mesh_config();n=len(target['targets'])
    priority=snapshot(D,O,C)
    patches={p:read(D/'tables'/f'patch_{p}_table.json') for p in ['ALS','LoD2']}
    validations={p:read(D/'tables'/f'patch_{p}_validation.json') for p in patches}
    rows=[];rm=[];s1=[]
    for r in passed:
        t=r['target'];ident={k:t[k] for k in ['site','prior','result']}
        for b,a in zip(r['before'],r['after']):
            row=dict(**ident,cell=b['cell'],area_m2=b['area_m2'])
            for k in ['within_tau_pct','floating_pct','floating_area_m2','no_surface_pct']:
                row[k+'_before']=b[k];row[k+'_after']=a[k];row[k+'_delta']=None if b[k] is None else a[k]-b[k]
            rows.append(row)
        for x in r['removed']['categories']:rm.append(dict(**ident,**x))
        if 'stage1_after' in r:
            for stage in ['before','after']:
                x=r['stage1_'+stage];sp=x['spread']['prior_error']['main'];cp=x['completeness']['missing_agreement']['all']
                s1.append(dict(**ident,stage=stage,prior_error=sp,missing_agreement=cp,summary=x['summary']))
    dump(D/'tables/mesh_comparison.json',dict(rows=rows,removed=rm,stage1=s1,completed=len(passed),requested=n,scientific_verdict=None))
    if rows:
        with (D/'tables/mesh_comparison.csv').open('w') as f:
            w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    md=['# 메시 정리 전·후','', '[이 발주에서 냄]', '', '| 평가 지역 | 사전 정보 | 방법 | 칸 | τ 안 전 % | 후 % | 뜬 면 전 % | 후 % | 면 없음 전 % | 후 % |','|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    md +=[f"| {r['site']} | {r['prior']} | {r['result']} | {r['cell']} | {num(r['within_tau_pct_before'])} | {num(r['within_tau_pct_after'])} | {num(r['floating_pct_before'])} | {num(r['floating_pct_after'])} | {num(r['no_surface_pct_before'])} | {num(r['no_surface_pct_after'])} |" for r in rows]
    md+=['','| 평가 지역 | 사전 정보 | 방법 | 남은 덩어리 | 최소 삼각형 수 | 지운 넓이 m² |','|---|---|---|---:|---:|---:|']
    md +=[f"| {r['target']['site']} | {r['target']['prior']} | {r['target']['result']} | {r['cleanup']['after_components']} | {r['cleanup']['min_remaining_component_triangles']} | {num(r['removed']['area_m2'])} |" for r in passed]
    (D/'tables/mesh_comparison.md').write_text('\n'.join(md)+'\n')
    lines=[f"한 일: 코드 확인, 공개 패치 표 {sum(x is not None for x in patches.values())}/2개 생성, 메시 정리·채점 {len(passed)}/{n}개 완료. [이 발주에서 냄]",
        '정리로 바뀐 값: '+('아래 일 2와 대상별 표에 기록.' if passed else '아직 산출되지 않음. 큰 CPU 작업의 메모리 입장 조건을 기다리는 중.'),
        '확인 불가: GeoGS 논문 전문, 원본 면 번호 배열·곡률 캐시·실행 환경, 서로 이어지지 않는 기존 영역 코드. R1 ALS 판 1은 기존 중단 상태 유지.',
        '', '# 일 1. 코드와 기록', '', 'GeoGS 원본 출발 커밋은 `db40c95c657ec03ff21c83cb99cf39f4e90247a6`이다. `utils/mesh_utils.py:23–44`의 `post_process_mesh`와 `render.py:39,131`의 기본값 50 및 호출이 원본에 있다. 가상 시점도 `render.py:100–114`에 있다. 포크가 처음 추가한 처리가 아니다.',
        '원본 함수는 50번째로 큰 삼각형 수와 50 중 큰 값을 문턱으로 쓰고, 그보다 작은 연결 성분을 지운다. 같은 수의 성분이 있으면 50개보다 많이 남을 수 있다. 남은 삼각형 수를 확인하며, 원본 함수 본문을 바꾸지 않고 호출한다.',
        '현재 채점용 `mesh_tsdf.ply`는 `gpu_s1.post`와 LOSSTRAIN의 조각 TSDF 경로에서 나왔다. 해당 경로에는 이 성분 정리나 가상 시점 합침이 없다. 2DGS·GeoGS·고친 GeoGS도 같은 후처리 경로를 쓴다. 별도 가상 시점 결과를 현재 채점 메시와 합쳤다고 보지 않는다.',
        '원본 README 133–136행은 `fuse_post.ply`를 건물 범위로 자른 다음 `mesh2pcd`로 평가하는 절차를 제시한다. 출판사 논문 전문은 HTTP 403으로 접근할 수 없어 전문의 평가 절차 문장은 확인 불가이다.',
        '[GeoGS 원본 코드](https://github.com/zqlin0521/GeoGS/tree/db40c95c657ec03ff21c83cb99cf39f4e90247a6) · 자세한 파일·줄·해시: `tables/task1_code_audit.json`.',
        '', '# 일 2. 메시 정리와 다시 채점', '', f'요청 대상 {n}개 중 완료 {len(passed)}개, 기존 중단 {sum(r["status"]=="UNAVAILABLE_FROZEN_STOP" for r in meshes)}개. 아직 완료 기록이 없는 대상은 수치나 그림을 채우지 않는다.',
        f"설명용 필수 대상은 R1·B173·B0 항공 LiDAR의 판정 끔·판 4 여섯 개다. 이들을 실행 큐 맨 앞에서 처리하며 현재 {priority['completed']}/6개, 사례 그림 {priority['completed_cases']}/7개 완료다. 10/30 09:30 묶음에 포함할 목록과 점검은 `tables/priority_six.json`에 기록한다.",
        '전체 단위 메시를 먼저 정리하고 사례 범위는 그 뒤 자른다. 처음 만난 면, τ, 오차의 표준화, 칸·평가 마스크는 기존 LOSSTRAIN 셈을 유지한다. 정리 전 기존 기록과의 차이가 0.5 %p를 넘으면 해당 대상을 멈춘다.',
        '삼각형 넓이는 실제 3차원 넓이다. 지운 삼각형 중심에서 XY 거리 √2×0.25 m 안의 기존 지붕 패치에 연결하여 정리 전 다섯 구분을 붙인다. 연결되지 않는 넓이는 별도 확인 불가로 기록한다. 이 연결은 새로운 가시성·영역 판정이나 독립 참값이 아니다.',
        '칸별 전체 값·지운 넓이 다섯 구분·남은 성분 수는 `tables/mesh_comparison.json`, 대상별 원본 기록은 `tables/meshes/`에 있다. 1단계 메시 지표는 기존 spread·completeness와 F1 표본 규칙(400/m², seed 0, 같은 bsurf)을 유지한다.',
        '그림은 FLOATDIAG의 고정 카메라·색을 사용한다. 정리 전, 후, 지운 면을 따로 표시한다. 그림 색은 원래 시각화 규칙이며, 첫 교차점의 다섯 구분 집계와 정의가 다르다. 웹용 간략화는 그림용 파일에만 적용한다.',
        '', '# 일 3. 패치 표 점검', '', '사용자 결정에 따라 새 가시성·영역 계산은 하지 않았다. 연결을 증명한 패치에만 기존 코드를 붙였다. 모든 패치에 mvs_p 결측 여부와 참값이 있는 경우 사전 정보가 τ 안인지 판정을 넣었다.',
        '', '| 사전 정보 | 패치 수 | 넓이 m² | 원본·CSV 일치 | MVS 없음 수 | 사전 정보 맞음 수 |','|---|---:|---:|---|---:|---:|']
    for p,x in patches.items():
        if x:lines.append(f"| {p} | {x['patches']:,} | {x['area_m2']:.6f} | {(validations[p] or {}).get('status','검사 중')} | {x['mvs_absent_by_mvs_p_patches']:,} | {x['prior_correct_patches']:,} |")
    lines+=['','| 사전 정보 | 평가 지역 | 표에서 미연결 수 | 표에서 미연결 m² | 기존 영역에서 미연결 수 | 기존 영역에서 미연결 m² |','|---|---|---:|---:|---:|---:|']
    for p,x in validations.items():
        if x:
            for r in x['region_rows']:lines.append(f"| {p} | {r['site']} | {r['unmatched_geometry_eval_patches']:,} | {r['unmatched_geometry_eval_area_m2']:.6f} | {r['reference_unjoined_patches']:,} | {r['reference_unjoined_area_m2']:.6f} |")
    lines+=['','| 사전 정보 | 평가 지역 | 영역 코드가 비어 있는 수 | 영역 코드가 비어 있는 m² |','|---|---|---:|---:|']
    for p,x in validations.items():
        if x:
            for r in x['region_rows']:lines.append(f"| {p} | {r['site']} | {r['unavailable_eval_patches']:,} | {r['unavailable_eval_area_m2']:.6f} |")
    lines+=['','ALS는 지역별 TIN과 전체 공개 표의 격자가 다르므로 영역 코드가 비어 있다. LoD2는 원래 중심·넓이·건물·면 종류·법선이 같은 행만 연결했다. 위 표는 기하 미연결이며, 참값이나 기존 코드가 없어 코드가 비는 경우까지 합친 값은 `tables/patch_*_validation.json`의 unavailable_eval에 있다. 지역끼리 겹치므로 위 넓이를 단순히 더하지 않는다.',
        '', '| 사전 정보 | Roofer 면 수 | 기준 | mvsshape_10 면 수 | 기준 | Roofer 대조 |','|---|---:|---:|---:|---:|---|']
    for p in patches:
        x=read(D/'tables'/f'patch_{p}_tracka_check.json')
        if x:
            a=x['checks']['roofer_def'];b=x['checks']['mvsshape_10'];lines.append(f"| {p} | {a['groups']} | {a['expected_groups']} | {b['groups']} | {b['expected_groups']} | {a['status']} |")
    lines+=['','첨부 원본 Roofer 드라이버와 종류 판정 코드를 직접 실행한 결과는 이 작업의 번호·종류 배열과 같다. 그러나 제공된 요약값과 Roofer 면 수가 달라 완전 일치를 주장할 수 없다. 면 개수를 맞추기 위한 문턱 수정은 하지 않았다. 종류 코드의 원래 대상인 mvsshape_10은 면 수와 제공된 비율이 일치한다.',
        '기준 JSON에 전체 넓이 분포가 없으므로 제공된 1 m² 이상 면의 넓이 비율만 대조했다. 자세한 차이는 `tables/patch_*_tracka_check.json`에 있다. 원본 값 보존 검사의 PASS와 이 대조의 FAIL은 별도이다.',
        'LoD2의 겹치는 평가 지역에서 기존 코드가 다른 3,291개 패치(205.6875 m²)는 통합 코드를 비웠다. 지역별 원본 코드는 별도 열로 보존했다. 어느 쪽이 맞는지 새로 정하지 않았다.',
        '', '# 걸린 시간과 전달', '', f'기록 갱신: {now()}. 큰 메시 작업은 공유 TSDF 잠금, 가용 메모리 56 GiB 이상 60초, 최대 40 GiB·8 CPU 조건을 유지한다. 패치 표는 파일 기반 열 저장으로 최대 4 GiB·2 CPU 안에서 실행한다.',
        f'완료한 메시 처리 시간 합: {sum(r.get("seconds",0) for r in passed):.1f}초. 원본 해시·코드 스냅샷·실행 로그는 외부 작업 폴더 logs에 보존한다.',
        '패치 표 마감 10/29 18:00, 설명용 중간 묶음 10/30 09:30. 중간 ZIP은 100 MB 미만이며 첫 파일은 진행.md이다. 전체 메시 파일은 중간 ZIP에서 제외한다.',
        '', 'scientific_verdict: null']
    report='\n'.join(lines)+'\n';assert len(report)<=10000
    (D/'메시정리와패치표_보고_v1.md').write_text(report)
    (D/'progress.md').write_text(f'# 진행\n\n갱신: {now()}\n\n일 1 코드 확인 완료(논문 전문 확인 불가). 일 3 표 {sum(x is not None for x in patches.values())}/2개, 검증 {sum(x is not None for x in validations.values())}/2개. 일 2 메시 {len(passed)}/{n}개 완료.\n\n영역 연결은 사용자 승인 범위만 적용. 새 가시성 계산 없음. 면 번호 대조의 불일치는 보고서 참조.\n\nscientific_verdict: null\n')
    print(json.dumps(dict(report_characters=len(report),completed_meshes=len(passed),targets=n)))
    update_priority()
    if (C/'axes_addendum_v1.json').exists():
        from axes_report import main as axes_report
        axes_report()

if __name__=='__main__':main()
