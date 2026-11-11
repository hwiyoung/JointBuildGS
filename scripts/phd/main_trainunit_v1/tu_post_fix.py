"""Host: finish one site's mesh with the tolerance merge (tu_merge_tol.py), then the unchanged finish and score steps.
  python3 tu_post_fix.py <run_key> <site> <prior>
"""
import json
import sys
from tu_post import M, R, TU, family_of, gt_cpu, sh, score, now, dump, progress, issue


def main(key, site, prior):
    fam = family_of(key)
    stem = f'{site}__{prior}'
    tag = f'{stem}-{fam}'.replace('_', '-').lower()
    cmd = gt_cpu(f'{tag}-mergetol', 'x')
    i = cmd.index('jointbuildgs:dev')
    cmd = cmd[:i] + [] + cmd[i:]
    cmd[cmd.index('/repo/scripts/phd/main_gtjudge_v1/x')] = '/tuscripts/tu_merge_tol.py'
    j = cmd.index('--entrypoint')
    cmd = cmd[:j] + ['-v', f'{R}/scripts/phd/main_trainunit_v1:/tuscripts:ro'] + cmd[j:]
    cmd += [site, prior, fam]
    ok = sh(cmd, M / 'logs' / f'mesh-{tag}.log')
    ok = ok and sh(gt_cpu(f'{tag}-finish', 'mesh_job.py', site, prior, fam, 'finish'), M / 'logs' / f'mesh-{tag}.log')
    ok = ok and score(key, site, prior)
    dump(TU / 'post' / key / f'{site}_merge_tolerance.json', dict(at=now().isoformat(), key=key, site=site, prior=prior, ok=bool(ok),
         merged=json.loads((M / 'meshes' / f'{stem}__{fam}' / 'final_work/merged.json').read_text()) if ok else None, scientific_verdict=None))
    progress(f'후처리 {key} {site}: 허용 합치기로 {"완료" if ok else "실패"}')
    if ok:
        dump(TU / 'post' / key / 'done.json', dict(at=now().isoformat(), key=key, sites=[site], ok=[True], merge='tolerance 1e-12 m', scientific_verdict=None))


if __name__ == '__main__':
    main(*sys.argv[1:])
