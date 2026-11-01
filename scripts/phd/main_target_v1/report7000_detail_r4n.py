"""Source-backed pilot detail, fixed camera, large-background ancestry and score tables."""
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save

def read(p):return json.loads(p.read_text()) if p.exists() else None
def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}
def pct(x):return f'{100*x:.3f}%' if x is not None else '확인 불가'

def main():
    rep=next(x for x in read(CFG/'representatives_v1.json')['rows'] if x['id']==1)
    text=['# 7,000회 점검 · r4n','',
        '항공 LiDAR 판의 목표 따름 32.724%가 발주 3.6과 11/1 r3 결정의 80% 기준에 미달해 두 판을 멈췄다. 두 판의 7,000회 모델을 보존했다. 나머지 여섯 판과 30,000회 학습은 진행하지 않았다. [이 발주에서 냄]','',
        '3.5는 사용자가 씨앗 위치·패치 하나씩의 렌더·목표 높이 복원으로 통과 처리했다. 학습 후 목표 따름의 분모는 사전 패치 원반과 배경 MVS를 포함한 모든 유효 목표 화소이며, 렌더 깊이 없음도 미달로 센다. 아래의 분해 표는 원인을 살펴보는 기록이며 통과 기준을 바꾸지 않는다.','']
    plotrows=[]
    for prior in ['ALS','LoD2']:
        run=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0';model=run/'model';root=model/'check7000'
        verification=read(run/'verification7000.json');cover=read(root/'coverage.json');score=read(run/'post7000/score.json')
        a=read(root/'large_background_descendants.json');text +=[f'## {prior}','']
        if cover:
            text +=[f"전체 목표 따름: {cover['inside']:,} / {cover['target_pixels']:,} = **{pct(cover['fraction'])}** ({cover['status']}, 기준 80%).",'']
            if 'readout_completion' in cover:text +=['공동 중단으로 끊긴 점검 영상을 저장 모델로 마저 렌더했다. 원래 저장된 영상은 보존했고 재렌더한 네 영상의 깊이가 바이트 단위로 같음을 확인했다. 추가 최적화는 0회다.','']
        if verification:
            text +=['| 목표 화소 구분 | 화소 수 | 목표 ±1.96σ 안 | 깊이 없음 |','|---|---:|---:|---:|']
            names={'all':'전체','prior':'사전 패치','background':'배경 MVS','prior_roof':'사전 지붕','prior_wall':'사전 벽',
                'prior_original':'사전 원값','prior_replaced':'사전 대체','region_0':'관측 없음','region_1':'일치','region_2':'보존','region_3':'보정'}
            for key,r in verification['strata'].items():
                text.append(f"| {names[key]} | {r['target_pixels']:,} | {pct(r['fraction'])} | {pct(r['missing_fraction'])} |")
                if key in ['all','prior','background','prior_roof','prior_wall']:plotrows.append(dict(prior=prior,label=names[key],**r))
            h=verification['snapshot_health'];text +=['',
                f"저장 당시 가우시안 {h['gaussians']:,}개, 6,000회 기록 대비 {h['count_ratio']:.4f}배, 불투명도 중앙값 {h['opacity_torch_median']:.6f}, 법선 폭 수치 잔차 최대 {h['max_normal_excess_m']*1000:.6f} mm. 마지막 손실 기록은 {h['last_logged_iteration']:,}회이며 모두 유한하다.",
                '목표 따름 미달로 7,000회 밀도 제어 뒤 건강 영수증은 생성되지 않았다. 위 값은 밀도 제어 직전 저장 모델을 독립 계산한 기록으로 구분한다.','']
        if a:
            text +=[f"처음 1 m 초과 배경 씨앗 {a['initial_large_background_count']:,}개 중 {a['surviving_original_ancestors']:,}개 계보의 자손 **{a['surviving_gaussians']:,}개**가 남았다. 원래 씨앗 자신과 복제·분할 자손을 같은 불변 init_id 계보로 합쳐 센다.",'',
                '| 남은 큰 배경 계보 자손 | 최솟값 | 중앙값 | 95% 분위 | 최댓값 |','|---|---:|---:|---:|---:|']
            for key,label in [('size_max_axis_m','긴 축 크기 (m)'),('opacity','불투명도'),('normal_displacement_abs_m','원 목표의 법선 방향 이동 (m)'),('tangent_displacement_m','원 목표 면을 따른 이동 (m)')]:
                q=a[key];text.append('| '+label+' | '+' | '.join(f'{q[k]:.6f}' for k in ['min','median','p95','max'])+' |')
            text +=['','크기는 활성화된 두 접선 축 중 큰 값이다. 법선 이동은 각 부모의 서로 다른 σ 폭과 함께 해석한다. 접선 이동을 묶지 않은 발주 규칙에 따라 큰 이동이 남았다. 이 사실만으로 뜬 면이나 인과를 확정하지 않으며 추가 멈춤 기준으로 쓰지 않는다.','']
            d=loadz(root/'large_background_descendants.npz');s=loadz(model/'target_monitor/snapshot_7000.npz');ids=d['init_id'];anc=np.unique(ids)
            fig,axes=plt.subplots(1,2,figsize=(11,4.5))
            axes[0].scatter(d['xyz'][:,0],d['xyz'][:,1],s=.2,c='#438bb6',alpha=.3,label='7,000회 자손 중심')
            axes[0].scatter(s['anchor'][anc,0],s['anchor'][anc,1],s=8,c='#bd4676',label='남은 계보의 처음 자리')
            axes[0].set(xlabel='지역 동쪽 (m)',ylabel='지역 북쪽 (m)');axes[0].set_aspect('equal');axes[0].legend(fontsize=7)
            axes[1].hist(d['tangent_displacement'],bins=50,color='#438bb6');axes[1].set(xlabel='원 목표 면을 따른 이동 (m)',ylabel='자손 수')
            fig.subplots_adjust(top=.8,bottom=.2,wspace=.3)
            save(fig,f'r4n_{prior}_large_background_spread',f'{prior}: 처음 큰 배경의 남은 계보와 자손',
                {k:v for k,v in a.items() if k!='counts_by_ancestor'},'전체 자손 위치 표시 · 접선 이동 제한 없음 · 뜬 면 여부는 메시 채점으로 별도 확인')
            text +=[f'![큰 배경 자손 분포](figures/r4n_{prior}_large_background_spread.png)','']
            fig,axes=plt.subplots(1,2,figsize=(11,4));sizes=d['scale'].max(1)
            axes[0].hist(sizes,bins=np.geomspace(sizes.min(),sizes.max(),55),color='#438bb6');axes[0].set_xscale('log')
            axes[0].set(xlabel='긴 축 크기 (m, 로그 눈금)',ylabel='자손 수');axes[0].axvline(1,c='black',ls='--',lw=1)
            axes[1].hist(d['opacity'],bins=np.linspace(0,1,51),color='#a94e83');axes[1].set(xlabel='불투명도',ylabel='자손 수',xlim=(0,1))
            fig.subplots_adjust(top=.8,bottom=.2,wspace=.3)
            save(fig,f'r4n_{prior}_large_background_size_opacity',f'{prior}: 처음 큰 배경 계보의 남은 자손 크기와 불투명도',
                dict(size_max_axis_m=a['size_max_axis_m'],opacity=a['opacity'],surviving_gaussians=len(sizes),
                    current_gt_1m=int((sizes>1).sum())),
                '처음 크기 >1 m였던 부모의 계보 전체 · 현재 1 m 이하로 작아진 자손도 포함 · 점선: 현재 크기 1 m')
            text +=[f'![큰 배경 자손 크기와 불투명도](figures/r4n_{prior}_large_background_size_opacity.png)','']
        name=rep['camera']['name'];p=root/'renders'/f'{name}.npz'
        if p.exists():
            d=loadz(p);m=loadz(OUT/'r2/stage1'/f'B173nb_b10_{prior}'/'maps'/f'{name}.npz')
            photo=loadz(OUT/'r2/preflight'/f'B173nb_b10_{prior}'/f'{name}.npz')['photo_rgb'].transpose(1,2,0)
            good=np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0)
            hit=good&np.isfinite(d['depth'])&(d['depth']>0)&(abs(d['depth']-m['depth'])<=1.96*m['sigma'])
            category=np.zeros(good.shape,np.int8);category[good]=1;category[hit]=2
            fig,axes=plt.subplots(1,3,figsize=(12,4))
            for ax,im,title in zip(axes,[photo,d['rgb'],category],['원본 사진','7,000회 렌더','목표 따름: 초록 / 미달: 빨강']):
                if im.ndim==2:ax.imshow(im,cmap=ListedColormap(['#dddddd','#c95d55','#55a577']),vmin=0,vmax=2)
                else:ax.imshow(im)
                ax.set_title(title,fontsize=9);ax.axis('off')
            line=np.c_[np.asarray([rep['start'],rep['end']]),np.full(2,rep['center_xyz'][2])];camera=rep['camera'];M=np.asarray(camera['W2C'])
            q=line@M[:3,:3].T+M[:3,3];u=camera['fx']*q[:,0]/q[:,2]+camera['cx'];v=camera['fy']*q[:,1]/q[:,2]+camera['cy']
            for ax in axes:ax.plot(u,v,color='white',lw=2.5);ax.plot(u,v,color='black',ls='--',lw=1)
            fig.subplots_adjust(top=.83,bottom=.16,wspace=.03)
            save(fig,f'r4n_{prior}_fixed_render',f'B173 날개 고정 영상 · {prior}',dict(camera=name,inside=int(hit.sum()),target_pixels=int(good.sum()),
                render_sha256=sha(p),representative_id=1),'회색: 목표 없음 · 고정한 전체 영상 · 깊이와 σ는 학습 전에 잠근 지도 사용')
            text +=[f'![고정 영상 렌더와 목표 따름](figures/r4n_{prior}_fixed_render.png)','']
            t=loadz(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz');owner=m['owner'];has=owner>=0;patch=np.maximum(owner,0)
            ix=read(OUT/'r2/stage1'/f'B173nb_b10_{prior}'/'maps/index.json')['views'][name]
            K=np.asarray(ix['K']);M=np.asarray(ix['W2C']);inv=np.linalg.inv(M);vv,uu=np.indices(owner.shape)
            q=np.stack([(uu-K[0,2])/K[0,0]*d['depth'],(vv-K[1,2])/K[1,1]*d['depth'],d['depth'],np.ones_like(d['depth'])],-1)
            world=(q.reshape(-1,4)@inv.T)[:,:3].reshape(*owner.shape,3)
            h=((world-t['centre'][patch])*t['normal'][patch]).sum(2);h[~has|(d['depth']<=0)]=np.nan
            h0=np.where(has,t['h'][patch],np.nan);region=np.where(has,t['region'][patch],np.nan)
            fig,axes=plt.subplots(1,3,figsize=(12,4))
            for ax,arr,title in zip(axes[:2],[h0,h],['잠근 목표 h','7,000회 렌더에서 구한 h']):
                im=ax.imshow(arr,cmap='coolwarm',vmin=-5,vmax=5);ax.set_title(title+' (m)',fontsize=9);fig.colorbar(im,ax=ax,fraction=.04,extend='both')
            axes[2].imshow(region,cmap=ListedColormap(['#a78bc2','#54ad80','#e6ab42','#478ac3']),vmin=0,vmax=3);axes[2].set_title('잠근 영역 표지',fontsize=9)
            for ax in axes:ax.axis('off')
            fig.subplots_adjust(top=.82,bottom=.2,wspace=.12)
            save(fig,f'r4n_{prior}_fixed_height',f'{prior}: 같은 사전 패치 법선에서 목표와 렌더 높이를 비교했다',
                dict(camera=name,render_sha256=sha(p),h_color_range_m=[-5,5],finite_h_pixels=int(np.isfinite(h).sum())),
                '사전 원반의 소유 패치를 기준으로 역투영 · 범위 밖은 끝 색 · 영역: 관측 없음 보라 / 일치 초록 / 보존 주황 / 보정 파랑')
            text +=[f'![고정 영상 높이와 영역](figures/r4n_{prior}_fixed_height.png)','']
        if score:
            text +=[f"현재 메시의 칸 0~3 뜬 면: **{pct(score['floating_fraction_cells_0_3'])}** ({score['status']}, 기준 5%).",'',
                '| 구분 | 영역 | 평가 넓이 (m²) | 결과 τ 안 | 목표 자체 τ 안 |','|---|---|---:|---:|---:|']
            for r in score['result_vs_target']:
                text.append(f"| {r['replacement']} | {['관측 없음','일치','보존','보정'][r['region']]} | {r['area_m2']:.3f} | {pct(r['result_within_tau_fraction'])} | {pct(r['target_within_tau_fraction'])} |")
            for suffix in ['section_comparison','within_tau']:
                key=f'r4n_{prior}_{suffix}'
                if (DOC/'figures'/f'{key}.png').exists():text+=['',f'![단면과 같은 자리의 결과](figures/{key}.png)','']
            attribution=read(run/'post7000/origin_attribution.json')
            if attribution:text +=['',f"뜬 면 패치 중 배경 렌더 기여가 절반 이상인 곳 {attribution['floating_background_dominant']:,}개, 처음 1 m 초과 배경 계보 기여가 절반 이상인 곳 {attribution['floating_large_background_dominant']:,}개. 출신 연관 기록이며 인과 확정이 아니다.",'',f'![뜬 면 출신 지도](figures/r4n_B173_{prior}_floating_origin.png)','']
        else:text +=['현재 메시·뜨는 면 비율·결과와 목표의 τ 비교: CPU 계산 중. 완료 전에는 통과나 0으로 적지 않는다.','']
    if plotrows:
        fig,axes=plt.subplots(1,2,figsize=(11,4))
        for ax,prior in zip(axes,['ALS','LoD2']):
            rows=[r for r in plotrows if r['prior']==prior];ax.bar(range(len(rows)),[100*r['fraction'] if r['fraction'] is not None else np.nan for r in rows],color='#438bb6')
            ax.axhline(80,color='black',ls='--');ax.set(xticks=range(len(rows)),xticklabels=[r['label'] for r in rows],xlim=(-.5,len(rows)-.5),ylim=(0,100),ylabel='목표 폭 안 (%)',title=prior)
            for i,r in enumerate(rows):
                if r['fraction'] is not None:ax.text(i,100*r['fraction']+2,f"{100*r['fraction']:.1f}",ha='center',fontsize=8)
                else:ax.text(i,4,'목표 없음',ha='center',fontsize=8)
        fig.subplots_adjust(top=.8,bottom=.2,wspace=.25)
        save(fig,'r4n_coverage_parts','7,000회: 목표가 있는 화소의 깊이 따름',plotrows,'점선: 전체 화소의 80% 기준 · 부분별 막대는 원인 분해 기록 · 깊이 없음도 미달로 셈')
        text +=['![목표 따름 분해](figures/r4n_coverage_parts.png)','']
    text +=['처음 불투명도는 사전·배경 모두 0.1로 기준선과 같다. [불투명도 실제 배열](처음불투명도_r4n.md)과 [처음 크기 상위 열 개](초기배경_크기_r3.md)를 함께 보존한다.','',
        '현재 메시의 채점은 기존 MESHPATCH 첫 면 채점이며, 참값은 메시 평가 범위와 채점에만 쓴다. 판단·목표·손실·폭에는 넣지 않았다. 배경 출신 지도는 저장된 렌더 기여에 따라 구분하며 보이는 영상이 없는 점은 확인 불가로 둔다.','',
        '최종 메시·30,000회·나머지 여섯 판·비교 방법의 새 채점은 수행하지 않았다. scientific_verdict: null.','',stamp()]
    (DOC/'단계1_7000회_점검_r4n.md').write_text('\n'.join(text)+'\n');print('DETAIL_REPORT_7000',flush=True)

if __name__=='__main__':main()
