"""Requested Korean report, full face-table index and r2/r7 area changes."""
from common import *

def pct(v):return '확인 불가' if v is None else f'{100*v:.1f}%'

def changes():
    rows=[];sealed=[]
    for scope in [*SITES,'development','holdout']:
        for prior in ['ALS','LoD2']:
            def path(rev):
                if scope in SITES:return OUT/f'{rev}/tables/faces_full_{scope}_{prior}.json'
                return OUT/('holdout' if scope=='holdout' else 'development')/rev/'tables'/f'faces_full_{prior}_{rev}.json'
            if not path('r7').exists():continue
            old={r['face_id']:r for r in read(path('r2'))['rows']};new={r['face_id']:r for r in read(path('r7'))['rows']}
            assert set(old)==set(new)
            for fid,r in new.items():
                p=old[fid];assert abs(p['eval_area_m2']-r['eval_area_m2'])<1e-8
                if all(abs(r[name+'_area_m2']-p[name+'_area_m2'])<1e-9 for name in NAMES.values()):continue
                change={k:r[k] for k in ['scope','prior','building','building_name','face_id','face_name','face_kind','eval_area_m2']}
                for name in NAMES.values():
                    change['r2_'+name+'_fraction']=p[name+'_fraction'];change['r7_'+name+'_fraction']=r[name+'_fraction']
                    change[name+'_change_pp']=100*(r[name+'_fraction']-p[name+'_fraction'])
                change.update(r2_purity=p['purity'],r7_purity=r['purity'],source_tag=TAG)
                (sealed if scope=='holdout' else rows).append(change)
    table(DOC/'tables/changed_faces_r2_to_r7.csv',rows)
    table(OUT/'holdout/changed_faces_r2_to_r7.csv',sealed)
    agg=[]
    for prior in ['ALS','LoD2']:
        for kind in ['roof','wall']:
            rr=[r for r in sealed if r['prior']==prior and r['face_kind']==kind]
            agg.append(dict(prior=prior,face_kind=kind,changed_face_count=len(rr),eval_area_m2=sum(r['eval_area_m2'] for r in rr),
                disappeared_area_m2=sum(r['r7_removed_fraction']*r['eval_area_m2'] for r in rr),source_tag=TAG))
    table(DOC/'tables/changed_faces_holdout_totals_r2_to_r7.csv',agg)
    return rows,agg

def main():
    summary=read(DOC/f'tables/summary_{REV}.json')['rows'];units=read(DOC/f'tables/association_units_{REV}.json')['rows']
    exp=[r for r in summary if r['scope'] in SITES]
    measured=read(OUT/f'measurement_complete_{REV}.json');figtime=read(OUT/f'figures_complete_{REV}.json')
    def rng(prior,kind,key):
        vals=[r[key]/r['eval_area_m2'] for r in exp if r['prior']==prior and r['face_kind']==kind and r['eval_area_m2']]
        return f'{100*min(vals):.1f}~{100*max(vals):.1f}%' if vals else '확인 불가'
    kinds=[('ALS','roof','항공 LiDAR 지붕'),('LoD2','roof','LoD2 지붕'),('LoD2','wall','LoD2 벽')]
    seconds=measured['seconds']+figtime['seconds']
    lines=[
        '면 순도 90% 이상 면의 넓이 비율(지역별 범위): '+'; '.join(f'{n} {rng(p,k,"high_purity_area_m2")}' for p,k,n in kinds)+'. '+TAG,
        '통째로 한 영역인 면의 넓이 비율: '+'; '.join(f'{n} {rng(p,k,"wholly_one_region_area_m2")}' for p,k,n in kinds)+'. '+TAG,
        '판단·참값 짝이 맞은 넓이 / 연결된 면의 평가 넓이: '+'; '.join(f'{n} {rng(p,k,"match_area_m2")}' for p,k,n in kinds)+'. '+TAG,
        '확인 불가: 셀 수 없음·칸 4~6을 남겼다. 관측 없음과 칸 3(둘 다 틀림)은 짝 맞음과 분리했다. 항공 LiDAR 벽 자료는 없다.',
        f'걸린 시간: {REV} 집계·그림 실행 {seconds/60:.1f}분. 준비·코드 작성·검증 시간은 별도 실행 기록. '+TAG,
        '',f'# 영역 지도와 면 요약 · {REV}','',
        '판단은 기존 패치 그대로다. 여기서는 묶어서 세고 표시하는 단위만 LoD2 면으로 바꿨다. 결론을 내리지 않으며 `scientific_verdict: null`을 유지한다. 모든 계산값은 [이 발주에서 냄]이다. 네 지역은 서로 겹치므로 합쳐 하나의 모집단처럼 해석하지 않는다.','',
        '## 면 나누기와 분모','',
        'LoD2는 원래 면 번호를 쓴다. 원본 면 ID와 `_poly` ID는 외곽·구멍 좌표가 정확히 같을 때만 연결했다. 지붕 이름은 원본 면 넓이 순서, 벽 이름은 바깥 법선 방향이다. 두 사전 정보와 두 판에 같은 원래 면을 쓴다.','',
        '항공 LiDAR의 빈 건물 번호는 사용자 답변에 따라 **이 발주에서 구한 연결**이다. 패치 중심이 LoD2 GroundSurface 평면 범위에 유일하게 들어가면 그 건물로 연결한다. 범위 밖은 1 m 안 후보 건물이 하나일 때만 연결한다. 겹침·복수 후보·범위 없음은 붙지 않음이다. 같은 건물 지붕 다각형 안이면 거리 0, 밖이면 평면 경계까지 최단거리로 면을 고른다. 1 m 밖은 붙지 않음이다. 같은 거리의 면은 원본 ID 순서로 고르고 동률 수를 따로 기록했다. 높이를 연결에 쓰지 않았다.','',
        '평가 넓이는 원래 패치 넓이의 합이다. 위 지도는 평가 패치 중심을 0.25 m 칸에 모은 래스터다. 겹친 칸은 영역별 넓이 합이 가장 큰 색을 쓰며 동률은 코드 순서다. 래스터 칸 수를 평가 넓이로 대신하지 않았다. 빨간 점선은 칸 0~2와 일치·보존·보정의 짝이 다른 칸을 같은 면 안에서 네 방향 이웃끼리 연결한 윤곽이다. 벽은 위에서 겹치므로 펼친 그림도 함께 본다.','',
        '짝 맞음은 일치↔칸 0, 보존↔칸 2, 보정↔칸 1이다. 표의 짝맞음 비율은 전체 평가 넓이가 분모다. 비교 가능한 칸만의 비율도 원본 CSV에 별도로 있다. 사전 정보만 틀린 넓이는 칸 1+3, 영상만 틀린 넓이는 칸 2+3이며 공통 분모는 칸 0~3이다. 관측 없음·사라짐·셀 수 없음과 칸 3~6은 각각 별도 열로 남겼다.','',
        '1 m² 미만 면은 공개 면 표에서 종류별 “작은 면”으로 묶었다. 아래 상위 20개 표에는 원래 개별 면을 넓이순으로 고른 뒤 나머지를 합했다. 순도 분포는 작은 면도 원래 한 면씩 센다. “통째로”는 양의 넓이를 가진 패치의 영역이 하나뿐인 경우이며 90% 기준과 다르다.','',
        '| 지역 | 항공 LiDAR 붙지 않은 넓이 m² | 비율 |','|---|---:|---:|']
    for r in units:
        if r['prior']=='ALS':lines.append(f'| {SITES.get(r["scope"],{"development":"개발용","holdout":"확인용"}.get(r["scope"],r["scope"]))} | {r["unassigned_area_m2"]:.3f} | {pct(r["unassigned_fraction"])} |')
    lines+=['','B173은 평면 범위가 같아도 높이가 다를 수 있다. 표와 그림의 이름·경계는 기존 LoD2 면이다. 이 연결은 현재 높이가 맞다는 뜻이 아니다.','',
        '## 지역별 면 표와 지도','',
        '지=지붕, 벽 이름은 방향. 순도는 가장 넓은 영역의 비율. 전체 영역 비율·참값 칸·두 단독 비교는 각 CSV/JSON에 있다. 전체 지도 옆 사진은 평가 넓이가 가장 큰 건물 한 채다. 건물별 지도와 사진은 그림 목록에 따로 있다. 사진은 원래 화면 범위까지만 보인다.','']
    for site,label in SITES.items():
        lines.extend([f'### {label}','', '| 사전 정보 | 건물·면 | 넓이 m² | 가장 넓은 영역 | 순도 | 짝맞음 |','|---|---|---:|---|---:|---:|'])
        rr=[]
        for prior in ['ALS','LoD2']:rr+=read(OUT/f'{REV}/tables/faces_full_{site}_{prior}.json')['rows']
        rr=sorted(rr,key=lambda r:(-r['eval_area_m2'],r['prior'],r['face_id']))
        for r in rr[:20]:
            fname=r['face_name'].replace('지붕 ','지').replace('벽 ','벽')
            name=r['building_name']+'/'+fname
            lines.append(f'| {r["prior"]} | {name} | {r["eval_area_m2"]:.1f} | {r["dominant_region"]} | {pct(r["purity"])} | {pct(r["match_fraction_all_eval"])} |')
        rest=rr[20:];ar=sum(r['eval_area_m2'] for r in rest);ma=sum(r['match_area_m2'] for r in rest)
        lines+= [f'| 합계 | 나머지 {len(rest)}개 | {ar:.1f} | — | — | {pct(ma/ar if ar else None)} |','']
        if site.startswith('B173'):lines+=['B173: 평면 범위가 같아도 높이가 다를 수 있음.','']
        for prior in ['ALS','LoD2']:
            lines+=[f'[{prior} 면 전체 표](tables/faces_{site}_{prior}_{REV}.csv)',f'![{label} {prior}](figures/map_{site}_{prior}_{REV}.png)','']
        walls=sorted((DOC/'figures').glob(f'walls_{site}_*_LoD2_{REV}.png'))
        for f in walls:lines+=[f'![{label} 벽](figures/{f.name})','']
    lines+=['## 면 순도 분포','',f'![면 순도](figures/purity_{REV}.png)','',
        f'[면 수·넓이·영역별 순도](tables/purity_{REV}.csv). 개발용과 확인용은 이 표와 합계 표에만 있으며 그림은 없다. 확인용의 면별·패치별 값은 외부 `holdout/`에만 있고 묶음에서 제외했다.','',
        '벽 그림의 가로축은 남→동→북→서 순으로 이어 놓은 각 벽면의 실제 가로 길이 합이다. 서로 맞닿지 않는 면 사이에는 점선과 연결 수를 표시했다. 건물 실제 둘레가 끊김 없이 이어진다는 뜻은 아니다. 높이는 공통 작업 좌표 Z다.','',
        '## 판의 차이','']
    if REV=='r7':
        changed,hold=changes();ex=[r for r in changed if r['scope'] in SITES]
        lines+=[f'r2→r7에서 영역 비율이 바뀐 실험 지역 면 기록은 {len(ex)}개다. 지역 중복은 제거하지 않았다. r2에서 관측 없음이던 패치가 저장된 r7 사라짐 표시로 바뀐 경우만 반영했다. 면 연결·넓이·참값은 동일하다. '+TAG,
            '', '[바뀐 면 전체 표](tables/changed_faces_r2_to_r7.csv) · [확인용 합계](tables/changed_faces_holdout_totals_r2_to_r7.csv).','']
    else:lines+=['r2 묶음을 먼저 작성했다. r7은 별도 잠금 출력과 완료 기록을 확인한 뒤 같은 코드·면 연결로 추가한다.','']
    lines+=['## 입력과 재현','',
        '실제 입력: `PH/main_target_v1/PHD-MAIN-TARGET-v1/r2/targets/`, 참값은 `PH/main_stage1_v1/PHD-MAIN-STAGE1-v1/regions_v3/`. 면 다각형은 `main_design_realchange_survey_v1/.../s1/lod2_buildings.json`와 `main_widen0_v2/.../inputs/lod2_context_buildings.json`; 면 번호 대응은 `main_prep_discard_rule_v1/.../s02_box/` 및 WIDEN의 타일별 면 표다. 개발용·확인용은 JUDGENUM 입력과 TARGET의 r2 단계 0 파일을 정확한 패치 ID로 연결했다. 학습 영상은 STAGE0의 `fork_inputs/s61/<지역>/split.json` 중 학습 목록만 사용했다.','',
        'r7 입력은 TARGET `r7/targets/`, 개발용·확인용은 `r7/stage0/development/`·`holdout/r7/stage0/`의 저장된 사라짐 표시다. 설정에서 사라짐 코드 5를 확인했다. 공개 파일은 [그림·표 목록](파일목록.md), 입력 해시와 검증 결과는 묶음의 실행 기록에 있다. Docker 읽기 전용 입력과 전용 출력 마운트, CPU 2개·메모리 8 GiB로 실행했다.','',
        '재현: `bash scripts/phd/main_regionview_v1/run_cpu.sh measure measure.py r2`, 이어 `render.py r2`, `verify.py r2`, `report.py r2`. r7도 같은 명령의 판 인수만 r7로 바꾼다. 원본 입력은 묶음에 없으므로 해시가 같은 외부 자료가 있어야 다시 계산할 수 있다. SHA-256·ZIP 검사는 파일 무결성 근거이며 과학적 결론이나 사용자 그림 승인을 뜻하지 않는다.','']
    text='\n'.join(lines);assert len(text)<10000,len(text)
    filename=f'영역지도면요약_보고_{REV}.md';writable(DOC/filename).write_text(text)
    writable(DOC/'영역지도면요약_보고_v1.md').write_text(text)
    index=['# 그림과 표 목록','', '실험 지역의 건물별 그림과 전체 표. 모든 계산값은 [이 발주에서 냄].','']
    for sub in ['figures','tables']:
        index.extend([f'## {sub}',''])
        for p in sorted((DOC/sub).glob('*')):
            if p.suffix in ['.png','.csv']:index.append(f'- [{p.stem}]({sub}/{p.name})')
        index.append('')
    writable(DOC/'파일목록.md').write_text('\n'.join(index))
    print('REPORT',REV,'characters',len(text),flush=True)

if __name__=='__main__':main()
