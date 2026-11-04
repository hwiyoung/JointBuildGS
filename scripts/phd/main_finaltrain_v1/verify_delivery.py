"""Check the per-arm report binding, figures and required numerical records."""
import sys
from PIL import Image
from common import *

def main(site,prior):
    stem=f'{site}__{prior}';report=json.loads((O/'reports'/f'{stem}.json').read_text());rows=[]
    if report['status']=='TRAINING_COMPLETE_30000' and not report['scored']:
        assert report.get('post',{}).get('status')=='UNAVAILABLE_ORIGINAL_VIRTUAL_VIEWS'
        assert not (O/'rescore/scores'/('ft_'+stem)/'values.json').exists()
        assert not report['figures']
    if report['scored']:
        value=json.loads((O/'rescore/scores'/('ft_'+stem)/'values.json').read_text())
        table=json.loads((D/'tables'/f'table3_{stem}.json').read_text())['rows'];row=next(x for x in table if x['family']=='finaltrain')
        for key in ['n_gt','n_result','completeness','accuracy','gt_mean_m','result_mean_m']:assert row[key]==value['scene'][key],key
        for number in [3,5]:
            path=D/'figures'/f'{stem}_그림7_{number}_{prior}.png';meta=json.loads(path.with_suffix('.json').read_text())
            assert meta['method']=='ft_'+stem and meta['scientific_verdict'] is None and meta['provisional'] is False
            with Image.open(path) as im:
                im.verify();size=im.size;assert min(size)>=1000
            rows.append(dict(file=str(path),sha256=sha(path),width=size[0],height=size[1]))
    if report['status']=='TRAINING_COMPLETE_30000':
        target_rows=json.loads((D/'tables'/f'table6_{stem}.json').read_text())['rows']
        core=loadz(JA/'core_points'/f'{stem}.npz',['area'])
        assert abs(sum(r['area_m2'] for r in target_rows)-float(core['area'].sum()))<1e-6
        model=Path(json.loads((O/'runs'/site/f'ft_{prior}_s0/receipt.json').read_text())['attempts'][-1]['model'])
        for it in [7000,15000,30000]:
            for name in [f'health_{it}.json',f'release_{it}.json',f'snapshot_{it}.npz']:assert (model/'target_monitor'/name).exists(),name
    dump(O/'verification'/f'delivery_{stem}.json',dict(at=now(),status='PARTIAL_UNAVAILABLE_FINAL_MESH' if report.get('post') else 'PASS',training_status=report['status'],score_table_binding=True if report['scored'] else None,
        exported_figures=rows,visual_inspection='separate human-visible image inspection required',scientific_verdict=None))
    print('DELIVERY_CHECK_PASS',stem,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
