"""Development roof maps and wrong-photo components, CPU only, 300dpi."""
import json,sys,zipfile
import numpy as np
import cv2,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.collections import LineCollection,PolyCollection
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import open3d as o3d
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz
from photo_cameras import Cameras,RAW,W
from photo_planes import same_surface_triangles
from selected_npz import selected
from prepare import array
from metrics_reply2 import val,EX
from record_setting_reply2 import record as record_setting
BASE=O/'r2';FONT=font_manager.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc');font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc');plt.rcParams.update({'font.family':FONT.get_name(),'axes.unicode_minus':False,'font.size':9})
COLORS=['#39a96b','#f39b34','#3f88db','#3f88db','#a57bd8','#4a4f57','#f2ca42','#b9bfc4']

def scene_from_prior(g,prior):
    scene=o3d.t.geometry.RaycastingScene(nthreads=2);sources=[]
    for tile in np.unique(g['tile']):
        # Surface IDs come exclusively from retained development inputs. Only
        # their indexed triangles and vertices are decoded, never other patches.
        with np.load(O/'r1/inputs'/f'{tile}__{prior}.npz') as z:surfaces=np.unique(z['surf'])
        path=W/'holdout/internal/prior_tiles'/str(tile)/('als_mesh.npz' if prior=='ALS' else 'lod2_mesh.npz')
        with zipfile.ZipFile(path) as z:
            membership=array(z,'tri_surface');keep=np.isin(membership,surfaces);faces=selected(z,'F',keep)
            with z.open('V.npy') as f:ver=np.lib.format.read_magic(f);shape,_,_=np.lib.format._read_array_header(f,ver)
            ids=np.unique(faces);mask=np.zeros(shape[0],bool);mask[ids]=True;verts=selected(z,'V',mask);faces=np.searchsorted(ids,faces)
        shift=np.array(json.loads((W/'holdout/internal/registration'/str(tile)/prior/'summary.json').read_text())['registration']['shift_applied'])
        scene.add_triangles(o3d.core.Tensor((verts+shift).astype('f4')),o3d.core.Tensor(faces.astype('u4')));sources.append(dict(path=str(path),sha256=sha(path),surface_ids=surfaces.tolist(),triangles=len(faces)))
    return scene,sources

def rgb(cam,j):
    if cam.archive is None:cam.archive=zipfile.ZipFile(RAW/'raw/uav/Images.zip')
    return cv2.cvtColor(cv2.imdecode(np.frombuffer(cam.archive.read(cam.members[j]),np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)

def background(g,cam,prior):
    c=g['centre'];lo=np.floor((c[:,:2].min(0)-1)/.05)*.05;hi=np.ceil((c[:,:2].max(0)+1)/.05)*.05
    xs=np.arange(lo[0],hi[0],.05)+.025;ys=np.arange(lo[1],hi[1],.05)+.025;xx,yy=np.meshgrid(xs,ys);scene,sources=scene_from_prior(g,prior)
    top=np.nanmax(c[:,2])+50;rays=np.c_[xx.ravel(),yy.ravel(),np.full(xx.size,top),np.zeros(xx.size),np.zeros(xx.size),-np.ones(xx.size)].astype('f4');hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy();pts=rays[:,:3].astype(float);pts[:,2]-=hit;valid=np.isfinite(hit)
    center=np.median(c,axis=0);direction=cam.centres-center;angles=np.degrees(np.arccos(np.clip(direction[:,2]/np.linalg.norm(direction,axis=1),-1,1)))
    camera=None
    for j in np.argsort(angles):
        uv,_,ok=cam.project(center[None],int(j))
        if ok[0] and 0<=uv[0,0]<cam.w and 0<=uv[0,1]<cam.h:camera=int(j);break
    image=np.full((xx.size,3),.72);occluded=np.zeros(xx.size,bool)
    if camera is not None and valid.any():
        v=pts[valid]-cam.centres[camera];distance=np.linalg.norm(v,axis=1);rays=np.c_[np.broadcast_to(cam.centres[camera],v.shape),v/distance[:,None]].astype('f4');depth=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy();uv,_,guard=cam.project(pts[valid],camera)
        visible=guard&(distance<=depth+.3)&(uv[:,0]>=0)&(uv[:,0]<cam.w-1)&(uv[:,1]>=0)&(uv[:,1]<cam.h-1);ids=np.flatnonzero(valid);occluded[ids[~visible]]=True
        im=rgb(cam,camera);pixels=np.empty((len(uv),3),float)
        for start in range(0,len(uv),16000):
            q=uv[start:start+16000];pixels[start:start+len(q)]=cv2.remap(im,q[:,0].astype('f4')[None],q[:,1].astype('f4')[None],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)[0]/255.
        image[ids[visible]]=pixels[visible]
    return image.reshape(xx.shape+(3,)),[lo[0],hi[0],lo[1],hi[1]],camera,dict(grid_m=.05,grid_cells=xx.size,prior_surface_cells=int(valid.sum()),occluded_or_out_of_image_cells=int(occluded.sum()),surface='original W registered prior mesh, surfaces referenced by retained development cores only; raycast visibility on those surfaces',sources=sources)

def boundaries(cells,mask):
    occupied=set(map(tuple,cells[mask]));segments=[]
    for x,y in occupied:
        for dx,dy,coords in [(1,0,[(x+1,y),(x+1,y+1)]),(-1,0,[(x,y),(x,y+1)]),(0,1,[(x,y+1),(x+1,y+1)]),(0,-1,[(x,y),(x+1,y)])]:
            if (x+dx,y+dy) not in occupied:segments.append(np.asarray(coords)*.25)
    return segments

def maps(prior):
    files=sorted((BASE/'core_points').glob(f'*__{prior}__1.npz'));parts=[loadz(p) for p in files];keys=['patch_id','photo_point_id','building','centre','normal','prior_height_m','area','surf','geometry','cell','region','reason'];g={k:np.concatenate([p[k] for p in parts],axis=1 if k in ['region','reason'] else 0) for k in keys};g['tile']=np.concatenate([np.full(len(p['patch_id']),f.stem.split('__')[0]) for f,p in zip(files,parts)]);del parts
    ranking=sorted([(float(g['area'][(g['building']==b)&(g['geometry']==1)].sum()),str(b)) for b in np.unique(g['building'])],key=lambda v:(-v[0],v[1]));chosen=ranking[:4]
    current=json.loads((C/'judgecheck_v1.json').read_text())['figures'].get('selected_buildings') or {};current[prior]=[b for _,b in chosen]
    record_setting('figures','selected_buildings',current,'Freeze ordered top-four outside-limit roof building IDs before figure rendering')
    lock=C/f'figure1.{prior}.selection.reply2.json';dump(lock,dict(at=now(),selection='top four retained roof outside-limit areas, ID tie break',buildings=[dict(building=b,outside_area_m2=a) for a,b in chosen],source_sha256=sha(Path(__file__)),scientific_verdict=None));cam=Cameras();acc=json.loads((D/'tables'/f'{prior}_1_6_2_buildings.json').read_text())['rows'];outputs=[]
    for _,bid in chosen:
        take=np.flatnonzero(g['building']==bid);d={k:(v[:,take] if k in ['region','reason'] else v[take]) for k,v in g.items()};bg,extent,j,meta=background(d,cam,prior);cells=np.floor(d['centre'][:,:2]/.25).astype(int)
        # Stable maximum-area core wins when multiple patches occupy one map cell.
        owners={}
        for i in np.argsort(-d['area'],kind='stable'):owners.setdefault(tuple(cells[i]),int(i))
        ii=np.array(list(owners.values()));coords=cells[ii]*.25;polys=np.stack([coords,coords+[.25,0],coords+[.25,.25],coords+[0,.25]],axis=1)
        for vi,label in [(0,'고친 사진'),(2,'옛 사진')]:
            reg=d['region'][vi];why=d['reason'][vi];geo=np.select([d['geometry']==0,d['geometry']==1,d['geometry']==2],[0,6,4],default=7);truth=np.select([d['cell']==0,d['cell']==1,d['cell']==2,d['cell']==3,np.isin(d['cell'],[4,5])],[0,2,1,5,4],default=7)
            fig,axes=plt.subplots(1,3,figsize=(13.8,5));fig.patch.set_facecolor('white')
            for ax,labels,title in zip(axes,[geo,reg,truth],['기하 검사','기하와 사진 확인','참값']):
                ax.imshow(bg,origin='lower',extent=extent);rgba=np.array([matplotlib.colors.to_rgba(COLORS[int(v)] if int(v)<len(COLORS) else COLORS[7],.54) for v in labels[ii]])
                if title=='참값':rgba[np.isin(d['cell'][ii],[6,9]),3]=0
                ax.add_collection(PolyCollection(polys,facecolors=rgba,edgecolors='none'));ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.set_aspect('equal');ax.set_title(title,fontsize=13);ax.set_xticks([]);ax.set_yticks([])
            for pattern,m in [('////',(why[ii]==2)&np.isin(reg[ii],[1,2])),('..',reg[ii]==3)]:
                if m.any():axes[1].add_collection(PolyCollection(polys[m],facecolors='none',edgecolors='#3f4650',linewidths=0,hatch=pattern))
            harm=((reg==0)&np.isin(d['cell'],[1,2]))|((reg==1)&(d['cell']==1))|(np.isin(reg,[2,3])&(d['cell']==2))
            for tile,surf in sorted(set(zip(d['tile'][harm],d['surf'][harm]))):
                seg=boundaries(cells[ii],harm[ii]&(d['surf'][ii]==surf)&(d['tile'][ii]==tile))
                if seg:axes[1].add_collection(LineCollection(seg,colors='#c9252d',linewidths=.8))
            rates=[]
            for v in ['new_clipped' if vi==0 else 'new_oldphoto','always_prior','always_mvs']:
                r=next(x for x in acc if x['building']==bid and x['variant']==v);rates.append('확인 불가' if r['fraction'] is None else f"{r['fraction']*100:.1f}%")
            fig.suptitle(f'{"항공 LiDAR" if prior=="ALS" else "LoD2"} · {label}: 같은 색의 짝과 다른 곳을 확인',fontsize=15,y=.98)
            handles=[Patch(facecolor=COLORS[k],label=l) for k,l in [(0,'일치 / 둘 다 맞음'),(1,'보존 / 영상만 틀림'),(2,'보정 / 사전 정보만 틀림'),(4,'결측 / 영상 없음'),(5,'둘 다 틀림'),(6,'한계 밖')]]
            handles.extend([Patch(facecolor='white',edgecolor='#3f4650',hatch='////',label='기본 방향'),Patch(facecolor=COLORS[2],edgecolor='#3f4650',hatch='..',label='빈 공간 보정'),Patch(facecolor=COLORS[7],label='셀 수 없음')])
            fig.legend(handles=handles,loc='lower center',ncol=3,bbox_to_anchor=(.5,.045),frameon=False);fig.text(.5,.015,f'짝이 맞으면 판단이 맞음  |  틀린 비율: 본 판 {rates[0]} · 늘 사전 정보 {rates[1]} · 늘 영상 {rates[2]}',ha='center',fontsize=9)
            fig.subplots_adjust(left=.015,right=.985,top=.88,bottom=.22,wspace=.035)
            out=D/'figures'/f'그림1_{prior}_{bid}_{vi}';out.parent.mkdir(exist_ok=True);fig.savefig(out.with_suffix('.png'),dpi=300);plt.close(fig)
            record=val(dict(at=now(),building=bid,prior=prior,variant=label,camera=cam.names[j] if j is not None else None,background=meta,patch_ids=d['patch_id'].tolist(),photo_point_ids=d['photo_point_id'].tolist(),display_owner_patch_ids=d['patch_id'][ii].tolist(),values={k:d[k].tolist() for k in ['area','geometry','cell']},region=reg.tolist(),reason=why.tolist(),wrong_rates=rates,excluded_shared_cores=EX,scientific_verdict=None));dump(out.with_suffix('.json'),record);outputs.append(str(out.with_suffix('.png')));print('FIGURE_MAP',out.name,flush=True)
    dump(BASE/'figures'/f'{prior}_maps.complete.json',dict(at=now(),files=outputs,scientific_verdict=None))

if __name__=='__main__':maps(sys.argv[1])
