"""Check the addendum-5 report against saved counts, then seal this audit only."""
from common import *
import re

def main():
    doc=Path('/docs');report=doc/'ch6_impl_check.md';meta=doc/'provenance/ch6_impl_check.json'
    data=json.loads(meta.read_text());text=report.read_text()
    initial=json.loads((C/'ch6_impl_check.initial.lock.json').read_text())
    assert initial['config_sha256']==sha(C/'ch6_impl_check.json')
    assert initial['script_sha256']==sha(Path(__file__).with_name('ch6_impl_check.py'))
    assert sha(doc/'tables/ch6_tau_residual_ratios.csv')==data['csv_sha256']
    for r in data['residual_rows']:
        name='R2 (B173 주변)' if r['search_region']=='R2' else r['search_region']
        surface='항공 LiDAR' if r['prior']=='ALS' else 'LoD2 '+('지붕' if r['surface']=='roof' else '벽')
        line=f"| {name} | {surface} | {r['n_finite']:,} | {r['tau_cm']:.1f} | {r['pct_abs_gt_tau']:.4f} | {r['pct_abs_gt_2m']:.4f} |"
        assert line in text,line
    hostbase='/media/innopam/InnoPAM-8TB/hwiyoung/code/'
    files={}
    for target in re.findall(r'\]\((/[^)]+)\)',text):
        match=re.fullmatch(r'(.*?)(?::(\d+))?',target);path,line=match.groups()
        path=path.replace(hostbase+'JointBuildGS-exp/','/repo/').replace(hostbase+'JointBuildGS-artifacts/','/art/')
        p=Path(path);assert p.is_file(),target
        if line:assert int(line)<=len(p.read_text().splitlines()),target
        files[target]=sha(p)
    files[str(report)]=sha(report);files[str(meta)]=sha(meta)
    final=C/'ch6_impl_check.final.lock.json';assert not final.exists()
    dump(final,dict(at=now(),status='PASS_REPORT_TABLES_LINKS_AND_PROVENANCE',source_files=files,
                    config_sha256=sha(C/'ch6_impl_check.json'),script_sha256=sha(Path(__file__).with_name('ch6_impl_check.py')),
                    seal_script_sha256=sha(__file__),checks=['9 report rows match saved ratios','CSV hash matches counting receipt',
                    'all cited local files and line numbers exist','initial config and counting script unchanged'],
                    legacy_reproduction_rerun=False,mesh_or_score_rebuild=False,scientific_verdict=None))
    print('PASS_REPORT_TABLES_LINKS_AND_PROVENANCE',len(files),flush=True)

if __name__=='__main__':main()
