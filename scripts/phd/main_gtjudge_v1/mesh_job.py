"""Exact inherited patch rendering and bounded TSDF recipe, task-local outputs."""
import sys
from inherited import *

def main(site,prior,family,step,ply=None):
    cfg();stem=f'{site}__{prior}';key=stem+'__'+family;view=ensure_views(site)
    path=O/'jobs'/f'{key}.json'
    if not path.exists():dump(path,dict(key=key,site=site,prior=prior,family=family,box=view['box'],**({'ply':ply} if ply else {})))
    job=json.loads(path.read_text());root=O/'meshes'/key;wd=root/'final_work'
    if step=='render':
        if (O/'renders'/key/'receipt.json').exists():return
        if family=='gt_judgment_mesh':
            full=loadz(O/'targets_gt'/f'{stem}.npz');core=loadz(JA/'core_points'/f'{stem}.npz',['source_index']);ix=core['source_index']
            savez(O/'targets_oracle'/f'{stem}.npz',patch_id=full['patch_id'][ix],target_height_m=full['target_height_m'][ix])
            m=module('render_patches');m.main(site,prior,family)
            rp=O/'renders'/key/'receipt.json';rec=json.loads(rp.read_text());rec.update(GT_read='정답 판단 target exception only',diagnostic='정답 판단');dump(rp,rec)
        else:
            module('renderer','main_finaltrain_v1').install();module('render_model').main(str(path))
    elif step=='prepare':module('mesh_pipeline').prepare(job,'final')
    elif step=='plan':
        from src.phd import streamed_tsdf as T
        T.plan(wd,'auto:18');T.order(wd)
    elif step.startswith('tile:'):
        from src.phd import streamed_tsdf as T
        T.tile(wd,int(step.split(':')[1]))
    elif step=='merge':module('bounded_merge').merge(wd,wd/'merged.ply',wd/'merged.json')
    elif step=='finish':module('mesh_pipeline').finish(job,'final')
    else:raise ValueError(step)
if __name__=='__main__':main(*sys.argv[1:])
