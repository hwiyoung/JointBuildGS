from common import *
from photos import *
from PIL import ImageOps
def main():
    c=config();rows=load(PAY/'task0/components.json')['components'][:10];poses,cams=models();photos=[]
    out=DOC/'figures/task0_crops';out.mkdir(exist_ok=True);native=PAY/'task0/native_crops';native.mkdir(exist_ok=True)
    for rank,row in enumerate(rows,1):
        row['rank']=rank
        view_counts={};total=len(row['patch_ids']);wanted=set(row['patch_ids'])
        for tile in row['tiles']:
            z=geometry(tile,row['prior']);m=dict(np.load(PAY/'task0/mvs_v4'/f'{tile}_{row["prior"]}.npz'))
            sel=np.array([s in wanted for s in z['patch_id'][m['patch_index']]])
            for i,name in enumerate(m['view_names']):view_counts[str(name)]=view_counts.get(str(name),0)+int(np.isfinite(m['per_view_signed'][sel,i]).sum())
        maxshare=max(view_counts.values())/total;names=[name for name,n in view_counts.items() if n/total>=min(.8,maxshare)]
        X=np.asarray(row['gt_representative']);normal=np.median(row['normal'],axis=0);normal/=np.linalg.norm(normal)
        try:
            best,bestlist=choose_native(X,names,normal,False);side,sidelist=choose_native(X,names,normal,True)
        except AssertionError:
            row['photo_unavailable']='No view contains at least 95 percent of component';photos.append(row);continue
        pair=[];records=[]
        for kind,sel in [('best',best),('oblique',side)]:
            im,rec=crop_native(sel['view'],X,aspect=1.5,pad=.25);marked=outlined(im,rec['polygon_px']);path=native/f'{rank:02d}_{kind}.png';marked.save(path)
            records.append(dict(kind=kind,file=str(path),selection=sel,pass_visible_patch_share=view_counts[sel['view']]/total,**rec));pair.append(ImageOps.contain(marked,(900,600)))
        canvas=Image.new('RGB',(1800,680),'white');d=ImageDraw.Draw(canvas);font=ImageFont.truetype('/fonts/NotoSansCJK-Regular.ttc',55)
        for i,im in enumerate(pair):canvas.paste(im,(i*900+(900-im.width)//2,80+(600-im.height)//2))
        d.text((25,10),f'{rank:02d}',font=font,fill='#202A35');canvas.save(out/f'{rank:02d}_pair.png')
        row.update(rank=rank,photos=records,pair_file=str(out/f'{rank:02d}_pair.png'),material=None);photos.append(row)
        print('PHOTO',rank,row['area_m2'],best['view'],side['view'],flush=True)
    combined=Image.new('RGB',(3600,3400),'white')
    for i,row in enumerate(photos):
        if row.get('pair_file'):combined.paste(Image.open(row['pair_file']),((i%2)*1800,(i//2)*680))
    combined.save(DOC/'figures/task0_contact_sheet.png')
    dump(PAY/'task0/top10_photos.json',dict(task_id=c['task_id'],candidates=photos,scientific_verdict=None))
    dump(DOC/'figures/task0_contact_sheet.json',dict(candidates=[dict(component_id=r['component_id'],rank=r.get('rank'),area_m2=r['area_m2'],photos=r.get('photos'),photo_unavailable=r.get('photo_unavailable')) for r in photos],scientific_verdict=None))
if __name__=='__main__':main()
