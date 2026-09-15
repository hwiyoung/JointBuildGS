"""Export concrete, independently scored development cases and current-image context."""
from pathlib import Path
import itertools
import gc
import time
import numpy as np
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
from analyze_final_surfaces import read,write,sha,mesh_arrays,distances
from build_failure_inspector import transform,crop

OUT=Path('/out');CFG=read(OUT/'config.json');ROOT=Path('/art')/CFG['attempt_relative'];U=ROOT/CFG['uas_folder'];ANA=ROOT/CFG['analysis'];RUN=read(ROOT/'config.json')
CASES=read(OUT/'chosen.json')['cases'];START=time.time()


def buffer(name,a,dtype):
    a=np.asarray(a,dtype=dtype);p=OUT/(name+'.bin');a.tofile(p)
    return dict(url=p.name,bytes=p.stat().st_size,shape=list(a.shape),dtype=dtype,sha256=sha(p))


def sections(xyz,tri,y):
    q=xyz[tri];dy=q[:,:,1]-y;keep=(dy.min(1)<0)&(dy.max(1)>0);q=q[keep];dy=dy[keep]
    points=np.full((len(q),3,3),np.nan)
    for k,(a,b) in enumerate([(0,1),(1,2),(2,0)]):
        good=dy[:,a]*dy[:,b]<0;t=dy[good,a]/(dy[good,a]-dy[good,b]);points[good,k]=q[good,a]+t[:,None]*(q[good,b]-q[good,a])
    valid=np.isfinite(points[:,:,0]);keep=valid.sum(1)==2
    return points[keep][valid[keep]].reshape(-1,2,3)


def depth_stats(a,z,x,y):
    values=np.asarray(a[y,x]);valid=np.isfinite(values)&(values>0);v=values[valid]-z[valid]
    return dict(n=len(x),valid=int(valid.sum()),median_signed_camera_z_m=float(np.median(v)) if len(v) else None,
        median_abs_camera_z_m=float(np.median(abs(v))) if len(v) else None,
        fraction_within_05m=float(np.mean(abs(v)<=.5)) if len(v) else None,
        fraction_in_front_over_1m=float(np.mean(v<-1)) if len(v) else None)


def photos(case,refs,inp):
    views=read(inp/'scene/split_manifest.json')['train'];center=refs.mean(0);possible=[]
    for v in views:
        R=np.array(v['R']);t=np.array(v['t']);cam=refs@R.T+t;q=cam@np.array(v['K']).T;uv=q[:,:2]/q[:,2,None]
        keep=(cam[:,2]>0)&(uv[:,0]>30)&(uv[:,0]<v['width']-30)&(uv[:,1]>30)&(uv[:,1]<v['height']-30)
        cc=-t@R;viewdir=(cc-center)/np.linalg.norm(cc-center)
        if keep.mean()<.9 or viewdir[2]<.5:continue
        score=v['K'][0][0]/np.median(cam[:,2])*viewdir[2]**2
        possible.append((score,v,uv,cam[:,2],cc))
    possible.sort(key=lambda x:-x[0]);possible=possible[:24]
    rows=[];chosen=[];da=ROOT/case['region']/('da3_inference_recovery_20260918T010840Z' if case['region']=='R2' else 'da3_inference')/'result'
    for score,v,uv,z,cc in possible:
        x=np.rint(uv[:,0]).astype(int);y=np.rint(uv[:,1]).astype(int);stem=Path(v['name']).stem
        stats={};hashes={}
        for name,folder in [('mvs',inp/'mvs_rgb/raw_depth'),('prior',inp/'prior/raw_depth'),('da3',da/'raw_depth_upsampled')]:
            p=folder/(stem+'.npy');a=np.load(p,mmap_mode='r');assert a.shape==(v['height'],v['width']),(p,a.shape)
            stats[name]=depth_stats(a,z,x,y);hashes[name]=sha(p)
        row=dict(name=v['name'],score=score,camera_center=cc.tolist(),projection_uv_min=uv.min(0).tolist(),projection_uv_max=uv.max(0).tolist(),depth_comparison=stats,depth_sha256=hashes)
        rows.append(row)
        # Prefer two spatially separated views; same selection rule for every candidate.
        if len(chosen)<2 and all(np.linalg.norm(cc-c[4])>=8 for c in chosen):chosen.append((score,v,uv,z,cc,row))
    if len(chosen)<2:chosen=[(*x,rows[i]) for i,x in enumerate(possible[:2])]
    canvas=Image.new('RGB',(1400,700*max(1,len(chosen))),'white');draw=ImageDraw.Draw(canvas)
    for i,(_,v,uv,_,_,row) in enumerate(chosen):
        im=Image.open(inp/'scene/images'/v['name']).convert('RGB');assert im.size==(v['width'],v['height']);assert sha(inp/'scene/images'/v['name'])==v['sha256']
        lo=uv.min(0);hi=uv.max(0);ctr=(lo+hi)/2
        full=im.copy();dd=ImageDraw.Draw(full);dd.rectangle([*lo,*hi],outline='red',width=4)
        full.thumbnail((900,650));canvas.paste(full,(0,i*700+35))
        half=max(120,float(np.max(hi-lo))*1.5);box=[max(0,int(ctr[0]-half)),max(0,int(ctr[1]-half)),min(im.width,int(ctr[0]+half)),min(im.height,int(ctr[1]+half))]
        detail=im.crop(box);ddd=ImageDraw.Draw(detail);ddd.rectangle([lo[0]-box[0],lo[1]-box[1],hi[0]-box[0],hi[1]-box[1]],outline='red',width=3);detail.thumbnail((480,650));canvas.paste(detail,(910,i*700+35))
        draw.text((10,i*700+8),case['id']+' / '+v['name']+' / projected reference patch (red)',fill='black')
        row['image_sha256']=v['sha256'];row['image_source']=str(inp/'scene/images'/v['name'])
    canvas.save(OUT/(case['id']+'_photos.jpg'),quality=92)
    report=dict(selected=[x[5]['name'] for x in chosen],views=rows,method='24 largest projected patch views with viewdir z>.5; first two camera centres at least8m apart; evaluation projection only. Depth differences may include occlusion, not automatically source error.')
    write(OUT/(case['id']+'_observations.json'),report);return report


def main():
    results=[]
    for r in CFG['regions']:
        cases=[c for c in CASES if c['region']==r]
        if not cases:continue
        ref=np.load(U/(r+'_reference.npz'))['xyz'];display=transform(ref);uvz=display.copy();uvz[:,1]*=-1
        frozen=np.load(U/(r+'_uas_distances.npz'));dp=np.load(U/(r+'_uas_to_prior.npy'))
        src=np.load(ANA/(r+'_paired_samples.npz'));input_mvs=transform(src['xyz'][src['source']==0])
        inp=Path('/art')/RUN['r1_prep_relative']/'result/input' if r=='R1' else ROOT/r/'preparation/input'
        for c in cases:
            low=np.array(c['uvz_min']);size=np.array(c['size']);c['_sel']=((uvz>=low)&(uvz<low+size)).all(1)
            assert int(c['_sel'].sum())==c['n'];center=low+size/2;center[1]*=-1
            c['_center']=center;c['_lo']=center-[10,8,8];c['_hi']=center+[10,8,8]
            use=((display>=c['_lo'])&(display<=c['_hi'])).all(1)
            im=((input_mvs>=c['_lo'])&(input_mvs<=c['_hi'])).all(1)
            c['_manifest']=dict(id=c['id'],case={k:v for k,v in c.items() if not k.startswith('_')},center=center.tolist(),
                display_box=[c['_lo'].tolist(),c['_hi'].tolist()],case_box=[[float(low[0]),float(-low[1]-size[1]),float(low[2])],[float(low[0]+size[0]),float(-low[1]),float(low[2]+size[2])]],
                uas=buffer(c['id']+'_uas',display[use],'<f4'),mvs_input=buffer(c['id']+'_input_mvs',input_mvs[im],'<f4'),models={},sections={},validation=[],scientific_verdict=None,role='EVALUATION_ONLY')
            c['_photos']=photos(c,ref[c['_sel']],inp);print('PHOTOS',c['id'],flush=True)
        info=read(U/(r+'_prior_reference.json'));models={'prior':info,**read(ANA/(r+'_summary.json'))['metadata']['models']}
        for b,info in models.items():
            path=Path(info['source'] if b=='prior' else info['path']);assert sha(path)==info['sha256']
            if b=='prior':a=np.load(path);xyz=transform(a['xyz']);faces=a['faces']
            else:v,f=mesh_arrays(path);xyz=transform(np.column_stack([v[k] for k in 'xyz']));faces=f['indices']
            for c in cases:
                x,t=crop(xyz,faces,c['_lo'],c['_hi']);m=c['_manifest'];d,_=distances(x.astype(np.float32),t,display[c['_sel']].astype(np.float32),10.)
                expected=dp[c['_sel']] if b=='prior' else frozen[b][c['_sel']]
                error=float(np.max(abs(d-expected)));assert error<.001,(c['id'],b,error)
                m['models'][b]=dict(xyz=buffer(c['id']+'_'+b+'_xyz',x,'<f4'),indices=buffer(c['id']+'_'+b+'_indices',t,'<u4'),vertices=len(x),triangles=len(t),median_m=float(np.median(expected)),source=info)
                seg=sections(x,t,c['_center'][1]);m['sections'][b]=buffer(c['id']+'_'+b+'_section',seg,'<f4')
                m['validation'].append(dict(branch=b,n=len(d),max_reference_distance_delta_m=error))
            del xyz,faces;gc.collect();print('EXPORTED',r,b,flush=True)
        for c in cases:
            m=c['_manifest'];write(OUT/(c['id']+'.json'),m)
            fig,axs=plt.subplots(1,2,figsize=(15,5),gridspec_kw={'width_ratios':[1,1.6]})
            rp=np.load(ANA/(r+'_paired_samples.npz'));cloud=transform(rp['xyz'][rp['source']==0]);axs[0].scatter(cloud[:,0],-cloud[:,1],s=.3,color='.6');axs[0].scatter(c['_center'][0],-c['_center'][1],color='red',s=60);axs[0].annotate(c['id']+' '+r+' '+c['zone'],(c['_center'][0],-c['_center'][1]),xytext=(8,8),textcoords='offset points');axs[0].invert_yaxis();axs[0].set_aspect('equal');axs[0].set_title('Exact site on region MVS plan');axs[0].set_xlabel('object u [m]');axs[0].set_ylabel('object v [m]')
            colors={'prior':'#139766','mvs':'#1976c4','local_prior0':'#a54fbd','da3':'#e78424'}
            for b,desc in m['sections'].items():
                a=np.fromfile(OUT/desc['url'],dtype='<f4').reshape(-1,2,3);axs[1].add_collection(LineCollection(a[:,:,[0,2]],colors=colors[b],linewidths=1.1,label=b))
            sel=(abs(display[:,1]-c['_center'][1])<=.25)&((display>=c['_lo'])&(display<=c['_hi'])).all(1)
            axs[1].scatter(display[sel,0],display[sel,2],c='black',s=5,label='UAS LiDAR',zorder=6)
            sel=(abs(input_mvs[:,1]-c['_center'][1])<=.5)&((input_mvs>=c['_lo'])&(input_mvs<=c['_hi'])).all(1)
            axs[1].scatter(input_mvs[sel,0],input_mvs[sel,2],c='#10aebc',s=24,marker='x',label='MVS input samples',zorder=7)
            axs[1].add_patch(Rectangle((c['uvz_min'][0],c['uvz_min'][2]),c['size'][0],c['size'][2],fill=False,color='red',lw=2));axs[1].set_xlim(c['_lo'][0],c['_hi'][0]);axs[1].set_ylim(c['_center'][2]-5,c['_center'][2]+5);axs[1].set_aspect('equal');axs[1].grid(alpha=.3);axs[1].legend(fontsize=8);axs[1].set_xlabel('object u [m]');axs[1].set_ylabel('local z [m]');axs[1].set_title('Native triangle section; no height exaggeration')
            fig.suptitle(c['id']+' / '+r+' '+c['zone']+' / same '+str(c['n'])+' UAS points: '+', '.join(b+' %.3fm'%m['models'][b]['median_m'] for b in ['prior','mvs','da3']))
            fig.tight_layout();fig.savefig(OUT/(c['id']+'_section.png'),dpi=135);plt.close(fig)
            results.append(dict(id=c['id'],case_file=c['id']+'.json',photo_file=c['id']+'_photos.jpg',section_file=c['id']+'_section.png',**{k:v for k,v in c.items() if not k.startswith('_') and k!='id'}))
            print('CASE',c['id'],flush=True)
    write(OUT/'sites.json',dict(status='PASS_NATIVE_GEOMETRY_AND_CURRENT_IMAGE_EXPORT',cases=results,scientific_verdict=None,elapsed_seconds=time.time()-START))


if __name__=='__main__':
    try:main()
    except Exception as e:write(OUT/'inspection_failure.json',dict(status='FAIL',error=repr(e),scientific_verdict=None));raise
