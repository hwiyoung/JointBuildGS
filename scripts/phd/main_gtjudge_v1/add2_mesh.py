import sys
import mesh_job
from inherited import *
from add2_common import target_file,config2

def main(site,prior,family,step,ply=None):
    config2()
    if family not in ['alt_na','alt_da'] or step!='render':return mesh_job.main(site,prior,family,step,ply)
    key=f'{site}__{prior}__{family}'
    if (O/'renders'/key/'receipt.json').exists():return
    ensure_views(site);full=loadz(target_file(site,prior,family));core=loadz(JA/'core_points'/f'{site}__{prior}.npz',['source_index']);ix=core['source_index']
    target=dict(patch_id=full['patch_id'][ix],target_height_m=full['target_height_m'][ix])
    m=module('render_patches');reader=m.loadz;expected=O/'targets_oracle'/f'{site}__{prior}.npz'
    m.loadz=lambda p,*a,**kw:target if Path(p)==expected else reader(p,*a,**kw)
    m.main(site,prior,family)
    p=O/'renders'/key/'receipt.json';v=json.loads(p.read_text());v.update(target_file=str(target_file(site,prior,family)),target_sha256=sha(target_file(site,prior,family)),GT_read=False);dump(p,v)
if __name__=='__main__':main(*sys.argv[1:])
