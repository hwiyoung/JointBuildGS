"""Whole-source coverage and outcome-blind building split. CPU only.

Never loads prior-minus-GT, uncertainties, historical cells or patch results.
"""
import collections
import datetime as dt
import hashlib
import json
import math
import re
import time
import zipfile
from pathlib import Path

import laspy
from lxml import etree
import numpy as np
from scipy.ndimage import distance_transform_edt
from shapely.geometry import Polygon, box, mapping
from shapely.ops import unary_union

from preflight import images, sha, dump, PH, PREP, DENSE

OUT, DOC, REPO = Path('/out'), Path('/docs'), Path('/repo')
CFG = json.loads(Path('/cfg/widen0_v2.json').read_text())
LOCK = json.loads(Path('/cfg/widen0_v2.lock.json').read_text())
assert sha('/cfg/widen0_v2.json') == LOCK['config_sha256']
RAW = Path('/art/phase-payloads/p0-audit/data/raw')
SHIFT = np.array(CFG['frame']['world_shift_xyz_m'])
NS = dict(gml='http://www.opengis.net/gml', bldg='http://www.opengis.net/citygml/building/1.0')
G, B = '{'+NS['gml']+'}', '{'+NS['bldg']+'}'

def stamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def ring(el):
    p = el.find('.//gml:posList', NS)
    if p is None or not p.text:
        return []
    dim = int(p.get('srsDimension', '3'))
    return np.fromstring(p.text, sep=' ').reshape(-1, dim).tolist()

def parse_buildings(bounds):
    broad = box(*bounds).buffer(20.)
    result, counts = {}, {}
    for p in sorted((RAW/'lod2').glob('*.gml')):
        n = kept = 0
        for _, el in etree.iterparse(str(p), events=('end',), tag=B+'Building', huge_tree=True):
            n += 1
            surfaces = {'roof': [], 'wall': [], 'ground': []}
            for typ, key in [('GroundSurface','ground'), ('RoofSurface','roof'), ('WallSurface','wall')]:
                for sf in el.iter(B+typ):
                    for poly in sf.iter(G+'Polygon'):
                        exterior = poly.find('gml:exterior', NS)
                        ext = ring(exterior) if exterior is not None else []
                        if len(ext) >= 4:
                            surfaces[key].append(dict(id=poly.get(G+'id') or sf.get(G+'id'), ext=ext,
                                holes=[ring(h) for h in poly.findall('gml:interior', NS)]))
            gps = [Polygon(np.array(q['ext'])[:,:2], [np.array(h)[:,:2] for h in q['holes'] if len(h)>=4]).buffer(0)
                   for q in surfaces['ground']]
            footprint = unary_union(gps) if gps else None
            if footprint is not None and not footprint.is_empty and footprint.intersects(broad):
                bid = el.get(G+'id')
                rt = el.find('bldg:roofType', NS)
                parts = sorted({q.text for bp in el.iter(B+'BuildingPart') for q in bp.findall('bldg:roofType',NS) if q.text})
                code = rt.text if rt is not None else (parts[0] if len(parts)==1 else ('부분마다 다름' if parts else None))
                rec = dict(id=bid, source=str(p), roofType=code, surfaces=surfaces,
                           footprint_area_m2=footprint.area, bbox=list(footprint.bounds))
                if bid in result:
                    if result[bid]['surfaces'] != surfaces:
                        raise ValueError('conflicting duplicate LoD2 building '+bid)
                else:
                    result[bid] = rec
                    kept += 1
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]
        counts[p.name] = dict(buildings=n, retained_near_nadir_bounds=kept, sha256=sha(p))
        print('CityGML', p.name, counts[p.name], flush=True)
    return result, counts

def polygon_from_mask(mask, e0, n0, res):
    # Union row runs avoids adding a geometric hull over unobserved holes.
    pieces = []
    for y, row in enumerate(mask):
        jumps = np.diff(np.r_[False, row, False].astype(np.int8))
        for a, b in zip(np.flatnonzero(jumps==1), np.flatnonzero(jumps==-1)):
            pieces.append(box(e0+a*res, n0+y*res, e0+b*res, n0+(y+1)*res))
    return unary_union(pieces)

def main():
    t0 = time.monotonic()
    if (OUT/'building_split.lock.json').exists():
        raise SystemExit('Split already frozen; refusing replacement.')
    nadir = RAW/'tum2twin/TUM_Downtown_ULS_20241217_nadir.laz'
    with laspy.open(nadir) as f:
        header = dict(points=f.header.point_count, mins=f.header.mins.tolist(), maxs=f.header.maxs.tolist())
    res=CFG['scope']['coverage_grid_m']
    e0,n0=np.floor(np.array(header['mins'][:2])/res)*res
    e1,n1=(np.floor(np.array(header['maxs'][:2])/res)+1)*res
    nx,ny=int(round((e1-e0)/res)),int(round((n1-n0)/res))
    counts={k:np.zeros((ny,nx),np.uint32) for k in ['uls','als','mvs']}
    ground_sum=np.zeros((ny,nx),float);ground_n=np.zeros((ny,nx),np.uint32)
    def add(k,x,y):
        ix=np.floor((x-e0)/res).astype(np.int64); iy=np.floor((y-n0)/res).astype(np.int64)
        ok=(ix>=0)&(ix<nx)&(iy>=0)&(iy<ny)
        b=np.bincount(iy[ok]*nx+ix[ok],minlength=nx*ny).reshape(ny,nx)
        counts[k] += b.astype(np.uint32)
        return int(ok.sum())
    rawcounts={}
    for k, files in [('uls',[nadir]),('als', sorted((RAW/'als').glob('*.laz')))]:
        for p in files:
            kept=total=0
            with laspy.open(p) as f:
                for pts in f.chunk_iterator(1_000_000):
                    x=np.asarray(pts.x); y=np.asarray(pts.y)
                    total+=len(x)
                    if k=='als':
                        ee,nn=[int(v)*1000 for v in p.stem.split('_')]
                        m=(x>=ee)&(x<ee+1000)&(y>=nn)&(y<nn+1000)
                        g=m&(np.asarray(pts.classification)==2)&(x>=e0)&(x<e1)&(y>=n0)&(y<n1)
                        gx=np.floor((x[g]-e0)/res).astype(np.int64);gy=np.floor((y[g]-n0)/res).astype(np.int64)
                        flat=gy*nx+gx
                        ground_sum[:]+=np.bincount(flat,weights=np.asarray(pts.z)[g]+45.7,minlength=nx*ny).reshape(ny,nx)
                        ground_n[:]+=np.bincount(flat,minlength=nx*ny).reshape(ny,nx).astype(np.uint32)
                        x,y=x[m],y[m]
                    kept+=add(k,x,y)
            rawcounts[str(p)]=dict(points=total, points_in_nadir_bbox=kept, sha256=sha(p))
            print('coverage',k,p.name,total,kept,flush=True)
    fused=Path('/art/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply')
    with fused.open('rb') as f:
        hdr=b''
        while not hdr.endswith(b'end_header\n'):
            line=f.readline()
            if not line: raise ValueError('PLY header missing end')
            hdr+=line
    assert b'format binary_little_endian 1.0' in hdr
    props=[s for s in hdr.decode().splitlines() if s.startswith('property')]
    normalized=[s.replace('float32','float').replace('uint8','uchar') for s in props]
    assert normalized==['property float x','property float y','property float z','property uchar red','property uchar green','property uchar blue'],props
    n=int(next(s.split()[-1] for s in hdr.decode().splitlines() if s.startswith('element vertex')))
    dtype=np.dtype([('x','<f4'),('y','<f4'),('z','<f4'),('r','u1'),('g','u1'),('b','u1')])
    mm=np.memmap(fused,mode='r',offset=len(hdr),dtype=dtype,shape=(n,))
    total=0
    for b in range(0,n,1_000_000):
        a=mm[b:b+1_000_000]
        m=np.isfinite(a['x'])&np.isfinite(a['y'])&np.isfinite(a['z'])
        total+=add('mvs',a['x'][m].astype(float)+SHIFT[0],a['y'][m].astype(float)+SHIFT[1])
    rawcounts[str(fused)]=dict(points=n,points_in_nadir_bbox=total,sha256=sha(fused))
    blds,gml_counts=parse_buildings([e0,n0,e1,n1])
    assert (ground_n>0).any()
    ground=ground_sum/np.maximum(ground_n,1)
    nearest=distance_transform_edt(ground_n==0,return_distances=False,return_indices=True)
    ground[ground_n==0]=ground[tuple(nearest[:,ground_n==0])]
    del nearest
    cx,cy=np.meshgrid(e0+(np.arange(nx)+.5)*res,n0+(np.arange(ny)+.5)*res)
    xyz=np.column_stack([cx.ravel(),cy.ravel(),ground.ravel()])-SHIFT
    del cx,cy
    with (DENSE/'sparse/cameras.bin').open('rb') as f:
        import struct
        nc,=struct.unpack('<Q',f.read(8));assert nc==1
        cid,model,iw,ih=struct.unpack('<iiQQ',f.read(24));assert model==1
        fx,fy,px,py=struct.unpack('<4d',f.read(32))
    views=images(DENSE/'sparse/images.bin');photo=np.zeros(nx*ny,bool);view_coverage={}
    for name,v in sorted(views.items()):
        w,x,y,z=v['q']
        R=np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                    [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                    [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])
        q=xyz@R.T+v['t'];pos=q[:,2]>1e-6
        zz=np.where(pos,q[:,2],1.)
        u=fx*q[:,0]/zz+px;vv=fy*q[:,1]/zz+py
        seen=pos&(u>=0)&(u<iw)&(vv>=0)&(vv<ih)
        photo|=seen
        view_coverage[name]=int((seen&(counts['uls'].ravel()>0)&(counts['als'].ravel()>0)).sum())
    photo=photo.reshape(ny,nx)
    common=(counts['uls']>0)&(counts['als']>0)&photo
    dump(OUT/'inputs/view_ground_coverage.json',view_coverage)
    common_poly=polygon_from_mask(common,e0,n0,res)
    ranges=json.loads((PREP/'step01/ranges.json').read_text())
    boxes=json.loads((PREP/'step06/box_ranges.json').read_text())
    a=np.deg2rad(70.); basis=np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]])
    forced_polys=[]; region_records={}
    for name in CFG['scope']['exploration_regions']:
        p=Polygon(ranges[name]['polygon_epsg25832']);forced_polys.append(p)
        region_records[name]=mapping(p)
    for name in CFG['scope']['evaluation_regions']:
        q=boxes[name];u0,u1=q['eval_u'];v0,v1=q['eval_v']
        pts=np.array([[u0,v0],[u1,v0],[u1,v1],[u0,v1]])@basis+SHIFT[:2]
        p=Polygon(pts);forced_polys.append(p);region_records[name]=mapping(p)
    forced_domain=unary_union(forced_polys)
    selected={};forced=[];other=[];geoms={}
    for bid,b in sorted(blds.items()):
        fp=unary_union([Polygon(np.array(q['ext'])[:,:2],[np.array(h)[:,:2] for h in q['holes'] if len(h)>=4]).buffer(0) for q in b['surfaces']['ground']])
        inside=fp.intersection(common_poly)
        if inside.area<=0:continue
        selected[bid]=b;geoms[bid]=fp
        b['common_footprint_area_m2']=inside.area
        (forced if fp.intersects(forced_domain) else other).append(bid)
    nh=int(math.floor(len(other)*0.3))
    rng=np.random.default_rng(CFG['split']['seed'])
    holdout=sorted(rng.choice(other,nh,replace=False).tolist()) if nh else []
    held=set(holdout);dev=sorted(set(selected)-held)
    building_rows=[dict(building=bid,split='holdout' if bid in held else 'development',
        forced_development=bid in forced, footprint_area_m2=b['footprint_area_m2'],
        common_footprint_area_m2=b['common_footprint_area_m2']) for bid,b in selected.items()]
    dump(OUT/'inputs/lod2_buildings.json',list(selected.values()))
    dump(OUT/'building_split.json',dict(rows=building_rows,forced_development=forced,other_sorted=other,
        development=dev,holdout=holdout,scientific_verdict=None))
    splitlock=dict(made=stamp(),config_sha256=LOCK['config_sha256'],split_sha256=sha(OUT/'building_split.json'),
        before_patch_outcomes=True,scientific_verdict=None)
    dump(OUT/'building_split.lock.json',splitlock)
    np.savez_compressed(OUT/'inputs/coverage.npz',**counts,photo=photo,ground=ground,ground_n=ground_n,common=common,e0=e0,n0=n0,res=res)
    dump(OUT/'inputs/scope.geojson',dict(type='FeatureCollection',features=[dict(type='Feature',properties=dict(id='common'),geometry=mapping(common_poly))]))
    tiles=[]
    for tx in range(int(e0//100),int(e1//100)+1):
        for ty in range(int(n0//100),int(n1//100)+1):
            core=box(tx*100,ty*100,(tx+1)*100,(ty+1)*100)
            if core.intersection(common_poly).area>0:
                tiles.append(dict(id=f'{tx}_{ty}',core_global=list(core.bounds),buffer_global=list(core.buffer(10).bounds)))
    dump(OUT/'inputs/tiles.json',tiles)
    summary=dict(task_id=CFG['task_id'],scientific_verdict=None,made=stamp(),config_sha256=LOCK['config_sha256'],
        scope_area_m2=float(common.sum()*res*res),grid=dict(e0=e0,n0=n0,e1=e1,n1=n1,res_m=res,nx=nx,ny=ny),
        coverage_area_inside_nadir_bbox_m2={k:float((v>0).sum()*res*res) for k,v in counts.items()},
        photographic_coverage_area_inside_nadir_bbox_m2=float(photo.sum()*res*res),
        common_without_existing_MVS_m2=float((common&(counts['mvs']==0)).sum()*res*res),
        note='Photo coverage uses camera projection of ALS terrain and does not require MVS. Old 937-image MVS is inventory only. Scope is rebuilt from full nadir extent, not the old survey crop.',
        buildings=len(selected),forced_development_buildings=len(forced),random_pool_buildings=len(other),
        development=dict(buildings=len(dev),common_footprint_area_m2=sum(selected[b]['common_footprint_area_m2'] for b in dev)),
        holdout=dict(buildings=len(held),common_footprint_area_m2=sum(selected[b]['common_footprint_area_m2'] for b in held)),
        building_split_lock=splitlock,raw_sources=rawcounts,gml_sources=gml_counts,tiles=len(tiles),regions=region_records,
        seconds=time.monotonic()-t0)
    dump(DOC/'tables/scope_split.json',summary)
    dump(OUT/'scope_split.json',summary)
    print(json.dumps({k:summary[k] for k in ['scope_area_m2','buildings','forced_development_buildings','random_pool_buildings','development','holdout','tiles','seconds']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
