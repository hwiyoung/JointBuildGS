"""Read-only progress counters; incomplete pilot is never a passed gate."""
from common import *
from run_measure import selected_geometry
def main():
    out=[]
    for prior in ['LoD2','ALS']:
        total=0;done=0;n=0;k=0;files=0
        for t in load(W/'inputs/tiles.json'):
            g,_=selected_geometry('pilot',t['id'],prior);total+=len(g['kind'])
            f=O/'work/pilot'/f'{t["id"]}__{prior}.npz'
            if not f.exists():continue
            p=npz(f);files+=1;done+=len(p['kind']);m=(p['kind']==1)&(abs(p['mvs_p'])<.05)&(p['raw_u_mvs']<.03)&(p['texture']>=5)&(p['selected_count']>=3)
            n+=int(m.sum());k+=int((m&(abs(p['h_max'])<=.100001)).sum())
        out.append(dict(prior=prior,total_including_observation_wall=total,completed_points=done,completed_files=files,gate_eligible_so_far=n,gate_within10cm_so_far=k))
    print(json.dumps(out,ensure_ascii=False));dump(O/'pilot_progress.json',dict(at=now(),rows=out,gate_status='PENDING'))
if __name__=='__main__':main()
