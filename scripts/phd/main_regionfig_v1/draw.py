"""Render only the frozen input evidence, with native photographs and linked section starts."""
import time
import resource
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, patheffects
from matplotlib.collections import PolyCollection, LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.transforms import Affine2D
from PIL import Image
from common import *

for p in ['/fonts/NotoSansCJK-Regular.ttc','/fonts/NotoSansCJK-Bold.ttc']:
    font_manager.fontManager.addfont(p)
plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,
                     'font.size':12,'pdf.fonttype':42,'axes.linewidth':.8})

def numpy_photo(rec):
    p=rec['photo'];pose={k:np.array(v) if k in ['R','t'] else v for k,v in p['pose'].items()}
    cam=dict(p['camera']);cam['p']=np.array(cam['p']);return p,pose,cam

def marker(ax,start,nextpoint,colour,photo=False,fontsize=13):
    ax.scatter(*start,s=85,c=colour,edgecolors='white',linewidths=1.7,zorder=20,clip_on=False)
    # Put the label opposite the forward direction in display coordinates.
    v=ax.transData.transform(nextpoint)-ax.transData.transform(start)
    v=v/max(np.linalg.norm(v),1e-9);off=-v*15
    txt=ax.annotate('시작',start,xytext=off,textcoords='offset points',color=colour,weight='bold',
                    fontsize=fontsize,ha='left' if off[0]>=0 else 'right',va='center',zorder=21,
                    bbox=dict(facecolor='white',alpha=.88,edgecolor='none',pad=1.3) if photo else None)
    return txt

def section_arrow(ax,xy,hidden=None,halo=False,lw=2.2):
    xy=np.asarray(xy);segments=np.stack([xy[:-1],xy[1:]],axis=1)
    if hidden is None:hidden=np.zeros(len(segments),bool)
    # Merge equal-visibility runs so a dash pattern does not restart at every 5 cm sample.
    hidden=np.asarray(hidden);cuts=np.r_[0,np.flatnonzero(hidden[1:]!=hidden[:-1])+1,len(hidden)]
    for i,j in zip(cuts[:-1],cuts[1:]):
        line,=ax.plot(xy[i:j+1,0],xy[i:j+1,1],color='black',lw=lw,
                      ls=(0,(3,2.5)) if hidden[i] else '-',zorder=12)
        if halo:line.set_path_effects([patheffects.Stroke(linewidth=lw+2,foreground='white'),patheffects.Normal()])
    # Head marks the final horizontal endpoint, irrespective of segment visibility.
    tail=xy[max(0,len(xy)-8)]
    a=ax.annotate('',xy[-1],xytext=tail,arrowprops=dict(arrowstyle='-|>',color='black',lw=lw,mutation_scale=16),zorder=13)
    if halo:a.arrow_patch.set_path_effects([patheffects.Stroke(linewidth=lw+2,foreground='white'),patheffects.Normal()])

def photo_polygons(ex,z,c,pose,cam,crop):
    cells=[c['cell_order'].index(k) for k in ex['highlight_cells']]
    m=z['in_eval']&np.isin(z['cell'],cells)&np.isfinite(z['gt_p'])
    centre=z['centre']+z['gt_p'][:,None]*z['normal']
    lo=np.minimum(ex['start_xy'],ex['end_xy'])-10;hi=np.maximum(ex['start_xy'],ex['end_xy'])+10
    m &= np.all((centre[:,:2]>=lo)&(centre[:,:2]<=hi),axis=1)
    ids=np.flatnonzero(m);n=z['normal'][ids];cc=centre[ids]
    # Stable tangent square at the GT-shifted centre, not the old prior height.
    helper=np.tile([0.,0.,1.],(len(n),1));helper[np.abs(n[:,2])>.9]=[1.,0.,0.]
    t1=np.cross(n,helper);t1/=np.linalg.norm(t1,axis=1)[:,None];t2=np.cross(n,t1)
    h=c['map']['cell_size_m']/2
    poly=np.stack([cc-h*t1-h*t2,cc+h*t1-h*t2,cc+h*t1+h*t2,cc-h*t1+h*t2],1)
    uv,depth=project(poly,pose,cam)
    x0,y0,x1,y1=crop
    inside=(depth>0).all(1)&(uv[:,:,0].max(1)>=x0)&(uv[:,:,0].min(1)<=x1)&(uv[:,:,1].max(1)>=y0)&(uv[:,:,1].min(1)<=y1)
    return uv[inside]-[x0,y0],ids[inside]

def photo(ax,ex,rec,z,c,export=False):
    p,pose,cam=numpy_photo(rec);im=np.asarray(Image.open(DOC/f"figures/crops/{ex['id']}_원본.png").convert('RGBA'))
    H,W=im.shape[:2]
    north_up=(CFG/'amendment_02.json').exists() and load(CFG/'amendment_02.json')['photo_display_north_up']
    angle=0.
    if north_up:
        mid=np.asarray(p['line_xyz'])[len(p['line_xyz'])//2]
        northuv,_=project(np.stack([mid,mid+[0,1,0]]),pose,cam)
        du,dv=northuv[1]-northuv[0]
        angle=np.pi/2-np.arctan2(-dv,du)
        transform=Affine2D().scale(1,-1).translate(-W/2,H/2).rotate(angle)
    else:transform=Affine2D()
    ax.imshow(im,extent=(0,W,H,0),interpolation='none',transform=transform+ax.transData)
    polys,ids=photo_polygons(ex,z,c,pose,cam,p['crop_box_px'])
    polys=transform.transform(polys.reshape(-1,2)).reshape(polys.shape)
    ax.add_collection(PolyCollection(polys,facecolors=ex['highlight_colour'],edgecolors='none',alpha=c['photo']['overlay_alpha'],zorder=5,rasterized=True))
    xy=transform.transform(np.array(p['line_pixels'])-p['crop_box_px'][:2])
    corners=transform.transform([[0,0],[W,0],[W,H],[0,H]])
    ax.set_xlim(corners[:,0].min(),corners[:,0].max())
    ax.set_ylim((corners[:,1].min(),corners[:,1].max()) if north_up else (H,0))
    ax.set_aspect('equal');ax.set_axis_off()
    section_arrow(ax,xy,np.array(p['line_midpoint_occluded']),halo=True)
    marker(ax,xy[0],xy[min(5,len(xy)-1)],c['colours']['start'],photo=True)
    if north_up:
        ax.annotate('북',xy=(.94,.96),xytext=(.94,.85),xycoords='axes fraction',ha='center',va='top',fontsize=11,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=1),
                    arrowprops=dict(arrowstyle='-|>',color='black',lw=1.3))
    return dict(projected_correction_patch_count=len(ids),projected_correction_patch_indices=ids,
                line_start_display_xy=xy[0],line_end_display_xy=xy[-1],crop_shape_px=[W,H],
                display_rotation_degrees=float(np.degrees(angle)),north_up=north_up)

def map_panel(ax,ex,rec,z,c):
    cell=z['cell'];m=z['in_eval'];p=z['centre'][m,:2];co=cell[m]
    corr=np.isin(co,[c['cell_order'].index(k) for k in ex['highlight_cells']])
    # Sorting only controls overdraw; every evaluation patch remains represented.
    priority=np.where(corr,3,np.where(co==c['cell_order'].index('c_refine'),2,1));order=np.argsort(priority,kind='stable')
    p=p[order];co=co[order];corr=corr[order]
    colours=np.where(corr,ex['highlight_colour'],np.where(co==c['cell_order'].index('c_refine'),c['colours']['refine'],
                np.where(co==c['cell_order'].index('c_nogt'),c['colours']['no_gt'],c['colours']['other'])))
    h=c['map']['cell_size_m']/2;d=np.array([[-h,-h],[h,-h],[h,h],[-h,h]])
    ax.add_collection(PolyCollection(p[:,None,:]+d,facecolors=colours,edgecolors='none',rasterized=True))
    lo=p.min(0);hi=p.max(0);span=hi-lo;pad=span*.04+1
    ax.set_xlim(lo[0]-pad[0],hi[0]+pad[0]);ax.set_ylim(lo[1]-pad[1]*2,hi[1]+pad[1]);ax.set_aspect('equal')
    foot=np.array(rec['photo']['crop_footprint_xyz']);ax.plot(foot[:,0],foot[:,1],ls=(0,(3,3)),lw=.9,color='0.25',zorder=7)
    start=np.array(ex['start_xy']);end=np.array(ex['end_xy']);line=np.linspace(start,end,30)
    section_arrow(ax,line,lw=2.1);marker(ax,start,end,c['colours']['start'])
    x=lo[0]+.03*span[0];y=lo[1]-.8*pad[1]
    ax.plot([x,x+10],[y,y],lw=3.3,color='black',solid_capstyle='butt')
    ax.text(x+5,y-pad[1]*.2,'10 m',ha='center',va='top',fontsize=10)
    ax.annotate('북',xy=(.91,.96),xytext=(.91,.84),xycoords='axes fraction',ha='center',va='top',fontsize=11,
                arrowprops=dict(arrowstyle='-|>',color='black',lw=1.2))
    ax.set_axis_off()

def delta_text(value_cm):
    unit=f'{abs(value_cm)/100:.1f} m' if abs(value_cm)>100 else f'{abs(value_cm):.0f} cm'
    return unit+(' 위' if value_cm>=0 else ' 아래')

def profile(ax,rec,c):
    edges=np.array(rec['bin_edges_m']);s=np.array(rec['bin_centres_m']);z=np.array(rec['heights_relative_m'],float)
    for i,b in enumerate(rec['correction_bins']):
        if b:ax.axvspan(edges[i],edges[i+1],color=c['colours']['highlight'],zorder=0,lw=0)
    ax.plot(s,z[:,0],color='black',lw=2.4,label=rec['prior_label'],zorder=3)
    ax.plot(s,z[:,1],color=c['colours']['mvs'],lw=2,label='MVS',zorder=4)
    ax.scatter(s,z[:,2],s=22,c=c['colours']['gt'],label='참값',zorder=6,edgecolors='none')
    finite=z[np.isfinite(z)];low,high=finite.min(),finite.max();span=high-low
    ax.set_ylim(low-.1*span-.12,high+.1*span+.12);ax.set_xlim(-.3,rec['length_m']+.3)
    ax.set_xlabel('시작점에서 화살표 쪽으로 간 거리 (m)',fontsize=11,labelpad=8)
    ax.set_ylabel('상대 높이 (m)',fontsize=12)
    ax.set_xticks(np.arange(0,13,2));ax.tick_params(labelsize=11)
    ax.legend(loc='upper left',frameon=True,facecolor='white',framealpha=.88,edgecolor='none',fontsize=11)
    lower=ax.get_ylim()[0]
    ax.scatter([0],[lower],s=85,c=c['colours']['start'],edgecolors='white',linewidths=1.7,zorder=20,clip_on=False)
    ax.annotate('시작',(0,lower),xytext=(8,9),textcoords='offset points',color=c['colours']['start'],weight='bold',fontsize=12)
    v=rec['values'];txt=rec.get('region','보정')+' 칸에서 참값보다\n'+rec['prior_label']+' '+delta_text(v['prior_minus_gt_cm'])+'\nMVS '+delta_text(v['mvs_minus_gt_cm'])
    ax.text(.985,.035,txt,transform=ax.transAxes,ha='right',va='bottom',fontsize=11,linespacing=1.25,
            bbox=dict(facecolor='white',edgecolor='0.8',pad=5),zorder=25)
    ax.grid(axis='y',color='0.9',lw=.6,zorder=1)

def main():
    t=time.time();c=load(CFG/'regionfig_v1.json');data=load(PAY/'prepared.json')
    assert sha(CFG/'regionfig_v1.json')==data['config_sha256']
    count=len(c['examples']);width,height=c['layout']['figure_inches']
    fig=plt.figure(figsize=(width,height*count/c['layout']['rows']),facecolor='white')
    gs=fig.add_gridspec(count,3,width_ratios=c['layout']['width_ratios'],left=.028,right=.978,bottom=.105,top=.866,hspace=.48,wspace=.19)
    title=fig.suptitle(c['title'],x=.5,y=.975,fontsize=23,weight='bold')
    headings=[];outputs=[]
    for row,(ex,rec) in enumerate(zip(c['examples'],data['examples'])):
        z,_=pv(ex);axes=[fig.add_subplot(gs[row,j]) for j in range(3)]
        top=gs[row,0].get_position(fig).y1
        headings.append(fig.text(.03,top+.065,ex['title'],fontsize=17,weight='bold'))
        for ax,label in zip(axes,c['layout']['columns']): ax.set_title(label,fontsize=13,color='0.35',pad=13)
        outputs.append(photo(axes[0],ex,rec,z,c));map_panel(axes[1],ex,rec,z,c);profile(axes[2],rec,c)
        # Save annotated crop at the original crop's pixel dimensions.
        W,H=rec['photo']['crop_size_px'];cf=plt.figure(figsize=(W/150,H/150),dpi=150)
        ca=cf.add_axes([0,0,1,1]);photo(ca,ex,rec,z,c,export=True)
        cf.savefig(DOC/f"figures/crops/{ex['id']}_표시.png",dpi=150);plt.close(cf)
    highlights={ex['region']:ex['highlight_colour'] for ex in c['examples']}
    handles=[Patch(facecolor=colour,label=region) for region,colour in highlights.items()]+[Patch(facecolor=c['colours']['refine'],label='다듬기'),
             Patch(facecolor=c['colours']['other'],label='그 밖의 칸'),Line2D([0,1],[0,0],color='black',lw=2,marker='>',markevery=[1],label='단면 자리와 방향')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.02),ncol=4,frameon=False,fontsize=13,handlelength=2.2,columnspacing=2.8)
    fig.text(.03,.073,'사진의 점선: 가려진 구간   ·   지도의 점선 네모: 사진 범위   ·   각 단면 참값의 최저 칸 = 0 m',fontsize=10,color='0.4')
    out=DOC/'figures'/c.get('output_stem','영역예시_'+'_'.join(highlights))
    fig.savefig(str(out)+'.png',dpi=c['layout']['dpi'])
    fig.savefig(str(out)+'.pdf',dpi=c['layout']['dpi'],metadata={'Title':c['title'],'Subject':'Input-only evidence; scientific_verdict: null'})
    # This separate rendering is the ONLY file supplied to the blind visual reviewer.
    title.set_visible(False)
    for h in headings:h.set_visible(False)
    fig.savefig(DOC/'figures/검토용_제목숨김.png',dpi=180)
    plt.close(fig)
    receipt=dict(rendered_at=now(),config_sha256=data['config_sha256'],amendments=[load(p) for p in sorted(CFG.glob('amendment_[0-9][0-9].json'))],seconds=time.time()-t,
                 max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,photo_overlay=outputs,scientific_verdict=None)
    dump(PAY/'render_receipt.json',receipt);dump(DOC/'figures/영역예시_보정_숫자.json',dict(data,render=receipt))
    print('RENDERED',receipt['seconds'],'s; peak KiB',receipt['max_rss_kib'])

if __name__=='__main__':main()
