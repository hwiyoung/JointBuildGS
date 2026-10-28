"""Development-only summaries; truth is joined here after photo judgments exist."""
import collections
from common import *
from wall_prepare import table
from wall_measure import atomic_npz

def point_sets(stage='pilot'):
    grouped=collections.defaultdict(list)
    for f in sorted((O/'work'/stage).glob('*.npz')):
        if stage=='full' and not f.name.endswith('__LoD2.npz'):continue
        if f.with_suffix('.json').exists():grouped[f.name.split('__')[0]].append(npz(f))
    for tile,parts in sorted(grouped.items()):
        p={k:np.concatenate([a[k] for a in parts]) for k in parts[0]}
        assert len(np.unique(p['geometry_index']))==len(p['geometry_index'])
        order=np.argsort(p['geometry_index']);yield tile,{k:v[order] for k,v in p.items()}

def projection_gate():
    rows=[];n=k=0
    for stage in ['pilot','fallback']:
        for tile,p in point_sets(stage):
            mask=(abs(p['mvs_p'])<.05)&(p['raw_u_mvs']<.03)&(p['texture']>=5)&(p['selected_count']>=3)
            good=mask&np.isfinite(p['h_max'])&(abs(p['h_max'])<=.100001)
            n+=int(mask.sum());k+=int(good.sum())
            rows.append(dict(stage=stage,tile=tile,eligible_points=int(mask.sum()),within_10cm=int(good.sum())))
    complete=(O/'pilot_complete.json').exists()
    needs_fallback=complete and n<100 and not (O/'fallback_complete.json').exists()
    passed=complete and not needs_fallback and n>=100 and k/n>.5
    status='PASS' if passed else ('FALLBACK_REQUIRED' if needs_fallback else ('STOP' if complete else 'PENDING'))
    rec=dict(at=now(),status=status,eligible_points=n,within_10cm=k,fraction=k/n if n else None,minimum_points=100,rows=rows,uses_gt=False,scientific_verdict=None)
    dump(O/'gates/projection.json',rec);dump(D/'tables/projection_gate.json',rec);return rec

def distributions(rows,label,values,weights,bins=None):
    values=np.asarray(values);weights=np.asarray(weights);valid=np.isfinite(values)
    if bins is None:
        keys=np.unique(values[valid]);groups=[(str(x),values==x) for x in keys]
    else:groups=[(f'[{lo},{hi})',(values>=lo)&(values<hi)) for lo,hi in zip(bins[:-1],bins[1:])]
    for name,m in groups+[('확인 불가',~valid)]:rows.append(dict(measure=label,bin=name,points=int(m.sum()),area_m2=float(weights[m].sum())))

def summarize(stage='pilot'):
    cfg=load(C/'wallphoto_v1.json');patches=[];allpoints=[];exports=[]
    measured=list(point_sets(stage))
    if stage=='pilot' and measured and (O/'pilot_complete.json').exists():
        seen={t for t,_ in measured};empty={k:v[:0] for k,v in measured[0][1].items()}
        for f in sorted((O/'geometry').glob('*__LoD2.npz')):
            tile=f.stem.split('__')[0]
            if tile not in seen and np.isin(npz(f)['building'],EXAMPLES).any():measured.append((tile,empty))
    for tile,p in sorted(measured,key=lambda x:x[0]):
        raw=npz(W/'patch_values'/f'{tile}__LoD2__R1.5.npz');g=npz(O/'geometry'/f'{tile}__LoD2.npz');mp=npz(O/'geometry'/f'{tile}__LoD2__mapping.npz')
        lookup=np.full(len(g['point_id']),-1,np.int32);lookup[p['geometry_index']]=np.arange(len(p['point_id']))
        take=np.ones(len(mp['patch_id']),bool)
        if stage=='pilot':take=np.isin(raw['building'][mp['source_index']],EXAMPLES)
        source=mp['source_index'][take];pos=lookup[mp['point_index'][take]];done=pos>=0
        assert np.array_equal(raw['patch_id'][source],mp['patch_id'][take])
        judgment=np.full((len(source),15),-1,np.int8);judgment[done]=p['judgment'][pos[done]]
        ids=np.full(len(source),'',dtype=p['point_id'].dtype);ids[done]=p['point_id'][pos[done]]
        export=dict(patch_id=raw['patch_id'][source],point_id=ids,point_index=pos,judgment=judgment)
        pf=O/'patches'/f'{tile}__LoD2.npz';qf=O/'points'/f'{tile}__LoD2.npz';atomic_npz(pf,export);atomic_npz(qf,p)
        exports.append(dict(tile=tile,patches=len(source),measured_patches=int(done.sum()),points=len(p['point_id']),area_m2=float(raw['area'][source].sum()),measured_area_m2=float(raw['area'][source[done]].sum()),patch_sha256=sha(pf),point_sha256=sha(qf)))
        d={k:raw[k][source[done]] for k in ['patch_id','building','kind','area','cell','mvs_p','u_mvs','u_prior','roof_type','gt_p','gt_status','gt_n_inner']}
        sp,sm=sigmas(d,'LoD2');d['sigma']=sp;d['significant']=abs(d['mvs_p'])>3*np.sqrt(sp**2+sm**2);d['gt_valid']=(d['gt_status']==0)&np.isfinite(d['gt_p']);d['prior_right']=d['gt_valid']&(abs(d['gt_p'])<=3*sp)
        d['judgment']=p['judgment'][pos[done]];patches.append(d);allpoints.append(p)
    if not patches:return dict(status='WAITING',stage=stage)
    d={k:np.concatenate([x[k] for x in patches]) for k in patches[0]};p={k:np.concatenate([x[k] for x in allpoints]) for k in allpoints[0]}
    scopes=[('합',np.ones(len(d['area']),bool))]+[(str(b),d['building']==b) for b in np.unique(d['building'])]
    summary=[];cross=[];gt=[];coverage=[];dist=[]
    order=[4,0]+[i for i in range(15) if i not in [4,0]]
    for name,m in scopes:
        for k in order:
            for cell in [-1,0,1,2,3,4,5,6]:
                for significant in ['전체','유의','비유의']:
                    z=m.copy()
                    if cell>=0:z&=d['cell']==cell
                    if significant!='전체':z&=(d['significant'] if significant=='유의' else ~d['significant'])
                    den=float(d['area'][z].sum())
                    row=dict(building=name,combination=k,**cfg['judgments']['candidates'][k],cell=cell,significant=significant,patches=int(z.sum()),area_m2=den)
                    for j in range(5):row[LABELS[j]+'_m2']=float(d['area'][z&(d['judgment'][:,k]==j)].sum())
                    cross.append(row)
                    if cell==-1 and significant=='전체':summary.append(row)
            for j in range(5):
                z=m&(d['judgment'][:,k]==j);v=z&d['gt_valid'];den=float(d['area'][v].sum());num=float(d['area'][v&d['prior_right']].sum())
                gt.append(dict(building=name,combination=k,judgment=LABELS[j],patches=int(z.sum()),area_m2=float(d['area'][z].sum()),gt_area_m2=den,prior_right_area_m2=num,prior_right_fraction=num/den if den else None))
            for cell,j,label in [(1,1,'사전 정보만 틀림에서 반박'),(2,0,'영상만 틀림에서 지지'),(0,1,'둘 다 맞음에서 반박')]:
                for sig in [False,True]:
                    z=m&(d['cell']==cell)
                    if sig:z&=d['significant']
                    den=float(d['area'][z].sum());num=float(d['area'][z&(d['judgment'][:,k]==j)].sum())
                    gt.append(dict(building=name,combination=k,judgment=label,significant_only=sig,patches=int(z.sum()),area_m2=den,selected_area_m2=num,fraction=num/den if den else None))
    for name in ['합']+sorted(np.unique(p['building']).tolist()):
        m=np.ones(len(p['area']),bool) if name=='합' else p['building']==name
        den=float(p['area'][m].sum());num=float(p['area'][m&(p['selected_count']>=3)].sum())
        coverage.append(dict(building=name,azimuth='전체',points=int(m.sum()),area_m2=den,three_or_more_area_m2=num,fraction=num/den if den else None,vertical_views=int(p['selected_vertical_count'][m].sum()),oblique_views=int((p['selected_count'][m]-p['selected_vertical_count'][m]).sum())))
        sectors=((p['normal_azimuth_deg']+45)//90).astype(int)%4
        for k,label in enumerate(['북','동','남','서']):
            mm=m&(sectors==k);a=float(p['area'][mm].sum());b=float(p['area'][mm&(p['selected_count']>=3)].sum())
            coverage.append(dict(building=name,azimuth=label,points=int(mm.sum()),area_m2=a,three_or_more_area_m2=b,fraction=b/a if a else None))
        for key,bins in [('eligible_images',None),('selected_count',None),('parallax',[0,.2,.5,1,2,10,np.inf]),('max_direction_angle_deg',[0,15,30,45,60,90,180.001]),('texture',[0,5,10,20,40,256])]:
            rr=[];distributions(rr,key,p[key][m],p['area'][m],bins)
            dist.extend(dict(building=name,**r) for r in rr)
    prefix=stage+'_'
    for name,rows in [('judgment_15',summary),('cell_significant_15',cross),('truth_checks_15',gt),('photo_coverage',coverage),('distributions',dist),('exports',exports)]:table(prefix+name,rows)
    rec=dict(at=now(),stage=stage,points=len(p['point_id']),patches=len(d['area']),area_m2=float(d['area'].sum()),tiles=len(exports),three_or_more_fraction=coverage[0]['fraction'],scientific_verdict=None)
    dump(O/(stage+'_summary.json'),rec)
    return rec

def truth_quality():
    pieces=[]
    for f in sorted((W/'patch_values').glob('*__LoD2__R1.5.npz')):
        raw=npz(f);m=np.isin(raw['building'],EXAMPLES)&np.isin(raw['kind'],[1,2])
        if m.any():pieces.append({k:raw[k][m] for k in ['building','kind','area','gt_status','gt_p','gt_n_inner','mvs_p','u_mvs']})
    d={k:np.concatenate([x[k] for x in pieces]) for k in pieces[0]};rows=[];distrib=[]
    for b in ['합']+EXAMPLES:
        for kind,label in [(2,'벽'),(1,'지붕')]:
            m=(d['kind']==kind)&(True if b=='합' else d['building']==b);v=m&(d['gt_status']==0)&np.isfinite(d['gt_p']);same=v&(abs(d['mvs_p'])<=.05)&(d['u_mvs']<.03)
            x=abs(d['gt_p'][same]);median=float(np.median(x)) if len(x) else None;nmad=float(1.4826*np.median(abs(x-median))) if len(x) else None
            a=float(d['area'][m].sum());varea=float(d['area'][v].sum())
            rows.append(dict(building=b,kind=label,patches=int(m.sum()),area_m2=a,gt_patches=int(v.sum()),gt_area_m2=varea,gt_area_fraction=varea/a if a else None,agree_patches=int(same.sum()),agree_area_m2=float(d['area'][same].sum()),abs_gt_p_median_m=median,abs_gt_p_nmad_m=nmad,weighting='patch-wise median and NMAD; area-weighted availability'))
            counts=d['gt_n_inner'][m]
            rows[-1].update(gt_n_inner_median=float(np.median(counts)) if len(counts) else None,gt_n_inner_p90=float(np.quantile(counts,.9)) if len(counts) else None,gt_n_inner_max=int(counts.max()) if len(counts) else None)
            edges=[0,1,2,3,5,10,20,50,100,200,500,1000,5000,10000,np.inf]
            for lo,hi in zip(edges[:-1],edges[1:]):
                z=m&(d['gt_n_inner']>=lo)&(d['gt_n_inner']<hi);distrib.append(dict(building=b,kind=label,gt_n_inner_bin=f'[{lo},{hi})',patches=int(z.sum()),area_m2=float(d['area'][z].sum())))
    table('pilot_truth_quality',rows);table('pilot_gt_n_inner_distribution',distrib)

@locked_public
def report(stage='pilot'):
    inv=load(O/'inventory.json');summary=summarize(stage);gate=projection_gate();timing=load(O/'timing_first_building.json') if (O/'timing_first_building.json').exists() else {}
    pilot_summary=load(O/'pilot_summary.json') if (O/'pilot_summary.json').exists() else summary
    coverage=pilot_summary.get('three_or_more_fraction');hours=timing.get('full_cpu_hours');checks=[gate['status']=='PASS',coverage is not None and coverage>=.30,hours is not None and hours<=48]
    complete=(O/'pilot_complete.json').exists()
    decision=dict(at=now(),projection=checks[0],photo_coverage=checks[1],cpu_time=checks[2],coverage_fraction=coverage,cpu_hours=hours,uses_gt=False,decision='START_FULL' if complete and all(checks) else ('STOP_AFTER_PILOT' if complete and gate['status'] not in ['PENDING','FALLBACK_REQUIRED'] else 'PENDING'),scientific_verdict=None)
    dump(O/'gates/full_decision.json',decision);dump(D/'tables/full_decision.json',decision)
    total=sum(r['area_m2'] for r in inv['pilot']);count=sum(r['patches'] for r in inv['pilot'])
    text=f'''범위: 시험 7동 {count:,}패치, {total:,.3f} m². 완료 점 {summary.get('points',0):,}개, 완료 패치 {summary.get('patches',0):,}개. 줄인 비율은 sampling 기록과 표에 적음.
확인 불가: 아직 계산하지 않은 점, GPU 시간 어림. GPU를 사용하지 않음.
시간: 첫 건물 CPU {timing.get('seconds','확인 불가')}초. 자원 대기는 logs/resource_wait.log에 기록.

## 바꾼 줄
원본 common.py의 시험 건물 목록, JSON 원자 저장, 설정 파일 이름을 바꾸었다. prepare.group, Cameras, select_photos, compute, derive는 설정 파일 이름을 제외하고 구문 트리가 같다. source_changes.diff와 reference_contract.json 참조. 새 실행·보고 스크립트는 kind=2 LoD2만 선택한다. 면 법선과 접선을 그대로 써서 수식 변경은 없다. gt_p는 이 보고와 그림에서만 사용한다.

실행 메모리는 12 GiB, 이미지 임시 보관은 2 GiB, CPU는 8개로 제한한다. 32 GiB 상한 안에서 MESHPATCH 입장 여유 56 GiB를 남기기 위한 실행 조건이다. 양쪽 패치 표 완료 후에는 16 GiB 여유를 남긴다. 사진 조건·곡선·판단 값은 바뀌지 않는다.

## 투영과 시간
투영 상태 {gate['status']}. 조건을 채운 점 {gate['eligible_points']}개 가운데 10 cm 안 {gate['within_10cm']}개. 비율 {gate['fraction']}.
첫 건물 기준 시험 CPU {timing.get('pilot_cpu_hours','확인 불가')}시간, 전체 {hours if hours is not None else '확인 불가'}시간. GPU는 확인 불가.

## 표
tables/{stage}_photo_coverage: 사진 수·방위별 넓이와 연직/비스듬한 사진 수.
tables/{stage}_distributions: 사진 수·시차·방향 차·무늬 분포.
tables/{stage}_judgment_15: 보기 값 index 4, 1단계 값 index 0을 먼저 적음.
tables/{stage}_cell_significant_15: 일곱 칸 및 유의 불일치별 넓이.
tables/pilot_truth_quality와 pilot_gt_n_inner_distribution: 벽과 같은 건물 지붕의 참값 점검.
tables/{stage}_truth_checks_15: 판단마다 3σ 참값 점검. 참값을 확대 결정에 쓰지 않음.
원본 cell을 그대로 쓰며, 유의 불일치는 사진 확인 v1과 같은 합친 σ를 쓴다.

## 단계 나
투영 통과 {checks[0]}, 사진 3장 이상 넓이 30% 이상 {checks[1]}, CPU 48시간 이하 {checks[2]}. 결정 {decision['decision']}.
앞 네 건물은 참값으로 정의한 보존 넓이를 보고 선정했다. 일곱 동은 대표 표본이 아니다. 줄인 경우 판단 -1은 미계산이며 모름과 구분한다.

## 그림
figures/ 아래 PNG와 같은 이름 JSON. 생성하지 못한 그림은 진행.md에 사유를 적는다.

## 확인용
벽 {inv['holdout']['buildings']}동, {inv['holdout']['patches']:,}패치, {inv['holdout']['area_m2']:,.3f} m². SHA-256은 inventory.json에 있다. 판단·점 값은 공개하지 않는다.

scientific_verdict: null
'''
    assert len(text)<15000;(D/'벽사진확인_보고_v1.md').write_text(text)
    return summary,decision

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--stage',default='pilot');ap.add_argument('--quality',action='store_true');a=ap.parse_args()
    if a.quality:truth_quality()
    print(report(a.stage),flush=True)
