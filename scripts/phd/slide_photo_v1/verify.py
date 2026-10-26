"""Bounded delivery validation; no rewriting source outputs."""
import json,sys
from PIL import Image
from common import *
def main():
    c=config();items=[];sizes={'figS_c_':(1500,1260),'figS_a_':(2700,1200),'figS_d_':(3200,800),'figS_e_':(1080,600),'figS_b_':(3200,1077)}
    for p in sorted((DOC/'figures').glob('figS_*.png')):
        prefix=next(k for k in sizes if p.name.startswith(k));im=Image.open(p);assert im.size==sizes[prefix],(p,im.size);assert p.with_suffix('.json').exists();meta=load(p.with_suffix('.json'));assert meta['scientific_verdict'] is None
        items.append(dict(file=p.name,size_px=list(im.size),sha256=sha(p),metadata_sha256=sha(p.with_suffix('.json')),status='PASS'))
    expected=10;done=len(items)
    # Display-only thinning never enters a quantity. Validate configured legibility.
    font_slide_px={k:c['output']['font_min_px'][k]*{'a':900/2700,'b':1664/3200,'c':500/1500,'d':1600/3200}[k] for k in ['a','b','c','d']}
    assert min(font_slide_px.values())>=24
    doc=dict(status='PASS' if done==expected else 'PARTIAL',rendered_count=done,expected_count=expected,figures=items,configured_minimum_slide_font_px=font_slide_px,config_sha256=sha(CFG/'slide_photo_v1.json'),amendment_sha256={p.name:sha(p) for p in CFG.glob('amendment*.json')},scientific_verdict=None)
    dump(DOC/'verification.json',doc);print({k:v for k,v in doc.items() if k!='figures'})
if __name__=='__main__':main()
