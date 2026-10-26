"""Record an additional requested gap illustration before rendering its curves."""
from common import *
def main():
    target=C/'figure_site_supplement.json'
    if target.exists():return
    record=dict(at=now(),original_measurement_config_sha256=sha(C/'photocheck_v1.json'),reason='Specify the separately requested R1 gap illustration before first curve figures. Located from prior-only surface map and original photograph, without GT or scores. Numerical processing and existing locked sections unchanged.',
      source_photo='DJI_20241217084543_0095_D.JPG',inspection_source=str(O/'inspection/r1_prior_surfaces.png'),inspection_sha256=sha(O/'inspection/r1_prior_surfaces.png'),
      sites=[dict(id='R1_gap',building='DEBY_LOD2_4906975',prior='LoD2',tile='6909_53361',surface=323,targets_xy_m=[[-10.42,35.06],[-10.42,41.06]],selection_reason='R1 narrow gap between the requested building and adjacent barrel roof, identified on photo 74 and prior surface 323; nearest point to fixed XY targets; no GT or curve filter')],
      example_rule='Use same building locked section for both priors when only one prior section was supplied; two nearest roof points at section 40% and 60%.',scientific_verdict=None)
    dump(target,record);dump(C/'figure_site_supplement.lock.json',dict(at=now(),sha256=sha(target)));print('figure supplement locked',sha(target))
if __name__=='__main__':main()
