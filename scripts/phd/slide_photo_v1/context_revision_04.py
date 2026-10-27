"""Zoom out for recognition; annotate actual locations and preserve frozen data."""
import shutil
from PIL import Image, ImageDraw, ImageOps
import layout_revision_02 as L
import semantic_revision_03 as S
from common import *

OUT=DOC/'revision_04';FIG=OUT/'figures';CACHE=PAY/'revision_04'

def save(n,im,meta):
    im.save(FIG/f'{n}.png');dump(FIG/f'{n}.json',dict(task_id='PHD-SLIDE-PHOTO-v1-R4',scientific_verdict=None,selection_unchanged=True,measurements_unchanged=True,**meta))

def outline(im,points,close=True,dashed=False):
    d=ImageDraw.Draw(im);q=[tuple(p) for p in points];q=q+[q[0]] if close else q
    if dashed:
        for a,b in zip(q[:-1],q[1:]):
            a=np.array(a);b=np.array(b);length=np.linalg.norm(b-a)
            for s in np.arange(0,length,36):
                v=(b-a)/length;p0=a+v*s;p1=a+v*min(s+22,length);d.line([tuple(p0),tuple(p1)],fill='black',width=11);d.line([tuple(p0),tuple(p1)],fill='#FFD60A',width=6)
    else:d.line(q,fill='black',width=11,joint='curve');d.line(q,fill='#FFD60A',width=6,joint='curve')

def annotation(im,label,origin,target,n=70):
    # Keep a white label box and a leader; never fill the selected photo surface.
    S.arrow(im,(origin[0]+min(240,len(label)*n/2),origin[1]+n+12),target,width=7)
    S.chip(im,origin,label,n)

def transformed_photo(p,rotation):
    im=L.native(p);poly=np.asarray(p['polygon_px'])+p['crop_box_px'][:2]
    if rotation==90:poly=np.c_[poly[:,1],im.width-poly[:,0]];im=im.transpose(Image.Transpose.ROTATE_90)
    return im,poly

def e_photo(key):
    n='figS_e_aim_'+key;m=L.source(n);p=m['photo'];rotation=90 if key in ['keep','correct','inherit'] else 0
    im,poly=transformed_photo(p,rotation);span=np.ptp(poly,axis=0);centre=(poly.min(0)+poly.max(0))/2
    if key=='keep':width=max(span[0]*1.35,3000)
    elif key=='correct':width=max(span[0],span[1]*1.8)*1.70
    elif key=='refine':width=max(span[0],span[1]*1.8)*2.7
    else:
        pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));line,_=G.project(np.asarray(m['line_xyz']),pose,p['camera']);poly=np.c_[line[:,1],p['camera']['w']-line[:,0]]
        centre=(poly.min(0)+poly.max(0))/2;centre[1]-=np.ptp(poly[:,0])*.14;width=np.ptp(poly[:,0])*1.20
    crop=L.crop_rect(im.size,centre,width,1.8);pic=im.crop(crop).resize((1080,600),Image.Resampling.LANCZOS);q=(poly-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])]
    outline(pic,q,close=key!='inherit',dashed=key=='inherit')
    target=q.mean(0);target=np.clip(target,[20,20],[1060,580])
    labels={'keep':'금속으로 보이는 면','correct':'현재의 날개 지붕','refine':'이 지붕 면의 차이를 확인','inherit':'지붕 아래 가려진 벽'}
    origin=(20,20) if key!='correct' else (20,480)
    if key=='correct':
        # From a bottom label, lead upward to the same frozen correction area.
        S.arrow(pic,(360,470),target,width=7);S.chip(pic,origin,labels[key],70)
    else:annotation(pic,labels[key],origin,target,70)
    return pic,dict(source=m,display_rotation_deg=rotation,crop_in_rotated_native_px=crop,annotation=labels[key],annotation_target_px=target,photo_fill='none',hidden_wall_line='dashed' if key=='inherit' else None)

def keep_plot():
    plt=plot_setup(50);m=L.source('figS_c_specular');row=load(DOC/'figures/task0_specular_candidates.json')['selected'];values=[m['reference_prior_abs_median_m']*100,m['reference_mvs_abs_median_m']*100]
    fig=plt.figure(figsize=(10.8,5.2),dpi=100);ax=fig.add_axes([.30,.18,.66,.75]);ax.axvspan(0,row['tau_m']*100,color='#EEF1F4',zorder=0);ax.axvline(row['tau_m']*100,color=S.GT,ls='--',lw=2)
    ax.barh([1,0],values,color=[S.PRIOR,S.MVS],height=.27);ax.set_yticks([1,0],['사전 정보','영상 깊이'],fontsize=50);ax.set_xlim(0,48);ax.set_ylim(-.6,1.8);ax.set_xticks([0,20,40]);ax.tick_params(axis='x',labelsize=50);ax.tick_params(axis='y',length=0);ax.spines['left'].set_visible(False)
    for y,v,col in zip([1,0],values,[S.PRIOR,S.MVS]):ax.text(v+.8,y,f'{v:.0f}',va='center',fontsize=50,color=col)
    ax.text(20,1.64,'허용 20',ha='center',va='center',fontsize=50,color=S.GT)
    f=CACHE/'keep_comparison.png';fig.savefig(f,dpi=100,facecolor='white');plt.close(fig)
    return Image.open(f),dict(source='figS_c_specular.json and task0_specular_candidates.json selected',absolute_residual_median_cm=values,tau_cm=row['tau_m']*100,aggregation='Frozen entire-component median absolute normal residual; not a fabricated section profile')

def draw_e():
    cards=[];titles=['보존','보정','다듬기','상속'];keys=['keep','correct','refine','inherit']
    subtitles=['참값과의 차이 · 중앙값(cm)','옛 지붕과 현재 지붕의 단면','같은 지붕의 단면 · 높이 확대','지붕과 벽의 위치 · 옆에서']
    lines=[['영상이 틀린 곳에서는','맞는 사전 정보를 지킨다'],['옛 지붕이 달라진 곳은','현재 영상을 따라 고친다'],['단순하게 표현된 지붕은','영상의 세부로 다듬는다'],['영상이 보지 못한 곳은','사전 정보로 메운다']]
    for i,key in enumerate(keys):
        card=Image.new('RGB',(1080,1620),'white');L.text(card,(36,24),titles[i],100,bold=True);pic,pmeta=e_photo(key);card.paste(pic,(0,160))
        L.text(card,(28,790),subtitles[i],70,bold=True)
        plot,evidence=keep_plot() if key=='keep' else S.plot_card(key);card.paste(plot,(0,890))
        L.text(card,(28,1430),lines[i][0],70,bold=True);L.text(card,(28,1530),lines[i][1],70,col=S.PROP)
        save('figS_e_aim_'+key,card,dict(photo=pmeta,comparison=evidence,explanation=lines[i],minimum_font_px=50*100/72,slide_card_size=[400,600],purpose_not_success_claim=True));cards.append(card)
    im=Image.new('RGB',(4320,1620),'white')
    for i,card in enumerate(cards):im.paste(card,(1080*i,0))
    d=ImageDraw.Draw(im)
    for x in [1080,2160,3240]:d.line((x,0,x,1620),fill='#CBD3D9',width=4)
    save('figS_e_purpose_overview',im,dict(cards=keys,minimum_font_px=50*100/72,slide_size=[1600,600]))

def draw_a():
    old=L.source('figS_a_image_limits');r2=load(DOC/'revision_02/figures/figS_a_image_limits.json');im=Image.new('RGB',(2700,1200),'white');records=[]
    for i,(r,title,label) in enumerate(zip(old['panels'],['무늬 없는 지붕','그늘진 벽','금속 면'],['지붕의 평가 구간','그늘에 있는 벽','금속으로 보이는 면'])):
        W,H=884,380;x=i*908;p=r['photo'];native=L.native(p);rotation=p.get('display_rotation_deg',0);orig=p['crop_box_px'];ra=np.asarray(Image.open(L.CACHE/f'a_{i}_raw.png'));ma=np.asarray(Image.open(L.CACHE/f'a_{i}_marked.png'));changed=np.any(ra!=ma,axis=2)
        prior_crop=r2['panels'][i]['display_crop_in_rotated_source_crop_px'];centre=(np.array(prior_crop[:2])+prior_crop[2:])/2;detail=L.crop_rect((ra.shape[1],ra.shape[0]),centre,max(prior_crop[2]-prior_crop[0],(prior_crop[3]-prior_crop[1])*W/H),W/H)
        # Map the old exact-source crop to the full native photograph, including rotation.
        if rotation==90:
            offset=np.array([orig[1],native.width-orig[2]]);native=native.transpose(Image.Transpose.ROTATE_90)
        else:offset=np.array(orig[:2])
        box_native=np.array(detail)+np.tile(offset,2);mid=(box_native[:2]+box_native[2:])/2
        width=max((orig[3]-orig[1] if rotation==90 else orig[2]-orig[0])*2.15,1400)
        context=L.crop_rect(native.size,mid,width,W/H);top=native.crop(context).resize((W,H),Image.Resampling.LANCZOS)
        corners=np.array([[box_native[0],box_native[1]],[box_native[2],box_native[1]],[box_native[2],box_native[3]],[box_native[0],box_native[3]]]);q=(corners-context[:2])*[W/(context[2]-context[0]),H/(context[3]-context[1])];outline(top,q)
        target=np.clip(q.mean(0),[20,20],[W-20,H-20]);annotation(top,label,(14,14),target,74);im.paste(top,(x,100))
        L.text(im,(x+W/2,4),title,80,bold=True,anchor='mt');L.text(im,(x+W/2,505),'표시한 부분의 깊이',74,bold=True,anchor='mt')
        grey=np.asarray(ImageOps.grayscale(Image.fromarray(ra)).convert('RGB')).copy();grey[changed]=ma[changed];bottom=Image.fromarray(grey).crop(detail).resize((W,H),Image.Resampling.LANCZOS)
        overlay=(ma.astype(float)-.48*ra)/.52;col=np.array([211,42,168] if i<2 else [217,54,54]);kind=changed&(np.linalg.norm(overlay-col,axis=2)<5);cc=kind[detail[1]:detail[3],detail[0]:detail[2]];yy,xx=np.nonzero(cc);j=np.argmin((xx-np.median(xx))**2+(yy-np.median(yy))**2);pt=np.array([xx[j]*W/cc.shape[1],yy[j]*H/cc.shape[0]])
        c=S.MISSING if i<2 else S.WRONG;S.arrow(bottom,(260,310),pt,c,8);S.chip(bottom,(14,300),'깊이 없음' if i<2 else '깊이 틀림',74,c);im.paste(bottom,(x,600))
        L.text(im,(x+W/2,1000),f'없음 {r["missing_share"]*100:.0f}% · 틀림 {r["wrong_share"]*100:.0f}%',74,bold=True,anchor='mt')
        if i==0:L.text(im,(x+W/2,1090),'평가 20화소 · 칠 4화소',74,anchor='mt')
        records.append(dict(source=r,context_crop_in_rotated_native_px=context,detail_crop_in_original_crop_px=detail,detail_box_in_rotated_native_px=box_native,annotation=label))
    L.text(im,(2675,1110),'자홍: 깊이 없음   빨강: 참값과 불일치',74,anchor='rt')
    save('figS_a_image_limits',im,dict(panels=records,minimum_font_px=74,display='Context photo above; yellow box is exactly the displayed detail crop below. Masks and counts unchanged.'))

def retained():
    for n in ['figS_d_gs_real','figS_b_correction_sections','figS_b_all_methods']:
        shutil.copy2(DOC/'revision_03/figures'/f'{n}.png',FIG/f'{n}.png');m=load(DOC/'revision_03/figures'/f'{n}.json');m['task_id']='PHD-SLIDE-PHOTO-v1-R4';m['retained_from_revision_03']=True;dump(FIG/f'{n}.json',m)

if __name__=='__main__':
    config();FIG.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True);{'a':draw_a,'e':draw_e,'retain':retained}[sys.argv[1]]();print('CONTEXT',sys.argv[1],now(),flush=True)
