"""Freeze visualization/sample definitions before the first web build."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *

def layers():
    out=[]
    def add(id,label,key,unit='cm',bounds=(0,50),group='방법이 쓰는 값',status=None,prior=None,kind='continuous',description=''):
        out.append(dict(id=id,label=label,key=key,unit=unit,range=bounds,group=group,status=status,prior=prior,kind=kind,description=description or label))
    add('difference','두 자료의 차','mvs_{v}_p',bounds=(-50,50),status='mvs_{v}_status',description='안쪽 원 MVS 점의 패치 법선 거리 중앙값. 사전 정보 면이 0, 바깥이 +.')
    for f,lab in [('u','불확실도'),('a','어긋남'),('s','흩어짐'),('q','68.3 % 값')]:
        add('mvs_'+f,'MVS '+lab,'mvs_{v}_'+f,status='mvs_{v}_status')
    add('prior_u','사전 정보 불확실도','u_prior',description='항공 LiDAR 원래 점의 불확실도. LoD2는 앞 작업에서 저장한 20 cm.')
    for f,lab in [('a','어긋남'),('s','흩어짐'),('q','68.3 % 값')]:
        add('als_'+f,'항공 LiDAR '+lab,'als_'+f,status='als_status',prior='ALS')
    add('z','z','z_{v}',unit='',bounds=(0,10),description='두 자료의 차의 크기를 두 불확실도의 제곱합 제곱근으로 나눈 값.')
    add('weight','MVS 무게 비율','w_{v}',unit='',bounds=(0,1))
    for f,lab in [('n_inner_all','안쪽 원 점 수 · 솎기 전'),('n_inner','안쪽 원 점 수 · 셈에 사용'),('n_ring','고리 점 수 · 셈에 사용'),('views','영상 수')]:
        add(f,'MVS '+lab,'mvs_{v}_'+f,unit='개',bounds=None,group='점의 사정')
    add('cell','칸 · 참값 점검용','cell',unit='',bounds=None,group='참값 점검용',kind='category')
    add('shape','지붕꼴·벽꼴','roof_like',unit='',bounds=None,group='자리',kind='category')
    add('roof_type','지붕 형태 · 참값 점검용','roof_type',unit='',bounds=None,group='참값 점검용',prior='LoD2',kind='category')
    add('status','값 없음 까닭','mvs_{v}_status',unit='',bounds=None,group='점의 사정',kind='category')
    add('gt_p','참값의 자리','gt_p',bounds=(-50,50),group='참값 점검용',status='gt_status')
    for f,lab,unit,bounds in [('e','MVS 실제 오차','cm',(0,50)),('qe','MVS 실제 68.3 % 값','cm',(0,50)),('f','틀린 점의 비율','%',(0,100))]:
        add('mvs_'+f,lab,'mvs_{v}_'+f,unit=unit,bounds=bounds,group='참값 점검용',status='gt_status')
    add('prior_e','사전 정보 실제 오차',{'ALS':'als_e','LoD2':'eL'},group='참값 점검용',status='gt_status')
    add('missed','놓친 패치','@missed',unit='',bounds=None,group='참값 점검용',kind='category')
    add('weighted_e','무게 평균 자리의 오차','errW_{v}',group='참값 점검용',status='gt_status')
    return out

def main():
    p=CFG/'view_v1.json'
    if p.exists(): raise SystemExit('Already locked; amendments require a separate timestamped record.')
    config=dict(task_id='PHD-MAIN-UNCERT-VIEW-v1',made=now(),scientific_verdict=None,
        source_config_sha256=sha(U.CFGP),coordinate=dict(crs='EPSG:25832',frame='COLMAP model',world_shift_xyz_m=U.SHIFT,scale=1,north_up=True),
        cases=U.CASES,radii=[1.,1.5,3.],default_radii={s:float(v['pick']) for s,v in load(SRC/'work/ring_choice.json')['per_site'].items()},
        layers=layers(),seed=20261023,
        samples=dict(base='chosen radius, MVS a',cell_count=20,place_count=10,missed_top=30,z_top=20,roof_type_count=10,
            rule='Cell: in_eval and MVS status 0. Place: exact preceding places.npz membership. Missed: in_eval, status 0, finite e, e > .2 and e > 2u; order e/u descending (u=0 -> infinity). z: in_eval finite z descending. Roof type: LoD2 in_eval roof_like and status 0. Stable ties by ascending patch index. Random default_rng([seed,site ID,prior ID]); iterate cell order, sorted place names, sorted roof types. Unique union; preserve every selected patch.',
            radius_replay='u2_run.one_patch and its column/ring_points, same seed and order, before display thinning',
            display=dict(inner=400,ring=1600,gt=400,als=400,strip_width_m=.5,precision='float64 projected coordinates; lossless binary encoding',
                rule='Per version: shared inner set; union of all three exact ring sets, deduplicate global point indices, membership bits per radius; slice +/- .25m before seeded display-only cap. ALS cap over its inner/ring union.' )),
        encoding=dict(method='per-array exact-byte deduplication across radii; byte-shuffle; zlib; base64 classic scripts',lossy=False,limit_bytes=300_000_000),
        questions=[dict(id=1,layers=['mvs_u','mvs_e'],scope='three sites per prior',chart='uncertainty bins and rank',report='t61_u_vs_error'),
            dict(id=2,layers=['mvs_u','cell'],scope='three sites per prior',chart='wrong/right histograms, AUC and missed count/area',report=['t62_roc','t65_missed_edge']),
            dict(id=3,layers=['prior_u','prior_e'],scope='three ALS sites, optional exclude both correction cells',chart='uncertainty bins and rank',report='t61_u_vs_error'),
            dict(id=4,layers=['mvs_u','cell'],scope='current case, correction cells and refine',chart='three box plots',report='t63_changed'),
            dict(id=5,layers=['roof_type','prior_e'],scope='current LoD2 case, roof types; MVS a <=5 and <=10cm; GT all and excluding corr4p',chart='empirical CDF',report='t64_lod2'),
            dict(id=6,layers=['difference','gt_p'],scope='R1 ALS refine cell',chart='two signed histograms',report='t72_weighted_preview')],
        source_tables=U.CFG['tables'],status={0:'값 있음',1:'면 없음',2:'점 부족',3:'후보 평면 없음',-1:'확인 불가'},
        validation=dict(length_tolerance_cm=.1,ratio_rank_tolerance=.01,section_tolerance_m=.001),
        service=dict(port=8912,bind='0.0.0.0',container='jbgs-main-uncert-view-8912'),amendments=[])
    dump(p,config)
    dump(CFG/'view_v1.lock.json',dict(made=now(),sha256=sha(p),source_config_sha256=sha(U.CFGP),before_first_build=True,scientific_verdict=None))
    progress('일 2 설정 잠금 완료: 층·색 범위·표본 규칙·씨앗·확인 물음 고정. SHA-256은 view_v1.lock.json. 첫 웹 빌드 전 저장.')
    print(sha(p))

if __name__=='__main__': main()
