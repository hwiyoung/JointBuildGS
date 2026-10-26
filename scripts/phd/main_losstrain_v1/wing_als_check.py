"""6.8: bounded B173-wing prior-frame diagnosis; never gates training."""
import json
import numpy as np
from scipy.spatial import cKDTree
from inputs import OUT,PH,S0,W,save,sha

def main():
    sf=S0/'fork_inputs/s61/B173nb_b10/store_ALS.npz'
    wf=W/'patch_values/6911_53361__ALS__R1.5.npz';wj=wf.with_suffix('.json')
    with np.load(sf) as s,np.load(wf) as w:
        c=s['loc_center'];shift=s['frame_shift'];wc=w['centre'];raw=w['raw_centre']
        assert not w['holdout'].any()
        ws=np.asarray(json.loads(wj.read_text())['frame_shift'])
        assert np.allclose(wc-raw,ws,rtol=0,atol=1e-10)
        # The fixed figure section lies west of this tile's core. 6.8 instead
        # uses the named wing faces AND the named tile, without outcome labels.
        lf=S0/'fork_inputs/s61/B173nb_b10/store_LoD2.npz'
        with np.load(lf) as l:
            wing=np.isin(l['surf_ext'][l['loc_surface']],[33,38]);xy=l['loc_center'][wing,:2]
        cells=set()
        for x,y in np.floor(xy/.25).astype(np.int64):
            for dx in [-1,0,1]:
                for dy in [-1,0,1]:cells.add((int(x+dx),int(y+dy)))
        wing_mask=np.array([tuple(v) in cells for v in np.floor(c[:,:2]/.25).astype(np.int64)])
        tile=next(t for t in json.loads((W/'inputs/tiles.json').read_text()) if t['id']=='6911_53361')
        x0,y0,x1,y1=np.array(tile['core_global'])-[690953.,5336071.,690953.,5336071.]
        cr=c-shift;m=wing_mask&(cr[:,0]>=x0)&(cr[:,0]<x1)&(cr[:,1]>=y0)&(cr[:,1]<y1)
        d,idx=cKDTree(raw).query((c-shift)[m]);dr,_=cKDTree(wc).query(c[m])
        close=d<=.18;delta=wc[idx]-c[m]
        qstats=lambda x:dict(n=int(len(x)),min=float(np.min(x)),median=float(np.median(x)),p95=float(np.quantile(x,.95)),max=float(np.max(x))) if len(x) else None
        report=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',order_section='6.8',training_gate=False,site='B173nb_b10',prior='ALS',tile='6911_53361',
            region='LoD2 prior wing faces 33/38, XY 0.25 m grid dilated by one cell, intersect named tile raw core; no GT/outcome labels',
            tile_core_local_xy=[x0,y0,x1,y1],stage1_shift_m=shift.tolist(),widen_shift_m=ws.tolist(),
            shift_difference_m=(ws-shift).tolist(),stage1_section_patches=int(m.sum()),
            raw_nearest_distance_m=qstats(d),registered_nearest_distance_m=qstats(dr),raw_nearest_within_18cm=int(close.sum()),
            paired_height_difference_m=qstats(delta[close,2]),
            height_difference_after_removing_recorded_shift_m=qstats(delta[close,2]-(ws-shift)[2]),
            source=[dict(path=str(p),sha256=sha(p)) for p in [sf,wf,wj,lf]],GT_used=False,
            conclusion='The public tile records a -3.7582159107849065 m vertical registration while this stage-1 scene records zero vertical shift. Raw-centre and shifted-centre distances quantify this existing frame difference; neither surface is judged correct here.',
            limitation='Raw nearest centres are geometry diagnostics, not new training correspondence or validation of physical truth.',scientific_verdict=None)
        save(OUT/'checks/direct_stage1/wing_als_v2.json',report);save('/docs/tables/wing_als.json',report)
        print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
