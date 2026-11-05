from common import *
from PIL import Image,ImageOps,ImageDraw
rank=json.loads((O/'ranking.json').read_text());images=[];checks=[]
for r in rank['top5']:
    for suffix in ['가_위에서','나_경사사진']:
        p=D/'figures'/f"{r['building']}_{suffix}.png"
        with Image.open(p) as im:
            im.load();assert im.size==(3000,2400);dpi=im.info.get('dpi');assert dpi and abs(dpi[0]-300)<.01
            thumb=im.convert('RGB');thumb.thumbnail((600,480));images.append(thumb.copy())
            checks.append(dict(file=p.name,dimensions=list(im.size),dpi=list(dpi),sha256=sha(p),decode='PASS'))
        j=json.loads(p.with_suffix('.json').read_text());assert j['building']==r['building'] and j['scientific_verdict'] is None
        for s in j['sources']:assert sha(s['path'])==s['sha256'],s['path']
sheet=Image.new('RGB',(1200,480*5),'white')
for i,im in enumerate(images):sheet.paste(im,((i%2)*600,(i//2)*480))
sheet.save(O/'contact_sheet.jpg',quality=95)
dump(D/'provenance/figure_decode.json',dict(at=now(),figures=checks,scientific_verdict=None));print('FIGURE_DECODE_PASS',len(checks),str(O/'contact_sheet.jpg'))
