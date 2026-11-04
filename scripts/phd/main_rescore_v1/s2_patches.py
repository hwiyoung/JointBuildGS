"""Inherited patch rendering at frozen training cameras; write only new outputs."""
from common import *
import types,sys
source=Path(__file__).with_name('render_patches.py');text=source.read_text()
assert "O/'targets_fusion'" in text;text=text.replace("O/'targets_fusion'","O/'fusion_targets_stage2'")
m=types.ModuleType('stage2_patch_render');m.__file__=str(source);exec(compile(text,str(source),'exec'),m.__dict__)
if __name__=='__main__':
 site,prior,family=sys.argv[1:];key=f'{site}__{prior}__{family}'
 if not (O/'renders'/key/'receipt.json').exists():m.main(site,prior,family)
 p=O/'jobs'/f'{key}.json';j=json.loads(p.read_text());j.update(cache=str(O/'renders'/key),views=len(json.loads((O/'views'/f'{site}.json').read_text())['views']));dump(p,j)
