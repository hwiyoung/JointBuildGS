"""One fixed middle training camera; the original model renderer and crop unchanged."""
from common import *
import types,sys
source=Path(__file__).with_name('render_model.py');text=source.read_text()
old="views=json.loads((O/'views'/f\"{job['site']}.json\").read_text())['views'];"
assert old in text
text=text.replace(old,old+"views=[views[len(views)//2]];")
text=text.replace("f'{i:04d}.npz'", "f\"{v['index']:04d}.npz\"")
m=types.ModuleType('stage2_diagnostic_render');m.__file__=str(source);exec(compile(text,str(source),'exec'),m.__dict__)
if __name__=='__main__':m.main(sys.argv[1])
