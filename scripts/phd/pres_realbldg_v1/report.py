from common import *
LABEL={'c1':'①','c2':'②','c3a':'③가','c3b':'③나','c4':'④'}
rank=json.loads((O/'ranking.json').read_text());top=rank['top5'];rows=rank['rows']
with (D/'tables/조건별_건물_수.csv').open() as f:counts=list(csv.DictReader(f))
text=f'''# 실제 건물 확인

저장된 지붕·벽 경우 범위에서 다섯 조건을 모두 채운 건물은 {rank['all_five']}동이며, 그 가운데 실험 지역 안은 {rank['all_five_experiment']}동이다. 바닥 경우 자료가 없어 ③나는 벽으로만 계산했으며, 바닥까지 포함한 다섯 조건 충족 여부는 확인 불가다. 윤곽 넓이 100 m² 이상이고 경우 자료가 있는 {rank['buildings']}동을 확인했다. 이 범위의 상위 다섯 동은 모두 네 조건을 채웠다.

|순위|건물|묶음|채운 조건|LoD2 / 항공 LiDAR|
|---|---|---|---|---|
'''
for i,r in enumerate(top,1):text+=f"|{i}|{r['building']}|{r['group']}|{'·'.join(LABEL[k] for k,v in r['conditions'].items() if v)}|{r['count']} / {r['als_count']}|\n"
text+='''
조건별로 확인된 충족 건물 수는 다음과 같다. ‘이상’은 사진 수를 구하지 않은 건물이 남았다는 뜻이다.

|묶음|①|②|③가|③나|④|
|---|---|---|---|---|---|
'''
for group in ['실험 지역 안','개발용','확인용']:
    values=[]
    for k in LABEL:
        r=next(x for x in counts if x['group']==group and x['condition']==k);values.append(r['satisfied']+(' 이상' if int(r['not_measured']) else ''))
    text+='|'+group+'|'+'|'.join(values)+'|\n'
text+='''
모든 조건에 충족 건물이 있어 느슨한 값은 쓰지 않았다. ①은 2동, ④는 52동의 벽 사진 수를 구하지 않았다. 발주문에 따라 지붕 사전 조건을 둘 이상 채운 건물과 면 53만 계산했다. 생략한 건물은 가능한 충족 수가 최대 두 개라 상위 다섯은 바뀌지 않는다. 사진으로 무늬를 확인할 수 없는 점은 무늬 있음·없음 어느 쪽에도 넣지 않았다.

기대와 달리 B173 주변 면 53이 모두 0장은 아니었다. 21,560패치 가운데 18,367개는 0장, 3,193개는 1장이다. 사진 DJI_20241217101359_0032_D의 각은 74.3~76.7°로, 앞 작업의 60° 밖이고 이번 80° 안이다. 이 사진과 가림 계산을 따로 확인했다.

실험 지역 여섯 장면은 저장된 GTJUDGE 법선 측정선 경우를 썼다. 지역 밖은 같은 패치 번호의 JUDGECHECK 경우를 우선 쓰고, 나머지는 WIDEN0-v2 경우를 썼다. 원래 칸 5는 둘 다 틀림에 합쳤으며, 참값이 없는 칸은 따로 남겼다. 모든 참값 점의 건물 소속은 RECOUNT의 기둥 소속 그대로다.

④는 벽 패치 넓이로 구했다. 벽 참값 점 수와 τ 안 비율은 조건 보조 표에 적었다. 지역 밖 점 수는 저장된 면 거리와 안쪽 원통에 속한 원래 참값 점의 중복을 제거한 수다. 실험 지역의 건물별 경우 넓이와 미소속 넓이를 더한 값은 여섯 장면 모두 장면 합과 같다.

설정은 2026-11-05 20:11:51 KST에 첫 계산 전에 잠갔다. 학습·메시 만들기·렌더·GPU 사용은 없었다. CPU 동시 할당 상한은 24개로, 물리 코어 64개의 절반 이하다. 앞 작업은 읽기 전용으로 두었고 새 파일은 지정한 네 경로에만 썼다. PH의 실제 경로는 `../JointBuildGS-artifacts/phase-payloads/phd/pres_realbldg_v1/PHD-PRES-REALBLDG-v1/`이다.

상위 다섯의 조건별 넓이·연속 길이·윤곽 크기는 [표](tables/상위_다섯.csv), 전체 순위는 [CSV](tables/전체_순위.csv), 계산과 검증 기록은 [검증 파일](validation.json)에 있다. 그림은 [그림 목록](그림_목록.md)에 있다.

scientific_verdict: null
'''
assert len(text)<=3000,len(text);(D/'보고.md').write_text(text)
extras=[]
for r in rows:
    if r['group']=='확인용' and r['building'] not in {x['building'] for x in top}:continue
    extras.append({k:r.get(k) for k in ['building','group','scene','c2_type','c2_reference_minus_prior_z_m','c4_face','c4_reference_n','c4_prior_tau_fraction','c4_reference_note','texture_unavailable_m2']})
table('조건_보조',extras)
lines=['# 상위 다섯 그림','']
for i,r in enumerate(top,1):
    b=r['building'];lines.extend([f'{i}. {b} · '+ ' '.join(LABEL[k] for k,v in r['conditions'].items() if v),'',f'![위에서](figures/{b}_가_위에서.png)','',f'![경사 사진](figures/{b}_나_경사사진.png)',''])
(D/'그림_목록.md').write_text('\n'.join(lines))
dump(D/'provenance/report_check.json',dict(characters=len(text),scientific_verdict=None));print('REPORT_CHARACTERS',len(text))
