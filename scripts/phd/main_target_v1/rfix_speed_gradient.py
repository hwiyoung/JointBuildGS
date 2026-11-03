"""Same frozen loss/30 views, new user relative-L2 criterion."""
import rfix_gradient as G
from rfix_gradient_fast import differences as full_differences
from rfix_speed_measure import speed
from common import *
def differences(a,b,c):
 r=full_differences(a,b,c);r['historical_jitter_pass']=r['pass_'];r['pass_']=r['nonfinite_masks_equal'] and r['relative_l2']<=1e-4;return r
if __name__=='__main__':
 import sys
 cfg=json.loads((CFG/'rfix_speed.json').read_text());row=next(r for r in cfg['states'] if r['key']==sys.argv[1]);label={'image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target')
 paths=[Path(__file__),Path(__file__).with_name('rfix_gradient_fast.py'),OUT/'rfix_speed/builds'/label/'extension'/('jbgs_rfix_speed_'+label+'.so'),CFG/'rfix_speed.json']
 dump(OUT/'rfix_speed/execution'/('gradient_wrapper_'+sys.argv[1]+'.lock.json'),dict(at=stamp(),files={str(p):sha(p) for p in paths},relative_l2_max=1e-4,training_use=False,scientific_verdict=None))
 G.ROOT=OUT/'rfix_speed';G.extension=speed;G.differences=differences;G.main()
