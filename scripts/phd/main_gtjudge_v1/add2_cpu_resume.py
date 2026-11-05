"""Resume only the unfinished wall view and task 4; preserve completed CPU work."""
from add2_host import *
assert cpu('wall-views-repaired','add2_figures.py','R1rep_b10','LoD2','wall')
for site in ['B173nb_b10','B0_b10','R1rep_b10']:
    for prior in ['ALS','LoD2']:
        if not (D/'tables/addendum2'/f'{site}__{prior}_feature_provenance.json').exists():assert cpu('features-'+site+'-'+prior,'add2_features.py',site,prior)
subprocess.run([sys.executable,str(R/'scripts/phd/main_gtjudge_v1/add2_publish.py'),'cpu'],cwd=R,check=True)
dump(O/'queue/addendum2/cpu_done.json',dict(at=now(),scientific_verdict=None));event('CPU_COMPLETE')
