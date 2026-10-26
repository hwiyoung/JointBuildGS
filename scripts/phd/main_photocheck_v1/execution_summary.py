"""Aggregate execution time and memory, exposing no holdout-dependent outcome values."""
from common import *
def main():
    rows=[];all_curves=0.;all_selection=0.;new_points=0;reused=0;peak_rss=0.;peak_container=0
    for base in [O,O/'holdout']:
        for f in (base/'work/full').glob('*.json'):
            if f.stem.endswith('_selection') or f.stem.endswith('_progress'):continue
            r=load(f);all_curves+=r['seconds'];all_selection+=r['selection_seconds'];new_points+=r['points'];reused+=r.get('reused_pilot_points',0)
            e=r['environment'];peak_rss=max(peak_rss,e.get('peak_rss_gib',0));peak_container=max(peak_container,e.get('cgroup_memory',{}).get('memory.peak',0))
    for f in (O/'work/pilot').glob('*.json'):
        if f.stem.endswith('_selection') or f.stem.endswith('_progress'):continue
        r=load(f);rows.append(r)
    wait=sum(float(p.read_text()) for p in (O/'logs').glob('*_gpu_wait_seconds.txt'))
    first=dt.datetime.fromisoformat(load(O/'input_preflight.json')['at']);last=dt.datetime.fromisoformat(now())
    result=dict(at=now(),input_preflight_at=first.isoformat(),elapsed_from_input_preflight_hours=(last-first).total_seconds()/3600,
      completed_full_curve_seconds=all_curves,full_selected_photo_seconds=all_selection,new_full_points=new_points,reused_pilot_roof_points=reused,
      valid_pilot_curve_seconds=sum(r['seconds'] for r in rows),valid_pilot_photo_selection_seconds=sum(r['selection_seconds'] for r in rows),gpu_wait_seconds=wait,
      peak_completed_curve_process_rss_gib=peak_rss,peak_recorded_container_memory_bytes=peak_container,enforced_container_memory_bytes=32*1024**3,
      timing_note='Per-stage operation sums may overlap with CPU preparation. Wall time includes validation and GPU/disk waits. Invalid early benchmark attempts and intentionally interrupted work remain in logs and are not presented as valid throughput.',
      scientific_verdict=None)
    dump(O/'execution_summary.json',result);dump(D/'tables/execution_summary.json',result);print('execution summary saved')
if __name__=='__main__':main()
