"""Same stage-1 diagnostics with site-qualified tables and arrays."""
from common import *
import types,sys
def main(site,prior,mode='targets'):
 source=Path(__file__).with_name('add3_checks.py');text=source.read_text()
 for name in ['check_c_LoD2.npz','check_b_LoD2_far_points.npz','check_b_selection.json']:
  text=text.replace("'checks/"+name+"'","f'checks/{SITE}__"+name+"'")
 m=types.ModuleType('stage2_checks');m.__file__=str(source);exec(compile(text,str(source),'exec'),m.__dict__);m.SITE=site
 m.table=lambda name,rr:table(name if name.startswith('target_quality_') else site+'__'+name,rr)
 m.main(prior,mode)
if __name__=='__main__':main(*sys.argv[1:])
