"""All-prior-height patch TSDF diagnostic; no GT enters the surface construction."""
from inherited import *
from add4_common import AC,AW,AF,AT,proof,case,getcase,section_mask,savepng
from geometry_add1 import MeshScene,read_surface,section_segments,section_points
from normal_line import measure,values

def main(site,prior,family,step):
    assert family in ['always_keep_mesh','always_keep_mesh_t010']
    trunc=.10 if family.endswith('t010') else .25
    from src.phd import streamed_tsdf as T
    T.TRUNC=trunc
    stem=f'{site}__{prior}';key=stem+'__'+family;view=ensure_views(site);root=O/'meshes'/key;wd=root/'final_work';cache=O/'renders'/(stem+'__always_keep_mesh')
    job=dict(key=key,site=site,prior=prior,family=family,box=view['box'],cache=str(cache),scientific_verdict=None)
    if not (O/'jobs'/f'{key}.json').exists():dump(O/'jobs'/f'{key}.json',job)
    if step=='render':
        if (cache/'receipt.json').exists():return
        core=loadz(JA/'core_points'/f'{stem}.npz',['patch_id','prior_height_m'])
        target=dict(patch_id=core['patch_id'],target_height_m=core['prior_height_m'])
        targetpath=AW/'keep_targets'/f'{stem}.npz';savez(targetpath,**target)
        m=module('render_patches');reader=m.loadz;expected=O/'targets_oracle'/f'{stem}.npz'
        m.loadz=lambda p,*a,**kw:target if Path(p)==expected else reader(p,*a,**kw)
        m.main(site,prior,'always_keep_mesh')
        rp=cache/'receipt.json';j=json.loads(rp.read_text());j.update(GT_read=False,target_rule='all core prior patches retain exact prior_height_m',target_source=proof(targetpath));dump(rp,j)
    elif step=='prepare':module('mesh_pipeline').prepare(job,'final')
    elif step=='plan':T.plan(wd,'auto:16');T.order(wd)
    elif step.startswith('tile:'):T.tile(wd,int(step.split(':')[1]))
    elif step=='merge':module('bounded_merge').merge(wd,wd/'merged.ply',wd/'merged.json')
    elif step=='finish':
        module('mesh_pipeline').finish(job,'final')
        j=json.loads((root/'final.json').read_text());j.update(trunc_m=trunc,GT_used_to_build_surface=False,all_prior_patches_preserved=True);dump(root/'final.json',j)
    elif step=='score':
        out=AW/'keep_scores'/stem/f'{family}.npz'
        if out.exists():return
        row=loadz(O/'scenes'/stem/'rows.npz');V,F=read_surface(root/'final.ply');scene=MeshScene(V,F);s,offset=measure(scene,row['xyz'],row['normal'],row['wall'])
        savez(out,row_s=s,row_offset=offset)
        dump(out.with_suffix('.json'),dict(mesh=proof(root/'final.ply'),rows=proof(O/'scenes'/stem/'rows.npz'),voxel_m=.05,trunc_m=trunc,
            scorer='unchanged stage1 normal_line.measure five origin rays, signed min absolute hit, roof 10m / wall 5m',scientific_verdict=None))
    else:raise ValueError(step)
    print('ADD4_KEEP',stem,family,step,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
