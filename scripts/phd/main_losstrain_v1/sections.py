"""9.1 frozen sections: exact mesh-plane intersections and original reference points."""
import argparse
import ast
import json
from pathlib import Path
import numpy as np
import open3d as o3d
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection
from inputs import OUT,PH,S1,save,sha
from mesh_score import source_mesh
from side_tables import VARS
from result_figures import LABELS

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':9,'axes.unicode_minus':False})
COL=dict(prior='#ae3434',mvs='#2171b5',gt='#238b45',analytic='#756bb1',trained='#e67e22',nojudge='#8c8c8c')
source=Path('/repo/scripts/phd/main_stage2_v1/figs_s2.py')
nodes=[x for x in ast.parse(source.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in ['plane_segments','crop_mesh']]
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'))

def read_mesh(path):
    mesh=o3d.io.read_triangle_mesh(str(path))
    return np.asarray(mesh.vertices).copy(),np.asarray(mesh.triangles).copy()

def near(x,centre,tangent,length,width):
    s=(x[:,:2]-centre[:2])@tangent[:2]
    cross=(x[:,:2]-centre[:2])@np.array([-tangent[1],tangent[0]])
    return (np.abs(s)<=length/2)&(np.abs(cross)<=width),s

def draw(ex,prior):
    site=ex['site'];start=np.array(ex['start']);end=np.array(ex['end']);length=np.linalg.norm(end-start)
    centre=np.r_[(start+end)/2,0.];tangent=np.r_[(end-start)/length,0.]
    variants=[v for v in VARS if (OUT/'patch_z'/f'{site}__{prior}__{v}_{prior}_s0.npz').exists()]
    assert variants,'no trained patch result yet'
    root=OUT/'direct_stage1_v2'/(site+'__'+prior)
    with np.load(root/'evaluation.npz') as z:e={k:z[k] for k in z.files}
    ids,s=near(e['centre'],centre,tangent,length,ex['half_width'])
    ids &= e['in_eval']&e['scoring_allowed'];ids=np.flatnonzero(ids)
    with np.load(S1/'defs'/site/f'prior_{prior}.npz') as p:
        pv,pf=p['V'].astype(np.float64),p['F'].astype(np.int64)
    pseg=plane_segments(*crop_mesh(pv,pf,centre,length/2+2),centre,tangent,length/2)
    gtpath=S1/'defs'/site/'gt_classes.npz'
    with np.load(gtpath) as g:
        xx=[g['xyz_gt_points'][g['use_gt_points']]]
        if 'xyz_gt_primary' in g.files:xx.append(g['xyz_gt_primary'][g['use_gt_primary']])
        gx=np.concatenate(xx).astype(np.float64)
    mask,gs=near(gx,centre,tangent,length,ex['half_width']);gpoints=np.c_[gs[mask],gx[mask,2]]
    mvpath=source_mesh(site,prior,'mvs_a');mv,mf=read_mesh(mvpath)
    mask,ms=near(mv,centre,tangent,length,ex['half_width']);mpoints=np.c_[ms[mask],mv[mask,2]];del mv,mf
    oldpath=source_mesh(site,prior,f'nojudge_{prior}_s0');v,f=read_mesh(oldpath)
    oldseg=plane_segments(*crop_mesh(v,f,centre,length/2+2),centre,tangent,length/2);del v,f
    # Limits depend only on original prior/reference geometry, shared by all panels.
    heights=np.r_[pseg[...,1].ravel(),gpoints[:,1]];assert len(heights)
    lo,hi=float(heights.min()-.6),float(heights.max()+.6)
    fig,axes=plt.subplots(2,len(variants),figsize=(4.2*len(variants),5.2),gridspec_kw={'height_ratios':[12,1]},sharex=True,squeeze=False)
    panels={};sources=[str(root/'evaluation.npz'),str(gtpath),str(mvpath),str(oldpath)]
    for j,var in enumerate(variants):
        ax=axes[0,j];path=source_mesh(site,prior,var+'_'+prior+'_s0');v,f=read_mesh(path)
        seg=plane_segments(*crop_mesh(v,f,centre,length/2+2),centre,tangent,length/2);del v,f
        az=e['z_'+VARS[var]];points=e['centre'][ids]+az[ids,None]*e['normal'][ids]
        ass=(points[:,:2]-centre[:2])@tangent[:2]
        # Display-only 25cm median curve, with explicit gaps; all scoring uses raw patches.
        edges=np.arange(-length/2,length/2+.25,.25);bins=np.digitize(ass,edges)-1
        yy=np.full(len(edges)-1,np.nan)
        for k in range(len(yy)):
            q=points[bins==k,2]
            if len(q):yy[k]=np.median(q)
        for x,col,width in [(oldseg,'nojudge',1.),(pseg,'prior',1.4),(seg,'trained',1.4)]:ax.add_collection(LineCollection(x,colors=COL[col],linewidths=width))
        ax.scatter(mpoints[:,0],mpoints[:,1],s=.8,c=COL['mvs'],alpha=.45,rasterized=True)
        ax.scatter(gpoints[:,0],gpoints[:,1],s=.8,c=COL['gt'],alpha=.45,rasterized=True)
        ax.plot((edges[:-1]+edges[1:])/2,yy,'--',color=COL['analytic'],linewidth=1.5)
        ax.set(xlim=(-length/2,length/2),ylim=(lo,hi),title=LABELS[var])
        if j==0:ax.set_ylabel('높이 (m)')
        band=axes[1,j];band.scatter(s[ids],np.zeros(len(ids)),c=e['cell'][ids],cmap='tab10',vmin=0,vmax=9,s=12,marker='s')
        band.set(yticks=[],xlabel='단면 위치 (m)',ylim=(-.5,.5))
        panels[var]=dict(trained_mesh=str(path),mesh_sha256=sha(path),mesh_plane_segments=len(seg),analytic_patch_ids=ids.tolist(),
            analytic_display_bin_m=.25,analytic_bin_centres=((edges[:-1]+edges[1:])/2).tolist(),analytic_height_m=[float(v) if np.isfinite(v) else None for v in yy],
            cell_counts={str(k):int((e['cell'][ids]==k).sum()) for k in range(7)})
        sources.append(str(path))
    title=f"{ex['name']} · {prior}: 학습 면과 두 자료의 높이를 같은 단면에서 본다"
    fig.suptitle(title,x=.04,ha='left',fontsize=13,y=.99)
    for i,(key,label) in enumerate([('prior','사전'),('mvs','MVS 표면 점'),('gt','참값 점'),('analytic','도착점'),('trained','학습'),('nojudge','판정 끔')]):
        fig.text(.05+i*.15,.92,label,color=COL[key],fontsize=10)
    fig.text(.04,.01,f'패치 {len(ids):,}개 · 참값 점 {len(gpoints):,}개 · MVS 표면 점 {len(mpoints):,}개 · 폭 ±{ex["half_width"]} m · 아래 띠: 칸 0~6',fontsize=9)
    fig.subplots_adjust(top=.83,bottom=.13,wspace=.12,hspace=.08)
    key=f'section_{site}_{prior}_{list(json.loads(Path("/config/losstrain_v1.json").read_text())["figures"]["sections"]).index(ex)}'
    dest=Path('/docs/figures');dest.mkdir(exist_ok=True)
    fig.savefig(dest/(key+'.png'),dpi=300);plt.close(fig)
    save(dest/(key+'.json'),dict(title=title,section=ex,prior=prior,panels=panels,sources=sources,ylim=[lo,hi],
        reference_points=len(gpoints),mvs_surface_vertices=len(mpoints),patches=len(ids),colours=COL,
        note='solid curves are exact intersections of source meshes with the centre plane; MVS points are mesh vertices within the strip; dashed analytic curve is display-only 0.25m bin medians; stage-1 cells',
        visual_review='PENDING',scientific_verdict=None))
    print('section',key,flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site');ap.add_argument('--prior');a=ap.parse_args()
    cfg=json.loads(Path('/config/losstrain_v1.json').read_text())
    for ex in cfg['figures']['sections']:
        if a.site and a.site!=ex['site']:continue
        for prior in ex['priors']:
            if not a.prior or a.prior==prior:draw(ex,prior)

if __name__=='__main__':main()
