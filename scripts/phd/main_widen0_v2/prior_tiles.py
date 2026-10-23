"""Inherited LoD2 and ALS prior meshes; no method decisions or region codes.

Patch stores may contain sealed buildings, so all temporary stores live under
holdout/internal until partitioned by the already-frozen building assignment.
"""
import json
from pathlib import Path
import time
import numpy as np
import common
import prior_mesh as PM
from tile_points import DT
from preflight import dump, sha

O=Path('/out')

def main():
    from scope_split import parse_buildings
    t0=time.monotonic();tiles=json.loads((O/'inputs/tiles.json').read_text())
    sc=json.loads((O/'scope_split.json').read_text());g=sc['grid']
    ctx=O/'inputs/lod2_context_buildings.json'
    if not ctx.exists():
        bs,_=parse_buildings([g['e0'],g['n0'],g['e1'],g['n1']]);dump(ctx,list(bs.values()))
    blds=json.loads(ctx.read_text())
    PM.CFG['ranges']['prior_margin_m']=0.
    root=O/'holdout/internal/prior_tiles';root.mkdir(parents=True,exist_ok=True)
    for tile in tiles:
        tid=tile['id'];d=root/tid;d.mkdir(exist_ok=True)
        if (d/'receipt.json').exists():continue
        start=time.monotonic()
        x0,y0,x1,y1=tile['buffer_global']
        rng=dict(id=tid,kind='xy_rect',xy_rect_local=[x0-690953.,y0-5336071.,x1-690953.,y1-5336071.])
        rect=np.array(rng['xy_rect_local']).reshape(2,2)
        m,tab,cuts,caps=PM.lod2_mesh(rng,blds)
        np.savez_compressed(d/'lod2_mesh.npz',**m)
        srf=[dict(ext=r['ext'],normal=r['normal'],o=r['o']) for r in tab]
        st=PM.locs.build_plane_store(m['V'],m['F'],m['tri_surface'],srf,rect,.25)
        PM.locs.save_store(d/'lod2_store.npz',st)
        dump(d/'lod2_surfaces.json',dict(surfaces=tab,party_wall=cuts,caps=caps))
        n_lod=len(st['loc_area']);del st,m
        pts=np.memmap(O/'inputs/points'/tid/'als.bin',mode='r',dtype=DT)
        def read_tile_als(lo,hi,classes=(2,6)):
            P=np.column_stack([pts[k] for k in ['x','y','z']])
            valid=(P[:,0]>=lo[0])&(P[:,0]<=hi[0])&(P[:,1]>=lo[1])&(P[:,1]<=hi[1])
            if classes is not None:valid&=np.isin(pts['cls'],classes)
            return P[valid],pts['cls'][valid],pts['multi'][valid].astype(bool)
        PM.read_als=read_tile_als
        m,tab,_=PM.als_mesh(rng)
        np.savez_compressed(d/'als_mesh.npz',**m)
        st=PM.locs.build_tin_store(m['V'],m['F'],m['tri_surface'],m['tri_normal'],m['tri_area'],
            [dict(ext=r['ext']) for r in tab],rect,.25)
        PM.locs.save_store(d/'als_store.npz',st)
        dump(d/'als_surfaces.json',dict(surfaces=tab))
        dump(d/'range.json',rng)
        # No per-tile totals are published: tile aggregates can reveal holdout outcomes later.
        dump(d/'receipt.json',dict(tile=tid,lod2_context_patches=n_lod,als_context_patches=len(st['loc_area']),
            seconds=time.monotonic()-start,config_sha256=sha('/cfg/widen0_v2.json'),scientific_verdict=None,
            source_code=dict(prior_mesh=sha('/repo/scripts/phd/main_prep_discard_rule_v1/s02_meshes.py'),
                note='copied unchanged; only read_als adapter supplies the same raw points from bounded tile files')))
        del st,m,pts
        print('prior input tile complete',tid,flush=True)
    print('all prior input tiles complete',len(tiles),'seconds',time.monotonic()-t0,flush=True)

if __name__=='__main__':main()
