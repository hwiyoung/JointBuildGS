"""Order 6 lists: states/ (paths + sha256; files stay in the payload), scene dumps, events, meshes with scores and timings (CPU)."""
from common import *
M = D/'manifests'

def main():
    M.mkdir(exist_ok=True); saves = [json.loads(l) for l in (RUNM/'trainlog/saves.jsonl').read_text().splitlines()]; rows = []
    for s in saves:
        a = RUNM/'trainlog/states'/f'{s["name"]}.npz'; b = DER/'gaussians'/f'{s["name"]}.npz'; c = RUNM/'trainlog/scene'/f'{s["name"]}.pt'
        rows.append(dict(state=s['name'], iteration=s['iteration'], seq=s['seq'], scene_gaussians=s['gaussians'], in_scope=s['inside'], phase=s['phase'],
                         raw_state=str(a), raw_sha256=sha(a), derived_state=str(b), derived_sha256=sha(b), scene_dump=str(c), scene_dump_bytes=c.stat().st_size))
    table('states', rows, folder=M)
    ev = json.loads((DER/'events/events_receipt.json').read_text()); table('events', [dict(kind=k, **({'rows': v} if isinstance(v, int) else dict(rows=v['rows'], npz=str(DER/'events'/f'{k}.npz'), npz_sha256=v['npz_sha256'], csv=str(DER/'events'/f'{k}.csv.gz'), csv_sha256=v['csv_sha256'], columns=' '.join(v['columns'])))) for k, v in ev['kinds'].items()], folder=M)
    tm = {}
    for l in (O/'logs/mesh_timing.jsonl').read_text().splitlines():
        r = json.loads(l)
        if r['exit_code'] == 0: tm.setdefault(r['family'], {}).setdefault(r['step'].split(':')[0], 0.); tm[r['family']][r['step'].split(':')[0]] += r['seconds']
    mr = []
    for p in sorted((O/'meshes').glob('tl_*/score.json')):
        fam = p.parent.name; s = json.loads(p.read_text()); r1 = next(r for r in s['rows'] if r['case_id'] == 1); ply = O/'gtj/meshes'/f'{STEM}__{fam}'/'final.ply'
        t = tm.get(fam, {}); mr.append(dict(family=fam, mesh=str(ply), mesh_sha256=sha(ply), case1_completeness_pct=r1['completeness_pct'], case1_accuracy_pct=r1['accuracy_pct'],
                       **{f'seconds_{k}': round(v, 1) for k, v in t.items()}, seconds_total=round(sum(t.values()), 1)))
    for r in mr:
        k = r['family'][3:]; e = O/'analysis'/f'mesh_{k}.npz'; j = O/'analysis'/f'mesh_{k}.json'
        if e.exists(): r.update(vertex_error_file=str(e), vertex_error_sha256=sha(e), **{('scope_'+a): b for a, b in json.loads(j.read_text()).items() if a in ('faces_in_scope', 'vertex_error_abs_median_m', 'within_tau_fraction')})
    table('meshes', mr, folder=M)
    rr = []
    for d in sorted((O/'renders').iterdir()):
        if d.is_dir(): rr.append(dict(state=d.name, files=len(list(d.glob('*.png'))), data=str(d/'data.npz'), data_sha256=sha(d/'data.npz'), **{k: v for k, v in json.loads((d/'render.json').read_text()).items() if k.endswith('psnr')}))
    table('renders', rr, folder=M); print('MANIFESTS', len(rows), len(mr), len(rr), flush=True)
if __name__ == '__main__': main()
