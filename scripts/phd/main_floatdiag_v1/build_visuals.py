"""Source-backed A1 plates, maps, orbit movies, and an entirely offline viewer."""
import argparse
import base64
import html
import json
import shutil
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
from matplotlib.collections import PolyCollection
from common import *
from recount import load_eval,classes

NAMES=dict(zip(RESULTS,['판정 끔','판 2','판 4']))
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':10})
WEB=DOC/'보기';IMG=WEB/'img';IMG.mkdir(parents=True,exist_ok=True)
FONT='/fonts/NotoSansCJK-Regular.ttc'

def save_figure(fig,key,meta,width=1800):
    path=DOC/'figures'/f'{key}.png';path.parent.mkdir(exist_ok=True)
    fig.savefig(path,dpi=300,bbox_inches='tight',facecolor='white');plt.close(fig)
    im=Image.open(path).convert('RGB');im.thumbnail((width,10000),Image.Resampling.LANCZOS)
    out=IMG/f'{key}.jpg';im.save(out,quality=90,optimize=True)
    assert out.stat().st_size<1500000
    save(path.with_suffix('.json'),dict(**meta,web_image=str(out.relative_to(WEB)),scientific_verdict=None))
    return str(out.relative_to(WEB))

def board(case,kind):
    fig,axs=plt.subplots(3,7,figsize=(21,9),squeeze=False)
    suffix='gaussian' if kind=='gaussian' else 'view'
    for i,result in enumerate(RESULTS):
        for j,cam in enumerate(case['cameras']):
            p=DOC/'3d'/case['id']/result/f'{suffix}_{j}.png'
            ax=axs[i,j];ax.imshow(Image.open(p));ax.set(xticks=[],yticks=[])
            if i==0:ax.set_title(f"{cam['azimuth_deg']}° / {cam['elevation_deg']}°")
            if j==0:ax.set_ylabel(NAMES[result],fontsize=12)
            for spine in ax.spines.values():spine.set_visible(False)
    fig.suptitle(case['id']+(' · 가우시안 색 렌더' if kind=='gaussian' else ' · 실제 결과 메시'),fontsize=18,x=.02,ha='left')
    caption='학습 사진이 없는 각도에서는 흐려 보일 수 있다.' if kind=='gaussian' else '빨강: 그 자리 참값보다 τ 넘게 위. 회색: τ 안. 연파랑: 그 밖. 연회색: 참값 또는 τ 없음.'
    fig.text(.02,.01,caption,fontsize=12)
    fig.subplots_adjust(top=.89,bottom=.07,left=.04,right=.99,wspace=.01,hspace=.04)
    return save_figure(fig,case['id']+'_'+kind,dict(case=case['id'],kind=kind,results=RESULTS,cameras=case['cameras'],caption=caption))

def orbit(case):
    frames=[];font=ImageFont.truetype(FONT,17)
    for i in range(36):
        canvas=Image.new('RGB',(1080,330),'white');draw=ImageDraw.Draw(canvas)
        for j,res in enumerate(RESULTS):
            im=Image.open(DOC/'3d'/case['id']/res/f'orbit_{i:02}.png').convert('RGB')
            canvas.paste(im,(j*360,30));draw.text((j*360+12,5),NAMES[res],font=font,fill='#222222')
        frames.append(canvas)
    dest=WEB/'video';dest.mkdir(exist_ok=True)
    gif=dest/(case['id']+'.gif')
    frames[0].save(gif,save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True)
    if gif.stat().st_size>=8000000:
        frames=[im.resize((810,248)).quantize(colors=64) for im in frames]
        frames[0].save(gif,save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True)
    assert gif.stat().st_size<8000000
    mp4=dest/(case['id']+'.mp4')
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        binaries=sorted((OUT/'tools/ffmpeg_runtime/imageio_ffmpeg/binaries').glob('ffmpeg-linux*'))
        assert len(binaries)==1,'pinned imageio-ffmpeg 0.6.0 runtime unavailable'
        ffmpeg=str(binaries[0])
    p=subprocess.Popen([ffmpeg,'-y','-loglevel','error','-f','rawvideo','-pixel_format','rgb24','-video_size','1080x330',
        '-framerate','10','-i','-','-an','-c:v','libx264','-crf','25','-pix_fmt','yuv420p',str(mp4)],stdin=subprocess.PIPE)
    for i in range(36):
        canvas=Image.new('RGB',(1080,330),'white');draw=ImageDraw.Draw(canvas)
        for j,res in enumerate(RESULTS):
            canvas.paste(Image.open(DOC/'3d'/case['id']/res/f'orbit_{i:02}.png').convert('RGB'),(j*360,30))
            draw.text((j*360+12,5),NAMES[res],font=font,fill='#222222')
        p.stdin.write(canvas.tobytes())
    p.stdin.close();assert p.wait()==0
    for media in [gif,mp4]:shutil.copyfile(media,DOC/'3d'/case['id']/media.name)
    save(DOC/'3d'/case['id']/'orbit.json',dict(case=case['id'],results=RESULTS,frames=36,
        azimuth_deg=list(range(0,360,10)),elevation_deg=20,frame_rate=10,
        renderer='full unreduced source mesh Open3D raycasting',encoder=ffmpeg,
        encoder_sha256=sha(ffmpeg),files=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in [mp4,gif]],scientific_verdict=None))
    return dict(mp4=str(mp4.relative_to(WEB)),gif=str(gif.relative_to(WEB)))

def case_values(case,e,result):
    p=LT/'patch_z'/f"{case['site']}__{PRIOR}__{result}.npz"
    with np.load(p) as f:z={k:f[k] for k in f.files}
    c=classes(e,z);xy=e['centre'][:,:2];b=case['bbox']
    # Case's diagnostic domain is its closed component plus the specified 3m
    # context crop; the original component membership is retained separately.
    m=e['in_eval']&e['scoring_allowed']&(e['cell']>=0)&(e['cell']<=3)&((xy>=np.array(b[:2])-3)&(xy<=np.array(b[2:])+3)).all(1)
    area=float(e['area'][m].sum());floating=m&(c==1)
    return dict(result=result,case=case['id'],patches=int(m.sum()),area_m2=area,
        within_tau_pct=100*float(e['area'][m&(c==0)].sum())/area if area else None,
        floating_area_m2=float(e['area'][floating].sum()),floating_pct=100*float(e['area'][floating].sum())/area if area else None,
        floating_height_median_m=float(np.median((z['z'][floating]-e['p_gt'][floating])*e['normal'][floating,2])) if floating.any() else None,
        no_surface_pct=100*float(e['area'][m&z['no_surface']].sum())/area if area else None,
        source=str(p),source_sha256=sha(p),domain='0..3 scoring patches inside component bbox + 3m',origin='[이 발주에서 냄]'),c

def photo_panel(ax,case,e,choice,types):
    if choice is None:
        ax.text(.5,.5,'확인 불가\n보이는 넓이 기준을 넘는 학습 사진 없음',ha='center',va='center',transform=ax.transAxes)
        ax.axis('off');return None
    root=OUT/'renders'/case['site']/f'nojudge_{PRIOR}_s0/iteration_30000'
    record=json.loads((root/'quality.json').read_text());cam=next(x for x in record['train'] if x['view']==choice['view'])
    ext=np.array(cam['world_to_camera']);K=np.array(cam['intrinsic']);xyz=e['centre'];b=np.array(case['bbox'])
    mask=e['in_eval']&e['scoring_allowed']&((xyz[:,:2]>=b[:2]-3)&(xyz[:,:2]<=b[2:]+3)).all(1)
    ids=np.flatnonzero(mask);pc=xyz[ids]@ext[:3,:3].T+ext[:3,3];q=pc@K.T;uv=q[:,:2]/q[:,2,None]
    valid=(pc[:,2]>0)&np.isfinite(uv).all(1)&(uv[:,0]>=0)&(uv[:,0]<cam['width'])&(uv[:,1]>=0)&(uv[:,1]<cam['height'])
    uv=uv[valid];ids=ids[valid]
    if not len(ids):ax.text(.5,.5,'확인 불가: 사례가 화면 밖',ha='center');return None
    lo=np.maximum(np.floor(uv.min(0)-20),[0,0]).astype(int);hi=np.minimum(np.ceil(uv.max(0)+20),[cam['width'],cam['height']]).astype(int)
    image=np.array(Image.open(OUT/'photos'/case['site']/(choice['view']+'.png')))
    ax.imshow(image[lo[1]:hi[1],lo[0]:hi[0]])
    corners=xyz[ids,None,:]+np.array([[-.125,-.125,0],[.125,-.125,0],[.125,.125,0],[-.125,.125,0]])
    pcorners=corners@ext[:3,:3].T+ext[:3,3];qcorners=pcorners@K.T
    polygons=qcorners[:,:,:2]/qcorners[:,:,2,None]-lo
    for typ,col,label in [(0,'#2e8b57','τ 안'),(1,'#d9534f','뜬 면')]:
        keep=types[ids]==typ
        ax.add_collection(PolyCollection(polygons[keep],facecolors='none' if typ==0 else col,
            edgecolors=col,linewidths=.35,alpha=.7 if typ==0 else .28,label=label))
    ax.set(xticks=[],yticks=[]);ax.set_title(f"(가) 실사 · 보이는 넓이 {choice['coverage']*100:.1f}%")
    return dict(view=choice['view'],crop_xyxy=[*lo.tolist(),*hi.tolist()],camera=cam,patches=len(ids),source=str(OUT/'photos'/case['site']/(choice['view']+'.png')))

def plate(case,e,unit_rows):
    vals=[];types=None
    for res in RESULTS:
        row,c=case_values(case,e,res);vals.append(row)
        if res==f'lt_dynnow_{PRIOR}_s0':types=c
    photos=json.loads((CFG/f"photos_{case['site']}_{PRIOR}.json").read_text());choice=next(x for x in photos['cases'] if x['case']==case['id'])
    fig=plt.figure(figsize=(15,11));gs=fig.add_gridspec(4,4,height_ratios=[2.3,2.3,1.8,1.8],width_ratios=[1.35,1,1,1])
    photo=photo_panel(fig.add_subplot(gs[:2,0]),case,e,choice['main'],types)
    oblique=photo_panel(fig.add_subplot(gs[2:,0]),case,e,choice['oblique'],types)
    for j,res in enumerate(RESULTS):
        for r,view in enumerate([4,5]):
            ax=fig.add_subplot(gs[r,j+1]);ax.imshow(Image.open(DOC/'3d'/case['id']/res/f'view_{view}_gt.png'))
            ax.set(xticks=[],yticks=[]);ax.set_title(f"{NAMES[res]} · {case['cameras'][view]['azimuth_deg']}°")
            for sp in ax.spines.values():sp.set_visible(False)
        ax=fig.add_subplot(gs[2:,j+1]);ax.axis('off');v=vals[j]
        unit=next(x for x in unit_rows if x['result']==res and x['cell']=='0~3')
        lines=[NAMES[res],f"사례 범위 {v['area_m2']:.1f} m²",f"τ 안 {v['within_tau_pct']:.2f}%",
            f"뜬 면 {v['floating_area_m2']:.1f} m²",f"뜬 면 {v['floating_pct']:.2f}%",'',
            f"단위 전체 {unit['area_m2']:.1f} m²",f"τ 안 {unit['within_tau_pct']:.2f}%",f"뜬 면 {unit['floating_pct']:.2f}%",f"뜬 면 {unit['floating_area_m2']:.1f} m²"]
        ax.text(.04,.98,'\n'.join(lines),va='top',fontsize=12,linespacing=1.45)
    fig.suptitle(case['id']+' · 같은 곳의 사진과 실제 결과 면을 비교한다',x=.02,ha='left',fontsize=18)
    fig.text(.02,.02,'(나) 낮은 두 각도: 실제 메시와 참값 점. (사) 숫자: 사례 경계 상자 + 3 m의 칸 0~3.\n메시 색은 수직 높이, 표는 바깥 법선을 따라 처음 만난 면으로 구분한다. 진단 값은 가-2에서 추가한다.',fontsize=10)
    fig.subplots_adjust(top=.9,bottom=.09,left=.02,right=.99,wspace=.08,hspace=.12)
    image=save_figure(fig,case['id']+'_plate_A1',dict(case=case['id'],phase='A1',values=vals,photo=photo,oblique=oblique,
        unavailable=choice['unavailable_reason'],visual_review='PENDING'))
    return image,vals

def map_site(site,e,cases):
    fig,axs=plt.subplots(1,3,figsize=(15,6));cmap=ListedColormap(config()['colours']['classes'])
    mask=e['in_eval']&e['scoring_allowed']&(e['cell']>=0)&(e['cell']<=3);xy=e['centre'][:,:2]
    for ax,res in zip(axs,RESULTS):
        with np.load(LT/'patch_z'/f'{site}__{PRIOR}__{res}.npz') as f:c=classes(e,{k:f[k] for k in f.files})
        ax.scatter(xy[mask,0],xy[mask,1],c=c[mask],cmap=cmap,vmin=0,vmax=4,s=2,marker='s',linewidths=0)
        ax.set(aspect='equal',xlabel='x (m)',title=NAMES[res]);ax.set_ylabel('y (m)')
        for i,case in enumerate(cases):
            b=case['bbox'];rect=plt.Rectangle(b[:2],b[2]-b[0],b[3]-b[1],fill=False,lw=1.,color='black');ax.add_patch(rect)
            ax.text(b[0],b[3],str(i+1),bbox=dict(facecolor='white',edgecolor='none',alpha=.9))
    fig.suptitle(site+' · 뜬 면과 사례 자리',fontsize=17,x=.03,ha='left')
    fig.text(.03,.01,'초록 τ 안 · 빨강 뜬 면 · 파랑 MVS 쪽 · 주황 사전 쪽 · 회색 그 밖·면 없음',fontsize=12)
    fig.tight_layout(rect=[0,.06,1,.93])
    return save_figure(fig,site+'_map_A1',dict(site=site,results=RESULTS,cases=[dict(number=i+1,id=c['id'],bbox=c['bbox']) for i,c in enumerate(cases)]))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',choices=SITES,required=True);ap.add_argument('--prior',default='ALS',choices=['ALS','LoD2']);a=ap.parse_args()
    cases=json.loads((CFG/f'geometry_{a.site}_{PRIOR}.json').read_text())['cases'];e,_=load_eval(a.site,PRIOR)
    rows=[x for x in json.loads((DOC/f'tables/recount_{PRIOR}.json').read_text())['rows'] if x['site']==a.site]
    output=[]
    for case in cases:
        captures={kind:board(case,kind) for kind in ['mesh','gaussian']};videos=orbit(case);image,vals=plate(case,e,rows)
        output.append(dict(id=case['id'],site=a.site,radius=case['radius'],translation=case['translation'],
            captures=captures,video=videos,plate=image,values=vals))
        print('visual case built',case['id'],flush=True)
    map_image=map_site(a.site,e,cases)
    save(WEB/f'data_{a.site}.json',dict(cases=output,map=map_image,unit_rows=[x for x in rows if x['result'] in RESULTS],scientific_verdict=None))

if __name__=='__main__':main()
