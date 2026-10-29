"""Inspect source sizes and predict fresh-process cleanup working memory."""
import argparse
import json
from pathlib import Path
from mesh_common import C, D, O, dump, mesh_config, now


def header(path):
    values={}
    with Path(path).open('rb') as stream:
        for _ in range(1000):
            line=stream.readline().decode('ascii').strip()
            if line.startswith('element '):
                _,kind,size=line.split();values[kind]=int(size)
            if line=='end_header':return values
    raise ValueError('Invalid PLY header: '+str(path))


def plan():
    from mesh_staged import policy
    policy()
    # A conservative prior until a fresh-process probe supplies an observed peak.
    # This only controls admission; scientific inputs and geometry stay unchanged.
    slope=480.;fixed=2*1024**3;observations=[]
    for p in sorted((O/'mesh_stages_v1').glob('*/cleanup.json')):
        if not p.with_name('cleanup_execution.json').exists():continue
        r=json.loads(p.read_text());e=json.loads(p.with_name('cleanup_execution.json').read_text())
        n=r['result']['before_triangles'];peak=e['peak_observed_bytes']
        observations.append(dict(key=p.parent.name,triangles=n,peak_bytes=peak))
    if observations:
        slope=max(max(0,r['peak_bytes']-fixed)/r['triangles'] for r in observations)*1.15
    rows=[]
    for row in mesh_config()['targets']:
        if row['status']!='READY':continue
        size=header(row['mesh']);estimate=int(fixed+slope*size['face'])
        done=(D/'tables/meshes'/f"{row['key']}.json").exists()
        cleanup=O/'mesh_stages_v1'/row['key']/'cleanup.json'
        receipt=cleanup.with_name('cleanup_execution.json')
        failed=receipt.exists() and json.loads(receipt.read_text())['exit_code']!=0
        disposition='COMPLETE' if done else 'CLEANUP_CACHED' if cleanup.exists() else 'WAIT_RESOURCE_REVIEW' if failed or estimate>36*1024**3 else 'ADMIT_STAGED'
        rows.append(dict(key=row['key'],vertices=size['vertex'],triangles=size['face'],
            estimated_cleanup_peak_gib=estimate/1024**3,disposition=disposition))
    data=dict(created_at=now(),host_available_gib=56,stable_seconds=60,container_limit_gib=40,
        proactive_stop_gib=38,estimated_admission_ceiling_gib=36,baseline_bytes=fixed,bytes_per_triangle=slope,
        observations=observations,rows=rows,
        note='Source PLY headers and observed fresh-process peaks; 15% slope margin, 2 GiB base. Unmeasured prior 480 bytes/triangle. A planned probe may bypass size prediction, never the resource lock, host gate, 40 GiB cap or 38 GiB stop. Failed attempts are not repeated automatically.',
        scientific_verdict=None)
    executions=[dict(path=str(p),**json.loads(p.read_text())) for p in sorted((O/'mesh_stages_v1').glob('*/*_execution.json'))]
    dump(D/'tables/mesh_memory_executions.json',dict(records=executions,created_at=now(),scientific_verdict=None))
    dump(D/'tables/mesh_memory_plan.json',data);return data


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--key');ap.add_argument('--finish-probe',action='store_true');args=ap.parse_args();p=plan()
    if args.finish_probe:
        dump(O/'status/memory_bootstrap_done.json',dict(at=now(),observations=p['observations'],scientific_verdict=None))
    if args.key:
        row=next(r for r in p['rows'] if r['key']==args.key);print(json.dumps(row))
        if row['disposition']=='WAIT_RESOURCE_REVIEW':raise SystemExit(75)
    else:print(json.dumps(dict(targets=len(p['rows']),observations=p['observations'],deferred=[r for r in p['rows'] if r['disposition']=='WAIT_RESOURCE_REVIEW']),ensure_ascii=False))
