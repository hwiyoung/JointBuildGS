"""Bind inherited RESCORE modules to this task's own output root."""
import sys,time,importlib.util
import numpy as np
import common
from common import *
common.np=np;common.time=time;common.TG=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
common.S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1';common.CELLS=RS/'cells_v2'
common.timing=lambda stage,start,**kw:dump(O/'timing'/f'{stage}.json',dict(at=now(),seconds=time.monotonic()-start,**kw))
sys.path.insert(0,'/repo');sys.path.append('/repo/scripts/phd/main_rescore_v1')
def module(name,folder='main_rescore_v1'):
    path=R/'scripts/phd'/folder/(name+'.py');spec=importlib.util.spec_from_file_location('inherited_'+name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def ensure_views(site):
    from geometry_add1 import views
    vv,p=views(site);z=json.loads(p.read_text());z['views']=vv
    if 'box' not in z:
        z['box']=json.loads((RS/'meshes/B173nb_b10__ALS__r8_30000/final_work/inputs/meta.json').read_text())['box']
    z.update(parent_view_source=str(p),parent_view_sha256=sha(p),GTJUDGE_diagnostic=True)
    out=O/'views'/f'{site}.json'
    if not out.exists():dump(out,z)
    return z
