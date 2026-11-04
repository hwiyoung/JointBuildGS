"""Host bounded mesh sequence reused from RESCORE s2_build_one.sh."""
import json,subprocess,sys
from gpu_job import R,O
def cpu(tag,*args):subprocess.run(['bash',str(R/'scripts/phd/main_release_v1/run_cpu.sh'),tag,'rescore_task.py',*map(str,args)],cwd=R,check=True)
def build(key):
    job='/release/jobs/'+key+'.json';wd=O/'meshes'/key/'train_work'
    if not (O/'meshes'/key/'primary.ply').exists():
        if not (wd/'inputs/meta.json').exists():cpu(key+'-prep','prepare',job)
        if not (wd/'order/order.json').exists():cpu(key+'-plan','plan',job)
        for tile in json.loads((wd/'plan/layout.json').read_text())['tiles']:
            k=tile['k']
            if not (wd/f'tiles/tile{k}.json').exists():cpu(key+f'-tile{k}','tile',job,k)
        if not (wd/'merged.json').exists():cpu(key+'-merge','merge',key)
        cpu(key+'-cleanup','cleanup',key)
    if not (O/'scores'/key/'values.json').exists():cpu(key+'-score','score',key)
if __name__=='__main__':build(sys.argv[1])
