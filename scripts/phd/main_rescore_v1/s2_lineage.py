"""Inherited contributor rendering/join, scoped to one stage-2 site."""
from common import *
import types,sys
def main(mode,site_or_job):
 site=json.loads(Path(site_or_job).read_text())['site'] if mode=='render' else site_or_job
 assert site in ['B0_b10','R1rep_b10']
 name='add3_lineage_render.py' if mode=='render' else 'add3_lineage_join.py';source=Path(__file__).with_name(name);text=source.read_text()
 text=text.replace("site='B173nb_b10'",'site='+repr(site))
 text=text.replace("model=FT/'runs'/site/'ft_LoD2_s0/attempt1/model'", "model=Path(json.loads((O/'jobs'/f'{site}__{prior}__FINALTRAIN_30000.json').read_text())['ply']).parents[2]")
 text=text.replace("FT/'meshes'/f'{site}__{prior}'/'render'","O/'renders'/f'{site}__{prior}__FINALTRAIN_30000'")
 text=text.replace("FT/'meshes/B173nb_b10__LoD2/render'","O/'renders'/"+repr(site+'__LoD2__FINALTRAIN_30000'))
 text=text.replace("O/'lineage'","O/'lineage'/"+repr(site))
 text=text.replace("'checks/check_b_LoD2_far_points.npz'",repr('checks/'+site+'__check_b_LoD2_far_points.npz'))
 text=text.replace("root.mkdir(exist_ok=True)","root.mkdir(parents=True,exist_ok=True)")
 m=types.ModuleType('stage2_lineage');m.__file__=str(source);exec(compile(text,str(source),'exec'),m.__dict__);m.table=lambda name,rr:table(site+'__'+name,rr);m.main()
if __name__=='__main__':
 if len(sys.argv)==2:main('render',sys.argv[1])
 else:main(*sys.argv[1:])
