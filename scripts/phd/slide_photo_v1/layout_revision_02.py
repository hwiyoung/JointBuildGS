"""Presentation revision only: frozen inputs, fixed selection and existing measurements."""
import io, json, zipfile, copy
from common import *
from photos import models, outlined
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy.spatial import ConvexHull

OUT=DOC/'revision_02'; FIG=OUT/'figures'; CACHE=PAY/'revision_02'; CACHE.mkdir(exist_ok=True)
BG='white'; INK='#172633'; GT='#253F52'; PROP='#B94A2E'; GOLD='#C08A2B'
FONT='/fonts/NotoSansCJK-Regular.ttc'; BOLD='/fonts/NotoSansCJK-Bold.ttc'
def font(n,bold=False):return ImageFont.truetype(BOLD if bold else FONT,n)
def text(im,xy,s,n=76,col=INK,bold=False,anchor='lt'):
    ImageDraw.Draw(im).text(xy,s,font=font(n,bold),fill=col,anchor=anchor)
def box(im,rect):
    x,y,w,h=rect;return im.crop((int(x),int(y),int(x+w),int(y+h)))
def paste(im,src,rect):
    x,y,w,h=map(int,rect);im.paste(src.resize((w,h),Image.Resampling.LANCZOS),(x,y))
def source(n):return load(DOC/'figures'/f'{n}.json')
def emit(n,im,meta):
    im.save(FIG/f'{n}.png');meta.update(task_id='PHD-SLIDE-PHOTO-v1-R2',scientific_verdict=None,source_metadata_sha256=sha(DOC/'figures'/f'{n}.json') if (DOC/'figures'/f'{n}.json').exists() else None)
    dump(FIG/f'{n}.json',meta)
def native(rec):
    with zipfile.ZipFile(RAW) as z:raw=z.read(rec['original_member'])
    import hashlib
    assert hashlib.sha256(raw).hexdigest()==rec['original_sha256']
    return Image.open(io.BytesIO(raw)).convert('RGB')
def crop_rect(size,centre,width,aspect):
    W,H=size;width=min(width,W,H*aspect);height=width/aspect
    x=float(np.clip(centre[0]-width/2,0,W-width));y=float(np.clip(centre[1]-height/2,0,H-height))
    return [int(round(x)),int(round(y)),int(round(x+width)),int(round(y+height))]
def roi_on_crop(photo):
    return np.asarray(photo['polygon_px'])
def chip(im,xy,s,n=76):
    d=ImageDraw.Draw(im);bb=d.textbbox(xy,s,font=font(n,True),anchor='lt');d.rectangle((bb[0]-9,bb[1]-7,bb[2]+9,bb[3]+7),fill='white');d.text(xy,s,font=font(n,True),anchor='lt',fill=INK)

def draw_a():
    import draw_a as old
    n='figS_a_image_limits';frozen=source(n);cache=CACHE/'a_cache.json'
    if not cache.exists():
        selected=load(DOC/'figures/task0_specular_candidates.json')['selected'];parts=[]
        for i,r in enumerate(frozen['panels']):
            raw,marked,rec=old.specular_panel(selected) if i==2 else old.legacy_panel(r['site'],r['face'],r['photo']['view'],r['patch_indices'])
            for key in ['pixels','missing_share','wrong_share','unknown_gt_share','tau_m']:assert rec[key]==r[key]
            raw.save(CACHE/f'a_{i}_raw.png');marked.save(CACHE/f'a_{i}_marked.png');parts.append(rec)
        dump(cache,parts)
    parts=load(cache);im=Image.new('RGB',(2700,1200),'white');recs=[]
    labels=['무늬 없는 지붕','그늘진 벽','금속 벽'];W=884;H=450
    for i,(r,label) in enumerate(zip(parts,labels)):
        raw=Image.open(CACHE/f'a_{i}_raw.png');marked=Image.open(CACHE/f'a_{i}_marked.png');p=np.asarray(r['photo']['polygon_px'])
        if i<2:
            # The visible locmap pixels, rather than the full projected face polygon,
            # locate the small observed roof strip and the fixed wall column.
            import cv2
            from task0_scan import cameras_depth
            lm=np.load(S0/'s61/export'/r['site']/'LoD2/locmap'/f'{r["photo"]["view"]}.npy');jj,ii=np.nonzero(np.isin(lm,r['patch_indices']));_,gc=cameras_depth();fx,fy,cx,cy=gc['p'];rays=np.c_[(ii+.5-cx)/fx,(jj+.5-cy)/fy,np.ones(len(ii))];cp=np.asarray(r['photo']['camera']['p']);K=np.array([[cp[0],0,cp[2]],[0,cp[1],cp[3]],[0,0,1.]])
            q,_=cv2.projectPoints(rays,np.zeros(3),np.zeros(3),K,cp[4:]);q=q.reshape(-1,2)-r['photo']['crop_box_px'][:2];p=q[ConvexHull(q).vertices]
        if r['photo'].get('display_rotation_deg')==90:p=np.c_[p[:,1],r['photo']['native_crop_size'][0]-p[:,0]]
        lo=np.maximum(p.min(0),[0,0]);hi=np.minimum(p.max(0),raw.size);mid=(lo+hi)/2
        # The exact same fixed face is enlarged. Tall wall columns retain vertical context.
        width=max(hi[0]-lo[0],(hi[1]-lo[1])*W/H)*1.08
        if i==0:width=max(220,width*1.3)
        if i==1:width=max(240,width*.62)
        if i==2:width*=.63
        crop=crop_rect(raw.size,mid,width,W/H);left=i*908
        paste(im,raw.crop(crop),(left,100,W,H));paste(im,marked.crop(crop),(left,566,W,H))
        # Photo markers are visibly outside the data: only the top, uncoloured photo gets the outline.
        pp=(p-np.array(crop[:2]))*np.array([W/(crop[2]-crop[0]),H/(crop[3]-crop[1])])
        top=raw.crop(crop).resize((W,H),Image.Resampling.LANCZOS);dr=ImageDraw.Draw(top);poly=[tuple(v) for v in pp];dr.line(poly+[poly[0]],fill='#16202A',width=13,joint='curve');dr.line(poly+[poly[0]],fill='#FFD60A',width=7,joint='curve');im.paste(top,(left,100))
        text(im,(left+W/2,12),label,n=81,bold=True,anchor='mt')
        text(im,(left+W/2,1035),f'없음 {r["missing_share"]*100:.0f}% · 틀림 {r["wrong_share"]*100:.0f}%',n=78,bold=True,anchor='mt')
        if i==0:text(im,(left+W/2,1120),'평가 20화소',n=74,col='#5A6470',anchor='mt')
        recs.append(dict(source=r,display_crop_in_rotated_source_crop_px=crop,photo_rects=[[left,100,W,H],[left,566,W,H]]))
    emit(n,im,dict(panels=recs,measurements_unchanged=True,source_selection='all original sites/views/patches retained',minimum_font_px=74,photo_area_share=6*W*H/(2700*1200)))

def d_arrays():
    meta=source('figS_d_gs_real');sel=meta['selection'];view=sel['view'];x0,y0,x1,y1=sel['crop_box_grid_px'];sl=np.s_[y0:y1,x0:x1]
    ex=S0/'s61/export/B0_b10/LoD2';a=[np.asarray(Image.open(meta['actual_image']))[sl],np.asarray(Image.open(meta['saved_rgb']))[sl]]
    depths=[np.load(ex/'mvs'/f'{view}.npy')[sl],np.load(meta['saved_depth'])[sl],np.load(ex/'prior'/f'{view}.npy')[sl]]
    cf=np.load(ex/'conf'/f'{view}.npy')[sl];depths[0]=np.where(cf>0,depths[0],np.nan)
    return meta,[np.rot90(x) for x in a+depths]

def draw_d():
    from plyfile import PlyData
    from matplotlib.collections import PolyCollection
    plt=plot_setup(36);meta,arr=d_arrays();roi=[0,170,741,400];out=Image.new('RGB',(3200,800),'white')
    # Fixed input-photo crop, applied unchanged to actual RGB, saved RGB and all three depth arrays.
    rects=[(830,80,1158,360),(2042,80,1158,360),(830,556,756,235),(1637,556,756,235),(2444,556,756,235)]
    labels=['실제 영상','렌더링 영상','MVS 깊이','렌더링 깊이','사전 정보 깊이']
    lo,hi=meta['depth_colour_range_m'];cm=plt.get_cmap('viridis')
    for i,(r,l,a) in enumerate(zip(rects,labels,arr)):
        x0,y0,x1,y1=roi;a=a[y0:y1,x0:x1]
        if i<2:pic=Image.fromarray(a).convert('RGB')
        else:
            good=np.isfinite(a)&(a>0);col=np.uint8(cm(np.clip((a-lo)/(hi-lo),0,1))*255)[:,:,:3];col[~good]=255;pic=Image.fromarray(col)
        paste(out,pic,r);text(out,(r[0],r[1]-66),l,n=54,bold=True)
    v=PlyData.read(meta['gaussian_file'])['vertex'].data;xyz=np.c_[v['x'],v['y'],v['z']];mid=np.asarray(meta['gaussian_display']['centre_xyz']);ids=np.flatnonzero((abs(xyz[:,0]-mid[0])<=1.5)&(abs(xyz[:,1]-mid[1])<=1.5)&(abs(xyz[:,2]-mid[2])<=2)&(v['opacity']>-4))
    q=np.c_[v['rot_0'][ids],v['rot_1'][ids],v['rot_2'][ids],v['rot_3'][ids]];q/=np.linalg.norm(q,axis=1)[:,None];R=np.stack([G.qR(x) for x in q]);sc=np.exp(np.c_[v['scale_0'][ids],v['scale_1'][ids]])*.25;t=np.linspace(0,2*np.pi,33)
    ell=xyz[ids,None,:]+R[:,:,0][:,None,:]*sc[:,0,None,None]*np.cos(t)[None,:,None]+R[:,:,1][:,None,:]*sc[:,1,None,None]*np.sin(t)[None,:,None]
    uv=np.stack([(ell-mid)@np.array([1.,0.,0.]),(ell-mid)@np.array([0.,-.5,np.sqrt(.75)])],-1);cols=np.clip(.5+.28209479177387814*np.c_[v['f_dc_0'][ids],v['f_dc_1'][ids],v['f_dc_2'][ids]],0,1)
    fig=plt.figure(figsize=(7.8,5.1),dpi=100);ax=fig.add_axes([0,0,1,1]);ax.add_collection(PolyCollection(uv,facecolors=cols,edgecolors='#3A4A5E',linewidths=.6,alpha=.95));ax.autoscale_view();ax.margins(.01);ax.set_aspect('equal');ax.axis('off');f=CACHE/'gaussians.png';fig.savefig(f,dpi=100,facecolor='white');plt.close(fig)
    paste(out,Image.open(f),(0,80,780,510));text(out,(10,14),'가우시안의 집합',n=54,bold=True)
    pic=Image.open(PAY/'c_repr_native.png');paste(out,ImageOps.fit(pic,(780,180)),(0,620,780,180));chip(out,(12,631),'같은 지붕',n=52)
    dr=ImageDraw.Draw(out)
    for x,y in [(2013,250),(1612,680),(2418,680)]:
        dr.line((x-16,y,x+16,y),fill=INK,width=4);dr.line((x-16,y,x-7,y-8),fill=INK,width=4);dr.line((x-16,y,x-7,y+8),fill=INK,width=4);dr.line((x+16,y,x+7,y-8),fill=INK,width=4);dr.line((x+16,y,x+7,y+8),fill=INK,width=4)
    emit('figS_d_gs_real',out,dict(source=meta,shared_additional_crop_after_rotation_px=roi,shared_depth_colour_range_m=[lo,hi],panels=[dict(label=l,rect_px=r) for l,r in zip(labels,rects)],gaussian_count=len(ids),minimum_font_px=52,photo_area_share=sum(r[2]*r[3] for r in rects)/(3200*800)))

def draw_e():
    for key in ['keep','correct','refine','inherit']:
        n='figS_e_aim_'+key;meta=source(n);p=meta['photo'];p['pose']['R']=np.asarray(p['pose']['R']);p['pose']['t']=np.asarray(p['pose']['t']);im=native(p);poly=np.asarray(p.get('polygon_px',[]))+np.asarray(p['crop_box_px'][:2]);rotation=p.get('display_rotation_deg',0)
        if key=='inherit':
            line,_=G.project(np.asarray(meta['line_xyz']),p['pose'],p['camera']);poly=line
        if key=='correct':rotation=90
        if rotation==90:
            poly=np.c_[poly[:,1],im.width-poly[:,0]];im=im.transpose(Image.Transpose.ROTATE_90)
        mid=(poly.min(0)+poly.max(0))/2;span=poly.max(0)-poly.min(0)
        if key=='keep':width=max(span[0]*.36,span[1]*1.9);mid[1]+=span[1]*.22
        elif key=='correct':width=max(span[0]*1.10,span[1]*1.80*1.10)
        elif key=='refine':width=max(span[0]*1.10,span[1]*1.80*1.10)
        else:width=span[0]*.42;mid[1]-=width*.07
        crop=crop_rect(im.size,mid,width,1.8);zoom=im.crop(crop).resize((1080,600),Image.Resampling.LANCZOS);q=(poly-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])]
        lay=Image.new('RGBA',zoom.size);d=ImageDraw.Draw(lay)
        if key!='inherit':
            xy=[tuple(a) for a in q];d.polygon(xy,fill=(255,214,10,22));d.line(xy+[xy[0]],fill=(0,0,0,255),width=10,joint='curve');d.line(xy+[xy[0]],fill=(255,214,10,255),width=5,joint='curve')
        else:
            # Same frozen occluding face as before; record it is the same building roof.
            u=np.load(S0/'s61/box/B173nb_b10/LoD2/units.npz');surf=u['surf_ext'][u['loc_surface']];x=u['loc_center'][np.isin(surf,meta['occluding_faces'])];a,_=G.project(x,p['pose'],p['camera']);a=np.c_[a[:,1],p['camera']['w']-a[:,0]];a=(a-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])];a=a[ConvexHull(a).vertices];d.polygon([tuple(v) for v in a],fill=(255,214,10,22));xy=[tuple(a) for a in q];d.line(xy,fill=(0,0,0,255),width=12);d.line(xy,fill=(255,214,10,255),width=6)
        result=Image.alpha_composite(zoom.convert('RGBA'),lay).convert('RGB');emit(n,result,dict(source=meta,display_rotation_deg=rotation,crop_in_rotated_native_px=crop,detail_only=key in ['keep','inherit'],whole_selection_and_values_unchanged=True))

def b_data():
    b=source('figS_b_correction_sections');h=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples'];cache=CACHE/'b_raw_reference_bands.npz'
    if not cache.exists():
        sys.path.insert(0,'/repo/scripts/phd/main_photofig_v1');import pf_geo as geo
        vals={}
        for i,e in enumerate(b['examples']):
            spec=e['example'];start=np.asarray(spec['start_xy']);axis=np.asarray(spec['end_xy'])-start;length=np.linalg.norm(axis);axis/=length
            with np.load(S1/'defs'/spec['site']/'gt_classes.npz') as z:
                parts=[]
                for k in ['xyz_gt_points','xyz_gt_primary']:
                    if k in z.files:
                        X=z[k];ok,s=geo.band(X,start,axis,[0,length],half=spec['half_width_m']);parts.append(np.c_[s[ok],X[ok,2]])
            vals[f'case{i}']=np.concatenate(parts)
        np.savez_compressed(cache,**vals)
    return b,h,dict(np.load(cache))

def b_axis(ax,e,h,raw,method,focus=False):
    from matplotlib.collections import LineCollection
    H=np.asarray(h['heights_model_m']);ss=np.asarray(h['bin_centres_m']);zero=e['height_zero_m'];length=np.linalg.norm(np.subtract(e['example']['end_xy'],e['example']['start_xy']))
    ax.scatter(raw[:,0],raw[:,1]-zero,s=7 if focus else 1.8,facecolors='none',edgecolors=GT,alpha=.8,linewidths=.65 if focus else .4,rasterized=True,zorder=1)
    ax.plot(ss,H[:,0]-zero,color=GOLD,ls='--',lw=2.8 if focus else 2,alpha=.55 if focus else .35,zorder=2)
    if method is not None:
        seg=np.asarray(method['section_segments']).copy();seg[:,:,1]-=zero;proposal=method['name']=='본 방법'
        ax.add_collection(LineCollection(seg,colors=PROP if proposal else '#9AA3A9',linewidths=4.8 if proposal else 1.8,zorder=3))
    # Input-only panel retains the original bin summaries; result panels use raw GT.
    if method is None:ax.scatter(ss,H[:,2]-zero,s=27,facecolors='white',edgecolors=GT,linewidths=1.4,zorder=4)
    ax.set_xlim(0,length);ax.set_ylim(np.asarray(e['height_range_m'])-zero);ax.set_xticks([0,4,8,12]);ax.tick_params(labelsize=35);ax.spines['left'].set_color('#A5ADB2');ax.spines['bottom'].set_color('#A5ADB2')
    return zero

def draw_b():
    from matplotlib.lines import Line2D
    b,h,raw=b_data();plt=plot_setup(35);fig=plt.figure(figsize=(32,10.77),dpi=100)
    for i,(e,hh) in enumerate(zip(b['examples'],h)):
        ax=fig.add_axes([.055+i*.50,.16,.425,.69]);o=e['outputs'][-1];b_axis(ax,e,hh,raw[f'case{i}'],o,True);ax.set_xlabel('단면 거리 (m)',fontsize=35);ax.set_ylabel('높이 (m)',fontsize=35);ax.set_title('B173 · 항공 LiDAR' if i==0 else 'R1 · LoD2',loc='left',fontsize=35,pad=18)
        ax.text(.98,.94,f'τ 안 {o["within_tau_share"]*100:.0f}%',transform=ax.transAxes,ha='right',va='top',fontsize=35,color=PROP,fontweight='bold')
    fig.legend(handles=[Line2D([],[],marker='o',mfc='white',mec=GT,mew=2,color=GT,ls='none',markersize=12,label='참값'),Line2D([],[],color=PROP,lw=5,label='제안 방법'),Line2D([],[],color=GOLD,ls='--',lw=3,alpha=.6,label='사전 정보')],loc='upper center',bbox_to_anchor=(.50,1.015),ncol=3,frameon=False,fontsize=35)
    n='figS_b_correction_sections';fig.savefig(FIG/f'{n}.png',dpi=100,facecolor='white');plt.close(fig)
    dump(FIG/f'{n}.json',dict(task_id='PHD-SLIDE-PHOTO-v1-R2',scientific_verdict=None,source_metadata_sha256=sha(DOC/'figures'/f'{n}.json'),source=b,reference_points='All frozen raw GT band points shown as dark open circles, no aggregation or thinning',focus='Reference and proposal only, same section limits; baseline comparison is separately delivered',minimum_font_px=35*100/72,metric_changes=False))
    # Companion retains every method and exact photograph, with a quieter hierarchy.
    fig=plt.figure(figsize=(32,10.77),dpi=100)
    for row,(e,hh) in enumerate(zip(b['examples'],h)):
        bottom=.565 if row==0 else .09;ax=fig.add_axes([.005,bottom,.14,.32]);ax.imshow(Image.open(e['photo']));ax.axis('off')
        for col in range(6):
            ax=fig.add_axes([.18+col*.135,bottom,.117,.32]);o=None if col==0 else e['outputs'][col-1];b_axis(ax,e,hh,raw[f'case{row}'],o);ax.set_xticks([0,12]);ax.get_xticklabels()[0].set_ha('left');ax.get_xticklabels()[-1].set_ha('right')
            label='입력' if col==0 else ('제안 방법' if col==5 else o['name']);ax.set_title(label,fontsize=35,color=PROP if col==5 else INK,fontweight='bold' if col==5 else 'normal')
            if col==0:ax.plot(hh['bin_centres_m'],np.asarray(hh['heights_model_m'])[:,1]-e['height_zero_m'],color='#2C6AA0',lw=2);ax.set_ylabel('높이 (m)',fontsize=35)
            else:ax.set_yticks([]);ax.text(.5,-.25,f'τ 안 {o["within_tau_share"]*100:.0f}%',ha='center',transform=ax.transAxes,fontsize=35,color=PROP if col==5 else '#53606B')
    fig.text(.40,.985,'○ 참값',color=GT,fontsize=35,ha='center',va='top');fig.text(.68,.985,'제안 방법',color=PROP,fontsize=35,ha='center',va='top')
    n='figS_b_all_methods';fig.savefig(FIG/f'{n}.png',dpi=100,facecolor='white');plt.close(fig);dump(FIG/f'{n}.json',dict(task_id='PHD-SLIDE-PHOTO-v1-R2',scientific_verdict=None,source=b,minimum_font_px=35*100/72,metric_changes=False))

if __name__=='__main__':
    config();FIG.mkdir(exist_ok=True,parents=True);globals()['draw_'+sys.argv[1]]();print('LAYOUT',sys.argv[1],now(),flush=True)
