"""CPU registration and patch geometry, sealed until building-based export.

The raw centre assigns a tile core, then the registered centre supplies geometry.
This prevents different neighbouring shifts from duplicating a boundary patch.
"""
import json
from pathlib import Path
import time
import numpy as np
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
from matplotlib.path import Path as MPath
import prior_registration as PR
from face_assignment import attach
from tile_points import DT
from preflight import dump,sha

O=Path('/out');ROOT=O/'holdout/internal'

def clean(x):
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

def main():
    cfg=json.loads(Path('/cfg/widen0_v2.json').read_text());tiles=json.loads((O/'inputs/tiles.json').read_text())
    split=json.loads((O/'building_split.json').read_text());selected=set(split['development']+split['holdout']);held=set(split['holdout'])
    blds={b['id']:b for b in json.loads((O/'inputs/lod2_context_buildings.json').read_text())}
    ranks={b:i for i,b in enumerate(sorted(blds))}
    cover=np.load(O/'inputs/coverage.npz');mask=cover['common'];e0,n0,res=float(cover['e0']),float(cover['n0']),float(cover['res']);ny,nx=mask.shape
    projected=json.loads((O/'inputs/projected_tile_views.json').read_text())['tiles']
    native=json.loads((ROOT/'mvs_points_partition.json').read_text())['per_tile_view_counts']
    train=set(json.loads((O/'image_split.json').read_text())['train'])
    geo=ROOT/'patch_geometry';geo.mkdir(exist_ok=True)
    for tile in tiles:
        tid=tile['id'];meshdir=ROOT/'prior_tiles'/tid
        faces=json.loads((meshdir/'lod2_surfaces.json').read_text())['surfaces'];tab={f['ext']:f for f in faces}
        lm=dict(np.load(meshdir/'lod2_mesh.npz'))
        views=sorted(set(projected[tid]['projected_candidates'])|{n for n,c in native[tid].items() if c>=100})
        assert set(views)<=train
        for prior in ['LoD2','ALS']:
            dest=geo/f'{tid}_{prior}.npz'
            if dest.exists() and (prior=='LoD2' or (ROOT/'points'/tid/'als_xyz.npy').exists()):continue
            t0=time.monotonic();rd=ROOT/'registration'/tid/prior;rd.mkdir(parents=True,exist_ok=True)
            if (rd/'summary.json').exists():
                info=json.loads((rd/'summary.json').read_text());shift=np.array(info['registration']['shift_applied'])
                st0=PR.locs.load_store(meshdir/('lod2_store.npz' if prior=='LoD2' else 'als_store.npz'))
                st=PR.locs.move_store(st0,shift)
            else:
                PR.RNG=np.random.default_rng(0)
                pr,reg,times=PR.run(tid,prior,views,O/'mvs/full',meshdir,rd)
                shift=pr.shift.copy();st0=pr.store;st=PR.locs.move_store(st0,shift)
                dump(rd/'summary.json',clean(dict(registration=reg,views=views,timings=times,scientific_verdict=None)))
                del pr
            raw=st0['loc_center'];c=st['loc_center']
            x0,y0,x1,y1=tile['core_global']
            core=(raw[:,0]+690953.>=x0)&(raw[:,0]+690953.<x1)&(raw[:,1]+5336071.>=y0)&(raw[:,1]+5336071.<y1)
            ix=np.floor((raw[:,0]+690953.-e0)/res).astype(np.int64);iy=np.floor((raw[:,1]+5336071.-n0)/res).astype(np.int64)
            ing=(ix>=0)&(ix<nx)&(iy>=0)&(iy<ny);ids=np.flatnonzero(ing)
            ins=np.zeros(len(raw),bool);ins[ids]=mask[iy[ids],ix[ids]]
            choose=np.flatnonzero(core&ins)
            # Do not fit a per-patch quantity until both source partitions are locked.
            c=c[choose];normal=np.cross(st['loc_t1'][choose],st['loc_t2'][choose]);normal/=np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1e-12)
            normal*=np.where(normal[:,2:3]<0,-1.,1.)
            ext=st['surf_ext'][st['loc_surface'][choose]].astype(np.int64)
            kind=st['loc_kind'][choose];area=st['loc_area'][choose]
            assigned=np.full(len(c),'',dtype='<U96');face_ext=np.full(len(c),-1,np.int64)
            flipped=[]
            if prior=='LoD2':
                assigned=np.array([tab[int(e)]['building'] for e in ext],dtype='<U96');face_ext=ext.copy()
                wall=kind==2
                if wall.any():normal[wall]=np.array([tab[int(e)]['normal'] for e in ext[wall]])
                hz=normal[:,:2]/np.maximum(np.linalg.norm(normal[:,:2],axis=1,keepdims=True),1e-12)
                for e in np.unique(ext[wall]):
                    ixw=np.flatnonzero(wall&(ext==e));b=tab[int(e)]['building']
                    po=c[ixw,:2]+.5*hz[ixw];pi=c[ixw,:2]-.5*hz[ixw]
                    ino=np.zeros(len(ixw),bool);ini=np.zeros(len(ixw),bool)
                    for p in blds[b]['surfaces']['ground']:
                        ring=np.array(p['ext'])[:,:2]-[690953.,5336071.];path=MPath(ring)
                        ino|=path.contains_points(po);ini|=path.contains_points(pi)
                    if int((ino&~ini).sum())>int((~ino&ini).sum()):normal[ixw]*=-1.;flipped.append(int(e))
            roof=np.abs(normal[:,2])>=np.cos(np.deg2rad(45.))
            assert np.isfinite(c).all() and np.isfinite(normal).all()
            assert np.allclose(np.linalg.norm(normal,axis=1),1.,atol=1e-6)
            assert np.isfinite(area).all() and np.all(area>=0)
            if prior=='ALS':
                face_index,ordered=attach(c,roof,faces,lm)
                valid=face_index>=0
                assigned[valid]=[ordered[i]['building'] for i in face_index[valid]]
                face_ext[valid]=[ordered[i]['ext'] for i in face_index[valid]]
            included=np.array([b in selected for b in assigned],dtype=bool);unmatched=assigned==''
            np.savez_compressed(dest,centre=c[included],normal=normal[included],roof_like=roof[included],
                tangent1=st['loc_t1'][choose][included],tangent2=st['loc_t2'][choose][included],
                surf=ext[included],face_ext=face_ext[included],kind=kind[included],area=area[included],
                building=assigned[included],roof_type=np.array([blds[b].get('roofType') or '' for b in assigned[included]],dtype='<U40'),
                holdout=np.array([b in held for b in assigned[included]],dtype=bool),raw_centre=raw[choose][included],
                source_patch=choose[included],tau=np.full(int(included.sum()),cfg['tau_m'][prior]),
                patch_id=np.array([f'{prior}:{tid}:{int(i)}' for i in choose[included]],dtype='<U80'),frame_shift=shift)
            dump(dest.with_suffix('.json'),dict(tile=tid,prior=prior,unmatched_count=int(unmatched.sum()),unmatched_area_m2=float(area[unmatched].sum()),
                matched_outside_scope_buildings_count=int((~included&~unmatched).sum()),matched_outside_scope_buildings_area_m2=float(area[~included&~unmatched].sum()),
                included_count=int(included.sum()),included_area_m2=float(area[included].sum()),flipped_wall_faces=flipped,
                ownership='unregistered centre in frozen core and common XY support; registered geometry retained',
                config_sha256=sha('/cfg/widen0_v2.json'),seconds=time.monotonic()-t0,scientific_verdict=None))
            if prior=='ALS':
                pp=ROOT/'points'/tid;pts=np.memmap(O/'inputs/points'/tid/'als.bin',mode='r',dtype=DT)
                X=np.column_stack([pts[k] for k in ['x','y','z']])+shift
                np.save(pp/'als_xyz.npy',X)
            print('registered geometry ready',tid,prior,flush=True)
            del st,st0

if __name__=='__main__':main()
