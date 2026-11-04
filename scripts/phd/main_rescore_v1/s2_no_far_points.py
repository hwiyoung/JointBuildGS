"""Record an empty far-point selection without unnecessary GPU contributor renders."""
from common import *
import sys
site=sys.argv[1];p=O/'checks'/f'{site}__check_b_selection.json';assert json.loads(p.read_text())['points']==0
table(site+'__check_b_LoD2_far_point_lineage',[])
dump(O/'lineage'/site/'join.json',dict(status='PASS_EMPTY_SELECTION_NO_RENDER_NEEDED',far_points=0,attributed_points=0,unavailable_points=0,selection_sha256=sha(p),scientific_verdict=None))
