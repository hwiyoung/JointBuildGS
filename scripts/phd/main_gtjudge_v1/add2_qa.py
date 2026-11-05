import sys
from common import *
from PIL import Image,ImageDraw
label=sys.argv[1];root=O/'verification/visuals/addendum2'/label;root.mkdir(parents=True,exist_ok=True)
files=sorted((D/'figures/addendum2').glob('*.png'))
if label=='cpu':files=[p for p in files if '_fix_' not in p.name]+[p for s in ['B173nb_b10','B0_b10'] for p in (D/'figures').glob(s+'__LoD2_stage2_*.png')]
else:files=[p for p in files if '_fix_' in p.name]
records=[];pages=[]
for begin in range(0,len(files),3):
    sheet=Image.new('RGB',(2200,1800),'white');draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(files[begin:begin+3]):
        with Image.open(p) as im:
            im.load();assert im.width>1000 and im.height>1000
            records.append(dict(path=str(p),sha256=sha(p),width=im.width,height=im.height,decode='PASS'))
            image=im.convert('RGB');image.thumbnail((2180,560));sheet.paste(image,((2200-image.width)//2,j*600+30));draw.text((12,j*600+8),p.name,fill='black')
    out=root/f'page_{begin//3+1:02}.png';sheet.save(out);pages.append(str(out))
dump(root/'receipt.json',dict(at=now(),figures=records,inspection_pages=pages,scientific_verdict=None));dump(D/'verification'/f'addendum2_{label}_decode.json',dict(at=now(),figures=records,scientific_verdict=None));print('ADD2_QA_READY',label,len(files),flush=True)
