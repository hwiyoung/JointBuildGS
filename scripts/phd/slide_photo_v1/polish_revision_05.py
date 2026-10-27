"""Reduce visual weight and distinguish display crops from depth classifications."""
import shutil
from PIL import Image,ImageDraw,ImageOps
import layout_revision_02 as L
import semantic_revision_03 as S
import context_revision_04 as C
from common import *

OUT=DOC/'revision_05';FIG=OUT/'figures'

def save(n,im,meta):
    im.save(FIG/f'{n}.png');dump(FIG/f'{n}.json',dict(task_id='PHD-SLIDE-PHOTO-v1-R5',scientific_verdict=None,selection_unchanged=True,measurements_unchanged=True,**meta))

def thin_outline(im,points,closed=True,dashed=False):
    d=ImageDraw.Draw(im);q=[tuple(v) for v in points];q=q+[q[0]] if closed else q
    for a,b in zip(q[:-1],q[1:]):
        a=np.asarray(a);b=np.asarray(b);length=np.linalg.norm(b-a);v=(b-a)/max(length,1)
        intervals=np.arange(0,length,30) if dashed else [0]
        for start in intervals:
            end=min(start+18,length) if dashed else length;p0=tuple(a+start*v);p1=tuple(a+end*v)
            d.line([p0,p1],fill='#243646',width=7);d.line([p0,p1],fill='#FFD60A',width=3)

def light_label(im,label,origin,target,up=False):
    layer=Image.new('RGBA',im.size);d=ImageDraw.Draw(layer);font=L.font(68);bb=d.textbbox(origin,label,font=font,anchor='lt')
    d.rounded_rectangle((bb[0]-12,bb[1]-8,bb[2]+12,bb[3]+8),radius=13,fill=(255,255,255,235))
    d.text(origin,label,font=font,fill=S.INK,anchor='lt');im.paste(Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB'))
    start=(origin[0]+min(220,(bb[2]-bb[0])/2),origin[1]-18 if up else bb[3]+20);S.arrow(im,start,target,S.INK,4)

def draw_a():
    r4=load(DOC/'revision_04/figures/figS_a_image_limits.json');im=Image.new('RGB',(2700,1200),'white');records=[]
    for i,(rec,title) in enumerate(zip(r4['panels'],['지붕의 평가 구간','그늘진 벽','금속 면'])):
        r=rec['source'];p=r['photo'];x=16+i*906;W,H=856,368;native=L.native(p)
        if p.get('display_rotation_deg',0)==90:native=native.transpose(Image.Transpose.ROTATE_90)
        context=rec['context_crop_in_rotated_native_px'];detail=rec['detail_crop_in_original_crop_px'];box=np.asarray(rec['detail_box_in_rotated_native_px'])
        top=native.crop(context).resize((W,H),Image.Resampling.LANCZOS);corners=np.array([[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]]);q=(corners-context[:2])*[W/(context[2]-context[0]),H/(context[3]-context[1])];thin_outline(top,q);im.paste(top,(x,100))
        L.text(im,(x,9),title,82,bold=True)
        raw=np.asarray(Image.open(L.CACHE/f'a_{i}_raw.png'));marked=np.asarray(Image.open(L.CACHE/f'a_{i}_marked.png'));changed=np.any(raw!=marked,axis=2);grey=np.asarray(ImageOps.grayscale(Image.fromarray(raw)).convert('RGB')).copy();grey[changed]=marked[changed]
        bottom=Image.fromarray(grey).crop(detail).resize((W,H),Image.Resampling.LANCZOS)
        overlay=(marked.astype(float)-.48*raw)/.52;colour=np.array([211,42,168] if i<2 else [217,54,54]);kind=changed&(np.linalg.norm(overlay-colour,axis=2)<5);cc=kind[detail[1]:detail[3],detail[0]:detail[2]];yy,xx=np.nonzero(cc);j=np.argmin((xx-np.median(xx))**2+(yy-np.median(yy))**2);pt=[xx[j]*W/cc.shape[1],yy[j]*H/cc.shape[0]]
        # A slender leader identifies an actually classified pixel; no new fill.
        S.arrow(bottom,(max(25,pt[0]-105),min(H-20,pt[1]+105)),pt,S.MISSING if i<2 else S.WRONG,4);im.paste(bottom,(x,580))
        label='결측 20/20 · 표시 4' if i==0 else f'결측 {r["missing_share"]*100:.0f}% · 불일치 {r["wrong_share"]*100:.0f}%'
        L.text(im,(x,984),label,74)
        records.append(dict(rec))
    L.text(im,(1350,493),'노란 테두리 = 아래 그림의 확대 범위',74,anchor='mt',col='#526373')
    legend='분홍: 깊이값 없음  ·  빨강: 참값과 다름  ·  무색: 미평가·참조 없음 포함'
    assert L.font(74).getlength(legend)<2670,L.font(74).getlength(legend)
    L.text(im,(1350,1110),legend,74,anchor='mt')
    save('figS_a_image_limits',im,dict(panels=records,minimum_font_px=74,crop_semantics='Yellow rectangle is the exact lower image crop, not a texture label or a missing-depth mask',pink_semantics='Pink marks positions with missing depth values and known GT support',uncoloured_semantics='May be normal, unevaluated, or unknown GT; uncoloured does not mean correct',roof_title='Neutral site label; texture is not a quantitative condition established by this 20-pixel sample',source_revision='revision_04'))

def e_photo(key):
    m=load(DOC/'revision_04/figures'/f'figS_e_aim_{key}.json');p=m['photo']['source']['photo'];rot=m['photo']['display_rotation_deg'];crop=m['photo']['crop_in_rotated_native_px'];native,poly=C.transformed_photo(p,rot)
    if key=='inherit':
        pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));line,_=G.project(np.asarray(m['photo']['source']['line_xyz']),pose,p['camera']);poly=np.c_[line[:,1],p['camera']['w']-line[:,0]]
    pic=native.crop(crop).resize((1080,600),Image.Resampling.LANCZOS);q=(poly-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])];thin_outline(pic,q,closed=key!='inherit',dashed=key=='inherit')
    labels={'keep':'금속으로 보이는 면','correct':'현재 날개 지붕','refine':'선택한 지붕 면','inherit':'가려진 벽의 위치'}
    origin=(26,486) if key=='correct' else (26,24);target=np.clip(q.mean(0),[20,20],[1060,580]);light_label(pic,labels[key],origin,target,up=key=='correct')
    return pic,m

def draw_e():
    keys=['keep','correct','refine','inherit'];titles=['보존','보정','다듬기','상속'];subtitles=['참값과의 차이 · 중앙값(cm)','옛 지붕과 현재 지붕의 단면','같은 지붕의 단면 · 높이 확대','지붕과 벽의 위치 · 옆에서'];cards=[]
    for i,key in enumerate(keys):
        im=Image.new('RGB',(1080,1620),'white');ImageDraw.Draw(im).line((28,3,1052,3),fill=S.INK,width=7);L.text(im,(28,28),titles[i],94,bold=True);pic,source=e_photo(key);im.paste(pic,(0,160));L.text(im,(28,790),subtitles[i],68)
        comparison=(C.CACHE/'keep_comparison.png') if key=='keep' else (S.CACHE/f'e_{key}_comparison.png');im.paste(Image.open(comparison),(0,890))
        L.text(im,(28,1430),source['explanation'][0],70);L.text(im,(28,1530),source['explanation'][1],70,col=S.PROP)
        save('figS_e_aim_'+key,im,dict(source_revision_04=source,minimum_font_px=68,slide_card_size=[400,600],style='Lighter annotation, thinner outline, regular-weight explanatory text; source crop and comparison raster unchanged'));cards.append(im)
    combined=Image.new('RGB',(4320,1620),'white')
    for i,im in enumerate(cards):combined.paste(im,(1080*i,0))
    for x in [1080,2160,3240]:ImageDraw.Draw(combined).line((x,0,x,1620),fill='#DFE5EA',width=2)
    save('figS_e_purpose_overview',combined,dict(cards=keys,minimum_font_px=68,slide_size=[1600,600]))

def retain():
    for n in ['figS_d_gs_real','figS_b_correction_sections','figS_b_all_methods']:
        shutil.copy2(DOC/'revision_04/figures'/f'{n}.png',FIG/f'{n}.png');m=load(DOC/'revision_04/figures'/f'{n}.json');m['task_id']='PHD-SLIDE-PHOTO-v1-R5';dump(FIG/f'{n}.json',m)

if __name__=='__main__':
    config();FIG.mkdir(parents=True,exist_ok=True);{'a':draw_a,'e':draw_e,'retain':retain}[sys.argv[1]]();print('POLISH',sys.argv[1],now(),flush=True)
