"""Bounded delivery validation; no rewriting source outputs."""
import json,sys,ast
from PIL import Image
from common import *
def main():
    c=config();items=[];sizes={'figS_c_':(1500,1260),'figS_a_':(2700,1200),'figS_d_':(3200,800),'figS_e_':(1080,600),'figS_b_':(3200,1077)}
    for p in sorted((DOC/'figures').glob('figS_*.png')):
        prefix=next(k for k in sizes if p.name.startswith(k));im=Image.open(p);assert im.size==sizes[prefix],(p,im.size);assert p.with_suffix('.json').exists();meta=load(p.with_suffix('.json'));assert meta['scientific_verdict'] is None
        qa=load(DOC/'qa'/p.with_suffix('.json').name)
        assert qa.get('round1',{}).get('answer'),p
        assert 'PENDING' not in qa['status'],p
        if 'revision' in qa:assert qa.get('round2',{}).get('answer'),p
        items.append(dict(file=p.name,size_px=list(im.size),sha256=sha(p),metadata_sha256=sha(p.with_suffix('.json')),blind_review=qa['status'],status='PASS'))
    expected=10;done=len(items)
    # Display-only thinning never enters a quantity. Validate configured legibility.
    font_slide_px={k:c['output']['font_min_px'][k]*{'a':900/2700,'b':1664/3200,'c':500/1500,'d':1600/3200}[k] for k in ['a','b','c','d']}
    assert min(font_slide_px.values())>24
    actual_fonts={}
    scales={'draw_a.py':900/2700,'draw_b.py':1664/3200,'draw_c_legacy.py':500/1500,'draw_c_specular.py':500/1500,'draw_d.py':1600/3200}
    for p in (REPO/'scripts/phd/slide_photo_v1').glob('*.py'):
        tree=ast.parse(p.read_text(),filename=str(p))
        if p.name not in scales:continue
        pts=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                for k in node.keywords:
                    if k.arg in ['fontsize','labelsize'] and isinstance(k.value,ast.Constant):pts.append(float(k.value.value))
                if isinstance(node.func,ast.Name) and node.func.id=='plot_setup':pts.append(float(node.args[0].value))
        actual_fonts[p.name]=dict(min_points=min(pts),dpi=100,min_slide_px=min(pts)*100/72*scales[p.name])
    assert min(v['min_slide_px'] for v in actual_fonts.values())>24
    expected_names={'figS_a_image_limits.png','figS_b_correction_sections.png','figS_c_change.png','figS_c_repr.png','figS_c_specular.png','figS_d_gs_real.png'}|{f'figS_e_aim_{n}.png' for n in ['keep','correct','refine','inherit']}
    assert {x['file'] for x in items}==expected_names
    doc=dict(status='PASS' if done==expected else 'PARTIAL',scope='file, dimension, metadata, completed blind-review record and newly authored text size checks; not a claim that all intended messages passed',rendered_count=done,expected_count=expected,figures=items,configured_minimum_slide_font_px=font_slide_px,actual_script_font_sizes=actual_fonts,font_exception='B reuses mandated original REGIONFIG marked photographs byte-for-byte; their embedded small original labels are not newly authored 24px text.',config_sha256=sha(CFG/'slide_photo_v1.json'),amendment_sha256={p.name:sha(p) for p in CFG.glob('amendment*.json')},scientific_verdict=None)
    dump(DOC/'verification.json',doc);print({k:v for k,v in doc.items() if k!='figures'})
if __name__=='__main__':main()
