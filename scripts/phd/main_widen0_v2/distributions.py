"""Public distributions use development patches only and explicit denominators."""
import json
import numpy as np
from matplotlib.path import Path as MPath
from analysis_common import O,DOC,CFG,CELLS,KO,load,save_table,font,figure,dump,quantiles
from preflight import PREP

def site_masks(c):
    boxes=json.loads((PREP/'step06/box_ranges.json').read_text());out={}
    for site in ['B0_b10','B173nb_b10','R1rep_b10']:
        b=boxes[site];r=dict(kind='uv_box',u_m=b['eval_u'],v_m=b['eval_v'])
        # Same rotating local u/v limits as the inherited range rule.
        from common import inside_range
        out[site]=inside_range(c[:,:2],r)
    out['three_regions_union']=np.logical_or.reduce(list(out.values()))
    return out

def main():
    plt=font();cellrows=[];thresholds=[];density=[];missing=[];extras=[]
    for prior in ['LoD2','ALS']:
        d=load(prior);area=d['area'];cells=d['cell'];p=d['mvs_p'];known=np.isfinite(p);total=float(area.sum())
        assert not ((~d['normal_defined'])&(d['gt_status']==0)).any()
        extras.append(dict(prior=prior,source_extra_patches=int(d['source_extra'].sum()),
            source_extra_area_m2=float(area[d['source_extra']].sum()),undefined_normal_patches=int((~d['normal_defined']).sum()),
            undefined_normal_area_m2=float(area[~d['normal_defined']].sum()),
            rule='Inherited loc_extra centroid fallback retained; LoD2 wall face normal retained when available; zero normal is not imputed.'))
        assert np.all((cells>=0)&(cells<7))
        for ci,name in enumerate(CELLS):
            m=cells==ci;aa=float(area[m].sum())
            cellrows.append(dict(prior=prior,cell=name,cell_ko=KO[ci],patches=int(m.sum()),area_m2=aa,fraction=aa/total if total else None,
                difference_available_patches=int((m&known).sum()),difference_available_area_m2=float(area[m&known].sum()),difference_missing_area_m2=float(area[m&~known].sum())))
        assert np.isclose(sum(r['area_m2'] for r in cellrows if r['prior']==prior),total,rtol=1e-12)
        for roof in [True,False]:
            m=(d['roof_like']==roof)&(d['gt_status']==0)
            density.append(dict(prior=prior,shape='지붕꼴' if roof else '벽꼴',patches=int(m.sum()),area_m2=float(area[m].sum()),
                density_points_m2=quantiles(d['gt_n_inner'][m]/(np.pi*.5**2)),rule='Nadir-only cleaned GT inner-column points / pi*(0.5 m)^2; surface-oriented support density, not planimetric source density'))
        for status in [0,1,2,3]:
            m=d['gt_status']==status
            missing.append(dict(prior=prior,gt_status=status,reason=['plane available','no accepted face','fewer than 10 inner points','plane fit unavailable'][status],patches=int(m.sum()),area_m2=float(area[m].sum()),zero_column_patches=int((m&(d['gt_n_col']==0)).sum())))
        scopes={'development_all':np.ones(len(area),bool),**site_masks(d['raw_centre'])}
        for scope,sm in scopes.items():
            for ci in [1,2]:
                for roof in [True,False]:
                    base=sm&(cells==ci)&(d['roof_like']==roof);m=base&known;den=float(area[m].sum())
                    row=dict(prior=prior,scope=scope,cell=CELLS[ci],shape='지붕꼴' if roof else '벽꼴',patches=int(base.sum()),valid_patches=int(m.sum()),
                        cell_area_m2=float(area[base].sum()),difference_area_m2=den,missing_difference_area_m2=float(area[base&~known].sum()))
                    for th in [.5,1.,2.]:row[f'fraction_abs_gt_{th:g}m']=float(area[m&(np.abs(p)>th)].sum()/den) if den else None
                    row['fraction_positive']=float(area[m&(p>0)].sum()/den) if den else None
                    thresholds.append(row)
        edges=np.geomspace(.01,10,61);fig,ax=plt.subplots(figsize=(8,4.5));histdata=[]
        for ci,col in [(1,'#0072b2'),(2,'#d55e00')]:
            m=(cells==ci)&known;den=float(area[m].sum());h,_=np.histogram(np.abs(p[m]),edges,weights=area[m]);h=h/den if den else h
            ax.stairs(h*100,edges,label=KO[ci],color=col,linewidth=1.7)
            histdata.append(dict(cell=CELLS[ci],edges_m=edges.tolist(),fraction_per_bin=h.tolist(),valid_patches=int(m.sum()),valid_area_m2=den,
                cell_area_m2=float(area[cells==ci].sum()),missing_difference_area_m2=float(area[(cells==ci)&~known].sum()),
                under_axis_area_m2=float(area[m&(np.abs(p)<.01)].sum()),over_axis_area_m2=float(area[m&(np.abs(p)>10)].sum())))
        ax.set(xscale='log',xlim=(.01,10),xlabel='|두 자료의 차| (m)',ylabel='넓이 비율 (%)',title=prior+' · 정하는 곳');ax.legend();ax.grid(alpha=.2)
        figure(fig,f'차의크기_{prior}',histdata);plt.close(fig)
        # Order 4.5 also requests each cell, beyond the two-cell overlay.
        fig,axs=plt.subplots(4,2,figsize=(10,12),sharex=True);allhist=[]
        for ci,ax in enumerate(axs.flat):
            if ci>=len(CELLS):
                ax.axis('off');ax.text(.05,.8,'분모: 차가 있는 넓이\n차 없음은 별도 기록\n1 cm 미만·10 m 초과는 JSON',va='top');continue
            m=(cells==ci)&known;den=float(area[m].sum());h,_=np.histogram(np.abs(p[m]),edges,weights=area[m]);h=h/den if den else h
            ax.stairs(h*100,edges,color={1:'#0072b2',2:'#d55e00'}.get(ci,'#555555'))
            ax.set(xscale='log',xlim=(.01,10),title=KO[ci],xlabel='|두 자료의 차| (m)',ylabel='넓이 비율 (%)');ax.grid(alpha=.2)
            if not den:
                ax.set_ylim(0,1)
                ax.text(.5,.5,'차가 있는 패치 없음',transform=ax.transAxes,ha='center')
            allhist.append(dict(cell=CELLS[ci],edges_m=edges.tolist(),fraction_per_bin=h.tolist(),valid_patches=int(m.sum()),valid_area_m2=den,
                cell_area_m2=float(area[cells==ci].sum()),missing_difference_area_m2=float(area[(cells==ci)&~known].sum()),
                under_axis_area_m2=float(area[m&(np.abs(p)<.01)].sum()),over_axis_area_m2=float(area[m&(np.abs(p)>10)].sum())))
        fig.suptitle(prior+' · 모든 칸 · 정하는 곳');fig.tight_layout()
        figure(fig,f'차의크기_모든칸_{prior}',allhist);plt.close(fig)
        fig,axs=plt.subplots(2,1,figsize=(8,5.8),sharex=True);sd=[]
        for ax,ci in zip(axs,[1,2]):
            m=(cells==ci)&known;den=float(area[m].sum());matrix=[]
            for sign in [-1,1]:
                mm=m&(p*sign>0);h,_=np.histogram(np.abs(p[mm]),edges,weights=area[mm]);matrix.append(h/den if den else h)
            z=np.array(matrix);im=ax.pcolormesh(edges,[-1.5,0,1.5],z*100,cmap='viridis',shading='flat')
            ax.set(xscale='log',yticks=[-.75,.75],yticklabels=['안쪽 −','바깥 +'],title=KO[ci]);fig.colorbar(im,ax=ax,label='넓이 비율 (%)')
            sd.append(dict(cell=CELLS[ci],edges_m=edges.tolist(),sign_order=[-1,1],fraction=z.tolist(),valid_patches=int(m.sum()),valid_area_m2=den,zero_area_m2=float(area[m&(p==0)].sum()),
                cell_area_m2=float(area[cells==ci].sum()),missing_difference_area_m2=float(area[(cells==ci)&~known].sum()),
                under_axis_area_m2=float(area[m&(np.abs(p)<.01)].sum()),over_axis_area_m2=float(area[m&(np.abs(p)>10)].sum())))
        axs[-1].set_xlabel('|두 자료의 차| (m)');fig.suptitle(prior+' · 부호와 크기');fig.tight_layout()
        figure(fig,f'차의부호크기_{prior}',sd);plt.close(fig)
    save_table('맞는쪽칸_넓이',cellrows);save_table('차의크기_비율',thresholds,denominator='finite difference area within each cell/shape/scope; missing area reported separately')
    save_table('참값_점밀도',density);save_table('참값_유무사유',missing);save_table('사전정보_추가패치_법선',extras)
    print('development distributions complete',flush=True)
if __name__=='__main__':main()
