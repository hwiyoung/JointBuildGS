"""Addendum 2 section 5.1--4, reusing frozen patch observations only."""
import argparse
from scipy.spatial import cKDTree
from column_store import unpack_npz
from interview_common import *

def curve_bins(x):
    # [0,.5), ... [7.5,8], (8,inf); unavailable remains a real row.
    out=np.full(len(x),-1,np.int16);ok=np.isfinite(x)&(x>=0)
    out[ok]=np.minimum(np.floor(x[ok]*2),15).astype(np.int16)
    out[ok&(x>8)]=16
    return out

def region_codes(site,prior,e):
    rpath=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'
    with np.load(rpath) as f:r={k:f[k] for k in ['centre','area','tau','gt_med','mvs_minus_gt_at_gt']}
    assert np.array_equal(e['centre'],r['centre']) and np.array_equal(e['area'],r['area']),'stage-1 patch identity differs'
    p=O/'patch_table'/f'{prior}_patch_table.npz'
    cols=unpack_npz(p,O/'cache/validation_columns'/prior)
    idx=cols['region_source_row_'+site];code=cols['region_code_'+site]
    good=(idx>=0)&(code>=0);ids=idx[good]
    assert len(np.unique(ids))==len(ids) and np.all(ids<len(e['area']))
    out=np.full(len(e['area']),-1,np.int16);out[ids]=code[good]
    return out,r,dict(evaluation_region_identity='exact centres and areas in original row order',
        region=source(rpath),patch_table=source(p),code_column='region_code_'+site,assigned=int(good.sum()))

def main():
    config();curves=[];missing=[];boundary=[];four=[];checks=[];sources=[]
    for site in SITES:
        for prior in PRIORS:
            e,v,base=evaluation(site,prior);ok=eligible(e)
            codes,r,binding=region_codes(site,prior,e);sources.append(dict(site=site,prior=prior,**binding))
            ratios={'correction':np.abs(r['gt_med'].astype(float))/r['tau'],
                    'preservation':np.abs(r['mvs_minus_gt_at_gt'].astype(float))/r['tau']}
            seed=ok&np.isin(e['cell'],[3,5]);dest=ok&np.isin(e['cell'],[0,1,2])
            distance=np.full(len(ok),np.inf)
            if seed.any():distance[dest]=cKDTree(e['centre'][seed,:2]).query(e['centre'][dest,:2],workers=2)[0]
            bins_dist=np.where(distance<=1,0,np.where(distance<=2,1,2)) if seed.any() else np.full(len(ok),-1)
            for prefix in ['nojudge','lt_dynnow']:
                result=f'{prefix}_{prior}_s0';z,zp=patch_values(site,prior,result,e)
                common=dict(site=site,prior=prior,result=result)
                sources.append(source(zp))
                for axis,cell in [('correction',1),('preservation',2)]:
                    parent=ok&(e['cell']==cell);b=curve_bins(ratios[axis]);rows=[]
                    for bi in list(range(17))+[-1]:
                        label='확인 불가' if bi==-1 else '>8τ' if bi==16 else f'{bi*.5:g}~{(bi+1)*.5:g}τ'
                        row=summary(e,z,parent&(b==bi),**common,axis=axis,cell=cell,bin=bi,bin_label=label)
                        rows.append(row);curves.append(row)
                    expected=float(e['area'][parent].sum());actual=sum(x['area_m2'] for x in rows)
                    assert np.isclose(actual,expected,rtol=1e-12,atol=1e-8)
                    checks.append(dict(check='curve_area_sum',**common,axis=axis,expected_m2=expected,actual_m2=actual,pass_check=True))
                for cell in [4,5]:
                    parent=ok&(e['cell']==cell)
                    for label,mask in [('결측',np.isin(codes,[4,13])),('비가시',np.isin(codes,[5,14])),
                                       ('다른 기존 코드',(codes>=0)&~np.isin(codes,[4,13,5,14])),('확인 불가',codes<0)]:
                        missing.append(summary(e,z,parent&mask,**common,cell=cell,region=label,
                            unavailable_reason='격자가 다름' if prior=='ALS' and label=='확인 불가' else '평가 지역 넓이가 빠짐' if label=='확인 불가' else None))
                for group,group_mask in [('0~2',dest)]+[(str(k),dest&(e['cell']==k)) for k in range(3)]:
                    for bi,label in list(enumerate(['수평 1 m 안','1~2 m','2 m 밖']))+[(-1,'확인 불가')]:
                        boundary.append(summary(e,z,group_mask&(bins_dist==bi),**common,cell=group,distance_bin=label,
                            reference_patches=int(seed.sum()),note='칸 3·5 없음: 최근접 거리 정의 불가' if not seed.any() else None))
                if prefix=='lt_dynnow' and prior=='LoD2':
                    analytic=e['z_dyn_now'];a=np.abs(analytic-e['p_gt'])<=e['tau'];b=classes(e,z)==0
                    finite=np.isfinite(analytic);cat=np.where(a,np.where(b,0,1),np.where(b,2,3))
                    for group,mask in [('0~3',ok&np.isin(e['cell'],[0,1,2,3]))]+[(str(k),ok&(e['cell']==k)) for k in range(4)]+[('보정',ok&(e['cell']==1)),('보존',ok&(e['cell']==2))]:
                        total=float(e['area'][mask].sum());den=float(e['area'][mask&finite].sum());out=[]
                        for i,label in enumerate(['정상','반영 실패','2단계가 뒤집음','1단계 탓']):
                            m=mask&finite&(cat==i);area=float(e['area'][m].sum())
                            row=dict(**common,cell=group,category=label,patches=int(m.sum()),area_m2=area,denominator_m2=den,
                                pct=100*area/den if den else None,total_cell_area_m2=total,unavailable_area_m2=total-den)
                            four.append(row);out.append(row)
                        pct=sum(x['pct'] for x in out) if den else None
                        assert pct is None or np.isclose(pct,100,atol=1e-9)
                        checks.append(dict(check='four_way_sum',**common,cell=group,percent_sum=pct,pass_check=True))
    write_table('axis_curves',curves,['0.5τ 구간은 덧붙임 2 지정. 값·영역 정의는 AXES71-v2. 결측 구간 포함해 넓이를 대조한다.'])
    write_table('missing_invisible',missing,['납품 패치 표에서 증명된 영역 코드만 사용. 원래 지역별 코드 열을 사용하며 미연결은 확인 불가.'])
    write_table('boundary_spread',boundary,['거리: 칸 3·5 평가 패치 중심까지의 최근접 수평 거리. 면 없음도 실패 분모에 포함.'])
    write_table('lod2_four_way',four,['명칭은 사용자가 지정한 진단 구분이며 인과관계의 확정 판정이 아니다.'])
    dump(IDOC/'checks/counts.json',dict(status='PASS',checks=checks,sources=sources,scientific_verdict=None))
    plot_curves(curves)
    record('counts',rows=dict(curves=len(curves),missing=len(missing),boundary=len(boundary),four_way=len(four)),checks=len(checks))

def plot_curves(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':11})
    root=IDOC/'figures';root.mkdir(parents=True,exist_ok=True)
    units=[(s,p) for s in SITES for p in PRIORS]
    for axis,title in [('correction','축 1 · 보정 칸'),('preservation','축 2 · 보존 칸')]:
        for category,label in zip(CATEGORIES,CAT_KO):
            fig,axs=plt.subplots(3,2,figsize=(14,13),sharex=True,sharey=True)
            for ax,(site,prior) in zip(axs.flat,units):
                for prefix,color,style in [('nojudge','#666666','--'),('lt_dynnow','#d97706','-')]:
                    rr=[x for x in rows if (x['site'],x['prior'],x['axis'],x['result'])==(site,prior,axis,f'{prefix}_{prior}_s0') and x['bin']>=0]
                    ax.plot([x['bin']*.5+.25 if x['bin']<16 else 8.5 for x in rr],
                            [x[category+'_pct'] if x[category+'_pct'] is not None else np.nan for x in rr],
                            color=color,linestyle=style,marker='o',markersize=3,label=NAMES[prefix])
                ax.set_title(f"{SHORT[site]} · {'항공 LiDAR' if prior=='ALS' else prior}")
                ax.set_ylim(0,100);ax.set_xticks([0,2,4,6,8.5],['0','2','4','6','>8']);ax.grid(alpha=.2)
            axs[0,0].legend(loc='upper right');fig.suptitle(f'{title} · {label} 넓이 비율',fontsize=19)
            fig.supxlabel('사전 정보의 참값 어긋남 / τ' if axis=='correction' else 'MVS의 참값 어긋남 / τ')
            fig.supylabel('넓이 비율 (%)');fig.tight_layout(rect=[.02,.02,1,.96])
            fig.savefig(root/f'{axis}_{category}.png',dpi=160);plt.close(fig)

if __name__=='__main__':main()
