"""CPU aggregation of unmodified-forward tile observations, with exact conservation checks."""
import csv
import numpy as np
from common import *
from cause_r8_spatial import writecsv
ROOT=OUT/'r8_lod2_cause'

def main():
    config=json.loads((CFG/'cause_r8_lod2.json').read_text());b=json.loads((ROOT/'boundaries.json').read_text())
    assert sha(ROOT/'boundaries.json')==json.loads((CFG/'cause_r8_boundaries.lock.json').read_text())['sha256']
    cells=json.loads((ROOT/'counts.json').read_text())['rows'];viewrows=[];crossrows=[];tops=[];states=[];proof=[]
    for row in config['rows']:
        key=row['key'];dest=ROOT/'states'/key;inv=json.loads((dest/'inventory.json').read_text());rr=ROOT/'renders'/key
        summary=json.loads((rr/'summary.json').read_text());views=summary['views'];assert len(views)==203
        group=np.load(dest/'groups.npz')['group'];names={r['tag']:r['provenance'] for r in cells if r['state']==key};matrix=[]
        for v in views:
            p=rr/'tiles'/(v['camera']+'.npz');assert sha(p)==v['tile_sha256'];tiles=np.load(p)['tiles']
            assert len(tiles)==len(group) and int(tiles.astype('i8').sum())==v['total']
            counts=np.bincount(group,weights=tiles.astype('i8'),minlength=len(names)*16).astype('i8');assert int(counts.sum())==v['total'];matrix.append(counts)
            vr=dict(state=key,camera=v['camera'],view_index=v['index'],overlaps=v['total'],visible_gaussians=v['visible_gaussians'],
                binning_bytes=v['binning_bytes'],geom_bytes=v['geom_bytes'],image_bytes=v['image_bytes'],
                peak_cuda_allocated_bytes=v['peak_cuda_allocated_bytes'],peak_cuda_reserved_bytes=v['peak_cuda_reserved_bytes'],depth_equal=v['depth_byte_equal'],alpha_equal=v['alpha_byte_equal'])
            viewrows.append(vr)
            for t,name in names.items():
                for xi in range(4):
                    for zi in range(4):
                        n=int(counts[t*16+xi*4+zi]);crossrows.append(dict(state=key,camera=v['camera'],provenance=name,tag=t,xy_bin=xi,height_bin=zi,overlaps=n,fraction=n/v['total'] if v['total'] else None))
        np.savez_compressed(rr/'grouped_overlaps.npz',overlaps=np.array(matrix),cameras=np.array([v['camera'] for v in views]))
        top=sorted([v for v in viewrows if v['state']==key],key=lambda r:(-r['overlaps'],r['camera']))[:5]
        for i,v in enumerate(top):tops.append(dict(rank=i+1,**v))
        states.append(dict(state=key,gaussians=inv['gaussians'],overlaps_total=sum(v['total'] for v in views),overlaps_median=float(np.median([v['total'] for v in views])),
            overlaps_max=max(v['total'] for v in views),binning_max_GiB=max(v['binning_bytes'] for v in views)/2**30,
            tag_counts=inv['tags'],gradient=inv['gradient'],released_at100=inv['released_at100']))
        proof.append(dict(state=key,views=203,conserved_total=True,depth_equal_views=sum(v['depth_byte_equal'] for v in views),alpha_equal_views=sum(v['alpha_byte_equal'] is True for v in views),
            alpha_absent_in_reference_views=sum(v['alpha_byte_equal'] is None for v in views),observer_first_view_all_outputs_equal=summary['first_view_observer_parity']))
        print('GROUPED_LOAD',key,flush=True)
    writecsv(ROOT/'render_views.csv',viewrows);writecsv(ROOT/'render_cross.csv',crossrows);writecsv(ROOT/'top5.csv',tops)
    dump(ROOT/'render_views.json',dict(rows=viewrows,scientific_verdict=None));dump(ROOT/'render_cross.json',dict(rows=crossrows,scientific_verdict=None));dump(ROOT/'top5.json',dict(rows=tops,scientific_verdict=None))
    dump(ROOT/'summary.json',dict(at=stamp(),states=states,views=len(viewrows),proof=proof,scientific_verdict=None))

if __name__=='__main__':main()
