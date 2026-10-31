"""Record the post-inspection implementation correction without changing training locks."""
from cp2_common import *

def main():
    check=OUT/'preflight/depth_r1.json';assert json.loads(check.read_text())['status']=='PASS'
    p=CFG/'depth_readout_amendment_r1.json'
    value=dict(at=now(),task_id='PHD-MAIN-CANDPICK-v2',status='LOCKED_BEFORE_CORRECTED_DEPTH_SCORING',
        reason='Source audit after unavailable depth maps: r0 invalidated entire pixels instead of skipping near contributors, and retained the gsplat .999 alpha cap. Match the requested GeoGS depth readout with full tile traversal, near skip before transmittance and .99 alpha cap.',
        original_config=bind(CFG/'candpick_v2.json'),original_depth_rule=config()['depth'],
        effective_depth=dict(mode='expected',depth_ratio=0,per_contributor_depth='s.x*Tw.x+s.y*Tw.y+Tw.z',
            near_m=.2,near_handling='skip contributor before updating transmittance; continue full tile list',
            alpha_cap=.99,alpha_min=1/255,exclusive_stop_transmittance=.0001,
            projection='unchanged gsplat1.4 projected discs, tile order and pixel centers x+.5/y+.5',
            unavailable='no positive finite alpha-normalized depth, nonfinite arithmetic, or no valid pixels in any of three fixed views'),
        unchanged=['all training inputs and 22 final states','fixed per-point three views and support pixels','tau and area weights','photo DL replay'],
        training_recomputed=False,scientific_verdict=None,source=SOURCE,
        source_reference_image='sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be',
        execution_image=config()['docker_image'],source_reference=[bind(OUT/'source_reference/geogs_forward.cu'),
            bind('/repo/src/phd/forks/GeoGS-conf-guided-v1-r18/gaussian_renderer/__init__.py')],
        preflight=bind(check),superseded_results=bind(OUT/'revisions/depth_r0/manifest.json'),
        implementation=[bind(Path(__file__).with_name(n)) for n in
            ['score_depth_r1.py','geogs_depth_readout.py','geogs_depth_readout.cu','check_depth_r1.py']])
    save(p,value);save(p.with_suffix('.lock.json'),dict(at=now(),sha256=sha(p),source=SOURCE,scientific_verdict=None))
    save(DOC/'tables/depth_correction_r1.json',value);print('DEPTH_R1_LOCK',sha(p),flush=True)

if __name__=='__main__':main()
