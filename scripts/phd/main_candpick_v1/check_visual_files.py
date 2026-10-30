"""Check exported figure files and make a contact sheet for human/model review."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from input_audit import sha
from result_io import save


def main():
    root = Path('/docs/figures')
    names = json.loads((root / 'quantitative_index.json').read_text())['files']
    reps = json.loads((root / 'representatives/index.json').read_text())['representatives']
    for rep in reps:
        names.extend('representatives/' + p for p in rep['files'])
    for unit in ['B173_ALS', 'R1_LoD2']:
        index = root / 'representatives' / (unit + '_photos_index.json')
        if index.exists(): names.extend('representatives/' + p for p in json.loads(index.read_text())['files'])
    rows = []
    thumbs = []
    font = ImageFont.truetype('/out/assets/NotoSansCJK-Regular.ttc', 12)
    for name in names:
        p = root / name
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            im = im.convert('RGB'); width, height = im.size
            assert width >= 800 and height >= 500, name
            extrema = im.getextrema(); assert any(low < high for low, high in extrema), name
            im.thumbnail((384, 272))
            tile = Image.new('RGB', (400, 310), 'white'); tile.paste(im, ((400 - im.width) // 2, 20))
            ImageDraw.Draw(tile).text((6, 290), p.stem, font=font, fill='black'); thumbs.append(tile)
        pdf = p.with_suffix('.pdf'); data = pdf.read_bytes()
        assert data.startswith(b'%PDF-') and b'%%EOF' in data[-1024:], pdf
        rows.append(dict(file=name, width=width, height=height, png_sha256=sha(p),
                         pdf_sha256=sha(pdf), pdf_check='header and EOF only; same source figure as PNG'))
    cols = 4; contact = Image.new('RGB', (400 * cols, 310 * ((len(thumbs) + cols - 1) // cols)), '#dddddd')
    for i, tile in enumerate(thumbs): contact.paste(tile, ((i % cols) * 400, (i // cols) * 310))
    contact.save(root / 'contact_sheet.png')
    report = dict(status='PASS_FILE_CHECKS', figure_count=len(rows), figures=rows,
                  visual_acceptance='PENDING separate visual_review.json', scientific_verdict=None)
    save(Path('/docs/visual_file_checks.json'), report)
    print('Checked', len(rows), 'PNG/PDF pairs; contact sheet created')


if __name__ == '__main__': main()
