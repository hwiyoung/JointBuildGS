"""Decode each requested figure once and make inspection sheets outside delivery figures."""
import sys,math
from common import *
from PIL import Image,ImageDraw
def main(label):
    if label=='단계01':files=sorted([*D.glob('figures/*_stage0_*.png'),*D.glob('figures/*_stage1_*.png')])
    elif label=='단계2':files=sorted(D.glob('figures/*_stage2_*.png'))
    elif label=='all':files=[]
    else:
        site,prior,arm=label.rsplit('_',2);files=sorted(D.glob(f'figures/{site}__{prior}_{arm}_*.png'))
    root=O/'verification/visuals'/label;root.mkdir(parents=True,exist_ok=True);pages=[];records=[]
    for start in range(0,len(files),3):
        sheet=Image.new('RGB',(2200,1800),'white');draw=ImageDraw.Draw(sheet)
        for j,p in enumerate(files[start:start+3]):
            with Image.open(p) as im:
                im.load();assert im.width>1000 and im.height>1000
                assert p.with_suffix('.json').exists()
                records.append(dict(path=str(p),sha256=sha(p),width=im.width,height=im.height,decode='PASS'))
                preview=im.convert('RGB');preview.thumbnail((2180,560));sheet.paste(preview,((2200-preview.width)//2,j*600+30));draw.text((12,j*600+8),p.name,fill='black')
        out=root/f'page_{start//3+1:02}.png';sheet.save(out);pages.append(str(out))
    rec=dict(at=now(),label=label,figures=records,inspection_pages=pages,scientific_verdict=None)
    dump(root/'receipt.json',rec);dump(D/'verification'/f'figure_decode_{label}.json',rec)
    print('VISUAL_PAGES_READY',label,len(files),len(pages),flush=True)
if __name__=='__main__':main(sys.argv[1])
