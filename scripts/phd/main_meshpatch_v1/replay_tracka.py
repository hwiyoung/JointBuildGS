"""Execute the received Roofer driver unchanged with the same prepared arrays."""
import sys,ast
from patch_units import *
prior=sys.argv[1];src=prepare(prior,locked());d=track_data(src)
E=np.load(CACHE/f'{prior}_edges.npy').astype(np.int64);U=dict(np.load(CACHE/f'{prior}_units.npz'))
cases=json.loads((O/'received/track_a_v3/results/cases.json').read_text())[prior]
out=O/'cache/replay_tracka';out.mkdir(exist_ok=True);tc.W=str(out);np.save(out/f'{prior}_curv.npy',np.load(CACHE/f'{prior}_curv.npy'))
tc.load=lambda p:(d,{'mvs_a_s':d['mvs_a_s']},E,U,cases)
p=O/'received/track_a_v3/scripts/roofer_like.py';sys.argv=[str(p),prior,'.3','.75','roofer_replay']
exec(compile(p.read_text(),str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
same=np.array_equal(U['roofer_def'],U['roofer_replay'])
# Execute the unchanged element-type calculation prefix, without its later plots.
p2=O/'received/track_a_v3/scripts/elem_types.py';tree=ast.parse(p2.read_text());loop=next(x for x in tree.body if isinstance(x,ast.For))
body=[]
for node in loop.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='Tl' for t in node.targets):break
    if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='unique':
        if any(isinstance(t,ast.Tuple) and any(isinstance(y,ast.Name) and y.id=='Tl' for y in t.elts) for t in node.targets):break
    body.append(node)
ns=dict(np=np,load=tc.load,truth_comp=tc.truth_comp,W=tc.W,prior=prior,EL='mvsshape_10')
exec(compile(ast.Module(body=body,type_ignores=[]),str(p2),'exec'),ns)
existing=np.load(CACHE/f'{prior}_mvsshape_10_types.npz')
types_same=all(np.array_equal(ns[k],existing[k]) for k in ['pt','edge','et','lab','tilt','escat','frac_up','earea'])
dump(D/'tables'/f'patch_{prior}_original_driver_replay.json',dict(prior=prior,roofer_driver_sha256=sha(p),element_source_sha256=sha(p2),
    driver_labels_identical=same,element_arrays_identical=types_same,groups=len(np.unique(U['roofer_replay'])),
    note='Same prepared inputs and curvature, original driver executed. Does not identify the cause of a difference from the supplied summary-only benchmark.',scientific_verdict=None))
assert same and types_same
print(prior,'original driver and element arrays identical',flush=True)
