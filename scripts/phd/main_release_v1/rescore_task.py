"""Path-only adapter for the frozen RESCORE renderer/TSDF/scorer."""
import sys,types
from common import *
sys.path.append('/repo/scripts/phd/main_rescore_v1')
def main(action,*args):
    cfg()
    if action=='render':
        sys.path.append('/repo/scripts/phd/main_finaltrain_v1');sys.path.insert(0,'/source')
        from renderer import install
        install()
        from render_model import main as render_main
        render_main(args[0])
    elif action in ['prepare','plan','tile']:
        import mesh_pipeline
        sys.argv=['mesh_pipeline.py',args[0],'train',action,*args[1:]];mesh_pipeline.main()
    elif action=='merge':
        from bounded_merge import merge
        key=args[0];wd=O/'meshes'/key/'train_work';merge(wd,wd/'merged.ply',wd/'merged.json')
    elif action=='cleanup':
        from bounded_cleanup import cleanup
        key=args[0];j=json.loads((O/'jobs'/f'{key}.json').read_text());root=O/'meshes'/key;cleanup(j['site'],root/'train_work/merged.ply',root/'primary.ply')
    elif action=='score':
        src=R/'scripts/phd/main_rescore_v1/score_mesh.py';text=src.read_text().replace("C/'rescore_v1.json'","C/'release_v1.json'")
        m=types.ModuleType('release_scorer');m.__file__=str(src);exec(compile(text,str(src),'exec'),m.__dict__)
        key=args[0];j=json.loads((O/'jobs'/f'{key}.json').read_text());m.score(j['site'],j['prior'],key,O/'meshes'/key/'primary.ply')
    else:raise ValueError(action)
if __name__=='__main__':main(*sys.argv[1:])
