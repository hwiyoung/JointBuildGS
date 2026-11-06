"""Decode only the recovered arm figures and save an inspection sheet."""
import sys
from PIL import Image, ImageDraw
from common import O, D, sha, dump, now


def main(site, prior, arm):
    folder = D/'figures/addendum2' if arm == 'fix' else D/'figures'
    paths = sorted(folder.glob(f'{site}__{prior}_{arm}_*.png'))
    assert len(paths) >= 3
    sheet = Image.new('RGB', (2200, 600*len(paths)), 'white')
    draw = ImageDraw.Draw(sheet)
    rows = []
    for i, path in enumerate(paths):
        with Image.open(path) as image:
            image.load()
            assert image.width > 1000 and image.height > 1000
            rows.append(dict(path=str(path), sha256=sha(path), width=image.width,
                             height=image.height, decode='PASS'))
            thumbnail = image.convert('RGB')
            thumbnail.thumbnail((2180, 560))
            sheet.paste(thumbnail, ((2200-thumbnail.width)//2, i*600+30))
            draw.text((12, i*600+8), path.name, fill='black')
    out = O/'verification/visuals/recovery_20261106'/f'{site}__{prior}__{arm}.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    dump(D/'verification'/f'addendum2_recovery_figures_{site}__{prior}__{arm}.json',
         dict(at=now(), figures=rows, inspection_sheet=str(out), human_visual_inspection='pending',
              scientific_verdict=None))
    print('RECOVERED_FIGURES_DECODED', str(out), flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
