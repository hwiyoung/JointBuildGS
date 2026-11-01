"""Combined requested checkpoint table, preserving unavailable and pending rows."""
import sys,csv
from common import *
def read(p):return json.loads(p.read_text())
def csvout(name,rows):
    if not rows:return
    with (DOC/'tables'/name).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    mode=sys.argv[1];assert mode in ['7000','final'];old=read(CFG/'scoring_continue_r7.r1.json');new=read(CFG/'scoring_r8.json');rows=[r for r in old['rows']+new['rows'] if mode=='final' or r['iteration']==7000];metrics=[];axes=[];clumps=[];states=[]
    for row in rows:
        root=OUT/('r8' if row['family']=='r8' else 'r7_continue')
        for kind in ['current','final']:
            p=root/'scoring'/row['key']/kind/'values.json'
            if not p.exists():
                state='NOT_REACHED' if row['family']=='r7' and row['prior']=='ALS' and row['iteration']>7000 else 'PENDING'
                if row['family']=='r8' and (OUT/'r8'/f'STOP_{row["prior"]}.json').exists() and not (OUT/'r8/runs'/row['name']/f'model/point_cloud/iteration_{row["iteration"]}/point_cloud.ply').exists():state='NOT_REACHED'
                states.append(dict(key=row['key'],kind=kind,status=state));continue
            r=read(p);assert r['status']=='PASS';states.append(dict(key=row['key'],kind=kind,status='PASS',sha256=sha(p)));common=dict(prior=row['prior'],family=row['family'],iteration=row['iteration'],kind=kind)
            for cell,b in r['metrics'].items():
                s=r['surface'].get(cell,{})
                metrics.append(dict(**common,cell=cell,R_tau=b['gt'].get('R_tau'),P_tau=b['res']['E'].get('P_tau'),gt_mean_cm=b['gt'].get('mean'),res_mean_cm=b['res']['E'].get('mean'),n_gt=b['gt']['n_gt'],n_result=b['res']['E']['n'],floating_fraction=s.get('floating_fraction'),no_surface_fraction=s.get('no_surface_fraction')))
            for axis,blocks in r['axes'].items():
                for bin,v in blocks.items():axes.append(dict(**common,axis=axis,bin=bin,n_gt=v['n_gt'],n_res=v['n_res'],R_tau=v['R_tau'],P_tau=v['P_tau'],gt_mean_cm=v['mean'],res_mean_cm=v['res_mean']))
            for cell,b in r['clumps'].items():
                for threshold,v in b['hits'].items():clumps.append(dict(**common,cell=cell,threshold=threshold,clumps=v['clumps'],hit=v['hit'],rate=v['rate']))
    result=dict(at=stamp(),status='MEASUREMENTS_ONLY',mode=mode,states=states,metrics=metrics,axes=axes,clumps=clumps,comparison_reference='unchanged AXES71-v2 tables and r8_compare figures; original mixed visible/invisible mesh rule retained for reference rows',scientific_verdict=None)
    dump(DOC/'tables'/f'r8_all_meshes_{mode}.json',result)
    for suffix,data in [('metrics',metrics),('axes',axes),('clumps',clumps)]:csvout(f'r8_all_meshes_{mode}_{suffix}.csv',data)
    print('R8_COMBINED_TABLE',mode,len([x for x in states if x['status']=='PASS']),len(states),flush=True)
if __name__=='__main__':main()
