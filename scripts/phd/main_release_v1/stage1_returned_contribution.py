"""Only the extra alpha*T pass for released descendants now inside valid bounds."""
import sys,types
from common import *
source=Path(__file__).with_name('stage1_render.py');text=source.read_text()
text=text.replace("/'lineage';root.mkdir", "/'lineage_returned';root.mkdir")
text=text.replace("existing=score_root(site)/'lineage'/site;use_existing=prior=='LoD2' and (existing/'receipt.json').exists()", "existing=root.parent/'lineage';use_existing=True")
text=text.replace("groups=[(r,k) for r in [0,1,2,4,9] for k in [0,1]]", "eligible=loadz(root.parent/'released_currently_eligible.npz')['eligible'];groups=[(r,2) for r in [0,1,2,4,9]]")
text=text.replace("(prep['case'][indices]==k)","eligible[indices]")
m=types.ModuleType('returned_pass');m.__file__=str(source);exec(compile(text,str(source),'exec'),m.__dict__);m.main(*sys.argv[1:])
