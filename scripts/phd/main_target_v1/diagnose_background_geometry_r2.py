"""Explain large MVS seed disks without changing any input, initialization or gate."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image
from common import *
from report_stage0 import plt,save
sys.path.insert(0,str(REPO/'scripts/phd/main_axes71_v2'))
import mvs_surface as MS

def main():
    site,prior=sys.argv[1:3];cfg,lock=locked_r2();key=f'{site}_{prior}'
    diagnostic=json.loads((OUT/'r2/diagnose'/key/'diagnosis.json').read_text());largest=diagnostic['largest_initial_disk'];i=largest['seed_index']
    with np.load(OUT/'r2/stage1'/key/'seeds.npz') as z:s={k:z[k] for k in ['xyz','origin','normal','patch']}
    with np.load(OUT/'r2/background'/site/prior/'background.npz') as z:b={k:z[k] for k in z.files}
    nb=int((s['origin']==1).sum());j=i-nb;assert j>=0 and np.array_equal(s['xyz'][i],b['xyz'][j])
    tree=cKDTree(s['xyz'].astype(float));dist,index=tree.query(s['xyz'][i].astype(float),k=4)
    scale=float(np.sqrt(np.mean(dist[1:]**2)))
    assert abs(scale-largest['scale'][0])<1e-4,(scale,largest)
    camlist,_=MS.cameras(site);cam=camlist[int(b['view'][j])];M=np.array(cam['W2C']);q=b['xyz'][j].astype(float)@M[:3,:3].T+M[:3,3]
    u=int(np.rint(cam['fx']*q[0]/q[2]+cam['cx']));v=int(np.rint(cam['fy']*q[1]/q[2]+cam['cy']))
    source=S0/'fork_inputs/s61'/site;depth=np.load(source/'maps/mvs'/f"{cam['name']}.npy");conf=np.load(source/'maps/conf'/f"{cam['name']}.npy")
    assert conf[v,u]>0 and depth[v,u]>0 and abs(depth[v,u]-q[2])<.001
    y0,y1=max(0,v-10),min(cam['H'],v+11);x0,x1=max(0,u-10),min(cam['W'],u+11)
    patch=depth[y0:y1,x0:x1];mask=(conf[y0:y1,x0:x1]>0)&np.isfinite(patch)&(patch>0)
    record=dict(at=stamp(),site=site,prior=prior,seed_index=i,background_index=j,source_mvs_index=int(b['source_index'][j]),
        xyz=b['xyz'][j].tolist(),normal=b['normal'][j].tolist(),normal_missing=bool(b['normal_missing'][j]),u_replaced=bool(b['u_replaced'][j]),
        camera=cam['name'],pixel_uv=[u,v],source_depth_m=float(depth[v,u]),source_confidence=float(conf[v,u]),
        three_neighbor_distances_m=dist[1:].tolist(),neighbor_seed_indices=index[1:].tolist(),
        cpu_nearest_neighbor_scale_m=scale,gpu_scale_m=largest['scale'][0],
        neighborhood_valid_depth_quantiles_m=np.quantile(patch[mask],[0,.1,.5,.9,1]).tolist() if mask.any() else None,
        normal_rule='finite differences, else vertical up; unchanged frozen initialization',
        status='PASS_LINEAGE_AND_SCALE_RECONSTRUCTION',diagnostic_only=True,no_filter_or_scale_change=True,scientific_verdict=None)
    dump(OUT/'r2/diagnose'/key/'background_geometry.json',record);dump(DOC/'tables'/f'r2_background_geometry_{key}.json',record)
    imfile=list((source/'scene_LoD2/images').glob(cam['name']+'.*'));assert len(imfile)==1
    photo=np.asarray(Image.open(imfile[0]).convert('RGB').resize((cam['W'],cam['H']),Image.Resampling.BILINEAR))
    fig,ax=plt.subplots(1,3,figsize=(12,4.5));ax[0].imshow(photo);ax[0].plot(u,v,'ro',ms=5,mfc='none');ax[0].set(title='원본 MVS 영상의 해당 화소');ax[0].axis('off')
    im=ax[1].imshow(np.where(mask,patch,np.nan),cmap='viridis');ax[1].plot(u-x0,v-y0,'ro',ms=5,mfc='none');ax[1].set(title='주변 21×21 화소의 MVS 깊이 (m)');fig.colorbar(im,ax=ax[1],fraction=.045)
    selected=index;ax[2].scatter(s['xyz'][selected,0],s['xyz'][selected,2],c=['#c34b35','#438bb6','#438bb6','#438bb6'],s=28)
    for k,ii in enumerate(selected):ax[2].annotate('해당 점' if k==0 else f'이웃 {k}',(s['xyz'][ii,0],s['xyz'][ii,2]),fontsize=8)
    ax[2].set(title='해당 점과 가까운 세 씨앗',xlabel='동쪽 (m)',ylabel='높이 (m)');ax[2].set_aspect('equal',adjustable='datalim')
    fig.subplots_adjust(top=.79,bottom=.21,wspace=.32)
    save(fig,f'r2_background_geometry_{key}',f'{SITES_NAME(site)} · {prior}: 신뢰도 통과 MVS에도 큰 배경 원반이 생겼다',record,
        f'원본 신뢰도 {conf[v,u]:.6g} · CPU 크기 복원 {scale:.6f} m · 씨앗·크기·5 cm 기준 변경 없음')
    print(json.dumps(record),flush=True)

def SITES_NAME(site):return {'B173nb_b10':'B173 주변','B0_b10':'B0','R1rep_b10':'R1','B173_b0':'B173만'}[site]
if __name__=='__main__':main()
