"""Verified task-local cylinders; no geometry GPU use."""
import subprocess,time
import numpy as np
from preflight import O,C,Path,sha,dump,now
from u_core import find_face
S=Path(__file__).parent;BASE=O/'r1'

def build():
    binary=BASE/'cylinders';src=S/'cylinders.cpp'
    subprocess.run(['g++','-O3','-std=c++17','-Wall','-Wextra',str(src),'-o',str(binary)],check=True)
    dump(BASE/'cylinders.build.json',dict(at=now(),source_sha256=sha(src),binary_sha256=sha(binary),
        compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0]))

def run(points,centres,normals,radii,destination):
    destination=Path(destination);destination.parent.mkdir(exist_ok=True,parents=True)
    cores=destination.with_suffix('.cores.bin');np.c_[centres,normals].astype('<f8').tofile(cores)
    with Path(points).open('rb') as f:
        v=np.lib.format.read_magic(f);shape,order,dtype=np.lib.format._read_array_header(f,v);offset=f.tell()
    assert not order and shape[1:]==(3,) and dtype in [np.dtype('<f4'),np.dtype('<f8')]
    args=[str(BASE/'cylinders'),str(points),str(offset),str(shape[0]),str(cores),str(len(centres)),
        str(destination),'f4' if dtype.itemsize==4 else 'f8',','.join(map(str,radii))]
    t0=time.monotonic();subprocess.run(args,check=True);seconds=time.monotonic()-t0
    outshape=(len(centres),2,len(radii),7);assert destination.stat().st_size==int(np.prod(outshape))*8
    dump(destination.with_suffix('.json'),dict(at=now(),seconds=seconds,command=args,shape=outshape,
        radii_m=radii,half_length_m=[5,10],columns=['n','mean_m','median_m','sd_m','nmad_m','face_m','raw_n'],
        output_sha256=sha(destination),scientific_verdict=None))
    return np.memmap(destination,mode='r',dtype='<f8',shape=outshape)

def verify():
    build();rng=np.random.default_rng(20261102);dest=BASE/'verification/cylinders';dest.mkdir(parents=True,exist_ok=True)
    xyz=np.r_[rng.uniform([-2,-2,-11],[2,2,11],(3000,3)),rng.normal(size=(1200,3))*[.5,.5,.02]+[0,0,1.2]]
    c=rng.uniform(-.5,.5,(20,3));n=rng.normal(size=(20,3));n/=np.linalg.norm(n,axis=1)[:,None];n[:3]=np.eye(3)
    radii=[.075,.125,.3,.4,.5,.55,.6,.75,1.];checked=0
    for dtype in ['f4','f8']:
        points=xyz.astype(dtype);np.save(dest/f'{dtype}.npy',points);got=run(dest/f'{dtype}.npy',c,n,radii,dest/f'{dtype}.bin')
        for i in range(len(c)):
            v=points.astype(float)-c[i];t=v@n[i];r2=np.sum((v-t[:,None]*n[i])**2,1)
            for hi,H in enumerate([5,10]):
                for ri,R in enumerate(radii):
                    col=t[(abs(t)<=H)&(r2<=R*R)];o,_,_=find_face(col,H,dict(layer_thickness_m=.3,layer_step_m=.05,layer_share=.2))
                    val=col[abs(col-o)<=1] if o is not None else np.empty(0)
                    exp=np.full(7,np.nan);exp[0]=len(val);exp[6]=len(col)
                    if len(val):
                        med=np.median(val);exp[1:6]=[val.mean(),med,val.std(ddof=1) if len(val)>1 else np.nan,1.4826*np.median(abs(val-med)),o]
                    assert np.allclose(got[i,hi,ri],exp,atol=1e-10,rtol=1e-10,equal_nan=True),(dtype,i,hi,ri)
                    checked+=1
    dump(BASE/'cylinder_verification.json',dict(at=now(),status='PASS',checked=checked,
        source_sha256=sha(S/'cylinders.cpp'),reference_sha256=sha(S/'u_core.py'),scientific_verdict=None))
    print('CYLINDER_PASS',checked)

if __name__=='__main__':verify()
