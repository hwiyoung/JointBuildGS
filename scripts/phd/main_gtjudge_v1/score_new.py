"""New diagnostic meshes, same rows/columns/tau and addendum ray/cylinder distances."""
import sys,gc
from inherited import *
from geometry_add1 import reference,rows,read_surface,MeshScene,Grid,sample_normals
from normal_line import measure
from cylinder import Cylinder
from scipy.spatial import cKDTree

def main(site,prior,family):
    cfg();stem=f'{site}__{prior}';root=O/'scenes'/stem;out=root/'distances'/f'{family}.npz'
    if out.exists():return
    mesh=O/'meshes'/(stem+'__'+family)/'final.ply';ref=reference(site);row=rows(site,prior,ref)
    V,F=read_surface(mesh);sc=MeshScene(V,F);s,offset=measure(sc,row['xyz'],row['normal'],row['wall']);del sc;gc.collect()
    P,N=sample_normals(V,F,Grid(site));del V,F;gc.collect()
    euclidean,idx=cKDTree(ref['xyz']).query(P,workers=4);rn=ref['normal'][idx].copy()
    if prior=='ALS':rn[rn[:,2]<0]*=-1
    N*=np.where((N*rn).sum(1)<0,-1.,1.)[:,None]
    wall=ref['wall'][idx] if prior=='LoD2' else np.zeros(len(P),bool)
    eligible=euclidean<=1;qs=np.full(len(P),np.nan);cy=Cylinder(ref['xyz'])
    qs[eligible],_=cy.query(P[eligible],N[eligible],np.where(wall[eligible],5.,10.),float(ref['radius']));cy.close()
    core=loadz(JA/'core_points'/f'{stem}.npz');owner,hits=module('geometry').columns(P,core,root/'new_columns'/family)
    good=row['row_owner']>=0;rr=np.flatnonzero(good);tree=cKDTree(np.c_[row['row_owner'][good].astype(float)*100000.,row['xyz'][good]])
    assigned=np.full(len(P),-1,'i8')
    for begin in range(0,len(P),200000):
        take=np.arange(begin,min(begin+200000,len(P)));take=take[owner[take]>=0]
        ii=rr[tree.query(np.c_[owner[take].astype(float)*100000.,P[take]],workers=4)[1]]
        same=row['row_owner'][ii]==owner[take];assigned[take[same]]=ii[same]
    with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:
        tau=next(x for x in csv.DictReader(f) if x['site']==site and x['prior']==prior)
    qt=np.where(wall,float(tau['wall_tau_m']),float(tau['roof_tau_m']))
    savez(out,row_s=s,row_offset=offset,sample_s=qs,sample_eligible=eligible,sample_reference_row=assigned,sample_tau=qt)
    savez(root/'distances'/f'{family}_samples.npz',xyz=P.astype('f4'),normal=N.astype('f4'),owner=owner)
    dump(out.with_suffix('.json'),dict(at=now(),site=site,prior=prior,method=family,mesh=str(mesh),mesh_sha256=sha(mesh),
        radius_m=float(ref['radius']),accuracy_ALS_all_nonwall=prior=='ALS',samples=len(P),reference_rows=len(s),
        excluded_no_reference_1m=int((~eligible).sum()),sample_density_m2=400,GT_triangulated=False,scientific_verdict=None))
    print('NEW_MESH_SCORED',stem,family,len(P),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
