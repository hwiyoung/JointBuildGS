"""Attach unchanged patch values to exact LoD2 triangles, then package the viewer."""
import shutil
import sys
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *
from build_data import encode, js
from lock_v11 import DR

WEB = OUT/'web_v1_1'

def inside_triangle(p,t):
    a,b,c=t[:,:2]; v0=b-a; v1=c-a; v=p-a
    det=v0[0]*v1[1]-v0[1]*v1[0]
    if abs(det)<1e-12: return np.zeros(len(p),bool), np.zeros(len(p)), np.zeros(len(p))
    u=(v[:,0]*v1[1]-v[:,1]*v1[0])/det
    w=(v0[0]*v[:,1]-v0[1]*v[:,0])/det
    return (u>=-1e-9)&(w>=-1e-9)&(u+w<=1+1e-9),u,w

def triangle_distance(p,t):
    a,b,c=t; ab=b-a; ac=c-a; n=np.cross(ab,ac); norm=np.linalg.norm(n)
    if norm<1e-12: return np.full(len(p),np.inf)
    n/=norm; signed=(p-a)@n; projected=p-signed[:,None]*n
    v=projected-a; d00=ab@ab;d01=ab@ac;d11=ac@ac;den=d00*d11-d01*d01
    u=(d11*(v@ab)-d01*(v@ac))/den;w=(d00*(v@ac)-d01*(v@ab))/den
    inside=(u>=-1e-9)&(w>=-1e-9)&(u+w<=1+1e-9)
    dist=np.full(len(p),np.inf)
    for start,end in [(a,b),(b,c),(c,a)]:
        edge=end-start; length=edge@edge
        q=np.clip(((p-start)@edge)/max(length,1e-30),0,1)
        dist=np.minimum(dist,np.linalg.norm(p-start-q[:,None]*edge,axis=1))
    return np.where(inside,np.abs(signed),dist)

def surfaces(site):
    records=load(DR/site/'lod2_surfaces.json')['surfaces']
    with np.load(DR/site/'lod2_mesh.npz') as z:
        triangles=z['V'][z['F']]; exts=z['tri_surface']
    lod=pv(site,'LoD2',1.)
    result=[]
    for r in sorted(records,key=lambda r:r['ext']):
        ids=np.flatnonzero(lod['surf']==r['ext']); codes=lod['roof_type'][ids]
        names,counts=np.unique(codes[codes!=''],return_counts=True)
        rt=str(names[np.argmax(counts)]) if len(names) else ''
        ts=triangles[exts==r['ext']]
        assert len(ts), ('surface without geometry',site,r['ext'])
        result.append(dict(id='L'+str(r['ext']),ext=r['ext'],type=r['type'],kind=r['kind'],
            roof_type=rt,area_m2=r['area_m2'],building=r['building'],triangles=ts.tolist(),grid=False))
    return result

def attach(site,prior,z,fs):
    c=z['centre']; assignment=np.full(len(c),-1,np.int32)
    ext_to_index={f['ext']:i for i,f in enumerate(fs)}
    if prior=='LoD2':
        with np.load(Path('/s1/regions_v3')/f'regions_ext_v3_{site}_{prior}.npz') as region:
            assert np.array_equal(c,region['centre'])
            assert np.array_equal(z['surf'],region['surf_ext'])
            assignment[:]=[ext_to_index.get(int(ext),-1) for ext in region['surf_ext']]
    else:
        best=np.full(len(c),np.inf); roof=z['roof_like'].astype(bool)
        for fi,f in enumerate(fs):
            for tri in np.asarray(f['triangles']):
                if f['type']=='roof':
                    lo,hi=tri[:,:2].min(0)-1e-9,tri[:,:2].max(0)+1e-9
                    ids=np.flatnonzero(roof&np.all(c[:,:2]>=lo,axis=1)&np.all(c[:,:2]<=hi,axis=1))
                    if not len(ids):continue
                    ok,u,w=inside_triangle(c[ids,:2],tri)
                    zz=tri[0,2]+u*(tri[1,2]-tri[0,2])+w*(tri[2,2]-tri[0,2])
                    distance=np.abs(c[ids,2]-zz); good=ok&(distance<best[ids]-1e-12)
                else:
                    lo,hi=tri.min(0)-1,tri.max(0)+1
                    ids=np.flatnonzero(~roof&np.all(c>=lo,axis=1)&np.all(c<=hi,axis=1))
                    if not len(ids):continue
                    distance=triangle_distance(c[ids],tri);good=(distance<=1)&(distance<best[ids]-1e-12)
                assignment[ids[good]]=fi;best[ids[good]]=distance[good]
    fallback=np.flatnonzero(assignment<0)
    ij=np.floor(c[fallback,:2]/2).astype(np.int64)
    cells,inv=np.unique(ij,axis=0,return_inverse=True)
    for k,(x,y) in enumerate(cells):
        ids=fallback[inv==k];zz=float(np.median(c[ids,2]));a=[x*2,y*2,zz];b=[x*2+2,y*2,zz];d=[x*2,y*2+2,zz];cc=[x*2+2,y*2+2,zz]
        assignment[ids]=len(fs)
        fs.append(dict(id=f'G{x}_{y}',ext=None,type='grid',kind=0,roof_type='',area_m2=4,
                       triangles=[[a,b,cc],[a,cc,d]],grid=True))
    assert (assignment>=0).all()
    return assignment

def main():
    config=load(CFG/'view_v1_1.json');assert sha(CFG/'view_v1_1.json')==load(CFG/'view_v1_1.lock.json')['sha256']
    WEB.mkdir(exist_ok=True)
    # Independent byte-identical copies keep the complete v1 bundle available.
    for name in ['data','sections']:
        if not (WEB/name).exists():shutil.copytree(OUT/'web'/name,WEB/name)
    for name in ['reports.js']:
        shutil.copy2(OUT/'web'/name,WEB/name)
    manifest=json.loads((OUT/'web/manifest.js').read_text().split('=',1)[1].rstrip(';\n'))
    manifest['view_v1_1']=config;manifest['view_v1_1_sha256']=sha(CFG/'view_v1_1.json')
    roof_layer=next(x for x in manifest['config']['layers'] if x['id']=='roof_type')
    roof_layer.update(label='지붕 형태',group='자리',description='LoD2 파일의 지붕 형태 속성')
    js(WEB/'manifest.js','UNCERT_MANIFEST',manifest)
    summary=[]
    for site,prior in U.CASES:
        case=site+'__'+prior;z=pv(site,prior,config['population']['pool_radii'][site]);fs=surfaces(site)
        assigned=attach(site,prior,z,fs)
        np.savez(OUT/f'faces_v1_1_{case}.npz',face=assigned)
        packet=dict(case=case,faces=fs,assignment=encode(assigned))
        js(WEB/'faces'/f'{case}.js','UNCERT_FACES',packet)
        dump(OUT/f'faces_v1_1_{case}.json',dict(case=case,faces=fs))
        grid=np.array([f['grid'] for f in fs])[assigned];ev=z['in_eval'].astype(bool)
        rec=dict(case=case,faces=len({int(f) for f in assigned[~grid]}),grids=len({int(f) for f in assigned[grid]}),
                 total=len(assigned),attached=int((~grid).sum()),fallback=int(grid.sum()),attached_fraction=float((~grid).mean()),
                 eval_total=int(ev.sum()),eval_attached=int((ev&~grid).sum()),eval_grid=int((ev&grid).sum()))
        summary.append(rec); print(rec,flush=True)
    dump(DOC/'tables_v1_1/face_assignment.json',dict(rows=summary,scientific_verdict=None))
    install_ui()
    progress('v1.1 일 2: 여섯 경우를 LoD2 면과 2 m 격자에 연결. 원본 패치 수치·v1 묶음 보존. 면 연결 파일과 비율 표 저장.')

def install_ui():
    for name in ['index.html','style.css','app.js','data.js','stats.js','analysis_v11.js','view_v11.js','view_v11.css']:
        p=ROOT/'scripts/phd/main_uncert_view_v1'/name
        if p.exists():shutil.copy2(p,WEB/name)

if __name__=='__main__':
    if '--ui' in sys.argv:install_ui()
    else:main()
