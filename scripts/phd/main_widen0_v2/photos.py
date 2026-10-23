"""Development-only original-resolution crops; no visual cause labels."""
import io
import json
from pathlib import Path
import zipfile
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import binary_erosion
from analysis_common import O,DOC,CELLS,KO,KEYS,load,font,figure,save_table,dump
from photo_geometry import calibration,project,verify
from preflight import images,DENSE

def polygon_area(q):
    return .5*np.abs(np.sum(q[:,:,0]*np.roll(q[:,:,1],-1,axis=1)-q[:,:,1]*np.roll(q[:,:,0],-1,axis=1),axis=1))

def main():
    verify();plt=font();w,h,params=calibration();poses=images(DENSE/'sparse/images.bin')
    inv=json.loads((O/'inputs/image_inventory.json').read_text())['rows'];views=[r for r in inv if r['split']=='train' and r['nadir'] and r['original_zip_member']]
    chosen=json.loads((DOC/'tables/대표자리_선정.json').read_text())['rows'];records=[];cache={}
    for prior in ['LoD2','ALS']:
        d=load(prior,keys=KEYS+['tangent1','tangent2']);z=np.load(O/'components'/f'{prior}_labels.npz')
        assert np.array_equal(d['patch_id'],z['patch_id']);cache[prior]=(d,z['component'])
    crops=DOC/'figures/crops';crops.mkdir(parents=True,exist_ok=True)
    archive=zipfile.ZipFile('/art/phase-payloads/p0-audit/data/raw/uav/Images.zip')
    for rank,row in enumerate(chosen):
        d,lab=cache[row['prior']];ids=np.flatnonzero(lab==int(row['component_id'].split(':')[-1]));assert len(ids)==row['patches']
        c=d['centre'][ids]+d['normal'][ids]*d['gt_p'][ids,None]
        t1=d['tangent1'][ids];t2=d['tangent2'][ids]
        offsets=np.array([[-1,-1],[1,-1],[1,1],[-1,1]])
        quad=c[:,None,:]+.125*(offsets[None,:,0,None]*t1[:,None,:]+offsets[None,:,1,None]*t2[:,None,:])
        # Same 0.25 m display quad as the inherited photo figure; clipped patch
        # area stays in numerical tables and is not inferred from the photo mask.
        margin=c[:,None,:]+3.125*(offsets[None,:,0,None]*t1[:,None,:]+offsets[None,:,1,None]*t2[:,None,:])
        best=None
        for v in views:
            po=poses[v['name']];uv,z=project(quad.reshape(-1,3),po['q'],po['t'],params);q=uv.reshape(-1,4,2)
            inside=(z.reshape(-1,4)>0).all(1)&(q[:,:,0]>=0).all(1)&(q[:,:,0]<w).all(1)&(q[:,:,1]>=0).all(1)&(q[:,:,1]<h).all(1)
            if not inside.all():continue
            a=float(polygon_area(q).sum())
            if best is None or a>best[0]:best=(a,v,q)
        rec=dict(component_id=row['component_id'],cell=row['cell'],prior=row['prior'],building_ids=row['building_ids'],area_m2=row['area_m2'])
        if best is None:
            rec.update(status='확인 불가',reason='No nadir training image contains all projected component patches.');records.append(rec);continue
        a,v,q=best;po=poses[v['name']];uv,z=project(margin.reshape(-1,3),po['q'],po['t'],params)
        lo=np.floor(uv.min(0)).astype(int);hi=np.ceil(uv.max(0)).astype(int)+1
        box=[max(0,int(lo[0])),max(0,int(lo[1])),min(w,int(hi[0])),min(h,int(hi[1]))];x0,y0,x1,y1=box
        raw=Image.open(io.BytesIO(archive.read(v['original_zip_member']))).convert('RGB');assert raw.size==(w,h)
        im=raw.crop(box);mask=Image.new('1',im.size);draw=ImageDraw.Draw(mask)
        for p in q:draw.polygon([(float(x-x0),float(y-y0)) for x,y in p],fill=1)
        m=np.asarray(mask,bool);edge=m&~binary_erosion(m,iterations=2);arr=np.array(im);arr[edge]=[255,210,0]
        name=f'{rank+1:02d}_{row["cell"]}_{row["prior"]}';Image.fromarray(arr).save(crops/f'{name}.png',dpi=(300,300))
        line=f'{KO[CELLS.index(row["cell"])]} · {row["building"]} · {row["area_m2"]:.2f} m² · 차 {row["difference_m"]["median"] if row["difference_m"]["median"] is not None else "없음"} m · {v["name"]}'
        fig,ax=plt.subplots(figsize=(10,7));ax.imshow(arr);ax.axis('off');fig.text(.5,.02,line,ha='center',fontsize=7)
        rec.update(status='PASS',image=v['name'],original_zip_member=v['original_zip_member'],crop_px=box,projected_patch_area_px2=a,nadir_tilt_deg=v['tilt_deg'],
            crop_clipped_to_image=bool((lo<0).any() or hi[0]>w or hi[1]>h),crop_file=f'figures/crops/{name}.png',panel_file=f'figures/{name}.png',caption=line,
            outline='0.25 m inherited display patch quads displaced by gt_p along outward normal; union outline',distortion_model='FULL_OPENCV')
        figure(fig,name,rec);plt.close(fig);records.append(rec)
    archive.close();save_table('대표사진_기록',records)
    for cell in ['prior_wrong','image_wrong','both_wrong']:
        rs=[r for r in records if r['cell']==cell];fig,axs=plt.subplots(5,4,figsize=(16,19))
        for i,ax in enumerate(axs.flat):
            ax.axis('off')
            if i>=len(rs):continue
            r=rs[i]
            if r['status']=='PASS':ax.imshow(Image.open(DOC/r['crop_file']))
            else:ax.text(.5,.5,'사진 확인 불가',ha='center',va='center')
            ax.set_title(f'{i+1}. {r["prior"]} · {r["building_ids"][0]}\n{r["area_m2"]:.2f} m²',fontsize=8)
        fig.suptitle(KO[CELLS.index(cell)]+' · 정하는 곳');fig.tight_layout()
        figure(fig,f'모음사진_{cell}',rs);plt.close(fig)
    print('photo panels complete',len(records),flush=True)
if __name__=='__main__':main()
