"""Bundle PHD-MAIN-TRAINLOG-v1_<stage>_<MMDD>-<HHMM>.zip (order 6). Payload files that are large are listed with sha256 only."""
import sys, zipfile, datetime as dt
from common import *
STAGES = {
    'stage1': dict(docs=['단계1_보고.md', 'issues.md', 'progress.md', 'r27_changed_lines.diff', 'camera_choice.json', 'tables/unit_checks_gpu_repeat.csv', 'tables/unit_checks_event_balance.csv', 'tables/unit_checks_r23_diagnostic.csv', 'tables/camera_choice.csv', 'verification'],
                   cfg=['trainlog_v1.json', 'trainlog_v1.lock.json', 'trainlog_v1.unitcheck_v2.json', 'trainlog_v1.unitcheck_v2.lock.json'], payload=[]),
    'stage3_compare': dict(docs=['단계3_대조표.md', 'comparison.json', 'tables/comparison_original_vs_new.csv', 'issues.md', 'progress.md'], cfg=['trainlog_v1.json', 'trainlog_v1.lock.json', 'trainlog_v1.runtime.lock.json'], payload=[]),
}
def main(stage):
    spec = STAGES[stage]; stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')
    out = O/'delivery'/f'PHD-MAIN-TRAINLOG-v1_{stage}_{stamp}.zip'; out.parent.mkdir(parents=True, exist_ok=True); members = []
    with zipfile.ZipFile(out, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        def add(src, arc):
            z.write(src, arc); members.append(dict(path=arc, bytes=src.stat().st_size, sha256=sha(src)))
        for rel in spec['docs']:
            p = D/rel
            for f in ([p] if p.is_file() else sorted(q for q in p.rglob('*') if q.is_file())): add(f, 'docs/'+str(f.relative_to(D)))
        for rel in spec['cfg']: add(C/rel, 'configs/'+rel)
        for rel in ['scripts/phd/main_trainlog_v1', 'src/phd/forks/GeoGS-conf-guided-v1-r27/jbgs_trainlog.py']:
            p = R/rel
            for f in ([p] if p.is_file() else sorted(q for q in p.rglob('*.py') if '__pycache__' not in q.parts)): add(f, 'code/'+str(f.relative_to(R)))
        manifest = dict(at=now(), stage=stage, members=members, scientific_verdict=None)
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
    (out.with_suffix('.zip.sha256')).write_text(sha(out)+'  '+out.name+'\n')
    print('PACKAGE', out, sha(out), len(members), flush=True)
if __name__ == '__main__': main(sys.argv[1])
