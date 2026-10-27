"""Supported roof replacement and exact section locator; no new method results."""
import shutil
from PIL import Image, ImageDraw, ImageOps
import layout_revision_02 as L
import semantic_revision_03 as S
import context_revision_04 as C
from common import *

OUT=DOC/'revision_06'; FIG=OUT/'figures'; CACHE=PAY/'revision_06'

def save(name,im,meta):
    im.save(FIG/f'{name}.png')
    dump(FIG/f'{name}.json',dict(task_id='PHD-SLIDE-PHOTO-v1-R6',scientific_verdict=None,**meta))

def thin_line(im,points,closed=False,dashed=False):
    q=[tuple(v) for v in points];q=q+[q[0]] if closed else q;d=ImageDraw.Draw(im)
    for a,b in zip(q[:-1],q[1:]):
        a,b=np.asarray(a),np.asarray(b);length=np.linalg.norm(b-a);v=(b-a)/max(length,1e-9)
        for start in np.arange(0,length,30) if dashed else [0]:
            end=min(start+18,length) if dashed else length
            points=[tuple(a+start*v),tuple(a+end*v)]
            d.line(points,fill='#243646',width=8);d.line(points,fill='#FFD60A',width=4)

def label(im,text,xy,size=68):
    lay=Image.new('RGBA',im.size);d=ImageDraw.Draw(lay);font=L.font(size);bb=d.textbbox(xy,text,font=font,anchor='lt')
    d.rounded_rectangle((bb[0]-10,bb[1]-8,bb[2]+10,bb[3]+8),radius=10,fill=(255,255,255,235))
    d.text(xy,text,font=font,fill=S.INK,anchor='lt');im.paste(Image.alpha_composite(im.convert('RGBA'),lay).convert('RGB'))

def roof_panel():
    r=load(OUT/'roof_photo_evidence.json');p=r['photo'];native=L.native(p);nw=native.width;native=native.transpose(Image.Transpose.ROTATE_90)
    raw=Image.open(CACHE/'roof_raw.png').transpose(Image.Transpose.ROTATE_90);marked=Image.open(CACHE/'roof_marked.png').transpose(Image.Transpose.ROTATE_90)
    with np.load(U/'patch_values'/f'{r["site"]}__LoD2__R1.5.npz') as z:X=z['centre'][r['patch_indices']]
    pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));uv,z=G.project(X,pose,p['camera']);inside=(z>0)&(uv[:,0]>=0)&(uv[:,0]<p['camera']['w'])&(uv[:,1]>=0)&(uv[:,1]<p['camera']['h'])
    # Visible input geometry sets the crop; missing/error colours do not set its bounds.
    q=np.c_[uv[inside,1]-p['crop_box_px'][1],p['crop_box_px'][2]-uv[inside,0]]
    lo=q.min(0);hi=q.max(0);mid=(lo+hi)/2
    detail=L.crop_rect(raw.size,mid,max((hi-lo)[0]*1.08,(hi-lo)[1]*2.326*1.08),2.326)
    offset=np.array([p['crop_box_px'][1],nw-p['crop_box_px'][2]]);box=np.array(detail)+np.tile(offset,2)
    context=L.crop_rect(native.size,(box[:2]+box[2:])/2,(box[2]-box[0])*1.25,2.326)
    return r,native,raw,marked,dict(source=r,display_rotation_deg=90,context_crop_in_rotated_native_px=context,detail_crop_in_original_crop_px=detail,detail_box_in_rotated_native_px=box,whole_roof_visible=False)

def draw_a():
    r4=load(DOC/'revision_04/figures/figS_a_image_limits.json');canvas=Image.new('RGB',(2700,1200),'white');records=[]
    for i,title in enumerate(['지붕의 깊이 결측','그늘진 벽','금속 면의 깊이 오류']):
        if i==0:r,native,raw,marked,rec=roof_panel()
        else:
            rec=r4['panels'][i];r=rec['source'];native=L.native(r['photo'])
            if r['photo'].get('display_rotation_deg',0)==90:native=native.transpose(Image.Transpose.ROTATE_90)
            raw=Image.open(L.CACHE/f'a_{i}_raw.png');marked=Image.open(L.CACHE/f'a_{i}_marked.png')
        x=16+i*906;W,H=856,368;context=rec['context_crop_in_rotated_native_px'];detail=rec['detail_crop_in_original_crop_px'];box=np.asarray(rec['detail_box_in_rotated_native_px'])
        top=native.crop(context).resize((W,H),Image.Resampling.LANCZOS)
        corners=np.array([[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]]);q=(corners-context[:2])*[W/(context[2]-context[0]),H/(context[3]-context[1])]
        thin_line(top,q,closed=True);canvas.paste(top,(x,100));L.text(canvas,(x,9),title,82,bold=True)
        ra,ma=np.asarray(raw),np.asarray(marked);changed=np.any(ra!=ma,axis=2);grey=np.asarray(ImageOps.grayscale(raw).convert('RGB')).copy();grey[changed]=ma[changed]
        bottom=Image.fromarray(grey).crop(detail).resize((W,H),Image.Resampling.LANCZOS);canvas.paste(bottom,(x,580))
        text=f'없음 {r["missing_share"]*100:.0f}% · 불일치 {r["wrong_share"]*100:.0f}%'
        assert L.font(74).getlength(text)<W,(text,L.font(74).getlength(text))
        L.text(canvas,(x,976),text,74);records.append(rec)
    L.text(canvas,(1350,493),'노란 테두리 = 아래 그림의 확대 범위',74,anchor='mt',col='#526373')
    for y,text in [(1045,'분홍: 깊이값 없음    빨강: 참값과 불일치'),(1120,'무색에는 미평가·참조 없음도 포함')]:
        assert L.font(74).getlength(text)<2670
        L.text(canvas,(1350,y),text,74,anchor='mt',col=S.INK if y==1045 else '#526373')
    save('figS_a_image_limits',canvas,dict(panels=records,minimum_font_px=74,roof_selection_replaced=True,other_two_selections_unchanged=True,
        crop_semantics='Yellow rectangle is the exact lower display crop, not a texture label, building boundary, or missing-depth mask',
        pink_semantics='Pink positions lack a valid depth value and have known reference support',uncoloured_semantics='Includes unevaluated and reference-unknown locations',
        roof_scope='Visible evaluated part of R1 face 23, not the whole building or a cause-of-texture experiment',reference='Aligned UAS LiDAR; not independent truth validation'))

def e_photo(key):
    m=load(DOC/'revision_04/figures'/f'figS_e_aim_{key}.json');p=m['photo']['source']['photo'];rot=m['photo']['display_rotation_deg'];crop=m['photo']['crop_in_rotated_native_px'];native,poly=C.transformed_photo(p,rot)
    meta=dict(m['photo']);meta['photo_fill']='none';meta['old_patch_hull_drawn']=key not in ['correct','inherit']
    pic=native.crop(crop).resize((1080,600),Image.Resampling.LANCZOS)
    if key=='correct':
        source=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples'][0]['photo'];assert source['stem']==p['view']
        pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));uv,_=G.project(np.asarray(source['line_xyz']),pose,p['camera'])
        if rot==90:uv=np.c_[uv[:,1],p['camera']['w']-uv[:,0]]
        q=(uv-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])]
        hidden=np.asarray(source['line_midpoint_occluded'])|~np.asarray(source['line_midpoint_known'])
        # Retain the exact sampled section. Occluded or unsupported segments are dotted.
        d=ImageDraw.Draw(pic)
        for j,(a,b) in enumerate(zip(q[:-1],q[1:])):
            if hidden[j] and j%4>=2:continue
            d.line([tuple(a),tuple(b)],fill='#243646',width=9);d.line([tuple(a),tuple(b)],fill='#FFD60A',width=5)
        for pt,text in [(q[0],'A'),(q[-1],'A′')]:
            d.ellipse((pt[0]-9,pt[1]-9,pt[0]+9,pt[1]+9),fill='#FFD60A',outline=S.INK,width=3)
            xy=np.clip(pt+[14,-64],[20,16],[985,510]);label(pic,text,tuple(xy))
        label(pic,'A–A′: 아래 단면의 위치',(26,510),68)
        meta.update(annotation='Exact A–A prime section locator; not a building boundary',old_patch_hull_drawn=False,section_line_xyz=source['line_xyz'],section_line_display_px=q.tolist(),section_hidden_segments=hidden.tolist(),section_source='main_regionfig_v1/tables/영역예시_보정_숫자.json examples[0].photo')
    else:
        if key=='inherit':
            pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));line,_=G.project(np.asarray(m['photo']['source']['line_xyz']),pose,p['camera']);poly=np.c_[line[:,1],p['camera']['w']-line[:,0]]
        q=(poly-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])];thin_line(pic,q,closed=key!='inherit',dashed=key=='inherit')
        labels={'keep':'금속으로 보이는 면','refine':'선택한 지붕 면','inherit':'가려진 벽의 위치'};label(pic,labels[key],(26,24));target=np.clip(q.mean(0),[20,20],[1060,580]);S.arrow(pic,(240,110),target,S.INK,4)
    return pic,meta,m

def draw_e():
    keys=['keep','correct','refine','inherit'];titles=['보존','보정','다듬기','상속'];subtitles=['참값과의 차이 · 중앙값(cm)','A–A′의 옛 지붕과 현재 지붕','같은 지붕의 단면 · 높이 확대','지붕과 벽의 위치 · 옆에서'];cards=[]
    for i,key in enumerate(keys):
        im=Image.new('RGB',(1080,1620),'white');ImageDraw.Draw(im).line((28,3,1052,3),fill=S.INK,width=7);L.text(im,(28,28),titles[i],94,bold=True)
        pic,pm,source=e_photo(key);im.paste(pic,(0,160));L.text(im,(28,790),subtitles[i],68)
        path=C.CACHE/'keep_comparison.png' if key=='keep' else S.CACHE/f'e_{key}_comparison.png';im.paste(Image.open(path),(0,890))
        explanation=['깊이값이 있어도 틀리면','맞는 사전 정보를 지킨다'] if key=='keep' else source['explanation']
        L.text(im,(28,1430),explanation[0],70);L.text(im,(28,1530),explanation[1],70,col=S.PROP)
        save('figS_e_aim_'+key,im,dict(photo=pm,comparison=source['comparison'],comparison_raster_sha256=sha(path),explanation=explanation,minimum_font_px=68,slide_card_size=[400,600],purpose_not_success_claim=True,source_revision_04=key));cards.append(im)
    combined=Image.new('RGB',(4320,1620),'white')
    for i,im in enumerate(cards):combined.paste(im,(1080*i,0))
    for x in [1080,2160,3240]:ImageDraw.Draw(combined).line((x,0,x,1620),fill='#DFE5EA',width=2)
    save('figS_e_purpose_overview',combined,dict(cards=keys,minimum_font_px=68,slide_size=[1600,600]))

def retain():
    for n in ['figS_d_gs_real','figS_b_correction_sections','figS_b_all_methods']:
        shutil.copy2(DOC/'revision_04/figures'/f'{n}.png',FIG/f'{n}.png');m=load(DOC/'revision_04/figures'/f'{n}.json');m['task_id']='PHD-SLIDE-PHOTO-v1-R6';dump(FIG/f'{n}.json',m)

if __name__=='__main__':
    config();FIG.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    {'a':draw_a,'e':draw_e,'retain':retain}[sys.argv[1]]();print('R6',sys.argv[1],now(),flush=True)
