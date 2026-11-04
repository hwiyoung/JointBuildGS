"""Same MVS wall rule as stage 1, adapted only to site and stage-2 caches."""
from common import *
import types,sys
source=Path(__file__).with_name('add3_walls.py');text=source.read_text()
text=text.replace("wall=O/'walls/mvs_wall.ply'", "wall=O/'walls'/f'{SITE}_mvs_wall.ply'")
text=text.replace("assert len(views)==203", "assert len(views)==len(json.loads((O/'views'/f'{SITE}.json').read_text())['views'])")
text=text.replace("BASE/'renders'", "O/'renders'")
m=types.ModuleType('stage2_wall_render');m.__file__=str(source);exec(compile(text,str(source),'exec'),m.__dict__)
if __name__=='__main__':
 site=sys.argv[1];m.SITE=site;m.main()
 for family in ['fusion','judgment_mesh','oracle']:
  p=O/'jobs'/f'{site}__ALS__{family}_mvswalls.json';j=json.loads(p.read_text());j['views']=len(json.loads((O/'views'/f'{site}.json').read_text())['views']);dump(p,j)
