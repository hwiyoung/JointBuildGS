"""Native photo extraction and geometric overlays; no image synthesis."""
import io,zipfile
from scipy.spatial import ConvexHull
from PIL import Image,ImageDraw,ImageFont
from common import *
def models():
    return G.poses(G.DENSE/'triangulated/images.bin'),G.cameras(G.DENSE/'triangulated/cameras.bin')
def crop_native(stem,X,aspect=None,pad=.25):
    poses,cams=models();p=poses[stem];cam=cams[p['cam']];uv,z=G.project(np.asarray(X),p,cam)
    inside=(z>0)&(uv[:,0]>=0)&(uv[:,0]<cam['w'])&(uv[:,1]>=0)&(uv[:,1]<cam['h'])
    assert inside.any(), 'ROI outside native photograph'
    q=uv[inside];lo=q.min(0);hi=q.max(0);mid=(lo+hi)/2;size=np.maximum((hi-lo)*(1+2*pad),[600,400])
    if aspect:
        size=np.maximum(size,[size[1]*aspect,size[0]/aspect])
    size=np.minimum(size,[cam['w'],cam['h']]);lo=np.maximum(0,np.minimum(mid-size/2,[cam['w'],cam['h']]-size));hi=lo+size
    box=[int(np.floor(lo[0])),int(np.floor(lo[1])),int(np.ceil(hi[0])),int(np.ceil(hi[1]))]
    with zipfile.ZipFile(RAW) as f:
        members={Path(n).stem:n for n in f.namelist() if n.upper().endswith('.JPG')};member=members[stem];raw=f.read(member)
    im=Image.open(io.BytesIO(raw)).convert('RGB');im=im.crop(box)
    import hashlib
    polygon=uv-np.array(box[:2]);polygon=polygon[ConvexHull(polygon).vertices] if len(polygon)>=3 else polygon
    rec=dict(view=stem,crop_box_px=box,native_crop_size=list(im.size),original_archive=str(RAW),original_member=member,original_sha256=hashlib.sha256(raw).hexdigest(),pose=p,camera=cam,projected_fraction=float(inside.mean()),polygon_px=polygon.tolist())
    return im,rec
def outlined(im,poly,fill=True):
    arr=np.asarray(poly);arr=arr[np.isfinite(arr).all(1)]
    if len(arr)<3:return im.copy()
    try:arr=arr[ConvexHull(arr).vertices]
    except Exception:return im.copy()
    xy=[tuple(v) for v in arr];out=im.convert('RGBA');lay=Image.new('RGBA',im.size);d=ImageDraw.Draw(lay)
    if fill:d.polygon(xy,fill=(255,214,10,28))
    width=max(5,round(min(im.size)/130));d.line(xy+[xy[0]],fill=(0,0,0,255),width=width+5,joint='curve');d.line(xy+[xy[0]],fill=(255,214,10,255),width=width,joint='curve')
    return Image.alpha_composite(out,lay).convert('RGB')
def choose_native(X,names,normal=None,oblique=False):
    poses,cams=models();rows=[]
    # Native distorted cameras can fold outside the field: also use pinhole bounds.
    traincams=G.cameras(G.DENSE/'colmap_dense/sparse/cameras.bin')
    trainposes=G.poses(G.DENSE/'colmap_dense/sparse/images.bin')
    for name in names:
        stem=Path(name).stem
        if stem not in poses or stem not in trainposes:continue
        p=poses[stem];cam=cams[p['cam']];q,d=G.project(X,p,cam);tp=trainposes[stem];tc=traincams[tp['cam']];tq,td=G.project(X,tp,tc)
        ok=(d>0)&(q[:,0]>=0)&(q[:,0]<cam['w'])&(q[:,1]>=0)&(q[:,1]<cam['h'])&(td>0)&(tq[:,0]>=0)&(tq[:,0]<tc['w'])&(tq[:,1]>=0)&(tq[:,1]<tc['h'])
        if ok.mean()<.95:continue
        C=-p['R'].T@p['t'];v=C-np.mean(X,axis=0);v/=np.linalg.norm(v)
        angle=np.degrees(np.arccos(np.clip(abs(v@normal),0,1))) if normal is not None else G.tilt(p)
        area=float(np.prod(np.ptp(q[ok],axis=0)));rows.append(dict(view=stem,projected_area_px=area,angle_deg=float(angle),tilt_deg=G.tilt(p)))
    assert rows,'No native training image contains 95 percent of ROI'
    rows.sort(key=lambda r:(-r['angle_deg'] if oblique else -r['projected_area_px'],r['view']))
    return rows[0],rows
