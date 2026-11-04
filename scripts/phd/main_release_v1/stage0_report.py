"""Stage 0 tables, requested four plots, and fact-only report."""
from common import *
import itertools
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib import font_manager
for font in Path('/fonts').glob('*.ttc'):font_manager.fontManager.addfont(str(font))
plt.rcParams['font.family']=['Noto Sans CJK JP','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
NAMES={'prior':'사전 정보','mvs':'MVS','fusion':'결합','baseline_30000':'기준선','GeoGS_30000':'GeoGS','2DGS_30000':'2DGS','CDGS_30000':'CDGS','judgment_mesh':'판단 조합','FINALTRAIN_30000':'V0'}
def readrows(p):return json.loads(p.read_text())['rows']
def artifact(fig,name,meta):
    p=D/'figures/stage0'/name;p.parent.mkdir(parents=True,exist_ok=True);fig.savefig(p.with_suffix('.png'),dpi=200,bbox_inches='tight');plt.close(fig)
    dump(p.with_suffix('.json'),dict(**meta,scientific_verdict=None))
def main():
    c=cfg();allrows=[];mismatch=[];repro=[];scene=[];quality=[];cross=[]
    for site in SITES:
        for prior in ['ALS','LoD2']:
            stem=f'{site}__{prior}';root=D/'tables/stage0';receipt=O/'stage0'/stem/'receipt.json';assert json.loads(receipt.read_text())['status']=='PASS'
            with (root/(stem+'_table4.csv')).open() as f:
                for row in csv.DictReader(f):
                    for k in ['tau_multiplier','completeness','accuracy','gt_mean_m','result_mean_m']:row[k]=float(row[k]) if row[k] else None
                    for k in ['cell','n_gt','n_result']:row[k]=int(row[k])
                    allrows.append(row)
            for suffix,dest in [('mismatch',mismatch),('reproduction',repro),('scene',scene),('target_judgment',quality),('crosswalk',cross)]:dest.extend(readrows(root/(stem+'_'+suffix+'.json')))
    table('stage0/table4_all',allrows,csv_only=True);table('stage0/mismatch',mismatch);table('stage0/scene_tau',scene);table('stage0/crosswalk',cross)
    summary=[]
    for factor,mode,scope,method in itertools.product(c['stage0']['tau_multipliers'],['original','score'],['B173_B0','all_six'],c['stage0']['methods']):
        pool=[r for r in allrows if r['tau_multiplier']==factor and r['cell_basis']==mode and r['cell'] in [0,1,2,4] and (scope=='all_six' or r['site']!='R1rep_b10') and r['completeness'] is not None]
        best={}
        for r in pool:
            if r['method']=='judgment_mesh':continue
            key=(r['site'],r['prior'],r['cell']);best[key]=max(best.get(key,-1),r['completeness'])
        mine=[r for r in pool if r['method']==method];gaps=[(best[(r['site'],r['prior'],r['cell'])]-r['completeness'])*100 for r in mine]
        if not mine:continue
        worst=max(range(len(mine)),key=lambda i:gaps[i]);r=mine[worst]
        summary.append(dict(tau_multiplier=factor,cell_basis=mode,scope=scope,method=method,minimum_completeness_pct=100*min(x['completeness'] for x in mine),max_gap_pp=gaps[worst],max_gap_site=r['site'],max_gap_prior=r['prior'],max_gap_cell=r['cell'],cells_count=len(mine),small_cells_count=sum(x['n_gt']<1000 for x in mine),within_3pp=sum(g<=3+1e-10 for g in gaps),within_5pp=sum(g<=5+1e-10 for g in gaps),within_10pp=sum(g<=10+1e-10 for g in gaps),small_cells_included=True))
    table('stage0/summary',summary)
    changes=[]
    for mode,scope in itertools.product(['original','score'],['B173_B0','all_six']):
        selected=[r for r in summary if r['cell_basis']==mode and r['scope']==scope]
        for a,b in zip(c['stage0']['tau_multipliers'][:-1],c['stage0']['tau_multipliers'][1:]):
            va={r['method']:r['max_gap_pp'] for r in selected if r['tau_multiplier']==a};vb={r['method']:r['max_gap_pp'] for r in selected if r['tau_multiplier']==b}
            for x,y in itertools.combinations(c['stage0']['methods'],2):
                s1=int(np.sign(va[x]-va[y]));s2=int(np.sign(vb[x]-vb[y]))
                if s1!=s2:changes.append(dict(cell_basis=mode,scope=scope,tau_from=a,tau_to=b,method_a=x,method_b=y,order_from=s1,order_to=s2,gap_a_from=va[x],gap_b_from=va[y],gap_a_to=vb[x],gap_b_to=vb[y]))
    table('stage0/rank_changes',changes)
    # Exact original patch-area target table, alongside new point-partition area.
    exact=[];rates=[]
    for site,prior in itertools.product(SITES,['ALS','LoD2']):
        stem=f'{site}__{prior}';core=loadz(JA/'core_points'/f'{stem}.npz');v=loadz(CELLS/f'{stem}.npz');t=loadz(FT/'targets'/f'{stem}.npz');ix=core['source_index'];reg=t['judge_region'][ix];err=abs(t['target_height_m'][ix]-core['gt_p']);valid=np.isfinite(err)&np.isfinite(v['tau_v2_m']);correct=valid&(err<=v['tau_v2_m'])
        for k,r in itertools.product([0,1,2,3,4,5,6,9],[0,1,2,3,4,9]):
            m=(v['cell_v2']==k)&(reg==r);den=float(core['area'][m&valid].sum());num=float(core['area'][m&correct].sum())
            exact.append(dict(site=site,prior=prior,cell_basis='original',cell=k,judgment_region=r,patches=int(m.sum()),area_m2=float(core['area'][m].sum()),valid_target_reference_area_m2=den,target_correct_area_m2=num,target_correct_fraction=num/den if den else None,area_rule='original exact patch areas'))
    target_rows=exact+[r for r in quality if r['cell_basis']=='score'];table('stage0/target_judgment',target_rows)
    for site,prior,mode in itertools.product(SITES,['ALS','LoD2'],['original','score']):
        q=[r for r in target_rows if r['site']==site and r['prior']==prior and r['cell_basis']==mode and r['cell'] in [1,2]]
        den=sum(r['area_m2'] for r in q);unknown=sum(r['area_m2'] for r in q if r['judgment_region']==9);wrong=sum(r['area_m2'] for r in q if r['judgment_region'] not in [9,{1:2,2:1}[r['cell']]])
        rates.append(dict(site=site,prior=prior,cell_basis=mode,denominator_cells='1 and 2 (inherited JUDGEAPPLY rate)',denominator_m2=den,unavailable_m2=unknown,correct_fraction=(den-wrong)/den if den and not unknown else None,correct_lower=(den-wrong-unknown)/den if den else None,correct_upper=(den-wrong)/den if den else None))
    table('stage0/judgment_accuracy',rates)
    fig,axes=plt.subplots(2,2,figsize=(14,10),sharex=True,sharey=True)
    for ax,(mode,scope) in zip(axes.flat,itertools.product(['original','score'],['B173_B0','all_six'])):
        for i,method in enumerate(c['stage0']['methods']):
            vals=sorted([r for r in summary if r['cell_basis']==mode and r['scope']==scope and r['method']==method],key=lambda r:r['tau_multiplier'])
            ax.plot([r['tau_multiplier'] for r in vals],[r['max_gap_pp'] for r in vals],marker=['o','s','^','D','v','p','X','*','h'][i],label=NAMES[method],linewidth=1.5)
        ax.set_title(('기존 칸' if mode=='original' else '채점 기준 칸')+' · '+('B173 주변·B0' if scope=='B173_B0' else '여섯 장면'));ax.set_xlabel('τ 배수');ax.set_ylabel('최고와의 차이 중 최댓값 (%p)');ax.grid(alpha=.2);ax.set_xticks(c['stage0']['tau_multipliers'])
    axes[0,1].legend(fontsize=9,ncol=3);fig.tight_layout()
    artifact(fig,'tau_gap',dict(axes=['tau multiplier','max completeness gap pp'],source_sha256={str(D/'tables/stage0/summary.csv'):sha(D/'tables/stage0/summary.csv')},x_range=[.5,2],y_range=list(axes[0,0].get_ylim())))
    top=sorted([r for r in mismatch if r['mismatch_fraction'] is not None],key=lambda r:r['mismatch_fraction'],reverse=True)[:3]
    p=O/'stage0'/f"{top[0]['site']}__{top[0]['prior']}"/'cells.npz';z=loadz(p);xyz=z['xyz'];chosen=z['old_cell']==top[0]['cell'];lo=xyz[chosen,:2].min(0)-1;hi=xyz[chosen,:2].max(0)+1
    keep=((xyz[:,:2]>=lo)&(xyz[:,:2]<=hi)).all(1);ids=np.flatnonzero(keep);colors=['#aaaaaa','#2ca02c','#d62728','#1f77b4','#8c564b','#9467bd','#dddddd','#eeeeee','#555555','#222222','#111111']
    for field,name,title in [('old_cell','old_cells','기존 칸'),('score_cell_1p0','score_cells','채점 기준 칸')]:
        fig,ax=plt.subplots(figsize=(9,7));lab=z[field][ids];norm=BoundaryNorm(np.arange(-1.5,10.5,1),len(colors));sc=ax.scatter(xyz[ids,0],xyz[ids,1],c=lab,cmap=ListedColormap(colors),norm=norm,s=1,rasterized=True);ax.set_aspect('equal');ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_title(f"{LABELS[top[0]['site']]} {top[0]['prior']} · {title}");ax.set_xlabel('local X (m)');ax.set_ylabel('local Y (m)');fig.colorbar(sc,ax=ax,ticks=[-1,0,1,2,3,4],label='칸 번호 (-1: 사전 정보 면 없음)')
        artifact(fig,name,dict(extent=[*lo,*hi],view='top XY',color_range=[-1,9],colors=colors,selected_old_cell=top[0]['cell'],source_sha256={str(p):sha(p)},crs='EPSG:25832, inherited local shift'))
    fig,ax=plt.subplots(figsize=(9,7));ii=np.flatnonzero(chosen);ratio=z['mvs_distance_m'][ii]/z['row_tau_m'][ii];sc=ax.scatter(xyz[ii,0],xyz[ii,1],c=ratio,cmap='viridis',vmin=0,vmax=2,s=3);ax.set_aspect('equal');ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_title('MVS 면 거리 / τ · 기존 칸 '+str(top[0]['cell']));ax.set_xlabel('local X (m)');ax.set_ylabel('local Y (m)');fig.colorbar(sc,ax=ax,label='거리 / τ (2 이상 끝색)')
    artifact(fig,'mvs_distance',dict(extent=[*lo,*hi],view='top XY',color_range=[0,2],clipped_above_2=int((ratio>2).sum()),source_sha256={str(p):sha(p)},crs='EPSG:25832, inherited local shift'))
    comparison=[
      ('비교 대상','prior_height_m / mvs_mean_m 대 gt_p','target_height_m 대 gt_p','참값 점 대 원래 prior 삼각형 / MVS 표면 메시'),
      ('단위','패치 핵심점마다 칸; 넓이 합','패치 넓이 가중','참값 행 수 비율; 결과 쪽 400점/m²'),
      ('거리','패치 법선 방향 스칼라 차','같은 법선 방향 목표 스칼라 차','가장 가까운 면은 전체 메시에서 검색; 지붕 3차원, 벽은 최근접 벡터의 참값 법선 성분'),
      ('문턱','tau_v2_m; 핵심점 kind 지붕·벽','동일 tau_v2_m','동일 지역 τ이나 row_kind / 가까운 참값 면 종류로 지붕·벽 선택'),
      ('결측','n<4 또는 mvs_mean_m 비유한','목표/참값 오차 비유한이면 분모에서 제외','원 채점기는 표면 전체 거리; 기둥은 결과점 소속. 새 칸의 결측만 면·기둥 실제 교차 여부로 정의'),
      ('입력 표현','JUDGEAPPLY core의 원통 내 평균과 참값 대표자리','FINALTRAIN 목표 파일 source_index 정확 조인','STAGE1 prior V/F; AXES71 MVS mesh_mvs_a.ply')]
    sources=['scripts/phd/main_rescore_v1/tau_cells.py:26-31; tau.search_regions, tau_v2_m','scripts/phd/main_rescore_v1/add3_checks.py:13-18; target_height_m, tau_v2_m','scripts/phd/main_rescore_v1/score_inputs.py:6-7; score_mesh.py:9-13,43-62; geometry.py:21-44; metrics.py:3-10; surface_tau.py:4-8; columns.patch_size_m, roof_half_length_m, wall_half_length_m']
    cr=[dict(item=x,cells=a,cells_source=sources[0],target=b,target_source=sources[1],completeness=d,completeness_source=sources[2]) for x,a,b,d in comparison];table('stage0/criteria_comparison',cr)
    lines=['# 단계 0: 채점 기준·τ 재채점','', 'scientific_verdict: null. 학습·GPU·메시 재생성 없음. [이 발주에서 냄]','', '| 어긋남 상위 | 비율 % | 참값 점 |','|---|---:|---:|']
    for r in top:lines.append(f"| {LABELS[r['site']]} {r['prior']} 칸 {r['cell']} | {r['mismatch_fraction']*100:.3f} | {r['n_gt']} {r['small']} |")
    lines+=['','코드로 확인된 차이: 핵심점 스칼라·패치 넓이와 참값 점·전체 표면 최근접 거리를 각각 쓴다. 위 어긋남에서 각 차이의 기여율은 분리하지 않았다. 이 차이가 원인이라는 설명은 추정이며, τ 자체는 같은 지역 값이다.','', '| 방법 | B173 주변·B0 최대 차이 %p | 여섯 장면 최대 차이 %p |','|---|---:|---:|']
    for method in c['stage0']['methods']:
        a=[next(r['max_gap_pp'] for r in summary if r['method']==method and r['tau_multiplier']==1 and r['cell_basis']=='score' and r['scope']==scope) for scope in ['B173_B0','all_six']];lines.append(f'| {NAMES[method]} | {a[0]:.3f} | {a[1]:.3f} |')
    lines+=['',f'τ 배수 인접 구간의 순서·동률 변화: {len(changes)}쌍. 정확한 τ와 방법쌍은 tables/stage0/rank_changes.csv. 작은 칸은 제외하지 않고 적음 표시; 요약에 작은 칸 수를 함께 적었다.',f"τ 배수 1 기존 칸 재현 최대 차이: {max(r['max_abs_delta_pp'] for r in repro):.8f} %p. 모든 54판의 표 4를 저장 거리로 대조했다.",'','새 칸의 목표 넓이는 같은 패치의 참값 행 수 비율로 넓이를 나눈 값이다. 참값 행 없는 패치 넓이는 unassigned.json에 별도다. 기존 칸 목표 넓이는 확인 값 (가)와 같은 패치 넓이로 계산했다. 판단 정확도는 기존 JUDGEAPPLY와 같이 칸 1·2의 넓이 분모이며 미판단은 상·하한으로 남겼다.','', '기존 기둥은 소속 규칙이지 완전성 최근접 탐색 범위 제한이 아니다. 새 칸도 원 채점 거리 그대로이며, 면 존재만 정확한 삼각형·기둥 교차로 확인했다. 결과점 새 칸은 같은 기둥 참값 행 중 가장 가까운 행에 연결했다.','', '기준 대조: tables/stage0/criteria_comparison.csv. 교차표: crosswalk.csv. 전체 표 4: table4_all.csv. 요약: summary.csv. 장면 전체: scene_tau.csv.']
    (D/'단계0_보고.md').write_text('\n'.join(lines)+'\n')
    dump(O/'stage0/complete.json',dict(at=now(),status='PASS_CALCULATION_PENDING_VISUAL_REVIEW',top3=top,rank_changes=len(changes),max_reproduction_delta_pp=max(r['max_abs_delta_pp'] for r in repro),scientific_verdict=None))
if __name__=='__main__':main()
