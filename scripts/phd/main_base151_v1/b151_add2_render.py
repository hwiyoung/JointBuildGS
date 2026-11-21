"""addendum 2 1-7, container side (fork image jointbuildgs:geogs-conf-guided-v1, /source = GeoGS-conf-guided-v1-r23): render one 4.2 unit job of the
TRAINUNIT cellsef_ALS_s0 cell-3 model with the GTJUDGE mesh_job rule for fork families (main_finaltrain_v1 renderer.install(), then RESCORE
render_model.main(job)) -- the same call TRAINUNIT-v2 used for its 4.1 renders. scientific_verdict: null
  python b151_add2_render.py /gtjudge/jobs/<key>.json
"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import cfg, module  # noqa: E402

cfg()
module('renderer', 'main_finaltrain_v1').install()
module('render_model').main(sys.argv[1])
