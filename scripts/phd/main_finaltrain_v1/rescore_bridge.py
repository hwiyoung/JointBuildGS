"""Use RESCORE code unchanged, redirecting only its output/config roots."""
import importlib.util,sys
from common import *
RS=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'

def bind():
    source=R/'scripts/phd/main_rescore_v1';p=source/'common.py'
    spec=importlib.util.spec_from_file_location('finaltrain_rescore_common',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.C=R/'configs/phd/main_rescore_v1';mod.O=O/'rescore';mod.D=D/'rescore';mod.CELLS=RS/'cells_v2';mod.O.mkdir(parents=True,exist_ok=True);mod.D.mkdir(parents=True,exist_ok=True)
    dest=mod.O/'cells_v2'
    if not dest.exists():dest.symlink_to(RS/'cells_v2',target_is_directory=True)
    sys.modules['common']=mod;sys.path.insert(0,str(source))
    return mod,source

def main():
    action,site,prior=sys.argv[1:4]
    from scope_policy import require_postprocessing
    require_postprocessing(site)
    cfg();stem=f'{site}__{prior}';mod,source=bind()
    if action=='cleanup':
        validation=RS/'validation/cleanup/validation.json'
        assert json.loads(validation.read_text())['status']=='PASS_EXACT_VERTICES_AND_TRIANGLES'
        import bounded_cleanup
        mesh=O/'meshes'/stem/'final.ply'
        bounded_cleanup.cleanup(site,mesh.parent/'final_work/merged.ply',mesh)
    elif action=='score':
        validation=RS/'validation/scorer.json'
        assert validation.exists(),'RESCORE_SCORER_NOT_READY'
        assert json.loads(validation.read_text())['columns']=='PASS_BOUNDARIES_OVERLAP_TIE'
        import score_mesh
        mesh=O/'meshes'/stem/'final.ply';score_mesh.score(site,prior,'ft_'+stem,mesh)
        dump(O/'scores'/stem/'binding.json',dict(at=now(),result=str(mod.O/'scores'/('ft_'+stem)/'values.json'),
            validation_sha256=sha(validation),source_files={str(p):sha(p) for p in [source/'score_mesh.py',source/'geometry.py',source/'metrics.py',source/'prism.cpp']},scientific_verdict=None))
    else:raise ValueError(action)
if __name__=='__main__':main()
