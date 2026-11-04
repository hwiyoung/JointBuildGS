from common import *
import ctypes,subprocess,sys
sys.path.append('/repo/scripts/phd/main_rescore_v1')
from geometry import patch_basis
def presence(core,mesh,path):
    if path.exists():return loadz(path)['present']
    import open3d as o3d
    if mesh.suffix=='.npz':
        z=loadz(mesh,['V','F']);V=z['V'];F=z['F']
    else:
        m=o3d.io.read_triangle_mesh(str(mesh));V=np.asarray(m.vertices);F=np.asarray(m.triangles)
    triangles=np.ascontiguousarray(V[F],dtype='f8')
    a,b,n=patch_basis(core);c=core['centre']+core['prior_height_m'][:,None]*n;length=np.where(core['kind']==1,10.,5.)
    basis=np.stack([a,b,n],axis=2);good=np.isfinite(basis).all((1,2))&np.isfinite(c).all(1);inverse=np.full_like(basis,np.nan)
    good[good]&=np.abs(np.linalg.det(basis[good]))>1e-10;inverse[good]=np.linalg.inv(basis[good])
    extent=.125*(abs(a)+abs(b))+length[:,None]*abs(n)
    records=np.ascontiguousarray(np.c_[c,inverse.reshape(-1,9),np.where(good,length,0),c-extent,c+extent],dtype='f8')
    exe=O/'bin/column_surface.so';src=Path(__file__).with_suffix('.py').with_name('column_surface.cpp')
    if not exe.exists():subprocess.run(['g++','-O3','-std=c++17','-shared','-fPIC','-fopenmp',str(src),'-o',str(exe)],check=True)
    lib=ctypes.CDLL(str(exe));dp=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS');bp=np.ctypeslib.ndpointer(dtype=np.uint8,flags='C_CONTIGUOUS')
    lib.surface_presence.argtypes=[dp,ctypes.c_int,dp,ctypes.c_int,bp]
    out=np.zeros(len(core['area']),'u1');lib.surface_presence(triangles,len(F),records,len(out),out)
    savez(path,present=out.astype(bool));dump(path.with_suffix('.json'),dict(mesh=str(mesh),mesh_sha256=sha(mesh),code_sha256=sha(src),rule='exact triangle versus inherited 0.25 m square prism, roof +/-10 m wall +/-5 m; no sample-empty approximation',scientific_verdict=None))
    return out.astype(bool)
