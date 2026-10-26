"""Paginated visual QA sheets for the generated scientific figures."""
import argparse
from PIL import Image,ImageDraw
from common import *
def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage');a=ap.parse_args();records=[]
    for kind in ['curve','map','section','montage','overall']:
        files=sorted((D/'figures'/a.stage).glob(kind+'_*.png'))
        for page in range((len(files)+5)//6):
            fs=files[page*6:(page+1)*6];canvas=Image.new('RGB',(2400,550*((len(fs)+2)//3)),'white')
            for i,f in enumerate(fs):
                with Image.open(f) as src:im=src.convert('RGB');im.thumbnail((800,525))
                canvas.paste(im,((i%3)*800,(i//3)*550));ImageDraw.Draw(canvas).text(((i%3)*800+5,(i//3)*550+530),f.stem,fill='black')
            path=O/'tmp'/f'{a.stage}_{kind}_{page+1}.jpg';canvas.save(path,quality=93);records.append(dict(sheet=str(path),files=[dict(file=str(f.relative_to(D)),sha256=sha(f)) for f in fs]))
    dump(O/'inspection'/f'{a.stage}_qa_sheets.json',records);print('QA sheets',len(records))
if __name__=='__main__':main()
