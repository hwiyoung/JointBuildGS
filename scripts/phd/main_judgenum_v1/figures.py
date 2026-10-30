"""300-dpi scientific figures, using development cores only."""
import argparse
import json
import inspect
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Polygon as Patch,Patch as LegendPatch,Rectangle
from matplotlib.lines import Line2D
from scipy.special import erf
from sample_report import setup
from analyse import clean
from lock_config import dump,sha
O=Path('/out');C=Path('/cfg');D=Path('/docs');F=D/'figures'
JC=['#0072b2','#d55e00','#999999'];PC=['#238b45','#d73027','#999999'];CC=['#8c564b','#238b45']

def data(prior,stage_a=False):
    folder=O/('core_points_stage_a' if stage_a else 'core_points');parts=[];sources=[]
    for p in sorted(folder.glob(f'*__{prior}.npz')):
        with np.load(p) as z:parts.append({k:z[k] for k in z.files})
        sources.append({'file':str(p),'sha256':sha(p)})
    return {k:np.concatenate([p[k] for p in parts]) for k in parts[0]},sources

def export(fig,name,values):
    F.mkdir(exist_ok=True);fig.savefig(F/f'{name}.png',dpi=300,bbox_inches='tight');plt.close(fig)
    dump(F/f'{name}.json',clean({'data':values,'dpi':300,'scientific_verdict':None,
      'generator_sha256':sha(Path(inspect.stack()[1].filename)),
      'figure_common_sha256':sha(Path(__file__)),'source':'[이 발주에서 냄]'}))

def outlines(ax,cfg):
    for ft in json.loads((C/'scope_geometry.json').read_text())['features']:
        state=ft['properties']['split']
        if state not in ['evaluation','holdout']:continue
        g=ft['geometry'];polys=[g['coordinates']] if g['type']=='Polygon' else g['coordinates']
        for poly in polys:
            ax.add_patch(Patch(np.asarray(poly[0])-[690953,5336071],closed=True,
              fill=state=='holdout',facecolor='#eeeeee',edgecolor='#777777',lw=.5,
              hatch='////' if state=='holdout' else None))

def maps(d,sources,prior,cfg,stage_a):
    fig,axs=plt.subplots(1,2,figsize=(12,8),sharex=True,sharey=True)
    for ax,key,title in zip(axs,['judgment_before','judgment_after'],['처리 전','처리 후']):
        if key not in d:
            ax.text(.5,.5,'작은 덩어리 처리 뒤 추가',ha='center',va='center',transform=ax.transAxes)
        else:
            for value,color in [(2,JC[2]),(0,JC[0]),(1,JC[1]),(-1,'#222222')]:
                m=d[key]==value;ax.scatter(d['centre'][m,0],d['centre'][m,1],s=.15,c=color,linewidths=0,rasterized=True)
        outlines(ax,cfg);ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel('동쪽 좌표 − 690953 (m)')
    axs[0].set_ylabel('북쪽 좌표 − 5336071 (m)');fig.suptitle(('항공 LiDAR' if prior=='ALS' else prior)+' · 판단 1')
    handles=[LegendPatch(color=c,label=l) for c,l in zip(JC,['같음','어긋남','상속'])]
    handles.append(LegendPatch(color='#222222',label='확인 불가'))
    fig.legend(handles=handles,ncol=4,loc='lower center');fig.tight_layout(rect=[0,.04,1,.96])
    export(fig,('stage_a_' if stage_a else '')+'judgment_map_'+prior,{'sources':sources,'photos':[],
       'coordinates':'centre XY; EPSG:25832 minus [690953,5336071]','judgments':['judgment_before','judgment_after'],
       'postprocessing_available':not stage_a})

def read_strip(path,centre,direction,halfwidth=.3):
    points=np.load(path,mmap_mode='r');pieces=[];indices=[];perp=np.array([-direction[1],direction[0]])
    for a in range(0,len(points),500000):
        q=np.asarray(points[a:a+500000]);v=q[:,:2]-centre[:2]
        along=v@direction;across=v@perp;m=(np.abs(along)<=5)&(np.abs(across)<=halfwidth)
        if m.any():pieces.append(q[m].astype(float));indices.append(a+np.flatnonzero(m))
    return (np.concatenate(pieces),np.concatenate(indices)) if pieces else (np.empty((0,3)),np.empty(0,np.int64))

def sections(d,sources,prior,cfg,stage_a):
    W=Path(cfg['sources']['widen']);root=W/'holdout/internal/points'
    for index,sec in enumerate(cfg['figures']['section_coordinates']):
        if sec['prior']!=prior or 'building' not in sec:continue
        centre=np.array(sec['centre_local_m']);direction=np.array(sec['b_local_xy_m'])-np.array(sec['a_local_xy_m']);direction/=np.linalg.norm(direction)
        perp=np.array([-direction[1],direction[0]]);v=d['centre'][:,:2]-centre[:2]
        along=v@direction;across=v@perp
        mask=(d['building']==sec['building'])&(np.abs(along)<=5)&(np.abs(across)<=.3)
        ids=np.flatnonzero(mask);ids=ids[np.argsort(along[ids],kind='stable')]
        fig=plt.figure(figsize=(12,7));gs=fig.add_gridspec(4,1,height_ratios=[8,1,1,1],hspace=.12)
        ax=fig.add_subplot(gs[0]);bandaxs=[fig.add_subplot(gs[k]) for k in [1,2,3]]
        payload={'section':sec,'patch_ids':d['patch_id'][ids].tolist(),'sources':sources,'photos':[],
                 'point_sources':[],'d_mean_cm':d['d_mean_cm'][ids].tolist(),'DL_cm':d['DL_cm'][ids].tolist()}
        # Membership by original 100 m core; adjacent context arrays can overlap.
        tiles=sorted({str(p).split(':')[1] for p in d['patch_id'][ids]})
        mvs=[];gt=[];previous_buffers=[]
        for tile in tiles:
            for name,store in [('mvs_a_xyz.npy',mvs),('gt_xyz.npy',gt)]:
                file=root/tile/name;X,rows=read_strip(file,centre,direction)
                owner=np.ones(len(X),bool)
                for x0,y0,x1,y1 in previous_buffers:
                    owner&=~((X[:,0]>=x0)&(X[:,0]<x1)&(X[:,1]>=y0)&(X[:,1]<y1))
                X=X[owner];rows=rows[owner];store.append(X)
                payload['point_sources'].append({'file':str(file),'row_indices':rows.tolist(),
                    'selection':'10m section, +/-0.3m; first lexicographic source tile owns overlapping buffered points'})
            tx,ty=map(int,tile.split('_'));previous_buffers.append([tx*100-690953-10,ty*100-5336071-10,(tx+1)*100-690953+10,(ty+1)*100-5336071+10])
        X=np.concatenate(mvs) if mvs else np.empty((0,3));G=np.concatenate(gt) if gt else np.empty((0,3))
        if len(G):ax.scatter((G[:,:2]-centre[:2])@direction,G[:,2],s=.5,c='#222222',alpha=.25,label='참값 점',linewidths=0)
        assignment=np.full(len(X),-1,np.int64)
        for kk,i in enumerate(ids):
            if d['n'][i]<0:continue
            n=d['normal'][i];vv=X-d['centre'][i];tt=vv@n;ll=vv-tt[:,None]*n
            radial=np.einsum('ij,ij->i',ll,ll)
            m=(np.abs(tt)<=5)&(radial<=d['chosen_radius_m'][i]**2)
            # The figure uses the measured first-face centre; final cores share
            # that unchanged baseline measurement from the stage-A sidecar.
            o=d.get('face_o_m',np.full(len(d['area']),np.nan))[i]
            if np.isfinite(o):m&=(tt>=o-1)&(tt<=o+1)
            else:m[:]=False
            assignment[m&(assignment<0)]=kk
        drawn=assignment>=0
        if drawn.any():ax.scatter((X[drawn,:2]-centre[:2])@direction,X[drawn,2],s=1.,c=assignment[drawn],cmap='turbo',alpha=.6,linewidths=0,label='영상 깊이 점')
        for surf in np.unique(d['surf'][ids]):
            ii=ids[d['surf'][ids]==surf];ax.plot(along[ii],d['centre'][ii,2],color='#6b4f37',lw=1.3)
        for i in ids:
            c=d['centre'][i];n=d['normal'][i];dl=d['DL_cm'][i]/100;dd=d['d_mean_cm'][i]/100
            if np.isfinite(dl):
                ends=c[None,:]+np.array([-dl,dl])[:,None]*n
                ax.plot((ends[:,:2]-centre[:2])@direction,ends[:,2],color='#0072b2',alpha=.18,lw=2)
            if np.isfinite(dd):
                end=c+dd*n;ax.plot([along[i],(end[:2]-centre[:2])@direction],[c[2],end[2]],color='#d55e00',alpha=.35,lw=.6)
        ax.set(xlim=(-5,5),ylabel='높이 − 604 (m)',title=f"{prior} · {sec['building'].replace('DEBY_LOD2_','')} · 칸 {sec['cell']}")
        if len(ids):
            low=d['centre'][ids,2].min()-5.5;high=d['centre'][ids,2].max()+5.5;ax.set_ylim(low,high)
        handles,labels=ax.get_legend_handles_labels()
        handles += [Line2D([],[],color='#6b4f37',label='사전 정보'),Line2D([],[],color='#d55e00',label='거리 d'),Line2D([],[],color='#0072b2',alpha=.4,lw=3,label='±DL')]
        ax.legend(handles=handles,loc='best',markerscale=3,fontsize=8,ncol=2);ax.grid(alpha=.15);ax.tick_params(labelbottom=False)
        bands=[('판단 1',d['judgment_before' if stage_a else 'judgment_after'][ids],JC)]
        if not stage_a:
            cal=json.loads((O/'calibration.json').read_text())['values'][prior]['base']['photo_choices'];ph=[]
            for i in ids:
                key='roof' if prior=='ALS' or d['kind'][i]==1 else 'wall';ph.append(d['photo_judgments'][i,cal[key]//9])
            bands += [('사진 판단',np.minimum(ph,2),PC),('처음 선택',d['initial_choice'][ids],CC)]
        else:bands += [('사진 판단',None,PC),('처음 선택',None,CC)]
        for ba,(label,vals,colors) in zip(bandaxs,bands):
            if vals is None:ba.text(.5,.5,'값을 고른 뒤 추가',ha='center',va='center',transform=ba.transAxes)
            else:
                for value,color in enumerate(colors):
                    m=np.asarray(vals)==value;ba.scatter(along[ids[m]],np.zeros(int(m.sum())),marker='s',s=25,c=color,linewidths=0)
            ba.set(xlim=(-5,5),ylim=(-.6,.6),yticks=[],ylabel=label);ba.tick_params(labelbottom=False)
        bandaxs[-1].set_xlabel('단면 거리 (m)');bandaxs[-1].tick_params(labelbottom=True)
        payload['mvs_drawn_rows_in_selected_strips']=np.flatnonzero(drawn).tolist()
        payload['mvs_core_assignment']=assignment[drawn].tolist()
        export(fig,('stage_a_' if stage_a else '')+f'section_{index+1}_{prior}',payload)
        print('SECTION_FIGURE',index+1,prior,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage-a',action='store_true');p.add_argument('--sections-only',action='store_true');args=p.parse_args()
    setup();cfg=json.loads((C/'judgenum_v1.json').read_text())
    for prior in ['LoD2','ALS']:
        d,sources=data(prior,args.stage_a)
        if not args.stage_a:
            old,_=data(prior,True);assert np.array_equal(d['patch_id'],old['patch_id']);d['face_o_m']=old['face_o_m']
        if not args.sections_only:maps(d,sources,prior,cfg,args.stage_a)
        sections(d,sources,prior,cfg,args.stage_a)
    print('MAPS_AND_SECTIONS_READY')

if __name__=='__main__':main()
