"""Final document links, inspected figure identities and delivery state."""
import re
from cp2_common import *

def main():
    report=DOC/'원인확인_보고_v1.md';content=report.read_text()
    links=re.findall(r'\]\(([^)]+)\)',content)
    assert len(content)<=20000
    for link in links:assert (DOC/link).is_file(),link
    images=['curves_B173_LoD2_right.png','section_B173_LoD2_front.png','render_B173_LoD2_front.png']
    receipt=dict(at=now(),status='PASS_DOCUMENT_LINKS_AND_SELECTED_AGENT_VISUAL_REVIEW',
        report=bind(report),characters=len(content),local_links=len(links),
        agent_visually_inspected=[bind(DOC/'figures'/name) for name in images],
        visual_scope='Checked readable Korean, shared axes, saved moved centers, consistent crop and visible height maps. Other PNG files passed automated decode/metadata checks.',
        human_visual_acceptance='NOT_REQUESTED_OR_CLAIMED',source=SOURCE,scientific_verdict=None)
    save(DOC/'tables/final_review.json',receipt)
    ready=OUT/'delivery_ready.json'
    if ready.exists():
        old=OUT/'revisions/delivery_1738.json'
        assert not old.exists();old.write_bytes(ready.read_bytes())
    print('FINAL_REVIEW',len(content),len(links),'links',flush=True)

if __name__=='__main__':main()
