"""Reconcile the stage-0 report with its completed numerical evidence."""
import re
from common import *


def main():
    cfg,lock=locked_r2()
    verify=json.loads((OUT/'r2/stage0/verification.json').read_text());assert verify['status']=='PASS_STAGE0_INDEPENDENT_CHECKS'
    report=DOC/'영역별목표학습_보고_r2.md';body=report.read_text()
    assert len(body)<20000 and len(re.findall(r'^## [1-8]\. ',body,re.M))==8
    links=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',body)
    for link in links:
        p=DOC/link;assert p.is_file() and p.with_suffix('.json').is_file()
    reference=json.loads((DOC/'tables/T2_historical_reference_r2.json').read_text())
    assert abs(reference['historical']['area_m2']-923.5357125585446)<1e-8
    assert abs(reference['historical']['fit']['T2_m']-.8548248176865011)<1e-10
    record=dict(at=stamp(),status='PASS_STAGE0_R2',report_sha256=sha(report),figure_pairs=len(links),
        config_sha256=lock['config_sha256'],source_binding_sha256=sha(OUT/'r2/verification/source_binding.json'),
        training_started=False,scientific_verdict=None)
    dump(OUT/'r2/stage0/status.json',record);dump(DOC/'tables/stage0_status_r2.json',record)
    dump(DOC/'tables/stage0_visual_review_r2.json',dict(at=stamp(),status='AGENT_REVIEWED',user_acceptance=False,
        figures=['r2_B173_wing_ALS.png'],observation='same section and vertical range; prior, MVS, reference and target differences retained, including targets below the reference',scientific_verdict=None))
    print(json.dumps(record),flush=True)


if __name__=='__main__':main()
