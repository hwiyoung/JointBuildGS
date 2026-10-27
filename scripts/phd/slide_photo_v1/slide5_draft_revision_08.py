"""Page-5 matched-pair draft from frozen measured sections, CPU only."""
import io
import os
import platform
import zipfile

from PIL import Image, ImageDraw, ImageFont

from common import CFG, DOC, G, PAY, REPO, RAW, dump, load, now, np, plot_setup, sha

OUT = DOC / 'revision_08'
CACHE = PAY / 'revision_08'
SCALE = 2
INK = '#172B40'
MUTED = '#5B6B7C'
PRIOR = '#C08A2B'
MVS = '#2C6AA0'
REF = '#3A4A5E'
BG = '#FFFFFF'
TEXT_RECORDS = []


def font(size, bold=False):
    return ImageFont.truetype('/fonts/NotoSansCJK-' + ('Bold' if bold else 'Regular') + '.ttc', round(size * SCALE))


def text(im, xy, value, size, colour=INK, bold=False, anchor='lt'):
    d = ImageDraw.Draw(im)
    p = tuple(round(v * SCALE) for v in xy)
    f = font(size, bold)
    box = d.textbbox(p, value, font=f, anchor=anchor)
    assert box[0] >= 0 and box[1] >= 0 and box[2] <= im.width and box[3] <= im.height, (value, box)
    d.text(p, value, font=f, fill=colour, anchor=anchor)
    TEXT_RECORDS.append(dict(text=value, size_display_px=size, bbox_export_px=box))


def line(im, points, fill, width=1):
    ImageDraw.Draw(im).line([tuple(round(v*SCALE) for v in p) for p in points], fill=fill, width=round(width*SCALE))


def photo(meta, key):
    pm = meta['photo']
    src = pm['source']['photo']
    with zipfile.ZipFile(RAW) as archive:
        raw = archive.read(src['original_member'])
    import hashlib
    assert hashlib.sha256(raw).hexdigest() == src['original_sha256']
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    if pm['display_rotation_deg'] == 90:
        im = im.transpose(Image.Transpose.ROTATE_90)
    crop = pm['crop_in_rotated_native_px']
    im = im.crop(crop).resize((880, 489), Image.Resampling.LANCZOS)
    q = np.asarray(pm['section_line_display_px']) * [880/1080, 489/600]
    # The previous exact photographic projection is also checked independently.
    X = np.asarray(pm['section_line_xyz'] if key == 'roof' else pm['section_centre_line_xyz'])
    pose = dict(src['pose'], R=np.asarray(src['pose']['R']), t=np.asarray(src['pose']['t']))
    native, _ = G.project(X, pose, src['camera'])
    if pm['display_rotation_deg'] == 90:
        native = np.c_[native[:,1], src['camera']['w'] - native[:,0]]
    expected = (native - np.asarray(crop[:2])) * [880/(crop[2]-crop[0]), 489/(crop[3]-crop[1])]
    assert np.allclose(q, expected), 'Photo line must remain the projected measured section'
    hidden = np.asarray(pm.get('section_hidden_segments', np.zeros(len(q)-1, bool)))
    d = ImageDraw.Draw(im)
    for j, (a, b) in enumerate(zip(q[:-1], q[1:])):
        if hidden[j] and j % 4 >= 2:
            continue
        d.line([tuple(a), tuple(b)], fill=INK, width=8)
        d.line([tuple(a), tuple(b)], fill='#FFD60A', width=4)
    # Labels are outside the measured section rather than coloured surface masks.
    for k, name in [(0, 'A'), (-1, 'A′')]:
        pt = q[k]
        d.ellipse((*tuple(pt-6), *tuple(pt+6)), fill='#FFD60A', outline=INK, width=2)
        offset = np.array([-34, 24] if key == 'roof' and k == 0 else [-25, -70])
        if key == 'wall':
            offset = np.array([-68, -66] if k == 0 else [10, -66])
        xy = np.clip(pt+offset, [12, 12], [im.width-90, im.height-80])
        f = font(28, True)
        bb = d.textbbox(tuple(xy), name, font=f, anchor='lt')
        d.rounded_rectangle((bb[0]-9, bb[1]-6, bb[2]+9, bb[3]+6), radius=6, fill='white')
        d.text(tuple(xy), name, font=f, fill=INK, anchor='lt')
    im.save(CACHE / f'{key}_locator.png')
    return im, dict(source_member=src['original_member'], source_sha256=src['original_sha256'], crop=crop,
                    section_line_px=q, projection_replay_max_error_px=float(np.max(abs(q-expected))),
                    section_line_meaning='Centre of the measured section band, not a boundary or material mask',
                    hidden_segments_dashed=bool(np.any(hidden)))


def chart(row, which):
    plt = plot_setup(17.28)  # 24 display pixels at 100 dpi; export at 2x.
    fig = plt.figure(figsize=(5.90, 2.65), dpi=200, facecolor=BG)
    ax = fig.add_axes([.11, .26, .86, .66])
    x = row['x']
    y = row[which]
    g = row['reference']
    colour = PRIOR if which == 'prior' else MVS
    if row['key'] == 'wall':
        ax.fill_between(x, g-20, g+20, color='#E7ECF1', linewidth=0, zorder=0)
    ax.plot(x, y, color=colour, lw=2.5, linestyle=(0, (5, 3)) if which == 'prior' else '-', zorder=3)
    ax.scatter(x, g, color=REF, s=17, zorder=4)
    ax.set_xlim(row['xlim']); ax.set_ylim(row['ylim'])
    ax.set_xticks(row['xticks']); ax.set_yticks(row['yticks'])
    ax.tick_params(axis='both', labelsize=17.28, colors=MUTED, length=0, pad=6)
    ax.spines['bottom'].set_color('#C1CBD5'); ax.spines['left'].set_visible(False)
    ax.set_axisbelow(True); ax.grid(axis='y', color='#E5EAF0', lw=.7)
    ax.set_xlabel('A → A′ 거리 (m)', fontsize=17.28, color=MUTED, labelpad=4)
    fig.text(.11, .99, row['axis_label'], va='top', color=MUTED, fontsize=17.28)
    path = CACHE / f'{row["key"]}_{which}.png'
    fig.savefig(path, dpi=200, facecolor=BG)
    # Verify render limits preserve every displayed value and tolerance bound.
    assert np.all((y[np.isfinite(y)] >= row['ylim'][0]) & (y[np.isfinite(y)] <= row['ylim'][1]))
    assert np.all((g[np.isfinite(g)] >= row['ylim'][0]) & (g[np.isfinite(g)] <= row['ylim'][1]))
    if row['key'] == 'wall':
        assert np.nanmin(g-20) >= row['ylim'][0] and np.nanmax(g+20) <= row['ylim'][1]
    axis_record = dict(xlim=list(ax.get_xlim()), ylim=list(ax.get_ylim()), xticks=list(ax.get_xticks()), yticks=list(ax.get_yticks()))
    plt.close(fig)
    return Image.open(path).convert('RGB'), axis_record


def main():
    config_path = CFG / 'slide5_draft_revision_08.json'
    config = load(config_path)
    locked = dict(task_id=config['task_id'], locked_at=now(), config_sha256=sha(config_path), sources=config['sources'])
    lock_path = OUT / 'input_lock.json'
    if lock_path.exists():
        assert load(lock_path)['config_sha256'] == locked['config_sha256']
    else:
        dump(lock_path, locked)  # Persist before any drawing.
    sources = {}
    for key, rec in config['sources'].items():
        assert sha(rec['path']) == rec['sha256'], key
        sources[key] = load(rec['path'])
    roof = sources['roof']['examples'][0]
    wall = sources['wall']
    H = np.asarray(roof['heights_model_m']) - roof['reference_zero_model_m']
    assert np.allclose(H, roof['heights_relative_m'], equal_nan=True)
    assert np.array_equal(np.asarray(sources['roof_photo']['comparison']['height_values']), np.asarray(roof['heights_model_m']), equal_nan=True)
    rows = [dict(key='roof', x=np.asarray(roof['bin_centres_m']), prior=H[:,0], mvs=H[:,1], reference=H[:,2],
                 xlim=[0,12], ylim=[-.6,9.5], xticks=[0,6,12], yticks=[0,4,8], axis_label='상대 높이 (m)',
                 reference_origin_model_m=roof['reference_zero_model_m'], section_half_width_m=roof['half_width_m']),
            dict(key='wall', x=np.asarray(wall['bin_centres_m'])+3,
                 **{('reference' if k == 'gt' else k): np.asarray(wall['series'][k]['median'])*100 for k in ['gt','prior','mvs']},
                 xlim=[0,6], ylim=[-65,30], xticks=[0,3,6], yticks=[-60,-30,0], axis_label='벽의 앞뒤 위치 (cm)',
                 section_half_width_m=wall['section_half_width_m'], normal=wall['source_view']['axis2'])]
    im = Image.new('RGB', (3840,2160), BG)
    text(im, (64,35), '두 자료의 오류', 25, MUTED)
    text(im, (64,82), '사전 정보와 영상은 서로 다른 곳에서 어긋난다', 46, bold=True)
    text(im, (64,146), '같은 위치의 단면에서, 두 자료를 동일한 참조와 비교', 28, MUTED)
    text(im, (1848,146), '●  참조: 2024 드론 LiDAR', 26, REF, anchor='rt')
    text(im, (64,202), '사진에서 위치 확인', 28, MUTED)
    text(im, (640,202), '사전 정보  prior', 32, PRIOR, True)
    text(im, (1250,202), '영상 기반 형상  MVS', 32, MVS, True)
    line(im, [(640,245),(1230,245)], PRIOR, 3)
    line(im, [(1250,245),(1840,245)], MVS, 3)
    records = []
    for i, row in enumerate(rows):
        y = 271 + i*396
        pic, photo_record = photo(sources[row['key']+'_photo'], row['key'])
        im.paste(pic, (128, round((y+46)*2)))
        text(im, (64,y), '01  바뀐 지붕' if i == 0 else '02  깊이가 어긋난 벽', 32, bold=True)
        text(im, (640,y), '2022 항공 LiDAR' if i == 0 else '기존 LoD2 벽면', 27, MUTED)
        text(im, (1250,y), '현재 영상에서 추정한 형상', 27, MUTED)
        text(im, (64,y+304), 'A–A′  지붕 단면 · B173' if i == 0 else 'A–A′  벽면의 위치 차이 확대', 25, MUTED)
        pairs = {}
        for which, x in [('prior',640),('mvs',1250)]:
            plot, axis_record = chart(row, which)
            im.paste(plot, (x*2, round((y+39)*2)))
            pairs[which] = axis_record
        assert pairs['prior'] == pairs['mvs'], 'Matched panels must have identical axes'
        if i == 0:
            captions = ['옛 지붕이 현재 참조보다 높음', '현재 참조에 가까운 형상']
        else:
            captions = ['참조의 허용 범위 안에 위치', '깊이는 있지만 위치가 어긋남']
        for x, value, col in zip([640,1250], captions, [PRIOR,MVS]):
            text(im, (x,y+310), value, 28, col, True)
        records.append(dict(**row, photo=photo_record, axes=pairs, captions=captions))
    line(im, [(64,636),(1840,636)], '#DDE4EB', 1)
    text(im, (64,1040), '선·점: 구간 대표값 · 같은 행은 같은 축척 · 아래: 벽 앞뒤 차이 확대 · 회색 띠: 참조 ±20 cm (허용 범위)', 24, MUTED)
    fig = OUT / 'figures'; fig.mkdir(exist_ok=True)
    preview = OUT / 'previews'; preview.mkdir(exist_ok=True)
    im.save(fig / 'slide5_prior_image_pairs.png')
    im.resize((1920,1080), Image.Resampling.LANCZOS).save(preview / 'slide5_prior_image_pairs.png')
    meta = dict(task_id=config['task_id'], scientific_verdict=None, created_at=now(), config_sha256=sha(config_path),
                sources=config['sources'], rows=records, export_size_px=list(im.size), display_size_px=[1920,1080],
                text_records=TEXT_RECORDS, minimum_main_text_display_px=min(t['size_display_px'] for t in TEXT_RECORDS),
                all_full_section_bins_retained=True, curve_smoothing=False, all_values_and_tolerance_visible=True,
                limitations=['Section curves summarize existing bins, not all raw points or a reconstructed continuous mesh.',
                             'Axes differ across rows. Wall vertical axis is the original surface normal, not roof height.',
                             'Source agreement is reference agreement, not independent truth validation.',
                             'The metal appearance does not establish the cause of depth errors.',
                             'Only two fixed examples; no new training, result selection, or population claim.'],
                crs='EPSG:25832 source; figures use documented source-local section coordinates')
    dump(fig / 'slide5_prior_image_pairs.json', meta)
    import PIL, matplotlib
    dump(OUT / 'verification.json', dict(task_id=config['task_id'], scientific_verdict=None, verified_at=now(),
         base_commit=os.environ['TASK_BASE_COMMIT'], script_sha256=sha(REPO/'scripts/phd/slide_photo_v1/slide5_draft_revision_08.py'),
         versions=dict(python=platform.python_version(), numpy=np.__version__, pillow=PIL.__version__, matplotlib=matplotlib.__version__),
         checks=dict(source_hashes_match=True, full_frozen_sections=True, roof_origin_replay=True, roof_R6_exact_values=True,
                     photo_projection_replay=True, reference_identical_per_pair=True, axes_identical_per_pair=True,
                     complete_axis_coverage=True, text_inside_canvas=True, no_data_smoothing=True, no_training=True),
         files={str(p.relative_to(OUT)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in [fig/'slide5_prior_image_pairs.png',preview/'slide5_prior_image_pairs.png']}))
    print('R8 slide-5 draft saved; rows:', [(r['key'], len(r['x'])) for r in rows], flush=True)


if __name__ == '__main__':
    main()
