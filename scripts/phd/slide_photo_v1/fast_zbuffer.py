import ctypes,subprocess,time
from common import *
def build():
    src=Path(__file__).with_name('zbuffer.cpp');dest=PAY/'tmp/zbuffer.so'
    if not dest.exists() or src.stat().st_mtime>dest.stat().st_mtime:
        subprocess.run(['g++','-O3','-ffp-contract=off','-shared','-fPIC',str(src),'-o',str(dest)],check=True)
    lib=ctypes.CDLL(str(dest));lib.zbuffer.argtypes=[ctypes.c_void_p,ctypes.c_int64,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p];return lib
LIB=None
def fast(X,p,cam,buf=None):
    global LIB
    if LIB is None:LIB=build()
    x=np.ascontiguousarray(X,dtype=np.float64);r=np.ascontiguousarray(p['R'],dtype=np.float64);t=np.ascontiguousarray(p['t'],dtype=np.float64);k=np.ascontiguousarray(cam['p'],dtype=np.float64)
    if buf is None:buf=np.full(741*1024,np.inf)
    LIB.zbuffer(x.ctypes.data,len(x),r.ctypes.data,t.ctypes.data,k.ctypes.data,buf.ctypes.data);return buf
if __name__=='__main__':
    from task0_scan import points,cameras_depth
    poses,cam=cameras_depth();X=points('6909_53361')[::7].copy();rows=[]
    # Deterministic geometry-only camera sample: four largest projected counts.
    choices=[]
    for name,p in poses.items():
        uv,z=G.project(X[::1000],p,cam);ok=(z>0)&(uv[:,0]>=0)&(uv[:,0]<1024)&(uv[:,1]>=0)&(uv[:,1]<741);choices.append((int(ok.sum()),name))
    for _,name in sorted(choices,reverse=True)[:4]:
        p=poses[name];start=time.monotonic();uv,z=G.project(X,p,cam);ij=np.floor(np.nan_to_num(uv,nan=-1,posinf=-1,neginf=-1)).astype(np.int64);ok=(z>0)&(ij[:,0]>=0)&(ij[:,0]<1024)&(ij[:,1]>=0)&(ij[:,1]<741);slow=np.full(741*1024,np.inf);np.minimum.at(slow,ij[ok,1]*1024+ij[ok,0],z[ok]);seconds=time.monotonic()-start
        start=time.monotonic();quick=fast(X,p,cam);s2=time.monotonic()-start;finite=np.isfinite(slow);same=np.array_equal(finite,np.isfinite(quick));delta=float(np.max(abs(slow[finite]-quick[finite]))) if finite.any() else 0;assert same and delta<1e-9
        rows.append(dict(view=name,points=len(X),same_occupied_pixels=same,max_depth_delta_m=delta,numpy_seconds=seconds,compiled_seconds=s2))
    dump(PAY/'zbuffer_replay.json',dict(status='PASS',checks=rows,source_sha256=sha(Path(__file__).with_name('zbuffer.cpp')),compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],scientific_verdict=None));print(rows)
