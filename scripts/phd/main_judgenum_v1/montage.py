"""Original training photographs of wrong components; geometric projection only, no new photo scoring."""
import hashlib
import io
import json
import struct
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
from shapely.ops import unary_union
from analysis_core import components
from figures import data,export,setup,O,C,D
from analyse import save,clean
from lock_config import sha,dump,stamp

ROOT=Path('/art/phase-payloads/p0-audit/data')

def poses(path):
    out={}
    with path.open('rb') as f:
        count,=struct.unpack('<Q',f.read(8))
        for _ in range(count):
            iid,=struct.unpack('<i',f.read(4));q=struct.unpack('<4d',f.read(32));t=struct.unpack('<3d',f.read(24));cid,=struct.unpack('<i',f.read(4));name=bytearray()
            while True:
                c=f.read(1)
                if not c:raise ValueError('Truncated COLMAP name')
                if c==b'\0':break
                name.extend(c)
            n,=struct.unpack('<Q',f.read(8));f.seek(24*n,1)
            out[name.decode()]={'q':q,'t':t,'camera_id':cid}
    return out

def rotation(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
       [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
       [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])

class Cameras:
    def __init__(self,W):
        path=ROOT/'work/mvs/colmap_input_db_ids/cameras.txt'
        lines=[x.split() for x in path.read_text().splitlines() if x and not x.startswith('#')]
        assert len(lines)==1 and lines[0][1]=='FULL_OPENCV'
        self.w,self.h=map(int,lines[0][2:4]);self.p=np.array(lines[0][4:],float)
        posepath=ROOT/'work/mvs/colmap_dense/sparse/images.bin';pp=poses(posepath)
        self.names=sorted(json.loads((W/'image_split.json').read_text())['train'])
        inv={r['name']:r for r in json.loads((W/'inputs/image_inventory.json').read_text())['rows']}
        self.members=[inv[n]['original_zip_member'] for n in self.names]
        self.R=np.array([rotation(pp[n]['q']) for n in self.names]);self.t=np.array([pp[n]['t'] for n in self.names])
        self.centres=-np.einsum('nij,ni->nj',self.R,self.t)
        self.archive=zipfile.ZipFile(ROOT/'raw/uav/Images.zip')
        self.source={'calibration':str(path),'calibration_sha256':sha(path),'poses':str(posepath),'poses_sha256':sha(posepath),
          'train_split_sha256':sha(W/'image_split.json'),'image_inventory_sha256':sha(W/'inputs/image_inventory.json')}
    def project(self,X,j):
        Q=X@self.R[j].T+self.t[j];z=Q[...,2]
        with np.errstate(over='ignore',divide='ignore',invalid='ignore'):
            x=Q[...,0]/z;y=Q[...,1]/z
            fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=self.p;r=x*x+y*y
            radial=(1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3)
            pin=np.stack([fx*x+cx,fy*y+cy],-1)
            uv=np.stack([fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx,fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy],-1)
            valid=(z>0)&np.isfinite(uv).all(-1)&(pin[...,0]>=-200)&(pin[...,0]<=self.w+200)&(pin[...,1]>=-200)&(pin[...,1]<=self.h+200)&(np.linalg.norm(uv-pin,axis=-1)<400)
        return uv,valid
    def photo(self,j):
        raw=self.archive.read(self.members[j]);im=Image.open(io.BytesIO(raw)).convert('RGB')
        assert im.size==(self.w,self.h)
        return im,hashlib.sha256(raw).hexdigest()

def supports(d,ii,margin=0):
    # Preserve each source centre, tangents and patch area; no GT geometry is used.
    t1=d['tangent1'][ii].astype(float);t2=d['tangent2'][ii].astype(float)
    a=np.linalg.norm(t1,axis=1);b=np.linalg.norm(t2,axis=1)
    if np.any(a<1e-10)|np.any(b<1e-10):return None
    t1/=a[:,None];t2/=b[:,None];half=np.sqrt(d['area'][ii])/2+margin
    signs=np.array([[-1,-1],[1,-1],[1,1],[-1,1]])
    return d['centre'][ii,None,:]+half[:,None,None]*(signs[None,:,0,None]*t1[:,None,:]+signs[None,:,1,None]*t2[:,None,:])

def wrong_components(d,radius):
    wrong=(d['judgment_after']==1)&(((d['cell']==1)&(d['initial_choice']==0))|((d['cell']==2)&(d['initial_choice']==1)))
    result=[]
    for bid in sorted(set(d['building'][wrong])):
        for cell in [1,2]:
            ids=np.flatnonzero(wrong&(d['building']==bid)&(d['cell']==cell))
            lab,nc=components(d['centre'][ids],radius)
            if not nc:continue
            areas=np.bincount(lab,weights=d['area'][ids],minlength=nc)
            order=np.argsort(lab,kind='stable');starts=np.r_[0,np.cumsum(np.bincount(lab,minlength=nc))]
            for k in range(nc):
                ii=ids[order[starts[k]:starts[k+1]]]
                result.append({'building':bid,'cell':cell,'area_m2':float(areas[k]),'indices':ii,'tie_patch':min(d['patch_id'][ii])})
    result.sort(key=lambda r:(-r['area_m2'],r['building'],r['cell'],r['tie_patch']))
    picked=[];counts={}
    for r in result:
        if counts.get(r['building'],0)>=3:continue
        picked.append(r);counts[r['building']]=counts.get(r['building'],0)+1
        if len(picked)==20:break
    return picked,len(result)

def select_camera(cam,d,ii):
    quads=supports(d,ii);margin=supports(d,ii,3.)
    if quads is None:return None
    ranking=[]
    for j in range(len(cam.names)):
        # A component must fit in the image. The score is summed front-facing
        # projected patch support, not a claim of unoccluded observed area.
        view=cam.centres[j]-d['centre'][ii];front=np.einsum('ij,ij->i',view,d['normal'][ii])>0
        if not front.any():continue
        uv,valid=cam.project(quads,j)
        within=valid&(uv[...,0]>=0)&(uv[...,0]<cam.w)&(uv[...,1]>=0)&(uv[...,1]<cam.h)
        if not within.all():continue
        area=np.abs(np.sum(uv[:,:,0]*np.roll(uv[:,:,1],-1,axis=1)-uv[:,:,1]*np.roll(uv[:,:,0],-1,axis=1),axis=1))*.5
        score=float(area[front].sum())
        if score<=0:continue
        expanded,ok=cam.project(margin,j)
        if not ok.all():continue
        ranking.append((score,j))
    if not ranking:return None
    ranking.sort(key=lambda x:(-x[0],cam.names[x[1]]));score,j=ranking[0]
    uv,_=cam.project(quads,j);expanded,_=cam.project(margin,j)
    box=[max(0,int(np.floor(expanded[...,0].min()))),max(0,int(np.floor(expanded[...,1].min()))),
         min(cam.w,int(np.ceil(expanded[...,0].max()))),min(cam.h,int(np.ceil(expanded[...,1].max())))]
    return j,score,uv,box,ranking

def main():
    setup();cfg=json.loads((C/'judgenum_v1.json').read_text());cal=json.loads((O/'calibration.json').read_text())['values']
    cam=Cameras(Path(cfg['sources']['widen']));allrows=[]
    # Verify copied rational projection with OpenCV, using the real calibration.
    import cv2
    X=np.array([[1.,2.,10.],[-2.,1.,5.]])
    K=np.array([[cam.p[0],0,cam.p[2]],[0,cam.p[1],cam.p[3]],[0,0,1.]])
    savedR,savedt=cam.R[0].copy(),cam.t[0].copy();cam.R[0]=np.eye(3);cam.t[0]=0
    uv,_=cam.project(X,0);check,_=cv2.projectPoints(X,np.zeros(3),np.zeros(3),K,cam.p[4:])
    assert np.allclose(uv,check.reshape(-1,2),rtol=0,atol=1e-8);cam.R[0],cam.t[0]=savedR,savedt
    for prior in ['LoD2','ALS']:
        d,sources=data(prior);base=cal[prior]['base'];picked,count=wrong_components(d,base['components_radius_m']);cards=[]
        for number,r in enumerate(picked,1):
            ii=r['indices'];photo=[]
            for i in ii:
                group='roof' if prior=='ALS' or d['kind'][i]==1 else 'wall';pi=base['photo_choices'][group]//9
                photo.append(min(int(d['photo_judgments'][i,pi]),2))
            photo=np.array(photo);pa=[float(d['area'][ii[photo==k]].sum()) for k in range(3)]
            description='/'.join(f'{label} {pa[k]/sum(pa)*100:.0f}%' for k,label in enumerate(['지지','반박','모름']) if pa[k]>0)
            meta={k:v for k,v in r.items() if k not in ['indices','tie_patch']};meta.update({'rank':number,'prior':prior,
              'patch_ids':d['patch_id'][ii].tolist(),'photo_area_m2':pa,'photo_label':description,
              'median_d_cm':float(np.median(d['d_mean_cm'][ii])),'camera_sources':cam.source,'photos':[]})
            selected=select_camera(cam,d,ii)
            crop=None;lines=[]
            if selected is None:meta['unavailable']='No complete component projection or undefined source tangent; no substitute image'
            else:
                j,score,uv,box,ranking=selected;im,imgsha=cam.photo(j);crop=np.array(im.crop(box));del im
                polygons=[Polygon(q) for q in uv if Polygon(q).is_valid and Polygon(q).area>0]
                union=unary_union(polygons)
                polys=[union] if union.geom_type=='Polygon' else list(union.geoms)
                for poly in polys:
                    if poly.geom_type!='Polygon':continue
                    lines.append(np.array(poly.exterior.coords)-box[:2])
                    for inner in poly.interiors:lines.append(np.array(inner.coords)-box[:2])
                meta.update({'photos':[{'name':cam.names[j],'zip_member':cam.members[j],'sha256':imgsha,'crop_xyxy_px':box}],
                  'projected_front_patch_area_px2':score,'eligible_training_images':len(ranking),
                  'ranking': [{'name':cam.names[k],'area_px2':s} for s,k in ranking],
                  'outline_crop_pixels':[x.tolist() for x in lines],
                  'projection_note':'Original FULL_OPENCV; prior centre/tangent patch support; 3m margin in each source plane; no new visibility test'})
            cards.append((crop,lines,meta));allrows.append({k:v for k,v in meta.items() if k not in ['patch_ids','ranking','outline_crop_pixels','camera_sources']})
            print('MONTAGE_CARD',prior,number,'AVAILABLE' if crop is not None else 'UNAVAILABLE',flush=True)
        for page in range((len(cards)+9)//10):
            fig,axs=plt.subplots(5,2,figsize=(14,17));values=[]
            for ax,card in zip(axs.flat,cards[page*10:(page+1)*10]):
                crop,lines,meta=card;values.append(meta)
                if crop is None:ax.text(.5,.5,'사진 확인 불가',ha='center',va='center',transform=ax.transAxes)
                else:
                    ax.imshow(crop)
                    for line in lines:ax.plot(line[:,0],line[:,1],color='#00ffff',lw=.6)
                bid=meta['building'].removeprefix('DEBY_LOD2_')
                ax.set_title(f"{meta['rank']:02d} · {bid} · {meta['area_m2']:.2f} m² · 칸 {meta['cell']}\n{meta['photo_label']} · d {meta['median_d_cm']:.1f} cm",fontsize=9)
                ax.set_axis_off()
            for ax in list(axs.flat)[len(values):]:ax.set_axis_off()
            fig.suptitle(('항공 LiDAR' if prior=='ALS' else prior)+' · 처음 선택이 틀린 덩어리',fontsize=16);fig.tight_layout(rect=[0,0,1,.98])
            export(fig,f'wrong_montage_{prior}_{page+1}',{'sources':sources,'cards':values,'total_wrong_components':count,'selected_count':len(cards),
              'no_cause_labels':True,'ranking_rule':'descending wrong area; at most 3 per building; equal area: building, cell, patch ID'})
    save('montage_inventory',allrows)
    dump(O/'montage_complete.json',{'at':stamp(),'cards':len(allrows),'unavailable_images':sum('unavailable' in r for r in allrows),'scientific_verdict':None})

if __name__=='__main__':main()
