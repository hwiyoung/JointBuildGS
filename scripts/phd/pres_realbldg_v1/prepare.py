"""Reuse saved cases and exact RECOUNT ownership; create task-local arrays only."""
from common import *
from shapely.geometry import Polygon,shape,mapping
from shapely.ops import unary_union
from shapely import affinity

def polygons(records,key):
    return unary_union([Polygon(np.asarray(p['ext'])[:,:2]-SHIFT[:2], [np.asarray(h)[:,:2]-SHIFT[:2] for h in p['holes'] if len(h)>3]).buffer(0) for p in records['surfaces'][key]])

def structures():
    raw=json.loads((W/'inputs/lod2_buildings.json').read_text())
    split={x['building']:x for x in json.loads((W/'building_split.json').read_text())['rows']}
    regions=json.loads((W/'scope_split.json').read_text())['regions']
    out={}
    for b in raw:
        bid=b['id'];fp=polygons(b,'ground');roof=polygons(b,'roof')
        if fp.area<100:continue
        rings=[np.asarray(p.exterior.coords) for p in getattr(roof,'geoms',[roof]) if p.geom_type=='Polygon']
        edges=[]
        for p in b['surfaces']['roof']:
            q=np.asarray(p['ext'],float)-SHIFT;q[:,2]+=45.7
            edges.extend(np.stack([q[:-1],q[1:]],1).tolist())
        rect=np.asarray(fp.minimum_rotated_rectangle.exterior.coords);lens=np.linalg.norm(np.diff(rect,axis=0),axis=1)
        cov={site:fp.intersection(affinity.translate(shape(regions[site]),-SHIFT[0],-SHIFT[1])).area/fp.area for site in cfg()['sites']}
        out[bid]=dict(building=bid,split=split[bid]['split'],footprint=mapping(fp),roof=mapping(roof),rings=[p.tolist() for p in rings],roof_edges=edges,
            footprint_m2=fp.area,long_m=float(lens.max()),short_m=float(lens.min()),coverage=cov,experiment=any(x>0 for x in cov.values()))
    dump(O/'buildings.json',out)
    return out

def grid_area(d):
    # One occupied cell per case/surface kind. Wall cells are projected onto
    # their inherited plane; the stable first reference row resolves overlap.
    P=d['xyz'];q=np.floor(P[:,:2]/.25).astype('i8');face=np.zeros(len(P),'i8')
    projection_face=d.get('projection_face',d['surf'])
    for f in np.unique(projection_face[d['kind']==2]):
        m=(d['kind']==2)&(projection_face==f);ii=np.flatnonzero(m)[0]
        q[m]=np.floor(np.c_[P[m]@d['t1'][ii],P[m]@d['t2'][ii]]/.25).astype('i8');face[m]=f+1
    key=np.c_[d['case'],d['kind'],face,q]
    _,ix=np.unique(key,axis=0,return_index=True);a=np.zeros(len(P));a[ix]=.0625
    d['area']=a;d['grid_key']=key
    return d

def unassigned_wall_frame(d,core,site):
    """Geometric projection only; never assign an unowned point to a building."""
    ix=np.flatnonzero((d['owner']<0)&(d['kind']==2));d['projection_face']=d['surf'].copy()
    if not len(ix):return d
    import open3d as o3d
    mesh=loadz(DR/'s02_box'/site/'lod2_mesh.npz');shift=loadz(S1/'defs'/site/'prior_LoD2.npz',['shift'])['shift']
    faces=json.loads((DR/'s02_box'/site/'lod2_surfaces.json').read_text())['surfaces'];walls=[f['ext'] for f in faces if f['kind']==2]
    take=np.isin(mesh['tri_surface'],walls);F=mesh['F'][take];surface=mesh['tri_surface'][take]
    scene=o3d.t.geometry.RaycastingScene(nthreads=4);scene.add_triangles(o3d.core.Tensor((mesh['V']+shift).astype('f4')),o3d.core.Tensor(F.astype('u4')))
    hits=scene.compute_closest_points(o3d.core.Tensor(d['xyz'][ix].astype('f4')))['primitive_ids'].numpy();sf=surface[hits]
    for f in np.unique(sf):
        ii=ix[sf==f];matches=np.flatnonzero((core['kind']==2)&(core['surf']==f));assert len(matches),'nearest wall lacks inherited tangent frame'
        j=matches[0];d['t1'][ii]=core['tangent1'][j];d['t2'][ii]=core['tangent2'][j];d['normal'][ii]=core['normal'][j]
        d['projection_face'][ii]=-1000000-int(f)
    return d

def experiment(site,prior,buildings):
    stem=f'{site}__{prior}';out=O/'data'/f'{stem}.npz'
    if out.exists():return
    root=G/'scenes'/stem;rp=root/'rows.npz';cp=root/'stage1_cells.npz'
    row=loadz(rp);cell=loadz(cp);core=loadz(JA/'core_points'/f'{stem}.npz')
    # Same join as RECOUNT: row_owner indexes the exact JA patch ordering.
    assert np.array_equal(row['row_owner'],cell['row_owner'])
    ft=loadz(FT/'targets'/f'{stem}.npz',['patch_id']);assert np.array_equal(ft['patch_id'][core['source_index']],core['patch_id'])
    owner=row['row_owner'];good=owner>=0;safe=np.maximum(owner,0)
    d=dict(xyz=row['xyz'],case=cell['case_id'],kind=row['row_kind'],building=core['building'][safe].copy(),surf=core['surf'][safe].copy(),
        normal=core['normal'][safe],t1=core['tangent1'][safe],t2=core['tangent2'][safe],owner=owner,prior_s=loadz(root/'distances/prior.npz',['row_s'])['row_s'],tau=row['row_tau_m'])
    d['building'][~good]='';d['surf'][~good]=-1
    d=grid_area(unassigned_wall_frame(d,core,site))
    d['texture']=np.full(len(owner),-1,'i1');d['texture_seen']=np.zeros(len(owner),'i4')
    f=root/'preservation_features.npz'
    if f.exists():
        v=loadz(f);valid=v['preservation']&(v['near_nadir_views']>0);d['texture'][valid]=v['textureless'][valid].astype('i1');d['texture_seen'][valid]=v['near_nadir_views'][valid]
    savez(out,**d)
    keys=['centre','normal','tangent1','tangent2','surf','kind','area','building','patch_id','prior_height_m']
    savez(O/'patches'/f'{stem}.npz',**{k:core[k] for k in keys})
    meta=dict(site=site,prior=prior,unit='reference',case_source='GTJUDGE stage1 '+json.loads((G/'targets_gt'/f'{stem}.json').read_text())['case_basis'],sources=[source(p) for p in [rp,cp,JA/'core_points'/f'{stem}.npz',root/'distances/prior.npz']],shift=loadz(S1/'defs'/site/'prior_LoD2.npz',['shift'])['shift'].tolist(),scientific_verdict=None)
    dump(out.with_suffix('.json'),meta)
    rows=[]
    for cc in np.unique(d['case']):
        m=d['case']==cc;total=float(d['area'][m].sum());assigned=float(d['area'][m&(d['building']!='')].sum());unassigned=float(d['area'][m&(d['building']=='')].sum())
        assert total==assigned+unassigned
        rows.append(dict(scene=stem,case=int(cc),scene_area_m2=total,assigned_building_area_m2=assigned,unassigned_area_m2=unassigned,difference_m2=total-assigned-unassigned,reference_rows=int(m.sum())))
    table('reconciliation_'+stem,rows);print('PREPARED',stem,len(owner),flush=True)

def outside(prior,buildings):
    out=O/'data'/f'outside__{prior}.npz'
    if out.exists():return
    parts=[];sources=[];jcparts={}
    for p in sorted((JC/'r2/core_points').glob(f'*__{prior}__*.npz')):
        z=loadz(p,['patch_id','cell']);jcparts.setdefault(p.stem.split('__')[0],[]).append(z);sources.append(source(p))
    keys=['centre','normal','tangent1','tangent2','surf','kind','area','building','patch_id','gt_p','gt_status','gt_n_inner','tau','cell']
    for split,folder in [('development',W/'patch_values'),('holdout',W/'holdout/patch_values')]:
        for p in sorted(folder.glob(f'*__{prior}__R1.5.npz')):
            z=loadz(p,keys);sources.append(source(p));n=len(z['cell'])
            if not n:continue
            tile=p.stem.split('__')[0];z['tile']=np.full(n,tile);z['split']=np.full(n,split);z['case_source']=np.full(n,'WIDEN0-v2','U20')
            if split=='development' and tile in jcparts:
                ids=np.concatenate([x['patch_id'] for x in jcparts[tile]]);lab=np.concatenate([x['cell'] for x in jcparts[tile]]);order=np.argsort(ids);q=np.searchsorted(ids[order],z['patch_id']);valid=q<len(ids);valid[valid]&=ids[order[q[valid]]]==z['patch_id'][valid]
                z['cell'][valid]=lab[order[q[valid]]];z['case_source'][valid]='JUDGECHECK-v1'
            # Retain every building and unassigned patch for location diagnostics.
            z['case']=z.pop('cell').copy();z['case'][z['case']==5]=3;z['case'][np.isin(z['case'],[6,9])]=-1
            z['xyz']=z.pop('centre');z['t1']=z.pop('tangent1');z['t2']=z.pop('tangent2');z['prior_s']=-z['gt_p'];z['texture']=np.full(n,-1,'i1');z['texture_seen']=np.zeros(n,'i4')
            parts.append(z)
    d={k:np.concatenate([z[k] for z in parts]) for k in parts[0]};savez(out,**d)
    dump(out.with_suffix('.json'),dict(site='outside',prior=prior,unit='patch',case_source='JUDGECHECK-v1 development where exact patch ID matches; otherwise WIDEN0-v2',sources=sources,scientific_verdict=None))
    print('PREPARED','outside',prior,len(d['case']),flush=True)

def main():
    first_calculation();b=structures()
    for site in cfg()['sites']:
        for prior in cfg()['priors']:experiment(site,prior,b)
    for prior in cfg()['priors']:outside(prior,b)
    issue('지역 밖 저장 칸 5는 사전 정보가 틀리고 영상이 없는 경우로, GTJUDGE의 다섯 경우에 맞춰 둘 다 틀림에 합쳤다. 칸 6·9는 확인 불가로 남겼다. 기존 칸 값은 바꾸지 않았다.')
if __name__=='__main__':main()
