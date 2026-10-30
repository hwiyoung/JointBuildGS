"""Finish and publish stage A before selecting minimum area or photo thresholds."""
import json
from pathlib import Path
import numpy as np
from analyse import load,read_counts,read_stats,save,area_rows
from analysis_core import radius_table,judgment
from cylinder_runtime import RADII
from lock_config import dump,sha,stamp
O=Path('/out');D=Path('/docs');C=Path('/cfg')

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());radiusrows=[];areas=[];oldrows=[];normal=[];chosenall={}
    target=O/'core_points_stage_a';target.mkdir(exist_ok=True)
    for prior in ['LoD2','ALS']:
        d,where=load(prior);counts=read_counts(where,0);chosen,rr=radius_table(counts,d['kind'],prior,RADII)
        radiusrows+=rr;chosenall[prior]=chosen;stats=read_stats(where,0,d['kind'],chosen);j,DL=judgment(d,stats,1.96)
        areas += [r for r in area_rows(d,j,j,DL,prior,'base') if r['stage']=='before']
        valid=(j>=0)&(j<2);old=j.copy();tau=cfg['detection']['old_comparison_tau_m'][prior]
        old[valid]=(np.abs(stats[valid,1])>np.maximum(DL[valid],tau)).astype(np.int8)
        for kind in [1,2]:
            m=d['kind']==kind
            oldrows.append({'prior':prior,'kind':kind,'changed_patch_count':int((m&(old!=j)).sum()),
                'changed_area_m2':float(d['area'][m&(old!=j)].sum())})
            normal.append({'prior':prior,'kind':kind,'patch_count':int(m.sum()),'area_m2':float(d['area'][m].sum()),
              'undefined_axis_count':int((m&~d['normal_defined']).sum()),
              'undefined_axis_area_m2':float(d['area'][m&~d['normal_defined']].sum()),
              'scale_25_status':'해당 없음: LoD2 면 법선' if prior=='LoD2' else '확인 불가: TIN 법선, 평면 맞춤 둘레와 거칠기 없음',
              'below_25_count':None,'below_25_area_m2':None})
        d.update({'n':stats[:,0].astype(np.int64),'d_mean_cm':stats[:,1]*100,'d_median_cm':stats[:,2]*100,
            's_cm':stats[:,3]*100,'s_nmad_cm':stats[:,4]*100,'face_o_m':stats[:,5],
            'DL_cm':DL*100,'a_cm':d['mvs_a_a'].astype(float)*100,'sigma_p_cm':d['sigma_p']*100,
            'a_missing':~np.isfinite(d['mvs_a_a']),'judgment_before':j,
            'chosen_radius_m':np.where(d['kind']==1,chosen[1]['radius_m'] or np.nan,chosen[2]['radius_m'] or np.nan)})
        for w in where:
            sl=slice(w['offset'],w['offset']+w['count']);np.savez_compressed(target/f"{w['tile']}__{prior}.npz",**{k:v[sl] for k,v in d.items()})
        print('STAGE_A',prior,chosen,flush=True)
    for name,rows in [('stage_a_radius_candidates',radiusrows),('stage_a_judgment_areas',areas),
                      ('stage_a_old_rule_comparison',oldrows),('stage_a_normal_checks',normal)]:save(name,rows)
    dump(O/'stage_a_complete.json',{'status':'COMPLETE_WITH_UNAVAILABLE_ROWS','at':stamp(),
      'chosen_radius':chosenall,'scientific_verdict':None})
    report=D/'중간보고_v1.md';text=report.read_text().split('\n## 단계 가 계산 결과',1)[0]
    text=text.replace('원통 반지름·최소 넓이·사진 조합·threshold2는 아직 정하지 않았다.',
      '원통 반지름은 아래 표에 기록했다. 최소 넓이·사진 조합·threshold2는 아직 정하지 않았다.')
    text=text.replace('원통 셈 시간 검사는 진행 중이다.','원통 셈 시간 검사 통과. 한 구역 535.93초 × 24구역 = 약 3.57시간이다. 덩어리 분석과 그림 시간은 별도다.')
    text += '\n## 단계 가 계산 결과\n\n| 사전 정보 | 패치 | 원통 반지름 m | 중앙값 20 도달 |\n|---|---|---:|---|\n'
    for prior,gg in chosenall.items():
        for kind,r in gg.items():text+=f"| {prior} | {'지붕' if kind==1 else '벽'} | {r['radius_m'] if r['radius_m'] is not None else '해당 없음'} | {r['target_reached']} |\n"
    text+='\n| 사전 정보 | 패치 | 같음 m² | 어긋남 m² | 상속 m² | 확인 불가 m² |\n|---|---|---:|---:|---:|---:|\n'
    for r in areas:
        if r['roof_type']=='all':text+=f"| {r['prior']} | {'지붕' if r['kind']==1 else '벽'} | {r['same_area_m2']:.6f} | {r['different_area_m2']:.6f} | {r['inherit_area_m2']:.6f} | {r['unavailable_area_m2']:.6f} |\n"
    text+='\n[후보 반지름 전체 표](tables/stage_a_radius_candidates.md), [지붕 형태별 판단 넓이](tables/stage_a_judgment_areas.md), [옛 규칙과의 비교](tables/stage_a_old_rule_comparison.md), [법선 확인](tables/stage_a_normal_checks.md).\n'
    text+='\n항공 LiDAR의 25배 법선 규칙은 필요한 평면 맞춤 둘레와 잔차 표준 편차가 없어 확인 불가다. 미달 수를 0으로 적지 않았다. 법선 미정의 또는 n≥4에서 사전 정보 흔들림 미정의인 곳은 판단 번호 -1로 따로 보존하며, 상속으로 바꾸지 않았다.\n'
    report.write_text(text)
    (D/'progress.md').write_text('# PHD-MAIN-JUDGENUM-v1 진행\n\n'+f'- 갱신: {stamp()}\n- 단계 가: 계산 완료, 확인 불가 행 보존\n- 원통 셈: 설정용 21구역 완료\n- 시간 어림: 3.57시간, 기준 통과\n- 단계 나: 중간 보고와 커밋 뒤 재개\n- 확인용: 아직 실행하지 않음\n- scientific_verdict: null\n')

if __name__=='__main__':main()
