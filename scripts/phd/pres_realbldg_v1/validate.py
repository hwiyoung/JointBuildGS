"""Independent arithmetic checks and meaningful boundary tests for the order."""
from common import *
from measure import component,longest
from finish_measure import flags
from PIL import Image

def main():
    c=cfg();checks={}
    first=json.loads((O/'first_calculation.json').read_text());lock=json.loads((C/'realbldg_v1.initial.lock.json').read_text());assert lock['saved_at']<first['at'];checks['precalculation_lock']=True
    a,mask=component(np.array([[0,0,0],[0,0,0],[.5,0,0],[4,0,0]],float),np.array([1.,2.,1.,3.]),.6);assert a==4 and mask.tolist()==[True,True,True,False];checks['component_duplicate_and_area_weight']=True
    length,ix=longest(np.array([True,True,False,False,True,True]),np.full(6,.5));assert length==2 and set(ix)=={4,5,0,1};checks['cyclic_eaves_run']=True
    q=np.arange(7*9,dtype='f4').reshape(7,9)/255;gy,gx=np.gradient(q);x=np.array([1,4,7]);y=np.array([1,3,5]);assert np.array_equal(gx[y,x],(q[y,x+1]-q[y,x-1])*.5);assert np.array_equal(gy[y,x],(q[y+1,x]-q[y-1,x])*.5);checks['inherited_gradient_stencil']=True
    rank=json.loads((O/'ranking.json').read_text());rows=rank['rows'];assert not rank['top5_unmeasured_competitors'];assert rank['all_five']==sum(all(v is True for v in r['conditions'].values()) for r in rows);assert all(r['count']==4 for r in rank['top5']);checks['count_and_ranking_upper_bound']=True
    b=json.loads((O/'buildings.json').read_text());present={r['building'] for r in rows};missing=sorted(set(b)-present)
    checks['population_geometry_buildings']=len(b);checks['population_with_case_material']=len(present);checks['population_missing_case_material']=missing
    audit=[]
    for r in rank['top5']:
        stem=r['scene'];bid=r['building'];d=loadz(O/'data'/f'{stem}.npz',['case','area','building']);m=d['building']==bid
        for case in [-1,0,1,2,3,4]:assert abs(float(d['area'][m&(d['case']==case)].sum())-r['case_areas'][str(case)])<1e-8
        edge=json.loads((O/'edges'/stem/f'{bid}.json').read_text())
        for e in edge:
            no=np.array(e['outside_count']);ni=np.array(e['inside_count']);po=np.array(e['prior_only_count']);bo=np.array(e['both_wrong_outer']);bi=np.array(e['both_wrong_inner']);valid=[]
            for j in range(len(no)):
                valid.append(bool(no[j]>=(2 if stem.startswith('outside') else 5) and po[j]/no[j]>=.5 and bo[j]/no[j]<.2 and (not ni[j] or bi[j]/ni[j]<.2)))
            assert valid==e['passes']
        audit.append(dict(building=bid,case_areas='PASS',edge_fractions='PASS',coverage=r['coverage'],minimum_satisfied_area_m2=r['minimum_satisfied_area_m2']))
    checks['top5_recalculation']=audit
    for p in (O/'data').glob('*.json'):
        for s in json.loads(p.read_text())['sources']:assert sha(s['path'])==s['sha256'],s['path']
    checks['inherited_sources_preserved']=True
    checks['gpu_device_files']=list(map(str,Path('/dev').glob('nvidia*')));assert not checks['gpu_device_files']
    checks['cpu_max']=Path('/sys/fs/cgroup/cpu.max').read_text().strip();checks['memory_max']=Path('/sys/fs/cgroup/memory.max').read_text().strip()
    checks['mountinfo']=Path('/proc/self/mountinfo').read_text();checks['scientific_verdict']=None
    dump(D/'validation.json',dict(at=now(),status='PASS_NUMERICAL_CHECKS',checks=checks,scientific_verdict=None));print(json.dumps({k:v for k,v in checks.items() if k!='mountinfo'},ensure_ascii=False))
if __name__=='__main__':main()
