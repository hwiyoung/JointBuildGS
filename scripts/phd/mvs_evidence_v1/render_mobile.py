"""Mobile scientific figures from sealed prior/MVS evidence; CPU Docker only."""
import argparse
import csv
import hashlib
import json
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from matplotlib import colormaps


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    ap = argparse.ArgumentParser()
    ap.add_argument('--evidence', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--font', type=Path, required=True)
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    assert sha(args.evidence/'receipt.json') == cfg['parent_receipt_sha256']
    receipt = json.loads((args.evidence/'receipt.json').read_text())
    assert receipt['status'] == 'PASS_OBSERVATION_DIAGNOSTIC'
    sealed = {r['path']: r['sha256'] for r in receipt['outputs']}
    args.output.mkdir(exist_ok=False)
    inputs = []

    def checked(path):
        digest = sha(path)
        assert digest == sealed[str(path.relative_to(args.evidence))], path
        inputs.append({'path': str(path.relative_to(args.evidence)), 'sha256': digest})
        return path

    fonts = {s: ImageFont.truetype(str(args.font), s) for s in (24, 27, 30, 32, 40)}
    rows, pages = [], []
    palette = np.array([[180, 187, 197], [0, 0, 0], [247, 161, 31], [213, 63, 67]], dtype=np.uint8)
    colors = {'mvs': '#008c83', 'prior': '#2457c5', 'tie': '#9e55a0', 'insufficient': '#777c85'}
    for folder in sorted(args.evidence.glob('P*/view_*')):
        camera = json.loads(checked(folder/'camera.json').read_text())
        cid = camera['id']
        rgb = Image.open(checked(folder/'photo.jpg')).convert('RGB')
        with np.load(checked(folder/'arrays.npz'), allow_pickle=False) as a:
            pd, md, delta = a['prior_common_ray'], a['mvs_common_ray'], a['delta']
            valid = np.isfinite(pd) & (pd > 0) & np.isfinite(md) & (md > 0)
            assert np.array_equal(valid, a['validity'] == 3)
            assert np.allclose(delta[valid], (pd-md)[valid])
            candidate = valid & (np.abs(delta) > cfg['candidate_threshold_m'])
            category = np.zeros(valid.shape, np.uint8)
            category[valid] = 1
            category[candidate] = 2
            category[valid & (np.abs(delta) > cfg['large_difference_m'])] = 3
            uv = a['centers']
            ii, jj = uv[:, 0].astype(int), uv[:, 1].astype(int)
            pc = candidate[jj, ii]
            support = pc & (a['point_common_photo_views'] >= cfg['minimum_photo_views']) & np.isfinite(a['point_photo_margin'])
            margin = a['point_photo_margin']
            mvs = support & (margin > cfg['photo_margin_display_threshold'])
            prior = support & (margin < -cfg['photo_margin_display_threshold'])
            tie = support & ~(mvs | prior)
            insufficient = pc & ~support
            assert np.array_equal(pc, mvs | prior | tie | insufficient)
            assert int(candidate.sum()) == camera['summary']['candidate_counts']['0.5']
            percent = 100 * candidate.sum() / max(1, valid.sum())
            support_percent = 100 * support.sum() / max(1, pc.sum())
            row = dict(camera=cid, name=camera['name'], both_pixels=int(valid.sum()),
                       candidate_pixels=int(candidate.sum()), candidate_percent=float(percent),
                       candidate_grid_points=int(pc.sum()), photo_comparable=int(support.sum()),
                       photo_comparable_percent=float(support_percent), mvs_lower_cost=int(mvs.sum()),
                       prior_lower_cost=int(prior.sum()), similar_cost=int(tie.sum()),
                       insufficient_photo_support=int(insufficient.sum()),
                       candidate_profile_supported=int((pc & (a['point_profile_neighbor_count'] >= 2)).sum()))
            for t in (1., 2.):
                row[f'candidate_percent_{t:g}m'] = float(100*(valid & (np.abs(delta)>t)).sum()/max(1, valid.sum()))
            rows.append(row)
            Image.fromarray(category, 'L').save(args.output/f'{cid}_discrepancy_classes.png')
            np.savez_compressed(args.output/f'{cid}_masks.npz', both_valid=valid,
                                discrepancy_candidate=candidate, discrepancy_classes=category,
                                centers=uv, candidate_grid=pc, photo_comparable=support,
                                mvs_lower_photo_cost=mvs, prior_lower_photo_cost=prior,
                                similar_photo_cost=tie, insufficient_photo_support=insufficient)

            # Data overlays are calculated at source raster resolution. Missing != unchanged.
            base = np.asarray(rgb).astype(float)
            overlay = base.copy()
            for code, alpha in ((0, .78), (2, .70), (3, .70)):
                mask = category == code
                overlay[mask] = (1-alpha)*base[mask] + alpha*palette[code]
            overlay = Image.fromarray(np.uint8(overlay))
            support_img = Image.blend(rgb.convert('L').convert('RGB'), Image.new('RGB', rgb.size, 'white'), .22)
            sd = ImageDraw.Draw(support_img)
            for key, mask in [('insufficient', insufficient), ('tie', tie), ('prior', prior), ('mvs', mvs)]:
                for x, y in uv[mask]:
                    sd.ellipse((x-6, y-6, x+6, y+6), fill=colors[key])

            w, pad, gap = cfg['card_width_px'], 32, 16
            inner = w - 2*pad
            half = (inner-gap)//2
            half_h = round(half*rgb.height/rgb.width)
            full_h = round(inner*rgb.height/rgb.width)
            canvas = Image.new('RGB', (w, 2200), '#ffffff')
            draw = ImageDraw.Draw(canvas)
            y = 25

            def line(s, size=30, color='#172b3a'):
                nonlocal y
                draw.text((pad, y), s, font=fonts[size], fill=color)
                y += size + 14

            line(f'{cid.replace("_", " · 시점 ")}  |  Prior–MVS 비교', 40)
            line('입력 불일치 후보 · 실제 시간 변화는 미확정', 27, '#885a17')
            line(f'두 깊이가 있는 영역 중 차이 >0.5m: {percent:.1f}%', 32)
            line('① Prior 깊이                         Image 깊이(MVS)', 30)
            lo, hi = cfg['depth_display_m']
            for k, depth in enumerate((pd, md)):
                finite = np.isfinite(depth) & (depth > 0)
                depth_rgb = (255*colormaps['viridis'](np.clip((np.nan_to_num(depth)-lo)/(hi-lo), 0, 1))[..., :3]).astype(np.uint8)
                depth_rgb[~finite] = [185, 190, 198]
                canvas.paste(Image.fromarray(depth_rgb).resize((half, half_h)), (pad+k*(half+gap), y))
            y += half_h + 9
            bar = (255*colormaps['viridis'](np.linspace(0, 1, inner))[None, :, :3]).astype(np.uint8)
            canvas.paste(Image.fromarray(bar).resize((inner, 17)), (pad, y))
            y += 23
            for x, label, anchor in [(pad, '0m', 'lt'), (w//2, '75m', 'mt'), (w-pad, '150m', 'rt')]:
                draw.text((x, y), label, font=fonts[24], fill='#172b3a', anchor=anchor)
            y += 38
            line('같은 색척도 · camera-Z 깊이 · 회색은 결측', 24)
            y += 5
            line('② 깊이차 후보를 원사진 위에 표시', 32)
            canvas.paste(overlay.resize((inner, full_h)), (pad, y)); y += full_h + 10
            for x, text, color in [(pad, '0.5–2m', '#f7a11f'), (pad+240, '>2m', '#d53f43'), (pad+430, '비교 불가', '#b4bbc5')]:
                draw.rectangle((x, y+7, x+22, y+29), fill=color)
                draw.text((x+32, y), text, font=fonts[27], fill='#172b3a')
            y += 48
            line('색이 없는 비교 가능 영역: 차이 ≤0.5m', 24)
            line('③ 후보 격자점의 사진 비교 결과', 32)
            canvas.paste(support_img.resize((inner, full_h)), (pad, y)); y += full_h + 10
            for text, color in [('청록: MVS 사진 비용 작음  /  파랑: Prior 작음', colors['mvs']),
                                ('보라: 비용 유사  /  회색: 사진 비교 근거 부족', '#616775')]:
                line(text, 27, color)
            line(f'사진 비교 가능: {support.sum():,}/{pc.sum():,}점 ({support_percent:.1f}%)', 30)
            line('16px 격자점만 표시 · 낮은 비용은 정확도 확정 아님', 24)
            line('그림 ②는 불일치 마스크이며 최종 변화 마스크가 아닙니다.', 24, '#885a17')
            assert y < canvas.height, (cid, y)
            canvas = canvas.crop((0, 0, w, y+22))
            canvas.save(args.output/f'{cid}_mobile.png', optimize=True)
            pages.append(canvas)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    pages[0].save(args.output/'P1_P2_P3_mobile.pdf', save_all=True, append_images=pages[1:], resolution=110.)
    (args.output/'summary.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    with (args.output/'summary.csv').open('w', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (args.output/'class_legend.json').write_text(json.dumps({
        'raster': {'0': 'not_comparable_missing_depth', '1': 'both_depths_abs_delta_le_0.5m',
                   '2': 'both_depths_0.5m_lt_abs_delta_le_2m', '3': 'both_depths_abs_delta_gt_2m'},
        'counts': 'Camera-view raster pixels or sampled image points, not unique 3D area.',
        'photo': 'ZNCC cost on identical pixels and neighbors; no authority or change decision.',
        'scientific_verdict': None}, ensure_ascii=False, indent=2)+'\n')
    shutil.copy2(args.config, args.output/'config.json')
    shutil.copy2(__file__, args.output/'render_mobile.py')
    out_receipt = dict(task_id=cfg['task_id'], status='PASS_MOBILE_FIGURES', scientific_verdict=None,
                       created_at=datetime.now(timezone.utc).isoformat(),
                       parent_receipt_sha256=sha(args.evidence/'receipt.json'),
                       script_sha256=sha(__file__),config_sha256=sha(args.config),font_sha256=sha(args.font),
                       python=platform.python_version(),numpy=np.__version__,inputs=inputs,
                       runtime_image=receipt['runtime']['image_id'],
                       cameras=len(rows),inline_selection=cfg['inline_selection'],
                       checks='All source hashes, validity masks, delta arithmetic, parent candidate counts, exhaustive photo categories, and canvas bounds passed.',
                       outputs=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(args.output.iterdir()) if p.is_file()])
    (args.output/'receipt.json').write_text(json.dumps(out_receipt,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    main()
