"""Load the already-validated speed build and its allocation guard."""
import importlib.util
from common import cfg,sha
def install():
    import torch
    import diff_surfel_rasterization as raster
    c=cfg()['renderer'];assert sha(c['path'])==c['sha256']
    spec=importlib.util.spec_from_file_location('jbgs_rfix_speed_target',c['path'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.jbgs_set_guard(c['binning_guard_fraction']);raster._C=module
    return module
