"""Run immutable r23/r15 source with seed 1 and task-local outputs."""
import sys,runpy,ast
from common import *
family=sys.argv[1];cfg();stage_lock(4)
model=Path(sys.argv[sys.argv.index('-m')+1]);source=Path('/source/train.py')
lock=json.loads((C/'seed1.add1.lock.json').read_text())
for path,digest in lock['files'].items():assert sha(path)==digest
sys.path.insert(0,'/repo/scripts/phd/main_finaltrain_v1');from renderer import install
install();sys.path.insert(0,'/source');sys.argv=[str(source)]+sys.argv[2:]
if family=='ft':runpy.run_path(str(source),run_name='__main__')
else:
    import seed1_monitor
    tree=ast.parse(source.read_text());count=0
    for func in tree.body:
        if isinstance(func,ast.FunctionDef) and func.name=='training':
            for node in ast.walk(func):
                if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='iteration':
                    node.body+=ast.parse('seed1_monitor.after_step(locals())').body;count+=1
    assert count==1
    ast.fix_missing_locations(tree);exec(compile(tree,str(source),'exec'),dict(__name__='__main__',__file__=str(source),seed1_monitor=seed1_monitor))
assert (model/'point_cloud/iteration_30000/point_cloud.ply').exists()
dump(model.parent/'TRAINING_COMPLETE.json',dict(at=now(),iteration=30000,seed=1,scientific_verdict=None))
