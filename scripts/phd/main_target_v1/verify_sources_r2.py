"""Parse task scripts, audit locked settings and preserve a prospective runtime binding."""
import ast
from common import *


def main():
    cfg,lock=locked_r2();files={}
    for root in [REPO/'scripts/phd/main_target_v1',REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19']:
        for f in sorted(root.rglob('*')):
            if not f.is_file():continue
            if f.suffix=='.py':ast.parse(f.read_text(),filename=str(f))
            files[str(f.relative_to(REPO))]=sha(f)
    for name in ['background_r2.lock.json','representatives_v1.json','decision_20261101_r2.txt']:
        files[str((CFG/name))]=sha(CFG/name)
    assert cfg['cylinder']['half_length_m']==dict(roof=10.,wall=5.)
    assert cfg['stage1']['bounds']['sigma_multiple']==1.96
    dump(OUT/'r2/verification/source_binding.json',dict(at=stamp(),status='PASS_PARSE_AND_BINDING',files=files,config_sha256=lock['config_sha256'],scientific_verdict=None))
    print('SOURCE_BINDING',len(files),flush=True)


if __name__=='__main__':main()
