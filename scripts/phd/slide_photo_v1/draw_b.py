"""Exact legacy section geometry; TSDF plane intersections, no Z filtering."""
from common import *
from PIL import Image
from matplotlib.collections import LineCollection
def main():
    c=config();sys.path.insert(0,'/repo/scripts/phd/main_photofig_v1');import pf_geo as geom
    specs=load(REPO/'configs/phd/main_regionfig_v1/regionfig_v1.json')['examples'];prepared=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples']
    SD=PH/'main_dist71_v1/PHD-MAIN-DIST71-v1'
    rootmap={'S0':S0,'S1':S1,'SB':PH/'main_baselines_v1/PHD-MAIN-BASELINES-v1','SF':PH/'main_fix_v1/PHD-MAIN-FIX-v1','S2':PH/'main_stage2_v1/PHD-MAIN-STAGE2-v1','S3':PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1','SL':PH/'main_fill_v1/PHD-MAIN-FILL-v1','MF':PH/'metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1'}
    def resolve(s):
        a,b=s.split('/',1);return rootmap[a]/b if a in rootmap else Path(s)
    cached_path=DOC/'figures/figS_b_correction_sections.json';cached=load(cached_path) if cached_path.exists() else None
    plt=plot_setup(35);fig=plt.figure(figsize=(32,10.77),dpi=100);allrec=[]
    for row,(ex,pr) in enumerate(zip(specs,prepared)):
        site,prior=ex['site'],ex['prior'];start=np.array(ex['start_xy']);end=np.array(ex['end_xy']);axis=end-start;length=np.linalg.norm(axis);axis/=length
        with np.load(S1/'defs'/site/f'rows_{prior}.npz') as r:rows={k:r[k] for k in ['src','point']}
        with np.load(S1/'defs'/site/'gt_classes.npz') as g:
            points={0:g['xyz_gt_points'],1:g['xyz_gt_primary']} if 'xyz_gt_primary' in g.files else {0:g['xyz_gt_points']}
        gt=np.concatenate(list(points.values()));band,s=geom.band(gt,start,axis,[0,length],half=ex['half_width_m']);gtline=np.c_[s[band],gt[band,2]]
        # Input bin heights are exactly the REGIONFIG final record, not reselected.
        H=np.asarray(pr['heights_model_m'],float);ss=np.asarray(pr['bin_centres_m'])
        zero=float(np.nanmin(gtline[:,1]));ylo=min(float(np.nanmin(H)),float(gtline[:,1].min()));yhi=max(float(np.nanmax(H)),float(gtline[:,1].max()))
        names=['2DGS','GeoGS','결합','CDGS 변형','본 방법'];res=['imgonly_2dgs_s0','geogs_ALS_fix1' if prior=='ALS' else 'trust_LoD2_fix1',f'mvsfuse_{prior}',f'cdgsnofit_{prior}_s0',f'prop_{prior}_s0'];outputs=[]
        for name,rid in zip(names,res):
            jp=SD/'dist'/f'{site}_{prior}__{rid}.json';dp=jp.with_suffix('.npz');info=load(jp);mesh=resolve(info['mesh'])
            old=next((o for o in cached['examples'][row]['outputs'] if o['result']==rid and o['mesh']==str(mesh)),None) if cached and cached['examples'][row]['example']==ex else None
            if old is not None:seg=np.asarray(old['section_segments'])
            else:
                V,F,minfo=geom.read_ply_mesh_box(mesh,[min(start[0],end[0]),min(start[1],end[1]),max(start[0],end[0]),max(start[1],end[1])],margin=3)
                seg=geom.cut_vertical(V,F,start,axis,[0,length])
            # No height filter on intersections; common displayed limits cover all input/reference points.
            with np.load(dp) as d:
                idx=d['r_idx'];src=rows['src'][idx];pid=rows['point'][idx];P=np.zeros((len(idx),3))
                for kind,X in points.items():P[src==kind]=X[pid[src==kind]]
                assert set(np.unique(src))<=set(points)
                keep,_=geom.band(P,start,axis,[0,length],half=ex['half_width_m']);dist=d['r_d'][keep];tau=d['r_tau'][keep]
                share=float(np.mean(dist<=tau)) if len(dist) else None
            outputs.append(dict(name=name,result=rid,mesh=str(mesh),distance_file=str(dp),tau_values_m=np.unique(tau),tau_source='stored DIST71 r_tau for each r_d row',within_tau_share=share,point_count=len(dist),section_segments=seg))
            print('B SECTION',site,rid,len(seg),len(dist),share,flush=True)
        bottom=.57 if row==0 else .075;height=.32
        ax=fig.add_axes([.005,bottom,.17,height]);photo=REPO/f'docs/experiments/phd/main_regionfig_v1/figures/crops/{ex["id"]}_표시.png';ax.imshow(Image.open(photo));ax.axis('off');ax.set_title('실제 사진',fontsize=35,pad=8)
        for col in range(6):
            ax=fig.add_axes([.19+col*.132,bottom,.117,height]);ref=np.c_[ss,H[:,2]] if col==0 else gtline;ax.scatter(ref[:,0],ref[:,1],c=c['colours']['gt'],s=22 if col==0 else .7,alpha=.9 if col==0 else .65,rasterized=True)
            ax.plot(ss,H[:,0],ls='--',color=c['colours']['prior'],lw=3,alpha=1 if col==0 else .32)
            if col==0:ax.plot(ss,H[:,1],color=c['colours']['mvs'],lw=3);name='입력'
            else:
                o=outputs[col-1];ax.add_collection(LineCollection(o['section_segments'],colors=c['colours']['result'],linewidths=3.2));name=o['name']
                txt=f'τ 안 {o["within_tau_share"]*100:.0f} %' if o['within_tau_share'] is not None else 'τ 안 확인 불가';ax.text(.5,-.22,txt,transform=ax.transAxes,ha='center',fontsize=35)
            ax.set(xlim=(0,length),ylim=(ylo-.15,yhi+.15));ax.set_xticks([0,round(length)]);ax.tick_params(labelsize=35);ax.set_title(name,fontsize=35,pad=8)
            ax.get_xticklabels()[0].set_ha('left');ax.get_xticklabels()[-1].set_ha('right')
            if col:ax.set_yticks([])
            else:
                ticks=np.linspace(ylo,yhi,3);ax.set_yticks(ticks);ax.set_yticklabels([f'{v-zero:.0f}' for v in ticks]);ax.set_ylabel('높이 (m)',fontsize=35)
        overlap=None
        if site=='R1rep_b10':
            from matplotlib.path import Path as MplPath
            v1=load(REPO/'configs/phd/main_viscmp_v4/places_v4.json')['V1'];pid=np.asarray(v1['place']);zz=np.load(U/'patch_values/R1rep_b10__LoD2__R1.5.npz');C=zz['centre'][pid];N=zz['normal'][pid]
            units=np.load(S0/'s61/box/R1rep_b10/LoD2/units.npz');T1=units['loc_t1'][pid];T2=units['loc_t2'][pid]
            ssample=np.linspace(0,length,int(np.ceil(length/.01))+1);line=start+ssample[:,None]*axis;inside=np.zeros(len(line),bool)
            for cen,t1,t2 in zip(C,T1,T2):
                poly=np.array([cen+u*t1+v*t2 for u,v in [(-.125,-.125),(.125,-.125),(.125,.125),(-.125,.125)]])[:,:2];inside|=MplPath(poly).contains_points(line,radius=1e-10)
            overlap=dict(source='configs/phd/main_viscmp_v4/places_v4.json V1 place',intersects=bool(inside.any()),sample_step_m=float(length/(len(line)-1)),sample_fraction=float(inside.mean()),inside_s_range_m=[float(ssample[inside].min()),float(ssample[inside].max())] if inside.any() else None,method='0.01m centreline sampling against exact XY footprints of V1 outlined 0.25m patches; no section relocation')
        for o in outputs:
            seg=np.asarray(o['section_segments']);o['segments_wholly_outside_display']=int(((seg[:,:,1].max(1)<ylo-.15)|(seg[:,:,1].min(1)>yhi+.15)).sum()) if len(seg) else 0
        allrec.append(dict(example=ex,photo=str(photo),height_range_m=[ylo-.15,yhi+.15],height_zero_m=zero,outputs=outputs,viscmp_v1_overlap=overlap))
    for xpos,label,key in [(.25,'참값','gt'),(.42,'사전 정보','prior'),(.65,'MVS','mvs'),(.80,'결과','result')]:fig.text(xpos,.99,label,color=c['colours'][key],fontsize=35,ha='center',va='top')
    p=DOC/'figures/figS_b_correction_sections.png';fig.savefig(p,dpi=100,facecolor='white');plt.close(fig)
    dump(p.with_suffix('.json'),dict(task_id=c['task_id'],scientific_verdict=None,source_numbers=str(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json'),examples=allrec,measurement='[이 발주에서 냄]; exact DIST71 r_d rows within unchanged section band; no height window'))
    print('DRAW b',[(r['example']['id'],[(o['name'],o['within_tau_share'],o['point_count']) for o in r['outputs']]) for r in allrec])
if __name__=='__main__':main()
