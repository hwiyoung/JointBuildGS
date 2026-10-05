"""Preserved input inspection; no inference, training, depth correction or alignment."""
import hashlib, json, os, sys, platform
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

TASK=Path('/task'); OUT=Path('/out'); REFS=Path('/references')
cfg=json.loads(Path('/out/config.json').read_text())
sources={}
def hashed(p):
    p=Path(p); h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    sources[str(p)]={'sha256':h.hexdigest(),'bytes':p.stat().st_size}
    return h.hexdigest()
def camera(region,name):
    base=TASK/'inputs'/region/'scene'/'train_sparse_txt'
    cams={}
    for line in (base/'cameras.txt').read_text().splitlines():
        t=line.split()
        if t and not t[0].startswith('#'):
            assert t[1]=='PINHOLE'; cams[t[0]]=(int(t[2]),int(t[3]),np.array(list(map(float,t[4:8]))))
    for line in (base/'images.txt').read_text().splitlines():
        t=line.split()
        if len(t)>=10 and Path(t[9]).stem==name:
            w,x,y,z=map(float,t[1:5]); tr=np.array(list(map(float,t[5:8])))
            R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
            W,H,intr=cams[t[8]]
            for f in ['cameras.txt','images.txt']:hashed(base/f)
            return W,H,intr,R,tr,t[9]
    raise ValueError('Missing camera '+region+'/'+name)
def load(region,name):
    c=camera(region,name); root=TASK/'inputs'/region
    receipt=json.loads((root/'da3/receipt.json').read_text());hashed(root/'da3/receipt.json')
    rec=next(r for r in receipt['images'] if Path(r['name']).stem==name)
    D=np.load(root/'da3/raw_depth'/f'{name}.npy')
    N=np.load(root/'da3/raw_depth_inference'/f'{name}.npy')
    P=np.load(root/'prior/raw_depth'/f'{name}.npy')
    for sub in ['raw_depth','raw_depth_inference']:
        key=f'{sub}/{name}.npy';assert hashed(root/'da3'/key)==rec['files'][key]['sha256']
    rgb=root/'scene/images'/c[-1];assert hashed(rgb)==rec['rgb_sha256']
    hashed(root/'prior/raw_depth'/f'{name}.npy')
    assert D.shape==P.shape==(c[1],c[0])
    return c,D,N,P,np.asarray(Image.open(rgb)),rec
def stats(x):
    x=np.asarray(x);x=x[np.isfinite(x)]
    return {'n':int(x.size),'median':float(np.median(x)),'mean_abs':float(np.mean(np.abs(x))),'q05':float(np.quantile(x,.05)),'q95':float(np.quantile(x,.95)),'p_abs_gt_1':float(np.mean(np.abs(x)>1))} if x.size else {'n':0}

plt.rcParams.update({'font.size':10,'axes.titlesize':11,'figure.facecolor':'white'})
summary={'schema':'DA3_VISUAL_REVIEW_v1','scientific_verdict':None,'status':'RUNNING','config':cfg,'cases':[],'same_image_pairs':[],'versions':{'python':platform.python_version(),'numpy':np.__version__,'matplotlib':matplotlib.__version__}}
refs={}
for case in cfg['cases']:
    rid,name=case['region'],case['name'];c,D,N,P,rgb,rec=load(rid,name)
    W,H,intr,R,tr,_=c;fx,fy,cx,cy=intr;B=cfg['block_px']
    if rid not in refs:
        rp=REFS/rid/'reference.npz';hashed(rp);refs[rid]=np.load(rp)['uas_xyz']
    pts=refs[rid];ny,nx=(H+B-1)//B,(W+B-1)//B;zb=np.full(ny*nx,np.inf)
    for start in range(0,len(pts),250000):
        X=pts[start:start+250000].astype(float)@R.T+tr;z=X[:,2]
        u=fx*X[:,0]/np.where(z!=0,z,1)+cx;v=fy*X[:,1]/np.where(z!=0,z,1)+cy
        m=(z>0)&(u>=0)&(u<W)&(v>=0)&(v<H)
        idx=(v[m]//B).astype(int)*nx+(u[m]//B).astype(int);np.minimum.at(zb,idx,z[m])
    zb=zb.reshape(ny,nx);vv,uu=np.indices(zb.shape);yy=np.minimum(vv*B+B//2,H-1);xx=np.minimum(uu*B+B//2,W-1)
    valid=np.isfinite(zb);da=D[yy,xx];pr=P[yy,xx]
    good=valid&np.isfinite(da)&(da>0);goodp=np.isfinite(pr)&(pr>0)&np.isfinite(da)&(da>0)
    row=int(np.argmax(valid.sum(axis=1)));py=int(yy[row,0]);pg=valid[row]
    vals=np.concatenate([P[(P>0)&np.isfinite(P)][::8],zb[valid]])
    lo,hi=np.quantile(vals,[.02,.98]);hi=max(hi,lo+1)
    cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#dfe3e6')
    fig,ax=plt.subplots(2,3,figsize=(15,9),constrained_layout=True)
    fig.suptitle(f"{rid} | batch {rec['batch_id']} | {name}\nPreserved inputs: shared camera-Z colour scale; no scale/shift correction",fontsize=14)
    ax[0,0].imshow(rgb);sample=np.flatnonzero(valid.ravel())[::max(1,int(valid.sum()/3500))]
    ax[0,0].scatter(xx.ravel()[sample],yy.ravel()[sample],s=.7,c='#ff37a6',alpha=.5)
    ax[0,0].axhline(py,color='white',lw=.8,ls='--');ax[0,0].set_title('Actual photo + regional UAS projection (pink)\nProjection does NOT certify visibility')
    for a,arr,title in [(ax[0,1],D,'DA3 input depth'),(ax[0,2],P,'ALS-derived prior depth (may be stale)')]:
        im=a.imshow(np.ma.masked_where(~np.isfinite(arr)|(arr<=0),arr),cmap=cmap,vmin=lo,vmax=hi,interpolation='nearest');a.set_title(title);a.axhline(py,color='white',lw=.8,ls='--');fig.colorbar(im,ax=a,shrink=.72,label='camera Z (m)',extend='both')
    im=ax[1,0].imshow(np.ma.masked_invalid(np.where(valid,zb,np.nan)),extent=[0,W,H,0],cmap=cmap,vmin=lo,vmax=hi,interpolation='nearest');ax[1,0].set_title('Regional UAS projected depth (evaluation only)\nGrey = no reference; outside occluders absent');fig.colorbar(im,ax=ax[1,0],shrink=.72,label='camera Z (m)',extend='both')
    ids=np.flatnonzero(good.ravel());show=ids[::max(1,len(ids)//10000)];ax[1,1].scatter(zb.ravel()[show],da.ravel()[show],s=2,alpha=.18,color='#d97706',rasterized=True)
    extent=np.quantile(np.r_[zb.ravel()[ids],da.ravel()[ids]],[.001,.999]);ax[1,1].plot(extent,extent,color='black',lw=1,ls='--');ax[1,1].set(xlabel='Regional UAS camera Z (m)',ylabel='DA3 camera Z (m)',title='Same projected cells; identity is dashed\nOccluded/outside-reference cases can disagree legitimately')
    ax[1,2].plot(np.arange(W),D[py],color='#d97706',lw=1,label='DA3');ax[1,2].plot(np.arange(W),np.where(P[py]>0,P[py],np.nan),color='#2876ae',lw=1,label='Prior')
    ax[1,2].scatter(xx[row,pg],zb[row,pg],s=3,c='black',label='Regional UAS')
    ax[1,2].set(xlabel='Image column (pixel)',ylabel='Camera Z (m)',title=f'Image row {py}; selected by UAS coverage\nFull values, no depth rescaling');ax[1,2].legend(fontsize=8)
    for a in [ax[0,0],ax[0,1],ax[0,2],ax[1,0]]:a.set_xlim(0,W);a.set_ylim(H,0);a.set_xlabel('Image column');a.set_ylabel('Image row')
    fig.savefig(OUT/(case['id']+'.png'),dpi=135);plt.close(fig)
    result={**case,'batch_actual':rec['batch_id'],'camera_direction_z':float(R[2,2]),'color_range_m':[float(lo),float(hi)],'reference_grid_cells':int(valid.sum()),'sample_row':py,'da3_minus_projected_uas':stats(da[good]-zb[good]),'da3_minus_prior':stats(da[goodp]-pr[goodp]),'native_depth_quantiles':np.quantile(N,[0,.1,.5,.9,1]).tolist(),'figure':case['id']+'.png','reference_visibility':'UNCERTIFIED_REGIONAL_OCCLUSION','source_receipt_status': 'HASH_VERIFIED'}
    summary['cases'].append(result);print(json.dumps(result),flush=True)

for pair in cfg['same_image_pairs']:
    a,b=[load(r,pair['name']) for r in pair['regions']]
    ca,da,na,pa,imga,ra=a;cb,db,nb,pb,imgb,rb=b
    assert np.array_equal(imga,imgb) and np.array_equal(ca[2],cb[2]) and np.array_equal(ca[3],cb[3]) and np.array_equal(ca[4],cb[4])
    assert na.shape==nb.shape
    diff=nb-na;lo,hi=np.quantile(np.r_[na.ravel(),nb.ravel()],[.02,.98])
    fig,ax=plt.subplots(1,4,figsize=(18,4.7),constrained_layout=True);fig.suptitle(pair['name']+' | identical RGB, input intrinsics and pose; different view batches',fontsize=13)
    ax[0].imshow(imga);ax[0].set_title('Same input photograph')
    for i,(n,r,rr) in enumerate([(na,pair['regions'][0],ra),(nb,pair['regions'][1],rb)],1):
        q=ax[i].imshow(n,cmap='viridis',vmin=lo,vmax=hi,interpolation='nearest');ax[i].set_title(f"{r} batch {rr['batch_id']} | DA3 camera Z");fig.colorbar(q,ax=ax[i],label='m',shrink=.8,extend='both')
    q=ax[3].imshow(diff,cmap='RdBu_r',vmin=-3,vmax=3,interpolation='nearest');ax[3].set_title(pair['regions'][1]+' minus '+pair['regions'][0]);fig.colorbar(q,ax=ax[3],label='m; clipped display at +/-3',shrink=.8,extend='both')
    for x in ax:x.axis('off')
    filename='same_photo_'+pair['name']+'.png';fig.savefig(OUT/filename,dpi=135);plt.close(fig)
    summary['same_image_pairs'].append({**pair,'figure':filename,'native_shape':list(na.shape),'absolute_difference':stats(np.abs(diff)),'identical_rgb_intrinsics_pose':True,'batches':[ra['batch_id'],rb['batch_id']]})
summary['status']='PASS_PRESERVED_INPUT_VISUALIZATION';summary['sources']=sources
summary['artifact_hashes']={p.name:hashed(p) for p in OUT.glob('*.png')}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':[{'cell_type':'markdown','metadata':{},'source':['# DA3 preserved-input inspection\n','Run the recorded Docker command in command.sh to regenerate. No training, inference or reference-based correction. Figures and definitions are in summary.json. Regional UAS visibility is uncertified.'],'id':'scope'},{'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':['import json\n','from pathlib import Path\n','from IPython.display import display, Image\n','s = json.loads(Path("summary.json").read_text())\n','for case in s["cases"] + s["same_image_pairs"]:\n','    display(Image(filename=case["figure"]))\n'],'id':'inspect'}]}
(OUT/'inspection.ipynb').write_text(json.dumps(nb,indent=2)+'\n')
