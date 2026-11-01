"""Current pilot status, curves, inherited background ancestry and mesh associations."""
import re
import numpy as np
from common import *
from report_stage0 import plt,save

def read(p):return json.loads(p.read_text()) if p.exists() else None
def main():
    root=OUT/'r4n';rows=[];curves={};ancestry=[]
    for prior in ['ALS','LoD2']:
        run=root/'runs'/f'tg_B173nb_b10_{prior}_s0';model=run/'model';mon=model/'target_monitor'
        curve=[json.loads(s) for s in (mon/'curve.jsonl').read_text().splitlines()] if (mon/'curve.jsonl').exists() else []
        curves[prior]=curve;coverage=read(model/'check7000/coverage.json');health=read(mon/'health_7000.json');score=read(run/'post7000/score.json')
        r=dict(prior=prior,last_recorded_iteration=curve[-1]['iteration'] if curve else 0,
            model7000=(model/'point_cloud/iteration_7000/point_cloud.ply').exists(),
            coverage=coverage['fraction'] if coverage else None,coverage_status=coverage['status'] if coverage else 'NOT_AVAILABLE',
            opacity7000=health['target_opacity_median'] if health else None,health_status=health['status'] if health else 'NOT_AVAILABLE',
            floating_fraction=score['floating_fraction_cells_0_3'] if score else None,floating_status=score['status'] if score else 'NOT_AVAILABLE',
            execution_receipt=read(run/'receipt.json'),stop=read(mon/'STOP.json'))
        v=read(run/'verification7000.json');r['saved_model_health']=v['snapshot_health'] if v else None
        rows.append(r)
        a=read(model/'check7000/large_background_descendants.json')
        if a:ancestry.append(dict(prior=prior,**a))
    joint=read(root/'STOP_BOTH.json');passed=all(r['coverage_status']=='PASS' and r['health_status']=='PASS_HEALTH' and r['floating_status']=='PASS' for r in rows)
    state=dict(at=stamp(),status='STOP_PILOT' if joint else ('PASS_7000' if passed else 'RUNNING_OR_CHECKING'),rows=rows,
        shared_stop=joint,large_background=ancestry,scientific_verdict=None)
    dump(root/'pilot_status.json',state);dump(DOC/'tables/pilot_status_r4n.json',state)
    fig,ax=plt.subplots(2,2,figsize=(11,6))
    for prior,color in [('ALS','#438bb6'),('LoD2','#ce8f36')]:
        c=curves[prior]
        if not c:continue
        it=[r['iteration'] for r in c]
        for a,key,mult in [(ax[0,0],'loss',1),(ax[0,1],'target_opacity_median',1),(ax[1,0],'gaussians',1),(ax[1,1],'max_normal_excess_m',1000)]:
            a.plot(it,[r[key]*mult for r in c],label=prior,color=color,lw=1.2)
    for a,title,ylab in [(ax[0,0],'기록된 전체 손실','손실'),(ax[0,1],'목표 씨앗 자손의 불투명도','중앙값'),
        (ax[1,0],'가우시안 수','개'),(ax[1,1],'목표 폭 바깥의 수치 잔차','mm')]:
        a.set(title=title,xlabel='반복',ylabel=ylab);a.grid(alpha=.15);a.legend(fontsize=8)
    ax[0,1].axhline(.05,color='black',ls='--',lw=.8);ax[1,1].axhline(.03,color='black',ls='--',lw=.8)
    fig.subplots_adjust(top=.86,bottom=.14,hspace=.65,wspace=.3)
    save(fig,'r4n_training_curves','두 사전 정보의 학습과 수치 폭 점검',state,'불투명도 재설정은 기준선 일정 그대로 · 폭·허용치 유지 · 수치 잔차는 float64로 확인')
    rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1)
    for prior in ['ALS','LoD2']:
        run=root/'runs'/f'tg_B173nb_b10_{prior}_s0';model=run/'model';seven=model/'target_monitor/snapshot_7000.npz'
        if seven.exists():
            with np.load(seven) as z:s={k:z[k] for k in z.files}
            with np.load(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz') as z:t={k:z[k] for k in z.files}
            with np.load(OUT/'r2/stage0/evaluation'/f'B173nb_b10_{prior}.npz') as z:e={k:z[k] for k in z.files}
            a,b=np.asarray(rep['start']),np.asarray(rep['end']);direction=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a)
            def crop(x):
                q=x[:,:2]-a;dist=q@direction;off=abs(q[:,0]*direction[1]-q[:,1]*direction[0]);return dist,(dist>=0)&(dist<=length)&(off<=rep['half_width'])
            dist,mask=crop(t['centre']);mask&=(t['kind']==1)&(t['region']>=0);ds,ms=crop(s['xyz']);bg=s['origin']==0
            fig,axes=plt.subplots(1,2,figsize=(12,4.5))
            for axis in axes:
                axis.scatter(dist[mask],t['centre'][mask,2]+e['gt_med'][mask]*t['normal'][mask,2],s=7,c='black',label='참값')
                axis.scatter(dist[mask],t['target'][mask,2],s=7,c='gray',label='목표')
                axis.set(xlabel='고정 단면 거리 (m)',ylabel='지역 높이 (m)')
            axes[0].scatter(ds[ms&~bg],s['xyz'][ms&~bg,2],s=3,c='#bd4676',label='7,000회 사전 출신')
            axes[1].scatter(ds[ms&bg],s['xyz'][ms&bg,2],s=3,c='#438bb6',label='7,000회 배경 출신')
            for axis in axes:axis.legend(fontsize=7)
            zlim=[float(np.min(t['target'][mask,2])-3),float(np.max(t['target'][mask,2])+3)]
            for axis in axes:axis.set_ylim(zlim)
            fig.subplots_adjust(top=.8,bottom=.2,wspace=.3)
            save(fig,f'r4n_B173_{prior}_section',f'B173 날개 {prior}: 7,000회 중심을 출신별로 나누어 보았다',
                dict(prior=prior,view=rep,prior_centers=int((ms&~bg).sum()),background_centers=int((ms&bg).sum()),z_limits=zlim),
                '목표 높이 범위 ±3 m 확대 · 범위 밖 중심은 별도 저장 · 학습 후 중심이며 결과 메시와 구분')
        attrib=run/'post7000/origin_attribution.npz'
        if attrib.exists():
            with np.load(attrib) as z:d={k:z[k] for k in z.files}
            floating=d['in_eval']&(d['category']==1);visible=d['views']>0;big=d['large_background_dominant'];bg=d['background_dominant']
            fig,ax=plt.subplots(figsize=(7,5));base=d['in_eval']&np.isfinite(d['hit_xyz']).all(1)
            ax.scatter(d['hit_xyz'][base,0],d['hit_xyz'][base,1],s=.5,c='lightgray',label='평가 첫 면')
            for label,sel,color in [('뜬 면: 사전 기여 우세',floating&visible&~bg,'#ce8f36'),('뜬 면: 배경 기여 우세',floating&visible&bg&~big,'#438bb6'),
                ('뜬 면: 처음 큰 배경 기여 우세',floating&visible&big,'#b44b73'),('뜬 면: 출신 확인 불가',floating&~visible,'#444444')]:
                ax.scatter(d['hit_xyz'][sel,0],d['hit_xyz'][sel,1],s=3,c=color,label=label)
            ax.set_aspect('equal');ax.set(xlabel='지역 동쪽 (m)',ylabel='지역 북쪽 (m)');ax.legend(fontsize=7)
            fig.subplots_adjust(top=.83,bottom=.18)
            save(fig,f'r4n_B173_{prior}_floating_origin',f'B173 주변 {prior}: 뜬 면과 배경 출신 렌더 기여',read(run/'post7000/origin_attribution.json'),
                '보이는 영상의 평균 기여 ≥50%로 표시 · 출신 연관 기록이며 인과 확정 아님 · 새 멈춤 기준 없음')
    base=(DOC/'영역별목표학습_보고_r3.md').read_text();parts=re.split(r'^## [1-8]\. [^\n]+\n',base,flags=re.M)
    text=['# 영역별 목표 학습 보고 v1 · r4n','',
        '판단 정확도: r2의 값과 목표를 그대로 유지했다. 개발용·확인용·실험 지역과 대체 패치 비교는 단계 0 표에 있다.',
        '7,000회 점검: '+state['status']+'. '+('두 판 모두 목표 따름 80% 미달로 학습을 멈췄다.' if joint else '아래 표에서 실제 저장·채점 상태를 구분한다.'),
        '8판의 네 값: 아직 완료되지 않았다.',
        'GS와 목표로 바로 만든 메시 비교: 아직 실행하지 않았다.',
        '확인 불가와 시간: 미완료 값은 아래에 명시하며 계산 영수증을 보존한다. scientific_verdict: null.','',
        '## 1. 현재 상태','',
        '11/1 r4n 후속 결정에 따른 저장 기준선 비교, 개별 최대 기여 출신, 두 출신의 이동, 자리별 판단 집계를 완료했다. [중단 후 비교·진단](중단후_비교진단_r5.md)과 [자리별 판단 점검](자리별_판단점검_r5.md)을 함께 본다. 80%는 유지했고 나머지 여섯 판은 시작하지 않는다. 최적화 상태가 없어 기록용 이어 학습은 실행하지 않았다.','',
        '사용자의 11/1 r3 결정으로 3.5 렌더 깊이 비교는 통과 기준에서 내렸다. 씨앗 위치·개별 패치 렌더·목표 지도 높이 복원의 세 검증으로 초기화를 통과 처리했다. 기존 전체 렌더 오차와 깊이 없음은 참고 기록이다.','',
        '첫 r4 실행은 ALS 6,100회의 float32 수치 폭 검사에서 멈췄고 두 판을 보존했다. 실제 6,000회 자손 자료에서 반올림으로 허용치를 넘는 사례를 재현했다. 폭과 허용치를 바꾸지 않고 묶기·잔차의 중간 계산을 float64로 고친 r4n을 새로 잠갔다. 6,156,164개 위치와 실제 복제·분할·제거 점검을 통과한 뒤 두 판을 씨앗 0으로 다시 시작했다.','',
        '## 2. 단계 0: 판단과 목표',parts[2],
        '## 3. 단계 1: 학습과 7,000회 점검','',
        '[7,000회 상세 점검: 목표 따름 분해·큰 배경 자손의 크기와 불투명도·고정 영상](단계1_7000회_점검_r4n.md)','',
        '[구현 변경 파일·줄과 재현 경계](구현과_재현_r4n.md)','',
        '| 사전 정보 | 마지막 기록 반복 | 7,000회 모델 | 목표 따름 | 불투명도 / 건강 | 뜬 면 0~3 |','|---|---:|---|---|---|---|']
    for r in rows:
        cov=f"{100*r['coverage']:.3f}%" if r['coverage'] is not None else '확인 불가'
        floating=f"{100*r['floating_fraction']:.3f}%" if r['floating_fraction'] is not None else '확인 불가'
        health=f"{r['opacity7000']:.6f} / {r['health_status']}" if r['opacity7000'] is not None else (f"저장 모델 {r['saved_model_health']['opacity_torch_median']:.6f}, 밀도 제어 뒤 기록 없음" if r['saved_model_health'] else '확인 불가')
        text.append(f"| {r['prior']} | {r['last_recorded_iteration']} | {'있음' if r['model7000'] else '없음'} | {cov} / {r['coverage_status']} | {health} | {floating} / {r['floating_status']} |")
    text+=['','기준은 목표 따름 80% 이상, 불투명도 중앙값 0.05 이상·손실 유한·6,000회 대비 수 3배 이하, 칸 0~3 뜬 면 5% 이하다. 사용자 지정대로 추가 큰 배경 기록은 멈춤 기준이 아니다.','',
        '![학습 곡선](figures/r4n_training_curves.png)','',
        '처음 불투명도는 두 판의 사전 목표와 MVS 배경 모두 0.1로 기준선과 같다. [실제 초기 배열과 표](처음불투명도_r4n.md)에 수·최소·중앙·최대와 해시를 기록했다. 배경 크기는 상한 없는 기준선 규칙 그대로다. [1 m 초과 개수·상위 열 개·위치 지도](초기배경_크기_r3.md)를 유지한다.','',
        '[초기 렌더 참고값](단계1_r3_재점검.md) · [수치 진단](tables/normal_projection_diagnosis_r4.json) · [수정 검증](tables/runtime_bounds_r4n.json)','',
        '### 처음 큰 배경의 자손','',
        '| 사전 정보 | 처음 1 m 초과 씨앗 | 7,000회 남은 자손 | 남은 원래 계보 수 |','|---|---:|---:|---:|']
    for a in ancestry:text.append(f"| {a['prior']} | {a['initial_large_background_count']} | {a['surviving_gaussians']} | {a['surviving_original_ancestors']} |")
    if not ancestry:text.append('| 아직 해당 모델 없음 | 확인 불가 | 확인 불가 | 확인 불가 |')
    if ancestry:
        text+=['','| 사전 정보 | 크기 중앙 / 최대 (m) | 불투명도 중앙 / 최대 | 접선 이동 중앙 / 최대 (m) |','|---|---:|---:|---:|']
        for a in ancestry:
            q=a['size_max_axis_m'];o=a['opacity'];t=a['tangent_displacement_m']
            text.append(f"| {a['prior']} | {q['median']:.3f} / {q['max']:.3f} | {o['median']:.4f} / {o['max']:.4f} | {t['median']:.3f} / {t['max']:.3f} |")
    text+=['','크기·불투명도·접선/법선 이동의 분포와 개별 자손 배열을 7,000회 모델에 저장한다. 멀리 퍼졌다는 사실만으로 뜬 면이라 부르지 않는다. 실제 메시 첫 면의 뜬 면 분류와 렌더 출신 기여를 함께 기록한다.','',
        '## 4. 단계 2: 본 학습과 채점','',
        '최신 사용자 결정으로 나머지 여섯 판은 시작하지 않는다. 두 판의 7,000회 메시·뜨는 면·목표 자체와 결과의 τ 비교는 완료했다. 30,000회 본 학습·최종 네 값·목표 직접 메시 비교는 실행하지 않았다. 기록용 이어 학습도 최적화 상태 부재로 미실행이다.','',
        '## 5. 비교 방법','기존 깊이 손실 30,000회 모델과 영상 2DGS 7,000회 모델을 동일한 r4n 목표 지도로 비교했다. [구분별 목표 따름 표](중단후_비교진단_r5.md)에 전체·사전·배경·지붕·벽·영역·대체를 기록했다. 재학습 0회.',parts[5].replace('이번 학습 결과가 없으므로 같은 메시 방식의 성능 비교 표를 아직 작성하지 않았다.','7,000회 결과의 메시 채점은 완료했으며 30,000회 최종 네 값 비교는 실행하지 않았다.'),
        '## 6. 대표 자리 그림','']
    for prior in ['ALS','LoD2']:
        for key in [f'r2_stage1_rep1_{prior}_section',f'r4n_B173_{prior}_section',f'r4n_{prior}_fixed_render',f'r4n_B173_{prior}_floating_origin']:
            if (DOC/'figures'/f'{key}.png').exists():text +=[f'![B173 {prior}](figures/{key}.png)','']
    text+=['나머지 고정 자리의 초기 목표·단면·렌더는 [r3 기록](영역별목표학습_보고_r3.md)에 보존한다.','',
        '## 7. 미리 정한 물음과 현재 증거','',
        '영역별 결과와 목표의 τ 안 비율은 7,000회 메시 채점이 끝난 판의 표에 기록한다. 학습 결과, 목표로 만든 메시, 비교 방법이 갖춰지기 전 성능 향상이나 과학적 결론을 내리지 않는다.','',
        '## 8. 출처·변경·확인 불가·시간','',
        'LoD2 σP 출처: '+json.loads((CFG/'target_v1.stage1.r4n.json').read_text())['lod2_sigma_provenance']['statement'],'',
        '최초 r4 실행, 실제 6,000회 모델, 종료 영수증과 수치 오류 재현을 보존했다. r4n은 학습 값을 다시 고른 판이 아니라 같은 목표 폭을 계산하는 수치 구현 수정이다. 실제 6,100회 실패 텐서가 없어 그 점의 정확한 재현은 확인 불가다. 수정 후에는 추가 중단 시 해당 반복 배열도 저장한다.','',
        '이 보고서 시각: '+stamp()+'. 확인용 상세는 외부 holdout/r2에 두며 공개 묶음에는 포함하지 않는다. `scientific_verdict: null`.','']
    body='\n'.join(text);(DOC/'영역별목표학습_보고_r4n.md').write_text(body);(DOC/'영역별목표학습_보고_v1.md').write_text(body)
    print('PILOT_REPORT_R4N',state['status'],flush=True)

if __name__=='__main__':main()
