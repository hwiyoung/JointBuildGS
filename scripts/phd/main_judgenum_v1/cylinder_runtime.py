"""Build the task-local CPU executable and retain every invocation/receipt."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from lock_config import sha,dump,stamp
S=Path(__file__).parent;O=Path('/out')
HS=[5.,3.,10.];RADII=[.05,.075,.10,.125,.15,.20,.25,.30,.40,.50]

def build():
    binary=O/'tmp/cylinders';source=S/'cylinders.cpp'
    subprocess.run(['g++','-O3','-std=c++17','-Wall','-Wextra',str(source),'-o',str(binary)],check=True)
    dump(O/'tmp/cylinders_build.json',{'at':stamp(),'source_sha256':sha(source),
      'binary_sha256':sha(binary),'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
      'command':['g++','-O3','-std=c++17','-Wall','-Wextra',str(source),'-o',str(binary)]})
    return binary

def run(points,centres,normals,destination,binary):
    destination=Path(destination);destination.parent.mkdir(exist_ok=True,parents=True)
    corefile=destination.with_suffix('.cores.bin')
    np.column_stack([centres,normals]).astype('<f8').tofile(corefile)
    with Path(points).open('rb') as f:
        version=np.lib.format.read_magic(f);shape,order,dtype=np.lib.format._read_array_header(f,version);offset=f.tell()
    assert not order and shape[1]==3 and dtype==np.dtype('<f4')
    args=[str(binary),str(points),str(offset),str(shape[0]),str(corefile),str(len(centres)),str(destination)]
    started=stamp();t0=time.monotonic()
    subprocess.run(args,check=True)
    seconds=time.monotonic()-t0
    assert destination.stat().st_size==len(centres)*3*10*7*8
    dump(destination.with_suffix('.json'),{'started_at':started,'finished_at':stamp(),
      'seconds':seconds,'command':args,'shape':[len(centres),3,10,7],
      'columns':['n','d_mean_m','d_median_m','s_sample_m','nmad_m','face_o_m','raw_column_n'],
      'half_lengths_m':HS,'radii_m':RADII,'output_sha256':sha(destination),
      'scientific_verdict':None})
    return seconds

def verify():
    binary=build();root=O/'tmp/cylinder_verification';root.mkdir(exist_ok=True)
    spec=importlib.util.spec_from_file_location('inherited_face','/repo/scripts/phd/main_widen0_v2/u_core.py')
    inherited=importlib.util.module_from_spec(spec);spec.loader.exec_module(inherited)
    rng=np.random.default_rng(20261031)
    xyz=rng.uniform([-2,-2,-11],[2,2,11],(6000,3)).astype('f4')
    roof=rng.normal(size=(3000,3))*[.3,.3,.02]+[0,0,1.2]
    xyz=np.concatenate([xyz,roof.astype('f4'),np.array([[0,0,0],[.5,0,0],[0,0,5],[0,0,-5]],'f4')])
    p=root/'points.npy';np.save(p,xyz)
    centres=np.vstack([np.zeros((3,3)),rng.uniform(-.5,.5,(29,3))])
    normals=rng.normal(size=(len(centres),3));normals/=np.linalg.norm(normals,axis=1)[:,None]
    normals[:3]=[[0,0,1],[0,0,-1],[1,0,0]]
    out=root/'result.bin';run(p,centres,normals,out,binary)
    actual=np.memmap(out,dtype='<f8',mode='r',shape=(len(centres),3,10,7))
    defs={'layer_thickness_m':.3,'layer_step_m':.05,'layer_share':.2}
    tested=0;maximum=0.
    for i,(c,n) in enumerate(zip(centres,normals)):
        vv=xyz.astype(float)-c;t=vv@n;l=vv-t[:,None]*n
        r2=np.sum(l*l,axis=1)
        for h,H in enumerate(HS):
            for r,R in enumerate(RADII):
                col=t[(np.abs(t)<=H)&(r2<=R*R)];face,_,_=inherited.find_face(col,H,defs)
                vals=col[(col>=face-1)&(col<=face+1)] if face is not None else np.empty(0)
                expected=np.full(7,np.nan);expected[0]=len(vals);expected[6]=len(col)
                if len(vals):
                    med=np.median(vals)
                    expected[1:6]=[np.mean(vals),med,np.std(vals,ddof=1) if len(vals)>1 else np.nan,
                        1.4826*np.median(np.abs(vals-med)),face]
                got=actual[i,h,r]
                assert np.array_equal(np.isfinite(got),np.isfinite(expected)),(i,h,r,got,expected)
                finite=np.isfinite(expected)
                assert np.allclose(got[finite],expected[finite],atol=1e-10,rtol=1e-10),(i,h,r,got,expected)
                maximum=max(maximum,float(np.max(np.abs(got[finite]-expected[finite]))));tested+=1
    dump(O/'cylinder_verification.json',{'status':'PASS','cylinders':tested,
      'maximum_absolute_difference':maximum,'reference':'unchanged u_core.find_face plus independent brute-force cylinder mask',
      'source_sha256':sha(S/'cylinders.cpp'),'scientific_verdict':None})
    print('CYLINDER_VERIFICATION_PASS',tested,maximum)

if __name__=='__main__':verify()
