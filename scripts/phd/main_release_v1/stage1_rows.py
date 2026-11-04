from common import *
import sys
sys.path.append('/repo/scripts/phd/main_rescore_v1')
from geometry import context,MeshScene,closest
from columns import presence
def main(site,prior):
    import open3d as o3d
    cfg();root=O/'stage1'/f'{site}__{prior}';ctx=context(site,prior);core=ctx['core'];own=ctx['row_owner'];inside=own>=0
    scores=score_dir(site,prior,'FINALTRAIN_30000');v=json.loads((scores/'values.json').read_text());z=loadz(scores/'points.npz',['row_distance_m','row_tau_m','row_owner']);assert np.array_equal(z['row_owner'],own)
    mesh=Path(v['mesh']);m=o3d.io.read_triangle_mesh(str(mesh));s=MeshScene(np.asarray(m.vertices),np.asarray(m.triangles));q,d=closest(s,ctx['row_points'])
    has=presence(core,mesh,root/'v0_presence.npz');present=np.zeros(len(own),bool);present[inside]=has[own[inside]]
    signed=np.einsum('ij,ij->i',q-ctx['row_points'],ctx['row_normals']);roof=ctx['row_kind']==1;signed[roof]=q[roof,2]-ctx['row_points'][roof,2]
    typ=np.where(signed>0,1,2).astype('i1');typ[~present]=3;typ[z['row_distance_m']<=z['row_tau_m']]=0
    cell=np.full(len(own),-1,'i1');cell[inside]=ctx['v2']['cell_v2'][own[inside]]
    source_index=np.full(len(own),-1,'i8');source_index[inside]=core['source_index'][own[inside]]
    target=loadz(FT/'targets'/f'{site}__{prior}.npz',['judge_region','target','normal','sigma']);reg=np.full(len(own),9,'i1');reg[inside]=target['judge_region'][source_index[inside]]
    for k in [0,1,2,4]:
        m=cell==k;old=next(r for r in v['cells'] if r['cell']==k)
        if m.any():assert abs(float((typ[m]==0).mean())-old['completeness'])*100<=.1
    lookup=q.copy();lookup[typ==3]=ctx['row_points'][typ==3]
    savez(root/'rows.npz',xyz=ctx['row_points'],surface_xyz=q,lineage_xyz=lookup,result_type=typ,old_cell=cell,row_owner=own,source_index=source_index,judge_region=reg,row_distance_m=z['row_distance_m'],row_tau_m=z['row_tau_m'],signed_distance_m=signed,normal=ctx['row_normals'])
    dump(root/'rows.json',dict(mesh_sha256=sha(mesh),score_sha256=sha(scores/'values.json'),n_rows=len(own),result_types={'0':'within tau','1':'outside front/up','2':'outside back/down','3':'outside tau and no surface intersecting own prism'},roof_sign='positive local Z',wall_sign='reference normal orientation inherited',scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
