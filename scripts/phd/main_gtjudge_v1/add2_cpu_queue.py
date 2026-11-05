import concurrent.futures,fcntl
from add2_host import *
SITES=['B173nb_b10','B0_b10','R1rep_b10']
def alternative(job):
    site,variant=job
    assert mesh(site,'LoD2',variant),(job,'mesh')
    assert cpu(site+'-'+variant+'-score','score_new.py',site,'LoD2',variant),(job,'score')
    event('ALTERNATIVE_FINISHED',site=site,variant=variant)
def selection_commit():
    paths=['configs/phd/main_gtjudge_v1/addendum2.json','configs/phd/main_gtjudge_v1/addendum2.lock.json','docs/experiments/phd/main_gtjudge_v1/판고르기.json','docs/experiments/phd/main_gtjudge_v1/provenance/addendum2.txt','src/phd/forks/GeoGS-conf-guided-v1-r26']
    paths += [str(p.relative_to(R)) for p in (R/'scripts/phd/main_gtjudge_v1').glob('add2_*.py')]
    paths += ['scripts/phd/main_gtjudge_v1/unit_add2.py','docs/experiments/phd/main_gtjudge_v1/tables/addendum2/alternative_metrics.csv','docs/experiments/phd/main_gtjudge_v1/tables/addendum2/alternative_metrics.json']
    with (O/'queue/publish.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        subprocess.run(['git','add','--',*paths],cwd=R,check=True)
        if subprocess.run(['git','diff','--cached','--quiet','--',*paths],cwd=R).returncode:subprocess.run(['git','commit','--only','-m','PHD-MAIN-GTJUDGE-v1 addendum2 locked alternative selection','--',*paths],cwd=R,check=True)
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();subprocess.run(['git','push','origin','HEAD:exp/main-experiment'],cwd=R,check=True)
    dump(O/'queue/addendum2/selection_commit.json',dict(at=now(),commit=commit,selection_sha256=hashlib.sha256((D/'판고르기.json').read_bytes()).hexdigest(),scientific_verdict=None))
def main():
    for site in ['R1rep_b10','B173nb_b10','B0_b10']:
        assert cpu('freespace-'+site+'-ALS','add2_targets.py','freespace',site,'ALS')
        assert cpu('prepare-fix-'+site+'-ALS','add2_prepare.py',site,'ALS')
    for site in SITES:assert cpu('alternatives-'+site,'add2_targets.py','alternatives',site)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        for f in [pool.submit(alternative,(site,variant)) for site in SITES for variant in ['alt_na','alt_da']]:f.result()
    assert cpu('choose','add2_scores.py','choose');selection_commit()
    for site in ['R1rep_b10','B173nb_b10','B0_b10']:
        assert cpu('freespace-'+site+'-LoD2','add2_targets.py','freespace',site,'LoD2')
        assert cpu('prepare-fix-'+site+'-LoD2','add2_prepare.py',site,'LoD2')
    # Requested CPU task order: alternative comparison, accuracy denominator, roof/wall, features.
    for site in SITES:
        for prior in ['ALS','LoD2']:assert cpu('accuracy-'+site+'-'+prior,'add2_scores.py',site,prior)
    for site in SITES:assert cpu('alternative-figures-'+site,'add2_figures.py',site,'LoD2','alternatives')
    assert cpu('wall-views','add2_figures.py','R1rep_b10','LoD2','wall')
    for site in SITES:
        for prior in ['ALS','LoD2']:assert cpu('features-'+site+'-'+prior,'add2_features.py',site,prior)
    subprocess.run([sys.executable,str(R/'scripts/phd/main_gtjudge_v1/add2_publish.py'),'cpu'],cwd=R,check=True)
    dump(O/'queue/addendum2/cpu_done.json',dict(at=now(),scientific_verdict=None));event('CPU_COMPLETE')
if __name__=='__main__':main()
