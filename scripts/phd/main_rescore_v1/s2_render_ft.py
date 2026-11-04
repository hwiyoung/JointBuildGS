"""Unchanged FT speed renderer plus RESCORE's frozen camera/crop inference."""
from common import *
import importlib.util,sys
import diff_surfel_rasterization as raster
c=json.loads((R/'configs/phd/main_finaltrain_v1/finaltrain_v1.json').read_text())['renderer'];assert sha(c['path'])==c['sha256']
spec=importlib.util.spec_from_file_location('jbgs_rfix_speed_target',c['path']);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.jbgs_set_guard(c['binning_guard_fraction']);raster._C=mod
import render_model
if __name__=='__main__':
 render_model.main(sys.argv[1]);j=json.loads(Path(sys.argv[1]).read_text());p=O/'renders'/j['key']/'receipt.json';r=json.loads(p.read_text());r.update(finaltrain_renderer=c,adapter_sha256=sha(__file__),training_steps=0);dump(p,r)
