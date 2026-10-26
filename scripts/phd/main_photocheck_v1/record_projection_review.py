"""Receipt for the agent's actual displayed projection-figure review."""
from common import *
def main():
    files=sorted((D/'figures/projection').glob('*.png'));assert len(files)==24
    receipt=dict(status='PASS',at=now(),reviewer='coding agent visual inspection',scope='24 projection panels via two contact sheets; B173 LoD2 additionally inspected as individual panels',
      observed='Projected geometry follows the correct buildings, camera directions and visible major roof edges. Local prior/photo differences remain visible, including changed-height examples. This checks projection presentation, not prior validity.',
      numeric_gate_required=True,files=[dict(file=str(p.relative_to(D)),sha256=sha(p),json_sha256=sha(p.with_suffix('.json'))) for p in files],scientific_verdict=None)
    dump(O/'gates/projection_visual.json',receipt)
    dump(C/'figure_palette.json',dict(at=now(),judgment=['#238b45','#d73027','#929292'],cells=['#4292c6','#0072b2','#d55e00','#9e9ac8','#41ab5d','#a65628','#bdbdbd'],inherited_cell_colors={'1':'#0072b2','2':'#d55e00'},inherited_source='/repo/scripts/phd/main_widen0_v2/distributions.py lines 51 and 65',remaining_cell_colors='Existing fixed colors not found; auxiliary display colors, always accompanied by cell numbers; no definition change',before_first_cell_map=True,scientific_verdict=None))
    print('projection visual review recorded',len(files))
if __name__=='__main__':main()
