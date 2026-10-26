"""Conservative occlusion veto from public input LoD2 patch support only."""
from common import *
SCENE=None
def prepare():
    p=CFG/'amendment_05_solid_occlusion.json'
    if not p.exists():dump(p,dict(at=now(),task_id='PHD-SLIDE-PHOTO-v1',scientific_verdict=None,
       reason='Global exact-point z-buffer removes only 37555/65018 old samples from views with >50m median discrepancy. Sparse nadir point visibility does not model continuous foreground walls.',
       correction='Add a conservative occlusion veto by raycasting all public development LoD2 input patch squares. Reject a GT sample if an input surface is at least 0.5m nearer on the same camera ray. No holdout meshes, no MVS/result-based visibility decision; retain raw GT nearest-pixel test and all candidate thresholds.',
       limitation='This is conservative prior-supported visibility, not proof that the sampled MVS point belongs to the same physical surface. Old solid geometry may reject some currently visible samples. 0.5m tolerance is an occluder separation guard, not the MVS error threshold.',
       previous_attempt='mvs_v3 retained as point-only visibility evidence; use mvs_v4 for final selection. No v3 material review occurred.'))
    dest=PAY/'task0/public_lod2_visibility.npz'
    if dest.exists():return
    vv=[];ff=[];off=0;count=0
    for tile in load(W/'inputs/tiles.json'):
        z=geometry(tile['id'],'LoD2');ix=z['normal_defined'];C=z['centre'][ix];A=z['tangent1'][ix];B=z['tangent2'][ix]
        V=np.stack([C+a*A+b*B for a,b in [(-.125,-.125),(.125,-.125),(.125,.125),(-.125,.125)]],1).reshape(-1,3).astype(np.float32)
        base=np.arange(len(C),dtype=np.uint32)*4;F=np.concatenate([base[:,None]+[0,1,2],base[:,None]+[0,2,3]],axis=0).astype(np.uint32)+off;vv.append(V);ff.append(F);off+=len(V);count+=len(C)
    np.savez(dest,V=np.concatenate(vv),F=np.concatenate(ff));dump(dest.with_suffix('.json'),dict(patches=count,triangles=sum(len(x) for x in ff),source='Public geometry allowlist only; 0.25m tangent squares, conservative at boundary patches',scientific_verdict=None));print('SOLID SUPPORT',count,flush=True)
def visible(Q,pose,zq):
    global SCENE
    if not len(Q):return np.zeros(0,bool)
    import open3d as o3d
    if SCENE is None:
        m=np.load(PAY/'task0/public_lod2_visibility.npz');SCENE=o3d.t.geometry.RaycastingScene(nthreads=1);SCENE.add_triangles(o3d.core.Tensor(m['V']),o3d.core.Tensor(m['F']))
    C=-pose['R'].T@pose['t'];D=(Q-C)/zq[:,None];rays=np.c_[np.broadcast_to(C,Q.shape),D].astype(np.float32);hit=SCENE.cast_rays(o3d.core.Tensor(rays),nthreads=1)['t_hit'].numpy()
    return hit>=zq-.5
if __name__=='__main__':prepare()
