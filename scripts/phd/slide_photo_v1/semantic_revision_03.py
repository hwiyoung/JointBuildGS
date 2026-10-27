"""Explain frozen observations using source photos, measured comparisons and labels.

No new selection, training, result geometry or metric calculation is performed.
"""
import shutil
import layout_revision_02 as L
from common import *
from PIL import Image, ImageDraw, ImageOps

OUT=DOC/'revision_03'; FIG=OUT/'figures'; CACHE=PAY/'revision_03'
GT='#3A4A5E'; PRIOR='#C08A2B'; MVS='#2C6AA0'; PROP='#B94A2E'
MISSING='#D32AA8'; WRONG='#D93636'; INK='#172633'

def save(name,im,meta):
    im.save(FIG/f'{name}.png')
    dump(FIG/f'{name}.json',dict(task_id='PHD-SLIDE-PHOTO-v1-R3',scientific_verdict=None,
         measurements_unchanged=True,selection_unchanged=True,**meta))

def arrow(im,start,end,col=INK,width=7):
    d=ImageDraw.Draw(im);a=np.asarray(start,float);b=np.asarray(end,float);v=(a-b)/np.linalg.norm(a-b);n=np.array([-v[1],v[0]])
    d.line([tuple(a),tuple(b)],fill=col,width=width);d.polygon([tuple(b),tuple(b+v*22+n*11),tuple(b+v*22-n*11)],fill=col)

def chip(im,xy,s,n=74,col=INK):
    d=ImageDraw.Draw(im);bb=d.textbbox(xy,s,font=L.font(n,True),anchor='lt');d.rectangle((bb[0]-8,bb[1]-4,bb[2]+8,bb[3]+6),fill='white');d.text(xy,s,font=L.font(n,True),fill=col,anchor='lt')

def draw_a():
    old=L.source('figS_a_image_limits');layout=load(DOC/'revision_02/figures/figS_a_image_limits.json')
    im=Image.new('RGB',(2700,1200),'white');records=[]
    for i,(r,title) in enumerate(zip(old['panels'],['무늬 없는 지붕','그늘진 벽','금속 면'])):
        x=i*908;W=884;H=400;crop=layout['panels'][i]['display_crop_in_rotated_source_crop_px']
        raw=Image.open(L.CACHE/f'a_{i}_raw.png').convert('RGB');marked=Image.open(L.CACHE/f'a_{i}_marked.png').convert('RGB')
        a=np.asarray(raw);b=np.asarray(marked);changed=np.any(a!=b,axis=2)
        # Reduce background colour only; every marked pixel stays byte-identical.
        grey=np.asarray(ImageOps.grayscale(raw).convert('RGB'));display=grey.copy();display[changed]=b[changed]
        top=raw.crop(crop).resize((W,H),Image.Resampling.LANCZOS)
        bottom=Image.fromarray(display).crop(crop).resize((W,H),Image.Resampling.LANCZOS)
        im.paste(top,(x,95));im.paste(bottom,(x,550));L.text(im,(x+W/2,3),title,80,bold=True,anchor='mt')
        chip(im,(x+15,110),'실제 사진',74)
        chip(im,(x+15,565),'깊이 검사',74)
        # Callout targets an actually coloured pixel, never the unobserved area.
        overlay=(b.astype(float)-.48*a)/.52;target_colour=np.array([211,42,168] if i<2 else [217,54,54]);kind=changed&(np.linalg.norm(overlay-target_colour,axis=2)<5)
        cc=kind[crop[1]:crop[3],crop[0]:crop[2]];yy,xx=np.nonzero(cc);j=np.argmin((xx-np.median(xx))**2+(yy-np.median(yy))**2)
        target=np.array([xx[j]*W/cc.shape[1]+x,yy[j]*H/cc.shape[0]+550])
        label='깊이 없음' if i<2 else '깊이 틀림';col=MISSING if i<2 else WRONG
        chip(im,(x+22,850),label,74,col);arrow(im,(x+260,838),target,col,8)
        metric=f'없음 {r["missing_share"]*100:.0f}% · 틀림 {r["wrong_share"]*100:.0f}%'
        L.text(im,(x+W/2,970),metric,74,bold=True,anchor='mt')
        if i==0:L.text(im,(x+W/2,1055),'평가 20화소 · 칠 4화소',74,anchor='mt')
        records.append(dict(source=r,display_crop=crop,callout_actual_coloured_pixel=target.tolist()))
    L.text(im,(2675,1110),'자홍: 깊이 없음   빨강: 참값과 불일치',74,anchor='rt')
    save('figS_a_image_limits',im,dict(panels=records,minimum_font_px=74,unknown_gt_policy='Unchanged: unknown GT pixels remain uncoloured. Roof missing count uses 20 pixels; only four have GT support.',display_change='Greyscale only outside existing masks; labels and leaders identify measured pixels.'))

def gaussian_photo_pair():
    from plyfile import PlyData
    meta=L.source('figS_d_gs_real');p=L.source('figS_c_repr')['photo'];pose=p['pose'];pose['R']=np.asarray(pose['R']);pose['t']=np.asarray(pose['t'])
    v=PlyData.read(meta['gaussian_file'])['vertex'].data;xyz=np.c_[v['x'],v['y'],v['z']];mid=np.asarray(meta['gaussian_display']['centre_xyz'])
    ids=np.flatnonzero((abs(xyz[:,0]-mid[0])<=1.5)&(abs(xyz[:,1]-mid[1])<=1.5)&(abs(xyz[:,2]-mid[2])<=2)&(v['opacity']>-4))
    q=np.c_[v['rot_0'][ids],v['rot_1'][ids],v['rot_2'][ids],v['rot_3'][ids]];q/=np.linalg.norm(q,axis=1)[:,None];R=np.stack([G.qR(x) for x in q]);sc=np.exp(np.c_[v['scale_0'][ids],v['scale_1'][ids]])*.25;t=np.linspace(0,2*np.pi,33)
    ell=xyz[ids,None,:]+R[:,:,0][:,None,:]*sc[:,0,None,None]*np.cos(t)[None,:,None]+R[:,:,1][:,None,:]*sc[:,1,None,None]*np.sin(t)[None,:,None]
    uv,_=G.project(ell.reshape(-1,3),pose,p['camera']);uv=uv.reshape(-1,33,2);centres,_=G.project(xyz[ids],pose,p['camera'])
    aspect=780/262;crop=L.crop_rect((p['camera']['w'],p['camera']['h']),(centres.min(0)+centres.max(0))/2,max(np.ptp(centres[:,0]),np.ptp(centres[:,1])*aspect)*1.2,aspect)
    pic=L.native(p).crop(crop).resize((780,262),Image.Resampling.LANCZOS);ellpic=Image.new('RGB',(780,262),'#F5F7F9');d=ImageDraw.Draw(ellpic)
    cols=np.clip(.5+.28209479177387814*np.c_[v['f_dc_0'][ids],v['f_dc_1'][ids],v['f_dc_2'][ids]],0,1)
    for poly,col in zip(uv,cols):
        xy=(poly-crop[:2])*[780/(crop[2]-crop[0]),262/(crop[3]-crop[1])];d.polygon([tuple(a) for a in xy],fill=tuple(np.uint8(col*255)),outline=GT,width=1)
    return pic,ellpic,dict(source_photo=p,original_photo_crop=crop,gaussian_ids=ids.tolist(),display_scale=.25,projection='Exact same source camera for photo and Gaussian ellipses',gaussian_file=meta['gaussian_file'])

def draw_d():
    plt=plot_setup();meta,arr=L.d_arrays();roi=[0,170,741,400];im=Image.new('RGB',(3200,800),'white')
    pic,ell,gm=gaussian_photo_pair();L.paste(im,pic,(0,78,780,262));L.paste(im,ell,(0,438,780,262))
    L.text(im,(6,5),'같은 지붕의 사진',52,bold=True);L.text(im,(6,370),'작은 타원들의 집합',52,bold=True)
    rects=[(850,78,1030,320),(2170,78,1030,320),(850,473,730,227),(1660,473,730,227),(2470,473,730,227)]
    labels=['실제 영상','렌더링 영상','MVS 깊이','렌더링 깊이','사전 정보 깊이'];lo,hi=meta['depth_colour_range_m'];cm=plt.get_cmap('viridis')
    for i,(r,label,a) in enumerate(zip(rects,labels,arr)):
        a=a[roi[1]:roi[3],roi[0]:roi[2]]
        if i<2:photo=Image.fromarray(a).convert('RGB')
        else:
            valid=np.isfinite(a)&(a>0);rgb=np.uint8(cm(np.clip((a-lo)/(hi-lo),0,1))*255)[:,:,:3];rgb[~valid]=255;photo=Image.fromarray(rgb)
        L.paste(im,photo,r);L.text(im,(r[0],r[1]-65),label,52,bold=True)
    for a,b in [((1900,250),(2150,250)),((1590,580),(1650,580)),((2400,580),(2460,580))]:arrow(im,a,b,width=5);arrow(im,b,a,width=5)
    L.text(im,(2025,174),'색 비교',52,bold=True,anchor='mt')
    L.text(im,(1600,731),'타원 표현 → 미분 가능 렌더링 → 실제 영상·깊이와 비교',54,bold=True,anchor='mt')
    save('figS_d_gs_real',im,dict(source=meta,gaussian_photo_pair=gm,shared_additional_crop_after_rotation_px=roi,shared_depth_colour_range_m=[lo,hi],panels=[dict(label=l,rect_px=r) for l,r in zip(labels,rects)],minimum_font_px=52,depth_missing_white=True))

def plot_card(key):
    plt=plot_setup(50);fig=plt.figure(figsize=(10.8,5.2),dpi=100);ax=fig.add_axes([.05,.10,.90,.75]);evidence={}
    if key=='keep':
        m=L.source('figS_c_specular');data=np.load(PAY/'task0/selected_clouds.npz');mid=np.array(m['view']['centre']);e1=np.array(m['view']['axis1']);e2=np.array(m['view']['axis2'])
        projected={k:np.c_[(data[k]-mid)@e1,(data[k]-mid)@e2] for k in ['mvs','prior','gt']}
        for k,col,s in [('mvs',MVS,7),('prior',PRIOR,45),('gt',GT,22)]:
            v=projected[k];ax.scatter(v[:,0],v[:,1],c=col,s=s,alpha=.55 if k=='mvs' else 1,linewidths=0)
        q=projected['gt'];ax.set_xlim(q[:,0].min()-.3,q[:,0].max()+.3);ax.set_ylim(q[:,1].min()-1,q[:,1].max()+1);ax.axis('off')
        evidence=dict(source='figS_c_specular.json',plot='Existing selected_clouds.npz and fixed orthographic projection; no fitted or synthetic lines',mvs_abs_median_m=m['reference_mvs_abs_median_m'],prior_abs_median_m=m['reference_prior_abs_median_m'])
    elif key=='correct':
        rec=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples'][0];H=np.asarray(rec['heights_model_m']);x=np.asarray(rec['bin_centres_m']);zero=np.nanmin(H)
        ax.plot(x,H[:,0]-zero,c=PRIOR,lw=5,ls='--');ax.plot(x,H[:,1]-zero,c=MVS,lw=4);ax.scatter(x,H[:,2]-zero,c=GT,s=55,zorder=3)
        ax.set_xlim(x.min(),x.max());ax.set_ylim(-.5,np.nanmax(H)-zero+.7);ax.axis('off')
        evidence=dict(source='main_regionfig_v1/tables/영역예시_보정_숫자.json examples[0]',section_bins=rec['bin_centres_m'],height_values=rec['heights_model_m'],same_source_section=True)
    elif key=='refine':
        m=L.source('figS_c_repr');a=np.asarray(m['section']['heights']);ax.plot(a[:,0],a[:,1],c=PRIOR,lw=5,ls='--');ax.plot(a[:,0],a[:,3],c=MVS,lw=4);ax.scatter(a[:,0],a[:,2],c=GT,s=65,zorder=3)
        ax.set_xlim(-2.5,2.5);ax.set_ylim(a[:,1:].min()-.05,a[:,1:].max()+.05);ax.axis('off');evidence=dict(source='figS_c_repr.json',section=m['section'],median_prior_minus_gt_m=m['selection']['prior_signed_median_m'],vertical_exaggeration=True)
    else:
        m=L.source('figS_e_aim_inherit');u=np.load(S0/'s61/box/B173nb_b10/LoD2/units.npz');surf=u['surf_ext'][u['loc_surface']];wall=u['loc_center'][surf==53];roof=u['loc_center'][np.isin(surf,m['occluding_faces'])];mid=wall.mean(0)
        _,_,vt=np.linalg.svd(wall[:,:2]-mid[:2],full_matrices=False);cross=np.array([-vt[0,1],vt[0,0]])
        pose=m['photo']['pose'];cam=-np.asarray(pose['R']).T@np.asarray(pose['t']);cross*=np.sign((cam[:2]-mid[:2])@cross) or 1
        def proj(X):return np.c_[(X[:,:2]-mid[:2])@cross,X[:,2]-wall[:,2].min()]
        from scipy.spatial import ConvexHull
        wr=proj(wall);rr=proj(roof);h=rr[ConvexHull(rr).vertices];ax.fill(h[:,0],h[:,1],color='#CED6DC');ax.plot(np.r_[h[:,0],h[0,0]],np.r_[h[:,1],h[0,1]],color=GT,lw=3)
        ax.plot([0,0],[wr[:,1].min(),wr[:,1].max()],c=PRIOR,lw=6,ls='--')
        # Direction is derived from the original camera, shortened for legibility.
        target=np.array([0,np.median(wr[:,1])]);camera=np.array([(cam[:2]-mid[:2])@cross,cam[2]-wall[:,2].min()]);v=camera-target;v/=np.linalg.norm(v);length=max(3,np.ptp(wr[:,1])*1.8);start=target+v*length
        ax.annotate('시선',xy=target+v*length*.35,xytext=start,fontsize=50,ha='center',arrowprops=dict(arrowstyle='->',color=INK,lw=4))
        ax.text(-.5,np.median(wr[:,1]),'가려진 벽',ha='right',va='center',color=PRIOR,fontsize=50);ax.text(np.median(rr[:,0]),rr[:,1].max()+.35,'지붕',ha='center',fontsize=50,color=GT)
        ax.set_xlim(min(rr[:,0].min()-2,-5),max(start[0]+2,rr[:,0].max()+1));ax.set_ylim(-1,max(start[1]+1,rr[:,1].max()+2));ax.axis('off')
        evidence=dict(source=m,projection_cross_axis=cross.tolist(),camera_xyz=cam.tolist(),wall_count=len(wall),roof_count=len(roof),geometry='Exact prior wall and roof points projected into a side view; camera arrow shortened, not a metric length',limitation='Same building roof; hidden wall currentness and successful inheritance are not established')
    if key!='inherit':
        for x,label,col in [(.02,'참값',GT),(.31,'사전 정보',PRIOR),(.78,'영상',MVS)]:fig.text(x,.98,label,color=col,fontsize=50,va='top')
    path=CACHE/f'e_{key}_comparison.png';fig.savefig(path,dpi=100,facecolor='white');plt.close(fig);return Image.open(path),evidence

def draw_e():
    cards=[];names=['keep','correct','refine','inherit'];titles=['보존','보정','다듬기','상속']
    compare=['같은 면을 옆에서 본 자료','옛 지붕과 현재 지붕의 단면','같은 지붕의 확대 단면','지붕과 벽을 옆에서 본 위치']
    foot=[['영상이 참값에서 벗어남','맞는 사전 정보를 보존'],['옛 지붕과 현재 지붕이 다름','현재 영상으로 보정'],['단순한 면과 실제 지붕의 차이','작은 차이를 다듬기'],['사진에서 보이지 않는 벽','사전 정보 상속이 필요한 곳']]
    for i,(key,title) in enumerate(zip(names,titles)):
        n='figS_e_aim_'+key;m=L.source(n);card=Image.new('RGB',(1080,1620),'white');L.text(card,(36,24),title,100,bold=True)
        photo=Image.open(DOC/'revision_02/figures'/f'{n}.png');card.paste(photo,(0,160))
        L.text(card,(28,790),compare[i],70,bold=True);plot,e=plot_card(key);card.paste(plot,(0,890))
        # At 400 px card width, 70 px source text remains 25.9 px.
        L.text(card,(28,1430),foot[i][0],70,bold=True);L.text(card,(28,1530),foot[i][1],70,col=PROP)
        save(n,card,dict(source=m,layout_source=load(DOC/'revision_02/figures'/f'{n}.json'),comparison=e,short_explanation=foot[i],minimum_font_px=50*100/72,slide_card_size=[400,600],not_a_result_claim=True))
        cards.append(card)
    combined=Image.new('RGB',(4320,1620),'white')
    for i,card in enumerate(cards):combined.paste(card,(i*1080,0))
    d=ImageDraw.Draw(combined)
    for x in [1080,2160,3240]:d.line((x,0,x,1620),fill='#CBD3D9',width=4)
    save('figS_e_purpose_overview',combined,dict(cards=[f'figS_e_aim_{k}' for k in names],minimum_font_px=50*100/72,slide_size=[1600,600],format_amendment='User explicitly selected photos plus comparison diagrams plus short explanations. Expanded cards supplement original text-free locators.'))

def draw_b():
    for n in ['figS_b_correction_sections','figS_b_all_methods']:
        shutil.copy2(DOC/'revision_02/figures'/f'{n}.png',FIG/f'{n}.png');m=load(DOC/'revision_02/figures'/f'{n}.json');m['task_id']='PHD-SLIDE-PHOTO-v1-R3';dump(FIG/f'{n}.json',m)

if __name__=='__main__':
    config();FIG.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True);globals()['draw_'+sys.argv[1]]();print('SEMANTIC',sys.argv[1],now(),flush=True)
