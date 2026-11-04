"""Compact requested metadata and previous-work comparisons; no new decisions."""
from common import *
from tables import write_table
def main():
    cal=json.loads((O/'calibration.json').read_text());limits=json.loads((D/'tables/limits.json').read_text())['rows'];comparisons=[];photos=[];points=[];schemas=[]
    for r in cal['r_rows']:
        key=f'{r["prior"]}_{r["kind"]}';p=R/'docs/experiments/phd/main_judgecheck_v1/tables'/f'{key}_6_5_geometry.json'
        old=json.loads(p.read_text())['rows'];oldlim={v['q']:v for v in old if v['metric']=='limit_quantile'}
        lim=next(x for x in limits if (x['site'],x['prior'],x['kind'])==(r['site'],r['prior'],r['kind']))
        comparisons.append(dict(**r,sigma_W_m=cal['sigma_W_m'],sigma_W_building_count=cal['building_count'],sigma_W_site_building_count=cal['buildings_per_site'][r['site']],
            previous_r_m=cal['prior_reference_only']['r_m'][key],previous_sigma_W_m=cal['prior_reference_only']['sigma_W_m'],
            **{k:v for k,v in lim.items() if k.startswith('L_')},L_count=lim['count'],
            previous_L_q25_m=oldlim[.25]['value_m'],previous_L_median_m=oldlim[.5]['value_m'],previous_L_q75_m=oldlim[.75]['value_m'],previous_L_count=oldlim[.5]['count'],previous_source=str(p),previous_values_used_for_decision=False))
    for site in cfg()['sites']:
      photos.extend(json.loads((D/'tables'/f'{site}_photo_thresholds.json').read_text())['rows'])
      for prior in cfg()['priors']:
        g=loadz(O/'photo_geometry'/f'{site}__{prior}.npz');new=np.array([str(x).startswith('[이 발주에서 냄]') for x in g['source']])
        for k in cfg()['priors'][prior]:
          for label,m in [('all',g['kind']==k),('created',(g['kind']==k)&new),('inherited',(g['kind']==k)&~new),('scored',(g['kind']==k)&g['target'])]:
            points.append(dict(site=site,prior=prior,kind=k,subset=label,count=int(m.sum()),core_count=int(g['patch_count'][m].sum()),area_m2=float(g['area'][m].sum()),source=f'photo_geometry/{site}__{prior}.npz'))
        for folder in ['core_points','photo_points','training_regions']:
          p=O/folder/f'{site}__{prior}.npz';d=loadz(p)
          schemas.append(dict(file=f'{folder}/{p.name}',sha256=sha(p),fields={k:dict(shape=list(v.shape),dtype=str(v.dtype)) for k,v in d.items()}))
    write_table('calibration_comparison',comparisons);write_table('photo_thresholds',photos);write_table('photo_point_scope',points)
    write_table('sigma_W_buildings',cal['buildings']);dump(D/'tables/file_schema.json',dict(files=schemas,scientific_verdict=None))
    (D/'training_schema.md').write_text('''# 학습용 판단 파일 대응표

`training_regions/<지역>__<사전 정보>.npz` 6개. 평가 핵심점만 포함하며 `source_index`로 TARGET 단계 0 전체 배열에 대응한다. `patch_id`는 이 대응을 사람이 읽을 수 있는 문자열이다. 좌표계 EPSG:25832 기반 원래 지역 좌표, 길이 단위 m.

| 열 | TARGET 대응과 뜻 |
| --- | --- |
| centre, normal, kind, area, building, surf, in_eval | 단계 0의 같은 이름. ALS normal은 이번 LiDAR 점 평면 법선 |
| region | TARGET 번호: 0 결측, 1 일치, 2 보존, 3 보정, 5 빈 공간; -1 확인 불가 |
| judge_region | 발주 번호: 0 일치, 1 보존, 2 보정, 3 빈 공간, 4 결측, 9 확인 불가 |
| reason | 0 사진 지지, 1 사진 반박, 2 기본 판단, 9 해당 없음 |
| h_no_r, h_with_r | TARGET h에 대응하는 두 선택지. centre 기준 normal 방향 높이 |
| target_no_r, target_with_r | TARGET target에 대응하는 두 선택지: centre + h × normal |
| u / u_M, sigma_p / sigma_P, sigma_W | 개별 표준 불확실성. 합성값으로 덮어쓰지 않음 |
| surface_exists | 일치·보존·보정·결측의 목표면 존재; 빈 공간과 확인 불가 false |

r 적용법을 정하지 않았으므로 단일 `h`/`target`은 만들지 않았다. 다음 학습 실행에서 두 선택지 중 하나를 명시해야 한다. 빈 공간과 확인 불가의 목표는 NaN; 확인 불가는 삭제 지시가 아니다. 이번 작업은 학습하지 않았다.

사진 점 번호는 과거 지붕·벽 파일에서 중복될 수 있다. `point_uid` 또는 `(kind, point_index)`가 파일 내 고유 키이며 핵심점의 `photo_point_uid`와 연결된다. `selected_images`는 지역 `split.json`의 학습 사진 순서(0 시작), -1은 빈 자리다. `centres[:,0/1]`, `normals[:,0/1]`은 사전 정보/MVS 후보 면이며 `mvs_fit_height_m`는 사진 점 중심 기준 사전 정보 법선 방향 높이다. `threshold_sample`은 표본으로 선택한 점, `threshold_used`는 그중 유한한 s_P로 분위수에 기여한 점이다.

사진 판단 9는 t 등을 구할 수 없어 판정 불가이며 기본 판단을 적용한다. 발주 0~7 번호와 겹치지 않는다. 기하 결과 0 한계 안, 1 한계 밖, 2 n<4, 9 확인 불가. 참값 칸 9는 사전 정보 높이/법선 자체가 없어 평가할 수 없는 별도 상태로 유지했다.
scientific_verdict: null
''')
    print('SUPPLEMENT_COMPLETE',flush=True)
if __name__=='__main__':main()
