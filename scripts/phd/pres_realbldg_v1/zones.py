"""LoD2 eaves, exact planar distances, and immutable region descriptors."""
from common import *
from shapely.geometry import shape
from shapely.vectorized import contains

def nearest(P,edges):
    P=np.asarray(P);edges=np.asarray(edges);dist=np.full(len(P),np.inf);which=np.zeros(len(P),'i4');alpha=np.zeros(len(P))
    for i,(a,b) in enumerate(edges):
        v=b[:2]-a[:2];den=v@v
        if den<1e-15:continue
        t=np.clip((P[:,:2]-a[:2])@v/den,0,1);dd=np.linalg.norm(P[:,:2]-(a[:2]+t[:,None]*v),axis=1);m=dd<dist
        dist[m]=dd[m];which[m]=i;alpha[m]=t[m]
    return dist,which,alpha

def eaves(b,shift=(0,0,0)):
    all_edges=[];length=[];ringid=[];offset=[];zsource=np.asarray(b['roof_edges'])
    for ri,ring in enumerate(b['rings']):
        q=np.asarray(ring);_,ii,tt=nearest(np.c_[q,np.zeros(len(q))],zsource)
        z=zsource[ii,0,2]*(1-tt)+zsource[ii,1,2]*tt
        q=np.c_[q,z]+shift;ed=np.stack([q[:-1],q[1:]],1);ll=np.linalg.norm(np.diff(q[:,:2],axis=0),axis=1)
        all_edges.extend(ed);length.extend(ll);ringid.extend([ri]*len(ll));offset.extend(np.r_[0,np.cumsum(ll)[:-1]])
    return np.asarray(all_edges),np.asarray(length),np.asarray(ringid),np.asarray(offset)

def main(stem):
    cfg();src=O/'data'/f'{stem}.npz';out=O/'zones'/src.name
    if out.exists():return
    d=loadz(src,['xyz','kind','building','surf','case']+(['tile'] if stem.startswith('outside') else []));meta=json.loads(src.with_suffix('.json').read_text());blds=json.loads((O/'buildings.json').read_text());n=len(d['xyz'])
    inside=np.zeros(n,bool);distance=np.full(n,np.inf);ring=np.full(n,-1,'i4');s=np.full(n,np.nan);edgez=s.copy();face=np.full(n,'','U160');in_eval=np.zeros(n,bool)
    groups=[('',np.arange(n))] if meta['site']!='outside' else [(t,np.flatnonzero(d['tile']==t)) for t in np.unique(d['tile'])]
    for tile,allix in groups:
        shift=np.asarray(meta['shift']) if not tile else np.asarray(json.loads((W/'holdout/internal/registration'/tile/'LoD2/summary.json').read_text())['registration']['shift_applied'])
        sp=DR/'s02_box'/meta['site']/'lod2_surfaces.json' if not tile else W/'holdout/internal/prior_tiles'/tile/'lod2_surfaces.json'
        tab=json.loads(sp.read_text())['surfaces'];lookup={v['ext']:v.get('gml',str(v['ext'])) for v in tab}
        for sf in np.unique(d['surf'][allix]):face[allix[d['surf'][allix]==sf]]=lookup.get(int(sf),'unmatched:'+str(sf))
        for bid in np.unique(d['building'][allix]):
            if bid not in blds:continue
            ii=allix[d['building'][allix]==bid];b=blds[bid];p=d['xyz'][ii];ed,ll,rr,ss=eaves(b,shift)
            dd,j,t=nearest(p,ed);distance[ii]=dd;ring[ii]=rr[j];s[ii]=ss[j]+t*ll[j];edgez[ii]=ed[j,0,2]+t*(ed[j,1,2]-ed[j,0,2]);in_eval[ii]=b['experiment']
            q=p[:,:2]-shift[:2];inside[ii]=contains(shape(b['roof']),q[:,0],q[:,1])|(dd<1e-7)
    roof=d['kind']==1;wall=d['kind']==2;interior=roof&inside&(distance>1);inner=roof&inside&(distance<=1)
    outer=((~roof&~wall)&~inside&(distance<=1.5))|(wall&(edgez-d['xyz'][:,2]>=-1e-6)&(edgez-d['xyz'][:,2]<=3))
    savez(out,interior=interior,inner=inner,outer=outer,distance=distance,ring=ring,along=s,eave_z=edgez,face=face,in_experiment=in_eval)
    print('ZONES',stem,'interior',int(interior.sum()),'outer',int(outer.sum()),flush=True)
if __name__=='__main__':main(sys.argv[1])
