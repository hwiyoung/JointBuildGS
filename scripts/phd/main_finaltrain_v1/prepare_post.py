"""Resolve scorer bindings and build unchanged bounded CPU kernels once."""
import subprocess
from common import *
from rescore_bridge import bind,RS
mod,source=bind()
assert json.loads((RS/'validation/scorer.json').read_text())['columns']=='PASS_BOUNDARIES_OVERLAP_TIE'
assert json.loads((RS/'validation/cleanup/validation.json').read_text())['status']=='PASS_EXACT_VERTICES_AND_TRIANGLES'
import geometry,score_mesh,bounded_cleanup
assert geometry.CELLS==RS/'cells_v2'
assert geometry.O==O/'rescore' and score_mesh.O==O/'rescore' and bounded_cleanup.O==O/'rescore'
for name in ['prism','cleanup']:
    src=source/(name+'.cpp');exe=mod.O/'bin'/name;exe.parent.mkdir(exist_ok=True)
    subprocess.run(['g++','-O3','-std=c++17',str(src),'-o',str(exe)],check=True)
    exe.with_suffix('.sha256').write_text(sha(src))
dump(O/'verification/post_bindings.json',dict(at=now(),status='PASS',output_root=str(mod.O),cells_root=str(mod.CELLS),
    sources={str(p):sha(p) for p in [source/'score_mesh.py',source/'geometry.py',source/'prism.cpp',source/'bounded_cleanup.py',source/'cleanup.cpp']},scientific_verdict=None))
print('POST_BINDINGS_PASS',flush=True)
