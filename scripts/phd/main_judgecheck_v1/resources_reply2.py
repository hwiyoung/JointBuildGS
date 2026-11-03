"""Report measured elapsed time and conservative, auditable GPU queue intervals."""
import json
from datetime import datetime
from preflight import C,D,O,Path,sha,dump,now
BASE=O/'r2'
def stamp(s):return datetime.fromisoformat(s).timestamp()
def main():
    cfg=json.loads((C/'judgecheck_v1.json').read_text());start=next(r['at'] for r in cfg['amendments'] if r.get('authority')=='reply_2.txt');at=now();intervals=[];open_intervals=[];sources={}
    for p in sorted((BASE/'resources').glob('*_gpu_wait.tsv')):
        lines=[line.split('\t') for line in p.read_text().splitlines() if line.strip()];pending=None;queues={};sources[p.name]=sha(p)
        for cols in lines:
            t,action=cols[:2]
            if action=='pause':pending=t
            elif action=='resume' and pending:
                intervals.append(dict(start=pending,end=t,source=p.name,kind='paused'));pending=None
            elif action=='wait_before_start':queues.setdefault(cols[2] if len(cols)>2 else 'queue',[]).append(t)
        if pending:open_intervals.append(dict(start=pending,source=p.name,reason='no exact closing timestamp; excluded from recorded lower bound'))
        for key,times in queues.items():
            # First through last observed busy sample is proven waiting. Do not
            # invent the unobserved time after the last sample or before first.
            if len(times)>1:intervals.append(dict(start=times[0],end=times[-1],source=p.name,kind='before_start',target=key))
    merged=[]
    for lo,hi in sorted((stamp(v['start']),stamp(v['end'])) for v in intervals):
        if merged and lo<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],hi)
        else:merged.append([lo,hi])
    durations={}
    for folder,field in [('photo_prepared','total_seconds'),('photo_scores','total_seconds'),('cpu_benchmark','total_seconds')]:
        records=[]
        for p in sorted((BASE/folder).rglob('complete.json')) if (BASE/folder).exists() else []:
            r=json.loads(p.read_text())
            if field in r:
                rec=dict(path=str(p.relative_to(BASE)),seconds=r[field],device=r.get('device','cpu'),points=r.get('points',r.get('target_count')),source_sha256=sha(p))
                if folder in ['photo_scores','cpu_benchmark']:
                    rec.update(image_cache_seconds=r['image_cache_total_seconds'],upload_seconds=r['upload_seconds'],
                        arithmetic_excluding_upload_seconds=r['arithmetic_and_reduction_seconds']-r['upload_seconds'],
                        original_image_decodes=r['original_image_decodes'],peak_cpu_rss_gib=r['peak_cpu_rss_gib'],
                        camera_count=r['camera_count'],row_blocks=r['row_blocks'],decode_seconds=r['decode_seconds'],
                        image_supply=r.get('image_supply','frozen grayscale NPY cache'),
                        purpose='parity_sample' if p.parent.name=='verify' else 'whole_tile_benchmark' if len(p.relative_to(BASE/folder).parts)==2 else 'ordered_census')
                records.append(rec)
        if folder=='photo_prepared':
            for p in sorted((BASE/folder).glob('*.complete.json')):
                r=json.loads(p.read_text());records.append(dict(path=str(p.relative_to(BASE)),seconds=r[field],source_sha256=sha(p)))
        by_device={}
        for r in records:
            key=r.get('device','cpu');by_device.setdefault(key,dict(seconds=0,points=0));by_device[key]['seconds']+=r['seconds'];by_device[key]['points']+=r.get('points') or 0
            for component in ['image_cache_seconds','upload_seconds','arithmetic_excluding_upload_seconds']:
                if component in r:by_device[key][component]=by_device[key].get(component,0.)+r[component]
        by_image_supply={}
        for r in records:
            if 'image_supply' not in r:continue
            key=r['device']+' / '+r['image_supply']+' / '+r['purpose']
            acc=by_image_supply.setdefault(key,dict(completed_runs=0,points=0,seconds=0.,camera_visits=0,original_image_decodes=0,decode_seconds=0.))
            acc['completed_runs']+=1
            for key2 in ['points','seconds','original_image_decodes','decode_seconds']:acc[key2]+=r[key2] or 0
            acc['camera_visits']+=r['camera_count']
        durations[folder]=dict(seconds=sum(r['seconds'] for r in records),by_device=by_device,by_image_supply=by_image_supply,records=records)
    cohorts={}
    for plan_path in sorted((BASE/'cpu_cohorts').glob('group*/plan.json')):
        complete_path=plan_path.parent/'complete.json'
        if not complete_path.exists():continue
        plan=json.loads(plan_path.read_text());complete=json.loads(complete_path.read_text())
        cohorts[plan_path.parent.name]=dict(start=plan['at'],end=complete['at'],elapsed_seconds=stamp(complete['at'])-stamp(plan['at']),
            points=sum(json.loads((BASE/'photo_scores'/tile/f"group{plan['group']}"/'complete.json').read_text())['points'] for tile in complete['tiles']),workers=plan['settings']['workers'])
    result=dict(at=at,task_first_lock_at=cfg['created_at'],task_elapsed_seconds=stamp(at)-stamp(cfg['created_at']),reply2_start=start,elapsed_seconds=stamp(at)-stamp(start),gpu_wait_recorded_minimum_seconds=sum(hi-lo for lo,hi in merged),gpu_wait_intervals=intervals,unclosed_wait_intervals=open_intervals,cpu_cohort_elapsed=cohorts,
        wait_precision='lower bound from closed pause/resume intervals and first-to-last busy observations; overlaps merged; initial manual pause timestamp was recorded late and aborted sample has no exact final timestamp',
        measurement_totals=durations,totals_note='elapsed includes concurrent CPU work and GPU waiting; measured phase totals are not additive wall time; incomplete cache trials excluded from completed scoring totals',
        component_notes='CPU cohort NPY image_cache_seconds includes exclusive cache-lock waiting, which was not separately measured; JPEG decode occurs inside upload_seconds, while its prepare only indexes levels. Upload also includes array conversion/copy on CPU and host-to-device transfer on GPU. Arithmetic excludes this interval. The bounded JPEG LRU may decode a photo again across row blocks after eviction; camera visits and actual decodes are recorded separately. Timings from different target groups are not controlled speedup comparisons.',sources=sources,scientific_verdict=None)
    dump(BASE/'resource_receipt.json',result);dump(D/'tables/reply2_resource_receipt.json',result);print('RESOURCE_RECEIPT',result['elapsed_seconds'],result['gpu_wait_recorded_minimum_seconds'],flush=True)
if __name__=='__main__':main()
