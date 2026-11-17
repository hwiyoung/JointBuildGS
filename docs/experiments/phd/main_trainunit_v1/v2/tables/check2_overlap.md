# 확인 2: ALS 판정 122 + 배경 33 = 155 와 LoD2 목록 154

scientific_verdict: null

## 결론

1이 더 많은 까닭은 **빈 문자열 `''`** 이다. 세 장면(B0_b10, R1rep_b10, B173nb_b10)의 ALS 사이트 행은 `building` 값이 모두 `''`이다. 그래서 `judged = set(U['building'])`에 `''` 하나가 판정 건물로 들어갔다. `''`는 LoD2 목록에 없으므로 배경(unjudged)은 154 − 121 = 33이다. 즉 122 = LoD2 id 121 + `''` 1이고, 실제 건물만 세면 121 + 33 = 154이다.

## 근거 숫자

| 사전 정보 | 행 수 | building 고유값 | source별 고유값 (0 B0 / 1 R1rep / 2 B173nb / 3 JUDGECHECK) | 목록 밖 값 | 배경 | 맞춤 |
|---|---:|---:|---|---|---:|---|
| ALS | 652,991 | 122 | 1 / 1 / 1 / 121 | `''` (행 167,866 = source 0: 44,994, 1: 46,215, 2: 76,657, 넓이 11,192.4 m²) | 33 | 121 + 33 = 154 |
| LoD2 | 2,604,813 | 135 | 5 / 2 / 4 / 124 | 없음 | 19 | 사이트 11 + JUDGECHECK 124 = 135 (겹침 0), 135 + 19 = 154 |

`''` 행은 source 3(JUDGECHECK)에는 없고 세 장면 행에만 있다. LoD2 목록은 154행, id 고유 154.

## 함께 드러난 것 (셈에 영향)

- ALS 사이트 건물 이름이 `''`이라 `tu_campus.py` 136행의 이름 기반 사이트 제외가 아무것도 빼지 못했다(`site_building_overlap_dropped` 0). 겹침은 1.0 m 공간 제외(addendum1)로만 걸러졌다(16,715 패치, 1,106.3 m²). LoD2에서는 이름 기반으로 `DEBY_LOD2_4959325` 62,871 패치를 뺐다.
- `DEBY_LOD2_4959325`는 LoD2에서 B173nb_b10 사이트 건물(source 2)이다. ALS에서는 공간 제외 뒤에도 JUDGECHECK 행 6,246개가 남아 121개 안에 있다.
- ALS 배경 33 = LoD2 배경 19 전부 + 14. 이 14 가운데 10은 LoD2 기준 사이트 건물(DEBY_LOD2_108580335, DEBY_LOD2_108580336, DEBY_LOD2_4906968, DEBY_LOD2_4906975, DEBY_LOD2_4959322, DEBY_LOD2_4959323, DEBY_LOD2_4959324, DEBY_LOD2_4959326, DEBY_LOD2_4959460, DEBY_LOD2_4959793)이다. ALS에서는 이름이 `''`인 사이트 행으로 대상에 들어 있지만 이름이 없어 배경으로 셈해졌다. 나머지 4(DEBY_LOD2_108247714, DEBY_LOD2_42364663, DEBY_LOD2_4959342, DEBY_LOD2_60098)는 ALS JUDGECHECK에 행이 없다.

## 출처

- 코드: `scripts/phd/main_trainunit_v1/tu_campus.py` `targets()`: 사이트 행 building 169행(`raw['building']`, stage0_r1/inputs/<site>_<prior>.npz), 이름 기반 사이트 제외 136행, judged 194행, unjudged 207행
- `$TU1/targets/campus__ALS.npz`, `campus__LoD2.npz`(np.load, allow_pickle=False), 같은 이름의 `.json`
- `$ART/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/lod2_buildings.json`
- 계산: jointbuildgs:dev 컨테이너, CPU, 읽기 전용 마운트
